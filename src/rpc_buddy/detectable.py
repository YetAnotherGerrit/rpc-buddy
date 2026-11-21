"""Discord's list of detectable games.

Maps a store's product id (e.g. a Steam app id) to the game's official
Discord application, with name and artwork. Discord lists the stores as
"distributors": steam, epic, gog, xbox, … — modules pass their own.

Memory: the list is ~13 MB of JSON. Parsing it would leave the app ~60 MB
bigger for good (Python keeps freed memory), so it is downloaded and indexed
in a short-lived child process (``python -m rpc_buddy.detectable --refresh``)
that writes a small SQLite database; the app only queries single rows.
"""

import asyncio
import json
import logging
import os
import sqlite3
import sys
import time
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from rpc_buddy import __version__

log = logging.getLogger(__name__)

DETECTABLE_URL = "https://discord.com/api/v10/applications/detectable"
USER_AGENT = f"rpc-buddy/{__version__} (+https://github.com/YetAnotherGerrit/rpc-buddy)"
CDN = "https://cdn.discordapp.com/app-icons"

SCHEMA_VERSION = 3
DB_NAME = "detectable.sqlite3"
REFRESH_TIMEOUT = 180.0  # seconds

# distributor -> sku id -> (discord app id, name, icon hash, cover hash)
Index = dict[str, dict[str, tuple]]


@dataclass(frozen=True)
class DiscordGame:
    app_id: str
    name: str
    icon_hash: str | None
    cover_hash: str | None

    @property
    def image_url(self) -> str | None:
        """Cover art if available, otherwise the icon."""
        h = self.cover_hash or self.icon_hash
        return f"{CDN}/{self.app_id}/{h}.png" if h else None


def build_index(apps: list[dict]) -> Index:
    index: Index = {}
    for app in apps:
        for sku in app.get("third_party_skus") or []:
            distributor, sku_id = sku.get("distributor"), sku.get("id")
            if distributor and sku_id:
                index.setdefault(distributor, {})[str(sku_id)] = (
                    str(app["id"]),
                    app.get("name") or "",
                    app.get("icon_hash"),
                    app.get("cover_image_hash"),
                )
    return index


def fetch_detectable() -> list[dict]:
    req = urllib.request.Request(DETECTABLE_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


# --- database -----------------------------------------------------------------


def write_database(path: Path, index: Index, fetched_at: float) -> None:
    """Write the index to ``path`` atomically (readers never see a half file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    with sqlite3.connect(tmp) as db:
        db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT) WITHOUT ROWID")
        db.execute(
            "CREATE TABLE games (distributor TEXT, sku TEXT, app_id TEXT, name TEXT, "
            "icon TEXT, cover TEXT, PRIMARY KEY (distributor, sku)) WITHOUT ROWID"
        )
        db.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [("version", str(SCHEMA_VERSION)), ("fetched_at", repr(fetched_at))],
        )
        db.executemany(
            "INSERT INTO games VALUES (?, ?, ?, ?, ?, ?)",
            ((d, sku, *entry) for d, skus in index.items() for sku, entry in skus.items()),
        )
    os.replace(tmp, path)


def refresh_database(path: Path, fetch: Callable[[], list[dict]] = fetch_detectable) -> Index:
    """Download, index and store the list. Meant to run in the child process."""
    if path.exists() and not path.is_file():
        raise IsADirectoryError(f"Not a file: {path}")  # fail before downloading
    index = build_index(fetch())
    write_database(path, index, time.time())
    return index


def read_fetched_at(path: Path) -> float | None:
    """When the database was written, or None if it is missing/unusable."""
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            meta = dict(db.execute("SELECT key, value FROM meta"))
        if meta.get("version") != str(SCHEMA_VERSION):
            return None
        return float(meta["fetched_at"])
    except (sqlite3.Error, KeyError, ValueError):
        return None


def query_game(path: Path, distributor: str, sku_id: str) -> DiscordGame | None:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        row = db.execute(
            "SELECT app_id, name, icon, cover FROM games WHERE distributor = ? AND sku = ?",
            (distributor, sku_id),
        ).fetchone()
    return DiscordGame(*row) if row else None


async def refresh_in_subprocess(path: Path) -> None:
    """Run the refresh in a child process; its memory is returned when it exits."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "rpc_buddy.detectable",
        "--refresh",
        str(path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), REFRESH_TIMEOUT)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("Refreshing the game list timed out") from None
    if proc.returncode != 0:
        lines = stderr.decode(errors="replace").strip().splitlines() or ["unknown error"]
        raise RuntimeError(lines[-1])


# --- cache --------------------------------------------------------------------


class DetectableCache:
    """Store -> Discord lookups, refreshed at most once a day."""

    MAX_AGE = 24 * 3600
    MISS_REFRESH_AGE = 6 * 3600  # refresh early on a miss if the list is this old

    def __init__(
        self,
        cache_dir: Path,
        refresh: Callable[[Path], Awaitable[None]] = refresh_in_subprocess,
    ):
        self.path = cache_dir / DB_NAME
        self._refresh_db = refresh
        self._fetched_at: float | None = None
        self._loaded = False
        self._lock = asyncio.Lock()
        for old in ("detectable-steam.json", "detectable-index.json"):  # older formats
            (cache_dir / old).unlink(missing_ok=True)

    async def lookup(self, distributor: str, sku_id: str) -> DiscordGame | None:
        """Find the Discord game for a store product, e.g. ``("steam", "1000001")``."""
        async with self._lock:
            if not self._loaded:
                self._loaded = True
                self._fetched_at = read_fetched_at(self.path)
            if self._fetched_at is None or self._age() > self.MAX_AGE:
                await self._refresh()
            game = self._query(distributor, sku_id)
            if game is None and self._age() > self.MISS_REFRESH_AGE:
                await self._refresh()
                game = self._query(distributor, sku_id)
        return game

    def _query(self, distributor: str, sku_id: str) -> DiscordGame | None:
        if self._fetched_at is None:
            return None
        try:
            return query_game(self.path, distributor, sku_id)
        except sqlite3.Error as e:
            log.warning("Could not read the game list: %s", e)
            return None

    def _age(self) -> float:
        return time.time() - (self._fetched_at or 0.0)

    async def _refresh(self) -> None:
        log.info("Downloading Discord's list of detectable games")
        try:
            await self._refresh_db(self.path)
        except Exception as e:
            if self._fetched_at is None:
                raise
            log.warning("Could not refresh the game list, keeping the old one: %s", e)
            self._fetched_at = time.time() - self.MAX_AGE + 3600  # retry in an hour
            return
        self._fetched_at = read_fetched_at(self.path)
        if self._fetched_at is None:
            raise RuntimeError("The refreshed game list could not be read")
        log.info("Game list updated")


def _main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "--refresh":
        print("usage: python -m rpc_buddy.detectable --refresh <database>", file=sys.stderr)
        return 2
    try:
        index = refresh_database(Path(argv[2]))
    except Exception as e:  # noqa: BLE001 - reported to the parent via stderr
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(", ".join(f"{d}: {len(skus)}" for d, skus in sorted(index.items())))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))

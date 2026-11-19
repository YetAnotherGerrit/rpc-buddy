"""Discord's list of detectable games.

Maps a store's product id (e.g. a Steam app id) to the game's official
Discord application, with name and artwork. Discord lists the stores as
"distributors": steam, epic, gog, xbox, … — modules pass their own.
"""

import asyncio
import json
import logging
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rpc_buddy import __version__

log = logging.getLogger(__name__)

DETECTABLE_URL = "https://discord.com/api/v10/applications/detectable"
USER_AGENT = f"rpc-buddy/{__version__} (+https://github.com/YetAnotherGerrit/rpc-buddy)"
CDN = "https://cdn.discordapp.com/app-icons"

INDEX_VERSION = 2

# distributor -> sku id -> [discord app id, name, icon hash, cover hash]
Index = dict[str, dict[str, list]]


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
                index.setdefault(distributor, {})[str(sku_id)] = [
                    str(app["id"]),
                    app.get("name") or "",
                    app.get("icon_hash"),
                    app.get("cover_image_hash"),
                ]
    return index


def fetch_detectable() -> list[dict]:
    req = urllib.request.Request(DETECTABLE_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


class DetectableCache:
    """Store -> Discord index, downloaded at most once a day and cached on disk."""

    MAX_AGE = 24 * 3600
    MISS_REFRESH_AGE = 6 * 3600  # refresh early on a miss if the index is this old

    def __init__(self, cache_dir: Path, fetch: Callable[[], list[dict]] = fetch_detectable):
        self.path = cache_dir / "detectable-index.json"
        self._fetch = fetch
        self._index: Index | None = None
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def lookup(self, distributor: str, sku_id: str) -> DiscordGame | None:
        """Find the Discord game for a store product, e.g. ``("steam", "1000001")``."""
        async with self._lock:
            if self._index is None:
                self._load_from_disk()
            if self._index is None or self._age() > self.MAX_AGE:
                await self._refresh()
            entry = self._get(distributor, sku_id)
            if entry is None and self._age() > self.MISS_REFRESH_AGE:
                await self._refresh()
                entry = self._get(distributor, sku_id)
        return DiscordGame(*entry) if entry else None

    def _get(self, distributor: str, sku_id: str) -> list | None:
        return (self._index or {}).get(distributor, {}).get(sku_id)

    def _age(self) -> float:
        return time.time() - self._fetched_at

    def _load_from_disk(self) -> None:
        try:
            data = json.loads(self.path.read_text())
            if data.get("version") == INDEX_VERSION:
                self._index = data["index"]
                self._fetched_at = float(data["fetched_at"])
                log.debug("Loaded game list from %s", self.path)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError) as e:
            log.warning("Ignoring broken cache %s: %s", self.path, e)

    async def _refresh(self) -> None:
        log.info("Downloading Discord's list of detectable games")
        try:
            apps = await asyncio.to_thread(self._fetch)
        except Exception as e:
            if self._index is None:
                raise
            log.warning("Could not refresh the game list, keeping the old one: %s", e)
            self._fetched_at = time.time() - self.MAX_AGE + 3600  # retry in an hour
            return
        self._index = build_index(apps)
        self._fetched_at = time.time()
        counts = ", ".join(f"{d}: {len(skus)}" for d, skus in sorted(self._index.items()))
        log.info("Game list updated (%s)", counts)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(
                    {"version": INDEX_VERSION, "fetched_at": self._fetched_at, "index": self._index}
                )
            )
        except OSError as e:
            log.warning("Could not write cache %s: %s", self.path, e)

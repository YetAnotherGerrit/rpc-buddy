"""Steam's own online status (Online, Invisible, Offline, …).

Steam's UI stores the status the user picked in ``localconfig.vdf``::

    "UserLocalConfigStore" > "WebStorage" >
        "FriendStoreLocalPrefs_<account id>"  "{\\"ePersonaState\\":7,…}"

and rewrites the file within seconds of a change (verified 2026-11). This is
undocumented: if the file or the entry can't be found, the status is
unknown and RPC Buddy behaves as if the user were online.
"""

import logging
import re
import time
from collections.abc import Callable
from pathlib import Path

from rpc_buddy.modules.steam.paths import steam_roots

log = logging.getLogger(__name__)

# Steam's EPersonaState values in which friends can't see you online.
OFFLINE = 0
INVISIBLE = 7
HIDDEN_STATES = frozenset({OFFLINE, INVISIBLE})

SEARCH_INTERVAL = 60.0  # seconds between searches for the active account's file

_STATE_RE = re.compile(r'ePersonaState\\?"\s*:\s*(\d+)')


def parse_persona_state(text: str) -> int | None:
    """The ``ePersonaState`` stored in a localconfig.vdf, if present."""
    for line in text.splitlines():
        if '"FriendStoreLocalPrefs_' in line:
            match = _STATE_RE.search(line)
            if match:
                return int(match.group(1))
    return None


def find_localconfig(roots: list[Path] | None = None) -> Path | None:
    """The localconfig.vdf of the logged-in account (the most recently written one)."""
    candidates = []
    seen = set()
    for root in roots if roots is not None else steam_roots():
        try:
            for path in root.glob("userdata/*/config/localconfig.vdf"):
                real = path.resolve()
                if real not in seen:
                    seen.add(real)
                    candidates.append((path.stat().st_mtime, path))
        except OSError:
            continue
    return max(candidates)[1] if candidates else None


class PersonaWatcher:
    """Reads the Steam status, re-reading the file only when it changed."""

    def __init__(
        self,
        find: Callable[[], Path | None] = find_localconfig,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._find = find
        self._clock = clock
        self._path: Path | None = None
        self._searched_at: float | None = None
        self._mtime: float | None = None
        self._state: int | None = None

    def state(self) -> int | None:
        now = self._clock()
        if self._searched_at is None or now - self._searched_at >= SEARCH_INTERVAL:
            self._searched_at = now
            path = self._find()
            if path != self._path:
                self._path, self._mtime, self._state = path, None, None
                if path is None:
                    log.info("Steam status not found; Invisible can't be respected")
        if self._path is None:
            return None
        try:
            mtime = self._path.stat().st_mtime
            if mtime != self._mtime:
                self._mtime = mtime
                self._state = parse_persona_state(
                    self._path.read_text(encoding="utf-8", errors="replace")
                )
                log.debug("Steam status: %s", self._state)
        except OSError:
            self._state = None
        return self._state

    def hidden(self) -> bool:
        """True while the user is Invisible or Offline on Steam."""
        return self.state() in HIDDEN_STATES

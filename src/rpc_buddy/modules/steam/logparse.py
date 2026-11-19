"""Parsing Steam's console_log.txt to find out which game is running.

Steam logs one line per state change of a game's process tree::

    [2026-01-01 12:00:00] Game process added : AppID 1000001 "…"
    [2026-01-01 12:00:05] Game process updated : AppID 1000001 "…"
    [2026-01-01 13:15:00] Game process removed: AppID 1000001 "…"
"""

import re
import time
from dataclasses import dataclass

_LINE_RE = re.compile(
    r"^\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] "
    r"Game process (?P<kind>added|updated|removed)\s*: AppID (?P<appid>\d+)\b"
)


@dataclass(frozen=True)
class SteamEvent:
    kind: str  # "added" | "updated" | "removed"
    appid: str
    timestamp: int  # Unix seconds (Steam logs local time)


def parse_line(line: str) -> SteamEvent | None:
    m = _LINE_RE.match(line)
    if not m:
        return None
    ts = int(time.mktime(time.strptime(m["ts"], "%Y-%m-%d %H:%M:%S")))
    return SteamEvent(kind=m["kind"], appid=m["appid"], timestamp=ts)


@dataclass(frozen=True)
class RunningGame:
    appid: str
    started: int


class GameTracker:
    """Keeps track of running games; the most recently started one wins."""

    def __init__(self) -> None:
        self._running: dict[str, int] = {}

    def reset(self) -> None:
        self._running.clear()

    def feed(self, event: SteamEvent) -> None:
        if event.kind == "removed":
            self._running.pop(event.appid, None)
        else:
            self._running.setdefault(event.appid, event.timestamp)

    def current(self) -> RunningGame | None:
        if not self._running:
            return None
        appid = max(self._running, key=lambda a: self._running[a])
        return RunningGame(appid, self._running[appid])

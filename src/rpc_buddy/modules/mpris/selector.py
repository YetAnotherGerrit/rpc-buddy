"""Decides which track to show, independent of D-Bus (easy to test)."""

from dataclasses import dataclass

from rpc_buddy.modules.mpris.players import Track

START_TOLERANCE = 3.0  # seconds; smaller jumps are polling jitter, not a seek


@dataclass(frozen=True)
class PlayerSnapshot:
    bus_name: str
    source: str  # e.g. "Deezer"
    track: Track
    playing: bool
    position: float | None  # seconds into the track, if known


@dataclass(frozen=True)
class NowPlaying:
    bus_name: str
    source: str
    track: Track
    paused: bool
    start: int | None  # Unix seconds; None while paused or unknown
    end: int | None


class Selector:
    """Picks one track out of all players.

    - A playing player beats paused ones; the one shown keeps priority, then
      the one that started playing most recently.
    - After pausing, the track stays (without timestamps) for
      ``pause_timeout`` seconds, then disappears.
    """

    def __init__(self, pause_timeout: float = 30.0):
        self.pause_timeout = pause_timeout
        self._shown: NowPlaying | None = None
        self._playing_since: dict[str, float] = {}
        self._paused_since: float | None = None

    def update(self, now: float, snapshots: list[PlayerSnapshot]) -> NowPlaying | None:
        by_bus = {s.bus_name: s for s in snapshots}
        for bus in list(self._playing_since):
            if bus not in by_bus or not by_bus[bus].playing:
                del self._playing_since[bus]
        for s in snapshots:
            if s.playing:
                self._playing_since.setdefault(s.bus_name, now)

        playing = [s for s in snapshots if s.playing]
        if playing:
            current = self._shown.bus_name if self._shown else None
            chosen = by_bus.get(current) if current in self._playing_since else None
            if chosen is None:
                chosen = max(playing, key=lambda s: self._playing_since[s.bus_name])
            self._paused_since = None
            self._shown = self._playing(now, chosen)
            return self._shown

        shown = self._shown
        if shown is not None:
            snap = by_bus.get(shown.bus_name)
            if snap is not None and snap.track == shown.track:
                if self._paused_since is None:
                    self._paused_since = now
                if now - self._paused_since < self.pause_timeout:
                    self._shown = NowPlaying(
                        shown.bus_name, shown.source, shown.track, True, None, None
                    )
                    return self._shown
        self._shown = None
        self._paused_since = None
        return None

    def _playing(self, now: float, snap: PlayerSnapshot) -> NowPlaying:
        start = end = None
        if snap.position is not None:
            start = int(now - snap.position)
            prev = self._shown
            if (
                prev is not None
                and not prev.paused
                and prev.start is not None
                and prev.bus_name == snap.bus_name
                and prev.track == snap.track
                and abs(prev.start - start) <= START_TOLERANCE
            ):
                start = prev.start  # keep stable, avoid needless Discord updates
            if snap.track.length:
                end = int(start + snap.track.length)
        return NowPlaying(snap.bus_name, snap.source, snap.track, False, start, end)

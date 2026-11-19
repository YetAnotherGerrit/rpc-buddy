"""Steam module: shows the running Steam game under its official Discord identity."""

import asyncio
import logging
from pathlib import Path

from rpc_buddy import APP_ID
from rpc_buddy.activity import Activity, ActivityType, Health, HealthState
from rpc_buddy.module import Module
from rpc_buddy.modules.steam.logparse import GameTracker, RunningGame, parse_line
from rpc_buddy.modules.steam.paths import find_console_log

log = logging.getLogger(__name__)

POLL_INTERVAL = 1.0  # seconds between log checks
SEARCH_INTERVAL = 30.0  # seconds between searches for Steam's logs

_UNSET = object()  # nothing published yet

DISTRIBUTOR = "steam"  # store name in Discord's game list

NOT_FOUND_HINT = (
    "Start Steam once so it creates its logs. If Steam is installed in an unusual "
    "place, allow RPC Buddy to read its logs folder:\n"
    f"flatpak override --user --filesystem=/path/to/Steam/logs:ro {APP_ID}"
)


class SteamModule(Module):
    id = "steam"
    name = "Steam"

    def __init__(self, ctx):
        super().__init__(ctx)
        self._tracker = GameTracker()
        self._shown: RunningGame | None | object = _UNSET

    async def run(self) -> None:
        while True:
            path = find_console_log()
            if path is None:
                self.ctx.set_health(
                    Health(HealthState.NEEDS_SETUP, "Steam logs not found", NOT_FOUND_HINT)
                )
                await asyncio.sleep(SEARCH_INTERVAL)
                continue
            log.info("Watching %s", path)
            await self._watch(path)

    async def _watch(self, path: Path) -> None:
        """Follow the log file; returns if it disappears."""
        f = None
        inode = None
        buffer = b""
        try:
            while True:
                try:
                    st = path.stat()
                except FileNotFoundError:
                    return
                if f is None or st.st_ino != inode or st.st_size < f.tell():
                    # First open, or Steam restarted and started a new log.
                    if f is not None:
                        f.close()
                    f = path.open("rb")
                    inode = st.st_ino
                    buffer = b""
                    self._tracker.reset()
                chunk = f.read()
                if chunk:
                    buffer += chunk
                    *lines, buffer = buffer.split(b"\n")
                    for raw in lines:
                        event = parse_line(raw.decode("utf-8", errors="replace"))
                        if event is not None:
                            self._tracker.feed(event)
                await self._update(self._tracker.current())
                await asyncio.sleep(POLL_INTERVAL)
        finally:
            if f is not None:
                f.close()

    async def _update(self, game: RunningGame | None) -> None:
        if game == self._shown:
            return
        self._shown = game

        if game is None:
            self.ctx.publish(None)
            self.ctx.set_health(Health(HealthState.OK, "No game running"))
            return

        try:
            discord_game = await self.ctx.detectable.lookup(DISTRIBUTOR, game.appid)
        except Exception as e:  # noqa: BLE001 - network errors etc.
            log.warning("Could not look up Steam app %s: %s", game.appid, e)
            self.ctx.publish(None)
            self.ctx.set_health(
                Health(
                    HealthState.ERROR,
                    "Could not load Discord's game list",
                    "Check your internet connection.",
                )
            )
            self._shown = _UNSET  # retry on next poll
            await asyncio.sleep(SEARCH_INTERVAL)
            return

        if discord_game is None:
            log.info("Steam app %s is not known to Discord, not shown", game.appid)
            self.ctx.publish(None)
            self.ctx.set_health(
                Health(HealthState.OK, f"Steam app {game.appid} is unknown to Discord")
            )
            return

        log.info(
            "Playing %s (Steam %s, Discord %s)", discord_game.name, game.appid, discord_game.app_id
        )
        self.ctx.publish(
            Activity(
                client_id=discord_game.app_id,
                type=ActivityType.PLAYING,
                large_image=discord_game.image_url,
                large_text=discord_game.name,
                start=game.started,
            ),
            summary=f"Playing {discord_game.name}",
        )
        self.ctx.set_health(Health(HealthState.OK, f"Playing {discord_game.name}"))

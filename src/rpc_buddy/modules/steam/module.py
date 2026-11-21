"""Steam module: shows the running Steam game under its official Discord identity."""

import asyncio
import logging
from pathlib import Path

from rpc_buddy.activity import Activity, ActivityType, Health, HealthState
from rpc_buddy.module import Module, Setting
from rpc_buddy.modules.steam.logparse import GameTracker, RunningGame, parse_line
from rpc_buddy.modules.steam.paths import find_console_log, override_command, steam_roots
from rpc_buddy.modules.steam.persona import PersonaWatcher, find_localconfig

log = logging.getLogger(__name__)

POLL_INTERVAL = 1.0  # seconds between log checks
SEARCH_INTERVAL = 30.0  # seconds between searches for Steam's logs

_UNSET = object()  # nothing published yet

DISTRIBUTOR = "steam"  # store name in Discord's game list

INVISIBLE_REASON = "you're invisible on Steam"


def not_found_hint(folder: str) -> str:
    return (
        "Start Steam once so it creates its logs. If Steam is installed in an unusual "
        "place, enter its folder in the Steam settings (⚙) and allow RPC Buddy to read it:\n"
        + override_command(folder)
    )


class SteamModule(Module):
    id = "steam"
    name = "Steam"
    settings = (
        Setting(
            "steam_folder",
            "Steam folder",
            "text",
            placeholder="Found automatically",
            help="Only needed if Steam is installed in an unusual place: the folder that "
            "contains Steam's logs and userdata folders.",
        ),
        Setting(
            "respect_invisible",
            "Hide games while I'm invisible on Steam",
            "bool",
            help="While your Steam status is Invisible or Offline, your game isn't shown "
            "on Discord either.",
        ),
    )

    def __init__(self, ctx, persona: PersonaWatcher | None = None):
        super().__init__(ctx)
        self._tracker = GameTracker()
        self._folder = str(ctx.settings.get("steam_folder") or "")
        self._roots = steam_roots(self._folder)
        self._persona = persona or PersonaWatcher(find=lambda: find_localconfig(self._roots))
        self._shown: tuple[RunningGame | None, bool] | object = _UNSET

    def _hidden_by_steam(self) -> bool:
        if not self.ctx.settings.get("respect_invisible", True):
            return False
        return self._persona.hidden()

    async def run(self) -> None:
        while True:
            path = find_console_log(self._roots)
            if path is None:
                self.ctx.set_health(
                    Health(
                        HealthState.NEEDS_SETUP,
                        "Steam logs not found",
                        not_found_hint(self._folder),
                    )
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
                await self._update(self._tracker.current(), self._hidden_by_steam())
                await asyncio.sleep(POLL_INTERVAL)
        finally:
            if f is not None:
                f.close()

    async def _update(self, game: RunningGame | None, hidden_by_steam: bool = False) -> None:
        if (game, hidden_by_steam) == self._shown:
            return
        self._shown = (game, hidden_by_steam)

        if game is None:
            self.ctx.publish(None)
            self.ctx.set_health(Health(HealthState.OK, "No game running"))
            return

        try:
            discord_game = await self.ctx.detectable.lookup(DISTRIBUTOR, game.appid)
        except Exception as e:  # noqa: BLE001 - network errors etc.
            log.warning("Could not look up the game in Discord's list: %s", e)
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
            log.debug("Steam app %s is not known to Discord, not shown", game.appid)
            self.ctx.publish(None)
            self.ctx.set_health(
                Health(HealthState.OK, f"Steam app {game.appid} is unknown to Discord")
            )
            return

        withheld = INVISIBLE_REASON if hidden_by_steam else ""
        log.debug(
            "Playing %s (Steam %s, Discord %s)%s",
            discord_game.name,
            game.appid,
            discord_game.app_id,
            f" — not on Discord: {withheld}" if withheld else "",
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
            hide_key=f"steam:{game.appid}",
            hide_label=discord_game.name,
            withheld=withheld,
        )
        if withheld:
            self.ctx.set_health(Health(HealthState.OK, f"Not on Discord — {withheld}"))
        else:
            self.ctx.set_health(Health(HealthState.OK, f"Playing {discord_game.name}"))

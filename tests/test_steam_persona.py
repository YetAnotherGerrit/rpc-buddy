# All ids and file contents below are made up.
import asyncio
import os

from rpc_buddy.activity import HealthState
from rpc_buddy.detectable import DiscordGame
from rpc_buddy.modules.steam.logparse import RunningGame
from rpc_buddy.modules.steam.module import SteamModule
from rpc_buddy.modules.steam.persona import (
    PersonaWatcher,
    find_localconfig,
    parse_persona_state,
)


def vdf(state: int) -> str:
    return (
        '"UserLocalConfigStore"\n{\n\t"WebStorage"\n\t{\n'
        f'\t\t"FriendStoreLocalPrefs_1000"\t\t"{{\\"ePersonaState\\":{state},'
        '\\"strNonFriendsAllowedToMsg\\":\\"\\"}"\n\t}\n}\n'
    )


def test_parse_persona_state():
    assert parse_persona_state(vdf(1)) == 1
    assert parse_persona_state(vdf(7)) == 7
    assert parse_persona_state('"UserLocalConfigStore"\n{\n}\n') is None
    assert parse_persona_state('"FriendStoreLocalPrefs_1"\t"garbage"') is None


def write_account(root, account, state, mtime):
    path = root / "userdata" / account / "config" / "localconfig.vdf"
    path.parent.mkdir(parents=True)
    path.write_text(vdf(state))
    os.utime(path, (mtime, mtime))
    return path


def test_find_localconfig_picks_most_recent_account(tmp_path):
    write_account(tmp_path, "1000", 1, 1_000_000)
    newer = write_account(tmp_path, "2000", 7, 2_000_000)
    assert find_localconfig([tmp_path]) == newer
    assert find_localconfig([tmp_path / "missing"]) is None


def test_watcher_rereads_only_on_change(tmp_path):
    path = write_account(tmp_path, "1000", 1, 1_000_000)
    watcher = PersonaWatcher(find=lambda: path)
    assert watcher.state() == 1 and not watcher.hidden()
    path.write_text(vdf(7))
    os.utime(path, (1_000_005, 1_000_005))
    assert watcher.hidden()
    path.write_text(vdf(0))
    os.utime(path, (1_000_010, 1_000_010))
    assert watcher.hidden()  # offline hides too


def test_watcher_without_file_is_not_hidden():
    watcher = PersonaWatcher(find=lambda: None)
    assert watcher.state() is None
    assert not watcher.hidden()


class FakeDetectable:
    async def lookup(self, distributor, sku):
        return DiscordGame("900000000000000001", "Example Quest", "icon1", "cover1")


class FakeCtx:
    def __init__(self, settings=None):
        self.settings = settings or {}
        self.detectable = FakeDetectable()
        self.published = []
        self.health = None

    def publish(self, activity, summary="", hide_key=None, hide_label=None, withheld=""):
        self.published.append(activity)
        self.withheld = withheld

    def set_health(self, health):
        self.health = health


class FakePersona:
    def __init__(self, hidden):
        self._hidden = hidden

    def hidden(self):
        return self._hidden


GAME = RunningGame("1000001", 1_767_268_800)


def run_update(ctx, persona):
    module = SteamModule(ctx, persona=persona)
    asyncio.run(module._update(GAME, module._hidden_by_steam()))


def test_game_withheld_while_invisible():
    ctx = FakeCtx()
    run_update(ctx, FakePersona(hidden=True))
    assert ctx.published[-1].large_text == "Example Quest"  # still shown in RPC Buddy
    assert ctx.withheld == "you're invisible on Steam"  # … but not sent to Discord
    assert ctx.health.state is HealthState.OK
    assert "invisible" in ctx.health.message


def test_game_shown_when_online_or_setting_off():
    ctx = FakeCtx()
    run_update(ctx, FakePersona(hidden=False))
    assert ctx.published[-1].large_text == "Example Quest"
    assert ctx.withheld == ""
    ctx = FakeCtx(settings={"respect_invisible": False})
    run_update(ctx, FakePersona(hidden=True))
    assert ctx.published[-1].large_text == "Example Quest"
    assert ctx.withheld == ""


def test_custom_steam_folder_is_searched_first(tmp_path):
    from rpc_buddy.modules.steam.paths import find_console_log, steam_roots

    roots = steam_roots(str(tmp_path))
    assert roots[0] == tmp_path and len(roots) == 5
    assert len(steam_roots("")) == 4
    log = tmp_path / "logs" / "console_log.txt"
    log.parent.mkdir()
    log.write_text("")
    assert find_console_log(roots) == log
    path = write_account(tmp_path, "1000", 7, 1_000_000)
    assert find_localconfig(roots[:1]) == path

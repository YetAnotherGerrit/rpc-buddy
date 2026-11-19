from rpc_buddy.activity import Health, HealthState
from rpc_buddy.engine import EngineState, ModuleStatus
from rpc_buddy.setup_checks import (
    CheckState,
    Environment,
    discord_check,
    music_check,
    run_checks,
    steam_check,
    tray_check,
)

FLATPAK = Environment(in_flatpak=True, tray_available=True, discord_flatpak_dir_visible=True)
NO_DISCORD_DIR = Environment(
    in_flatpak=True, tray_available=False, discord_flatpak_dir_visible=False
)


def module(module_id, health, enabled=True):
    return ModuleStatus(module_id, module_id, enabled, health, None, "", False, (), {})


OK = Health(HealthState.OK)


def state(discord, steam=OK, music=OK):
    return EngineState(
        discord=discord,
        paused=False,
        modules=(module("steam", steam), module("mpris", music)),
        hidden=(),
        recent=(),
    )


NOT_REACHABLE = Health(HealthState.NEEDS_SETUP, "Discord not reachable")


def test_everything_ok():
    checks = run_checks(state(Health(HealthState.OK, "Discord found")), FLATPAK)
    assert [c.state for c in checks] == [CheckState.OK] * 4


def test_discord_flatpak_not_running_just_says_start_it():
    check = discord_check(state(NOT_REACHABLE), FLATPAK)
    assert check.state is CheckState.WARNING
    assert check.command == ""


def test_native_discord_gets_override_command():
    check = discord_check(state(NOT_REACHABLE), NO_DISCORD_DIR)
    assert check.state is CheckState.WARNING
    assert "--filesystem=xdg-run/discord-ipc-0" in check.command
    assert "before RPC Buddy" in check.note


def test_outside_flatpak_no_override_command():
    env = Environment(in_flatpak=False, tray_available=True, discord_flatpak_dir_visible=False)
    assert discord_check(state(NOT_REACHABLE), env).command == ""


def test_steam_logs_missing_offers_override():
    check = steam_check(state(NOT_REACHABLE, steam=Health(HealthState.NEEDS_SETUP)))
    assert check.state is CheckState.WARNING
    assert check.command.startswith("flatpak override --user --filesystem=")


def test_disabled_module_is_info():
    s = EngineState(
        discord=NOT_REACHABLE,
        paused=False,
        modules=(module("mpris", Health(HealthState.DISABLED), enabled=False),),
        hidden=(),
        recent=(),
    )
    assert music_check(s).state is CheckState.INFO


def test_no_tray_is_info_not_error():
    assert tray_check(NO_DISCORD_DIR).state is CheckState.INFO

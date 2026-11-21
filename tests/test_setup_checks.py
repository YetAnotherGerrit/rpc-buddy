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

FLATPAK = Environment(in_flatpak=True, tray_available=True)
NATIVE_ALLOWED = Environment(in_flatpak=True, tray_available=True, native_discord_allowed=True)
NO_TRAY = Environment(in_flatpak=True, tray_available=False)


def module(module_id, health, enabled=True):
    return ModuleStatus(module_id, module_id, enabled, health, None, "", False, (), {})


OK = Health(HealthState.OK)


def state(discord, steam=OK, music=OK):
    return EngineState(
        discord=discord,
        paused=False,
        modules=(module("steam", steam), module("mpris", music)),
        hidden=(),
        autostart=True,
    )


NOT_REACHABLE = Health(HealthState.NEEDS_SETUP, "Discord not reachable")


def test_everything_ok():
    checks = run_checks(state(Health(HealthState.OK, "Discord found")), FLATPAK)
    assert [c.state for c in checks] == [CheckState.OK] * 5


def test_discord_not_running_says_start_it_and_offers_native_command():
    check = discord_check(state(NOT_REACHABLE), FLATPAK)
    assert check.state is CheckState.WARNING
    assert "Start it" in check.message
    assert "doesn't matter which starts first" in check.message
    assert "--filesystem=xdg-run/discord-ipc-0" in check.command
    assert "before RPC Buddy" in check.note


def test_native_override_already_set_only_explains_start_order():
    check = discord_check(state(NOT_REACHABLE), NATIVE_ALLOWED)
    assert check.command == ""
    assert "restart RPC Buddy after restarting Discord" in check.note


def test_outside_flatpak_no_override_command():
    env = Environment(in_flatpak=False, tray_available=True)
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
    )
    assert music_check(s).state is CheckState.INFO


def test_no_tray_is_info_not_error():
    assert tray_check(NO_TRAY).state is CheckState.INFO


def test_autostart_row():
    from dataclasses import replace

    from rpc_buddy.setup_checks import autostart_check

    base = state(Health(HealthState.OK))
    assert autostart_check(replace(base, autostart=True, setup_done=True)).state is CheckState.OK
    assert autostart_check(replace(base, autostart=True, setup_done=False)).state is CheckState.INFO
    assert autostart_check(replace(base, autostart=False)).state is CheckState.INFO
    failed = replace(base, autostart=True, autostart_error="denied")
    assert autostart_check(failed).state is CheckState.WARNING


def test_steam_override_uses_configured_folder():
    from dataclasses import replace

    s = state(NOT_REACHABLE, steam=Health(HealthState.NEEDS_SETUP))
    custom = replace(s.modules[0], values={"steam_folder": "/mnt/games/Steam/"})
    check = steam_check(replace(s, modules=(custom, s.modules[1])))
    assert "--filesystem=/mnt/games/Steam/logs:ro" in check.command
    assert "--filesystem=/mnt/games/Steam/userdata:ro" in check.command


def test_steam_not_found_offers_choose_and_dont_use_steam():
    from dataclasses import replace

    from rpc_buddy.setup_checks import CHOOSE_STEAM_FOLDER, DISABLE_STEAM

    s = state(NOT_REACHABLE, steam=Health(HealthState.NEEDS_SETUP))
    check = steam_check(s)
    assert [a for a, _ in check.actions] == [CHOOSE_STEAM_FOLDER, DISABLE_STEAM]
    assert "If choosing the folder doesn't work" in check.note
    assert steam_check(state(Health(HealthState.OK))).actions == ()
    failed = steam_check(replace(s, folder_error="no portal"))
    assert "Couldn't open the folder dialog (no portal)" in failed.note

# All app ids, paths and timestamps below are made up.
from rpc_buddy.modules.steam.logparse import MAX_RUNNING, GameTracker, parse_line

ADDED = (
    '[2026-01-01 12:00:00] Game process added : AppID 1000001 "/home/u/.local/share/'
    'Steam/steamrt64/steam-launch-wrapper -- reaper SteamLaunch AppId=1000001 --"'
)
UPDATED = '[2026-01-01 12:00:05] Game process updated : AppID 1000001 "…"'
REMOVED = '[2026-01-01 13:15:00] Game process removed: AppID 1000001 "…"'
NOW = parse_line('[2026-01-01 14:00:00] Game process added : AppID 1 ""').timestamp


def test_parse_added_updated_removed():
    assert parse_line(ADDED).kind == "added"
    assert parse_line(ADDED).appid == "1000001"
    assert parse_line(UPDATED).kind == "updated"
    assert parse_line(REMOVED).kind == "removed"


def test_parse_ignores_other_lines():
    assert parse_line("[2026-01-01 12:00:05] ThreadGetProcessExitCode: no such process") is None
    assert parse_line("[2026-01-01 12:00:00] AppID 1000001 adding PID 4242 as a tracked") is None
    assert parse_line("") is None


def test_tracker_start_time_is_first_added():
    t = GameTracker()
    t.feed(parse_line(ADDED))
    t.feed(parse_line(UPDATED))
    game = t.current(NOW)
    assert game.appid == "1000001"
    assert game.started == parse_line(ADDED).timestamp


def test_tracker_removed_clears():
    t = GameTracker()
    for line in (ADDED, UPDATED, REMOVED):
        t.feed(parse_line(line))
    assert t.current(NOW) is None


def test_tracker_most_recent_game_wins():
    t = GameTracker()
    t.feed(parse_line(ADDED))
    t.feed(parse_line('[2026-01-01 12:30:00] Game process added : AppID 1000002 "…"'))
    assert t.current(NOW).appid == "1000002"
    t.feed(parse_line('[2026-01-01 12:45:00] Game process removed: AppID 1000002 "…"'))
    assert t.current(NOW).appid == "1000001"


def test_tracker_ignores_games_running_too_long():
    t = GameTracker()
    t.feed(parse_line(ADDED))  # Steam crashed before logging "removed"
    started = parse_line(ADDED).timestamp
    assert t.current(started + MAX_RUNNING).appid == "1000001"
    assert t.current(started + MAX_RUNNING + 1) is None


def test_tracker_stale_game_does_not_hide_newer_one():
    t = GameTracker()
    t.feed(parse_line(ADDED))
    t.feed(parse_line('[2026-01-01 23:00:00] Game process added : AppID 1000002 "…"'))
    t.feed(parse_line('[2026-01-01 23:30:00] Game process removed: AppID 1000002 "…"'))
    t.feed(parse_line('[2026-01-02 01:00:00] Game process added : AppID 1000003 "…"'))
    assert t.current(parse_line(ADDED).timestamp + 13 * 3600).appid == "1000003"

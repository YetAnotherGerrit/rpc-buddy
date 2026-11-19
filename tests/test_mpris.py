# All tracks, artists and albums below are made up.
from rpc_buddy.modules.mpris.players import player_key, source_name, track_from_metadata
from rpc_buddy.modules.mpris.selector import PlayerSnapshot, Selector

FIREFOX = "org.mpris.MediaPlayer2.firefox.instance_1_23"
CHROMIUM = "org.mpris.MediaPlayer2.chromium.instance4242"

TRACK_A = track_from_metadata(
    {
        "xesam:title": "Placeholder Song",
        "xesam:artist": ["Nobody In Particular"],
        "xesam:album": "Made-Up Album",
        "mpris:length": 180_000_000,
        "xesam:url": "https://www.deezer.com/track/0",
    }
)
TRACK_B = track_from_metadata({"xesam:title": "Another Example", "xesam:artist": ["Someone Else"]})


def test_player_key():
    assert player_key(FIREFOX) == "firefox"
    assert player_key("org.mpris.MediaPlayer2.tidal-hifi") == "tidal-hifi"


def test_dedicated_music_player():
    assert source_name("org.mpris.MediaPlayer2.elisa", "Elisa", None) == "Elisa"


def test_browser_only_for_music_sites():
    assert source_name(FIREFOX, "Mozilla firefox", "https://www.deezer.com/account") == "Deezer"
    assert source_name(FIREFOX, "Mozilla firefox", "https://music.youtube.com/watch") == (
        "YouTube Music"
    )
    assert source_name(FIREFOX, "Mozilla firefox", "https://www.youtube.com/watch") is None
    assert source_name(FIREFOX, "Mozilla firefox", None) is None


def test_electron_app_recognised_by_identity():
    assert source_name(CHROMIUM, "Deezer", None) == "Deezer"
    assert source_name(CHROMIUM, "Chromium", None) is None


def test_spotify_is_never_duplicated():
    assert source_name("org.mpris.MediaPlayer2.spotify", "Spotify", None) is None
    assert source_name(FIREFOX, "Mozilla firefox", "https://open.spotify.com/track/0") is None


def test_unknown_and_video_players_are_ignored():
    assert source_name("org.mpris.MediaPlayer2.vlc", "VLC media player", None) is None
    assert source_name("org.mpris.MediaPlayer2.mpv", "mpv", None) is None


def test_track_from_metadata():
    assert TRACK_A.title == "Placeholder Song"
    assert TRACK_A.artist == "Nobody In Particular"
    assert TRACK_A.length == 180.0
    assert track_from_metadata({"xesam:title": "  "}) is None
    assert track_from_metadata({"xesam:title": "X", "xesam:artist": "Solo"}).artists == ("Solo",)


def snap(bus, track, playing=True, position=10.0):
    return PlayerSnapshot(bus, "Deezer", track, playing, position)


def test_playing_track_with_timestamps():
    sel = Selector()
    now = sel.update(1000.0, [snap(FIREFOX, TRACK_A, position=10.0)])
    assert now.track == TRACK_A
    assert (now.start, now.end) == (990, 1170)
    assert not now.paused


def test_start_is_stable_against_polling_jitter():
    sel = Selector()
    first = sel.update(1000.0, [snap(FIREFOX, TRACK_A, position=10.0)])
    second = sel.update(1002.0, [snap(FIREFOX, TRACK_A, position=11.2)])
    assert second.start == first.start


def test_seek_changes_start():
    sel = Selector()
    sel.update(1000.0, [snap(FIREFOX, TRACK_A, position=10.0)])
    now = sel.update(1002.0, [snap(FIREFOX, TRACK_A, position=100.0)])
    assert now.start == 902


def test_pause_keeps_track_until_timeout():
    sel = Selector(pause_timeout=30)
    sel.update(1000.0, [snap(FIREFOX, TRACK_A)])
    paused = sel.update(1002.0, [snap(FIREFOX, TRACK_A, playing=False)])
    assert paused.paused and paused.start is None
    assert sel.update(1031.0, [snap(FIREFOX, TRACK_A, playing=False)]).paused
    assert sel.update(1033.0, [snap(FIREFOX, TRACK_A, playing=False)]) is None


def test_resume_after_pause():
    sel = Selector(pause_timeout=30)
    sel.update(1000.0, [snap(FIREFOX, TRACK_A)])
    sel.update(1002.0, [snap(FIREFOX, TRACK_A, playing=False)])
    assert not sel.update(1010.0, [snap(FIREFOX, TRACK_A)]).paused


def test_player_gone_clears():
    sel = Selector()
    sel.update(1000.0, [snap(FIREFOX, TRACK_A)])
    assert sel.update(1002.0, []) is None


def test_shown_player_keeps_priority_newest_otherwise():
    sel = Selector()
    sel.update(1000.0, [snap(FIREFOX, TRACK_A)])
    both = [snap(FIREFOX, TRACK_A), snap(CHROMIUM, TRACK_B)]
    assert sel.update(1002.0, both).bus_name == FIREFOX
    # Firefox stops: the other player takes over.
    assert sel.update(1004.0, [snap(CHROMIUM, TRACK_B)]).bus_name == CHROMIUM

# Pure helpers of the GUI (no display needed). Values are made up.
from rpc_buddy.activity import Activity, Health, HealthState
from rpc_buddy.engine import EngineState, ModuleStatus
from rpc_buddy.gui.covers import image_format
from rpc_buddy.gui.tray import tooltip_text


def test_image_format_accepts_only_cover_formats():
    assert image_format(b"\x89PNG\r\n\x1a\n" + b"0" * 10) == "PNG"
    assert image_format(b"\xff\xd8\xff\xe0" + b"0" * 10) == "JPEG"
    assert image_format(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "WEBP"
    assert image_format(b"<svg xmlns='http://www.w3.org/2000/svg'/>") is None
    assert image_format(b"GIF89a") is None
    assert image_format(b"") is None


def state(paused=False, titles=(), discord_ok=True):
    modules = tuple(
        ModuleStatus(
            f"m{i}",
            "M",
            True,
            Health(HealthState.OK),
            Activity(client_id=str(i)),
            title,
            False,
            (),
            {},
        )
        for i, title in enumerate(titles)
    )
    discord = Health(
        HealthState.OK if discord_ok else HealthState.NEEDS_SETUP, "Discord not reachable"
    )
    return EngineState(discord=discord, paused=paused, modules=modules, hidden=())


def test_tooltip_never_contains_titles():
    text = tooltip_text(
        state(titles=("Listening to <b>Placeholder Song</b>", "Playing Example Quest"))
    )
    assert "Placeholder" not in text and "Example Quest" not in text and "<b>" not in text
    assert "2 activities on Discord" in text


def test_tooltip_states():
    assert "Nothing on Discord" in tooltip_text(state())
    assert "1 activity on Discord" in tooltip_text(state(titles=("x",)))
    assert "Paused" in tooltip_text(state(paused=True, titles=("x",)))
    assert "⚠ Discord not reachable" in tooltip_text(state(discord_ok=False))

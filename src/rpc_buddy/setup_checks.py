"""Setup check: what works, what is missing, and how to fix it.

Pure logic (no Qt), so it can be tested; ``gui/setup.py`` displays it.
"""

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from rpc_buddy import APP_ID
from rpc_buddy.activity import HealthState
from rpc_buddy.engine import EngineState


class CheckState(Enum):
    OK = "ok"
    WARNING = "warning"  # something the user should fix
    INFO = "info"  # optional / nothing to do right now


@dataclass(frozen=True)
class Check:
    title: str
    state: CheckState
    message: str
    command: str = ""  # copyable fix, e.g. a flatpak override
    note: str = ""


@dataclass(frozen=True)
class Environment:
    in_flatpak: bool
    tray_available: bool
    discord_flatpak_dir_visible: bool  # $XDG_RUNTIME_DIR/app/com.discordapp.Discord


def detect_environment(tray_available: bool) -> Environment:
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    return Environment(
        in_flatpak=Path("/.flatpak-info").exists(),
        tray_available=tray_available,
        discord_flatpak_dir_visible=(runtime / "app" / "com.discordapp.Discord").is_dir(),
    )


def _module(state: EngineState, module_id: str):
    return next((m for m in state.modules if m.id == module_id), None)


def discord_check(state: EngineState, env: Environment) -> Check:
    title = "Discord"
    if state.discord.ok:
        return Check(title, CheckState.OK, state.discord.message or "Discord found")
    if state.discord.state is HealthState.STARTING:
        return Check(title, CheckState.INFO, "Looking for Discord…")
    if not env.in_flatpak or env.discord_flatpak_dir_visible:
        return Check(title, CheckState.WARNING, "Discord is not running. Start Discord.")
    return Check(
        title,
        CheckState.WARNING,
        "Discord is not reachable. If you use the Discord Flatpak, just start it. "
        "If you use Discord installed without Flatpak (e.g. .deb, .rpm, AUR), "
        "allow RPC Buddy to reach it once with this command, then restart RPC Buddy:",
        command=f"flatpak override --user --filesystem=xdg-run/discord-ipc-0 {APP_ID}",
        note="With a non-Flatpak Discord, start Discord before RPC Buddy.",
    )


def steam_check(state: EngineState) -> Check:
    title = "Steam games"
    m = _module(state, "steam")
    if m is None or not m.enabled:
        return Check(title, CheckState.INFO, "Switched off.")
    if m.health.state is HealthState.NEEDS_SETUP:
        return Check(
            title,
            CheckState.WARNING,
            "Steam's logs were not found. Start Steam once. If Steam is installed in an "
            "unusual place, allow RPC Buddy to read its logs folder (adjust the path):",
            command=f"flatpak override --user --filesystem=/path/to/Steam/logs:ro {APP_ID}",
        )
    if m.health.state is HealthState.ERROR:
        return Check(title, CheckState.WARNING, m.health.message, note=m.health.hint)
    if m.health.state is HealthState.STARTING:
        return Check(title, CheckState.INFO, "Starting…")
    return Check(title, CheckState.OK, "Steam found. Games show up when you start them.")


def music_check(state: EngineState) -> Check:
    title = "Music"
    m = _module(state, "mpris")
    if m is None or not m.enabled:
        return Check(title, CheckState.INFO, "Switched off.")
    if m.health.state is HealthState.ERROR:
        return Check(title, CheckState.WARNING, m.health.message, note=m.health.hint)
    if m.health.state is HealthState.STARTING:
        return Check(title, CheckState.INFO, "Starting…")
    return Check(
        title,
        CheckState.OK,
        "Ready. Supported music players and music websites (e.g. Deezer in a browser) "
        "show up while they play.",
    )


def tray_check(env: Environment) -> Check:
    title = "Tray icon"
    if env.tray_available:
        return Check(title, CheckState.OK, "RPC Buddy lives in your system tray.")
    return Check(
        title,
        CheckState.INFO,
        "Your desktop shows no tray icons (e.g. GNOME without the AppIndicator extension). "
        "RPC Buddy still works; open it from your app menu to change settings.",
    )


def autostart_check(state: EngineState) -> Check:
    title = "Start with your desktop"
    if state.autostart_error:
        return Check(
            title,
            CheckState.WARNING,
            f"Could not set up autostart: {state.autostart_error}",
            note="You can retry with the checkbox in the main window.",
        )
    if not state.autostart:
        return Check(title, CheckState.INFO, "Off. You can switch it on in the main window.")
    if not state.setup_done:
        return Check(
            title,
            CheckState.INFO,
            "RPC Buddy will start quietly in the background when you log in "
            "(set up when you click Done). You can change this in the main window.",
        )
    return Check(title, CheckState.OK, "RPC Buddy starts quietly in the background.")


def run_checks(state: EngineState, env: Environment) -> list[Check]:
    return [
        discord_check(state, env),
        steam_check(state),
        music_check(state),
        tray_check(env),
        autostart_check(state),
    ]

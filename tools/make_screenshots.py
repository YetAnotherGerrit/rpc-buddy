"""Render README/store screenshots of the main window with made-up content.

    QT_QPA_PLATFORM=offscreen uv run python tools/make_screenshots.py

Writes docs/screenshots/main-light.png and main-dark.png. Everything shown is
made up (game, song, artist) — never use real titles in the repository.
"""

import asyncio
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication

from rpc_buddy.activity import Activity, ActivityType, Health, HealthState, StatusDisplay
from rpc_buddy.config import Config
from rpc_buddy.engine import Engine
from rpc_buddy.gui.tray import EngineBridge
from rpc_buddy.gui.window import MainWindow
from rpc_buddy.module import Module
from rpc_buddy.modules.mpris import MprisModule
from rpc_buddy.modules.steam import SteamModule

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"

PALETTES = {  # Breeze-like colours
    "light": {
        "Window": "#eff0f1",
        "WindowText": "#232629",
        "Base": "#ffffff",
        "Text": "#232629",
        "Button": "#fcfcfc",
        "ButtonText": "#232629",
        "Highlight": "#3daee9",
        "Link": "#2980b9",
    },
    "dark": {
        "Window": "#202326",
        "WindowText": "#fcfcfc",
        "Base": "#141618",
        "Text": "#fcfcfc",
        "Button": "#292c30",
        "ButtonText": "#fcfcfc",
        "Highlight": "#3daee9",
        "Link": "#1d99f3",
    },
}


class FakeSink:
    status = Health(HealthState.OK, "Connected to Discord")
    on_status = None

    def set_desired(self, desired):
        pass

    async def run(self):
        await asyncio.Event().wait()

    async def shutdown(self):
        pass


class FakeSteam(Module):
    id = SteamModule.id
    name = SteamModule.name
    settings = SteamModule.settings

    async def run(self):
        self.ctx.set_health(Health(HealthState.OK, "Playing Example Quest"))
        self.ctx.publish(
            Activity(client_id="1", large_text="Example Quest", start=int(time.time()) - 5025),
            "Playing Example Quest",
            hide_key="steam:1000001",
            hide_label="Example Quest",
        )
        await asyncio.Event().wait()


class FakeMusic(Module):
    id = MprisModule.id
    name = MprisModule.name
    settings = MprisModule.settings

    async def run(self):
        self.ctx.set_health(Health(HealthState.OK, "Deezer: Listening to Placeholder Song"))
        now = int(time.time())
        self.ctx.publish(
            Activity(
                client_id="2",
                type=ActivityType.LISTENING,
                name="Deezer",
                details="Placeholder Song",
                state="Nobody In Particular",
                large_text="Made-Up Album",
                start=now - 72,
                end=now + 108,
                status_display=StatusDisplay.STATE,
            ),
            "Listening to Placeholder Song",
            hide_key="mpris:Deezer",
            hide_label="Deezer (music)",
        )
        await asyncio.Event().wait()


def render(mode: str) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    QIcon.setThemeSearchPaths([*QIcon.themeSearchPaths(), "/usr/share/icons"])
    QIcon.setThemeName("breeze-dark" if mode == "dark" else "breeze")
    palette = QPalette()
    for role, color in PALETTES[mode].items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    app.setPalette(palette)

    config = Config(Path(tempfile.mkdtemp()) / "config.toml")
    config.setup_done = True
    config.set_hidden("steam:1000002", "Sample Racer", True)
    bridge = EngineBridge()
    engine = Engine(
        config,
        on_state=bridge.state_changed.emit,
        modules=[FakeSteam, FakeMusic],
        sink=FakeSink(),
        detectable=object(),
    )
    window = MainWindow(engine, quit_app=app.quit, keep_running=True, open_setup=lambda: None)
    bridge.state_changed.connect(window.on_state)
    engine.start_in_thread()
    window.show_and_raise()
    window.resize(600, 860)

    def grab() -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(OUT / f"main-{mode}.png"))
        print("wrote", OUT / f"main-{mode}.png")
        engine.stop()
        window.close()
        app.quit()

    QTimer.singleShot(1500, grab)
    app.exec()


if __name__ == "__main__":
    for mode in sys.argv[1:] or ["light", "dark"]:
        render(mode)

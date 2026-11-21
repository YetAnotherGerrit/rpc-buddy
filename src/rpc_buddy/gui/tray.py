"""Tray icon — the main way to interact with RPC Buddy on KDE Plasma."""

import logging
from collections.abc import Callable
from importlib.resources import files

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from rpc_buddy import APP_ID, APP_NAME
from rpc_buddy.activity import HealthState
from rpc_buddy.engine import Engine, EngineState

log = logging.getLogger(__name__)


def app_icon() -> QIcon:
    fallback = QIcon(str(files("rpc_buddy") / "resources" / "icon.svg"))
    return QIcon.fromTheme(APP_ID, fallback)


class EngineBridge(QObject):
    """Delivers engine state (emitted in the core thread) to the GUI thread."""

    state_changed = Signal(object)


class Tray(QObject):
    def __init__(
        self, engine: Engine, open_window: Callable[[], None], quit_app: Callable[[], None]
    ):
        super().__init__()
        self._engine = engine
        self._open_window = open_window
        self._quit_app = quit_app
        self._menu = QMenu()
        self._icon = QSystemTrayIcon(app_icon())
        self._icon.setContextMenu(self._menu)
        self._icon.setToolTip(APP_NAME)
        self._icon.activated.connect(self._on_activated)
        self._icon.show()

    def notify(self, title: str, message: str) -> None:
        self._icon.showMessage(title, message, app_icon(), 10_000)

    @staticmethod
    def available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._open_window()

    def on_state(self, state: EngineState) -> None:
        self._menu.clear()

        self._menu.addSection(APP_NAME)
        lines: list[str] = []
        if state.paused:
            lines.append("Paused — nothing is shown")
        else:
            lines += [m.summary for m in state.shown] or ["Nothing to show"]
        discord = state.discord.message or "Discord"
        if not state.discord.ok:
            discord = f"⚠ {discord}"
        lines.append(discord)
        for line in lines:
            self._menu.addAction(line).setEnabled(False)

        self._menu.addSeparator()
        pause = QAction("Pause presence", self._menu, checkable=True, checked=state.paused)
        pause.toggled.connect(self._engine.set_paused)
        self._menu.addAction(pause)

        self._menu.addSection("Modules")
        for m in state.modules:
            label = m.name
            if m.enabled and m.health.state in (HealthState.NEEDS_SETUP, HealthState.ERROR):
                label += f" — ⚠ {m.health.message}"
            action = QAction(label, self._menu, checkable=True, checked=m.enabled)
            action.toggled.connect(lambda on, mid=m.id: self._engine.set_module_enabled(mid, on))
            self._menu.addAction(action)

        self._menu.addSeparator()
        self._menu.addAction(f"Open {APP_NAME}…", self._open_window)
        self._menu.addAction("Quit", self._quit_app)

        self._icon.setToolTip(f"{APP_NAME}\n" + "\n".join(lines))

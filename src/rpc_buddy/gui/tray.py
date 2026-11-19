"""Tray icon — the main way to interact with RPC Buddy on KDE Plasma."""

import logging
from importlib.resources import files

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

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
    def __init__(self, app: QApplication, engine: Engine, bridge: EngineBridge):
        super().__init__()
        self._app = app
        self._engine = engine
        self._menu = QMenu()
        self._icon = QSystemTrayIcon(app_icon())
        self._icon.setContextMenu(self._menu)
        self._icon.setToolTip(APP_NAME)
        bridge.state_changed.connect(self.on_state)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.warning("No system tray available — RPC Buddy keeps running in the background")
        self._icon.show()

    @Slot(object)
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
            if m.health.hint and m.enabled and not m.health.ok:
                action.setToolTip(m.health.hint)
            action.toggled.connect(lambda on, mid=m.id: self._engine.set_module_enabled(mid, on))
            self._menu.addAction(action)

        self._menu.addSeparator()
        self._menu.addAction("Quit", self._app.quit)

        self._icon.setToolTip(f"{APP_NAME}\n" + "\n".join(lines))

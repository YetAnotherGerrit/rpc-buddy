"""Tray icon — the main way to interact with RPC Buddy on KDE Plasma."""

import logging
from collections.abc import Callable
from importlib.resources import files

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from rpc_buddy import APP_ID, APP_NAME
from rpc_buddy.activity import HealthState
from rpc_buddy.engine import Engine, EngineState
from rpc_buddy.gui import style

log = logging.getLogger(__name__)


def app_icon() -> QIcon:
    fallback = QIcon(str(files("rpc_buddy") / "resources" / "icon.svg"))
    return QIcon.fromTheme(APP_ID, fallback)


def needs_attention(state: EngineState) -> bool:
    """Discord can't be reached: the tray icon shows a warning badge."""
    return state.discord.state in (HealthState.NEEDS_SETUP, HealthState.ERROR)


def warning_icon(base: QIcon) -> QIcon:
    """``base`` with an amber "!" badge in the bottom-right corner."""
    icon = QIcon()
    for size in (16, 22, 24, 32, 48, 64, 128):
        pixmap = base.pixmap(size, size)
        if pixmap.isNull():
            continue
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        badge = max(8, size * (0.62 if size <= 24 else 0.55))
        rect = QRectF(size - badge, size - badge, badge, badge)
        p.setPen(QPen(QColor("white"), max(1.0, size / 24)))
        p.setBrush(QColor(style.AMBER))
        p.drawEllipse(rect.adjusted(0.5, 0.5, -0.5, -0.5))
        font = p.font()
        font.setBold(True)
        font.setPixelSize(max(6, int(badge * 0.75)))
        p.setFont(font)
        p.setPen(QColor("white"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "!")
        p.end()
        icon.addPixmap(pixmap)
    return icon


def tooltip_text(state: EngineState) -> str:
    """A short, general status for the tray tooltip (no titles)."""
    if state.paused:
        status = "Paused — nothing is shown on Discord"
    else:
        count = len(state.shown)
        status = {0: "Nothing on Discord"}.get(
            count, f"{count} {'activity' if count == 1 else 'activities'} on Discord"
        )
    if not state.discord.ok:
        status += f"\n⚠ {state.discord.message or 'Discord not reachable'}"
    return f"{APP_NAME}\n{status}"


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
        self._normal_icon = app_icon()
        self._warning_icon = warning_icon(self._normal_icon)
        self._warning = False
        self._icon = QSystemTrayIcon(self._normal_icon)
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
        warning = needs_attention(state)
        if warning != self._warning:
            self._warning = warning
            self._icon.setIcon(self._warning_icon if warning else self._normal_icon)
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
            # Titles can contain "&", which Qt would treat as a shortcut marker.
            self._menu.addAction(line.replace("&", "&&")).setEnabled(False)

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

        # No titles in the tooltip: it is rendered by the desktop (possibly as
        # HTML) and shows up on mere hover.
        self._icon.setToolTip(tooltip_text(state))

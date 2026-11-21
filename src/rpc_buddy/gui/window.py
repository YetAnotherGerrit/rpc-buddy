"""Main window: what's on Discord now, quick toggles, sources, hidden items."""

import time
from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from rpc_buddy import APP_NAME
from rpc_buddy.activity import ActivityType, Health, HealthState
from rpc_buddy.engine import Engine, EngineState, Item, ModuleStatus
from rpc_buddy.gui import style
from rpc_buddy.gui.covers import CoverLoader
from rpc_buddy.gui.tray import app_icon
from rpc_buddy.gui.widgets import CoverImage, FlowLayout, ToggleSwitch
from rpc_buddy.module import Setting

# Default window size, chosen for Full HD (1920×1080) screens.
DEFAULT_SIZE = (600, 860)

_SYMBOLS = {
    HealthState.OK: style.OK,
    HealthState.STARTING: style.BUSY,
    HealthState.NEEDS_SETUP: style.WARNING,
    HealthState.ERROR: style.ERROR,
    HealthState.DISABLED: style.OFF,
}

_KINDS = {
    ActivityType.PLAYING: "PLAYING",
    ActivityType.LISTENING: "LISTENING",
    ActivityType.WATCHING: "WATCHING",
}

# Module id -> (theme icon, fallback symbol) for the source list.
_SOURCE_ICONS = {"steam": ("input-gaming", "▶"), "mpris": ("audio-x-generic", "♫")}


def _label(text: str = "", name: str = "", wrap: bool = False) -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


def _health_html(health: Health, fallback: str = "") -> str:
    return style.status_html(_SYMBOLS[health.state], health.message or fallback)


def _duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def _card() -> QFrame:
    card = QFrame()
    card.setObjectName("Card")
    return card


def _divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    return line


def _section(text: str) -> QLabel:
    label = _label(text.upper(), "Section")
    font = style.scaled_font(label, 0.85, bold=True)
    font.setLetterSpacing(font.SpacingType.AbsoluteSpacing, 1.0)
    label.setFont(font)
    return label


class ActivityCard(QFrame):
    """One activity as Discord shows it: cover, kind, title, time, Hide."""

    def __init__(self, covers: CoverLoader, on_hide: Callable[[Item, bool], None]):
        super().__init__()
        self.setObjectName("Card")
        self._covers = covers
        self._on_hide = on_hide
        self._status: ModuleStatus | None = None
        self._cover_url: str | None = None
        self._cover_key: tuple[str, str | None] | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(16)
        self._content = QWidget()
        content = QHBoxLayout(self._content)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(16)
        self._cover = CoverImage(84)
        content.addWidget(self._cover, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(2)
        self._kind = _label(name="Kind")
        self._kind.setFont(style.scaled_font(self._kind, 0.8, bold=True))
        self._title = _label(wrap=True)
        self._title.setFont(style.scaled_font(self._title, 1.35, bold=True))
        self._subtitle = _label(name="Muted", wrap=True)
        self._elapsed = _label(name="Elapsed")
        self._progress = QProgressBar()
        self._progress.setObjectName("Track")
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 1000)
        times = QHBoxLayout()
        times.setContentsMargins(0, 0, 0, 0)
        self._position = _label(name="Muted")
        self._length = _label(name="Muted")
        for label in (self._position, self._length):
            label.setFont(style.scaled_font(label, 0.8))
        times.addWidget(self._position)
        times.addStretch(1)
        times.addWidget(self._length)
        self._times = QWidget()
        self._times.setLayout(times)
        for widget in (self._kind, self._title, self._subtitle, self._elapsed, self._progress):
            text.addWidget(widget)
        text.addWidget(self._times)
        text.addStretch(1)
        content.addLayout(text, 1)
        layout.addWidget(self._content, 1)

        self._button = QPushButton()
        self._button.setObjectName("Soft")
        self._button.clicked.connect(self._toggle_hidden)
        layout.addWidget(self._button, 0, Qt.AlignmentFlag.AlignVCenter)

        # Laid over the dimmed content when the activity is not sent to Discord.
        self._overlay = _label(name="Overlay")
        self._overlay.setParent(self)
        self._overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._overlay.hide()

    def update_status(self, m: ModuleStatus, off_discord_reason: str = "") -> None:
        self._status = m
        a = m.activity
        music = a.type == ActivityType.LISTENING
        source = a.name or m.name
        self._kind.setText(f"{_KINDS.get(a.type, 'PLAYING')} · {source.upper()}")
        self._title.setText(a.details or a.large_text or m.summary)
        self._subtitle.setText(a.state or "")
        self._subtitle.setVisible(bool(a.details and a.state))

        kind = "music" if music else "game"
        if (kind, a.large_image) != self._cover_key:
            self._cover_key = (kind, a.large_image)
            self._cover_url = a.large_image
            self._cover.set_kind(kind)
            self._cover.show_placeholder()
            url = a.large_image
            self._covers.request(url, lambda pixmap: self._cover_loaded(url, pixmap))

        self._button.setText("Show" if m.hidden else "Hide")
        self._button.setVisible(m.item is not None)
        self._button.setToolTip(
            "Show this on Discord again"
            if m.hidden
            else "Keep this off Discord. You can show it again under Hidden."
        )
        if not off_discord_reason:
            self._content.setGraphicsEffect(None)
            self._overlay.hide()
        else:
            effect = QGraphicsOpacityEffect(self._content)
            effect.setOpacity(0.35)
            self._content.setGraphicsEffect(effect)
            self._overlay.setText(f"Not on Discord — {off_discord_reason}")
            self._overlay.show()
            self._place_overlay()
            QTimer.singleShot(0, self._place_overlay)  # again once the layout has settled
        self.tick()

    def _place_overlay(self) -> None:
        """Centre the overlay over the card's content (left of the button)."""
        area = self._content.geometry()
        self._overlay.adjustSize()
        width = min(self._overlay.width(), area.width())
        self._overlay.setGeometry(
            area.x() + (area.width() - width) // 2,
            area.y() + (area.height() - self._overlay.height()) // 2,
            width,
            self._overlay.height(),
        )
        self._overlay.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if not self._overlay.isHidden():
            self._place_overlay()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._overlay.isHidden():
            QTimer.singleShot(0, self._place_overlay)

    def _cover_loaded(self, url: str, pixmap) -> None:
        if url == self._cover_url:
            self._cover.show_image(pixmap)

    def tick(self) -> None:
        """Update elapsed time / progress (called every second)."""
        a = self._status.activity if self._status else None
        if a is None:
            return
        now = time.time()
        has_progress = bool(a.start and a.end and a.end > a.start)
        self._progress.setVisible(has_progress)
        self._times.setVisible(has_progress)
        self._elapsed.setVisible(not has_progress)
        if has_progress:
            total = a.end - a.start
            done = min(max(now - a.start, 0), total)
            self._progress.setValue(int(done / total * 1000))
            self._position.setText(_duration(done))
            self._length.setText(_duration(total))
        elif a.start:
            self._elapsed.setText(f"● {_duration(now - a.start)} elapsed")
        else:
            self._elapsed.setText("Paused" if a.type == ActivityType.LISTENING else "")

    def _toggle_hidden(self) -> None:
        if self._status and self._status.item:
            self._on_hide(self._status.item, not self._status.hidden)


class ModuleSettingsDialog(QDialog):
    """Settings of one module, generated from its ``settings`` declaration."""

    def __init__(self, parent: QWidget, engine: Engine, status: ModuleStatus):
        super().__init__(parent)
        self.setWindowTitle(f"{status.name} settings")
        self.setMinimumWidth(440)
        self._engine = engine
        self._id = status.id
        layout = QVBoxLayout(self)
        health = status.health
        if health.hint and not health.ok:
            hint = _label(
                style.status_html(_SYMBOLS[health.state], health.message, health.hint), wrap=True
            )
            hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(hint)
        form = QFormLayout()
        for setting in status.settings:
            widget = self._editor(setting, status.values.get(setting.key))
            if setting.help:
                widget.setToolTip(setting.help)
            form.addRow(setting.label, widget)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _editor(self, s: Setting, value) -> QWidget:
        def save(v) -> None:
            self._engine.set_module_setting(self._id, s.key, v)

        if s.kind == "bool":
            switch = ToggleSwitch(s.label)
            switch.setChecked(bool(value))
            switch.toggled.connect(save)
            return switch
        if s.kind == "choice":
            combo = QComboBox()
            for choice, label in s.choices:
                combo.addItem(label, choice)
            combo.setCurrentIndex(max(0, combo.findData(value)))
            combo.activated.connect(lambda _i: save(combo.currentData()))
            return combo
        if s.kind == "int":
            spin = QSpinBox()
            spin.setRange(s.minimum, s.maximum)
            spin.setSuffix(s.suffix)
            spin.setValue(int(value or 0))
            spin.editingFinished.connect(lambda: save(spin.value()))
            return spin
        edit = QLineEdit(str(value or ""))
        edit.setPlaceholderText(s.placeholder)
        edit.editingFinished.connect(lambda: save(edit.text().strip()))
        return edit


class SourceRow(QWidget):
    """A module in the source list: icon, name, health, settings, on/off."""

    def __init__(self, window: QWidget, engine: Engine, status: ModuleStatus):
        super().__init__()
        self._window = window
        self._engine = engine
        self._status = status
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        icon_name, fallback = _SOURCE_ICONS.get(status.id, ("application-x-executable", "•"))
        tile = _label(name="IconTile")
        tile.setFixedSize(38, 38)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QIcon.fromTheme(icon_name)
        if icon.isNull():
            tile.setText(fallback)
        else:
            tile.setPixmap(icon.pixmap(22, 22))
        layout.addWidget(tile)

        text = QVBoxLayout()
        text.setSpacing(1)
        name = _label(status.name)
        name.setFont(style.scaled_font(name, 1.05, bold=True))
        self._health = _label(wrap=True)
        self._health.setTextFormat(Qt.TextFormat.RichText)
        text.addWidget(name)
        text.addWidget(self._health)
        layout.addLayout(text, 1)

        if status.settings:
            gear = QToolButton()
            gear.setObjectName("Gear")
            gear.setIcon(QIcon.fromTheme("configure", QIcon.fromTheme("preferences-system")))
            if gear.icon().isNull():
                gear.setText("⚙")
            gear.setToolTip(f"{status.name} settings")
            gear.clicked.connect(self._open_settings)
            layout.addWidget(gear)

        self._switch = ToggleSwitch(f"{status.name} on/off")
        self._switch.toggled.connect(lambda on: engine.set_module_enabled(status.id, on))
        layout.addWidget(self._switch)
        self.update_status(status)

    def update_status(self, status: ModuleStatus) -> None:
        self._status = status
        self._switch.blockSignals(True)
        self._switch.setChecked(status.enabled)
        self._switch.blockSignals(False)
        self._health.setText(_health_html(status.health, "Off" if not status.enabled else ""))
        self._health.setToolTip(status.health.hint if not status.health.ok else "")

    def _open_settings(self) -> None:
        ModuleSettingsDialog(self._window, self._engine, self._status).exec()


class MainWindow(QMainWindow):
    def __init__(
        self,
        engine: Engine,
        quit_app: Callable[[], None],
        keep_running: bool,
        open_setup: Callable[[], None],
        on_first_hide: Callable[[], None] = lambda: None,
    ):
        super().__init__()
        self._engine = engine
        self._keep_running = keep_running  # closing hides the window (tray available)
        self._quit_app = quit_app
        self._open_setup = open_setup
        self._on_first_hide = on_first_hide
        self._close_hint_shown = True  # updated from the engine state
        self._sized = False
        self._theme: style.Theme | None = None
        self._covers = CoverLoader()
        self._cards: dict[str, ActivityCard] = {}
        self._sources: dict[str, SourceRow] = {}
        self._hidden_items: tuple[Item, ...] | None = None
        self.setWindowTitle(APP_NAME)
        self.setObjectName("Main")

        content = QWidget()
        content.setObjectName("MainContent")
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(24, 20, 24, 20)
        self._layout.setSpacing(12)

        self._layout.addLayout(self._make_header())
        self._layout.addSpacing(6)
        self._layout.addWidget(_section("Your activity"))
        self._cards_box = QVBoxLayout()
        self._cards_box.setSpacing(12)
        self._layout.addLayout(self._cards_box)
        self._empty = self._make_empty_card()
        self._cards_box.addWidget(self._empty)
        self._layout.addWidget(self._make_toggles())

        self._layout.addSpacing(8)
        self._layout.addWidget(_section("Sources"))
        self._sources_card = _card()
        self._sources_box = QVBoxLayout(self._sources_card)
        self._sources_box.setContentsMargins(16, 14, 16, 14)
        self._sources_box.setSpacing(12)
        self._layout.addWidget(self._sources_card)

        self._layout.addSpacing(8)
        self._layout.addWidget(_section("Hidden"))
        self._hidden_box = QWidget()
        self._hidden_flow = FlowLayout(self._hidden_box)
        self._layout.addWidget(self._hidden_box)
        self._layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("MainScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(scroll, 1)
        central_layout.addWidget(self._make_footer())
        self.setCentralWidget(central)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._apply_theme()

    # --- building blocks --------------------------------------------------

    def _make_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(44, 44))
        header.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = _label(APP_NAME)
        title.setFont(style.scaled_font(title, 1.55, bold=True))
        titles.addWidget(title)
        titles.addWidget(_label("Your games and music on Discord", "Muted"))
        header.addLayout(titles, 1)
        self._badge = _label("● Looking for Discord…", "BadgeWarn")
        header.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignVCenter)
        return header

    def _make_empty_card(self) -> QFrame:
        card = _card()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        text = QVBoxLayout()
        self._empty_title = _label()
        self._empty_title.setFont(style.scaled_font(self._empty_title, 1.1, bold=True))
        self._empty_text = _label(name="Muted", wrap=True)
        text.addWidget(self._empty_title)
        text.addWidget(self._empty_text)
        layout.addLayout(text, 1)
        self._resume = QPushButton("Resume")
        self._resume.setObjectName("Soft")
        self._resume.clicked.connect(lambda: self._engine.set_paused(False))
        layout.addWidget(self._resume, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _make_toggles(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        self._pause = self._toggle_row(
            layout, "Pause presence", "Show nothing on Discord for now", self._engine.set_paused
        )
        layout.addWidget(_divider())
        self._autostart = self._toggle_row(
            layout, "Start with my desktop", "Runs quietly in the tray", self._engine.set_autostart
        )
        self._autostart_error = _label(wrap=True)
        self._autostart_error.setTextFormat(Qt.TextFormat.RichText)
        self._autostart_error.hide()
        layout.addWidget(self._autostart_error)
        return card

    def _toggle_row(self, layout, title: str, subtitle: str, on_toggle) -> ToggleSwitch:
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(1)
        name = _label(title)
        name.setFont(style.scaled_font(name, 1.0, bold=True))
        text.addWidget(name)
        text.addWidget(_label(subtitle, "Muted"))
        row.addLayout(text, 1)
        switch = ToggleSwitch(title)
        switch.toggled.connect(on_toggle)
        row.addWidget(switch, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(row)
        return switch

    def _make_footer(self) -> QFrame:
        """Always visible: explains what closing does, and how to really quit."""
        footer = QFrame()
        footer.setObjectName("Footer")
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(24, 12, 24, 14)
        if self._keep_running:
            text = (
                f"Closing this window keeps {APP_NAME} running in the tray, "
                "so your activity stays visible on Discord."
            )
        else:
            text = f"Closing this window quits {APP_NAME} — your activity disappears from Discord."
        hint = _label(style.status_html(style.INFO, text), "Muted", wrap=True)
        hint.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        setup = QPushButton("Run setup check…")
        setup.setObjectName("Link")
        setup.setCursor(Qt.CursorShape.PointingHandCursor)
        setup.clicked.connect(self._open_setup)
        buttons.addWidget(setup)
        buttons.addStretch(1)
        if self._keep_running:
            hide = QPushButton(style.theme_icon("window-minimize", "go-down"), "Hide to tray")
            hide.setObjectName("Soft")
            hide.setToolTip(f"Close this window; {APP_NAME} keeps running in the tray.")
            hide.clicked.connect(self.close)
            buttons.addWidget(hide)
        quit_button = QPushButton(style.theme_icon("application-exit"), f"Quit {APP_NAME}")
        quit_button.setObjectName("Soft")
        quit_button.setToolTip(f"Stop {APP_NAME}. Your activity disappears from Discord.")
        quit_button.clicked.connect(self._quit_app)
        buttons.addWidget(quit_button)
        layout.addLayout(buttons)
        return footer

    # --- state ------------------------------------------------------------

    def on_state(self, state: EngineState) -> None:
        self._update_badge(state.discord)
        self._update_cards(state)
        for widget, value in ((self._pause, state.paused), (self._autostart, state.autostart)):
            widget.blockSignals(True)
            widget.setChecked(value)
            widget.blockSignals(False)
        self._autostart_error.setVisible(bool(state.autostart_error))
        if state.autostart_error:
            self._autostart_error.setText(
                style.status_html(style.WARNING, f"Autostart: {state.autostart_error}")
            )
        self._update_sources(state)
        self._update_hidden(state.hidden)
        self._close_hint_shown = state.close_hint_shown

    def _update_badge(self, discord: Health) -> None:
        self._badge.setText(f"● {discord.message or 'Discord'}")
        name = "BadgeOk" if discord.ok else "BadgeWarn"
        self._badge.setToolTip(discord.hint)
        if self._badge.objectName() != name:
            self._badge.setObjectName(name)
            self._badge.style().unpolish(self._badge)
            self._badge.style().polish(self._badge)
        self._badge.updateGeometry()

    def _update_cards(self, state: EngineState) -> None:
        # Also while paused: a preview of what would be shown, so games can be
        # hidden before they ever reach Discord.
        active = [m for m in state.modules if m.activity is not None]
        active_ids = {m.id for m in active}
        for module_id in list(self._cards):
            if module_id not in active_ids:
                self._cards.pop(module_id).deleteLater()
        for i, m in enumerate(active):
            card = self._cards.get(m.id)
            if card is None:
                card = ActivityCard(self._covers, self._engine.set_hidden)
                self._cards[m.id] = card
                self._cards_box.insertWidget(i, card)
            card.update_status(m, state.off_discord_reason(m))
        self._empty.setVisible(not active)
        self._resume.setVisible(state.paused)
        if state.paused:
            self._empty_title.setText("Presence paused")
            self._empty_text.setText("Nothing is shown on Discord until you resume.")
        else:
            self._empty_title.setText("Nothing on Discord right now")
            self._empty_text.setText("Start a Steam game or play some music — it shows up here.")

    def _update_sources(self, state: EngineState) -> None:
        for m in state.modules:
            row = self._sources.get(m.id)
            if row is None:
                if self._sources:
                    self._sources_box.addWidget(_divider())
                row = SourceRow(self, self._engine, m)
                self._sources[m.id] = row
                self._sources_box.addWidget(row)
            else:
                row.update_status(m)

    def _update_hidden(self, items: tuple[Item, ...]) -> None:
        if items == self._hidden_items:
            return
        self._hidden_items = items
        while (child := self._hidden_flow.takeAt(0)) is not None:
            if child.widget():
                child.widget().deleteLater()
        for item in items:
            chip = QPushButton(f"{item.label}  ✕")
            chip.setObjectName("Chip")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip("Show on Discord again")
            chip.clicked.connect(lambda _c=False, i=item: self._engine.set_hidden(i, False))
            self._hidden_flow.addWidget(chip)
        if not items:
            self._hidden_flow.addWidget(
                _label("Use “Hide” on an activity to keep it off Discord.", "Muted")
            )

    def _tick(self) -> None:
        if self.isVisible():
            for card in self._cards.values():
                card.tick()

    # --- theme ------------------------------------------------------------

    def _apply_theme(self) -> None:
        theme = style.theme(QApplication.palette())
        if theme != self._theme:
            self._theme = theme
            self.setStyleSheet(style.stylesheet(theme))

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt API
        if event.type() in (QEvent.Type.ApplicationPaletteChange, QEvent.Type.PaletteChange):
            self._apply_theme()  # the desktop switched between light and dark
        super().changeEvent(event)

    # --- window -----------------------------------------------------------

    def _apply_default_size(self) -> None:
        """Fits a Full HD screen with a panel; smaller screens get 90% + scrolling."""
        screen = self.screen().availableGeometry()
        self.resize(
            min(DEFAULT_SIZE[0], int(screen.width() * 0.9)),
            min(DEFAULT_SIZE[1], int(screen.height() * 0.9)),
        )

    def show_and_raise(self) -> None:
        if not self._sized:  # only the first time; later the user's size is kept
            self._sized = True
            self._apply_default_size()
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self._keep_running:
            event.ignore()
            self.hide()
            if not self._close_hint_shown:
                self._close_hint_shown = True
                self._on_first_hide()
        else:
            event.accept()
            self._quit_app()

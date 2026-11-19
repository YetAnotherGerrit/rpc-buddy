"""First-run setup check dialog."""

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from rpc_buddy import APP_NAME
from rpc_buddy.engine import EngineState
from rpc_buddy.gui import style
from rpc_buddy.setup_checks import Check, CheckState, Environment, run_checks

_SYMBOLS = {CheckState.OK: style.OK, CheckState.WARNING: style.WARNING, CheckState.INFO: style.INFO}


def _label(text: str, *, bold: bool = False) -> QLabel:
    label = QLabel(f"<b>{text}</b>" if bold else text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class CheckRow(QFrame):
    def __init__(self, check: Check):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        grid = QGridLayout(self)
        icon = QLabel(style.symbol_html(_SYMBOLS[check.state]))
        icon.setTextFormat(Qt.TextFormat.RichText)
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        font = icon.font()
        font.setPointSizeF(font.pointSizeF() * 1.4)
        icon.setFont(font)
        grid.addWidget(icon, 0, 0, 3, 1)
        grid.addWidget(_label(check.title, bold=True), 0, 1)
        grid.addWidget(_label(check.message), 1, 1)
        row = 2
        if check.command:
            line = QHBoxLayout()
            edit = QLineEdit(check.command)
            edit.setReadOnly(True)
            edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
            edit.setCursorPosition(0)
            copy = QPushButton("Copy")
            copy.clicked.connect(lambda: QApplication.clipboard().setText(check.command))
            line.addWidget(edit, 1)
            line.addWidget(copy)
            grid.addLayout(line, row, 1)
            row += 1
        if check.note:
            grid.addWidget(_label(check.note), row, 1)
        grid.setColumnStretch(1, 1)


# Answers to the Spotify question; only "via_buddy" shows Spotify through RPC Buddy.
SPOTIFY_ANSWERS = (
    ("linked", "Yes, it's linked — Discord shows Spotify itself"),
    ("via_buddy", "No — show Spotify through RPC Buddy"),
    ("not_used", "I don't use Spotify"),
)


class SpotifyQuestion(QFrame):
    """Asks whether Spotify is linked in Discord (then Discord shows it itself)."""

    def __init__(self, on_answer: Callable[[str], None]):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.addWidget(_label("Spotify", bold=True))
        layout.addWidget(
            _label(
                "Is your Spotify account linked to Discord (Discord settings → Connections)? "
                "Then Discord already shows what you play on Spotify. If not, RPC Buddy can "
                "show it for you."
            )
        )
        self._buttons: dict[str, QRadioButton] = {}
        for answer, text in SPOTIFY_ANSWERS:
            button = QRadioButton(text)
            layout.addWidget(button)
            self._buttons[answer] = button
        self._buttons["linked"].setChecked(True)
        # Connect only after the default is set, so it doesn't count as an answer.
        for answer, button in self._buttons.items():
            button.toggled.connect(lambda on, a=answer: on and on_answer(a))
        layout.addWidget(_label("You can change this later in the main window (Music)."))

    def set_value(self, include_spotify: bool, answer: str | None) -> None:
        """Show the stored answer; the "Include Spotify" switch always wins."""
        if include_spotify:
            answer = "via_buddy"
        elif answer not in ("linked", "not_used"):
            answer = "linked"
        button = self._buttons[answer]
        if not button.isChecked():
            for b in self._buttons.values():
                b.blockSignals(True)
            button.setChecked(True)
            for b in self._buttons.values():
                b.blockSignals(False)


class SetupDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        environment: Callable[[], Environment],
        on_done: Callable[[], None],
        set_spotify_answer: Callable[[str], None],
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Set up {APP_NAME}")
        self.resize(620, 400)
        self._sized = False
        self._environment = environment
        self._state: EngineState | None = None

        layout = QVBoxLayout(self)
        self._intro = _label(
            f"{APP_NAME} shows your Steam games and music on Discord. "
            "Here is what it found on your system:"
        )
        layout.addWidget(self._intro)

        # Rows scroll if the screen is too small, instead of being squeezed.
        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self._rows = QVBoxLayout()
        content_layout.addLayout(self._rows)
        # Created once (not re-rendered), so a click is never lost.
        self._spotify = SpotifyQuestion(set_spotify_answer)
        content_layout.addWidget(self._spotify)
        content_layout.addStretch(1)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll, 1)

        buttons = QDialogButtonBox()
        recheck = buttons.addButton("Check again", QDialogButtonBox.ButtonRole.ActionRole)
        recheck.clicked.connect(self._render)
        done = buttons.addButton("Done", QDialogButtonBox.ButtonRole.AcceptRole)
        done.setDefault(True)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self._buttons = buttons
        self.accepted.connect(on_done)

    def on_state(self, state: EngineState) -> None:
        changed = self._state is None or (
            (state.discord, [(m.enabled, m.health) for m in state.modules])
            != (self._state.discord, [(m.enabled, m.health) for m in self._state.modules])
        )
        self._state = state
        music = next((m for m in state.modules if m.id == "mpris"), None)
        self._spotify.setVisible(music is not None and music.enabled)
        if music is not None:
            self._spotify.set_value(
                bool(music.values.get("include_spotify", False)),
                music.values.get("spotify_answer"),
            )
        if changed and self.isVisible():
            self._render()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._render()
        super().showEvent(event)

    def _render(self) -> None:
        if self._state is None:
            return
        while self._rows.count():
            widget = self._rows.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for check in run_checks(self._state, self._environment()):
            self._rows.addWidget(CheckRow(check))
        if not self._sized:
            self._sized = True
            # Measure once the new rows are laid out.
            QTimer.singleShot(0, self._fit)

    def _fit(self) -> None:
        """As tall as the content needs, at most 90% of the screen (then it scrolls)."""
        layout = self.layout()
        margins = layout.contentsMargins()
        inner_width = self.width() - margins.left() - margins.right()
        scrollbar = self.style().pixelMetric(self.style().PixelMetric.PM_ScrollBarExtent)
        height = (
            margins.top()
            + self._intro.heightForWidth(inner_width)
            + self._content.layout().totalHeightForWidth(inner_width - scrollbar)
            + self._buttons.sizeHint().height()
            + 2 * layout.spacing()
            + margins.bottom()
        )
        screen = self.screen().availableGeometry()
        self.resize(self.width(), min(height, int(screen.height() * 0.9)))

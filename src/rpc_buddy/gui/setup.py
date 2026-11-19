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


class SetupDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        environment: Callable[[], Environment],
        on_done: Callable[[], None],
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Set up {APP_NAME}")
        self.resize(620, 400)
        self._sized = False
        self._environment = environment
        self._state: EngineState | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(
            _label(
                f"{APP_NAME} shows your Steam games and music on Discord. "
                "Here is what it found on your system:"
            )
        )
        self._rows = QVBoxLayout()
        layout.addLayout(self._rows)
        layout.addStretch(1)

        buttons = QDialogButtonBox()
        recheck = buttons.addButton("Check again", QDialogButtonBox.ButtonRole.ActionRole)
        recheck.clicked.connect(self._render)
        done = buttons.addButton("Done", QDialogButtonBox.ButtonRole.AcceptRole)
        done.setDefault(True)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self.accepted.connect(on_done)

    def on_state(self, state: EngineState) -> None:
        changed = self._state is None or (
            (state.discord, [(m.enabled, m.health) for m in state.modules])
            != (self._state.discord, [(m.enabled, m.health) for m in self._state.modules])
        )
        self._state = state
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
            QTimer.singleShot(0, lambda: style.fit_to_content(self, self))

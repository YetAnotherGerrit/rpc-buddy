"""Main window: status, modules with their settings, hidden items."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from rpc_buddy import APP_NAME
from rpc_buddy.activity import Health, HealthState
from rpc_buddy.engine import Engine, EngineState, Item, ModuleStatus
from rpc_buddy.module import Setting

_ICONS = {
    HealthState.OK: "✔",
    HealthState.STARTING: "…",
    HealthState.NEEDS_SETUP: "⚠",
    HealthState.ERROR: "✖",
    HealthState.DISABLED: "○",
}


def _health_text(health: Health, fallback: str = "") -> str:
    text = f"{_ICONS[health.state]} {health.message or fallback}".strip()
    if health.hint and not health.ok:
        text += f"\n{health.hint}"
    return text


def _wrapping_label() -> QLabel:
    label = QLabel()
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class ModuleBox(QGroupBox):
    """One module: enable toggle, health, generated settings form."""

    def __init__(self, engine: Engine, status: ModuleStatus):
        super().__init__(status.name)
        self._engine = engine
        self._id = status.id
        self.setCheckable(True)
        self.setChecked(status.enabled)
        self.toggled.connect(lambda on: engine.set_module_enabled(self._id, on))

        layout = QVBoxLayout(self)
        self._health = _wrapping_label()
        layout.addWidget(self._health)

        self._editors: dict[str, tuple[QWidget, Callable]] = {}
        if status.settings:
            form = QFormLayout()
            for setting in status.settings:
                widget, setter = self._make_editor(setting)
                if setting.help:
                    widget.setToolTip(setting.help)
                form.addRow(setting.label, widget)
                self._editors[setting.key] = (widget, setter)
            layout.addLayout(form)
        self.update_status(status)

    def _make_editor(self, s: Setting) -> tuple[QWidget, Callable]:
        save = self._engine.set_module_setting
        if s.kind == "choice":
            combo = QComboBox()
            for value, label in s.choices:
                combo.addItem(label, value)
            combo.activated.connect(lambda _i: save(self._id, s.key, combo.currentData()))

            def set_combo(v):
                combo.setCurrentIndex(max(0, combo.findData(v)))

            return combo, set_combo
        if s.kind == "int":
            spin = QSpinBox()
            spin.setRange(s.minimum, s.maximum)
            spin.setSuffix(s.suffix)
            spin.editingFinished.connect(lambda: save(self._id, s.key, spin.value()))
            return spin, lambda v: spin.setValue(int(v or 0))
        edit = QLineEdit()
        edit.setPlaceholderText(s.placeholder)
        edit.editingFinished.connect(lambda: save(self._id, s.key, edit.text().strip()))
        return edit, lambda v: edit.setText(str(v or ""))

    def update_status(self, status: ModuleStatus) -> None:
        self.blockSignals(True)
        self.setChecked(status.enabled)
        self.blockSignals(False)
        self._health.setText(_health_text(status.health, "Off" if not status.enabled else ""))
        for key, (widget, setter) in self._editors.items():
            if not widget.hasFocus():  # don't overwrite what the user is editing
                setter(status.values.get(key))


class ItemList(QWidget):
    """A list of games / sources with one action button."""

    def __init__(self, title: str, button: str, action: Callable[[Item], None]):
        super().__init__()
        self._items: tuple[Item, ...] = ()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(title))
        self._list = QListWidget()
        self._list.setMinimumHeight(120)
        layout.addWidget(self._list)
        self._button = QPushButton(button)
        self._button.setEnabled(False)
        self._button.clicked.connect(self._run)
        self._list.itemSelectionChanged.connect(
            lambda: self._button.setEnabled(bool(self._list.selectedItems()))
        )
        self._list.itemDoubleClicked.connect(lambda _i: self._run())
        layout.addWidget(self._button)
        self._action = action

    def set_items(self, items: tuple[Item, ...]) -> None:
        if items == self._items:
            return
        self._items = items
        self._list.clear()
        for item in items:
            entry = QListWidgetItem(item.label)
            entry.setData(Qt.ItemDataRole.UserRole, item)
            self._list.addItem(entry)
        self._button.setEnabled(False)

    def _run(self) -> None:
        for entry in self._list.selectedItems():
            self._action(entry.data(Qt.ItemDataRole.UserRole))


class MainWindow(QMainWindow):
    def __init__(self, engine: Engine, quit_app: Callable[[], None], keep_running: bool):
        super().__init__()
        self._engine = engine
        self._keep_running = keep_running  # closing hides the window (tray available)
        self._quit_app = quit_app
        self._module_boxes: dict[str, ModuleBox] = {}
        self.setWindowTitle(APP_NAME)
        self.resize(560, 720)

        content = QWidget()
        self._layout = QVBoxLayout(content)

        status = QGroupBox("Status")
        status_layout = QVBoxLayout(status)
        self._discord = _wrapping_label()
        self._shown = _wrapping_label()
        self._pause = QCheckBox("Pause presence (show nothing on Discord)")
        self._pause.toggled.connect(engine.set_paused)
        status_layout.addWidget(self._discord)
        status_layout.addWidget(self._shown)
        status_layout.addWidget(self._pause)
        self._layout.addWidget(status)

        self._modules_anchor = self._layout.count()

        hidden = QGroupBox("Hidden games and music sources")
        hidden_layout = QHBoxLayout(hidden)
        self._recent = ItemList("Seen recently", "Hide", lambda i: engine.set_hidden(i, True))
        self._hidden = ItemList("Hidden", "Show again", lambda i: engine.set_hidden(i, False))
        hidden_layout.addWidget(self._recent)
        hidden_layout.addWidget(self._hidden)
        self._layout.addWidget(hidden)

        self._layout.addStretch(1)
        quit_row = QHBoxLayout()
        quit_row.addStretch(1)
        quit_button = QPushButton(f"Quit {APP_NAME}")
        quit_button.clicked.connect(quit_app)
        quit_row.addWidget(quit_button)
        self._layout.addLayout(quit_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self.setCentralWidget(scroll)

    def on_state(self, state: EngineState) -> None:
        self._discord.setText(_health_text(state.discord))
        if state.paused:
            shown = "Paused — nothing is shown on Discord."
        else:
            shown = "\n".join(f"• {m.summary}" for m in state.shown) or "Nothing shown right now."
        hidden_now = [m.summary for m in state.modules if m.hidden and m.activity]
        if hidden_now and not state.paused:
            shown += "\n" + "\n".join(f"• {s} (hidden)" for s in hidden_now)
        self._shown.setText(shown)
        self._pause.blockSignals(True)
        self._pause.setChecked(state.paused)
        self._pause.blockSignals(False)

        for i, m in enumerate(state.modules):
            box = self._module_boxes.get(m.id)
            if box is None:
                box = ModuleBox(self._engine, m)
                self._module_boxes[m.id] = box
                self._layout.insertWidget(self._modules_anchor + i, box)
            else:
                box.update_status(m)

        self._recent.set_items(state.recent)
        self._hidden.set_items(state.hidden)

    def show_and_raise(self) -> None:
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self._keep_running:
            event.ignore()
            self.hide()
        else:
            event.accept()
            self._quit_app()

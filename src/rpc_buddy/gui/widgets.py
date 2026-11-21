"""Small reusable widgets: toggle switch, wrapping layout, cover image."""

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPalette, QPixmap
from PySide6.QtWidgets import QAbstractButton, QLabel, QLayout, QSizePolicy, QWidget

from rpc_buddy.gui.style import mix


class ToggleSwitch(QAbstractButton):
    """An on/off switch; behaves like a checkable button (``toggled`` signal)."""

    def __init__(self, accessible_name: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(accessible_name)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(42, 24)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        palette = self.palette()
        window = palette.color(QPalette.ColorRole.Window)
        text = palette.color(QPalette.ColorRole.WindowText)
        track = (
            palette.color(QPalette.ColorRole.Highlight)
            if self.isChecked()
            else mix(window, text, 0.3)
        )
        if not self.isEnabled():
            track = mix(track, window, 0.5)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        radius = rect.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(rect, radius, radius)
        knob = rect.height() - 6
        x = rect.right() - knob - 3 if self.isChecked() else rect.left() + 3
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, rect.top() + 3, knob, knob))
        if self.hasFocus():
            focus = QColor(palette.color(QPalette.ColorRole.Highlight))
            focus.setAlpha(120)
            p.setPen(focus)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(-0.5, -0.5, 0.5, 0.5), radius, radius)


class FlowLayout(QLayout):
    """Places widgets left to right and wraps them into new lines."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 8):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: N802 - Qt API
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802 - Qt API
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802 - Qt API
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt API
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt API
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt API
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt API
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _arrange(self, rect: QRect, apply: bool) -> int:
        x, y, line_height = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > rect.right() and line_height > 0:
                x, y = rect.x(), y + line_height + self._spacing
                line_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


# Placeholder gradients per activity kind (when there is no cover image).
_PLACEHOLDERS = {
    "game": ("#e0773a", "#7a2f8c", "input-gaming", "▶"),
    "music": ("#2fa4b8", "#2c4a9a", "audio-x-generic", "♫"),
}


class CoverImage(QLabel):
    """A square cover with rounded corners, or a coloured placeholder."""

    def __init__(self, size: int, kind: str = "game", parent: QWidget | None = None):
        super().__init__(parent)
        self._size = size
        self._kind = kind
        self.setFixedSize(size, size)
        self.show_placeholder()

    def set_kind(self, kind: str) -> None:
        self._kind = kind

    def show_placeholder(self) -> None:
        start, end, icon_name, fallback = _PLACEHOLDERS.get(self._kind, _PLACEHOLDERS["game"])
        pixmap = self._canvas()
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, self._size, self._size)
        gradient.setColorAt(0, QColor(start))
        gradient.setColorAt(1, QColor(end))
        p.setClipPath(self._rounded())
        p.fillRect(pixmap.rect(), gradient)
        icon = QIcon.fromTheme(icon_name)
        symbol = self._size // 2
        if not icon.isNull():
            icon.paint(
                p, QRect((self._size - symbol) // 2, (self._size - symbol) // 2, symbol, symbol)
            )
        else:
            font = p.font()
            font.setPixelSize(symbol)
            p.setFont(font)
            p.setPen(QColor(255, 255, 255, 220))
            p.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, fallback)
        p.end()
        self.setPixmap(pixmap)

    def show_image(self, image: QPixmap) -> None:
        pixmap = self._canvas()
        scaled = image.scaled(
            self._size,
            self._size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setClipPath(self._rounded())
        p.drawPixmap(
            (self._size - scaled.width()) // 2, (self._size - scaled.height()) // 2, scaled
        )
        p.end()
        self.setPixmap(pixmap)

    def _canvas(self) -> QPixmap:
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(round(self._size * ratio), round(self._size * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        return pixmap

    def _rounded(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self._size, self._size), 8, 8)
        return path

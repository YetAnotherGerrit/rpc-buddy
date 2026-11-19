"""Shared status symbols and colours (readable on light and dark themes)."""

import html

from PySide6.QtWidgets import QWidget

GREEN = "#2ea043"
AMBER = "#d29922"
RED = "#e5534b"
BLUE = "#4493f8"
GREY = "#8b949e"

OK = ("✔", GREEN)
WARNING = ("⚠", AMBER)
ERROR = ("✖", RED)
INFO = ("ℹ", BLUE)
BUSY = ("…", GREY)
OFF = ("○", GREY)


def symbol_html(symbol: tuple[str, str]) -> str:
    char, color = symbol
    return f'<span style="color:{color}; font-weight:bold">{char}</span>'


def status_html(symbol: tuple[str, str], text: str, details: str = "") -> str:
    """``symbol`` + escaped ``text``; optional ``details`` on following lines."""
    result = f"{symbol_html(symbol)}&nbsp;{html.escape(text)}"
    if details:
        result += "<br>" + html.escape(details).replace("\n", "<br>")
    return result


def fit_to_content(
    window: QWidget, content: QWidget, extra_width: int = 0, extra_height: int = 0
) -> None:
    """Resize ``window`` so ``content`` fits, at most 90% of the screen.

    ``extra_width``/``extra_height`` is the space around ``content`` (frames,
    scroll bars). Word-wrapped text gets taller when narrower, so the height
    is computed for the final width.
    """
    screen = window.screen().availableGeometry()
    width = min(
        max(window.width(), content.sizeHint().width() + extra_width),
        int(screen.width() * 0.9),
    )
    layout = content.layout()
    if layout is not None and layout.hasHeightForWidth():
        content_height = layout.totalHeightForWidth(width - extra_width)
    else:
        content_height = content.sizeHint().height()
    window.resize(width, min(content_height + extra_height, int(screen.height() * 0.9)))

"""Shared look: colours derived from the system palette, status symbols.

Nothing is hard-coded to light or dark: ``Theme`` is computed from the
current palette and the stylesheet is rebuilt when the desktop switches.
"""

import html
from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QPalette
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


DANGER = "#da373c"


def mix(a: QColor, b: QColor, t: float) -> QColor:
    """Blend ``a`` towards ``b`` by ``t`` (0..1)."""
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


@dataclass(frozen=True)
class Theme:
    dark: bool
    window: str
    card: str  # cards stand out from the window background
    raised: str  # buttons, chips, icon tiles on cards
    hover: str
    border: str
    footer: str
    text: str
    muted: str
    accent: str  # the user's accent colour (switches, progress)
    link: str
    ok_bg: str
    ok_fg: str
    warn_bg: str
    warn_fg: str


def theme(palette: QPalette) -> Theme:
    window = palette.color(QPalette.ColorRole.Window)
    text = palette.color(QPalette.ColorRole.WindowText)
    base = palette.color(QPalette.ColorRole.Base)
    dark = window.lightness() < 128
    if dark:
        card = mix(window, text, 0.06)
    else:
        card = base if base.lightness() > window.lightness() else mix(window, QColor("white"), 0.7)
    return Theme(
        dark=dark,
        window=window.name(),
        card=card.name(),
        raised=mix(window, text, 0.12 if dark else 0.08).name(),
        hover=mix(window, text, 0.2 if dark else 0.14).name(),
        border=mix(window, text, 0.14).name(),
        footer=mix(window, text, 0.03).name(),
        text=text.name(),
        muted=mix(text, window, 0.42).name(),
        accent=palette.color(QPalette.ColorRole.Highlight).name(),
        link=palette.color(QPalette.ColorRole.Link).name(),
        ok_bg="rgba(46,160,67,0.18)",
        ok_fg="#7ee2a0" if dark else "#1a7f37",
        warn_bg="rgba(210,153,34,0.2)",
        warn_fg="#f0c060" if dark else "#9a6700",
    )


def stylesheet(t: Theme) -> str:
    return f"""
    QWidget#Main, QScrollArea#MainScroll, QWidget#MainContent {{
        background: {t.window}; border: none;
    }}
    QFrame#Card {{ background: {t.card}; border-radius: 12px; }}
    QFrame#Footer {{ background: {t.footer}; border-top: 1px solid {t.border}; }}
    QFrame#Divider {{ background: {t.border}; max-height: 1px; min-height: 1px; border: none; }}
    QLabel#Section, QLabel#Kind {{ color: {t.muted}; font-weight: 700; }}
    QLabel#Muted {{ color: {t.muted}; }}
    QLabel#Elapsed {{ color: {GREEN}; font-weight: 600; }}
    QLabel#IconTile {{ background: {t.raised}; border-radius: 8px; }}
    QLabel#BadgeOk {{
        background: {t.ok_bg}; color: {t.ok_fg}; border-radius: 12px;
        padding: 4px 12px; font-weight: 600;
    }}
    QLabel#BadgeWarn {{
        background: {t.warn_bg}; color: {t.warn_fg}; border-radius: 12px;
        padding: 4px 12px; font-weight: 600;
    }}
    QPushButton#Soft, QPushButton#Chip {{
        background: {t.raised}; color: {t.text}; border: none;
        border-radius: 8px; padding: 6px 14px;
    }}
    QPushButton#Chip {{ border-radius: 14px; padding: 4px 12px; }}
    QPushButton#Soft:hover, QPushButton#Chip:hover {{ background: {t.hover}; }}
    QPushButton#Danger {{
        background: {DANGER}; color: white; border: none; border-radius: 8px;
        padding: 6px 14px; font-weight: 600;
    }}
    QPushButton#Danger:hover {{ background: #c42f34; }}
    QPushButton#Link {{
        background: transparent; color: {t.link}; border: none; padding: 6px 0;
    }}
    QPushButton#Link:hover {{ text-decoration: underline; }}
    QToolButton#Gear {{ background: transparent; border: none; border-radius: 6px; padding: 4px; }}
    QToolButton#Gear:hover {{ background: {t.hover}; }}
    QProgressBar#Track {{
        background: {t.border}; border: none; border-radius: 2px;
        max-height: 4px; min-height: 4px;
    }}
    QProgressBar#Track::chunk {{ background: {t.text}; border-radius: 2px; }}
    """


def scaled_font(widget: QWidget, factor: float = 1.0, bold: bool = False) -> QFont:
    """The widget's font, scaled relative to the user's font size."""
    font = QFont(widget.font())
    font.setPointSizeF(font.pointSizeF() * factor)
    font.setBold(bold)
    return font


def symbol_html(symbol: tuple[str, str]) -> str:
    char, color = symbol
    return f'<span style="color:{color}; font-weight:bold">{char}</span>'


def status_html(symbol: tuple[str, str], text: str, details: str = "") -> str:
    """``symbol`` + escaped ``text``; optional ``details`` on following lines."""
    result = f"{symbol_html(symbol)}&nbsp;{html.escape(text)}"
    if details:
        result += "<br>" + html.escape(details).replace("\n", "<br>")
    return result

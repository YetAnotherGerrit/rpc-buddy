"""Where Steam keeps its logs."""

from pathlib import Path


def steam_roots() -> list[Path]:
    home = Path.home()
    return [
        home / ".local/share/Steam",  # native
        home / ".steam/steam",  # native (symlink on most distros)
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",  # Flatpak
        home / ".var/app/com.valvesoftware.Steam/data/Steam",  # older Flatpak layout
    ]


def find_console_log() -> Path | None:
    for root in steam_roots():
        log = root / "logs" / "console_log.txt"
        if log.is_file():
            return log
    return None

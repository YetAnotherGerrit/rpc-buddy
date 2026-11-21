"""Where Steam keeps its logs and user data."""

from pathlib import Path

from rpc_buddy import APP_ID


def steam_roots(custom: str = "") -> list[Path]:
    """Steam folders to search; a folder set by the user comes first."""
    home = Path.home()
    roots = [Path(custom.strip()).expanduser()] if custom.strip() else []
    return roots + [
        home / ".local/share/Steam",  # native
        home / ".steam/steam",  # native (symlink on most distros)
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",  # Flatpak
        home / ".var/app/com.valvesoftware.Steam/data/Steam",  # older Flatpak layout
    ]


def find_console_log(roots: list[Path] | None = None) -> Path | None:
    for root in roots if roots is not None else steam_roots():
        log = root / "logs" / "console_log.txt"
        if log.is_file():
            return log
    return None


def override_command(folder: str = "") -> str:
    """The command that lets the Flatpak read a Steam folder in an unusual place."""
    base = folder.strip().rstrip("/") or "/path/to/Steam"
    return (
        f"flatpak override --user --filesystem={base}/logs:ro "
        f"--filesystem={base}/userdata:ro {APP_ID}"
    )

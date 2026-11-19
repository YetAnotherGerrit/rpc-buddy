"""XDG locations. Inside the Flatpak these resolve to ~/.var/app/<app-id>/…"""

import os
from pathlib import Path


def _xdg(var: str, fallback: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / fallback


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "rpc-buddy"


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache") / "rpc-buddy"


def in_flatpak() -> bool:
    return Path("/.flatpak-info").exists()

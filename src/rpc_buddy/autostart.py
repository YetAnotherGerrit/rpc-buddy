"""Start RPC Buddy with the desktop session.

Inside the Flatpak, the XDG Background portal creates (or removes) the
autostart entry; a Flatpak cannot write ~/.config/autostart itself. Outside
the Flatpak (development), the entry is written directly.
"""

import asyncio
import logging
import os
import shutil
import sys
from pathlib import Path

from dbus_fast import Variant

from rpc_buddy import APP_ID, APP_NAME, portal
from rpc_buddy.paths import in_flatpak

log = logging.getLogger(__name__)

RESPONSE_TIMEOUT = 120.0  # the desktop may ask the user


class AutostartError(Exception):
    pass


async def set_autostart(enabled: bool) -> None:
    """Enable or disable autostart. Raises AutostartError on failure."""
    if in_flatpak():
        await _portal_request(enabled)
    else:
        await asyncio.to_thread(write_desktop_entry, enabled, autostart_dir())


async def _portal_request(enabled: bool) -> None:
    try:
        response, results = await portal.request(
            "org.freedesktop.portal.Background",
            "RequestBackground",
            [""],
            {
                "reason": Variant("s", f"Start {APP_NAME} when you log in"),
                "autostart": Variant("b", enabled),
                "commandline": Variant("as", ["rpc-buddy", "--background"]),
            },
            timeout=RESPONSE_TIMEOUT,
        )
    except portal.PortalError as e:
        raise AutostartError(str(e)) from e
    if response != portal.SUCCESS or (enabled and results.get("autostart") is False):
        raise AutostartError("Autostart was not allowed by the desktop")
    log.info("Autostart %s via the Background portal", "enabled" if enabled else "disabled")


def autostart_dir() -> Path:
    config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config) / "autostart"


def write_desktop_entry(enabled: bool, directory: Path) -> None:
    entry = directory / f"{APP_ID}.desktop"
    if not enabled:
        entry.unlink(missing_ok=True)
        return
    exe = shutil.which("rpc-buddy") or sys.argv[0]
    directory.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        f"Exec={exe} --background\n"
        f"Icon={APP_ID}\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    log.info("Autostart entry written to %s", entry)

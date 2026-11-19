"""Start RPC Buddy with the desktop session.

Inside the Flatpak, the XDG Background portal creates (or removes) the
autostart entry; a Flatpak cannot write ~/.config/autostart itself. Outside
the Flatpak (development), the entry is written directly.
"""

import asyncio
import logging
import os
import secrets
import shutil
import sys
from pathlib import Path

from dbus_fast import Message, MessageType, Variant
from dbus_fast.aio import MessageBus

from rpc_buddy import APP_ID, APP_NAME
from rpc_buddy.paths import in_flatpak

log = logging.getLogger(__name__)

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
RESPONSE_TIMEOUT = 120.0  # the desktop may ask the user


class AutostartError(Exception):
    pass


def request_path(unique_name: str, token: str) -> str:
    """Object path of the portal Request for our ``handle_token``."""
    sender = unique_name.removeprefix(":").replace(".", "_")
    return f"{PORTAL_PATH}/request/{sender}/{token}"


async def set_autostart(enabled: bool) -> None:
    """Enable or disable autostart. Raises AutostartError on failure."""
    if in_flatpak():
        await _portal_request(enabled)
    else:
        await asyncio.to_thread(write_desktop_entry, enabled, autostart_dir())


async def _portal_request(enabled: bool) -> None:
    bus = await MessageBus().connect()
    try:
        token = "rpc_buddy_" + secrets.token_hex(8)
        path = request_path(bus.unique_name, token)
        future: asyncio.Future = asyncio.get_running_loop().create_future()

        def on_message(msg: Message) -> None:
            if (
                msg.message_type == MessageType.SIGNAL
                and msg.path == path
                and msg.member == "Response"
                and not future.done()
            ):
                future.set_result(msg.body)

        bus.add_message_handler(on_message)
        match = f"type='signal',interface='org.freedesktop.portal.Request',path='{path}'"
        await bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=[match],
            )
        )
        options = {
            "handle_token": Variant("s", token),
            "reason": Variant("s", f"Start {APP_NAME} when you log in"),
            "autostart": Variant("b", enabled),
            "commandline": Variant("as", ["rpc-buddy", "--background"]),
        }
        reply = await bus.call(
            Message(
                destination=PORTAL,
                path=PORTAL_PATH,
                interface="org.freedesktop.portal.Background",
                member="RequestBackground",
                signature="sa{sv}",
                body=["", options],
            )
        )
        if reply.message_type == MessageType.ERROR:
            raise AutostartError(f"Background portal unavailable: {reply.error_name}")
        try:
            response, results = await asyncio.wait_for(future, RESPONSE_TIMEOUT)
        except TimeoutError as e:
            raise AutostartError("The desktop did not answer the autostart request") from e
        if response != 0:
            raise AutostartError("Autostart was not allowed by the desktop")
        granted = results.get("autostart")
        if enabled and granted is not None and not granted.value:
            raise AutostartError("Autostart was not allowed by the desktop")
        log.info("Autostart %s via the Background portal", "enabled" if enabled else "disabled")
    finally:
        bus.disconnect()


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

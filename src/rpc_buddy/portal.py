"""Calls to XDG desktop portals — the desktop's own services for sandboxed apps.

A portal call returns a "Request" object; the result arrives later as its
``Response`` signal (e.g. after the user picked a folder in the desktop's
file dialog). ``request()`` hides that dance.
"""

import asyncio
import secrets
from typing import Any
from urllib.parse import unquote, urlparse

from dbus_fast import Message, MessageType, Variant
from dbus_fast.aio import MessageBus

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"

# Response codes of org.freedesktop.portal.Request.Response
SUCCESS, CANCELLED = 0, 1


class PortalError(Exception):
    pass


def request_path(unique_name: str, token: str) -> str:
    """Object path of the portal Request for our ``handle_token``."""
    sender = unique_name.removeprefix(":").replace(".", "_")
    return f"{PORTAL_PATH}/request/{sender}/{token}"


def _unwrap(value: Any) -> Any:
    return value.value if isinstance(value, Variant) else value


async def request(
    interface: str,
    method: str,
    args: list,
    options: dict[str, Variant],
    timeout: float | None,
) -> tuple[int, dict[str, Any]]:
    """Call ``interface.method(*args, options)`` and wait for its Response.

    Returns (response code, results). Raises PortalError if the portal is
    unavailable or doesn't answer within ``timeout`` seconds.
    """
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
        await bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=[f"type='signal',interface='org.freedesktop.portal.Request',path='{path}'"],
            )
        )
        signature = "".join("s" for _ in args) + "a{sv}"
        reply = await bus.call(
            Message(
                destination=PORTAL,
                path=PORTAL_PATH,
                interface=interface,
                member=method,
                signature=signature,
                body=[*args, {"handle_token": Variant("s", token), **options}],
            )
        )
        if reply.message_type == MessageType.ERROR:
            raise PortalError(f"Portal unavailable: {reply.error_name}")
        try:
            response, results = await asyncio.wait_for(future, timeout)
        except TimeoutError as e:
            raise PortalError("The desktop did not answer") from e
        return response, {k: _unwrap(v) for k, v in results.items()}
    finally:
        bus.disconnect()


def uri_to_path(uri: str) -> str:
    return unquote(urlparse(uri).path)


async def choose_folder(title: str) -> str | None:
    """Let the user pick a folder in the desktop's file dialog.

    The desktop grants the Flatpak (lasting) access to the chosen folder; the
    returned path is where the sandbox sees it (``/run/user/…/doc/…``).
    Returns None if the user cancelled.
    """
    response, results = await request(
        "org.freedesktop.portal.FileChooser",
        "OpenFile",
        ["", title],
        {"directory": Variant("b", True), "modal": Variant("b", True)},
        timeout=None,  # the user may take their time
    )
    if response != SUCCESS:
        return None
    uris = results.get("uris") or []
    return uri_to_path(uris[0]) if uris else None

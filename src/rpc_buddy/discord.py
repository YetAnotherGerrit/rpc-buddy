"""Publishing activities to the local Discord client over IPC.

One IPC connection is kept per Discord application (``client_id``): a game's
official application, or the RPC Buddy app. Discord shows activities of
different applications side by side.
"""

import asyncio
import contextlib
import logging
import math
import os
import time
from collections.abc import Callable
from typing import Protocol

from pypresence import AioPresence
from pypresence import exceptions as pp_exc
from pypresence.types import ActivityType as PPActivityType
from pypresence.types import StatusDisplayType as PPStatusDisplayType
from pypresence.utils import get_ipc_path

from rpc_buddy.activity import Activity, Health, HealthState

log = logging.getLogger(__name__)

# Errors that mean "Discord is not running / not reachable".
_UNREACHABLE = (
    pp_exc.DiscordNotFound,
    pp_exc.InvalidPipe,
    pp_exc.ConnectionTimeout,
    pp_exc.PipeClosed,
    pp_exc.ResponseTimeout,
    ConnectionError,
    FileNotFoundError,
)

NOT_RUNNING_HINT = (
    "Start Discord. If it is running, make sure RPC Buddy may access its IPC "
    "socket (Flatpak Discord: $XDG_RUNTIME_DIR/app/com.discordapp.Discord)."
)


class Connection(Protocol):
    client_id: str

    async def open(self) -> None: ...
    async def set_activity(self, activity: Activity | None) -> None: ...
    def is_alive(self) -> bool: ...
    def close(self) -> None: ...


class PypresenceConnection:
    """Thin adapter around pypresence's AioPresence.

    Isolates pypresence quirks — notably ``AioPresence.close()`` closes the
    whole asyncio event loop, so we disconnect manually.
    """

    def __init__(self, client_id: str):
        self.client_id = client_id
        self._rpc: AioPresence | None = None

    async def open(self) -> None:
        rpc = AioPresence(self.client_id, connection_timeout=5, response_timeout=5)
        await rpc.connect()
        self._rpc = rpc

    async def set_activity(self, activity: Activity | None) -> None:
        assert self._rpc is not None
        if activity is None:
            await self._rpc.clear(pid=os.getpid())
            return
        kwargs = {
            "activity_type": PPActivityType(int(activity.type)),
            "name": activity.name,
            "details": activity.details,
            "state": activity.state,
            "large_image": activity.large_image,
            "large_text": activity.large_text,
            "small_image": activity.small_image,
            "small_text": activity.small_text,
            "start": activity.start,
            "end": activity.end,
        }
        if activity.status_display is not None:
            kwargs["status_display_type"] = PPStatusDisplayType(int(activity.status_display))
        await self._rpc.update(pid=os.getpid(), **kwargs)

    def is_alive(self) -> bool:
        reader = self._rpc.sock_reader if self._rpc else None
        return reader is not None and not reader.at_eof()

    def close(self) -> None:
        rpc, self._rpc = self._rpc, None
        if rpc is None or rpc.sock_writer is None:
            return
        try:
            rpc.send_data(2, {"v": 1, "client_id": self.client_id})
            rpc.sock_writer.close()
        except Exception:  # noqa: BLE001 - best effort on shutdown
            pass


def discord_reachable() -> bool:
    """True if a Discord IPC socket can be found and connected to."""
    try:
        return get_ipc_path() is not None
    except OSError:
        return False


class DiscordSink:
    """Keeps Discord in sync with the desired set of activities.

    ``set_desired()`` may be called any time from the event loop; ``run()``
    reconciles in the background, reconnects after Discord restarts and
    respects Discord's rate limit (about 5 updates per 20 seconds).
    """

    MIN_INTERVAL = 4.0  # seconds between updates per connection
    RETRY_DELAY = 15.0  # seconds before retrying after a failure
    LIVENESS_INTERVAL = 10.0  # seconds between dead-connection checks

    def __init__(
        self,
        connection_factory: Callable[[str], Connection] = PypresenceConnection,
        on_status: Callable[[Health], None] | None = None,
        probe: Callable[[], bool] = discord_reachable,
    ):
        self._factory = connection_factory
        self.on_status = on_status or (lambda h: None)
        self._probe = probe
        self._desired: dict[str, Activity] = {}
        self._applied: dict[str, Activity] = {}
        self._conns: dict[str, Connection] = {}
        self._last_sent: dict[str, float] = {}
        self._rejected: dict[str, Activity] = {}
        self._wake = asyncio.Event()
        self.status = Health(HealthState.STARTING, "Looking for Discord…")

    def set_desired(self, desired: dict[str, Activity]) -> None:
        self._desired = dict(desired)
        self._wake.set()

    async def run(self) -> None:
        while True:
            self._wake.clear()
            delay = await self.reconcile()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=delay)

    async def reconcile(self) -> float | None:
        """Apply the desired state once. Returns seconds until the next check."""
        next_check = math.inf
        failed = False

        for cid, conn in list(self._conns.items()):
            if not conn.is_alive():
                log.info("Discord connection for %s was lost", cid)
                self._drop(cid)

        for cid in list(self._conns):
            if cid not in self._desired:
                await self._remove(cid)

        for cid, activity in self._desired.items():
            if self._applied.get(cid) == activity and cid in self._conns:
                continue
            if self._rejected.get(cid) == activity:
                continue
            wait = self._last_sent.get(cid, -math.inf) + self.MIN_INTERVAL - time.monotonic()
            if wait > 0:
                next_check = min(next_check, wait)
                continue
            try:
                conn = self._conns.get(cid)
                if conn is None:
                    conn = self._factory(cid)
                    await conn.open()
                    self._conns[cid] = conn
                    log.info("Connected to Discord as application %s", cid)
                await conn.set_activity(activity)
                self._applied[cid] = activity
                self._last_sent[cid] = time.monotonic()
            except pp_exc.InvalidID:
                log.warning("Discord rejected application id %s", cid)
                self._rejected[cid] = activity
                self._drop(cid)
            except _UNREACHABLE as e:
                log.debug("Discord not reachable: %r", e)
                self._drop(cid)
                failed = True
            except Exception:
                log.exception("Failed to publish activity for %s", cid)
                self._drop(cid)
                failed = True

        if failed:
            next_check = min(next_check, self.RETRY_DELAY)
            self._set_status(
                Health(HealthState.NEEDS_SETUP, "Discord not reachable", NOT_RUNNING_HINT)
            )
        elif self._conns:
            next_check = min(next_check, self.LIVENESS_INTERVAL)
            self._set_status(Health(HealthState.OK, "Connected to Discord"))
        else:
            # Nothing to show: just check whether Discord is around.
            next_check = min(next_check, self.RETRY_DELAY)
            if await asyncio.to_thread(self._probe):
                self._set_status(Health(HealthState.OK, "Discord found"))
            else:
                self._set_status(
                    Health(HealthState.NEEDS_SETUP, "Discord not reachable", NOT_RUNNING_HINT)
                )

        return None if next_check is math.inf else next_check

    async def shutdown(self) -> None:
        for cid in list(self._conns):
            await self._remove(cid)

    async def _remove(self, cid: str) -> None:
        conn = self._conns.get(cid)
        if conn is not None:
            # Best effort: closing the connection clears the activity anyway.
            with contextlib.suppress(Exception):
                await asyncio.wait_for(conn.set_activity(None), timeout=2)
        self._drop(cid)

    def _drop(self, cid: str) -> None:
        conn = self._conns.pop(cid, None)
        if conn is not None:
            conn.close()
        self._applied.pop(cid, None)

    def _set_status(self, status: Health) -> None:
        if status != self.status:
            self.status = status
            self.on_status(status)

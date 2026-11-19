"""Music module: shows what MPRIS music players are playing as "Listening"."""

import asyncio
import logging
import time
from typing import Any

from dbus_fast import Message, MessageType, Variant
from dbus_fast.aio import MessageBus

from rpc_buddy import RPC_BUDDY_CLIENT_ID
from rpc_buddy.activity import Activity, ActivityType, Health, HealthState, StatusDisplay
from rpc_buddy.module import Module, Setting
from rpc_buddy.modules.mpris.players import BUS_PREFIX, source_name, track_from_metadata
from rpc_buddy.modules.mpris.selector import NowPlaying, PlayerSnapshot, Selector

log = logging.getLogger(__name__)

POLL_INTERVAL = 2.0
CALL_TIMEOUT = 1.0
MPRIS_PATH = "/org/mpris/MediaPlayer2"
ROOT_IFACE = "org.mpris.MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"


def _unwrap(value: Any) -> Any:
    if isinstance(value, Variant):
        return _unwrap(value.value)
    if isinstance(value, dict):
        return {k: _unwrap(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    return value


def _fit(text: str | None, limit: int = 128) -> str | None:
    """Discord requires 2..128 characters for text fields."""
    if not text:
        return None
    text = text if len(text) <= limit else text[: limit - 1] + "…"
    return text if len(text) >= 2 else text + "⠀"


class MprisModule(Module):
    id = "mpris"
    name = "Music"
    settings = (
        Setting(
            "status_display",
            "Status line shows",
            "choice",
            choices=(("state", "Artist"), ("name", "Player / service"), ("details", "Track")),
            help="What Discord shows next to your name in member lists.",
        ),
        Setting(
            "pause_timeout",
            "Keep paused tracks for",
            "int",
            minimum=0,
            maximum=3600,
            suffix=" s",
        ),
        Setting(
            "client_id",
            "Discord application ID",
            "text",
            placeholder="Default: RPC Buddy",
            help="Optional: the ID of your own app from the Discord Developer Portal.",
        ),
    )

    def __init__(self, ctx):
        super().__init__(ctx)
        self._bus: MessageBus | None = None
        self._identities: dict[str, str | None] = {}
        self._selector = Selector(float(ctx.settings.get("pause_timeout", 30)))
        self._published: Activity | None | object = object()

    async def run(self) -> None:
        self._bus = await MessageBus().connect()
        try:
            self.ctx.set_health(Health(HealthState.OK, "Nothing playing"))
            while True:
                snapshots = await self._snapshots()
                now_playing = self._selector.update(time.time(), snapshots)
                self._publish(now_playing)
                await asyncio.sleep(POLL_INTERVAL)
        finally:
            self._bus.disconnect()

    async def _call(self, dest: str, path: str, iface: str, member: str, sig="", body=()):
        msg = Message(
            destination=dest,
            path=path,
            interface=iface,
            member=member,
            signature=sig,
            body=list(body),
        )
        reply = await asyncio.wait_for(self._bus.call(msg), CALL_TIMEOUT)
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"{reply.error_name}: {reply.body}")
        return reply.body

    async def _snapshots(self) -> list[PlayerSnapshot]:
        (names,) = await self._call(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames"
        )
        players = [n for n in names if n.startswith(BUS_PREFIX)]
        for gone in set(self._identities) - set(players):
            del self._identities[gone]

        snapshots = []
        for bus_name in players:
            try:
                snap = await self._snapshot(bus_name)
            except Exception as e:  # noqa: BLE001 - one broken player must not stop the rest
                log.debug("Skipping %s: %s", bus_name, e)
                continue
            if snap is not None:
                snapshots.append(snap)
        return snapshots

    async def _snapshot(self, bus_name: str) -> PlayerSnapshot | None:
        if bus_name not in self._identities:
            (root,) = await self._call(
                bus_name, MPRIS_PATH, "org.freedesktop.DBus.Properties", "GetAll", "s", [ROOT_IFACE]
            )
            self._identities[bus_name] = _unwrap(root.get("Identity"))
        (props,) = await self._call(
            bus_name, MPRIS_PATH, "org.freedesktop.DBus.Properties", "GetAll", "s", [PLAYER_IFACE]
        )
        props = _unwrap(props)
        status = props.get("PlaybackStatus")
        if status not in ("Playing", "Paused"):
            return None
        track = track_from_metadata(props.get("Metadata") or {})
        if track is None:
            return None
        source = source_name(bus_name, self._identities[bus_name], track.url)
        if source is None:
            return None
        position = props.get("Position")
        return PlayerSnapshot(
            bus_name=bus_name,
            source=source,
            track=track,
            playing=status == "Playing",
            position=position / 1_000_000 if isinstance(position, int) else None,
        )

    def _publish(self, now: NowPlaying | None) -> None:
        if now is None:
            activity, summary = None, ""
        else:
            t = now.track
            art = t.art_url if t.art_url and t.art_url.startswith("https://") else None
            activity = Activity(
                client_id=str(self.ctx.settings.get("client_id") or RPC_BUDDY_CLIENT_ID),
                type=ActivityType.LISTENING,
                name=now.source,
                details=_fit(t.title),
                state=_fit(t.artist),
                large_image=art,
                large_text=_fit(t.album),
                start=now.start,
                end=now.end,
                status_display=self._status_display(),
            )
            summary = f"Listening to {t.title}" + (f" by {t.artist}" if t.artist else "")
            if now.paused:
                summary += " (paused)"
        if activity == self._published:
            return
        self._published = activity
        source = now.source if now else None
        self.ctx.publish(
            activity,
            summary,
            hide_key=f"mpris:{source}" if source else None,
            hide_label=f"{source} (music)" if source else None,
        )
        message = f"{now.source}: {summary}" if now else "Nothing playing"
        self.ctx.set_health(Health(HealthState.OK, message))

    def _status_display(self) -> StatusDisplay:
        value = str(self.ctx.settings.get("status_display", "state")).upper()
        return StatusDisplay[value] if value in StatusDisplay.__members__ else StatusDisplay.STATE

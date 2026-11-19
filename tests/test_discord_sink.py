import asyncio

from pypresence import exceptions as pp_exc

from rpc_buddy.activity import Activity, HealthState
from rpc_buddy.discord import DiscordSink


class FakeConnection:
    instances: list["FakeConnection"] = []
    fail_open = False

    def __init__(self, client_id):
        self.client_id = client_id
        self.sent: list = []
        self.alive = True
        self.closed = False
        FakeConnection.instances.append(self)

    async def open(self):
        if FakeConnection.fail_open:
            raise pp_exc.DiscordNotFound

    async def set_activity(self, activity):
        self.sent.append(activity)

    def is_alive(self):
        return self.alive

    def close(self):
        self.closed = True


def make_sink():
    FakeConnection.instances = []
    FakeConnection.fail_open = False
    sink = DiscordSink(connection_factory=FakeConnection, probe=lambda: True)
    sink.MIN_INTERVAL = 0
    return sink


GAME = Activity(client_id="game", large_text="Game")
MUSIC = Activity(client_id="music", details="Song")


def test_one_connection_per_client_id():
    sink = make_sink()
    sink.set_desired({"game": GAME, "music": MUSIC})
    asyncio.run(sink.reconcile())
    assert {c.client_id for c in FakeConnection.instances} == {"game", "music"}
    assert sink.status.state is HealthState.OK


def test_unchanged_activity_is_not_resent():
    sink = make_sink()
    sink.set_desired({"game": GAME})

    async def go():
        await sink.reconcile()
        await sink.reconcile()

    asyncio.run(go())
    assert FakeConnection.instances[0].sent == [GAME]


def test_removed_activity_is_cleared_and_closed():
    sink = make_sink()

    async def go():
        sink.set_desired({"game": GAME})
        await sink.reconcile()
        sink.set_desired({})
        await sink.reconcile()

    asyncio.run(go())
    conn = FakeConnection.instances[0]
    assert conn.sent == [GAME, None]
    assert conn.closed


def test_reconnects_after_connection_lost():
    sink = make_sink()

    async def go():
        sink.set_desired({"game": GAME})
        await sink.reconcile()
        FakeConnection.instances[0].alive = False
        await sink.reconcile()

    asyncio.run(go())
    assert len(FakeConnection.instances) == 2
    assert FakeConnection.instances[1].sent == [GAME]


def test_discord_not_running_reports_and_retries():
    sink = make_sink()
    FakeConnection.fail_open = True
    sink.set_desired({"game": GAME})
    delay = asyncio.run(sink.reconcile())
    assert sink.status.state is HealthState.NEEDS_SETUP
    assert delay == sink.RETRY_DELAY


def test_rate_limit_delays_update():
    sink = make_sink()
    sink.MIN_INTERVAL = 100

    async def go():
        sink.set_desired({"game": GAME})
        await sink.reconcile()
        sink.set_desired({"game": Activity(client_id="game", large_text="Other")})
        return await sink.reconcile()

    delay = asyncio.run(go())
    assert FakeConnection.instances[0].sent == [GAME]
    assert 0 < delay <= 100

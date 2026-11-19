import asyncio

from rpc_buddy.activity import Activity, Health, HealthState
from rpc_buddy.config import Config
from rpc_buddy.engine import Engine
from rpc_buddy.module import Module


class RecordingSink:
    def __init__(self):
        self.desired = None
        self.status = Health(HealthState.OK, "fake")
        self.on_status = None

    def set_desired(self, desired):
        self.desired = desired

    async def run(self):
        await asyncio.Event().wait()

    async def shutdown(self):
        pass


class DummyModule(Module):
    id = "dummy"
    name = "Dummy"

    async def run(self):
        await asyncio.Event().wait()


def make_engine(tmp_path):
    sink = RecordingSink()
    engine = Engine(
        Config(tmp_path / "config.toml"), modules=[DummyModule], sink=sink, detectable=object()
    )
    return engine, sink


def test_publish_reaches_sink(tmp_path):
    engine, sink = make_engine(tmp_path)
    activity = Activity(client_id="game")
    engine.publish("dummy", activity, "Playing Game")
    assert sink.desired == {"game": activity}
    assert engine.state().shown[0].summary == "Playing Game"


def test_pause_clears_everything_and_is_saved(tmp_path):
    engine, sink = make_engine(tmp_path)
    engine.publish("dummy", Activity(client_id="game"), "x")
    engine._set_paused(True)
    assert sink.desired == {}
    assert engine.state().shown == []
    assert Config.load(tmp_path / "config.toml").paused is True


def test_same_client_id_newest_wins(tmp_path):
    engine, sink = make_engine(tmp_path)
    engine._module_classes["other"] = DummyModule
    engine.publish("dummy", Activity(client_id="app", details="old"), "")
    engine.publish("other", Activity(client_id="app", details="new"), "")
    assert sink.desired["app"].details == "new"


def test_disable_module_removes_its_activity(tmp_path):
    engine, sink = make_engine(tmp_path)

    async def go():
        engine._loop = asyncio.get_running_loop()
        engine._start_module("dummy")
        engine.publish("dummy", Activity(client_id="game"), "x")
        await engine._stop_module("dummy")

    asyncio.run(go())
    assert sink.desired == {}
    assert engine.state().modules[0].health.state is HealthState.DISABLED

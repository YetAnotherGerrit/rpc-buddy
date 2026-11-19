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


def test_hidden_item_is_not_published(tmp_path):
    from rpc_buddy.engine import Item

    engine, sink = make_engine(tmp_path)
    item = Item("steam:1000001", "Example Quest")
    engine.publish("dummy", Activity(client_id="game"), "Playing Example Quest", item)
    assert sink.desired == {"game": Activity(client_id="game")}
    assert engine.state().recent == (item,)

    engine._set_hidden(item, True)
    assert sink.desired == {}
    state = engine.state()
    assert state.shown == []
    assert state.modules[0].hidden
    assert state.hidden == (item,)
    assert state.recent == ()  # hidden items are not offered again
    assert Config.load(tmp_path / "config.toml").hidden_keys == {"steam:1000001"}

    engine._set_hidden(item, False)
    assert sink.desired == {"game": Activity(client_id="game")}


def test_recent_is_newest_first_and_bounded(tmp_path):
    from rpc_buddy.engine import MAX_RECENT, Item

    engine, _ = make_engine(tmp_path)
    for i in range(MAX_RECENT + 5):
        engine.publish("dummy", Activity(client_id="x"), "", Item(f"steam:{i}", f"Game {i}"))
    recent = engine.state().recent
    assert len(recent) == MAX_RECENT
    assert recent[0].key == f"steam:{MAX_RECENT + 4}"


def test_module_setting_is_saved(tmp_path):
    engine, _ = make_engine(tmp_path)
    engine._set_module_setting("dummy", "volume", 7)
    assert engine.state().modules[0].values["volume"] == 7
    assert Config.load(tmp_path / "config.toml").module_settings("dummy")["volume"] == 7

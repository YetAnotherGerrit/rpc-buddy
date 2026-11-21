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
    assert engine.state().modules[0].item == item

    engine._set_hidden(item, True)
    assert sink.desired == {}
    state = engine.state()
    assert state.shown == []
    assert state.modules[0].hidden
    assert state.hidden == (item,)
    assert Config.load(tmp_path / "config.toml").hidden_keys == {"steam:1000001"}

    engine._set_hidden(item, False)
    assert sink.desired == {"game": Activity(client_id="game")}


def test_module_setting_is_saved(tmp_path):
    engine, _ = make_engine(tmp_path)
    engine._set_module_settings("dummy", {"volume": 7})
    assert engine.state().modules[0].values["volume"] == 7
    assert Config.load(tmp_path / "config.toml").module_settings("dummy")["volume"] == 7


def test_setup_done_enables_autostart_and_reports_errors(tmp_path):
    engine, _ = make_engine(tmp_path)
    calls = []

    async def fake_autostart(enabled):
        calls.append(enabled)
        if len(calls) == 2:
            raise RuntimeError("denied")

    engine._apply_autostart = fake_autostart

    async def go():
        engine._set_setup_done()
        await asyncio.sleep(0)
        engine._set_autostart(False)
        await asyncio.sleep(0)

    asyncio.run(go())
    assert calls == [True, False]
    state = engine.state()
    assert state.autostart is False
    assert state.autostart_error == "denied"
    assert Config.load(tmp_path / "config.toml").autostart is False


def test_overlapping_restarts_leave_one_running_module(tmp_path):
    engine, _ = make_engine(tmp_path)

    async def go():
        engine._loop = asyncio.get_running_loop()
        engine._restart_lock = asyncio.Lock()
        engine._start_module("dummy")
        engine._set_module_settings("dummy", {"a": 1})
        engine._set_module_settings("dummy", {"b": 2})
        for _ in range(10):
            await asyncio.sleep(0)
        tasks = [t for t in asyncio.all_tasks() if t.get_name() == "module-dummy"]
        assert len(tasks) == 1
        assert engine.state().modules[0].health.state is HealthState.STARTING
        await engine._stop_module("dummy")

    asyncio.run(go())


def test_close_hint_is_shown_once_and_saved(tmp_path):
    engine, _ = make_engine(tmp_path)
    assert engine.state().close_hint_shown is False
    engine._set_close_hint_shown()
    assert engine.state().close_hint_shown is True
    assert Config.load(tmp_path / "config.toml").close_hint_shown is True


def test_withheld_activity_stays_off_discord_but_visible(tmp_path):
    engine, sink = make_engine(tmp_path)
    engine.publish("dummy", Activity(client_id="game"), "Playing X", withheld="reason")
    assert sink.desired == {}
    state = engine.state()
    m = state.modules[0]
    assert m.activity is not None and not m.on_discord
    assert state.off_discord_reason(m) == "reason"
    assert state.shown == []


def test_off_discord_reason_order(tmp_path):
    from rpc_buddy.engine import Item

    engine, sink = make_engine(tmp_path)
    item = Item("steam:1000001", "Example Quest")
    engine.publish("dummy", Activity(client_id="game"), "x", item, withheld="module reason")
    reason = lambda: engine.state().off_discord_reason(engine.state().modules[0])  # noqa: E731
    assert reason() == "module reason"
    engine._set_paused(True)
    assert reason() == "presence paused"
    engine._set_hidden(item, True)
    assert reason() == "hidden by you"
    # Hidden stays hidden after resuming; nothing reaches Discord meanwhile.
    engine._set_paused(False)
    assert reason() == "hidden by you"
    assert sink.desired == {}

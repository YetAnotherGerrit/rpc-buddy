"""The headless core: runs modules, applies rules, feeds Discord.

The engine runs its own asyncio loop (in a worker thread when used with the
GUI). The public ``set_*`` methods and ``stop`` are thread-safe; state
changes are reported through ``on_state``, which is called from the
engine's thread.
"""

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rpc_buddy.activity import Activity, Health, HealthState
from rpc_buddy.autostart import set_autostart
from rpc_buddy.config import Config
from rpc_buddy.detectable import DetectableCache
from rpc_buddy.discord import DiscordSink
from rpc_buddy.module import Module, ModuleContext, Setting
from rpc_buddy.modules import MODULES
from rpc_buddy.paths import cache_dir

log = logging.getLogger(__name__)

MODULE_RESTART_DELAY = 30.0
MAX_RECENT = 20


@dataclass(frozen=True)
class Item:
    """Something that can be hidden, e.g. a game or a music source."""

    key: str  # e.g. "steam:1000001", "mpris:Deezer"
    label: str  # shown in the UI


@dataclass(frozen=True)
class Publication:
    timestamp: float
    activity: Activity | None
    summary: str
    item: Item | None


@dataclass(frozen=True)
class ModuleStatus:
    id: str
    name: str
    enabled: bool
    health: Health
    activity: Activity | None
    summary: str
    hidden: bool
    settings: tuple[Setting, ...]
    values: dict[str, Any]


@dataclass(frozen=True)
class EngineState:
    discord: Health
    paused: bool
    modules: tuple[ModuleStatus, ...]
    hidden: tuple[Item, ...]
    recent: tuple[Item, ...]  # seen this session, newest first, not hidden
    autostart: bool = False  # the user wants autostart
    autostart_error: str = ""
    setup_done: bool = True

    @property
    def shown(self) -> list[ModuleStatus]:
        """Modules whose activity is currently published."""
        if self.paused:
            return []
        return [m for m in self.modules if m.activity is not None and not m.hidden]


class Engine:
    def __init__(
        self,
        config: Config,
        on_state: Callable[[EngineState], None] | None = None,
        modules: list[type[Module]] | None = None,
        sink: DiscordSink | None = None,
        detectable: DetectableCache | None = None,
    ):
        self.config = config
        self.on_state = on_state or (lambda s: None)
        self.detectable = detectable or DetectableCache(cache_dir())
        self.sink = sink or DiscordSink()
        self.sink.on_status = lambda _h: self._emit()
        self._module_classes = {cls.id: cls for cls in (modules or MODULES)}
        self._published: dict[str, Publication] = {}
        self._recent: dict[str, Item] = {}  # insertion order = oldest first
        self._health: dict[str, Health] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stopping: asyncio.Event | None = None
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._autostart_error = ""
        self._apply_autostart = set_autostart  # replaceable in tests

    # --- lifecycle --------------------------------------------------------

    def start_in_thread(self) -> None:
        self._thread = threading.Thread(target=self.run_forever, name="rpc-buddy-core", daemon=True)
        self._thread.start()
        self._ready.wait()

    def run_forever(self) -> None:
        asyncio.run(self._main())

    def stop(self, timeout: float = 5.0) -> None:
        if self._loop is not None and self._stopping is not None:
            self._loop.call_soon_threadsafe(self._stopping.set)
        if self._thread is not None:
            self._thread.join(timeout)

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stopping = asyncio.Event()
        self._restart_lock = asyncio.Lock()
        sink_task = asyncio.create_task(self.sink.run(), name="discord-sink")
        for module_id in self._module_classes:
            if self.config.module_enabled(module_id):
                self._start_module(module_id)
            else:
                self._health[module_id] = Health(HealthState.DISABLED)
        self._ready.set()
        self._emit()
        try:
            await self._stopping.wait()
        finally:
            for module_id in list(self._tasks):
                await self._stop_module(module_id)
            await self.sink.shutdown()
            sink_task.cancel()
            await asyncio.gather(sink_task, return_exceptions=True)
            log.info("Engine stopped")

    # --- thread-safe API --------------------------------------------------

    def set_paused(self, paused: bool) -> None:
        self._call(self._set_paused, paused)

    def set_module_enabled(self, module_id: str, enabled: bool) -> None:
        self._call(self._set_module_enabled, module_id, enabled)

    def set_module_setting(self, module_id: str, key: str, value: Any) -> None:
        self._call(self._set_module_settings, module_id, {key: value})

    def set_module_settings(self, module_id: str, values: dict[str, Any]) -> None:
        """Change several settings at once (one module restart)."""
        self._call(self._set_module_settings, module_id, dict(values))

    def set_hidden(self, item: Item, hidden: bool) -> None:
        self._call(self._set_hidden, item, hidden)

    def set_setup_done(self) -> None:
        self._call(self._set_setup_done)

    def set_autostart(self, enabled: bool) -> None:
        self._call(self._set_autostart, enabled)

    def _call(self, fn, *args) -> None:
        if self._loop is None:
            raise RuntimeError("Engine is not running")
        self._loop.call_soon_threadsafe(fn, *args)

    # --- called by modules (engine thread) ---------------------------------

    def publish(
        self, module_id: str, activity: Activity | None, summary: str, item: Item | None = None
    ) -> None:
        self._published[module_id] = Publication(time.monotonic(), activity, summary, item)
        if activity is not None and item is not None:
            self._recent.pop(item.key, None)
            self._recent[item.key] = item
            while len(self._recent) > MAX_RECENT:
                self._recent.pop(next(iter(self._recent)))
        self._recompute()

    def set_health(self, module_id: str, health: Health) -> None:
        if self._health.get(module_id) != health:
            self._health[module_id] = health
            self._emit()

    # --- internals --------------------------------------------------------

    def _set_paused(self, paused: bool) -> None:
        self.config.paused = paused
        self._save_config()
        self._recompute()

    def _set_module_enabled(self, module_id: str, enabled: bool) -> None:
        if module_id not in self._module_classes:
            return
        self.config.set_module_enabled(module_id, enabled)
        self._save_config()
        if enabled and module_id not in self._tasks:
            self._start_module(module_id)
            self._emit()
        elif not enabled and module_id in self._tasks:
            asyncio.ensure_future(self._stop_module(module_id))

    def _set_module_settings(self, module_id: str, values: dict[str, Any]) -> None:
        settings = self.config.module_settings(module_id)
        if all(settings.get(k) == v for k, v in values.items()):
            return
        settings.update(values)
        self._save_config()
        if module_id in self._tasks:
            asyncio.ensure_future(self._restart_module(module_id))
        else:
            self._emit()

    async def _restart_module(self, module_id: str) -> None:
        async with self._restart_lock:  # restarts must not overlap
            await self._restart_module_locked(module_id)

    async def _restart_module_locked(self, module_id: str) -> None:
        await self._stop_module(module_id)
        if self.config.module_enabled(module_id):
            self._start_module(module_id)
            self._emit()

    def _set_hidden(self, item: Item, hidden: bool) -> None:
        self.config.set_hidden(item.key, item.label, hidden)
        self._save_config()
        self._recompute()

    def _set_setup_done(self) -> None:
        if not self.config.setup_done:
            self.config.setup_done = True
            self._save_config()
            if self.config.autostart:
                asyncio.ensure_future(self._autostart(True))

    def _set_autostart(self, enabled: bool) -> None:
        self.config.autostart = enabled
        self._save_config()
        asyncio.ensure_future(self._autostart(enabled))

    async def _autostart(self, enabled: bool) -> None:
        try:
            await self._apply_autostart(enabled)
            self._autostart_error = ""
        except Exception as e:
            log.warning("Could not change autostart: %s", e)
            self._autostart_error = str(e) or type(e).__name__
        self._emit()

    def _save_config(self) -> None:
        try:
            self.config.save()
        except OSError as e:
            log.error("Could not save config: %s", e)

    def _start_module(self, module_id: str) -> None:
        if module_id in self._tasks:  # never run a module twice
            return
        cls = self._module_classes[module_id]
        ctx = ModuleContext(self, module_id, self.config.module_settings(module_id))
        self._health[module_id] = Health(HealthState.STARTING)
        self._tasks[module_id] = asyncio.create_task(
            self._supervise(cls(ctx)), name=f"module-{module_id}"
        )

    async def _supervise(self, module: Module) -> None:
        while True:
            try:
                await module.run()
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("Module %s crashed", module.id)
                self.publish(module.id, None, "")
                self.set_health(
                    module.id,
                    Health(HealthState.ERROR, f"Crashed: {e}", "Restarting in 30 seconds."),
                )
                await asyncio.sleep(MODULE_RESTART_DELAY)

    async def _stop_module(self, module_id: str) -> None:
        task = self._tasks.pop(module_id, None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._published.pop(module_id, None)
        self._health[module_id] = Health(HealthState.DISABLED)
        self._recompute()

    def _is_hidden(self, pub: Publication) -> bool:
        return pub.item is not None and pub.item.key in self.config.hidden_keys

    def _recompute(self) -> None:
        desired: dict[str, Activity] = {}
        if not self.config.paused:
            # Several sources may share a Discord application: newest wins.
            newest: dict[str, float] = {}
            for pub in self._published.values():
                activity = pub.activity
                if activity is None or self._is_hidden(pub):
                    continue
                if pub.timestamp >= newest.get(activity.client_id, -1.0):
                    newest[activity.client_id] = pub.timestamp
                    desired[activity.client_id] = activity
        self.sink.set_desired(desired)
        self._emit()

    def state(self) -> EngineState:
        modules = []
        empty = Publication(0.0, None, "", None)
        for module_id, cls in self._module_classes.items():
            pub = self._published.get(module_id, empty)
            modules.append(
                ModuleStatus(
                    id=module_id,
                    name=cls.name,
                    enabled=self.config.module_enabled(module_id),
                    health=self._health.get(module_id, Health(HealthState.STARTING)),
                    activity=pub.activity,
                    summary=pub.summary,
                    hidden=self._is_hidden(pub),
                    settings=tuple(cls.settings),
                    values=dict(self.config.module_settings(module_id)),
                )
            )
        hidden = tuple(Item(h["key"], h["label"]) for h in self.config.hidden)
        hidden_keys = self.config.hidden_keys
        recent = tuple(i for i in reversed(self._recent.values()) if i.key not in hidden_keys)
        return EngineState(
            discord=self.sink.status,
            paused=self.config.paused,
            modules=tuple(modules),
            hidden=hidden,
            recent=recent,
            autostart=self.config.autostart,
            autostart_error=self._autostart_error,
            setup_done=self.config.setup_done,
        )

    def _emit(self) -> None:
        try:
            self.on_state(self.state())
        except Exception:
            log.exception("State listener failed")

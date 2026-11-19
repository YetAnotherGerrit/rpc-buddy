"""Base class for activity sources ("modules").

To add a module: subclass :class:`Module`, implement :meth:`Module.run`, and
add the class to ``rpc_buddy.modules.MODULES``.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from rpc_buddy.activity import Activity, Health

if TYPE_CHECKING:
    from rpc_buddy.detectable import DetectableCache
    from rpc_buddy.engine import Engine


class ModuleContext:
    """What a module may use to talk to the rest of the app."""

    def __init__(self, engine: "Engine", module_id: str, settings: dict[str, Any]):
        self._engine = engine
        self._module_id = module_id
        self.settings = settings

    @property
    def detectable(self) -> "DetectableCache":
        return self._engine.detectable

    def publish(self, activity: Activity | None, summary: str = "") -> None:
        """Show ``activity`` (or nothing, if None). ``summary`` is shown in the UI."""
        self._engine.publish(self._module_id, activity, summary)

    def set_health(self, health: Health) -> None:
        self._engine.set_health(self._module_id, health)


class Module(ABC):
    id: ClassVar[str]
    name: ClassVar[str]

    def __init__(self, ctx: ModuleContext):
        self.ctx = ctx

    @abstractmethod
    async def run(self) -> None:
        """Run until cancelled. Disabling the module cancels this task."""

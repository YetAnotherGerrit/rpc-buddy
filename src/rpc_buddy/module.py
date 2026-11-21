"""Base class for activity sources ("modules").

To add a module: subclass :class:`Module`, implement :meth:`Module.run`,
declare its ``settings`` (the main window builds a form from them), add its
defaults to ``rpc_buddy.config.DEFAULTS`` and the class to
``rpc_buddy.modules.MODULES``.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from rpc_buddy.activity import Activity, Health

if TYPE_CHECKING:
    from rpc_buddy.detectable import DetectableCache
    from rpc_buddy.engine import Engine


@dataclass(frozen=True)
class Setting:
    """A user-editable module setting, stored in the module's config section."""

    key: str
    label: str
    kind: Literal["text", "choice", "int", "bool", "folder"]
    help: str = ""
    choices: tuple[tuple[str, str], ...] = ()  # (value, label) for kind="choice"
    minimum: int = 0
    maximum: int = 3600
    suffix: str = ""  # e.g. " s" for kind="int"
    placeholder: str = ""  # for kind="text"


class ModuleContext:
    """What a module may use to talk to the rest of the app."""

    def __init__(self, engine: "Engine", module_id: str, settings: dict[str, Any]):
        self._engine = engine
        self._module_id = module_id
        self.settings = settings

    @property
    def detectable(self) -> "DetectableCache":
        return self._engine.detectable

    def publish(
        self,
        activity: Activity | None,
        summary: str = "",
        hide_key: str | None = None,
        hide_label: str | None = None,
        withheld: str = "",
    ) -> None:
        """Show ``activity`` (or nothing, if None).

        ``summary`` is shown in the UI. ``hide_key`` (e.g. ``"steam:<appid>"``)
        lets the user hide this kind of activity; ``hide_label`` names it.
        ``withheld`` (a short reason, e.g. "you're invisible on Steam") keeps the
        activity off Discord but still shows it, greyed out, in the main window.
        """
        from rpc_buddy.engine import Item

        item = Item(hide_key, hide_label or hide_key) if hide_key else None
        self._engine.publish(self._module_id, activity, summary, item, withheld)

    def set_health(self, health: Health) -> None:
        self._engine.set_health(self._module_id, health)


class Module(ABC):
    id: ClassVar[str]
    name: ClassVar[str]
    settings: ClassVar[tuple[Setting, ...]] = ()

    def __init__(self, ctx: ModuleContext):
        self.ctx = ctx

    @abstractmethod
    async def run(self) -> None:
        """Run until cancelled. Disabling the module cancels this task."""

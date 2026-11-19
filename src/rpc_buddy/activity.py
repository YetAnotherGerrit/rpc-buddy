"""Internal activity model, independent of the Discord library in use."""

from dataclasses import dataclass
from enum import Enum, IntEnum


class ActivityType(IntEnum):
    """Discord activity types that can be set over IPC."""

    PLAYING = 0
    LISTENING = 2
    WATCHING = 3


class StatusDisplay(IntEnum):
    """Which field Discord shows in the member-list status line."""

    NAME = 0
    STATE = 1
    DETAILS = 2


@dataclass(frozen=True)
class Activity:
    """One Rich Presence activity.

    ``client_id`` is the Discord application the activity is published as —
    e.g. a game's official Discord application, or the RPC Buddy app.
    Timestamps are Unix seconds.
    """

    client_id: str
    type: ActivityType = ActivityType.PLAYING
    name: str | None = None
    details: str | None = None
    state: str | None = None
    large_image: str | None = None
    large_text: str | None = None
    small_image: str | None = None
    small_text: str | None = None
    start: int | None = None
    end: int | None = None
    status_display: StatusDisplay | None = None


class HealthState(Enum):
    OK = "ok"
    STARTING = "starting"
    NEEDS_SETUP = "needs_setup"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass(frozen=True)
class Health:
    """Status of a component, shown in the UI.

    ``hint`` tells the user what to do when the state is not OK.
    """

    state: HealthState
    message: str = ""
    hint: str = ""

    @property
    def ok(self) -> bool:
        return self.state is HealthState.OK

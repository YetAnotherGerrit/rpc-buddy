"""User configuration, stored as a single TOML file."""

import copy
import logging
import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from rpc_buddy.paths import config_dir

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "general": {
        "paused": False,
    },
    "modules": {
        "steam": {"enabled": True},
        "mpris": {
            "enabled": True,
            # Discord application id; replace with your own app to use its name/assets.
            "client_id": "",
            # Member-list status line: "state" (artist), "name" (e.g. Deezer), "details" (title)
            "status_display": "state",
            # Seconds a paused track stays visible
            "pause_timeout": 30,
        },
    },
}


def _merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _diff(data: dict, defaults: dict) -> dict:
    """Only the values that differ from the defaults (so changed defaults apply)."""
    result = {}
    for key, value in data.items():
        default = defaults.get(key)
        if isinstance(value, dict) and isinstance(default, dict):
            sub = _diff(value, default)
            if sub:
                result[key] = sub
        elif key not in defaults or value != default:
            result[key] = value
    return result


class Config:
    def __init__(self, path: Path, data: dict[str, Any] | None = None):
        self.path = path
        self.data = _merge(DEFAULTS, data or {})

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or config_dir() / "config.toml"
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except FileNotFoundError:
            data = {}
        except (OSError, tomllib.TOMLDecodeError) as e:
            log.error("Could not read %s, using defaults: %s", path, e)
            data = {}
        return cls(path, data)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".toml.tmp")
        with tmp.open("wb") as f:
            tomli_w.dump(_diff(self.data, DEFAULTS), f)
        os.replace(tmp, self.path)

    @property
    def paused(self) -> bool:
        return bool(self.data["general"].get("paused", False))

    @paused.setter
    def paused(self, value: bool) -> None:
        self.data["general"]["paused"] = value

    def module_settings(self, module_id: str) -> dict[str, Any]:
        return self.data["modules"].setdefault(module_id, {"enabled": True})

    def module_enabled(self, module_id: str) -> bool:
        return bool(self.module_settings(module_id).get("enabled", True))

    def set_module_enabled(self, module_id: str, enabled: bool) -> None:
        self.module_settings(module_id)["enabled"] = enabled

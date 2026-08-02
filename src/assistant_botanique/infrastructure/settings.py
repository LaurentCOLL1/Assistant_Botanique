"""Réglages utilisateur JSON, écrits de façon atomique."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from assistant_botanique.paths import SETTINGS_FILE

DEFAULT_SETTINGS = {
    "theme": "light",
    "geometry": "1200x800",
    "ui_mode": "advanced",
    "ingredient_stock": {},
    "notifications": {
        "enabled": True,
        "time": "09:00",
        "times": ["09:00"],
        "quiet_start": "22:00",
        "quiet_end": "07:00",
        "group_by_location": True,
        "max_items": 8,
    },
    "automatic_backups": {
        "enabled": True,
        "cadence": "daily",
        "retention": 14,
        "last_run": "",
        "last_path": "",
        "last_error": "",
    },
    "onboarding": {
        "completed": False,
        "dismissed": False,
    },
    "weather": {
        "enabled": False,
        "location_name": "",
        "latitude": None,
        "longitude": None,
        "timezone": "auto",
    },
    "companion": {
        "lan": False,
        "port": 8765,
        "token": "",
        "pwa_enabled": True,
    },
    "accessibility": {
        "text_scale": 1.0,
        "high_contrast": False,
        "reduce_motion": False,
        "focus_highlight": True,
    },
    "sync": {
        "folder": "",
    },
    "update_checks": True,
}


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def _merge(defaults: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(defaults))
    for key, value in raw.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


class SettingsRepository:
    def __init__(self, path: Path = SETTINGS_FILE):
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return json.loads(json.dumps(DEFAULT_SETTINGS))
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return json.loads(json.dumps(DEFAULT_SETTINGS))
        return _merge(DEFAULT_SETTINGS, raw) if isinstance(raw, dict) else json.loads(json.dumps(DEFAULT_SETTINGS))

    def save(self, settings: dict[str, Any]) -> None:
        atomic_write_json(self.path, settings)

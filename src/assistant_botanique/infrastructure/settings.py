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
    "notifications": {"enabled": True, "time": "09:00"},
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


class SettingsRepository:
    def __init__(self, path: Path = SETTINGS_FILE):
        self.path = path

    def load(self) -> dict[str, Any]:
        settings = json.loads(json.dumps(DEFAULT_SETTINGS))
        if not self.path.exists():
            return settings
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return settings
        if isinstance(raw, dict):
            settings.update(raw)
            if isinstance(raw.get("notifications"), dict):
                settings["notifications"].update(raw["notifications"])
        return settings

    def save(self, settings: dict[str, Any]) -> None:
        atomic_write_json(self.path, settings)

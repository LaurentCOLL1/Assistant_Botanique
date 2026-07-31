"""Chemins de ressources et de données utilisateur, compatibles avec PyInstaller."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "AssistantBotanique"


def _resource_dir() -> Path:
    override = os.getenv("ASSISTANT_BOTANIQUE_RESOURCE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen).resolve()
    candidates = [
        Path.cwd(),
        Path(__file__).resolve().parents[2],
        Path(__file__).resolve().parents[3],
    ]
    for candidate in candidates:
        if (candidate / "familles_plantes").exists():
            return candidate
    return candidates[0]


def _data_dir() -> Path:
    override = os.getenv("ASSISTANT_BOTANIQUE_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


def resource_dir() -> Path:
    return _resource_dir()


def user_data_dir() -> Path:
    return _data_dir()


RESOURCE_DIR = resource_dir()
DATA_DIR = user_data_dir()
USER_DATA_DIR = DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)
FAMILIES_DIR = RESOURCE_DIR / "familles_plantes"
SCHEMAS_DIR = RESOURCE_DIR / "schemas"
LEGACY_COLLECTION_FILE = RESOURCE_DIR / "mes_plantes.json"
COLLECTION_FILE = DATA_DIR / "mes_plantes.json"
DATABASE_FILE = DATA_DIR / "assistant_botanique.sqlite3"
SETTINGS_FILE = DATA_DIR / "settings.json"
LOG_FILE = DATA_DIR / "assistant_botanique.log"
PHOTOS_DIR = DATA_DIR / "photos"
OVERRIDES_DIR = DATA_DIR / "catalogue_overrides"
BACKUPS_DIR = DATA_DIR / "backups"
for directory in (PHOTOS_DIR, OVERRIDES_DIR, BACKUPS_DIR):
    directory.mkdir(parents=True, exist_ok=True)

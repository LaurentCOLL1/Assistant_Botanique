"""Chemins de ressources et de données utilisateur de l'application."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "AssistantBotanique"


def resource_dir() -> Path:
    """Retourne le dossier contenant les ressources embarquées."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def user_data_dir() -> Path:
    """Retourne un dossier utilisateur inscriptible, indépendant du dépôt."""
    override = os.environ.get("ASSISTANT_BOTANIQUE_DATA_DIR")
    if override:
        path = Path(override).expanduser().resolve()
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        path = base / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


RESOURCE_DIR = resource_dir()
FAMILIES_DIR = RESOURCE_DIR / "familles_plantes"
SCHEMAS_DIR = RESOURCE_DIR / "schemas"
USER_DATA_DIR = user_data_dir()
COLLECTION_FILE = USER_DATA_DIR / "mes_plantes.json"
SETTINGS_FILE = USER_DATA_DIR / "settings.json"
LOG_FILE = USER_DATA_DIR / "assistant_botanique.log"
LEGACY_COLLECTION_FILE = RESOURCE_DIR / "mes_plantes.json"

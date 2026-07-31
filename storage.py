"""Façade de compatibilité : la collection est désormais persistée dans SQLite."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from app_paths import COLLECTION_FILE, DATABASE_FILE, LEGACY_COLLECTION_FILE
from assistant_botanique.infrastructure.database import Database, normalize_plant
from assistant_botanique.infrastructure.settings import SettingsRepository, atomic_write_json

SCHEMA_VERSION = 3
migrate_item = normalize_plant


class CollectionRepository:
    def __init__(self, path: Path = COLLECTION_FILE, legacy_path: Path = LEGACY_COLLECTION_FILE):
        self.path = Path(path)
        self.legacy_path = Path(legacy_path)
        if self.path.suffix.casefold() in {".sqlite", ".sqlite3", ".db"}:
            database_path = self.path
        elif self.path == COLLECTION_FILE:
            database_path = DATABASE_FILE
        else:
            database_path = self.path.with_suffix(".sqlite3")
        self.database = Database(database_path)

    def migrate_legacy_file(self) -> bool:
        return self.database.import_legacy_if_needed(candidates=(self.path, self.legacy_path))

    def load(self, defaults: Iterable[dict[str, Any]] = ()) -> list[dict[str, Any]]:
        self.database.import_legacy_if_needed(defaults=defaults, candidates=(self.path, self.legacy_path))
        return self.database.load_plants()

    def save(self, plants: list[dict[str, Any]]) -> None:
        self.database.save_plants(plants)

__all__ = ["CollectionRepository", "SCHEMA_VERSION", "SettingsRepository", "atomic_write_json", "migrate_item"]

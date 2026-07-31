"""Persistance fiable de la collection et des réglages."""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from app_paths import COLLECTION_FILE, LEGACY_COLLECTION_FILE, SETTINGS_FILE
from core import ValidationError, format_date_fr, parse_date

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 2


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _backup(path: Path) -> None:
    if not path.exists():
        return
    backup = path.with_suffix(path.suffix + ".backup")
    shutil.copy2(path, backup)


def _new_instance(species_id: str, nickname: str, pot_l: float, watering_date: date) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "species_id": species_id,
        "surnom": nickname,
        "pot_l": pot_l,
        "date_arrosage": format_date_fr(watering_date),
        "historique_soins": [
            {"type": "arrosage", "date": format_date_fr(watering_date), "note": "Import ou création initiale"}
        ],
        "contexte": {
            "emplacement": "interieur",
            "exposition": "non_renseignee",
            "matiere_pot": "non_renseignee",
            "substrat": "non_renseigne",
        },
    }


def migrate_item(item: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(item)
    migrated["id"] = str(migrated.get("id") or uuid4())
    migrated["species_id"] = str(migrated.get("species_id") or migrated.get("nom_sci") or "").strip()
    migrated["surnom"] = str(migrated.get("surnom") or "Plante sans nom").strip()
    raw_pot = migrated.get("pot_l", migrated.get("pot", 1.0))
    try:
        migrated["pot_l"] = float(raw_pot)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Volume de pot invalide pour {migrated['surnom']!r}: {raw_pot!r}") from exc
    if migrated["pot_l"] <= 0:
        raise ValidationError(f"Le volume du pot doit être positif pour {migrated['surnom']!r}.")
    watering = parse_date(migrated.get("date_arrosage") or date.today())
    migrated["date_arrosage"] = format_date_fr(watering)
    history = migrated.get("historique_soins")
    if not isinstance(history, list):
        history = []
    if not history:
        history.append({"type": "arrosage", "date": format_date_fr(watering), "note": "Historique migré"})
    migrated["historique_soins"] = history
    context = migrated.get("contexte") if isinstance(migrated.get("contexte"), dict) else {}
    migrated["contexte"] = {
        "emplacement": context.get("emplacement", "interieur"),
        "exposition": context.get("exposition", "non_renseignee"),
        "matiere_pot": context.get("matiere_pot", "non_renseignee"),
        "substrat": context.get("substrat", "non_renseigne"),
    }
    migrated.pop("nom_sci", None)
    migrated.pop("pot", None)
    return migrated


class CollectionRepository:
    def __init__(self, path: Path = COLLECTION_FILE, legacy_path: Path = LEGACY_COLLECTION_FILE):
        self.path = path
        self.legacy_path = legacy_path

    def migrate_legacy_file(self) -> bool:
        if self.path.exists() or not self.legacy_path.exists() or self.legacy_path.resolve() == self.path.resolve():
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.legacy_path, self.path)
        LOGGER.info("Collection historique copiée vers %s", self.path)
        return True

    def load(self, defaults: Iterable[dict[str, Any]] = ()) -> list[dict[str, Any]]:
        self.migrate_legacy_file()
        if not self.path.exists():
            plants = [
                _new_instance(
                    str(item.get("species_id") or item.get("nom_sci") or ""),
                    str(item.get("surnom") or "Plante"),
                    float(item.get("pot_l", item.get("pot", 1.0))),
                    date.today(),
                )
                for item in defaults
            ]
            self.save(plants)
            return plants
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Collection JSON corrompue : {exc}") from exc
        if isinstance(raw, dict):
            items = raw.get("plantes", [])
        elif isinstance(raw, list):
            items = raw
        else:
            raise ValidationError("Le fichier de collection doit contenir une liste ou un objet avec la clé 'plantes'.")
        if not isinstance(items, list):
            raise ValidationError("La clé 'plantes' doit contenir une liste.")
        plants = [migrate_item(item) for item in items if isinstance(item, dict)]
        ids = [plant["id"] for plant in plants]
        if len(ids) != len(set(ids)):
            raise ValidationError("Des identifiants de plantes sont dupliqués dans la collection.")
        return plants

    def save(self, plants: list[dict[str, Any]]) -> None:
        validated = [migrate_item(plant) for plant in plants]
        _backup(self.path)
        atomic_write_json(
            self.path,
            {"schema_version": SCHEMA_VERSION, "plantes": validated},
        )


class SettingsRepository:
    def __init__(self, path: Path = SETTINGS_FILE):
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"theme": "light", "geometry": "1200x800", "ingredient_stock": {}}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            LOGGER.exception("Impossible de charger les réglages")
            return {"theme": "light", "geometry": "1200x800", "ingredient_stock": {}}

    def save(self, settings: dict[str, Any]) -> None:
        atomic_write_json(self.path, settings)

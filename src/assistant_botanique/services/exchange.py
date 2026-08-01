"""Export modifiable et réimportation contrôlée de la collection."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from core import ValidationError
from assistant_botanique.infrastructure.database import Database, normalize_plant
from assistant_botanique.services.planner import CarePlanner

EXCHANGE_FORMAT = 1
CSV_FIELDS = (
    "id",
    "species_id",
    "surnom",
    "pot_l",
    "date_arrosage",
    "emplacement",
    "exposition",
    "matiere_pot",
    "substrat",
)


@dataclass(frozen=True, slots=True)
class ImportPreview:
    path: Path
    format: str
    plants: tuple[dict[str, Any], ...]
    tasks: tuple[dict[str, Any], ...]
    new_count: int
    updated_count: int
    warnings: tuple[str, ...]


class ExchangeService:
    def __init__(self, database: Database):
        self.database = database

    def export_json(self, destination: Path | str) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        planner = CarePlanner(self.database)
        payload = {
            "exchange_format": EXCHANGE_FORMAT,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "plants": self.database.load_plants(),
            "pending_tasks": planner.list_tasks(status="pending"),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def export_csv(self, destination: Path | str) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for plant in self.database.load_plants():
                context = plant.get("contexte") if isinstance(plant.get("contexte"), dict) else {}
                writer.writerow(
                    {
                        "id": plant.get("id", ""),
                        "species_id": plant.get("species_id", ""),
                        "surnom": plant.get("surnom", ""),
                        "pot_l": plant.get("pot_l", ""),
                        "date_arrosage": plant.get("date_arrosage", ""),
                        "emplacement": context.get("emplacement", ""),
                        "exposition": context.get("exposition", ""),
                        "matiere_pot": context.get("matiere_pot", ""),
                        "substrat": context.get("substrat", ""),
                    }
                )
        return path

    def preview(self, source: Path | str) -> ImportPreview:
        path = Path(source)
        suffix = path.suffix.casefold()
        current = {str(item["id"]): item for item in self.database.load_plants()}
        warnings: list[str] = []
        tasks: list[dict[str, Any]] = []
        if suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                raw_plants = payload
            elif isinstance(payload, dict):
                if payload.get("exchange_format") not in (None, EXCHANGE_FORMAT):
                    raise ValueError("Version d'export non prise en charge.")
                raw_plants = payload.get("plants", [])
                raw_tasks = payload.get("pending_tasks", [])
                tasks = [dict(item) for item in raw_tasks if isinstance(item, dict)] if isinstance(raw_tasks, list) else []
            else:
                raise ValueError("Le fichier JSON doit contenir une liste ou un export Assistant Botanique.")
            if not isinstance(raw_plants, list):
                raise ValueError("La clé 'plants' doit être une liste.")
            plants = [self._normalize_imported(item, current) for item in raw_plants if isinstance(item, dict)]
            source_format = "json"
        elif suffix == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            plants = [self._from_csv(row, current) for row in rows]
            source_format = "csv"
            warnings.append("Le format CSV ne contient pas l'historique complet ; l'historique existant est conservé lors d'une fusion.")
        else:
            raise ValueError("Formats acceptés : .json et .csv")

        identifiers = [str(item["id"]) for item in plants]
        if len(identifiers) != len(set(identifiers)):
            raise ValidationError("Le fichier contient plusieurs plantes avec le même identifiant.")
        new_count = sum(identifier not in current for identifier in identifiers)
        updated_count = len(identifiers) - new_count
        return ImportPreview(path, source_format, tuple(plants), tuple(tasks), new_count, updated_count, tuple(warnings))

    def apply(self, preview: ImportPreview, *, mode: str = "merge") -> None:
        mode = mode.casefold()
        if mode not in {"merge", "replace"}:
            raise ValueError("Le mode d'import doit être 'merge' ou 'replace'.")
        incoming = [dict(item) for item in preview.plants]
        if mode == "replace":
            final = incoming
        else:
            existing = {str(item["id"]): item for item in self.database.load_plants()}
            for item in incoming:
                identifier = str(item["id"])
                if preview.format == "csv" and identifier in existing:
                    item["historique_soins"] = existing[identifier].get("historique_soins", [])
                existing[identifier] = item
            final = list(existing.values())
        self.database.save_plants(final)
        if preview.tasks and mode == "replace":
            CarePlanner(self.database).replace_pending(preview.tasks)

    @staticmethod
    def _normalize_imported(item: dict[str, Any], current: dict[str, dict[str, Any]]) -> dict[str, Any]:
        candidate = dict(item)
        identifier = str(candidate.get("id") or "")
        if identifier and identifier in current and "historique_soins" not in candidate:
            candidate["historique_soins"] = current[identifier].get("historique_soins", [])
        return normalize_plant(candidate)

    @staticmethod
    def _from_csv(row: dict[str, Any], current: dict[str, dict[str, Any]]) -> dict[str, Any]:
        identifier = str(row.get("id") or "").strip()
        previous = current.get(identifier, {})
        context = previous.get("contexte") if isinstance(previous.get("contexte"), dict) else {}
        candidate = {
            "id": identifier,
            "species_id": str(row.get("species_id") or "").strip(),
            "surnom": str(row.get("surnom") or "").strip(),
            "pot_l": row.get("pot_l") or 1,
            "date_arrosage": row.get("date_arrosage"),
            "historique_soins": previous.get("historique_soins", []),
            "contexte": {
                **context,
                "emplacement": str(row.get("emplacement") or context.get("emplacement") or "interieur").strip(),
                "exposition": str(row.get("exposition") or context.get("exposition") or "non_renseignee").strip(),
                "matiere_pot": str(row.get("matiere_pot") or context.get("matiere_pot") or "non_renseignee").strip(),
                "substrat": str(row.get("substrat") or context.get("substrat") or "non_renseigne").strip(),
            },
        }
        return normalize_plant(candidate)


def count_exported_plants(path: Path | str) -> int:
    """Petit utilitaire de contrôle, utile aux tests et aux scripts."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    plants: Iterable[Any] = payload.get("plants", []) if isinstance(payload, dict) else payload
    return sum(1 for item in plants if isinstance(item, dict))

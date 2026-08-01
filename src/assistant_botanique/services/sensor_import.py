"""Import de mesures de capteurs depuis un CSV simple."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from assistant_botanique.infrastructure.advanced_repository import AdvancedRepository


class SensorImportService:
    REQUIRED_COLUMNS = {"source_id", "value"}

    def __init__(self, repository: AdvancedRepository):
        self.repository = repository

    def inspect_csv(self, source: Path | str) -> dict[str, Any]:
        source = Path(source)
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            rows = list(reader)
        missing = sorted(self.REQUIRED_COLUMNS - columns)
        return {
            "rows": len(rows),
            "columns": sorted(columns),
            "missing_columns": missing,
            "valid": not missing,
        }

    def import_csv(self, source: Path | str) -> dict[str, int]:
        source = Path(source)
        created = 0
        errors = 0
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = self.REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    "Colonnes manquantes : " + ", ".join(sorted(missing))
                )
            for row in reader:
                try:
                    self.repository.add_sensor_reading(
                        str(row.get("source_id") or ""),
                        float(str(row.get("value") or "").replace(",", ".")),
                        recorded_at=row.get("recorded_at") or None,
                        unit=row.get("unit") or None,
                        metadata={
                            key.removeprefix("meta_"): value
                            for key, value in row.items()
                            if key.startswith("meta_") and value not in (None, "")
                        },
                    )
                    created += 1
                except Exception:
                    errors += 1
        return {"created": created, "errors": errors}

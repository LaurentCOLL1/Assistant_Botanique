"""Chargement robuste du catalogue et compatibilité avec les données historiques."""
from __future__ import annotations

import json
import logging
import os
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from app_paths import FAMILIES_DIR, RESOURCE_DIR
from core import profile_id, scientific_name, vernacular_names

_previous_cwd = Path.cwd()
try:
    os.chdir(RESOURCE_DIR)
    from data import COLLECTION_INITIALE_DEFAUT, DIAGNOSTICS_DATA, PROFILS_GENERIQUES
finally:
    os.chdir(_previous_cwd)

LOGGER = logging.getLogger(__name__)


def normalize_profile(profile: dict[str, Any], source_file: str = "") -> dict[str, Any]:
    normalized = deepcopy(profile)
    normalized["id"] = profile_id(normalized)
    normalized["nom_sci"] = scientific_name(normalized)
    normalized["nom_vern"] = ", ".join(vernacular_names(normalized))
    metadata = normalized.get("metadata") if isinstance(normalized.get("metadata"), dict) else {}
    normalized["metadata"] = {
        "schema_version": int(metadata.get("schema_version", 1)),
        "source_file": source_file,
        "sources": metadata.get("sources", []),
        "last_reviewed": metadata.get("last_reviewed"),
        "confidence": metadata.get("confidence", "non_renseignee"),
    }
    return normalized


def load_catalogue(directory: Path = FAMILIES_DIR) -> tuple[list[dict[str, Any]], list[str]]:
    catalogue: list[dict[str, Any]] = []
    errors: list[str] = []
    if not directory.exists():
        return [], [f"Dossier catalogue introuvable : {directory}"]
    for path in sorted(directory.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, list):
                errors.append(f"{path.name}: la racine doit être une liste")
                continue
            for index, profile in enumerate(payload, start=1):
                if not isinstance(profile, dict):
                    errors.append(f"{path.name}[{index}]: entrée non objet")
                    continue
                catalogue.append(normalize_profile(profile, path.name))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
    counts = Counter(item["id"] for item in catalogue)
    duplicates = sorted(identifier for identifier, count in counts.items() if count > 1)
    if duplicates:
        errors.append("Identifiants scientifiques dupliqués : " + ", ".join(duplicates[:20]))
    for error in errors:
        LOGGER.warning("Validation catalogue : %s", error)
    return catalogue, errors


DATABASE_PLANTES, CATALOGUE_ERRORS = load_catalogue()
DATABASE_BY_ID = {profile["id"]: profile for profile in DATABASE_PLANTES}
DATABASE_BY_SCIENTIFIC_NAME = {scientific_name(profile): profile for profile in DATABASE_PLANTES}

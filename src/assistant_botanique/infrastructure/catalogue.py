"""Chargement du catalogue, adaptateur de données historiques et surcharges révisées."""
from __future__ import annotations

import importlib.util
import json
import os
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from core import family_name, profile_id, scientific_name, toxicity_level, vernacular_names

from assistant_botanique.paths import FAMILIES_DIR, OVERRIDES_DIR, RESOURCE_DIR


def _load_legacy_module():
    path = RESOURCE_DIR / "data.py"
    spec = importlib.util.spec_from_file_location("assistant_botanique_legacy_data", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Impossible de charger {path}")
    module = importlib.util.module_from_spec(spec)
    previous = Path.cwd()
    try:
        os.chdir(RESOURCE_DIR)
        spec.loader.exec_module(module)
    finally:
        os.chdir(previous)
    return module


def load_legacy_constants() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    module = _load_legacy_module()
    return (
        deepcopy(getattr(module, "COLLECTION_INITIALE_DEFAUT", [])),
        deepcopy(getattr(module, "DIAGNOSTICS_DATA", {})),
        deepcopy(getattr(module, "PROFILS_GENERIQUES", {})),
    )


def normalize_profile(profile: dict[str, Any], source_file: str = "") -> dict[str, Any]:
    normalized = deepcopy(profile)
    normalized["id"] = profile_id(normalized)
    normalized["nom_sci"] = scientific_name(normalized)
    normalized["nom_vern"] = ", ".join(vernacular_names(normalized))
    metadata = normalized.get("metadata") if isinstance(normalized.get("metadata"), dict) else {}
    normalized["metadata"] = {
        "schema_version": int(metadata.get("schema_version", 1)),
        "source_file": source_file or metadata.get("source_file", ""),
        "sources": [str(item).strip() for item in metadata.get("sources", []) if str(item).strip()],
        "last_reviewed": metadata.get("last_reviewed"),
        "confidence": metadata.get("confidence", "non_renseignee"),
        "review_status": metadata.get("review_status", "a_verifier"),
    }
    return normalized


def validate_profile(profile: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if scientific_name(profile) == "Inconnu":
        errors.append("nom scientifique absent")
    if not isinstance(profile.get("taxonomie"), dict):
        errors.append("section taxonomie absente")
    metadata = profile.get("metadata", {})
    if not isinstance(metadata, dict) or not metadata.get("sources"):
        warnings.append("sources botaniques absentes")
    if toxicity_level(profile.get("sante_securite", {}).get("toxicite")) == "inconnue":
        warnings.append("toxicité non normalisée")
    text = json.dumps(profile, ensure_ascii=False).casefold()
    for typo in ("llegume", "étiollement"):
        if typo in text:
            warnings.append(f"coquille probable : {typo}")
    return errors, warnings


def _load_overrides() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(OVERRIDES_DIR.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                result[profile_id(value)] = value
        except (OSError, json.JSONDecodeError):
            continue
    return result


def load_catalogue(directory: Path = FAMILIES_DIR) -> tuple[list[dict[str, Any]], list[str]]:
    catalogue: list[dict[str, Any]] = []
    errors: list[str] = []
    overrides = _load_overrides()
    if not directory.exists():
        return [], [f"Dossier catalogue introuvable : {directory}"]
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if not isinstance(payload, list):
            errors.append(f"{path.name}: la racine doit être une liste")
            continue
        for index, raw in enumerate(payload, start=1):
            if not isinstance(raw, dict):
                errors.append(f"{path.name}[{index}]: entrée non objet")
                continue
            base = normalize_profile(raw, path.name)
            override = overrides.get(base["id"])
            profile = normalize_profile(override, path.name) if override else base
            profile_errors, _warnings = validate_profile(profile)
            if profile_errors:
                errors.extend(f"{path.name}[{index}]: {item}" for item in profile_errors)
            catalogue.append(profile)
    counts = Counter(profile["id"] for profile in catalogue)
    duplicates = [identifier for identifier, count in counts.items() if count > 1]
    if duplicates:
        errors.append("Identifiants dupliqués : " + ", ".join(sorted(duplicates)[:20]))
    return catalogue, errors


def save_override(profile: dict[str, Any]) -> Path:
    normalized = normalize_profile(profile)
    errors, _warnings = validate_profile(normalized)
    if errors:
        raise ValueError("; ".join(errors))
    slug = re.sub(r"[^a-z0-9-]+", "-", normalized["id"].casefold()).strip("-") or "profile"
    path = OVERRIDES_DIR / f"{slug}.json"
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return path


def catalogue_review_score(profile: dict[str, Any]) -> int:
    score = 0
    metadata = profile.get("metadata", {}) if isinstance(profile.get("metadata"), dict) else {}
    score += min(30, len(metadata.get("sources", [])) * 10)
    score += 20 if metadata.get("last_reviewed") else 0
    score += 15 if metadata.get("confidence") in {"moyenne", "elevee"} else 0
    score += 15 if isinstance(profile.get("gestion_eau"), dict) else 0
    score += 10 if isinstance(profile.get("substrat"), dict) else 0
    score += 10 if family_name(profile) != "Non renseignée" else 0
    return min(100, score)

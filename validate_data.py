"""Audit des fiches botaniques JSON.

Usage : python validate_data.py [--strict] [--baseline fichier.json]
Le mode normal signale les anomalies sans bloquer. Avec une baseline, le mode
strict échoue uniquement lorsqu'une nouvelle erreur structurelle apparaît :
les défauts historiques restent visibles et doivent être résorbés progressivement.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app_paths import FAMILIES_DIR
from core import MONTH_KEYS, profile_id, scientific_name, toxicity_level

MONTHS = tuple(MONTH_KEYS.values())


def audit_profile(profile: dict[str, Any], location: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    name = scientific_name(profile)
    if name == "Inconnu":
        errors.append(f"{location}: nom scientifique absent")
    tax = profile.get("taxonomie")
    if not isinstance(tax, dict):
        errors.append(f"{location}: section taxonomie absente")
    water = profile.get("gestion_eau", {})
    if isinstance(water, dict) and isinstance(water.get("frequence_arrosage"), dict):
        frequency = water["frequence_arrosage"]
        missing = [month for month in MONTHS if month not in frequency]
        if missing:
            errors.append(f"{location}: mois manquants dans l'arrosage: {', '.join(missing)}")
        for month, value in frequency.items():
            if month not in MONTHS:
                warnings.append(f"{location}: mois inconnu {month!r}")
            if not isinstance(value, int) or value < 0:
                errors.append(f"{location}: fréquence invalide pour {month}: {value!r}")
    substrate = profile.get("substrat", {})
    if isinstance(substrate, dict) and isinstance(substrate.get("roles"), list):
        ratios = [role.get("ratio") for role in substrate["roles"] if isinstance(role, dict)]
        if not all(isinstance(ratio, (int, float)) and ratio >= 0 for ratio in ratios):
            errors.append(f"{location}: ratio de substrat invalide")
        elif abs(sum(ratios) - 1.0) > 0.001:
            errors.append(f"{location}: somme des ratios de substrat = {sum(ratios):.3f}, attendu 1.0")
    health = profile.get("sante_securite", {})
    if isinstance(health, dict):
        toxicity = health.get("toxicite")
        if toxicity_level(toxicity) == "inconnue" and toxicity not in (None, "", "Variable / Se renseigner avant ingestion"):
            warnings.append(f"{location}: toxicité difficile à normaliser: {toxicity!r}")
    metadata = profile.get("metadata", {})
    if not isinstance(metadata, dict) or not metadata.get("sources"):
        warnings.append(f"{location}: sources botaniques à compléter")
    text = json.dumps(profile, ensure_ascii=False).lower()
    for typo in ("llegume", "étiollement"):
        if typo in text:
            warnings.append(f"{location}: coquille probable {typo!r}")
    return errors, warnings


def audit_directory(directory: Path = FAMILIES_DIR) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    identifiers: list[tuple[str, str]] = []
    fingerprints: defaultdict[str, list[str]] = defaultdict(list)
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: JSON illisible: {exc}")
            continue
        if not isinstance(payload, list):
            errors.append(f"{path.name}: la racine doit être une liste")
            continue
        for index, profile in enumerate(payload, start=1):
            location = f"{path.name}[{index}]"
            if not isinstance(profile, dict):
                errors.append(f"{location}: entrée non objet")
                continue
            identifiers.append((profile_id(profile), location))
            profile_errors, profile_warnings = audit_profile(profile, location)
            errors.extend(profile_errors)
            warnings.extend(profile_warnings)
            morph = profile.get("morphologie", {})
            water = profile.get("gestion_eau", {})
            signature_text = json.dumps({"morphologie": morph, "gestion_eau": water}, ensure_ascii=False, sort_keys=True)
            signature = re.sub(r"\s+", " ", signature_text)
            if len(signature) > 120:
                fingerprints[signature].append(location)
    counts = Counter(identifier for identifier, _ in identifiers)
    for identifier, count in counts.items():
        if count > 1:
            locations = [location for item_id, location in identifiers if item_id == identifier]
            errors.append(f"Identifiant dupliqué {identifier!r}: {', '.join(locations)}")
    for locations in fingerprints.values():
        if len(locations) >= 4:
            warnings.append(f"Contenu morphologie/arrosage identique dans {len(locations)} fiches: {', '.join(locations[:6])}")
    return errors, warnings


def load_baseline(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("errors") if isinstance(payload, dict) else payload
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError("La baseline doit contenir une liste de chaînes sous la clé 'errors'.")
    return set(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Échouer en présence de nouvelles erreurs structurelles")
    parser.add_argument("--baseline", type=Path, help="Fichier recensant les erreurs historiques tolérées temporairement")
    args = parser.parse_args()
    errors, warnings = audit_directory()
    baseline: set[str] = set()
    if args.baseline:
        try:
            baseline = load_baseline(args.baseline)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"BASELINE INVALIDE: {exc}")
            return 2
    new_errors = [item for item in errors if item not in baseline]
    known_errors = [item for item in errors if item in baseline]
    resolved_errors = sorted(baseline.difference(errors))
    print(
        f"Audit catalogue: {len(errors)} erreur(s), {len(warnings)} avertissement(s), "
        f"{len(new_errors)} nouvelle(s), {len(resolved_errors)} résolue(s) depuis la baseline"
    )
    for item in new_errors:
        print(f"NOUVELLE ERREUR: {item}")
    for item in known_errors:
        print(f"ERREUR HISTORIQUE: {item}")
    for item in resolved_errors:
        print(f"RÉSOLUE DEPUIS LA BASELINE: {item}")
    for item in warnings[:200]:
        print(f"AVERTISSEMENT: {item}")
    return 1 if args.strict and new_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

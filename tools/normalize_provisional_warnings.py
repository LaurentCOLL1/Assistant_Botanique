"""Normalise les avertissements provisoires et les identifiants du catalogue."""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "familles_plantes"
METADATA_PATHS = (
    ROOT / "catalogue_metadata" / "taxonomy_audit.json",
    ROOT / "catalogue_metadata" / "photos.json",
)
CATALOGUE_TOOL = ROOT / "tools" / "catalogue_enrichment.py"
TOXICITY_WARNING = (
    "À vérifier spécifiquement ; ne pas ingérer sans validation botanique et sanitaire."
)


def scientific_name(profile: dict[str, Any]) -> str:
    taxonomy = profile.get("taxonomie")
    if not isinstance(taxonomy, dict):
        return "ce taxon"
    return str(taxonomy.get("nom_scientifique") or "ce taxon").strip()


def normalized_identifier(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode()
        .casefold()
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")


def normalize_profile(profile: dict[str, Any]) -> bool:
    validation = profile.get("validation_catalogue")
    if not isinstance(validation, dict):
        return False

    changed = False
    name = scientific_name(profile)
    warning = (
        f"Profil horticole provisoire pour {name}. "
        "Vérifier individuellement les besoins de culture, la toxicité et les usages "
        "avant toute culture destinée à la consommation."
    )
    current_advice = str(profile.get("conseil") or "").strip()
    if "provisoire" not in current_advice.casefold():
        profile["conseil"] = f"{warning} {current_advice}".strip()
        changed = True
    elif "consomm" not in current_advice.casefold():
        profile["conseil"] = f"{current_advice} Ne pas consommer sans validation spécifique."
        changed = True

    health = profile.get("sante_securite")
    if not isinstance(health, dict):
        health = {}
        profile["sante_securite"] = health
        changed = True
    if health.get("toxicite") != TOXICITY_WARNING:
        health["toxicite"] = TOXICITY_WARNING
        changed = True
    property_warning = (
        "Identité taxonomique vérifiée par GBIF ; données horticoles provisoires à réviser."
    )
    if health.get("proprietes_particulieres") != property_warning:
        health["proprietes_particulieres"] = property_warning
        changed = True
    return changed


def patch_catalogue_identifier_generator() -> bool:
    """Aligne le générateur d'identifiants sur la normalisation Unicode des tests."""
    text = CATALOGUE_TOOL.read_text(encoding="utf-8")
    changed = False
    if "import unicodedata\n" not in text:
        marker = "import time\nimport urllib.error\n"
        if marker not in text:
            raise RuntimeError("Bloc d'import attendu introuvable dans catalogue_enrichment.py")
        text = text.replace(
            marker,
            "import time\nimport unicodedata\nimport urllib.error\n",
            1,
        )
        changed = True

    old_function = '''def normalize(value: str) -> str:\n    value = value.casefold()\n    value = re.sub(r"[^a-z0-9]+", "-", value)\n    return value.strip("-")\n'''
    new_function = '''def normalize(value: str) -> str:\n    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()\n    value = re.sub(r"[^a-z0-9]+", "-", value)\n    return value.strip("-")\n'''
    if old_function in text:
        text = text.replace(old_function, new_function, 1)
        changed = True
    elif new_function not in text:
        raise RuntimeError("Fonction normalize attendue introuvable dans catalogue_enrichment.py")

    if changed:
        CATALOGUE_TOOL.write_text(text, encoding="utf-8")
    return changed


def rekey_metadata(path: Path) -> int:
    """Reconstruit les clés à partir du nom scientifique, doublons compris."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    if not isinstance(profiles, dict):
        raise ValueError(f"{path}: objet 'profiles' absent")

    counts: Counter[str] = Counter()
    rekeyed: dict[str, Any] = {}
    changed = 0
    for old_identifier, item in profiles.items():
        if not isinstance(item, dict):
            raise ValueError(f"{path}: entrée invalide pour {old_identifier}")
        name = str(item.get("scientific_name") or "").strip()
        base_identifier = normalized_identifier(name) if name else str(old_identifier)
        counts[base_identifier] += 1
        count = counts[base_identifier]
        new_identifier = (
            base_identifier
            if count == 1
            else f"{base_identifier}--duplicate-{count}"
        )
        if new_identifier in rekeyed:
            raise ValueError(f"{path}: collision d'identifiant {new_identifier}")
        rekeyed[new_identifier] = item
        if new_identifier != old_identifier:
            changed += 1

    if changed:
        payload["profiles"] = rekeyed
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def main() -> int:
    changed_files = 0
    changed_profiles = 0
    for path in sorted(FAMILY_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            continue
        changed = False
        for profile in payload:
            if isinstance(profile, dict) and normalize_profile(profile):
                changed = True
                changed_profiles += 1
        if changed:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            changed_files += 1

    generator_changed = patch_catalogue_identifier_generator()
    metadata_changes = {
        path.name: rekey_metadata(path)
        for path in METADATA_PATHS
    }
    print(
        f"Avertissements normalisés : {changed_profiles} profil(s), "
        f"{changed_files} fichier(s). Générateur corrigé : {generator_changed}. "
        f"Clés de métadonnées corrigées : {metadata_changes}.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

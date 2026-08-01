"""Rend explicites les limites horticoles de chaque profil ajouté par GBIF."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "familles_plantes"
TOXICITY_WARNING = (
    "À vérifier spécifiquement ; ne pas ingérer sans validation botanique et sanitaire."
)


def scientific_name(profile: dict[str, Any]) -> str:
    taxonomy = profile.get("taxonomie")
    if not isinstance(taxonomy, dict):
        return "ce taxon"
    return str(taxonomy.get("nom_scientifique") or "ce taxon").strip()


def normalize_profile(profile: dict[str, Any]) -> bool:
    validation = profile.get("validation_catalogue")
    if not isinstance(validation, dict):
        return False

    name = scientific_name(profile)
    warning = (
        f"Profil horticole provisoire pour {name}. "
        "Vérifier individuellement les besoins de culture, la toxicité et les usages "
        "avant toute culture destinée à la consommation."
    )
    current_advice = str(profile.get("conseil") or "").strip()
    if "provisoire" not in current_advice.casefold():
        profile["conseil"] = f"{warning} {current_advice}".strip()
    elif "consomm" not in current_advice.casefold():
        profile["conseil"] = f"{current_advice} Ne pas consommer sans validation spécifique."

    health = profile.get("sante_securite")
    if not isinstance(health, dict):
        health = {}
        profile["sante_securite"] = health
    health["toxicite"] = TOXICITY_WARNING
    health["proprietes_particulieres"] = (
        "Identité taxonomique vérifiée par GBIF ; données horticoles provisoires à réviser."
    )
    return True


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
    print(
        f"Avertissements normalisés : {changed_profiles} profil(s), "
        f"{changed_files} fichier(s).",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

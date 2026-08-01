"""Enrichit toutes les fiches du catalogue avec des recettes de substrat sourcées."""
from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import substrate_classifier  # noqa: E402
from substrate_knowledge import enrich_profile, validate_resolved_profile  # noqa: E402

substrate_classifier.install()

FAMILY_DIR = ROOT / "familles_plantes"
REPORT_PATH = ROOT / "catalogue_metadata" / "substrate_audit.json"
GENERATED_SUBSTRATE_KEYS = {
    "categorie_horticole",
    "modele_recherche",
    "version_recherche",
    "variantes",
    "sources",
}


def _without_previous_generation(profile: dict) -> dict:
    """Retire uniquement les champs ajoutés par une génération précédente."""
    cleaned = copy.deepcopy(profile)
    substrate = cleaned.get("substrat", {})
    if not isinstance(substrate, dict) or not substrate.get("version_recherche"):
        return cleaned

    for key in GENERATED_SUBSTRATE_KEYS:
        substrate.pop(key, None)
    # Ces champs de compatibilité ont été écrits par le générateur avec la
    # première variante. Ils doivent être recalculés avec la classification.
    substrate.pop("composition_ideale", None)
    substrate.pop("ingredients_recommandes", None)
    substrate.pop("elements_interdits", None)
    cleaned["substrat"] = substrate
    cleaned.pop("roles", None)
    cleaned.pop("interdits", None)
    return cleaned


def main() -> int:
    profile_count = 0
    file_count = 0
    variant_count = 0
    template_counts: Counter[str] = Counter()
    errors: list[str] = []

    for path in sorted(FAMILY_DIR.glob("*.json")):
        source = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(source, list):
            errors.append(f"{path.name}: la racine JSON n'est pas une liste")
            continue
        enriched_profiles: list[dict] = []
        for index, profile in enumerate(source):
            if not isinstance(profile, dict):
                errors.append(f"{path.name}[{index}]: fiche invalide")
                continue
            enriched = enrich_profile(_without_previous_generation(profile))
            validation = validate_resolved_profile(enriched)
            scientific = enriched.get("taxonomie", {}).get("nom_scientifique", f"index {index}")
            errors.extend(f"{path.name} — {scientific}: {message}" for message in validation)
            substrate = enriched["substrat"]
            template_counts[str(substrate["modele_recherche"])] += 1
            variant_count += len(substrate["variantes"])
            profile_count += 1
            enriched_profiles.append(enriched)
        rendered = json.dumps(enriched_profiles, ensure_ascii=False, indent=2) + "\n"
        if path.read_text(encoding="utf-8") != rendered:
            path.write_text(rendered, encoding="utf-8")
        file_count += 1

    report = {
        "version": "2026.08",
        "family_files": file_count,
        "profiles": profile_count,
        "variants": variant_count,
        "templates": dict(sorted(template_counts.items())),
        "errors": errors,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(f"Audit substrat en échec: {len(errors)} erreur(s).")
    if profile_count == 0:
        raise SystemExit("Aucune fiche trouvée dans le catalogue.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

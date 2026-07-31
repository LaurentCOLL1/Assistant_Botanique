"""Corrige les anomalies certaines détectées par l'audit exhaustif.

Les remplacements sont volontairement exacts et vérifient leur cardinalité afin
d'éviter toute modification large ou ambiguë des gros fichiers historiques.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from catalogue_enrichment import (
    REPORT_OUTPUT,
    TAXONOMY_OUTPUT,
    build_report,
    family_name,
    load_profiles,
    profile_id,
    scientific_name,
    structural_audit,
)

ROOT = Path(__file__).resolve().parents[1]

REPLACEMENTS: dict[str, list[tuple[str, str]]] = {
    "familles_plantes/bromeliaceae.json": [
        ('"april": 7', '"avril": 7'),
    ],
    "familles_plantes/liliaceae.json": [
        ('"jullet": 4', '"juillet": 4'),
    ],
    "familles_plantes/tiliaceae.json": [
        ('"april": 1', '"avril": 1'),
    ],
    "familles_plantes/aizoaceae_portulacaceae.json": [
        ('"famille": "Portulacariaceae (ex-Portulacaceae)"', '"famille": "Didiereaceae"'),
        ('"famille": "Anacampserotaceae (ex-Portulacaceae)"', '"famille": "Anacampserotaceae"'),
    ],
    "familles_plantes/cycadaceae_zamiaceae.json": [
        ('"famille": "Zamiaceae (ex-Cycadales)"', '"famille": "Zamiaceae"'),
    ],
    "familles_plantes/polygonaceae.json": [
        (
            '"famille": "Asparagaceae (anciennement classé parfois proche ou confondu, mais ici mentionné comme alternative de sous-bois, attention aux confusions de noms vernaculaires, restons sur une vraie Polygonacée de sous-bois si possible : Polygonatum est Asparagacée, remplaçons par Rumex thyrsiflorus ou Oxyria digyna pour rester strictement dans les Polygonaceae)"',
            '"famille": "Asparagaceae"',
        ),
    ],
}


def apply_exact_replacements() -> list[str]:
    changed: list[str] = []
    for relative_path, replacements in REPLACEMENTS.items():
        path = ROOT / relative_path
        text = path.read_text(encoding="utf-8")
        updated = text
        for old, new in replacements:
            count = updated.count(old)
            if count == 0 and new in updated:
                continue
            if count != 1:
                raise RuntimeError(
                    f"{relative_path}: remplacement non sûr pour {old!r}; occurrences trouvées: {count}."
                )
            updated = updated.replace(old, new, 1)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed.append(relative_path)
    return changed


def normalized_status(taxonomic: dict[str, Any]) -> str:
    current = str(taxonomic.get("status") or "")
    if current != "family_mismatch":
        return current
    match_type = str(taxonomic.get("match_type") or "")
    taxonomic_status = str(taxonomic.get("taxonomic_status") or "")
    if match_type == "EXACT" and taxonomic_status == "ACCEPTED":
        return "accepted_exact"
    if taxonomic_status in {"SYNONYM", "HETEROTYPIC_SYNONYM", "HOMOTYPIC_SYNONYM"}:
        return "synonym"
    return "matched_review"


def refresh_generated_audit() -> None:
    if not TAXONOMY_OUTPUT.exists():
        return
    payload = json.loads(TAXONOMY_OUTPUT.read_text(encoding="utf-8"))
    audit_profiles = payload.get("profiles") if isinstance(payload, dict) else None
    if not isinstance(audit_profiles, dict):
        raise RuntimeError("taxonomy_audit.json ne contient pas de table profiles exploitable.")
    profiles, file_errors = load_profiles()
    if file_errors:
        raise RuntimeError("; ".join(file_errors))
    for profile in profiles:
        identifier = profile_id(profile)
        audit = audit_profiles.get(identifier)
        if not isinstance(audit, dict):
            continue
        audit["scientific_name"] = scientific_name(profile)
        audit["declared_family"] = family_name(profile)
        audit["source_file"] = profile.get("_source_file")
        audit["source_index"] = profile.get("_source_index")
        audit["structure"] = structural_audit(profile)
        taxonomic = audit.get("taxonomic") if isinstance(audit.get("taxonomic"), dict) else {}
        matched_family = str(taxonomic.get("family") or "")
        declared_family = family_name(profile)
        if matched_family:
            consistent = matched_family.casefold() == declared_family.casefold()
            taxonomic["family_consistent"] = consistent
            if consistent:
                taxonomic["status"] = normalized_status(taxonomic)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    TAXONOMY_OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    photos_path = ROOT / "catalogue_metadata/photos.json"
    photos_payload = json.loads(photos_path.read_text(encoding="utf-8")) if photos_path.exists() else {}
    photos = photos_payload.get("profiles", {}) if isinstance(photos_payload, dict) else {}
    REPORT_OUTPUT.write_text(
        build_report(profiles, file_errors, audit_profiles, photos),
        encoding="utf-8",
    )


def main() -> int:
    changed = apply_exact_replacements()
    refresh_generated_audit()
    if changed:
        print("Fichiers corrigés : " + ", ".join(changed))
    else:
        print("Les corrections certaines étaient déjà appliquées.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

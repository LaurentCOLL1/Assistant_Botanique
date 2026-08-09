"""Remplace les placeholders de noms vernaculaires par des noms attestés.

L'audit porte sur tous les fichiers canoniques de ``familles_plantes``. Un
placeholder tel que « Nom vernaculaire non documenté » est considéré comme une
absence de nom. Les recherches utilisent GBIF puis iNaturalist et n'inventent
jamais de traduction à partir du nom scientifique.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any

from tools.enrich_selenicereus_and_vernaculars import (
    GBIF_VERNACULAR,
    INAT_TAXA,
    LANGUAGE_ORDER,
    clean_candidate,
    gbif_names,
    request_json,
)

ROOT = Path(__file__).resolve().parents[1]
FAMILIES_DIR = ROOT / "familles_plantes"
REPORT_FILE = ROOT / "catalogue_metadata" / "global_vernacular_name_audit.json"

PLACEHOLDER_PATTERNS = (
    r"^nom vernaculaire non document[ée]$",
    r"^nom commun non document[ée]$",
    r"^nom vernaculaire (?:à|a) documenter$",
    r"^nom commun (?:à|a) documenter$",
    r"^non renseign[ée]$",
    r"^inconnu$",
    r"^unknown$",
    r"^aucun nom vernaculaire(?: document[ée])?$",
    r"^aucun nom commun(?: document[ée])?$",
    r"^no common name$",
)
PLACEHOLDER_RE = re.compile("|".join(f"(?:{pattern})" for pattern in PLACEHOLDER_PATTERNS), re.IGNORECASE)


def _taxonomy(profile: dict[str, Any]) -> dict[str, Any]:
    value = profile.get("taxonomie")
    return value if isinstance(value, dict) else {}


def _scientific(profile: dict[str, Any]) -> str:
    return str(_taxonomy(profile).get("nom_scientifique") or "").strip()


def _is_placeholder(value: Any) -> bool:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" .;:-")
    return not text or bool(PLACEHOLDER_RE.fullmatch(text))


def _real_names(profile: dict[str, Any]) -> list[str]:
    raw = _taxonomy(profile).get("noms_vernaculaires")
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in raw:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if _is_placeholder(text):
            continue
        marker = text.casefold()
        if marker not in seen:
            seen.add(marker)
            result.append(text)
    return result


def _known_gbif_key(profile: dict[str, Any]) -> int | None:
    validation = profile.get("validation_catalogue")
    if not isinstance(validation, dict):
        return None
    value = validation.get("gbif_key")
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _gbif_names_from_key(scientific: str, key: int) -> list[dict[str, str]]:
    payload = request_json(GBIF_VERNACULAR.format(key=key), {"limit": 1000})
    rows = payload if isinstance(payload, list) else (payload or {}).get("results", []) if isinstance(payload, dict) else []
    result: list[dict[str, str]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        name = clean_candidate(row.get("vernacularName"), scientific)
        if not name or _is_placeholder(name):
            continue
        result.append(
            {
                "name": name,
                "language": str(row.get("language") or "").casefold(),
                "provider": "GBIF",
                "source": str(row.get("source") or "GBIF").strip(),
                "url": f"https://www.gbif.org/species/{key}",
            }
        )
    return result


def _inat_fallback(scientific: str) -> list[dict[str, str]]:
    """Cherche au plus un nom français et un nom anglais lorsque GBIF est vide."""
    result: list[dict[str, str]] = []
    for locale in ("fr", "en"):
        payload = request_json(INAT_TAXA, {"q": scientific, "rank": "species", "locale": locale, "per_page": 5})
        rows = payload.get("results", []) if isinstance(payload, dict) else []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            row_name = str(row.get("name") or "").strip()
            matched = str(row.get("matched_term") or "").strip()
            if row_name.casefold() != scientific.casefold() and matched.casefold() != scientific.casefold():
                continue
            name = clean_candidate(row.get("preferred_common_name"), scientific)
            if name and not _is_placeholder(name):
                result.append(
                    {
                        "name": name,
                        "language": locale,
                        "provider": "iNaturalist",
                        "source": "iNaturalist taxon names",
                        "url": f"https://www.inaturalist.org/taxa/{row.get('id')}",
                    }
                )
            break
    return result


def _research(scientific: str, family: str, gbif_key: int | None) -> dict[str, Any]:
    if gbif_key is not None:
        rows = _gbif_names_from_key(scientific, gbif_key)
        key = str(gbif_key)
    else:
        rows, key = gbif_names(scientific, family)

    if not rows:
        rows.extend(_inat_fallback(scientific))

    rows.sort(key=lambda row: (LANGUAGE_ORDER.get(row.get("language", ""), 5), row["name"].casefold()))
    names: list[str] = []
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        name = re.sub(r"\s+", " ", str(row.get("name") or "")).strip()
        if _is_placeholder(name):
            continue
        marker = name.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        names.append(name)
        sources.append(row)
        if len(names) == 4:
            break
    return {"scientific_name": scientific, "names": names, "sources": sources, "gbif_key": key}


def _load_files() -> list[tuple[Path, list[dict[str, Any]]]]:
    loaded: list[tuple[Path, list[dict[str, Any]]]] = []
    for path in sorted(FAMILIES_DIR.glob("*.json")):
        if path.name.endswith("_selenicereus.json"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, list):
            loaded.append((path, [item for item in payload if isinstance(item, dict)]))
    return loaded


def main() -> int:
    files = _load_files()
    by_path = {path: profiles for path, profiles in files}
    targets: list[tuple[Path, int, str, str, int | None]] = []
    cleaned_paths: set[Path] = set()
    cleaned_existing = 0
    total = 0

    for path, profiles in files:
        for index, profile in enumerate(profiles):
            total += 1
            taxonomy = _taxonomy(profile)
            raw = taxonomy.get("noms_vernaculaires")
            real = _real_names(profile)
            raw_list = raw if isinstance(raw, list) else []
            if real:
                if real != raw_list:
                    taxonomy["noms_vernaculaires"] = real
                    cleaned_existing += 1
                    cleaned_paths.add(path)
                continue

            scientific = _scientific(profile)
            if not scientific or scientific.casefold() == "inconnu" or "'" in scientific or scientific.endswith(" sp."):
                if raw_list:
                    taxonomy["noms_vernaculaires"] = []
                    cleaned_paths.add(path)
                continue
            family = str(taxonomy.get("famille") or "").strip()
            targets.append((path, index, scientific, family, _known_gbif_key(profile)))

    unique_queries: dict[tuple[str, str, int | None], dict[str, Any]] = {}
    keys = {(scientific, family, gbif_key) for _, _, scientific, family, gbif_key in targets}
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {
            executor.submit(_research, scientific, family, gbif_key): (scientific, family, gbif_key)
            for scientific, family, gbif_key in keys
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                unique_queries[key] = future.result()
            except Exception as exc:  # noqa: BLE001 - une source indisponible ne doit pas annuler l'audit
                unique_queries[key] = {
                    "scientific_name": key[0],
                    "names": [],
                    "sources": [],
                    "error": str(exc),
                }

    changed_files: set[Path] = set(cleaned_paths)
    resolved_records: list[dict[str, Any]] = []
    unresolved: list[str] = []
    resolved = 0
    for path, index, scientific, family, gbif_key in targets:
        result = unique_queries[(scientific, family, gbif_key)]
        names = list(result.get("names") or [])
        profile = by_path[path][index]
        profile.setdefault("taxonomie", {})["noms_vernaculaires"] = names
        changed_files.add(path)
        if names:
            resolved += 1
            resolved_records.append(result)
        else:
            unresolved.append(scientific)

    for path, profiles in files:
        if path in changed_files:
            path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "generated_at": date.today().isoformat(),
        "catalogue_profiles": total,
        "missing_or_placeholder_before": len(targets),
        "resolved": resolved,
        "remaining_without_attested_name": sorted(set(unresolved), key=str.casefold),
        "remaining_count": len(set(unresolved)),
        "cleaned_placeholder_entries_with_existing_real_names": cleaned_existing,
        "changed_files": sorted(path.name for path in changed_files),
        "resolved_records": sorted(resolved_records, key=lambda row: str(row.get("scientific_name") or "").casefold()),
        "method": "GBIF vernacularNames ; iNaturalist seulement lorsque GBIF est vide ; aucun nom généré par traduction",
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Audit global : {total} fiches ; {len(targets)} sans vrai nom vernaculaire ; "
        f"{resolved} complétées ; {report['remaining_count']} sans nom attesté."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

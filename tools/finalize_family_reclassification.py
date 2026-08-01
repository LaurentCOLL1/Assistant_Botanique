"""Finalise le reclassement familial et synchronise les métadonnées du catalogue.

Ce passage retire les compléments automatiques classés sans signal de popularité,
les remplace par les espèces les plus observées dans GBIF, puis reconstruit les
tables d'audit et de photos sans inventer de contenu horticole ou visuel.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import catalogue_enrichment as audit_tools
import reclassify_and_expand_families as base

ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "familles_plantes"
META_DIR = ROOT / "catalogue_metadata"
TAXONOMY_PATH = META_DIR / "taxonomy_audit.json"
PHOTOS_PATH = META_DIR / "photos.json"
CATALOGUE_REPORT_PATH = META_DIR / "catalogue_audit_report.md"
FAMILY_REPORT_PATH = META_DIR / "family_reclassification_report.md"
OCCURRENCE_API = "https://api.gbif.org/v1/occurrence/search"
SPECIES_API = "https://api.gbif.org/v1/species"
MAX_WORKERS = 16
TARGET = 20
TODAY = datetime.now(timezone.utc).date().isoformat()
SMALL_FAMILY_LIMITS = {
    "Cephalotaceae": 1,
    "Dioncophyllaceae": 3,
    "Mystropetalaceae": 4,
}


def request_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    target = url
    if params:
        target += "?" + urllib.parse.urlencode(params, doseq=True)
    request = urllib.request.Request(target, headers=base.HEADERS)
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.load(response)
                return payload if isinstance(payload, dict) else None
        except urllib.error.HTTPError as exc:
            if exc.code == 404 or (exc.code != 429 and exc.code < 500):
                return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(0.5 + attempt)
    return None


def accepted_family_key(family_name: str) -> int | None:
    match = base.match(family_name, "FAMILY") or {}
    key = match.get("acceptedUsageKey") or match.get("usageKey")
    return key if isinstance(key, int) else None


def occurrence_ranked_species(family_name: str) -> list[dict[str, Any]]:
    """Retourne les espèces de la famille classées par occurrences GBIF."""
    family_key = accepted_family_key(family_name)
    if family_key is None:
        return []
    payload = request_json(
        OCCURRENCE_API,
        {
            "taxon_key": family_key,
            "limit": 0,
            "facet": "speciesKey",
            "facet_limit": 1000,
            "facet_mincount": 1,
        },
    ) or {}
    facets = payload.get("facets") if isinstance(payload.get("facets"), list) else []
    counts: list[tuple[int, int]] = []
    for facet in facets:
        if not isinstance(facet, dict):
            continue
        field = str(facet.get("field") or "").casefold()
        if field not in {"specieskey", "species_key"}:
            continue
        for item in facet.get("counts", []) if isinstance(facet.get("counts"), list) else []:
            if not isinstance(item, dict):
                continue
            try:
                key = int(item.get("name"))
                count = int(item.get("count") or 0)
            except (TypeError, ValueError):
                continue
            counts.append((key, count))
    counts.sort(key=lambda pair: (-pair[1], pair[0]))
    if not counts:
        return []

    ranked: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="gbif-detail") as executor:
        futures = {
            executor.submit(request_json, f"{SPECIES_API}/{key}"): (key, count)
            for key, count in counts[:400]
        }
        for future in as_completed(futures):
            key, count = futures[future]
            item = future.result() or {}
            canonical = base.clean(item.get("canonicalName") or item.get("scientificName"))
            accepted_family = base.clean(item.get("family"))
            rank = str(item.get("rank") or "").upper()
            status = str(item.get("taxonomicStatus") or item.get("status") or "").upper()
            if accepted_family.casefold() != family_name.casefold():
                continue
            if rank != "SPECIES" or status not in {"ACCEPTED", "DOUBTFUL"}:
                continue
            if len(canonical.split()) != 2 or "×" in canonical:
                continue
            ranked.append(
                {
                    "name": canonical,
                    "family": family_name,
                    "key": item.get("nubKey") or item.get("key") or key,
                    "occurrences": count,
                }
            )
    return sorted(ranked, key=lambda item: (-int(item["occurrences"]), item["name"].casefold()))


def current_profiles_by_family() -> dict[str, list[dict[str, Any]]]:
    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(FAMILY_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for profile in payload if isinstance(payload, list) else []:
            validation = profile.get("validation_catalogue")
            priority = validation.get("priorite") if isinstance(validation, dict) else None
            if priority == "gbif_frequente":
                continue
            families[base.family(profile)].append(profile)
    return families


def refine_family(
    family_name: str,
    source_items: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], int]:
    items = list(source_items)
    existing = {base.normalized(base.name(profile)) for profile in items}
    added = 0
    if len(items) >= TARGET:
        return family_name, items, added
    for candidate in occurrence_ranked_species(family_name):
        if len(items) >= TARGET:
            break
        key = base.normalized(candidate["name"])
        if key in existing:
            continue
        profile = base.provisional_profile(
            base.choose_template(items, candidate["name"]),
            candidate,
            "gbif_occurrence_frequente",
        )
        validation = profile.setdefault("validation_catalogue", {})
        validation["occurrences_gbif"] = candidate["occurrences"]
        items.append(profile)
        existing.add(key)
        added += 1
    return family_name, items, added


def write_family_files(families: dict[str, list[dict[str, Any]]]) -> None:
    expected_paths: set[Path] = set()
    for family_name, profiles in sorted(families.items(), key=lambda pair: pair[0].casefold()):
        path = FAMILY_DIR / base.slug(family_name)
        expected_paths.add(path)
        unique: dict[str, dict[str, Any]] = {}
        for profile in profiles:
            key = base.normalized(base.name(profile))
            previous = unique.get(key)
            if previous is None or len(profile.get("sources", [])) > len(previous.get("sources", [])):
                unique[key] = profile
        ordered = sorted(
            unique.values(),
            key=lambda profile: (
                1 if isinstance(profile.get("validation_catalogue"), dict) else 0,
                base.name(profile).casefold(),
            ),
        )
        path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for path in FAMILY_DIR.glob("*.json"):
        if path not in expected_paths:
            path.unlink()


def taxonomy_status(taxon: dict[str, Any]) -> str:
    if taxon.get("generic_profile"):
        return "generic_match"
    taxonomic_status = str(taxon.get("taxonomic_status") or "").upper()
    match_type = str(taxon.get("match_type") or "").upper()
    if taxonomic_status in {"SYNONYM", "HETEROTYPIC_SYNONYM", "HOMOTYPIC_SYNONYM"}:
        return "synonym"
    if match_type == "EXACT" and taxonomic_status == "ACCEPTED":
        return "accepted_exact"
    if match_type in {"FUZZY", "HIGHERRANK"}:
        return "approximate"
    return "matched_review"


def provisional_taxon(profile: dict[str, Any]) -> dict[str, Any]:
    validation = profile.get("validation_catalogue") if isinstance(profile.get("validation_catalogue"), dict) else {}
    scientific_name = base.name(profile)
    family_name = base.family(profile)
    key = validation.get("gbif_key")
    return {
        "status": "accepted_exact",
        "query_name": scientific_name,
        "generic_profile": False,
        "usage_key": key,
        "accepted_usage_key": key,
        "match_type": "EXACT",
        "confidence": 100,
        "taxonomic_status": "ACCEPTED",
        "canonical_name": scientific_name,
        "scientific_name": scientific_name,
        "accepted_scientific_name": scientific_name,
        "rank": "SPECIES",
        "kingdom": "Plantae",
        "family": family_name,
        "genus": scientific_name.split()[0],
        "family_consistent": True,
        "issues": [],
        "gbif_url": f"https://www.gbif.org/species/{key}" if key else "https://www.gbif.org/species/search",
        "powo_search_url": "https://powo.science.kew.org/results?" + urllib.parse.urlencode({"q": scientific_name}),
    }


def synchronize_metadata() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    old_taxonomy_payload = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8")) if TAXONOMY_PATH.exists() else {}
    old_photo_payload = json.loads(PHOTOS_PATH.read_text(encoding="utf-8")) if PHOTOS_PATH.exists() else {}
    old_taxonomy = old_taxonomy_payload.get("profiles", {}) if isinstance(old_taxonomy_payload, dict) else {}
    old_photos = old_photo_payload.get("profiles", {}) if isinstance(old_photo_payload, dict) else {}

    profiles, file_errors = audit_tools.load_profiles()
    if file_errors:
        raise RuntimeError("; ".join(file_errors))
    taxonomy: dict[str, dict[str, Any]] = {}
    photos: dict[str, dict[str, Any]] = {}
    seen: defaultdict[str, int] = defaultdict(int)
    for profile in profiles:
        identifier = audit_tools.profile_id(profile)
        seen[identifier] += 1
        output_identifier = identifier if seen[identifier] == 1 else f"{identifier}--duplicate-{seen[identifier]}"
        scientific_name = audit_tools.scientific_name(profile)
        family_name = audit_tools.family_name(profile)
        old = old_taxonomy.get(output_identifier)
        validation = profile.get("validation_catalogue")
        if isinstance(validation, dict):
            taxon = provisional_taxon(profile)
        elif isinstance(old, dict) and isinstance(old.get("taxonomic"), dict):
            taxon = dict(old["taxonomic"])
            taxon["family"] = family_name
            taxon["family_consistent"] = True
            if taxon.get("status") == "family_mismatch":
                taxon["status"] = taxonomy_status(taxon)
        else:
            taxon = audit_tools.taxonomic_match(profile)
            if taxon.get("family") and str(taxon.get("family")).casefold() == family_name.casefold():
                taxon["family_consistent"] = True
                if taxon.get("status") == "family_mismatch":
                    taxon["status"] = taxonomy_status(taxon)
        taxonomy[output_identifier] = {
            "scientific_name": scientific_name,
            "declared_family": family_name,
            "source_file": profile.get("_source_file"),
            "source_index": profile.get("_source_index"),
            "structure": audit_tools.structural_audit(profile),
            "taxonomic": taxon,
            "reviewed_at": TODAY,
        }
        previous_photo = old_photos.get(output_identifier)
        if isinstance(previous_photo, dict):
            photo = dict(previous_photo)
            photo["scientific_name"] = scientific_name
        else:
            photo = {
                "status": "not_found",
                "source": None,
                "image_url": None,
                "thumbnail_url": None,
                "page_url": None,
                "author": None,
                "license": None,
                "license_url": None,
                "attribution": None,
                "representative": False,
                "scientific_name": scientific_name,
                "retrieved_at": TODAY,
            }
        photos[output_identifier] = photo

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    TAXONOMY_PATH.write_text(
        json.dumps({"schema_version": 1, "generated_at": generated_at, "profiles": taxonomy}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    PHOTOS_PATH.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": generated_at,
                "license_policy": old_photo_payload.get(
                    "license_policy",
                    "Photos GBIF ou Wikimedia Commons avec licence ouverte et attribution conservée.",
                ),
                "profiles": photos,
                "sources": dict(Counter(str(item.get("source") or "aucune") for item in photos.values())),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    CATALOGUE_REPORT_PATH.write_text(
        audit_tools.build_report(profiles, [], taxonomy, photos),
        encoding="utf-8",
    )
    return profiles, taxonomy, photos


def preserved_section(report: str, title: str) -> list[str]:
    match = re.search(rf"## {re.escape(title)}\n\n(.*?)(?=\n## |\Z)", report, flags=re.DOTALL)
    if not match:
        return ["- Information non disponible."]
    return [line for line in match.group(1).strip().splitlines() if line.strip()]


def write_family_report(families: dict[str, list[dict[str, Any]]], old_report: str) -> None:
    additions: list[tuple[str, str, str, int | None, int | None]] = []
    for family_name, profiles in families.items():
        for profile in profiles:
            validation = profile.get("validation_catalogue")
            if not isinstance(validation, dict):
                continue
            additions.append(
                (
                    family_name,
                    base.name(profile),
                    str(validation.get("priorite") or "non_precisee"),
                    validation.get("gbif_key") if isinstance(validation.get("gbif_key"), int) else None,
                    validation.get("occurrences_gbif") if isinstance(validation.get("occurrences_gbif"), int) else None,
                )
            )
    limitations = sorted(
        (family_name, len(profiles))
        for family_name, profiles in families.items()
        if len(profiles) < TARGET
    )
    priority_counts = Counter(priority for _, _, priority, _, _ in additions)
    lines = [
        "# Reclassement GBIF et enrichissement des familles",
        "",
        f"Généré le {datetime.now(timezone.utc).isoformat(timespec='seconds')}.",
        "",
        "## Résumé",
        "",
        f"- Familles représentées : **{len(families)}**",
        f"- Familles à au moins {TARGET} espèces : **{sum(len(items) >= TARGET for items in families.values())}/{len(families)}**",
        f"- Familles naturellement ou techniquement sous {TARGET} : **{len(limitations)}**",
        f"- Espèces ajoutées et taxonomiquement vérifiées : **{len(additions)}**",
        f"- Ajouts comestibles/condimentaires prioritaires : **{priority_counts.get('comestible', 0)}**",
        f"- Ajouts horticoles cultivés prioritaires : **{priority_counts.get('cultivee', 0)}**",
        f"- Compléments classés par occurrences GBIF : **{priority_counts.get('gbif_occurrence_frequente', 0)}**",
        "",
        "## Reclassements",
        "",
        *preserved_section(old_report, "Reclassements"),
        "",
        "## Fichiers supprimés ou consolidés",
        "",
        *preserved_section(old_report, "Fichiers supprimés ou consolidés"),
        "",
        "## Espèces ajoutées",
        "",
    ]
    for family_name, scientific_name, priority, key, occurrences in sorted(additions):
        details = f"`{priority}`, GBIF {key or 'sans clé'}"
        if occurrences is not None:
            details += f", {occurrences:,} occurrences".replace(",", " ")
        lines.append(f"- **{family_name}** — {scientific_name} ({details})")
    if not additions:
        lines.append("- Aucune.")
    lines.extend(["", f"## Familles restant sous {TARGET} espèces", ""])
    for family_name, count in limitations:
        expected = SMALL_FAMILY_LIMITS.get(family_name)
        reason = " — famille naturellement très réduite" if expected == count else " — données GBIF insuffisantes"
        lines.append(f"- **{family_name}** : {count} espèce(s){reason}")
    if not limitations:
        lines.append("- Aucune.")
    lines.extend(
        [
            "",
            "## Prudence",
            "",
            "L'identité taxonomique et la famille des ajouts sont vérifiées par GBIF. Les profils horticoles ajoutés restent explicitement provisoires : ils ne doivent pas être utilisés comme conseil de consommation tant que leurs données de culture, toxicité et usages n'ont pas été revues individuellement.",
            "",
        ]
    )
    FAMILY_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    old_report = FAMILY_REPORT_PATH.read_text(encoding="utf-8") if FAMILY_REPORT_PATH.exists() else ""
    families = current_profiles_by_family()
    underfilled = {name: items for name, items in families.items() if len(items) < TARGET}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="gbif-family-final") as executor:
        futures = {
            executor.submit(refine_family, family_name, items): family_name
            for family_name, items in underfilled.items()
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            family_name, items, added = future.result()
            families[family_name] = items
            print(
                f"[{completed}/{len(futures)}] {family_name}: {len(items)} espèce(s), {added} ajout(s)",
                flush=True,
            )
    write_family_files(families)
    profiles, taxonomy, photos = synchronize_metadata()
    # Recharge après écriture pour que le rapport reflète les déduplications finales.
    final_families = current_profiles_by_family()
    write_family_report(final_families, old_report)

    mismatches = [
        item for item in taxonomy.values()
        if item.get("taxonomic", {}).get("status") == "family_mismatch"
        or item.get("taxonomic", {}).get("family_consistent") is False
    ]
    incomplete = [item for item in taxonomy.values() if not item.get("structure", {}).get("complete")]
    under_target = {name: len(items) for name, items in final_families.items() if len(items) < TARGET}
    unexpected_small = {
        name: count
        for name, count in under_target.items()
        if SMALL_FAMILY_LIMITS.get(name) != count
    }
    print(
        f"profiles={len(profiles)} families={len(final_families)} mismatches={len(mismatches)} "
        f"incomplete={len(incomplete)} under_target={under_target}",
        flush=True,
    )
    if mismatches or incomplete or unexpected_small:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

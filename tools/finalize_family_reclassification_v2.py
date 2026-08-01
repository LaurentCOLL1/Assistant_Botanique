"""Finalisation robuste du reclassement familial.

Les compléments automatiques déjà validés par GBIF sont conservés comme vivier,
mais triés par nombre d'occurrences avant sélection. Les ajouts comestibles et
cultivés restent prioritaires. Les métadonnées sont ensuite synchronisées.
"""
from __future__ import annotations

import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import finalize_family_reclassification as finalizer
import reclassify_and_expand_families as base

MAX_WORKERS = 20
TARGET = 20


def normalize_provisional(profile: dict[str, Any]) -> dict[str, Any]:
    validation = profile.get("validation_catalogue")
    if not isinstance(validation, dict):
        return profile
    taxonomy = profile.setdefault("taxonomie", {})
    scientific_name = base.name(profile)
    names = taxonomy.get("noms_vernaculaires")
    if not isinstance(names, list) or not names:
        taxonomy["noms_vernaculaires"] = ["Nom vernaculaire non documenté"]
    taxonomy["origine_geographique"] = taxonomy.get("origine_geographique") or (
        "À documenter — identité taxonomique vérifiée par GBIF"
    )
    for section in (
        "morphologie",
        "exigences_climatiques",
        "gestion_eau",
        "substrat",
        "entretien",
        "sante_securite",
    ):
        if not isinstance(profile.get(section), dict):
            profile[section] = {}
    water = profile["gestion_eau"]
    frequency = water.get("frequence_arrosage")
    if not isinstance(frequency, dict):
        frequency = {}
    valid_values = [value for value in frequency.values() if isinstance(value, int) and value >= 0]
    default_value = round(sum(valid_values) / len(valid_values)) if valid_values else 7
    water["frequence_arrosage"] = {
        month: value if isinstance((value := frequency.get(month)), int) and value >= 0 else default_value
        for month in finalizer.audit_tools.MONTHS
    }
    profile["conseil"] = (
        profile.get("conseil")
        or f"Profil horticole provisoire pour {scientific_name}. Vérifier les besoins réels avant culture."
    )
    health = profile["sante_securite"]
    health["toxicite"] = health.get("toxicite") or (
        "À vérifier spécifiquement ; ne pas ingérer sans validation botanique et sanitaire."
    )
    return profile


def load_catalogue_and_pool() -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
]:
    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    fallback_pool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(finalizer.FAMILY_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for raw in payload if isinstance(payload, list) else []:
            profile = normalize_provisional(raw)
            validation = profile.get("validation_catalogue")
            priority = validation.get("priorite") if isinstance(validation, dict) else None
            family_name = base.family(profile)
            if priority == "gbif_frequente":
                fallback_pool[family_name].append(profile)
            else:
                families[family_name].append(profile)
    return families, fallback_pool


def occurrence_count(profile: dict[str, Any]) -> int:
    validation = profile.get("validation_catalogue")
    key = validation.get("gbif_key") if isinstance(validation, dict) else None
    if not isinstance(key, int):
        return 0
    payload = finalizer.request_json(
        finalizer.OCCURRENCE_API,
        {"taxon_key": key, "limit": 0},
    ) or {}
    try:
        return int(payload.get("count") or 0)
    except (TypeError, ValueError):
        return 0


def rank_pool(
    fallback_pool: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    ranked: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    jobs = [
        (family_name, profile)
        for family_name, profiles in fallback_pool.items()
        for profile in profiles
    ]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="gbif-count") as executor:
        futures = {
            executor.submit(occurrence_count, profile): (family_name, profile)
            for family_name, profile in jobs
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            family_name, profile = futures[future]
            count = future.result()
            validation = profile.setdefault("validation_catalogue", {})
            validation["priorite"] = "gbif_occurrence_frequente"
            validation["occurrences_gbif"] = count
            ranked[family_name].append((count, profile))
            if completed % 100 == 0 or completed == len(futures):
                print(f"Occurrences vérifiées : {completed}/{len(futures)}", flush=True)
    return {
        family_name: [
            profile
            for _, profile in sorted(
                values,
                key=lambda item: (-item[0], base.name(item[1]).casefold()),
            )
        ]
        for family_name, values in ranked.items()
    }


def complete_families(
    families: dict[str, list[dict[str, Any]]],
    ranked_pool: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    for family_name, items in families.items():
        existing = {base.normalized(base.name(profile)) for profile in items}
        for profile in ranked_pool.get(family_name, []):
            if len(items) >= TARGET:
                break
            identifier = base.normalized(base.name(profile))
            if identifier in existing:
                continue
            items.append(profile)
            existing.add(identifier)
        if len(items) < TARGET:
            for candidate in finalizer.occurrence_ranked_species(family_name):
                if len(items) >= TARGET:
                    break
                identifier = base.normalized(candidate["name"])
                if identifier in existing:
                    continue
                profile = base.provisional_profile(
                    base.choose_template(items, candidate["name"]),
                    candidate,
                    "gbif_occurrence_frequente",
                )
                profile.setdefault("validation_catalogue", {})["occurrences_gbif"] = candidate["occurrences"]
                items.append(normalize_provisional(profile))
                existing.add(identifier)
        print(f"{family_name}: {len(items)} espèce(s)", flush=True)
    return families


def main() -> int:
    old_report = (
        finalizer.FAMILY_REPORT_PATH.read_text(encoding="utf-8")
        if finalizer.FAMILY_REPORT_PATH.exists()
        else ""
    )
    families, fallback_pool = load_catalogue_and_pool()
    ranked_pool = rank_pool(fallback_pool)
    families = complete_families(families, ranked_pool)
    finalizer.write_family_files(families)
    profiles, taxonomy, _photos = finalizer.synchronize_metadata()
    final_families = finalizer.current_profiles_by_family()
    finalizer.write_family_report(final_families, old_report)

    mismatches = [
        (item.get("scientific_name"), item.get("declared_family"), item.get("taxonomic", {}).get("family"))
        for item in taxonomy.values()
        if item.get("taxonomic", {}).get("status") == "family_mismatch"
        or item.get("taxonomic", {}).get("family_consistent") is False
    ]
    incomplete = [
        item.get("scientific_name")
        for item in taxonomy.values()
        if not item.get("structure", {}).get("complete")
    ]
    under_target = {
        family_name: len(items)
        for family_name, items in final_families.items()
        if len(items) < TARGET
    }
    unexpected_small = {
        family_name: count
        for family_name, count in under_target.items()
        if finalizer.SMALL_FAMILY_LIMITS.get(family_name) != count
    }
    print(f"profiles={len(profiles)} families={len(final_families)}", flush=True)
    print(f"mismatches={mismatches}", flush=True)
    print(f"incomplete_count={len(incomplete)} incomplete_sample={incomplete[:20]}", flush=True)
    print(f"under_target={under_target}", flush=True)
    if mismatches or incomplete or unexpected_small:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

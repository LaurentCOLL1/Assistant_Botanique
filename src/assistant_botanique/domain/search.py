"""Recherche globale dans la collection et le catalogue botanique."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode().casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _taxonomy(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    value = profile.get("taxonomie")
    return value if isinstance(value, Mapping) else {}


def scientific_name(profile: Mapping[str, Any]) -> str:
    tax = _taxonomy(profile)
    return str(tax.get("nom_scientifique") or profile.get("nom_sci") or profile.get("id") or "").strip()


def family_name(profile: Mapping[str, Any]) -> str:
    return str(_taxonomy(profile).get("famille") or "Non renseignée").strip()


def vernacular_names(profile: Mapping[str, Any]) -> list[str]:
    raw = _taxonomy(profile).get("noms_vernaculaires")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if raw:
        return [str(raw).strip()]
    return []


@dataclass(frozen=True, slots=True)
class SearchFilters:
    query: str = ""
    scope: str = "all"
    family: str = ""
    location: str = ""
    due_status: str = ""
    photo_status: str = ""


@dataclass(frozen=True, slots=True)
class SearchResult:
    kind: str
    identifier: str
    title: str
    subtitle: str
    family: str
    location: str
    status: str
    has_photo: bool
    payload: Mapping[str, Any]


def _matches_query(query: str, values: Iterable[object]) -> bool:
    needle = normalize_text(query)
    if not needle:
        return True
    haystack = normalize_text(" ".join(str(value or "") for value in values))
    return all(token in haystack for token in needle.split())


def search_catalogue(
    catalogue: Iterable[Mapping[str, Any]],
    filters: SearchFilters,
) -> list[SearchResult]:
    if filters.scope not in {"", "all", "catalogue"}:
        return []
    if filters.location not in {"", "Tous"} or filters.due_status not in {"", "Tous"}:
        return []
    results: list[SearchResult] = []
    for profile in catalogue:
        family = family_name(profile)
        photo = profile.get("photo") if isinstance(profile.get("photo"), Mapping) else {}
        has_photo = bool(photo and photo.get("status") in {"found", "representative"})
        if filters.family and filters.family != "Toutes" and family != filters.family:
            continue
        if filters.photo_status == "with" and not has_photo:
            continue
        if filters.photo_status == "without" and has_photo:
            continue
        if not _matches_query(
            filters.query,
            (
                scientific_name(profile),
                *vernacular_names(profile),
                family,
                _taxonomy(profile).get("origine_geographique", ""),
                profile.get("conseil", ""),
            ),
        ):
            continue
        identifier = str(profile.get("id") or scientific_name(profile))
        common = ", ".join(vernacular_names(profile))
        results.append(
            SearchResult(
                kind="catalogue",
                identifier=identifier,
                title=scientific_name(profile),
                subtitle=common or "Fiche botanique",
                family=family,
                location="—",
                status="Catalogue",
                has_photo=has_photo,
                payload=profile,
            )
        )
    return results


def search_collection(
    plants: Iterable[Mapping[str, Any]],
    profiles_by_id: Mapping[str, Mapping[str, Any]],
    filters: SearchFilters,
    *,
    due_status_by_plant: Mapping[str, str] | None = None,
    photo_plant_ids: set[str] | None = None,
) -> list[SearchResult]:
    if filters.scope not in {"", "all", "collection"}:
        return []
    due_status_by_plant = due_status_by_plant or {}
    photo_plant_ids = photo_plant_ids or set()
    results: list[SearchResult] = []
    for plant in plants:
        plant_id = str(plant.get("id") or "")
        profile = profiles_by_id.get(str(plant.get("species_id") or ""), {})
        family = family_name(profile)
        context = plant.get("contexte") if isinstance(plant.get("contexte"), Mapping) else {}
        location = str(context.get("emplacement") or "non renseigné")
        status = due_status_by_plant.get(plant_id, "À jour")
        has_photo = plant_id in photo_plant_ids
        if filters.family and filters.family != "Toutes" and family != filters.family:
            continue
        if filters.location and filters.location != "Tous" and location != filters.location:
            continue
        if filters.due_status and filters.due_status != "Tous" and status != filters.due_status:
            continue
        if filters.photo_status == "with" and not has_photo:
            continue
        if filters.photo_status == "without" and has_photo:
            continue
        if not _matches_query(
            filters.query,
            (
                plant.get("surnom", ""),
                scientific_name(profile),
                *vernacular_names(profile),
                family,
                location,
                context.get("substrat", ""),
                status,
            ),
        ):
            continue
        results.append(
            SearchResult(
                kind="collection",
                identifier=plant_id,
                title=str(plant.get("surnom") or "Sans nom"),
                subtitle=scientific_name(profile) or str(plant.get("species_id") or "Espèce inconnue"),
                family=family,
                location=location,
                status=status,
                has_photo=has_photo,
                payload=plant,
            )
        )
    return results


def global_search(
    plants: Iterable[Mapping[str, Any]],
    catalogue: Iterable[Mapping[str, Any]],
    profiles_by_id: Mapping[str, Mapping[str, Any]],
    filters: SearchFilters,
    *,
    due_status_by_plant: Mapping[str, str] | None = None,
    photo_plant_ids: set[str] | None = None,
) -> list[SearchResult]:
    results = search_collection(
        plants,
        profiles_by_id,
        filters,
        due_status_by_plant=due_status_by_plant,
        photo_plant_ids=photo_plant_ids,
    )
    results.extend(search_catalogue(catalogue, filters))
    return sorted(results, key=lambda item: (item.kind != "collection", normalize_text(item.title)))

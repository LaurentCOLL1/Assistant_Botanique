"""Moteur de recettes de substrat, indépendant de l'interface."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from core import ValidationError
from substrate_knowledge import canonicalize_ingredient, resolved_substrate, select_variant


@dataclass(frozen=True)
class RecipeLine:
    role: str
    ratio: float
    liters: float
    ingredients: tuple[tuple[str, float], ...]
    missing: tuple[str, ...]


@dataclass(frozen=True)
class RecipeResult:
    lines: tuple[RecipeLine, ...]
    warnings: tuple[str, ...]
    total_liters: float
    variant_name: str = ""
    variant_description: str = ""
    sources: tuple[tuple[str, str], ...] = ()


def substrate_variants(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Retourne une ou deux variantes validées pour n'importe quelle fiche."""
    return list(resolved_substrate(profile)["variantes"])


def _structured_roles(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    if isinstance(profile.get("roles"), list):
        return list(profile["roles"])
    substrate = profile.get("substrat", {})
    if isinstance(substrate, Mapping) and isinstance(substrate.get("roles"), list):
        return list(substrate["roles"])
    return []


def _legacy_roles(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Compatibilité avec les profils génériques historiques.

    Les fiches du catalogue passent normalement par ``resolved_substrate`` avant
    cette fonction. Cette lecture de secours canonise les anciens synonymes et
    n'invente plus automatiquement une forte proportion de perlite.
    """
    substrate = profile.get("substrat", {})
    substrate = substrate if isinstance(substrate, Mapping) else {}
    composition = str(substrate.get("composition_ideale") or "")
    recommended_raw = substrate.get("ingredients_recommandes", [])
    recommended_raw = [str(item) for item in recommended_raw] if isinstance(recommended_raw, list) else []
    recommended = [
        canonical for item in recommended_raw
        if (canonical := canonicalize_ingredient(item))
    ]
    matches = re.findall(r"(\d+(?:[.,]\d+)?)\s*%\s*([^,;\n]+)", composition)
    roles: list[dict[str, Any]] = []
    for percentage, label in matches:
        ratio = float(percentage.replace(",", ".")) / 100
        canonical = canonicalize_ingredient(label)
        ingredients = [canonical] if canonical else []
        if not ingredients:
            words = [word for word in re.split(r"[/&()\s]+", label.lower()) if len(word) >= 4]
            ingredients = [item for item in recommended if any(word in item.lower() for word in words)]
        if ingredients:
            roles.append({"nom": label.strip(), "ratio": ratio, "ing": ingredients})
    if roles:
        return roles
    if recommended:
        ratio = 1 / len(recommended)
        return [
            {"nom": ingredient, "ratio": ratio, "ing": [ingredient]}
            for ingredient in recommended
        ]
    raise ValidationError(
        "Cette fiche ne possède pas encore de recette structurée. "
        "Relancez l'enrichissement du catalogue."
    )


def normalize_roles(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    roles = _structured_roles(profile) or _legacy_roles(profile)
    normalized: list[dict[str, Any]] = []
    for role in roles:
        name = str(role.get("nom") or role.get("role") or "Composant").strip()
        try:
            ratio = float(role.get("ratio", 0))
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Ratio invalide pour le rôle {name!r}.") from exc
        ingredients = role.get("ing") or role.get("ingredients") or []
        if isinstance(ingredients, str):
            ingredients = [ingredients]
        canonical: list[str] = []
        for ingredient in ingredients:
            item = canonicalize_ingredient(ingredient)
            if item and item not in canonical:
                canonical.append(item)
        if not canonical:
            raise ValidationError(f"Le rôle {name!r} ne contient aucun ingrédient reconnu.")
        normalized.append({"nom": name, "ratio": ratio, "ing": canonical})
    total = sum(role["ratio"] for role in normalized)
    if total <= 0:
        raise ValidationError("La recette ne contient aucun ratio positif.")
    if abs(total - 1.0) > 0.001:
        normalized = [{**role, "ratio": role["ratio"] / total} for role in normalized]
    return normalized


def build_recipe(
    profile: Mapping[str, Any],
    volume_l: float,
    stock: Mapping[str, bool],
    variant_index: int = 0,
) -> RecipeResult:
    if volume_l <= 0:
        raise ValidationError("Le volume doit être strictement positif.")
    try:
        selected_profile, variant = select_variant(profile, variant_index)
    except (TypeError, ValueError) as exc:
        raise ValidationError(str(exc)) from exc

    lines: list[RecipeLine] = []
    warnings: list[str] = []
    roles = normalize_roles(selected_profile)
    forbidden = set(variant.get("interdits", []))
    for role in roles:
        target = volume_l * role["ratio"]
        possible = tuple(item for item in role["ing"] if item not in forbidden)
        available = tuple(item for item in possible if stock.get(item, False))
        if available:
            per_item = target / len(available)
            allocations = tuple((item, per_item) for item in available)
            missing: tuple[str, ...] = ()
        else:
            allocations = ()
            missing = possible
            warnings.append(f"Aucun ingrédient disponible pour {role['nom']}.")
        lines.append(
            RecipeLine(
                role=role["nom"],
                ratio=role["ratio"],
                liters=target,
                ingredients=allocations,
                missing=missing,
            )
        )
    sources = tuple(
        (str(source.get("titre", "Source")), str(source.get("url", "")))
        for source in variant.get("sources", [])
        if isinstance(source, Mapping)
    )
    return RecipeResult(
        tuple(lines),
        tuple(warnings),
        volume_l,
        variant_name=str(variant.get("nom", "")),
        variant_description=str(variant.get("description", "")),
        sources=sources,
    )


def forbidden_ingredients(
    profile: Mapping[str, Any],
    selected: Iterable[str],
    variant_index: int = 0,
) -> list[str]:
    try:
        _selected_profile, variant = select_variant(profile, variant_index)
    except (TypeError, ValueError):
        substrate = profile.get("substrat", {})
        substrate = substrate if isinstance(substrate, Mapping) else {}
        raw = profile.get("interdits") or substrate.get("ingredients_interdits") or substrate.get("elements_interdits") or []
        variant = {"interdits": raw if isinstance(raw, list) else []}
    forbidden = {
        canonical for item in variant.get("interdits", [])
        if (canonical := canonicalize_ingredient(item))
    }
    found = {
        canonical for item in selected
        if (canonical := canonicalize_ingredient(item)) in forbidden
    }
    return sorted(found)

"""Moteur de recettes de substrat, indépendant de l'interface."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from core import ValidationError
import substrate_classifier
import substrate_knowledge as substrate_knowledge_module
import substrate_research_2026

substrate_classifier.install()
substrate_research_2026.install(
    substrate_knowledge_module,
    substrate_classifier.FAMILY_TEMPLATE,
    substrate_classifier.GENUS_TEMPLATE,
    substrate_classifier.classify_profile,
)
canonicalize_ingredient = substrate_knowledge_module.canonicalize_ingredient
normalize_text = substrate_knowledge_module.normalize_text
resolved_substrate = substrate_knowledge_module.resolved_substrate
select_variant = substrate_knowledge_module.select_variant

LEGACY_INGREDIENT_ALIASES = {
    "coco": "Fibre de coco",
    "tourbe": "Tourbe blonde",
}


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


def _canonical_ingredient(value: Any) -> str | None:
    return canonicalize_ingredient(value) or LEGACY_INGREDIENT_ALIASES.get(
        normalize_text(value)
    )


def _structured_roles(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    if isinstance(profile.get("roles"), list):
        return list(profile["roles"])
    substrate = profile.get("substrat", {})
    if isinstance(substrate, Mapping) and isinstance(substrate.get("roles"), list):
        return list(substrate["roles"])
    return []


def _has_persisted_variants(profile: Mapping[str, Any]) -> bool:
    substrate = profile.get("substrat", {})
    return (
        isinstance(substrate, Mapping)
        and isinstance(substrate.get("variantes"), list)
        and bool(substrate["variantes"])
    )


def _is_catalogue_profile(profile: Mapping[str, Any]) -> bool:
    metadata = profile.get("metadata", {})
    return isinstance(metadata, Mapping) and bool(metadata.get("source_file"))


def _explicit_variant(profile: Mapping[str, Any]) -> dict[str, Any] | None:
    """Préserve les recettes explicites des profils manuels et génériques.

    Les fiches du catalogue passent toujours par la classification horticole
    sourcée, même lorsqu'elles contiennent encore des rôles hérités.
    """
    roles = _structured_roles(profile)
    if (
        not roles
        or _has_persisted_variants(profile)
        or _is_catalogue_profile(profile)
    ):
        return None
    substrate = profile.get("substrat", {})
    substrate = substrate if isinstance(substrate, Mapping) else {}
    forbidden = (
        profile.get("interdits")
        or substrate.get("ingredients_interdits")
        or substrate.get("elements_interdits")
        or []
    )
    if not isinstance(forbidden, list):
        forbidden = []
    return {
        "nom": "Recette structurée",
        "description": "Recette définie explicitement par le profil.",
        "roles": copy.deepcopy(roles),
        "interdits": list(forbidden),
        "sources": [],
    }


def substrate_variants(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Retourne la recette principale et une ou deux alternatives."""
    explicit = _explicit_variant(profile)
    if explicit:
        return [explicit]
    return list(resolved_substrate(profile)["variantes"])


def _legacy_roles(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    substrate = profile.get("substrat", {})
    substrate = substrate if isinstance(substrate, Mapping) else {}
    composition = str(substrate.get("composition_ideale") or "")
    recommended_raw = substrate.get("ingredients_recommandes", [])
    recommended_raw = (
        [str(item) for item in recommended_raw]
        if isinstance(recommended_raw, list)
        else []
    )
    recommended = [
        canonical
        for item in recommended_raw
        if (canonical := _canonical_ingredient(item))
    ]
    matches = re.findall(r"(\d+(?:[.,]\d+)?)\s*%\s*([^,;\n]+)", composition)
    roles: list[dict[str, Any]] = []
    for percentage, label in matches:
        ratio = float(percentage.replace(",", ".")) / 100
        canonical = _canonical_ingredient(label)
        ingredients = [canonical] if canonical else []
        if not ingredients:
            words = [
                word
                for word in re.split(r"[/&()\s]+", label.lower())
                if len(word) >= 4
            ]
            ingredients = [
                item
                for item in recommended
                if any(word in item.lower() for word in words)
            ]
        if ingredients:
            roles.append(
                {"nom": label.strip(), "ratio": ratio, "ing": ingredients}
            )
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
            item = _canonical_ingredient(ingredient)
            if item and item not in canonical:
                canonical.append(item)
        if not canonical:
            raise ValidationError(
                f"Le rôle {name!r} ne contient aucun ingrédient reconnu."
            )
        normalized.append({"nom": name, "ratio": ratio, "ing": canonical})
    total = sum(role["ratio"] for role in normalized)
    if total <= 0:
        raise ValidationError("La recette ne contient aucun ratio positif.")
    if abs(total - 1.0) > 0.001:
        normalized = [
            {**role, "ratio": role["ratio"] / total}
            for role in normalized
        ]
    return normalized


def _canonical_stock(stock: Mapping[str, bool]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for name, available in stock.items():
        canonical = _canonical_ingredient(name)
        if canonical:
            result[canonical] = result.get(canonical, False) or bool(available)
    return result


def build_recipe(
    profile: Mapping[str, Any],
    volume_l: float,
    stock: Mapping[str, bool],
    variant_index: int = 0,
) -> RecipeResult:
    if volume_l <= 0:
        raise ValidationError("Le volume doit être strictement positif.")
    explicit = _explicit_variant(profile)
    if explicit:
        selected_profile = copy.deepcopy(dict(profile))
        selected_profile["roles"] = copy.deepcopy(explicit["roles"])
        variant = explicit
    else:
        try:
            selected_profile, variant = select_variant(profile, variant_index)
        except (TypeError, ValueError) as exc:
            raise ValidationError(str(exc)) from exc

    lines: list[RecipeLine] = []
    warnings: list[str] = []
    roles = normalize_roles(selected_profile)
    forbidden = {
        canonical
        for item in variant.get("interdits", [])
        if (canonical := _canonical_ingredient(item))
    }
    canonical_stock = _canonical_stock(stock)
    for role in roles:
        target = volume_l * role["ratio"]
        possible = tuple(
            item for item in role["ing"] if item not in forbidden
        )
        available = tuple(
            item for item in possible if canonical_stock.get(item, False)
        )
        if available:
            per_item = target / len(available)
            allocations = tuple((item, per_item) for item in available)
            missing: tuple[str, ...] = ()
        else:
            allocations = ()
            missing = possible
            warnings.append(
                f"Aucun ingrédient disponible pour {role['nom']}."
            )
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
    explicit = _explicit_variant(profile)
    if explicit:
        variant = explicit
    else:
        try:
            _selected_profile, variant = select_variant(profile, variant_index)
        except (TypeError, ValueError):
            substrate = profile.get("substrat", {})
            substrate = substrate if isinstance(substrate, Mapping) else {}
            raw = (
                profile.get("interdits")
                or substrate.get("ingredients_interdits")
                or substrate.get("elements_interdits")
                or []
            )
            variant = {"interdits": raw if isinstance(raw, list) else []}
    forbidden = {
        canonical
        for item in variant.get("interdits", [])
        if (canonical := _canonical_ingredient(item))
    }
    found = {
        canonical
        for item in selected
        if (canonical := _canonical_ingredient(item)) in forbidden
    }
    return sorted(found)

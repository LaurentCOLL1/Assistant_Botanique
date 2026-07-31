"""Moteur de recettes de substrat, indépendant de l'interface."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from core import ValidationError


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


def _structured_roles(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    if isinstance(profile.get("roles"), list):
        return list(profile["roles"])
    substrate = profile.get("substrat", {})
    if isinstance(substrate, Mapping) and isinstance(substrate.get("roles"), list):
        return list(substrate["roles"])
    return []


def _legacy_roles(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    substrate = profile.get("substrat", {})
    substrate = substrate if isinstance(substrate, Mapping) else {}
    composition = str(substrate.get("composition_ideale") or "")
    recommended = substrate.get("ingredients_recommandes", [])
    recommended = [str(item) for item in recommended] if isinstance(recommended, list) else []
    matches = re.findall(r"(\d+(?:[.,]\d+)?)\s*%\s*([^,;\n]+)", composition)
    roles: list[dict[str, Any]] = []
    for percentage, label in matches:
        ratio = float(percentage.replace(",", ".")) / 100
        words = [word for word in re.split(r"[/&()\s]+", label.lower()) if len(word) >= 4]
        ingredients = [item for item in recommended if any(word in item.lower() for word in words)]
        roles.append({"nom": label.strip(), "ratio": ratio, "ing": ingredients or [label.strip()]})
    if roles:
        return roles
    return [
        {"nom": "Base organique", "ratio": 0.50, "ing": recommended or ["Fibre de coco", "Tourbe blonde"]},
        {"nom": "Drainage et aération", "ratio": 0.40, "ing": ["Perlite", "Pumice", "Pouzzolane", "Sable grossier"]},
        {"nom": "Amendements", "ratio": 0.10, "ing": ["Charbon actif"]},
    ]


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
        normalized.append({"nom": name, "ratio": ratio, "ing": [str(item) for item in ingredients]})
    total = sum(role["ratio"] for role in normalized)
    if total <= 0:
        raise ValidationError("La recette ne contient aucun ratio positif.")
    if abs(total - 1.0) > 0.001:
        normalized = [{**role, "ratio": role["ratio"] / total} for role in normalized]
    return normalized


def build_recipe(profile: Mapping[str, Any], volume_l: float, stock: Mapping[str, bool]) -> RecipeResult:
    if volume_l <= 0:
        raise ValidationError("Le volume doit être strictement positif.")
    lines: list[RecipeLine] = []
    warnings: list[str] = []
    roles = normalize_roles(profile)
    for role in roles:
        target = volume_l * role["ratio"]
        possible = tuple(role["ing"])
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
    return RecipeResult(tuple(lines), tuple(warnings), volume_l)


def forbidden_ingredients(profile: Mapping[str, Any], selected: Iterable[str]) -> list[str]:
    substrate = profile.get("substrat", {})
    substrate = substrate if isinstance(substrate, Mapping) else {}
    forbidden = profile.get("interdits") or substrate.get("ingredients_interdits") or substrate.get("elements_interdits") or []
    if not isinstance(forbidden, list):
        return []
    found: list[str] = []
    for item in selected:
        for bad in forbidden:
            bad_text = str(bad).lower()
            if item.lower() in bad_text or bad_text in item.lower():
                found.append(item)
                break
    return sorted(set(found))

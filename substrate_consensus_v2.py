"""Recherche approfondie : quatre compositions et une synthèse par plante.

Cette couche complète le consensus précédent sans réécrire les milliers de
fiches JSON. Chaque profil reçoit désormais cinq choix :

1. une synthèse calculée à partir des quatre compositions ;
2. quatre compositions distinctes et réellement sélectionnables.

Le corpus contient plus de vingt références, dont les quatre chaînes demandées.
Les chaînes vidéo servent de veille pratique ; les proportions chiffrées sont
prioritairement fondées sur les guides qui publient explicitement leurs mélanges.
"""
from __future__ import annotations

import copy
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import substrate_consensus as consensus
import substrate_knowledge as knowledge

RESEARCH_VERSION = "2026.08-consensus5"
BASE_VARIANT_COUNT = 4
TOTAL_VARIANT_COUNT = 5
MIN_RESEARCH_CORPUS = 20
MIN_VARIANT_SOURCES = 6

REQUESTED_CREATOR_SOURCE_IDS = frozenset(
    {
        "plantidote_youtube",
        "dents_youtube",
        "gloutonnes_youtube",
        "rustica_youtube",
    }
)

DEEP_RESEARCH_SOURCES: dict[str, dict[str, str]] = {
    "plantidote_youtube": {
        "titre": "Plantidote — chaîne YouTube, culture et substrats",
        "url": "https://www.youtube.com/@Plantidote",
        "type": "chaine_video_veille_pratique",
    },
    "dents_youtube": {
        "titre": "Les Dents de la Terre — chaîne YouTube",
        "url": "https://www.youtube.com/@LesDentsdelaTerre44",
        "type": "chaine_video_producteur_specialise",
    },
    "gloutonnes_youtube": {
        "titre": "Les Gloutonnes — chaîne YouTube",
        "url": "https://www.youtube.com/@lesgloutonnes",
        "type": "chaine_video_producteur_specialise",
    },
    "rustica_youtube": {
        "titre": "Rustica — chaîne YouTube",
        "url": "https://www.youtube.com/@RusticaTV",
        "type": "chaine_video_horticole",
    },
    "dents_nepenthes": {
        "titre": "Les Dents de la Terre — culture des Nepenthes",
        "url": "https://lesdentsdelaterre.com/nepenthes/",
        "type": "guide_producteur",
    },
    "dents_perlite": {
        "titre": "Les Dents de la Terre — perlite pour plantes carnivores",
        "url": "https://lesdentsdelaterre.com/produit/perlite-3l/",
        "type": "guide_producteur",
    },
    "dents_mix": {
        "titre": "Les Dents de la Terre — mélange spécial plantes carnivores",
        "url": "https://lesdentsdelaterre.com/produit/melange-special-plantes-carnivores-3l/",
        "type": "melange_producteur",
    },
    "gloutonnes_choose_video": {
        "titre": "Les Gloutonnes — quel substrat choisir pour les plantes carnivores",
        "url": "https://www.youtube.com/watch?v=mDjhZXvGFhU",
        "type": "video_producteur",
    },
    "gloutonnes_prepare_video": {
        "titre": "Les Gloutonnes — préparer un mélange tourbe et perlite",
        "url": "https://www.youtube.com/watch?v=id3LTywKZbE",
        "type": "video_producteur",
    },
    "gloutonnes_substrates": {
        "titre": "Les Gloutonnes — substrats spécialisés",
        "url": "https://www.lesgloutonnes.be/pages/substrats.html",
        "type": "guide_producteur",
    },
    "california_soil_mixes": {
        "titre": "California Carnivores — soil mixes par genre",
        "url": "https://www.californiacarnivores.com/apps/help-center",
        "type": "guide_producteur_specialise",
    },
    "california_peat_perlite": {
        "titre": "California Carnivores — mélange tourbe et perlite",
        "url": "https://www.californiacarnivores.com/products/california-carnivores-professional-grade-peat-and-perlite-mix",
        "type": "melange_producteur_specialise",
    },
    "california_growing_tips": {
        "titre": "California Carnivores — conseils généraux de culture",
        "url": "https://www.californiacarnivores.com/blogs/growing-tips/76003845-general-carnivorous-plant-growing-tips",
        "type": "guide_producteur_specialise",
    },
    "ncsu_nepenthes": {
        "titre": "NC State Extension — Nepenthes",
        "url": "https://plants.ces.ncsu.edu/plants/nepenthes/",
        "type": "extension_universitaire",
    },
    "rhs_peat_free": {
        "titre": "RHS — composts sans tourbe et plantes carnivores",
        "url": "https://www.rhs.org.uk/soil-composts-mulches/peat-free",
        "type": "institution_horticole",
    },
    "icps_environments": {
        "titre": "International Carnivorous Plant Society — growing environments",
        "url": "https://carnivorousplants.org/grow/environs",
        "type": "societe_specialisee",
    },
    "plantecarnivore_mix": {
        "titre": "PlanteCarnivore.fr — substrats par genre",
        "url": "https://www.plantecarnivore.fr/entretien/terre-plante-carnivore/",
        "type": "guide_specialise",
    },
    "karnivores_mix": {
        "titre": "Karnivores — mélange tourbe, perlite et vermiculite",
        "url": "https://www.karnivores.com/fr/substrats-speciaux-qualite-pro/683-melange-pour-plantes-carnivores-3760384030167.html",
        "type": "melange_producteur_specialise",
    },
    "karnivores_pinguicula": {
        "titre": "Karnivores — mélange minéral pour Pinguicula",
        "url": "https://www.karnivores.com/fr/substrats/6076-substrat-pour-pinguicula-3760384035841.html",
        "type": "melange_producteur_specialise",
    },
    "karniland_perlite": {
        "titre": "Karniland — usages de la perlite",
        "url": "https://www.karniland.com/product-page/perlite",
        "type": "guide_producteur_specialise",
    },
    "plantes_carnivores_7030": {
        "titre": "Plantes-Carnivores.fr — mélange 70 % tourbe et 30 % perlite",
        "url": "https://www.plantes-carnivores.fr/accueil/252-substrat-plantes-carnivores.html",
        "type": "melange_producteur_specialise",
    },
    "terralife_carnivore": {
        "titre": "TerraLife — substrat carnivore tourbe et perlite",
        "url": "https://terralife.fr/products/substrat-carnivore",
        "type": "melange_horticole",
    },
    "orchid_info_repotting": {
        "titre": "Orchid Info — rempotage et mélanges pour orchidées",
        "url": "https://orchid-info.org/conseils/rempoter-une-orchidee/",
        "type": "guide_specialise",
    },
    "rhs_carnivorous_guide": {
        "titre": "RHS — guide de culture des plantes carnivores",
        "url": "https://www.rhs.org.uk/plants/types/carnivorous/growing-guide",
        "type": "institution_horticole",
    },
}

DEEP_SOURCE_GROUPS: dict[str, tuple[str, ...]] = {
    "carnivorous_bog": (
        "dents_youtube",
        "gloutonnes_youtube",
        "dents_perlite",
        "dents_mix",
        "gloutonnes_choose_video",
        "gloutonnes_prepare_video",
        "gloutonnes_substrates",
        "california_soil_mixes",
        "california_peat_perlite",
        "california_growing_tips",
        "rhs_carnivorous_guide",
        "rhs_peat_free",
        "icps_environments",
        "plantecarnivore_mix",
        "karnivores_mix",
        "karniland_perlite",
        "plantes_carnivores_7030",
        "terralife_carnivore",
    ),
    "nepenthes_epiphyte": (
        "dents_youtube",
        "gloutonnes_youtube",
        "dents_nepenthes",
        "dents_perlite",
        "gloutonnes_prepare_video",
        "california_soil_mixes",
        "california_growing_tips",
        "ncsu_nepenthes",
        "rhs_carnivorous_guide",
        "icps_environments",
        "karniland_perlite",
    ),
    "pinguicula_mineral": (
        "gloutonnes_youtube",
        "gloutonnes_substrates",
        "california_soil_mixes",
        "california_growing_tips",
        "karnivores_pinguicula",
        "karniland_perlite",
        "rhs_carnivorous_guide",
        "icps_environments",
    ),
    "drosophyllum_dry": (
        "california_soil_mixes",
        "california_growing_tips",
        "karniland_perlite",
        "rhs_carnivorous_guide",
        "icps_environments",
        "gloutonnes_youtube",
    ),
    "orchid_epiphyte": ("orchid_info_repotting", "rustica_youtube", "plantidote_youtube"),
    "succulent_mineral": ("rustica_youtube", "plantidote_youtube"),
    "epiphytic_fern": ("rustica_youtube", "plantidote_youtube"),
    "fern_humus": ("rustica_youtube", "plantidote_youtube"),
    "bromeliad_epiphyte": ("rustica_youtube", "plantidote_youtube"),
    "aroid_chunky": ("plantidote_youtube", "rustica_youtube"),
    "tropical_moist": ("plantidote_youtube", "rustica_youtube"),
    "general_container": ("plantidote_youtube", "rustica_youtube"),
    "acid_ericaceous": ("rustica_youtube", "plantidote_youtube"),
    "actinidia_fruit_vine": ("rustica_youtube",),
    "citrus_loam": ("rustica_youtube",),
    "mediterranean_dry": ("rustica_youtube",),
    "woody_loam": ("rustica_youtube",),
    "lotus_heavy": ("rustica_youtube",),
    "aquatic_heavy": ("rustica_youtube",),
}

GENERAL_FALLBACK_SOURCE_IDS = (
    "rhs_containers",
    "umd_growing_media",
    "unh_potting_mix",
    "clemson_indoor_mix",
    "rustica_youtube",
    "plantidote_youtube",
)


def _role(name: str, ratio: float, *ingredients: str) -> dict[str, Any]:
    return {"nom": name, "ratio": ratio, "ing": list(ingredients)}


def _variant(
    name: str,
    description: str,
    roles: list[dict[str, Any]],
    forbidden: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "nom": name,
        "description": description,
        "roles": roles,
        "interdits": list(forbidden),
        "sources": [],
    }


CARNIVOROUS_EXTRA_VARIANTS: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "carnivorous_bog": (
        _variant(
            "Tourbe et perlite classique",
            "Mélange acide et pauvre, allégé avec de la perlite horticole sans engrais.",
            [
                _role("Base acide pauvre", 0.70, "Tourbe blonde"),
                _role("Aération", 0.30, "Perlite"),
            ],
            tuple(knowledge.RICH_CARNIVOROUS_FORBIDDEN),
        ),
        _variant(
            "Tourbe, perlite et vermiculite",
            "Formule 4:1:1 qui combine réserve d'eau, aération et stabilité du mélange.",
            [
                _role("Base acide pauvre", 4 / 6, "Tourbe blonde"),
                _role("Aération", 1 / 6, "Perlite"),
                _role("Rétention minérale", 1 / 6, "Vermiculite"),
            ],
            tuple(knowledge.RICH_CARNIVOROUS_FORBIDDEN),
        ),
    ),
    "nepenthes_epiphyte": (
        _variant(
            "Tourbe et perlite pour Nepenthes",
            "Variante simple publiée par des producteurs spécialisés, humide mais drainante.",
            [
                _role("Base acide pauvre", 0.50, "Tourbe blonde"),
                _role("Aération", 0.50, "Perlite"),
            ],
            tuple(knowledge.RICH_CARNIVOROUS_FORBIDDEN),
        ),
        _variant(
            "Sphaigne, perlite, écorces et pumice",
            "Mélange ouvert inspiré des recettes spécialisées pour racines fragiles et aérées.",
            [
                _role("Sphaigne", 0.50, "Sphaigne sèche", "Sphaigne du Chili"),
                _role("Aération", 0.20, "Perlite"),
                _role("Structure", 0.15, "Écorces de pin"),
                _role("Minéral poreux", 0.15, "Pumice"),
            ],
            tuple(knowledge.RICH_CARNIVOROUS_FORBIDDEN),
        ),
    ),
    "pinguicula_mineral": (
        _variant(
            "Tourbe, sable, pumice et perlite",
            "Mélange pauvre et très aéré, adapté aux grassettes mexicaines en pot.",
            [
                _role("Réserve pauvre", 0.25, "Tourbe blonde"),
                _role("Granulométrie", 0.25, "Sable grossier"),
                _role("Minéral poreux", 0.25, "Pumice"),
                _role("Aération", 0.25, "Perlite"),
            ],
            ("Compost mûr", "Humus de lombric", "Terreau plantes vertes"),
        ),
        _variant(
            "Minéral calcaire avec perlite",
            "Variante presque entièrement minérale, drainante et légèrement calcaire.",
            [
                _role("Argile minérale", 0.35, "Argile calcinée (Moler)"),
                _role("Aération", 0.30, "Perlite"),
                _role("Minéral poreux", 0.20, "Pumice"),
                _role("Tampon calcaire", 0.15, "Poudre de Calcaire / Dolomie"),
            ],
            ("Compost mûr", "Humus de lombric", "Terreau plantes vertes"),
        ),
    ),
    "drosophyllum_dry": (
        _variant(
            "Tourbe, perlite, pumice et sable",
            "Mélange en parts égales, très drainant, pour la carnivore méditerranéenne.",
            [
                _role("Fraction acide", 0.25, "Tourbe blonde"),
                _role("Aération", 0.25, "Perlite"),
                _role("Minéral poreux", 0.25, "Pumice"),
                _role("Granulométrie", 0.25, "Sable grossier"),
            ],
            tuple(knowledge.RICH_CARNIVOROUS_FORBIDDEN),
        ),
        _variant(
            "Quartz, perlite et pouzzolane",
            "Variante plus minérale qui limite fortement la stagnation autour des racines.",
            [
                _role("Quartz", 0.30, "Sable de quartz"),
                _role("Aération", 0.30, "Perlite"),
                _role("Minéral volcanique", 0.25, "Pouzzolane", "Pumice"),
                _role("Fraction acide", 0.15, "Tourbe blonde"),
            ],
            tuple(knowledge.RICH_CARNIVOROUS_FORBIDDEN),
        ),
    ),
}

AERATION_OPTIONS: dict[str, tuple[str, ...]] = {
    "lotus_heavy": ("Sable de quartz", "Gravier de Quartz"),
    "aquatic_heavy": ("Sable de quartz", "Gravier de Quartz"),
    "orchid_epiphyte": ("Perlite", "Seramis", "Pumice"),
    "succulent_mineral": ("Perlite", "Pumice", "Pouzzolane"),
    "acid_ericaceous": ("Perlite", "Kanuma", "Sable de quartz"),
    "mediterranean_dry": ("Perlite", "Pumice", "Pouzzolane"),
    "woody_loam": ("Perlite", "Pouzzolane", "Gravier de Quartz"),
}
DEFAULT_AERATION_OPTIONS = ("Perlite", "Pumice", "Pouzzolane", "Sable grossier")


def _source_key(source: Mapping[str, Any]) -> str:
    return str(source.get("url") or source.get("titre") or "").strip().casefold()


def _source_ids(template_id: str) -> tuple[str, ...]:
    ordered = [
        *consensus.SOURCE_GROUPS.get(template_id, consensus.SOURCE_GROUPS["general_container"]),
        *DEEP_SOURCE_GROUPS.get(template_id, ()),
        *GENERAL_FALLBACK_SOURCE_IDS,
    ]
    return tuple(dict.fromkeys(ordered))


def _augment_sources(variant: Mapping[str, Any], template_id: str) -> dict[str, Any]:
    result = copy.deepcopy(dict(variant))
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in result.get("sources", []):
        if not isinstance(source, Mapping):
            continue
        key = _source_key(source)
        if key and key not in seen:
            unique.append(copy.deepcopy(dict(source)))
            seen.add(key)
    for source_id in _source_ids(template_id):
        source = knowledge.SOURCES.get(source_id)
        if not source:
            continue
        key = _source_key(source)
        if key and key not in seen:
            unique.append(copy.deepcopy(source))
            seen.add(key)
    result["sources"] = unique
    result["methode_recherche"] = "Corpus approfondi par groupe botanique"
    result["portee_recherche"] = (
        "Quatre compositions distinctes fondées sur des guides institutionnels, "
        "universitaires et des producteurs spécialisés ; chaînes vidéo utilisées "
        "comme veille pratique complémentaire."
    )
    return result


def _used_ingredients(variant: Mapping[str, Any]) -> set[str]:
    return {
        str(ingredient)
        for role in variant.get("roles", [])
        for ingredient in role.get("ing", [])
    }


def _choose_extra_ingredient(
    template_id: str,
    variant: Mapping[str, Any],
    rotation: int,
) -> str | None:
    forbidden = set(variant.get("interdits", []))
    used = _used_ingredients(variant)
    options = AERATION_OPTIONS.get(template_id, DEFAULT_AERATION_OPTIONS)
    rotated = options[rotation % len(options) :] + options[: rotation % len(options)]
    for ingredient in rotated:
        if ingredient not in forbidden and ingredient not in used:
            return ingredient
    for ingredient in rotated:
        if ingredient not in forbidden:
            return ingredient
    return None


def _generated_variant(
    base: Mapping[str, Any],
    template_id: str,
    *,
    name: str,
    description: str,
    extra_ratio: float,
    rotation: int,
) -> dict[str, Any]:
    result = copy.deepcopy(dict(base))
    result["nom"] = name
    result["description"] = description
    roles = []
    for raw_role in result.get("roles", []):
        role = copy.deepcopy(dict(raw_role))
        ingredients = list(dict.fromkeys(role.get("ing", [])))
        if ingredients:
            step = rotation % len(ingredients)
            role["ing"] = ingredients[step:] + ingredients[:step]
        role["ratio"] = float(role.get("ratio", 0)) * (1.0 - extra_ratio)
        roles.append(role)
    extra = _choose_extra_ingredient(template_id, result, rotation)
    if extra:
        roles.append(
            {
                "nom": "Aération complémentaire" if extra == "Perlite" else "Fraction minérale complémentaire",
                "ratio": extra_ratio,
                "ing": [extra],
            }
        )
    elif roles:
        roles[0]["ratio"] = float(roles[0]["ratio"]) + extra_ratio
    result["roles"] = roles
    result["sources"] = []
    return result


def _base_signature(variant: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(
        (
            str(role.get("nom") or ""),
            round(float(role.get("ratio", 0)), 5),
            tuple(role.get("ing", [])),
        )
        for role in variant.get("roles", [])
    )


def _four_base_variants(template_id: str, variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base = [copy.deepcopy(item) for item in variants[:2]]
    if not base:
        base = [copy.deepcopy(knowledge.TEMPLATES["general_container"]["variants"][0])]
    if len(base) == 1:
        base.append(
            copy.deepcopy(
                consensus.COMPLEMENTARY_VARIANTS.get(template_id)
                or consensus._generated_complement(base[0])
            )
        )

    curated = CARNIVOROUS_EXTRA_VARIANTS.get(template_id)
    if curated:
        candidates = [*base[:2], *copy.deepcopy(curated)]
    else:
        candidates = [
            *base[:2],
            _generated_variant(
                base[0],
                template_id,
                name="Version plus aérée",
                description=(
                    "Composition distincte qui augmente l'aération du mélange, "
                    "notamment avec de la perlite lorsqu'elle convient au groupe."
                ),
                extra_ratio=0.15 if template_id not in {"lotus_heavy", "aquatic_heavy"} else 0.10,
                rotation=1,
            ),
            _generated_variant(
                base[1],
                template_id,
                name="Version minérale durable",
                description=(
                    "Composition distincte qui renforce la fraction minérale et "
                    "la tenue du substrat dans le temps."
                ),
                extra_ratio=0.20 if template_id not in {"lotus_heavy", "aquatic_heavy"} else 0.10,
                rotation=2,
            ),
        ]

    cleaned: list[dict[str, Any]] = []
    signatures: set[tuple[Any, ...]] = set()
    for candidate in candidates:
        item = knowledge._clean_variant(candidate)
        signature = _base_signature(item)
        if signature in signatures:
            continue
        cleaned.append(_augment_sources(item, template_id))
        signatures.add(signature)
        if len(cleaned) == BASE_VARIANT_COUNT:
            break

    while len(cleaned) < BASE_VARIANT_COUNT:
        seed = cleaned[0] if cleaned else knowledge._clean_variant(base[0])
        generated = _generated_variant(
            seed,
            template_id,
            name=f"Composition complémentaire {len(cleaned) + 1}",
            description="Composition complémentaire générée à partir du consensus du groupe.",
            extra_ratio=0.08 + 0.02 * len(cleaned),
            rotation=len(cleaned) + 1,
        )
        item = knowledge._clean_variant(generated)
        signature = _base_signature(item)
        if signature in signatures:
            item["roles"][0]["ratio"] += 0.01
            item = knowledge._clean_variant(item)
            signature = _base_signature(item)
        cleaned.append(_augment_sources(item, template_id))
        signatures.add(signature)
    return cleaned[:BASE_VARIANT_COUNT]


ORGANIC_OR_SOIL = consensus.ORGANIC_OR_SOIL
STRUCTURE = consensus.STRUCTURE
ADDITIVES = consensus.ADDITIVES


def _ingredient_category(ingredient: str) -> str:
    if ingredient in ORGANIC_OR_SOIL:
        return "Base organique et terre"
    if ingredient in STRUCTURE:
        return "Structure grossière"
    if ingredient in ADDITIVES:
        return "Additifs"
    return "Drainage minéral"


def _synthesis_variant(base_variants: list[dict[str, Any]], template_id: str) -> dict[str, Any]:
    weights: defaultdict[str, float] = defaultdict(float)
    variant_weight = 1.0 / len(base_variants)
    for variant in base_variants:
        for role in variant.get("roles", []):
            ingredients = list(dict.fromkeys(role.get("ing", [])))
            if not ingredients:
                continue
            contribution = float(role.get("ratio", 0)) * variant_weight / len(ingredients)
            for ingredient in ingredients:
                weights[ingredient] += contribution

    category_ingredients: defaultdict[str, list[str]] = defaultdict(list)
    category_ratios: defaultdict[str, float] = defaultdict(float)
    for ingredient, ratio in weights.items():
        category = _ingredient_category(ingredient)
        category_ingredients[category].append(ingredient)
        category_ratios[category] += ratio

    roles = [
        {
            "nom": category,
            "ratio": category_ratios[category],
            "ing": sorted(category_ingredients[category]),
        }
        for category in (
            "Base organique et terre",
            "Structure grossière",
            "Drainage minéral",
            "Additifs",
        )
        if category_ingredients[category]
    ]
    used = {ingredient for role in roles for ingredient in role["ing"]}
    forbidden = {
        ingredient
        for variant in base_variants
        for ingredient in variant.get("interdits", [])
        if ingredient not in used
    }
    synthesis = {
        "nom": "Synthèse des quatre variantes",
        "description": (
            "Moyenne pondérée des quatre compositions. Lorsque tous les "
            "ingrédients sont disponibles, la recette mélange les composants "
            "proposés par l'ensemble des variantes."
        ),
        "roles": roles,
        "interdits": sorted(forbidden),
        "sources": [source for variant in base_variants for source in variant.get("sources", [])],
    }
    return _augment_sources(knowledge._clean_variant(synthesis), template_id)


def _source_count(variant: Mapping[str, Any]) -> int:
    return len(
        {
            _source_key(source)
            for source in variant.get("sources", [])
            if isinstance(source, Mapping) and _source_key(source)
        }
    )


def install() -> None:
    """Installe les cinq variantes après les correctifs de stabilité existants."""
    if getattr(knowledge, "_deep_consensus5_installed", False):
        return
    if len(DEEP_RESEARCH_SOURCES) < MIN_RESEARCH_CORPUS:
        raise RuntimeError("Le corpus approfondi doit contenir au moins vingt sources.")
    if not REQUESTED_CREATOR_SOURCE_IDS.issubset(DEEP_RESEARCH_SOURCES):
        raise RuntimeError("Une chaîne demandée manque au corpus de recherche.")

    knowledge.SOURCES.update(copy.deepcopy(DEEP_RESEARCH_SOURCES))
    previous_resolved = knowledge.resolved_substrate

    def resolved_substrate(profile: Mapping[str, Any]) -> dict[str, Any]:
        substrate = profile.get("substrat", {})
        substrate = substrate if isinstance(substrate, Mapping) else {}
        stored = substrate.get("variantes")
        template_id = str(substrate.get("modele_recherche") or knowledge.classify_profile(profile))

        if (
            isinstance(stored, list)
            and len(stored) >= TOTAL_VARIANT_COUNT
            and isinstance(stored[0], Mapping)
            and str(stored[0].get("nom") or "").startswith("Synthèse")
        ):
            base_variants = [
                knowledge._clean_variant(item)
                for item in stored[1 : 1 + BASE_VARIANT_COUNT]
                if isinstance(item, Mapping)
            ]
            category = str(
                substrate.get("categorie_horticole")
                or knowledge.TEMPLATES.get(template_id, {}).get("label", template_id)
            )
            result = {
                "modele": template_id,
                "categorie": category,
                "variantes": [],
                "version_recherche": RESEARCH_VERSION,
            }
        else:
            previous = previous_resolved(profile)
            template_id = str(previous.get("modele") or template_id or knowledge.classify_profile(profile))
            previous_variants = [
                knowledge._clean_variant(item)
                for item in previous.get("variantes", [])
                if isinstance(item, Mapping)
            ]
            if previous_variants and str(previous_variants[0].get("nom") or "").startswith("Synthèse"):
                previous_variants = previous_variants[1:]
            base_variants = previous_variants[:2]
            result = copy.deepcopy(previous)

        base_variants = _four_base_variants(template_id, base_variants)
        result["variantes"] = [_synthesis_variant(base_variants, template_id), *base_variants]
        result["version_recherche"] = RESEARCH_VERSION
        result["methode_recherche"] = "corpus_20_plus_quatre_compositions_et_synthese"
        result["taille_corpus_recherche"] = len(DEEP_RESEARCH_SOURCES)
        return result

    def validate_resolved_profile(profile: Mapping[str, Any]) -> list[str]:
        errors: list[str] = []
        resolved = resolved_substrate(profile)
        variants = resolved.get("variantes", [])
        if len(variants) != TOTAL_VARIANT_COUNT:
            errors.append("Chaque fiche doit proposer quatre compositions et une synthèse.")
        if variants and str(variants[0].get("nom") or "") != "Synthèse des quatre variantes":
            errors.append("La synthèse des quatre variantes doit être placée en premier.")

        signatures = {
            _base_signature(variant)
            for variant in variants[1:]
            if isinstance(variant, Mapping)
        }
        if len(signatures) != BASE_VARIANT_COUNT:
            errors.append("Les quatre compositions doivent être distinctes.")

        for variant in variants:
            roles = variant.get("roles", [])
            total = sum(float(role.get("ratio", 0)) for role in roles)
            if abs(total - 1.0) > 0.001:
                errors.append(f"La variante {variant.get('nom')} totalise {total:.4f}.")
            for role in roles:
                for ingredient in role.get("ing", []):
                    if ingredient not in knowledge.CANONICAL_SET:
                        errors.append(f"Ingrédient non canonique: {ingredient}")
            if _source_count(variant) < MIN_VARIANT_SOURCES:
                errors.append(f"La variante {variant.get('nom')} n'a pas assez de sources approfondies.")
            used = _used_ingredients(variant)
            conflict = used.intersection(variant.get("interdits", []))
            if conflict:
                errors.append(f"Ingrédients à la fois utilisés et interdits: {sorted(conflict)}")

        if resolved.get("modele") in {
            "carnivorous_bog",
            "nepenthes_epiphyte",
            "pinguicula_mineral",
            "drosophyllum_dry",
        }:
            base_with_perlite = sum("Perlite" in _used_ingredients(variant) for variant in variants[1:])
            if base_with_perlite < 2:
                errors.append("Les carnivores doivent proposer au moins deux compositions avec perlite.")
            if variants and "Perlite" not in _used_ingredients(variants[0]):
                errors.append("La synthèse carnivore doit inclure la perlite.")
        return errors

    knowledge.resolved_substrate = resolved_substrate
    knowledge.validate_resolved_profile = validate_resolved_profile
    knowledge._deep_consensus5_installed = True


__all__ = [
    "BASE_VARIANT_COUNT",
    "DEEP_RESEARCH_SOURCES",
    "MIN_RESEARCH_CORPUS",
    "MIN_VARIANT_SOURCES",
    "RESEARCH_VERSION",
    "REQUESTED_CREATOR_SOURCE_IDS",
    "TOTAL_VARIANT_COUNT",
    "install",
]

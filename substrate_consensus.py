"""Consensus horticole sourcé pour les variantes de substrat.

Chaque fiche reçoit trois propositions :
1. une synthèse qui combine les deux variantes complémentaires ;
2. une première variante horticole ;
3. une seconde variante horticole.

Les sources documentent le groupe botanique et le type de culture. Elles ne
constituent pas une validation manuelle, espèce par espèce, de tout le catalogue.
Cette distinction est conservée dans les métadonnées de chaque variante.
"""
from __future__ import annotations

import copy
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import substrate_knowledge as knowledge

RESEARCH_VERSION = "2026.08-consensus4"
MIN_SOURCES = 4

ADDITIONAL_SOURCES: dict[str, dict[str, str]] = {
    "rhs_aquatic_planting": {
        "titre": "RHS — Aquatic plants: planting guide",
        "url": "https://www.rhs.org.uk/plants/types/aquatic-bog/planting",
    },
    "iowa_carnivorous": {
        "titre": "Iowa State University Extension — Carnivorous plants",
        "url": "https://yardandgarden.extension.iastate.edu/article/1998/12-11-1998/carnplants.html",
    },
    "unl_carnivorous": {
        "titre": "Nebraska Extension — Care for carnivorous plants",
        "url": "https://lancaster.unl.edu/care-carnivorous-plants/",
    },
    "bbg_carnivorous": {
        "titre": "Brooklyn Botanic Garden — Carnivorous mini-bog medium",
        "url": "https://www.bbg.org/article/mini_bog_garden_with_carnivorous_plants",
    },
    "aos_cattleya": {
        "titre": "American Orchid Society — Cattleya culture sheet",
        "url": "https://www.aos.org/orchid-care/care-sheets/cattleya-culture-sheet",
    },
    "aos_gongora": {
        "titre": "American Orchid Society — Gongora culture sheet",
        "url": "https://www.aos.org/orchid-care/care-sheets/gongora-culture-sheet",
    },
    "wvu_succulents": {
        "titre": "West Virginia University Extension — Succulents 101",
        "url": "https://extension.wvu.edu/lawn-gardening-pests/indoor-plants/succulents-101",
    },
    "iowa_succulents": {
        "titre": "Iowa State University Extension — Growing succulents indoors",
        "url": "https://yardandgarden.extension.iastate.edu/how-to/growing-succulents-indoors",
    },
    "illinois_succulents": {
        "titre": "Illinois Extension — Propagating succulents and cacti",
        "url": "https://extension.illinois.edu/blogs/hort-home-landscape/2015-06-04-propagating-succulents-and-cacti",
    },
    "uconn_ferns": {
        "titre": "University of Connecticut — Growing indoor ferns",
        "url": "https://homegarden.cahnr.uconn.edu/factsheets/growing-indoor-ferns/",
    },
    "uga_houseplants": {
        "titre": "University of Georgia Extension — Growing indoor plants",
        "url": "https://extension.uga.edu/publications/detail.html?number=B1318",
    },
    "ncsu_bromeliad": {
        "titre": "NC State Extension — Guzmania bromeliad",
        "url": "https://plants.ces.ncsu.edu/plants/guzmania/common-name/bromeliad/",
    },
    "wisc_bromeliads": {
        "titre": "University of Wisconsin Extension — Bromeliads",
        "url": "https://hort.extension.wisc.edu/articles/bromeliads/",
    },
    "uf_bromeliads": {
        "titre": "UF/IFAS — Bromeliads",
        "url": "https://gardeningsolutions.ifas.ufl.edu/plants/ornamentals/bromeliads/",
    },
    "umd_epiphytes": {
        "titre": "University of Maryland Extension — Potting epiphytic houseplants",
        "url": "https://extension.umd.edu/resource/potting-and-repotting-indoor-plants",
    },
    "uconn_philodendron": {
        "titre": "University of Connecticut — Philodendron potting mix",
        "url": "https://homegarden.cahnr.uconn.edu/factsheets/philodendron/",
    },
    "uf_philodendron": {
        "titre": "UF/IFAS — Philodendron growing media",
        "url": "https://ask.ifas.ufl.edu/publication/EP150",
    },
    "illinois_houseplants": {
        "titre": "Illinois Extension — Houseplant potting mixes",
        "url": "https://extension.illinois.edu/houseplants/get-started",
    },
    "okstate_houseplants": {
        "titre": "Oklahoma State University — Houseplant potting medium",
        "url": "https://extension.okstate.edu/fact-sheets/houseplant-care",
    },
    "ncsu_containers": {
        "titre": "NC State Extension — Plants grown in containers",
        "url": "https://content.ces.ncsu.edu/extension-gardener-handbook/18-plants-grown-in-containers",
    },
    "unh_potting_mix": {
        "titre": "University of New Hampshire Extension — Potting mixes",
        "url": "https://extension.unh.edu/blog/2020/01/what-best-soil-potted-plants",
    },
    "clemson_indoor_mix": {
        "titre": "Clemson Extension — Indoor plant soil mixes",
        "url": "https://hgic.clemson.edu/factsheet/indoor-plants-soil-mixes/",
    },
    "ucanr_acid": {
        "titre": "University of California ANR — Acid-loving plants",
        "url": "https://ucanr.edu/node/164135/printable/print",
    },
    "missouri_houseplants": {
        "titre": "University of Missouri Extension — Caring for houseplants",
        "url": "https://extension.missouri.edu/publications/g6510",
    },
    "uga_containers": {
        "titre": "University of Georgia Extension — Gardening in containers",
        "url": "https://extension.uga.edu/publications/detail.html?number=C787",
    },
    "umd_growing_media": {
        "titre": "University of Maryland Extension — Growing media for containers",
        "url": "https://extension.umd.edu/resource/growing-media-potting-soil-containers",
    },
    "tamu_citrus": {
        "titre": "Texas A&M AgriLife — Citrus in containers",
        "url": "https://aggie-horticulture.tamu.edu/fruit-nut/fact-sheets/citrus/",
    },
    "psu_woody_containers": {
        "titre": "Penn State Extension — Container-grown trees and shrubs",
        "url": "https://extension.psu.edu/container-grown-trees-and-shrubs-fix-those-roots-before-you-plant",
    },
}

SOURCE_GROUPS: dict[str, tuple[str, ...]] = {
    "lotus_heavy": (
        "rhs_lotus", "missouri_lotus", "ncsu_lotus", "rhs_aquatic_planting",
    ),
    "aquatic_heavy": (
        "rhs_aquatic", "rhs_lotus", "ncsu_lotus", "rhs_aquatic_planting",
    ),
    "carnivorous_bog": (
        "rhs_carnivorous", "ncsu_dionaea", "penn_carnivorous", "iowa_carnivorous", "unl_carnivorous", "bbg_carnivorous",
    ),
    "pinguicula_mineral": (
        "rhs_pinguicula", "rhs_carnivorous", "penn_carnivorous", "iowa_carnivorous",
    ),
    "nepenthes_epiphyte": (
        "rhs_carnivorous", "aos_media", "aos_repotting", "umd_epiphytes",
    ),
    "drosophyllum_dry": (
        "rhs_carnivorous", "penn_carnivorous", "iowa_carnivorous", "unl_carnivorous",
    ),
    "orchid_epiphyte": (
        "aos_media", "aos_repotting", "aos_vanda", "aos_cattleya", "aos_gongora",
    ),
    "succulent_mineral": (
        "umn_succulents", "wvu_succulents", "iowa_succulents", "illinois_succulents",
    ),
    "epiphytic_fern": (
        "rhs_epiphytic_ferns", "rhs_ferns", "uconn_ferns", "uga_houseplants",
    ),
    "fern_humus": (
        "rhs_ferns", "uconn_ferns", "uga_houseplants", "illinois_houseplants",
    ),
    "bromeliad_epiphyte": (
        "ncsu_bromeliad", "wisc_bromeliads", "uf_bromeliads", "umd_epiphytes",
    ),
    "aroid_chunky": (
        "uconn_philodendron", "uf_philodendron", "umd_epiphytes", "okstate_houseplants",
    ),
    "acid_ericaceous": (
        "rhs_blueberries", "ucanr_acid", "missouri_houseplants", "rhs_containers",
    ),
    "actinidia_fruit_vine": (
        "osu_kiwi", "rhs_trees", "rhs_containers", "uga_containers",
    ),
    "citrus_loam": (
        "rhs_citrus", "tamu_citrus", "rhs_containers", "umd_growing_media",
    ),
    "mediterranean_dry": (
        "rhs_containers", "rhs_low_carbon_mix", "ncsu_containers", "umd_growing_media",
    ),
    "woody_loam": (
        "rhs_trees", "rhs_containers", "uga_containers", "psu_woody_containers",
    ),
    "tropical_moist": (
        "rhs_houseplants", "illinois_houseplants", "okstate_houseplants", "clemson_indoor_mix",
    ),
    "general_container": (
        "rhs_containers", "ncsu_containers", "unh_potting_mix", "umd_growing_media",
    ),
}


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


COMPLEMENTARY_VARIANTS: dict[str, dict[str, Any]] = {
    "pinguicula_mineral": _variant(
        "Minéral volcanique pauvre",
        "Alternative très aérée, à faible fertilité, avec une petite réserve organique.",
        [
            _role("Réserve pauvre", 0.20, "Tourbe blonde"),
            _role("Minéral poreux", 0.35, "Pumice", "Pouzzolane"),
            _role("Granulométrie", 0.30, "Sable grossier", "Gravier de Quartz"),
            _role("Tampon calcaire", 0.15, "Poudre de Calcaire / Dolomie"),
        ],
        ("Compost mûr", "Humus de lombric", "Terreau plantes vertes"),
    ),
    "drosophyllum_dry": _variant(
        "Quartz, pumice et tourbe minimale",
        "Variante très minérale qui limite la stagnation autour des racines sensibles.",
        [
            _role("Quartz", 0.45, "Sable de quartz", "Gravier de Quartz"),
            _role("Minéral poreux", 0.35, "Pumice", "Pouzzolane"),
            _role("Fraction acide", 0.20, "Tourbe blonde"),
        ],
        tuple(knowledge.RICH_CARNIVOROUS_FORBIDDEN),
    ),
    "fern_humus": _variant(
        "Feuilles, coco et écorces fines",
        "Alternative humifère plus légère, adaptée aux contenants d'intérieur.",
        [
            _role("Humus de feuilles", 0.40, "Terreau de feuilles"),
            _role("Base légère", 0.25, "Terreau léger"),
            _role("Rétention", 0.20, "Fibre de coco"),
            _role("Structure", 0.15, "Écorces de pin", "Perlite"),
        ],
    ),
    "citrus_loam": _variant(
        "Écorces, terreau et sable",
        "Alternative plus aérée pour les agrumes cultivés durablement en pot.",
        [
            _role("Terreau", 0.45, "Terreau horticole"),
            _role("Structure", 0.25, "Écorces de pin"),
            _role("Loam", 0.15, "Terre franche / Terre de jardin"),
            _role("Drainage", 0.15, "Sable grossier", "Pumice"),
        ],
    ),
    "mediterranean_dry": _variant(
        "Terre franche et pouzzolane",
        "Alternative plus minérale pour les espèces de garrigue et de climat sec.",
        [
            _role("Terre stable", 0.40, "Terre franche / Terre de jardin"),
            _role("Base organique", 0.25, "Terreau horticole"),
            _role("Pouzzolane", 0.20, "Pouzzolane", "Micro-pouzzolane"),
            _role("Drainage", 0.15, "Sable grossier", "Gravier de Quartz"),
        ],
    ),
}

ORGANIC_OR_SOIL = {
    "Tourbe blonde", "Fibre de coco", "Sphaigne sèche", "Sphaigne du Chili",
    "Mousse de sphaigne vivante", "Pépites de tourbe", "Humus de lombric",
    "Terreau de feuilles", "Terreau argileux (Aquatique / Nénuphars)",
    "Terre franche / Terre de jardin", "Terreau de semis", "Terreau horticole",
    "Terreau léger", "Terreau plantes vertes", "Compost mûr",
}
STRUCTURE = {"Chips de coco", "Écorces de pin"}
ADDITIVES = {
    "Charbon actif", "Charbon de bambou", "Farine de basalte",
    "Poudre de Calcaire / Dolomie",
}


def _source_key(source: Mapping[str, Any]) -> str:
    return str(source.get("url") or source.get("titre") or "").strip().casefold()


def _augment_sources(variant: dict[str, Any], template_id: str) -> dict[str, Any]:
    result = copy.deepcopy(variant)
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in result.get("sources", []):
        if not isinstance(source, Mapping):
            continue
        key = _source_key(source)
        if key and key not in seen:
            unique.append(copy.deepcopy(dict(source)))
            seen.add(key)
    for source_id in SOURCE_GROUPS.get(template_id, SOURCE_GROUPS["general_container"]):
        source = knowledge.SOURCES.get(source_id)
        if not source:
            continue
        key = _source_key(source)
        if key and key not in seen:
            unique.append(copy.deepcopy(source))
            seen.add(key)
    result["sources"] = unique
    result["methode_recherche"] = "Consensus horticole par groupe botanique"
    result["portee_recherche"] = (
        "Sources concordantes pour le groupe et le type de culture ; "
        "validation individuelle de l'espèce non revendiquée."
    )
    return result


def _generated_complement(first: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(first))
    result["nom"] = f"{result.get('nom', 'Recette')} — alternative"
    result["description"] = (
        "Alternative issue du même consensus, avec priorité donnée aux autres "
        "ingrédients proposés pour chaque fonction."
    )
    for role in result.get("roles", []):
        ingredients = list(role.get("ing", []))
        if len(ingredients) > 1:
            role["ing"] = ingredients[1:] + ingredients[:1]
    return result


def _ingredient_category(ingredient: str) -> str:
    if ingredient in ORGANIC_OR_SOIL:
        return "Base organique et terre"
    if ingredient in STRUCTURE:
        return "Structure grossière"
    if ingredient in ADDITIVES:
        return "Additifs"
    return "Drainage minéral"


def _composite_variant(base_variants: list[dict[str, Any]], template_id: str) -> dict[str, Any]:
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
    composite = {
        "nom": "Synthèse des variantes",
        "description": (
            "Moyenne pondérée des deux compositions complémentaires. "
            "Elle est placée en premier comme point de départ équilibré."
        ),
        "roles": roles,
        "interdits": sorted(forbidden),
        "sources": [
            source
            for variant in base_variants
            for source in variant.get("sources", [])
        ],
    }
    return _augment_sources(composite, template_id)


def _three_variants(template_id: str, variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base = [copy.deepcopy(variant) for variant in variants[:2]]
    if not base:
        base = [copy.deepcopy(knowledge.TEMPLATES["general_container"]["variants"][0])]
    if len(base) == 1:
        base.append(copy.deepcopy(COMPLEMENTARY_VARIANTS.get(template_id) or _generated_complement(base[0])))
    base = [_augment_sources(variant, template_id) for variant in base[:2]]
    return [_composite_variant(base, template_id), *base]


def install() -> None:
    """Étend la base chargée sans réécrire les milliers de fiches JSON."""
    if getattr(knowledge, "_consensus_variants_installed", False):
        return
    knowledge.SOURCES.update(copy.deepcopy(ADDITIONAL_SOURCES))
    original_resolved = knowledge.resolved_substrate

    def resolved_substrate(profile: Mapping[str, Any]) -> dict[str, Any]:
        resolved = original_resolved(profile)
        template_id = str(resolved.get("modele") or knowledge.classify_profile(profile))
        variants = [
            knowledge._clean_variant(item)
            for item in resolved.get("variantes", [])
            if isinstance(item, Mapping)
        ]
        result = copy.deepcopy(resolved)
        result["variantes"] = [knowledge._clean_variant(item) for item in _three_variants(template_id, variants)]
        result["version_recherche"] = RESEARCH_VERSION
        result["methode_recherche"] = "consensus_groupe_quatre_sources_minimum"
        return result

    def validate_resolved_profile(profile: Mapping[str, Any]) -> list[str]:
        errors: list[str] = []
        resolved = resolved_substrate(profile)
        variants = resolved.get("variantes", [])
        if len(variants) != 3:
            errors.append("Chaque fiche doit proposer exactement trois variantes.")
        if variants and str(variants[0].get("nom")) != "Synthèse des variantes":
            errors.append("La synthèse des variantes doit être placée en premier.")
        for variant in variants:
            roles = variant.get("roles", [])
            total = sum(float(role.get("ratio", 0)) for role in roles)
            if abs(total - 1.0) > 0.001:
                errors.append(f"La variante {variant.get('nom')} totalise {total:.4f}.")
            for role in roles:
                for ingredient in role.get("ing", []):
                    if ingredient not in knowledge.CANONICAL_SET:
                        errors.append(f"Ingrédient non canonique: {ingredient}")
            source_count = len({
                _source_key(source)
                for source in variant.get("sources", [])
                if isinstance(source, Mapping) and _source_key(source)
            })
            if source_count < MIN_SOURCES:
                errors.append(
                    f"La variante {variant.get('nom')} n'a que {source_count} sources distinctes."
                )
            used = {ingredient for role in roles for ingredient in role.get("ing", [])}
            conflict = used.intersection(variant.get("interdits", []))
            if conflict:
                errors.append(f"Ingrédients à la fois utilisés et interdits: {sorted(conflict)}")
        return errors

    knowledge.resolved_substrate = resolved_substrate
    knowledge.validate_resolved_profile = validate_resolved_profile
    knowledge._consensus_variants_installed = True


__all__ = [
    "MIN_SOURCES",
    "RESEARCH_VERSION",
    "SOURCE_GROUPS",
    "install",
]

"""Base de connaissances documentée pour les recettes de substrat.

Les recettes utilisent exclusivement les ingrédients visibles dans l'onglet
Substrats. Les règles spécifiques (genre/famille/écologie) priment toujours sur
les modèles généraux afin d'éviter les mélanges génériques dangereux.
"""
from __future__ import annotations

import copy
import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

CANONICAL_INGREDIENTS = (
    "Tourbe blonde",
    "Fibre de coco",
    "Chips de coco",
    "Sphaigne sèche",
    "Sphaigne du Chili",
    "Mousse de sphaigne vivante",
    "Pépites de tourbe",
    "Humus de lombric",
    "Terreau de feuilles",
    "Terreau argileux (Aquatique / Nénuphars)",
    "Terre franche / Terre de jardin",
    "Terreau de semis",
    "Terreau horticole",
    "Terreau léger",
    "Terreau plantes vertes",
    "Sable grossier",
    "Perlite",
    "Pumice",
    "Pouzzolane",
    "Micro-pouzzolane",
    "Vermiculite",
    "Zéolite",
    "Kanuma",
    "Akadama",
    "Kiryu",
    "Seramis",
    "Argile calcinée (Moler)",
    "Billes d'argile",
    "Gravier de Quartz",
    "Sable de quartz",
    "Charbon actif",
    "Charbon de bambou",
    "Écorces de pin",
    "Farine de basalte",
    "Poudre de Calcaire / Dolomie",
    "Compost mûr",
)
CANONICAL_SET = frozenset(CANONICAL_INGREDIENTS)


def normalize_text(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text.casefold()).split())


_CANONICAL_BY_NORMALIZED = {normalize_text(item): item for item in CANONICAL_INGREDIENTS}
INGREDIENT_ALIASES = {
    "compost": "Compost mûr",
    "compost mur": "Compost mûr",
    "matiere organique": "Compost mûr",
    "fumier bien decompose": "Compost mûr",
    "well rotted manure": "Compost mûr",
    "terreau": "Terreau horticole",
    "terreau de qualite": "Terreau horticole",
    "terreau universel": "Terreau horticole",
    "potting soil": "Terreau horticole",
    "potting compost": "Terreau horticole",
    "compost terreau": "Terreau horticole",
    "terreau plante verte": "Terreau plantes vertes",
    "terreau pour plantes vertes": "Terreau plantes vertes",
    "terreau leger": "Terreau léger",
    "terreau semis": "Terreau de semis",
    "terreau aquatique": "Terreau argileux (Aquatique / Nénuphars)",
    "aquatic compost": "Terreau argileux (Aquatique / Nénuphars)",
    "terre argileuse": "Terreau argileux (Aquatique / Nénuphars)",
    "loam lourd": "Terreau argileux (Aquatique / Nénuphars)",
    "heavy loam": "Terreau argileux (Aquatique / Nénuphars)",
    "loam": "Terre franche / Terre de jardin",
    "terre de jardin": "Terre franche / Terre de jardin",
    "terre franche": "Terre franche / Terre de jardin",
    "garden soil": "Terre franche / Terre de jardin",
    "ecorces": "Écorces de pin",
    "ecorce de pin": "Écorces de pin",
    "ecorces de pin": "Écorces de pin",
    "pine bark": "Écorces de pin",
    "orchid bark": "Écorces de pin",
    "fir bark": "Écorces de pin",
    "sphaigne": "Sphaigne sèche",
    "sphaigne seche": "Sphaigne sèche",
    "dried sphagnum": "Sphaigne sèche",
    "live sphagnum": "Mousse de sphaigne vivante",
    "mousse de sphaigne": "Mousse de sphaigne vivante",
    "coco": "Fibre de coco",
    "coir": "Fibre de coco",
    "fibre coco": "Fibre de coco",
    "coco chips": "Chips de coco",
    "eclats de coco": "Chips de coco",
    "sable": "Sable grossier",
    "sable horticole": "Sable grossier",
    "sharp sand": "Sable grossier",
    "coarse sand": "Sable grossier",
    "sable siliceux": "Sable de quartz",
    "silica sand": "Sable de quartz",
    "quartz sand": "Sable de quartz",
    "gravier": "Gravier de Quartz",
    "grit": "Gravier de Quartz",
    "horticultural grit": "Gravier de Quartz",
    "charbon": "Charbon actif",
    "charcoal": "Charbon actif",
    "dolomie": "Poudre de Calcaire / Dolomie",
    "calcaire": "Poudre de Calcaire / Dolomie",
    "dolomitic limestone": "Poudre de Calcaire / Dolomie",
    "pierre ponce": "Pumice",
    "pumice stone": "Pumice",
    "argile calcinee": "Argile calcinée (Moler)",
    "expanded clay": "Billes d'argile",
}


def canonicalize_ingredient(value: Any) -> str | None:
    normalized = normalize_text(value)
    if not normalized:
        return None
    direct = _CANONICAL_BY_NORMALIZED.get(normalized)
    if direct:
        return direct
    if normalized in INGREDIENT_ALIASES:
        return INGREDIENT_ALIASES[normalized]
    # Les libellés hérités contiennent souvent plusieurs synonymes séparés.
    for alias in sorted(INGREDIENT_ALIASES, key=len, reverse=True):
        if alias in normalized:
            return INGREDIENT_ALIASES[alias]
    return None


SOURCES = {
    "rhs_lotus": {
        "titre": "RHS — Nelumbo nucifera",
        "url": "https://www.rhs.org.uk/plants/11438/nelumbo-nucifera/details",
    },
    "rhs_lotus_cultivar": {
        "titre": "RHS — Nelumbo 'Perry's Giant Sunburst'",
        "url": "https://www.rhs.org.uk/plants/324098/nelumbo-perrys-giant-sunburst/details",
    },
    "missouri_lotus": {
        "titre": "Missouri Botanical Garden — Nelumbo nucifera",
        "url": "https://www.missouribotanicalgarden.org/PlantFinder/PlantFinderDetails.aspx?taxonid=282911",
    },
    "ncsu_lotus": {
        "titre": "NC State Extension — Nelumbo nucifera",
        "url": "https://plants.ces.ncsu.edu/plants/nelumbo-nucifera/",
    },
    "missouri_lotus_collection": {
        "titre": "Missouri Botanical Garden — Lotus collection",
        "url": "https://www.missouribotanicalgarden.org/gardens-gardening/our-garden/notable-plant-collections/lotus",
    },
    "rhs_aquatic": {
        "titre": "RHS — Zantedeschia en bassin",
        "url": "https://www.rhs.org.uk/plants/zantedeschia/growing-guide",
    },
    "rhs_carnivorous": {
        "titre": "RHS — Carnivorous plants growing guide",
        "url": "https://www.rhs.org.uk/plants/types/carnivorous/growing-guide",
    },
    "ncsu_dionaea": {
        "titre": "NC State Extension — Dionaea muscipula",
        "url": "https://plants.ces.ncsu.edu/plants/dionaea-muscipula/",
    },
    "penn_carnivorous": {
        "titre": "Penn State Extension — Carnivorous plants",
        "url": "https://extension.psu.edu/carnivorous-plants",
    },
    "rhs_pinguicula": {
        "titre": "RHS — Pinguicula gigantea",
        "url": "https://www.rhs.org.uk/plants/149227/pinguicula-gigantea/details",
    },
    "aos_media": {
        "titre": "American Orchid Society — Potting media",
        "url": "https://www.aos.org/orchid-care/what-is-the-best-potting-media",
    },
    "aos_repotting": {
        "titre": "American Orchid Society — Repotting",
        "url": "https://www.aos.org/orchid-care-and-culture-sheets/repotting",
    },
    "aos_vanda": {
        "titre": "American Orchid Society — Vanda culture",
        "url": "https://www.aos.org/orchid-care/care-sheets/vanda-culture-sheet",
    },
    "umn_succulents": {
        "titre": "University of Minnesota Extension — Cacti and succulents",
        "url": "https://extension.umn.edu/gardening-minnesota/cacti-and-succulents",
    },
    "rhs_epiphytic_ferns": {
        "titre": "RHS — Epiphytic ferns",
        "url": "https://www.rhs.org.uk/plants/epiphytic-ferns/how-to-grow-epiphytic-ferns",
    },
    "rhs_ferns": {
        "titre": "RHS — Ferns growing guide",
        "url": "https://www.rhs.org.uk/plants/types/ferns/growing-guide",
    },
    "rhs_blueberries": {
        "titre": "RHS — Blueberries growing guide",
        "url": "https://www.rhs.org.uk/fruit/blueberries/grow-your-own",
    },
    "rhs_containers": {
        "titre": "RHS — Growing plants in containers",
        "url": "https://www.rhs.org.uk/container-gardening/growing-plants-in-containers",
    },
    "rhs_trees": {
        "titre": "RHS — Trees in containers",
        "url": "https://www.rhs.org.uk/plants/types/trees/container-growing",
    },
    "rhs_citrus": {
        "titre": "RHS — Citrus growing guide",
        "url": "https://www.rhs.org.uk/fruit/citrus/grow-your-own",
    },
    "osu_kiwi": {
        "titre": "Oregon State University Extension — Kiwifruit",
        "url": "https://extension.oregonstate.edu/catalog/em-9322-growing-kiwifruit-your-home-garden",
    },
    "rhs_houseplants": {
        "titre": "RHS — Houseplants growing guide",
        "url": "https://www.rhs.org.uk/plants/types/houseplants/growing-guide",
    },
    "rhs_low_carbon_mix": {
        "titre": "RHS — Low-carbon container growing",
        "url": "https://www.rhs.org.uk/gardening-for-the-environment/low-carbon-gardening/low-carbon-container-growing",
    },
}


def _role(name: str, ratio: float, *ingredients: str) -> dict[str, Any]:
    return {"nom": name, "ratio": ratio, "ing": list(ingredients)}


def _variant(
    name: str,
    description: str,
    roles: list[dict[str, Any]],
    source_ids: tuple[str, ...],
    forbidden: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "nom": name,
        "description": description,
        "roles": roles,
        "interdits": list(forbidden),
        "sources": [copy.deepcopy(SOURCES[source_id]) for source_id in source_ids],
    }


LIGHTWEIGHT_AQUATIC_FORBIDDEN = (
    "Perlite",
    "Pumice",
    "Pouzzolane",
    "Micro-pouzzolane",
    "Vermiculite",
    "Billes d'argile",
    "Fibre de coco",
    "Chips de coco",
    "Sphaigne sèche",
    "Mousse de sphaigne vivante",
)
RICH_CARNIVOROUS_FORBIDDEN = (
    "Terreau horticole",
    "Terreau plantes vertes",
    "Terreau de feuilles",
    "Terre franche / Terre de jardin",
    "Terreau argileux (Aquatique / Nénuphars)",
    "Humus de lombric",
    "Compost mûr",
    "Farine de basalte",
)

TEMPLATES: dict[str, dict[str, Any]] = {
    "lotus_heavy": {
        "label": "Lotus aquatique à rhizome",
        "variants": [
            _variant(
                "Loam aquatique enrichi",
                "Mélange lourd qui reste au fond et ancre le rhizome.",
                [
                    _role("Loam aquatique lourd", 0.70, "Terreau argileux (Aquatique / Nénuphars)"),
                    _role("Terre minérale stable", 0.20, "Terre franche / Terre de jardin"),
                    _role("Apport organique modéré", 0.10, "Compost mûr"),
                ],
                ("rhs_lotus", "rhs_lotus_cultivar", "missouri_lotus", "ncsu_lotus", "missouri_lotus_collection"),
                LIGHTWEIGHT_AQUATIC_FORBIDDEN,
            ),
            _variant(
                "Terre franche et compost",
                "Variante simple et lourde pour panier immergé.",
                [
                    _role("Terre franche lourde", 0.80, "Terre franche / Terre de jardin"),
                    _role("Matière organique mûre", 0.20, "Compost mûr"),
                ],
                ("rhs_lotus", "missouri_lotus", "ncsu_lotus"),
                LIGHTWEIGHT_AQUATIC_FORBIDDEN,
            ),
        ],
    },
    "aquatic_heavy": {
        "label": "Aquatique ou plante de berge immergée",
        "variants": [
            _variant(
                "Compost aquatique lourd",
                "Substrat minéral lourd, stable sous l'eau.",
                [
                    _role("Base aquatique", 0.80, "Terreau argileux (Aquatique / Nénuphars)"),
                    _role("Ancrage minéral", 0.20, "Terre franche / Terre de jardin"),
                ],
                ("rhs_aquatic", "rhs_lotus", "ncsu_lotus"),
                LIGHTWEIGHT_AQUATIC_FORBIDDEN,
            ),
            _variant(
                "Terre franche lourde",
                "Alternative sans terreau aquatique commercial.",
                [
                    _role("Terre lourde", 0.90, "Terre franche / Terre de jardin"),
                    _role("Organique modéré", 0.10, "Compost mûr"),
                ],
                ("rhs_aquatic", "rhs_lotus"),
                LIGHTWEIGHT_AQUATIC_FORBIDDEN,
            ),
        ],
    },
    "carnivorous_bog": {
        "label": "Carnivore de tourbière pauvre",
        "variants": [
            _variant(
                "Tourbe et sable siliceux",
                "Mélange pauvre, acide et constamment humide.",
                [
                    _role("Base acide pauvre", 0.50, "Tourbe blonde"),
                    _role("Fraction minérale inerte", 0.50, "Sable de quartz"),
                ],
                ("rhs_carnivorous", "ncsu_dionaea", "penn_carnivorous"),
                RICH_CARNIVOROUS_FORBIDDEN,
            ),
            _variant(
                "Sphaigne et écorces fines",
                "Alternative sans terreau riche, inspirée des essais sans tourbe.",
                [
                    _role("Sphaigne", 0.75, "Sphaigne sèche", "Mousse de sphaigne vivante"),
                    _role("Structure pauvre", 0.25, "Écorces de pin"),
                ],
                ("rhs_carnivorous",),
                RICH_CARNIVOROUS_FORBIDDEN,
            ),
        ],
    },
    "pinguicula_mineral": {
        "label": "Pinguicula mexicaine minérale",
        "variants": [
            _variant(
                "Minéral calcaire équilibré",
                "Mélange très aéré pour grassettes mexicaines.",
                [
                    _role("Rétention pauvre", 0.25, "Tourbe blonde"),
                    _role("Sable", 0.25, "Sable grossier"),
                    _role("Aération", 0.25, "Perlite"),
                    _role("Fraction calcaire", 0.25, "Poudre de Calcaire / Dolomie"),
                ],
                ("rhs_pinguicula",),
                ("Compost mûr", "Humus de lombric", "Terreau plantes vertes"),
            )
        ],
    },
    "nepenthes_epiphyte": {
        "label": "Nepenthes tropicale épiphyte",
        "variants": [
            _variant(
                "Sphaigne et écorces",
                "Mélange très ouvert, humide mais non compact.",
                [
                    _role("Rétention", 0.45, "Sphaigne sèche", "Sphaigne du Chili"),
                    _role("Structure", 0.30, "Écorces de pin"),
                    _role("Aération", 0.15, "Perlite"),
                    _role("Charbon", 0.10, "Charbon actif", "Charbon de bambou"),
                ],
                ("rhs_carnivorous", "aos_repotting"),
                RICH_CARNIVOROUS_FORBIDDEN,
            ),
            _variant(
                "Sphaigne et coco grossière",
                "Variante organique très aérée.",
                [
                    _role("Sphaigne", 0.55, "Sphaigne sèche", "Sphaigne du Chili"),
                    _role("Structure coco", 0.25, "Chips de coco"),
                    _role("Aération", 0.20, "Perlite", "Pumice"),
                ],
                ("rhs_carnivorous",),
                RICH_CARNIVOROUS_FORBIDDEN,
            ),
        ],
    },
    "drosophyllum_dry": {
        "label": "Carnivore méditerranéenne sèche",
        "variants": [
            _variant(
                "Sable minéral pauvre",
                "Mélange pauvre et très drainant, sans compost riche.",
                [
                    _role("Minéral principal", 0.55, "Sable de quartz", "Sable grossier"),
                    _role("Aération", 0.25, "Perlite", "Pumice"),
                    _role("Fraction acide", 0.20, "Tourbe blonde"),
                ],
                ("rhs_carnivorous",),
                RICH_CARNIVOROUS_FORBIDDEN,
            )
        ],
    },
    "orchid_epiphyte": {
        "label": "Orchidée épiphyte",
        "variants": [
            _variant(
                "Écorces aérées",
                "Mélange grossier à drainage rapide.",
                [
                    _role("Structure principale", 0.60, "Écorces de pin"),
                    _role("Rétention", 0.20, "Sphaigne sèche", "Sphaigne du Chili"),
                    _role("Aération", 0.10, "Perlite", "Pumice"),
                    _role("Charbon", 0.10, "Charbon actif", "Charbon de bambou"),
                ],
                ("aos_media", "aos_repotting", "aos_vanda"),
                ("Terre franche / Terre de jardin", "Terreau argileux (Aquatique / Nénuphars)"),
            ),
            _variant(
                "Écorces et coco",
                "Alternative sans sphaigne pour les orchidées aimant sécher davantage.",
                [
                    _role("Écorces", 0.65, "Écorces de pin"),
                    _role("Coco grossière", 0.20, "Chips de coco"),
                    _role("Aération", 0.10, "Pumice", "Perlite"),
                    _role("Charbon", 0.05, "Charbon actif"),
                ],
                ("aos_media", "aos_vanda"),
                ("Terre franche / Terre de jardin", "Terreau argileux (Aquatique / Nénuphars)"),
            ),
        ],
    },
    "succulent_mineral": {
        "label": "Cactée ou succulente",
        "variants": [
            _variant(
                "Terreau et sable grossier",
                "Mélange simple qui se désagrège facilement une fois humide.",
                [
                    _role("Base", 0.50, "Terreau horticole", "Terreau léger"),
                    _role("Fraction minérale", 0.50, "Sable grossier"),
                ],
                ("umn_succulents",),
                ("Terreau argileux (Aquatique / Nénuphars)",),
            ),
            _variant(
                "Minéral renforcé",
                "Variante plus minérale pour espèces sensibles à la pourriture.",
                [
                    _role("Base organique", 0.35, "Terreau horticole", "Terreau léger"),
                    _role("Pumice", 0.25, "Pumice"),
                    _role("Pouzzolane", 0.25, "Pouzzolane", "Micro-pouzzolane"),
                    _role("Sable", 0.15, "Sable grossier"),
                ],
                ("umn_succulents",),
                ("Terreau argileux (Aquatique / Nénuphars)",),
            ),
        ],
    },
    "epiphytic_fern": {
        "label": "Fougère épiphyte",
        "variants": [
            _variant(
                "Écorces, rétention et aération",
                "Mélange ouvert, légèrement acide et rétenteur.",
                [
                    _role("Base", 0.50, "Terreau léger", "Fibre de coco"),
                    _role("Écorces", 0.25, "Écorces de pin"),
                    _role("Aération", 0.25, "Perlite", "Pumice"),
                ],
                ("rhs_epiphytic_ferns",),
            ),
            _variant(
                "Sphaigne et écorces",
                "Alternative pour forte humidité avec excellente aération.",
                [
                    _role("Sphaigne", 0.50, "Sphaigne sèche", "Sphaigne du Chili"),
                    _role("Écorces", 0.30, "Écorces de pin"),
                    _role("Coco grossière", 0.20, "Chips de coco"),
                ],
                ("rhs_epiphytic_ferns",),
            ),
        ],
    },
    "fern_humus": {
        "label": "Fougère terrestre humifère",
        "variants": [
            _variant(
                "Humifère frais et drainé",
                "Mélange riche en matière organique, humide sans être détrempé.",
                [
                    _role("Base organique", 0.55, "Terreau de feuilles", "Terreau horticole"),
                    _role("Rétention", 0.20, "Fibre de coco"),
                    _role("Terre stable", 0.15, "Terre franche / Terre de jardin"),
                    _role("Drainage", 0.10, "Sable grossier", "Perlite"),
                ],
                ("rhs_ferns",),
            )
        ],
    },
    "bromeliad_epiphyte": {
        "label": "Broméliacée épiphyte",
        "variants": [
            _variant(
                "Écorces et coco",
                "Mélange léger et très aéré.",
                [
                    _role("Écorces", 0.40, "Écorces de pin"),
                    _role("Coco", 0.25, "Fibre de coco", "Chips de coco"),
                    _role("Base légère", 0.20, "Terreau léger"),
                    _role("Aération", 0.15, "Perlite", "Pumice"),
                ],
                ("rhs_epiphytic_ferns", "rhs_houseplants"),
            ),
            _variant(
                "Sphaigne et écorces",
                "Variante plus rétentrice pour atmosphère sèche.",
                [
                    _role("Sphaigne", 0.40, "Sphaigne sèche", "Sphaigne du Chili"),
                    _role("Écorces", 0.35, "Écorces de pin"),
                    _role("Aération", 0.25, "Perlite", "Pumice"),
                ],
                ("rhs_epiphytic_ferns",),
            ),
        ],
    },
    "aroid_chunky": {
        "label": "Aroïde et tropicale à racines aérées",
        "variants": [
            _variant(
                "Mélange tropical structuré",
                "Base organique aérée par des éléments grossiers.",
                [
                    _role("Base", 0.35, "Terreau plantes vertes", "Terreau léger"),
                    _role("Écorces", 0.25, "Écorces de pin"),
                    _role("Aération minérale", 0.20, "Pumice", "Perlite"),
                    _role("Coco grossière", 0.15, "Chips de coco"),
                    _role("Charbon", 0.05, "Charbon actif", "Charbon de bambou"),
                ],
                ("rhs_houseplants", "rhs_epiphytic_ferns"),
            ),
            _variant(
                "Coco et écorces",
                "Variante légère pour arrosages fréquents.",
                [
                    _role("Coco", 0.35, "Fibre de coco"),
                    _role("Écorces", 0.30, "Écorces de pin"),
                    _role("Terreau", 0.20, "Terreau plantes vertes"),
                    _role("Aération", 0.15, "Perlite", "Pumice"),
                ],
                ("rhs_houseplants",),
            ),
        ],
    },
    "acid_ericaceous": {
        "label": "Plante acidophile",
        "variants": [
            _variant(
                "Acide organique drainé",
                "Mélange sans amendement calcaire.",
                [
                    _role("Base acide", 0.50, "Tourbe blonde"),
                    _role("Structure acide", 0.25, "Écorces de pin"),
                    _role("Matière humifère", 0.15, "Terreau de feuilles"),
                    _role("Drainage", 0.10, "Sable de quartz", "Perlite"),
                ],
                ("rhs_blueberries", "rhs_containers"),
                ("Poudre de Calcaire / Dolomie",),
            ),
            _variant(
                "Coco, kanuma et feuilles",
                "Variante sans tourbe, à surveiller avec un test de pH.",
                [
                    _role("Base", 0.45, "Fibre de coco"),
                    _role("Minéral acide", 0.25, "Kanuma"),
                    _role("Humus de feuilles", 0.20, "Terreau de feuilles"),
                    _role("Écorces", 0.10, "Écorces de pin"),
                ],
                ("rhs_blueberries", "rhs_containers"),
                ("Poudre de Calcaire / Dolomie",),
            ),
        ],
    },
    "actinidia_fruit_vine": {
        "label": "Actinidia et liane fruitière",
        "variants": [
            _variant(
                "Terreau horticole et compost mûr",
                "Mélange fertile, organique et bien drainé pour grand contenant.",
                [
                    _role("Terreau durable", 0.45, "Terreau horticole"),
                    _role("Matière organique", 0.25, "Compost mûr"),
                    _role("Terre stable", 0.20, "Terre franche / Terre de jardin"),
                    _role("Drainage", 0.10, "Sable grossier"),
                ],
                ("osu_kiwi", "rhs_trees", "rhs_containers"),
            ),
            _variant(
                "Terre franche enrichie",
                "Variante plus minérale pour culture extérieure en bac.",
                [
                    _role("Terre franche", 0.50, "Terre franche / Terre de jardin"),
                    _role("Terreau horticole", 0.25, "Terreau horticole"),
                    _role("Compost mûr", 0.20, "Compost mûr"),
                    _role("Aération", 0.05, "Écorces de pin"),
                ],
                ("osu_kiwi", "rhs_trees"),
            ),
        ],
    },
    "citrus_loam": {
        "label": "Agrume en contenant",
        "variants": [
            _variant(
                "Loam riche et drainé",
                "Mélange durable avec environ vingt pour cent de sable ou gravier.",
                [
                    _role("Compost de culture", 0.55, "Terreau horticole"),
                    _role("Loam", 0.25, "Terre franche / Terre de jardin"),
                    _role("Drainage", 0.20, "Sable grossier", "Gravier de Quartz"),
                ],
                ("rhs_citrus",),
            )
        ],
    },
    "mediterranean_dry": {
        "label": "Méditerranéenne drainante",
        "variants": [
            _variant(
                "Loam et minéraux",
                "Mélange drainant pour plantes tolérant la sécheresse.",
                [
                    _role("Base", 0.50, "Terreau horticole", "Terre franche / Terre de jardin"),
                    _role("Sable", 0.25, "Sable grossier"),
                    _role("Granulats", 0.25, "Pouzzolane", "Pumice", "Gravier de Quartz"),
                ],
                ("rhs_containers", "rhs_low_carbon_mix"),
            )
        ],
    },
    "woody_loam": {
        "label": "Arbre, arbuste ou liane durable",
        "variants": [
            _variant(
                "Loam durable enrichi",
                "Mélange lourd et stable pour culture longue en contenant.",
                [
                    _role("Loam", 0.55, "Terre franche / Terre de jardin"),
                    _role("Terreau", 0.25, "Terreau horticole"),
                    _role("Organique", 0.10, "Compost mûr"),
                    _role("Drainage", 0.10, "Sable grossier", "Gravier de Quartz"),
                ],
                ("rhs_trees", "rhs_containers", "rhs_low_carbon_mix"),
            ),
            _variant(
                "Terreau horticole structuré",
                "Variante plus légère pour pots mobiles.",
                [
                    _role("Terreau", 0.55, "Terreau horticole"),
                    _role("Terre", 0.20, "Terre franche / Terre de jardin"),
                    _role("Écorces", 0.15, "Écorces de pin"),
                    _role("Drainage", 0.10, "Sable grossier", "Perlite"),
                ],
                ("rhs_trees", "rhs_containers"),
            ),
        ],
    },
    "tropical_moist": {
        "label": "Tropicale humifère",
        "variants": [
            _variant(
                "Humifère et aéré",
                "Mélange retenant l'humidité sans rester saturé.",
                [
                    _role("Base", 0.50, "Terreau plantes vertes", "Terreau horticole"),
                    _role("Rétention", 0.20, "Fibre de coco"),
                    _role("Humus", 0.15, "Terreau de feuilles"),
                    _role("Aération", 0.15, "Perlite", "Pumice"),
                ],
                ("rhs_houseplants", "rhs_containers"),
            ),
            _variant(
                "Terreau léger et coco",
                "Variante simple pour intérieur.",
                [
                    _role("Terreau léger", 0.55, "Terreau léger", "Terreau plantes vertes"),
                    _role("Coco", 0.25, "Fibre de coco"),
                    _role("Drainage", 0.20, "Perlite", "Pumice"),
                ],
                ("rhs_houseplants",),
            ),
        ],
    },
    "general_container": {
        "label": "Plante générale en contenant",
        "variants": [
            _variant(
                "Terreau horticole équilibré",
                "Recette polyvalente fondée sur les recommandations générales de culture en bac.",
                [
                    _role("Base", 0.55, "Terreau horticole"),
                    _role("Terre stable", 0.20, "Terre franche / Terre de jardin"),
                    _role("Matière organique", 0.15, "Compost mûr"),
                    _role("Drainage", 0.10, "Sable grossier", "Perlite"),
                ],
                ("rhs_containers", "rhs_low_carbon_mix"),
            ),
            _variant(
                "Terreau léger drainé",
                "Variante plus légère pour petites plantes et pots mobiles.",
                [
                    _role("Base légère", 0.60, "Terreau léger", "Terreau horticole"),
                    _role("Coco", 0.20, "Fibre de coco"),
                    _role("Drainage", 0.20, "Perlite", "Sable grossier"),
                ],
                ("rhs_containers", "rhs_houseplants"),
            ),
        ],
    },
}

AQUATIC_FAMILIES = {
    "nelumbonaceae", "nymphaeaceae", "cabombaceae", "hydrocharitaceae",
    "aponogetonaceae", "pontederiaceae", "alismataceae", "butomaceae",
    "menyanthaceae", "typhaceae", "juncaginaceae",
}
CARNIVOROUS_FAMILIES = {
    "sarraceniaceae", "droseraceae", "nepenthaceae", "lentibulariaceae",
    "cephalotaceae", "drosophyllaceae", "roridulaceae",
}
SUCCULENT_FAMILIES = {
    "cactaceae", "crassulaceae", "aizoaceae", "didiereaceae",
    "portulacaceae", "anacampserotaceae",
}
FERN_FAMILIES = {
    "polypodiaceae", "pteridaceae", "aspleniaceae", "dryopteridaceae",
    "blechnaceae", "davalliaceae", "nephrolepidaceae", "cyatheaceae",
    "dicksoniaceae", "osmundaceae", "marattiaceae", "thelypteridaceae",
    "athyriaceae", "dennstaedtiaceae", "woodsiaceae", "onocleaceae",
    "plagiogyriaceae", "gleicheniaceae", "hymenophyllaceae",
}
ACID_FAMILIES = {"ericaceae", "theaceae", "clethraceae", "cyrillaceae"}
TROPICAL_FOLIAGE_FAMILIES = {
    "araceae", "marantaceae", "strelitziaceae", "musaceae", "begoniaceae",
    "gesneriaceae", "acanthaceae", "commelinaceae", "costaceae", "zingiberaceae",
}

SUCCULENT_GENERA = {
    "aloe", "agave", "haworthia", "haworthiopsis", "gasteria", "euphorbia",
    "sansevieria", "dracaena", "yucca", "beaucarnea", "adenium", "pachypodium",
    "stapelia", "huernia", "senecio", "curio", "lithops", "conophytum",
}
EPIPHYTIC_FERN_GENERA = {"platycerium", "phlebodium", "davallia", "microsorum", "drynaria"}
MEDITERRANEAN_GENERA = {
    "lavandula", "rosmarinus", "salvia", "thymus", "origanum", "santolina",
    "cistus", "olea", "myrtus", "phlomis", "helichrysum", "arbutus",
}
WOODY_WORDS = ("arbre", "arbuste", "liane", "grimpante", "woody", "tree", "shrub", "vine")
AQUATIC_WORDS = (
    "aquatique", "submerge", "immerge", "nenuphar", "lotus", "water lily",
    "pond plant", "plante de bassin", "eau stagnante", "rhizome dans la vase",
)
EPIPHYTE_WORDS = ("epiphyte", "epiphytique", "racines aeriennes")


def _taxonomy(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    taxonomy = profile.get("taxonomie", {})
    return taxonomy if isinstance(taxonomy, Mapping) else {}


def profile_identity(profile: Mapping[str, Any]) -> tuple[str, str, str, str]:
    taxonomy = _taxonomy(profile)
    scientific = str(taxonomy.get("nom_scientifique") or profile.get("nom_sci") or "").strip()
    family = str(taxonomy.get("famille") or profile.get("famille") or "").strip()
    genus_match = re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", scientific)
    genus = genus_match.group(0) if genus_match else ""
    haystack = normalize_text(json.dumps(profile, ensure_ascii=False, default=str))
    return scientific, family, genus, haystack


def classify_profile(profile: Mapping[str, Any]) -> str:
    scientific, family, genus, haystack = profile_identity(profile)
    family_key = normalize_text(family)
    genus_key = normalize_text(genus)
    scientific_key = normalize_text(scientific)

    if genus_key == "nelumbo":
        return "lotus_heavy"
    if genus_key == "drosophyllum":
        return "drosophyllum_dry"
    if genus_key == "nepenthes":
        return "nepenthes_epiphyte"
    if genus_key == "pinguicula" and any(word in haystack for word in ("mexique", "mexico", "dolomie", "calcaire")):
        return "pinguicula_mineral"
    if family_key in CARNIVOROUS_FAMILIES or any(
        name in scientific_key for name in ("dionaea", "drosera", "sarracenia", "darlingtonia", "heliamphora", "cephalotus", "utricularia", "genlisea")
    ):
        return "carnivorous_bog"
    if family_key in AQUATIC_FAMILIES or any(word in haystack for word in AQUATIC_WORDS):
        return "aquatic_heavy"
    if family_key == "orchidaceae":
        return "orchid_epiphyte"
    if family_key in SUCCULENT_FAMILIES or genus_key in SUCCULENT_GENERA or any(
        word in haystack for word in ("cactee", "cactus", "succulente", "plante grasse")
    ):
        return "succulent_mineral"
    if family_key == "bromeliaceae":
        return "bromeliad_epiphyte"
    if family_key in FERN_FAMILIES:
        if genus_key in EPIPHYTIC_FERN_GENERA or any(word in haystack for word in EPIPHYTE_WORDS):
            return "epiphytic_fern"
        return "fern_humus"
    if genus_key == "actinidia":
        return "actinidia_fruit_vine"
    if genus_key in {"citrus", "fortunella", "poncirus"}:
        return "citrus_loam"
    if family_key in ACID_FAMILIES or any(word in haystack for word in ("acidophile", "ericace", "terre acide", "ph 4", "ph 5")):
        return "acid_ericaceous"
    if family_key == "araceae" or any(word in haystack for word in EPIPHYTE_WORDS):
        return "aroid_chunky"
    if genus_key in MEDITERRANEAN_GENERA or any(word in haystack for word in ("mediterraneen", "garrigue", "maquis")):
        return "mediterranean_dry"
    if family_key in TROPICAL_FOLIAGE_FAMILIES or any(word in haystack for word in ("tropical", "foret humide", "hygrometrie 70")):
        return "tropical_moist"
    if any(word in haystack for word in WOODY_WORDS):
        return "woody_loam"
    return "general_container"


def _clean_variant(variant: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(variant))
    clean_roles: list[dict[str, Any]] = []
    for role in result.get("roles", []):
        ingredients: list[str] = []
        for ingredient in role.get("ing", []):
            canonical = canonicalize_ingredient(ingredient)
            if canonical and canonical not in ingredients:
                ingredients.append(canonical)
        if ingredients:
            clean_roles.append({
                "nom": str(role.get("nom") or "Composant"),
                "ratio": float(role.get("ratio", 0)),
                "ing": ingredients,
            })
    total = sum(role["ratio"] for role in clean_roles)
    if total <= 0:
        raise ValueError("Une variante de substrat ne contient aucun ratio positif.")
    for role in clean_roles:
        role["ratio"] = round(role["ratio"] / total, 6)
    # Corrige l'arrondi sur la dernière ligne.
    clean_roles[-1]["ratio"] = round(1 - sum(role["ratio"] for role in clean_roles[:-1]), 6)
    result["roles"] = clean_roles
    result["interdits"] = [
        canonical for item in result.get("interdits", [])
        if (canonical := canonicalize_ingredient(item))
    ]
    return result


def resolved_substrate(profile: Mapping[str, Any]) -> dict[str, Any]:
    substrate = profile.get("substrat", {})
    substrate = substrate if isinstance(substrate, Mapping) else {}
    stored = substrate.get("variantes")
    if isinstance(stored, list) and stored:
        variants = [_clean_variant(item) for item in stored[:2] if isinstance(item, Mapping)]
        template_id = str(substrate.get("modele_recherche") or classify_profile(profile))
        return {
            "modele": template_id,
            "categorie": str(substrate.get("categorie_horticole") or TEMPLATES.get(template_id, {}).get("label", template_id)),
            "variantes": variants,
            "version_recherche": str(substrate.get("version_recherche") or "2026.08"),
        }
    template_id = classify_profile(profile)
    template = TEMPLATES[template_id]
    return {
        "modele": template_id,
        "categorie": template["label"],
        "variantes": [_clean_variant(item) for item in template["variants"][:2]],
        "version_recherche": "2026.08",
    }


def enrich_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    enriched = copy.deepcopy(dict(profile))
    resolved = resolved_substrate(enriched)
    variants = resolved["variantes"]
    substrate = enriched.get("substrat", {})
    substrate = copy.deepcopy(dict(substrate)) if isinstance(substrate, Mapping) else {}
    substrate.update({
        "categorie_horticole": resolved["categorie"],
        "modele_recherche": resolved["modele"],
        "version_recherche": resolved["version_recherche"],
        "variantes": variants,
        "composition_ideale": " / ".join(
            f"{role['ratio'] * 100:.0f}% {role['ing'][0]}" for role in variants[0]["roles"]
        ),
        "ingredients_recommandes": [
            ingredient
            for role in variants[0]["roles"]
            for ingredient in role["ing"]
        ],
        "elements_interdits": variants[0].get("interdits", []),
        "sources": variants[0].get("sources", []),
    })
    enriched["substrat"] = substrate
    enriched["roles"] = copy.deepcopy(variants[0]["roles"])
    enriched["interdits"] = list(variants[0].get("interdits", []))
    return enriched


def select_variant(profile: Mapping[str, Any], index: int = 0) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = resolved_substrate(profile)
    variants = resolved["variantes"]
    if not variants:
        raise ValueError("Aucune variante de substrat disponible.")
    index = max(0, min(int(index), len(variants) - 1))
    variant = variants[index]
    selected = copy.deepcopy(dict(profile))
    selected["roles"] = copy.deepcopy(variant["roles"])
    selected["interdits"] = list(variant.get("interdits", []))
    selected["variante_substrat_selectionnee"] = copy.deepcopy(variant)
    return selected, variant


def validate_resolved_profile(profile: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    resolved = resolved_substrate(profile)
    variants = resolved.get("variantes", [])
    if not 1 <= len(variants) <= 2:
        errors.append("Le nombre de variantes doit être compris entre 1 et 2.")
    for variant in variants:
        roles = variant.get("roles", [])
        total = sum(float(role.get("ratio", 0)) for role in roles)
        if abs(total - 1.0) > 0.001:
            errors.append(f"La variante {variant.get('nom')} totalise {total:.4f}.")
        for role in roles:
            for ingredient in role.get("ing", []):
                if ingredient not in CANONICAL_SET:
                    errors.append(f"Ingrédient non canonique: {ingredient}")
        if not variant.get("sources"):
            errors.append(f"La variante {variant.get('nom')} n'a aucune source.")
        used = {ingredient for role in roles for ingredient in role.get("ing", [])}
        conflict = used.intersection(variant.get("interdits", []))
        if conflict:
            errors.append(f"Ingrédients à la fois utilisés et interdits: {sorted(conflict)}")
    return errors

"""Recherche horticole sourcée pour les recettes de substrat (2026.09)."""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any, Callable

RESEARCH_VERSION = "2026.09"

_SOURCE_ROWS = {
    "rhs_media": ("RHS — Compost mixes for houseplants", "https://www.rhs.org.uk/plants/types/houseplants/growing-media-houseplants"),
    "rhs_houseplants": ("RHS — How to grow houseplants", "https://www.rhs.org.uk/plants/types/houseplants/growing-guide"),
    "rhs_containers": ("RHS — Growing plants in containers", "https://www.rhs.org.uk/container-gardening/growing-plants-in-containers"),
    "rhs_epipremnum": ("RHS — How to grow Epipremnum", "https://www.rhs.org.uk/plants/epipremnum/growing-guide"),
    "rhs_hoya": ("RHS — How to grow Hoya", "https://www.rhs.org.uk/plants/hoya/how-to-grow"),
    "rhs_bromeliads": ("RHS — How to grow bromeliads", "https://www.rhs.org.uk/plants/bromeliads/growing-guide"),
    "rhs_epiphytic_ferns": ("RHS — How to grow epiphytic ferns", "https://www.rhs.org.uk/plants/epiphytic-ferns/how-to-grow-epiphytic-ferns"),
    "rhs_phalaenopsis": ("RHS — How to grow Phalaenopsis", "https://www.rhs.org.uk/plants/phalaenopsis/growing-guide"),
    "rhs_cymbidium": ("RHS — How to grow Cymbidium orchids", "https://www.rhs.org.uk/plants/cymbidium-orchids/how-to-grow-cymbidium-orchids"),
    "aos_media": ("American Orchid Society — Potting media", "https://www.aos.org/orchid-care/what-is-the-best-potting-media"),
    "aos_repotting": ("American Orchid Society — Repotting", "https://www.aos.org/orchid-care-and-culture-sheets/repotting"),
    "rhs_carnivorous": ("RHS — How to grow carnivorous plants", "https://www.rhs.org.uk/plants/types/carnivorous/growing-guide"),
    "ncsu_dionaea": ("NC State Extension — Dionaea muscipula", "https://plants.ces.ncsu.edu/plants/dionaea-muscipula/"),
    "umn_succulents": ("University of Minnesota Extension — Cacti and succulents", "https://extension.umn.edu/gardening-minnesota/cacti-and-succulents"),
    "rhs_blueberries": ("RHS — How to grow blueberries", "https://www.rhs.org.uk/fruit/blueberries/grow-your-own"),
    "rhs_citrus": ("RHS — How to grow citrus", "https://www.rhs.org.uk/fruit/citrus/grow-your-own"),
    "osu_kiwi": ("Oregon State University Extension — Growing kiwifruit", "https://extension.oregonstate.edu/catalog/em-9322-growing-kiwifruit-your-home-garden"),
    "rhs_dracaena": ("RHS — How to grow Dracaena", "https://www.rhs.org.uk/plants/dracaena/how-to-grow-dracaena"),
}
SOURCES = {key: {"titre": title, "url": url} for key, (title, url) in _SOURCE_ROWS.items()}


def _role(name: str, ratio: float, ingredients: tuple[str, ...]) -> dict[str, Any]:
    return {"nom": name, "ratio": ratio, "ing": list(ingredients)}


def _variant(
    name: str,
    description: str,
    roles: tuple[tuple[str, float, tuple[str, ...]], ...],
    source_ids: tuple[str, ...],
    forbidden: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "nom": name,
        "description": description,
        "roles": [_role(*role) for role in roles],
        "interdits": list(forbidden),
        "sources": [copy.deepcopy(SOURCES[source_id]) for source_id in source_ids],
    }


RICH_FORBIDDEN = (
    "Terreau horticole", "Terreau plantes vertes", "Terreau de feuilles",
    "Humus de lombric", "Compost mûr",
)
AQUATIC_FORBIDDEN = (
    "Perlite", "Pumice", "Pouzzolane", "Micro-pouzzolane", "Vermiculite",
    "Billes d'argile", "Fibre de coco", "Chips de coco", "Sphaigne sèche",
)

LIBRARY = {
    "aquatic": _variant(
        "Alternative — argile et gravier", "Mélange lourd sans constituant flottant.",
        (("Base argileuse", .75, ("Terreau argileux (Aquatique / Nénuphars)",)),
         ("Terre franche", .20, ("Terre franche / Terre de jardin",)),
         ("Couverture", .05, ("Gravier de Quartz",))),
        ("rhs_containers",), AQUATIC_FORBIDDEN,
    ),
    "bog": _variant(
        "Alternative — tourbe, sable et perlite", "Mélange pauvre, acide et aéré.",
        (("Base acide", .50, ("Tourbe blonde",)),
         ("Sable siliceux", .25, ("Sable de quartz",)),
         ("Aération", .25, ("Perlite",))),
        ("rhs_carnivorous", "ncsu_dionaea"), RICH_FORBIDDEN,
    ),
    "carnivore_dry": _variant(
        "Alternative — quartz et pumice", "Mélange pauvre et très drainant.",
        (("Quartz", .45, ("Sable de quartz",)), ("Pumice", .30, ("Pumice",)),
         ("Aération", .15, ("Perlite",)), ("Tourbe", .10, ("Tourbe blonde",))),
        ("rhs_carnivorous", "umn_succulents"), RICH_FORBIDDEN,
    ),
    "pinguicula": _variant(
        "Alternative — minérale sans tourbe", "Pour grassettes mexicaines en repos sec.",
        (("Pumice", .35, ("Pumice",)), ("Perlite", .25, ("Perlite",)),
         ("Sable", .20, ("Sable grossier",)), ("Vermiculite", .15, ("Vermiculite",)),
         ("Calcaire", .05, ("Poudre de Calcaire / Dolomie",))),
        ("rhs_carnivorous",), RICH_FORBIDDEN,
    ),
    "epiphyte": _variant(
        "Alternative — écorces dominantes", "Support grossier, aéré et rapidement drainant.",
        (("Écorces", .65, ("Écorces de pin",)), ("Rétention", .15, ("Sphaigne sèche", "Fibre de coco")),
         ("Aération", .15, ("Pumice", "Perlite")), ("Charbon", .05, ("Charbon actif",))),
        ("rhs_phalaenopsis", "aos_media", "aos_repotting"),
        ("Terre franche / Terre de jardin", "Terreau argileux (Aquatique / Nénuphars)"),
    ),
    "succulent": _variant(
        "Alternative — quatre cinquièmes minéraux", "Pour les espèces sensibles à la pourriture.",
        (("Base organique", .20, ("Terreau léger", "Terreau horticole")),
         ("Pumice", .30, ("Pumice",)), ("Pouzzolane", .25, ("Pouzzolane", "Micro-pouzzolane")),
         ("Sable", .15, ("Sable grossier",)), ("Gravier", .10, ("Gravier de Quartz",))),
        ("umn_succulents", "rhs_media"), ("Terreau argileux (Aquatique / Nénuphars)",),
    ),
    "fern": _variant(
        "Alternative — coco, feuilles et minéraux", "Fin, humide et aéré pour racines fibreuses.",
        (("Feuilles", .35, ("Terreau de feuilles",)), ("Coco", .30, ("Fibre de coco",)),
         ("Terreau", .20, ("Terreau léger",)), ("Aération", .10, ("Perlite", "Pumice")),
         ("Charbon", .05, ("Charbon actif",))),
        ("rhs_epiphytic_ferns", "rhs_media"),
    ),
    "bromeliad": _variant(
        "Alternative — trois tiers RHS", "Écorces, coco et fraction minérale en parts égales.",
        (("Écorces", 1/3, ("Écorces de pin",)), ("Coco", 1/3, ("Fibre de coco",)),
         ("Drainage", 1/3, ("Gravier de Quartz", "Sable grossier", "Pumice"))),
        ("rhs_bromeliads",),
    ),
    "aroid": _variant(
        "Alternative — mélange aroïde complet", "Composants optimaux pour racines épaisses.",
        (("Coco", .25, ("Fibre de coco",)), ("Écorces", .20, ("Écorces de pin",)),
         ("Pumice", .15, ("Pumice",)), ("Perlite", .10, ("Perlite",)),
         ("Terreau", .15, ("Terreau plantes vertes",)), ("Humus", .05, ("Humus de lombric",)),
         ("Zéolite", .05, ("Zéolite",)), ("Charbon", .05, ("Charbon actif",))),
        ("rhs_media", "rhs_epipremnum"),
    ),
    "acid": _variant(
        "Alternative — tourbe, kanuma et écorces", "Mélange acide sans amendement calcaire.",
        (("Tourbe", .40, ("Tourbe blonde",)), ("Kanuma", .25, ("Kanuma",)),
         ("Écorces", .20, ("Écorces de pin",)), ("Feuilles", .10, ("Terreau de feuilles",)),
         ("Quartz", .05, ("Sable de quartz",))),
        ("rhs_blueberries", "rhs_containers"), ("Poudre de Calcaire / Dolomie",),
    ),
    "fruit": _variant(
        "Alternative — sol organique drainé", "Terre durable, matière organique et drainage.",
        (("Terre", .40, ("Terre franche / Terre de jardin",)),
         ("Terreau", .25, ("Terreau horticole",)), ("Compost", .20, ("Compost mûr",)),
         ("Écorces", .10, ("Écorces de pin",)), ("Sable", .05, ("Sable grossier",))),
        ("osu_kiwi", "rhs_containers"),
    ),
    "citrus": _variant(
        "Alternative — loam à vingt pour cent minéral", "Formule stable et drainante pour agrumes.",
        (("Terreau", .50, ("Terreau horticole",)), ("Terre", .25, ("Terre franche / Terre de jardin",)),
         ("Compost", .05, ("Compost mûr",)), ("Drainage", .20, ("Sable grossier", "Gravier de Quartz"))),
        ("rhs_citrus", "rhs_containers"),
    ),
    "dry": _variant(
        "Alternative — minérale renforcée", "Pour climat humide ou hivernage frais.",
        (("Base", .30, ("Terreau léger",)), ("Pumice", .25, ("Pumice",)),
         ("Pouzzolane", .20, ("Pouzzolane",)), ("Sable", .15, ("Sable grossier",)),
         ("Gravier", .10, ("Gravier de Quartz",))),
        ("rhs_containers", "umn_succulents"),
    ),
    "woody": _variant(
        "Alternative — loam, compost et écorces", "Stable et durable pour grand contenant.",
        (("Terre", .40, ("Terre franche / Terre de jardin",)), ("Terreau", .25, ("Terreau horticole",)),
         ("Compost", .15, ("Compost mûr",)), ("Écorces", .10, ("Écorces de pin",)),
         ("Drainage", .10, ("Gravier de Quartz", "Sable grossier"))),
        ("rhs_containers", "osu_kiwi"),
    ),
    "tropical": _variant(
        "Alternative — tropicale complète", "Fine mais poreuse, avec rétention et nutrition modérées.",
        (("Terreau", .35, ("Terreau plantes vertes",)), ("Coco", .20, ("Fibre de coco",)),
         ("Feuilles", .15, ("Terreau de feuilles",)), ("Écorces", .10, ("Écorces de pin",)),
         ("Aération", .10, ("Pumice", "Perlite")), ("Humus", .05, ("Humus de lombric",)),
         ("Charbon", .05, ("Charbon actif",))),
        ("rhs_media", "rhs_houseplants"),
    ),
    "general": _variant(
        "Alternative — mélange polyvalent complet", "Stabilité, aération et nutrition équilibrées.",
        (("Terreau", .35, ("Terreau horticole",)), ("Terre", .20, ("Terre franche / Terre de jardin",)),
         ("Coco", .15, ("Fibre de coco",)), ("Compost", .10, ("Compost mûr",)),
         ("Écorces", .10, ("Écorces de pin",)), ("Drainage", .10, ("Pumice", "Perlite", "Sable grossier"))),
        ("rhs_containers", "rhs_media", "rhs_houseplants"),
    ),
}

EXTRA_BY_TEMPLATE = {
    "lotus_heavy": ("aquatic",), "aquatic_heavy": ("aquatic",),
    "carnivorous_bog": ("bog",), "pinguicula_mineral": ("pinguicula", "bog"),
    "nepenthes_epiphyte": ("epiphyte",), "drosophyllum_dry": ("carnivore_dry", "dry"),
    "orchid_epiphyte": ("epiphyte",), "succulent_mineral": ("succulent",),
    "epiphytic_fern": ("fern",), "fern_humus": ("fern", "tropical"),
    "bromeliad_epiphyte": ("bromeliad",), "aroid_chunky": ("aroid",),
    "acid_ericaceous": ("acid",), "actinidia_fruit_vine": ("fruit",),
    "citrus_loam": ("citrus", "fruit"), "mediterranean_dry": ("dry", "succulent"),
    "woody_loam": ("woody",), "tropical_moist": ("tropical",),
    "general_container": ("general",),
}

PRIMARY_SOURCES = {
    "carnivorous_bog": ("rhs_carnivorous", "ncsu_dionaea"),
    "pinguicula_mineral": ("rhs_carnivorous",), "nepenthes_epiphyte": ("rhs_carnivorous", "aos_repotting"),
    "drosophyllum_dry": ("rhs_carnivorous", "umn_succulents"),
    "orchid_epiphyte": ("rhs_phalaenopsis", "aos_media", "aos_repotting"),
    "succulent_mineral": ("umn_succulents", "rhs_media"),
    "epiphytic_fern": ("rhs_epiphytic_ferns", "rhs_media"),
    "fern_humus": ("rhs_media", "rhs_houseplants"),
    "bromeliad_epiphyte": ("rhs_bromeliads", "rhs_media"),
    "aroid_chunky": ("rhs_epipremnum", "rhs_media"),
    "acid_ericaceous": ("rhs_blueberries", "rhs_containers"),
    "actinidia_fruit_vine": ("osu_kiwi", "rhs_containers"),
    "citrus_loam": ("rhs_citrus", "rhs_containers"),
    "mediterranean_dry": ("rhs_containers", "umn_succulents"),
    "woody_loam": ("rhs_containers", "osu_kiwi"),
    "tropical_moist": ("rhs_media", "rhs_houseplants"),
    "general_container": ("rhs_containers", "rhs_media"),
    "lotus_heavy": ("rhs_containers",), "aquatic_heavy": ("rhs_containers",),
}


def _template(label: str, primary_key: str, alt_keys: tuple[str, str]) -> dict[str, Any]:
    primary = copy.deepcopy(LIBRARY[primary_key])
    primary["nom"] = primary["nom"].replace("Alternative", "Principale", 1)
    return {"label": label, "variants": [primary, *(copy.deepcopy(LIBRARY[key]) for key in alt_keys)]}


NEW_TEMPLATES = {
    "hoya_epiphyte": _template("Hoya ou Dischidia épiphyte", "aroid", ("epiphyte", "general")),
    "orchid_terrestrial": _template("Orchidée terrestre ou semi-terrestre", "fern", ("epiphyte", "tropical")),
    "palm_container": _template("Palmier en contenant", "tropical", ("woody", "general")),
    "dracaena_dry": _template("Dracaena, Yucca ou plante à réserve", "dry", ("succulent", "general")),
    "air_plant_mount": {
        "label": "Tillandsia épiphyte sans terre",
        "variants": [
            _variant("Principale — montage sur écorce", "Support uniquement : ne pas enterrer la plante.",
                     (("Support", 1.0, ("Écorces de pin",)),), ("rhs_bromeliads",),
                     ("Terreau horticole", "Terreau plantes vertes", "Terre franche / Terre de jardin")),
            _variant("Alternative — écorce et charbon", "Support ouvert sans eau au collet.",
                     (("Support", .80, ("Écorces de pin",)), ("Charbon", .20, ("Charbon actif",))),
                     ("rhs_bromeliads", "rhs_media")),
            _variant("Alternative — peu de sphaigne", "Rétention très localisée en atmosphère sèche.",
                     (("Support", .85, ("Écorces de pin",)), ("Sphaigne", .15, ("Sphaigne sèche",))),
                     ("rhs_bromeliads",)),
        ],
    },
}

GENUS_ASSIGNMENTS = {
    "hoya": "hoya_epiphyte", "dischidia": "hoya_epiphyte",
    "cymbidium": "orchid_terrestrial", "paphiopedilum": "orchid_terrestrial",
    "phragmipedium": "orchid_terrestrial", "ludisia": "orchid_terrestrial",
    "habenaria": "orchid_terrestrial", "bletilla": "orchid_terrestrial",
    "spathoglottis": "orchid_terrestrial", "calanthe": "orchid_terrestrial",
    "dracaena": "dracaena_dry", "sansevieria": "dracaena_dry",
    "yucca": "dracaena_dry", "beaucarnea": "dracaena_dry",
    "zamioculcas": "dracaena_dry", "tillandsia": "air_plant_mount",
}
FAMILY_ASSIGNMENTS = {"arecaceae": "palm_container"}


def _merge_sources(variant: dict[str, Any], source_ids: tuple[str, ...]) -> None:
    sources = variant.setdefault("sources", [])
    urls = {str(item.get("url", "")) for item in sources if isinstance(item, Mapping)}
    for source_id in source_ids:
        source = SOURCES[source_id]
        if source["url"] not in urls:
            sources.append(copy.deepcopy(source))
            urls.add(source["url"])


def _name_variants(variants: list[dict[str, Any]]) -> None:
    for index, variant in enumerate(variants):
        name = str(variant.get("nom") or f"Variante {index + 1}")
        if index == 0 and not name.startswith("Principale"):
            variant["nom"] = f"Principale — {name}"
        elif index and not name.startswith("Alternative"):
            variant["nom"] = f"Alternative {index} — {name}"


def _patch_runtime(knowledge: Any, classify: Callable[[Mapping[str, Any]], str]) -> None:
    def resolved(profile: Mapping[str, Any]) -> dict[str, Any]:
        substrate = profile.get("substrat", {})
        substrate = substrate if isinstance(substrate, Mapping) else {}
        template_id = str(substrate.get("modele_recherche") or classify(profile))
        template = knowledge.TEMPLATES.get(template_id) or knowledge.TEMPLATES["general_container"]
        variants: list[dict[str, Any]] = []
        stored = substrate.get("variantes")
        stored_version = str(substrate.get("version_recherche") or "")
        if isinstance(stored, list) and stored and stored_version >= RESEARCH_VERSION:
            variants.extend(knowledge._clean_variant(item) for item in stored[:3] if isinstance(item, Mapping))
        names = {str(item.get("nom", "")) for item in variants}
        for item in template["variants"]:
            clean = knowledge._clean_variant(item)
            if str(clean.get("nom", "")) not in names:
                variants.append(clean)
                names.add(str(clean.get("nom", "")))
            if len(variants) == 3:
                break
        _name_variants(variants)
        return {
            "modele": template_id,
            "categorie": str(substrate.get("categorie_horticole") or template.get("label", template_id)),
            "variantes": variants[:3],
            "version_recherche": RESEARCH_VERSION,
        }

    def enrich(profile: Mapping[str, Any]) -> dict[str, Any]:
        enriched = copy.deepcopy(dict(profile))
        result = resolved(enriched)
        variants = result["variantes"]
        substrate = enriched.get("substrat", {})
        substrate = copy.deepcopy(dict(substrate)) if isinstance(substrate, Mapping) else {}
        substrate.update({
            "categorie_horticole": result["categorie"], "modele_recherche": result["modele"],
            "version_recherche": RESEARCH_VERSION, "variantes": copy.deepcopy(variants),
            "composition_ideale": " / ".join(
                f"{role['ratio'] * 100:.0f}% {role['ing'][0]}" for role in variants[0]["roles"]
            ),
            "ingredients_recommandes": [item for role in variants[0]["roles"] for item in role["ing"]],
            "elements_interdits": list(variants[0].get("interdits", [])),
            "sources": copy.deepcopy(variants[0].get("sources", [])),
        })
        enriched["substrat"] = substrate
        enriched["roles"] = copy.deepcopy(variants[0]["roles"])
        enriched["interdits"] = list(variants[0].get("interdits", []))
        return enriched

    def select(profile: Mapping[str, Any], index: int = 0) -> tuple[dict[str, Any], dict[str, Any]]:
        variants = resolved(profile)["variantes"]
        if not variants:
            raise ValueError("Aucune variante de substrat disponible.")
        index = max(0, min(int(index), len(variants) - 1))
        variant = variants[index]
        selected = copy.deepcopy(dict(profile))
        selected["roles"] = copy.deepcopy(variant["roles"])
        selected["interdits"] = list(variant.get("interdits", []))
        selected["variante_substrat_selectionnee"] = copy.deepcopy(variant)
        return selected, variant

    def validate(profile: Mapping[str, Any]) -> list[str]:
        errors: list[str] = []
        variants = resolved(profile)["variantes"]
        if not 2 <= len(variants) <= 3:
            errors.append("Le nombre de variantes doit être compris entre 2 et 3.")
        for variant in variants:
            roles = variant.get("roles", [])
            total = sum(float(role.get("ratio", 0)) for role in roles)
            if abs(total - 1.0) > .001:
                errors.append(f"La variante {variant.get('nom')} totalise {total:.4f}.")
            for role in roles:
                unknown = set(role.get("ing", ())) - knowledge.CANONICAL_SET
                errors.extend(f"Ingrédient non canonique: {item}" for item in sorted(unknown))
            if not variant.get("sources"):
                errors.append(f"La variante {variant.get('nom')} n'a aucune source.")
            used = {item for role in roles for item in role.get("ing", ())}
            conflict = used.intersection(variant.get("interdits", ()))
            if conflict:
                errors.append(f"Ingrédients utilisés et interdits: {sorted(conflict)}")
        return errors

    knowledge.resolved_substrate = resolved
    knowledge.enrich_profile = enrich
    knowledge.select_variant = select
    knowledge.validate_resolved_profile = validate


def install(
    knowledge: Any,
    family_template: dict[str, str],
    genus_template: dict[str, str],
    classify_profile: Callable[[Mapping[str, Any]], str],
) -> None:
    knowledge.SOURCES.update(copy.deepcopy(SOURCES))
    family_template.update(FAMILY_ASSIGNMENTS)
    genus_template.update(GENUS_ASSIGNMENTS)
    knowledge.TEMPLATES.update(copy.deepcopy(NEW_TEMPLATES))
    for template_id, template in knowledge.TEMPLATES.items():
        variants = template.setdefault("variants", [])
        for key in EXTRA_BY_TEMPLATE.get(template_id, ()):
            if len(variants) >= 3:
                break
            variants.append(copy.deepcopy(LIBRARY[key]))
        if variants:
            _merge_sources(variants[0], PRIMARY_SOURCES.get(template_id, ("rhs_containers",)))
        for variant in variants:
            if not variant.get("sources"):
                _merge_sources(variant, ("rhs_containers",))
        _name_variants(variants)
    knowledge.classify_profile = classify_profile
    _patch_runtime(knowledge, classify_profile)

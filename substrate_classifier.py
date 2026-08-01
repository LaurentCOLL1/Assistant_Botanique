"""Classification horticole prudente des fiches pour les modèles de substrat.

La classification ne lit volontairement pas les anciennes compositions de
substrat, leurs interdits, les maladies ni un simple fragment de pH. Ces champs
étaient souvent génériques et provoquaient des classifications circulaires.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import substrate_knowledge as knowledge


FAMILY_TEMPLATE: dict[str, str] = {}


def _families(template: str, *names: str) -> None:
    for name in names:
        FAMILY_TEMPLATE[knowledge.normalize_text(name)] = template


_families(
    "aquatic_heavy",
    "Alismataceae",
)
_families(
    "carnivorous_bog",
    "Byblidaceae",
    "Cephalotaceae",
    "Dioncophyllaceae",
    "Droseraceae",
    "Lentibulariaceae",
    "Roridulaceae",
    "Sarraceniaceae",
)
_families("nepenthes_epiphyte", "Nepenthaceae")
_families("drosophyllum_dry", "Drosophyllaceae")
_families("orchid_epiphyte", "Orchidaceae")
_families(
    "succulent_mineral",
    "Aizoaceae",
    "Anacampserotaceae",
    "Cactaceae",
    "Crassulaceae",
    "Didiereaceae",
)
_families("bromeliad_epiphyte", "Bromeliaceae")
_families("epiphytic_fern", "Polypodiaceae")
_families("fern_humus", "Aspleniaceae", "Nephrolepidaceae")
_families("acid_ericaceous", "Ericaceae", "Myricaceae", "Proteaceae")
_families("aroid_chunky", "Araceae", "Cyclanthaceae")
_families(
    "tropical_moist",
    "Acanthaceae",
    "Araliaceae",
    "Arecaceae",
    "Balsaminaceae",
    "Begoniaceae",
    "Cannaceae",
    "Commelinaceae",
    "Costaceae",
    "Gesneriaceae",
    "Heliconiaceae",
    "Marantaceae",
    "Musaceae",
    "Pandanaceae",
    "Piperaceae",
    "Strelitziaceae",
    "Zingiberaceae",
)
_families("mediterranean_dry", "Cistaceae")
_families(
    "woody_loam",
    "Anacardiaceae",
    "Annonaceae",
    "Aquifoliaceae",
    "Berberidaceae",
    "Betulaceae",
    "Bignoniaceae",
    "Burseraceae",
    "Buxaceae",
    "Calycanthaceae",
    "Caprifoliaceae",
    "Celastraceae",
    "Combretaceae",
    "Cornaceae",
    "Cycadaceae",
    "Ebenaceae",
    "Fagaceae",
    "Juglandaceae",
    "Lardizabalaceae",
    "Lauraceae",
    "Magnoliaceae",
    "Moraceae",
    "Myrtaceae",
    "Oleaceae",
    "Pinaceae",
    "Rosaceae",
    "Rutaceae",
    "Salicaceae",
    "Sapindaceae",
    "Sapotaceae",
    "Schisandraceae",
    "Viburnaceae",
    "Vitaceae",
    "Zamiaceae",
)

GENUS_TEMPLATE: dict[str, str] = {}


def _genera(template: str, *names: str) -> None:
    for name in names:
        GENUS_TEMPLATE[knowledge.normalize_text(name)] = template


_genera("lotus_heavy", "Nelumbo")
_genera(
    "aquatic_heavy",
    "Alisma",
    "Aponogeton",
    "Butomus",
    "Cabomba",
    "Echinodorus",
    "Eichhornia",
    "Hydrocharis",
    "Nuphar",
    "Nymphaea",
    "Pontederia",
    "Sagittaria",
    "Vallisneria",
)
_genera(
    "carnivorous_bog",
    "Byblis",
    "Cephalotus",
    "Darlingtonia",
    "Dionaea",
    "Drosera",
    "Genlisea",
    "Heliamphora",
    "Roridula",
    "Sarracenia",
    "Utricularia",
)
_genera("nepenthes_epiphyte", "Nepenthes")
_genera("drosophyllum_dry", "Drosophyllum")
_genera("pinguicula_mineral", "Pinguicula")
_genera(
    "succulent_mineral",
    "Adenium",
    "Agave",
    "Aloe",
    "Anacampseros",
    "Astrophytum",
    "Beaucarnea",
    "Conophytum",
    "Crassula",
    "Curio",
    "Echeveria",
    "Gasteria",
    "Haworthia",
    "Haworthiopsis",
    "Huernia",
    "Kalanchoe",
    "Lithops",
    "Mammillaria",
    "Opuntia",
    "Pachypodium",
    "Sansevieria",
    "Schlumbergera",
    "Sedum",
    "Sempervivum",
    "Stapelia",
)
_genera(
    "aroid_chunky",
    "Dischidia",
    "Hoya",
    "Monstera",
    "Philodendron",
    "Scindapsus",
)
_genera("actinidia_fruit_vine", "Actinidia")
_genera("citrus_loam", "Citrus", "Fortunella", "Poncirus")
_genera(
    "acid_ericaceous",
    "Azalea",
    "Camellia",
    "Gardenia",
    "Kalmia",
    "Pieris",
    "Rhododendron",
    "Vaccinium",
)
_genera(
    "mediterranean_dry",
    "Arbutus",
    "Cistus",
    "Helichrysum",
    "Lavandula",
    "Myrtus",
    "Olea",
    "Origanum",
    "Phlomis",
    "Rosmarinus",
    "Santolina",
    "Thymus",
)


AQUATIC_TERMS = (
    "plante aquatique",
    "plante de bassin",
    "plante submergee",
    "plante immergee",
    "rhizome dans la vase",
    "nenuphar",
    "water lily",
)
EPIPHYTIC_TERMS = ("plante epiphyte", "port epiphyte", "racines aeriennes")
SUCCULENT_TERMS = ("plante succulente", "plante grasse", "cactee", "cactus")
MEDITERRANEAN_TERMS = ("origine mediterraneenne", "region mediterraneenne", "garrigue", "maquis")
WOODY_TERMS = ("port arbustif", "port arborescent", "arbre", "arbuste", "liane ligneuse")


def _taxonomy(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    value = profile.get("taxonomie", {})
    return value if isinstance(value, Mapping) else {}


def _descriptive_text(profile: Mapping[str, Any]) -> str:
    """Construit un texte sans les anciens champs de substrat et de santé."""
    taxonomy = _taxonomy(profile)
    morphology = profile.get("morphologie", {})
    climate = profile.get("exigences_climatiques", {})
    pieces = {
        "taxonomie": taxonomy,
        "morphologie": morphology if isinstance(morphology, Mapping) else {},
        "climat": climate if isinstance(climate, Mapping) else {},
        "conseil": profile.get("conseil", ""),
    }
    return knowledge.normalize_text(json.dumps(pieces, ensure_ascii=False, default=str))


def classify_profile(profile: Mapping[str, Any]) -> str:
    taxonomy = _taxonomy(profile)
    scientific = str(taxonomy.get("nom_scientifique") or profile.get("nom_sci") or "").strip()
    family = knowledge.normalize_text(taxonomy.get("famille") or profile.get("famille") or "")
    genus = knowledge.normalize_text(scientific.split()[0] if scientific.split() else "")
    text = _descriptive_text(profile)

    genus_template = GENUS_TEMPLATE.get(genus)
    if genus_template:
        return genus_template

    family_template = FAMILY_TEMPLATE.get(family)
    if family_template:
        return family_template

    if any(term in text for term in AQUATIC_TERMS):
        return "aquatic_heavy"
    if any(term in text for term in SUCCULENT_TERMS):
        return "succulent_mineral"
    if any(term in text for term in EPIPHYTIC_TERMS):
        return "aroid_chunky"
    if any(term in text for term in MEDITERRANEAN_TERMS):
        return "mediterranean_dry"
    if any(term in text for term in WOODY_TERMS):
        return "woody_loam"
    return "general_container"


def install() -> None:
    """Installe cette classification dans la base de connaissances chargée."""
    knowledge.AQUATIC_WORDS = tuple(
        word for word in knowledge.AQUATIC_WORDS if word != "eau stagnante"
    )
    knowledge.classify_profile = classify_profile

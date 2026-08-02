"""Décision d'arrosage fondée sur l'état réel du substrat et la fiche botanique.

Le calendrier indique quand contrôler. Ce module répond à une autre question :
une fois le substrat observé comme sec, humide ou trempé, faut-il arroser ?

Les règles sont volontairement prudentes :
- un substrat trempé n'est jamais arrosé ;
- la plupart des plantes sont arrosées lorsque le substrat est sec ;
- seules les plantes explicitement aquatiques, palustres ou de tourbière peuvent
  demander un réapprovisionnement lorsque le substrat est encore humide ;
- un repos saisonnier défini par la fiche bloque l'arrosage automatique.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from core import family_name, normalize_text, scientific_name, water_interval

SOIL_DRY = "dry"
SOIL_MOIST = "moist"
SOIL_WET = "wet"
SOIL_STATES = (SOIL_DRY, SOIL_MOIST, SOIL_WET)

SOIL_LABELS = {
    SOIL_DRY: "Sec",
    SOIL_MOIST: "Humide",
    SOIL_WET: "Trempé",
}

SOIL_EVENT_TYPES = {
    SOIL_DRY: "substrat_sec",
    SOIL_MOIST: "substrat_humide",
    SOIL_WET: "substrat_trempe",
}

EVENT_TO_SOIL = {
    "substrat_sec": SOIL_DRY,
    "controle_sec": SOIL_DRY,
    "substrat_humide": SOIL_MOIST,
    "encore_humide": SOIL_MOIST,
    "controle_humide": SOIL_MOIST,
    "substrat_trempe": SOIL_WET,
    "controle_trempe": SOIL_WET,
}

# Références consultées pour construire les classes horticoles.
RESEARCH_SOURCES = {
    "general": "https://extension.illinois.edu/houseplants/watering",
    "rhs_general": "https://www.rhs.org.uk/plants/types/houseplants/growing-guide",
    "succulents": "https://www.rhs.org.uk/plants/types/cacti-succulents/houseplants/growing-guide/",
    "carnivorous": "https://www.rhs.org.uk/plants/types/carnivorous",
    "ferns": "https://www.rhs.org.uk/plants/types/ferns/growing-guide",
    "orchids": "https://www.rhs.org.uk/plants/phalaenopsis",
    "overwatering": "https://extension.uconn.edu/2013/12/24/watering-houseplants/",
}

# Genres dont le substrat est normalement maintenu mouillé ou dont le pot est
# fréquemment placé dans une soucoupe d'eau pendant la croissance.
BOG_OR_AQUATIC_GENERA = {
    "aldrovanda",
    "darlingtonia",
    "dionaea",
    "drosera",
    "genlisea",
    "heliamphora",
    "sarracenia",
    "utricularia",
    "nelumbo",
    "nymphaea",
    "victoria",
    "eichhornia",
    "pistia",
    "lemna",
    "azolla",
    "salvinia",
    "pontederia",
    "typha",
    "acorus",
    "cyperus",
}

# Genres explicitement exclus de la règle générale des carnivores de tourbière.
# Ils apprécient un substrat aéré et humide, mais pas un pot constamment dans l'eau.
AERATED_CARNIVOROUS_GENERA = {"nepenthes", "cephalotus"}

DROUGHT_FAMILIES = {
    "cactaceae",
    "crassulaceae",
    "aizoaceae",
    "didiereaceae",
    "portulacaceae",
}

DROUGHT_GENERA = {
    "adenium",
    "agave",
    "aloe",
    "beaucarnea",
    "crassula",
    "echeveria",
    "euphorbia",
    "gasteria",
    "haworthia",
    "lithops",
    "pachypodium",
    "sansevieria",
    "dracaena",  # inclut les Sansevieria reclassées
    "sedum",
    "zamioculcas",
}

ORCHID_FAMILIES = {"orchidaceae"}
MOIST_SENSITIVE_FAMILIES = {
    "marantaceae",
    "gesneriaceae",
    "begoniaceae",
}

WET_PROFILE_MARKERS = (
    "pieds dans l eau",
    "soucoupe d eau",
    "bac d eau",
    "toujours detrempe",
    "constamment detrempe",
    "substrat gorge d eau",
    "substrat sature",
    "milieu aquatique",
    "plante aquatique",
    "plante palustre",
    "tourbiere",
    "marecage",
    "bog plant",
    "water garden",
)

MOIST_PROFILE_MARKERS = (
    "ne jamais laisser secher",
    "ne pas laisser secher",
    "maintenir humide",
    "garder humide",
    "constamment humide",
    "uniformement humide",
    "moist but not soggy",
    "moist but not waterlogged",
)

DRY_PROFILE_MARKERS = (
    "laisser secher completement",
    "entierement sec",
    "substrat sec avant",
    "almost dry",
    "allow to dry",
    "arrosage quasi nul",
    "repos au sec",
)


@dataclass(frozen=True, slots=True)
class MoisturePolicy:
    """Seuil botanique utilisé pour une espèce."""

    code: str
    trigger: str
    label: str
    explanation: str
    source_key: str
    confidence: str


@dataclass(frozen=True, slots=True)
class WateringDecision:
    """Résultat de la décision après observation du substrat."""

    moisture: str | None
    can_water: bool
    reason: str
    policy: MoisturePolicy
    resting: bool = False


def normalize_soil_state(value: object) -> str | None:
    text = normalize_text(value)
    aliases = {
        "sec": SOIL_DRY,
        "seche": SOIL_DRY,
        "dry": SOIL_DRY,
        "humide": SOIL_MOIST,
        "moist": SOIL_MOIST,
        "damp": SOIL_MOIST,
        "trempe": SOIL_WET,
        "detrempe": SOIL_WET,
        "sature": SOIL_WET,
        "wet": SOIL_WET,
        "soggy": SOIL_WET,
    }
    return aliases.get(text) if text else None


def soil_label(value: object) -> str:
    state = normalize_soil_state(value)
    return SOIL_LABELS.get(state, "Non indiqué")


def _profile_text(profile: Mapping[str, Any]) -> str:
    try:
        raw = json.dumps(profile, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        raw = " ".join(str(value) for value in profile.values())
    return normalize_text(raw)


def _explicit_trigger(profile: Mapping[str, Any]) -> str | None:
    water = profile.get("gestion_eau")
    water = water if isinstance(water, Mapping) else {}
    candidates = (
        water.get("seuil_humidite_arrosage"),
        water.get("humidite_substrat_cible"),
        profile.get("seuil_humidite_arrosage"),
        profile.get("humidite_substrat_cible"),
    )
    for candidate in candidates:
        state = normalize_soil_state(candidate)
        if state in {SOIL_DRY, SOIL_MOIST}:
            return state
    return None


def watering_policy(profile: Mapping[str, Any]) -> MoisturePolicy:
    """Retourne une politique déterministe pour n'importe quelle fiche du catalogue."""
    explicit = _explicit_trigger(profile)
    if explicit:
        return MoisturePolicy(
            code="catalogue_explicit",
            trigger=explicit,
            label=f"Seuil explicite : {SOIL_LABELS[explicit].lower()}",
            explanation="La fiche botanique contient déjà un seuil d'humidité exploitable.",
            source_key="catalogue",
            confidence="élevée",
        )

    name = normalize_text(scientific_name(profile))
    genus = name.split(" ", 1)[0] if name else ""
    family = normalize_text(family_name(profile))
    text = _profile_text(profile)

    if genus in AERATED_CARNIVOROUS_GENERA:
        return MoisturePolicy(
            code="aerated_carnivorous",
            trigger=SOIL_DRY,
            label="Humide mais aéré",
            explanation=(
                "Cette carnivore tropicale ne doit pas rester dans un substrat saturé. "
                "Arroser lorsque le substrat devient sec, puis laisser égoutter."
            ),
            source_key="carnivorous",
            confidence="élevée",
        )

    if genus in BOG_OR_AQUATIC_GENERA or any(marker in text for marker in WET_PROFILE_MARKERS):
        return MoisturePolicy(
            code="bog_or_aquatic",
            trigger=SOIL_MOIST,
            label="Milieu humide à mouillé",
            explanation=(
                "Cette espèce est aquatique, palustre ou issue d'une tourbière. "
                "Réapprovisionner dès que le substrat n'est plus trempé, sans attendre un dessèchement complet."
            ),
            source_key="carnivorous",
            confidence="élevée",
        )

    if family in DROUGHT_FAMILIES or genus in DROUGHT_GENERA or any(marker in text for marker in DRY_PROFILE_MARKERS):
        return MoisturePolicy(
            code="dry_tolerant",
            trigger=SOIL_DRY,
            label="Dessèchement requis",
            explanation=(
                "Cette espèce stocke l'eau ou demande un substrat très drainant. "
                "Arroser seulement lorsque le substrat est sec et jamais lorsqu'il est humide ou trempé."
            ),
            source_key="succulents",
            confidence="élevée",
        )

    if family in ORCHID_FAMILIES:
        return MoisturePolicy(
            code="orchid_aerated",
            trigger=SOIL_DRY,
            label="Substrat aéré presque sec",
            explanation=(
                "Les racines d'orchidées demandent de l'air et pourrissent dans un substrat détrempé. "
                "Le niveau simplifié « sec » est le seuil prudent avant arrosage."
            ),
            source_key="orchids",
            confidence="élevée",
        )

    if family in MOIST_SENSITIVE_FAMILIES or any(marker in text for marker in MOIST_PROFILE_MARKERS):
        return MoisturePolicy(
            code="evenly_moist",
            trigger=SOIL_DRY,
            label="Humidité régulière, sans saturation",
            explanation=(
                "Cette espèce apprécie une humidité régulière mais pas un substrat détrempé. "
                "Avec trois niveaux seulement, arroser dès que le niveau « sec » est observé."
            ),
            source_key="ferns",
            confidence="moyenne",
        )

    return MoisturePolicy(
        code="general_container",
        trigger=SOIL_DRY,
        label="Contrôle standard en pot",
        explanation=(
            "Aucune exigence de milieu aquatique n'est indiquée. La règle prudente est d'arroser "
            "lorsque le substrat est sec, jamais lorsqu'il est humide ou trempé."
        ),
        source_key="general",
        confidence="moyenne",
    )


def watering_decision(
    profile: Mapping[str, Any],
    moisture: object,
    *,
    today: date | None = None,
) -> WateringDecision:
    """Décide si le bouton Arrosé peut être activé."""
    policy = watering_policy(profile)
    state = normalize_soil_state(moisture)
    if state is None:
        return WateringDecision(
            moisture=None,
            can_water=False,
            reason="Indiquez d'abord si le substrat est sec, humide ou trempé.",
            policy=policy,
        )

    current = today or date.today()
    try:
        resting = water_interval(profile, current) == 0
    except (TypeError, ValueError):
        resting = False
    if resting:
        return WateringDecision(
            moisture=state,
            can_water=False,
            reason="La fiche indique un repos saisonnier : surveiller la plante sans arroser automatiquement.",
            policy=policy,
            resting=True,
        )

    if state == SOIL_WET:
        return WateringDecision(
            moisture=state,
            can_water=False,
            reason="Le substrat est trempé : un nouvel arrosage augmenterait le risque d'asphyxie racinaire.",
            policy=policy,
        )

    if state == SOIL_MOIST and policy.trigger != SOIL_MOIST:
        return WateringDecision(
            moisture=state,
            can_water=False,
            reason=f"Le substrat est encore humide. {policy.explanation}",
            policy=policy,
        )

    return WateringDecision(
        moisture=state,
        can_water=True,
        reason=f"Arrosage conseillé. {policy.explanation}",
        policy=policy,
    )

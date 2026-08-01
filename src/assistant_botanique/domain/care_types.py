"""Types de soins partagés par le calendrier, le journal et les actions rapides."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CareType:
    key: str
    label: str
    default_note: str
    default_recurrence_days: int | None = None


CARE_TYPES: tuple[CareType, ...] = (
    CareType("controle_humidite", "Contrôle d'humidité", "Contrôle de l'humidité du substrat", 7),
    CareType("arrosage", "Arrosage", "Arrosage réalisé après contrôle"),
    CareType("fertilisation", "Fertilisation", "Fertilisation réalisée", 30),
    CareType("rempotage", "Rempotage", "Rempotage réalisé", 365),
    CareType("taille", "Taille", "Taille ou nettoyage réalisé", 90),
    CareType("traitement", "Traitement", "Traitement phytosanitaire réalisé"),
    CareType("rotation", "Rotation du pot", "Pot tourné pour équilibrer la croissance", 14),
    CareType("nettoyage", "Nettoyage", "Feuillage nettoyé", 30),
    CareType("observation", "Observation", "Observation ajoutée"),
)

CARE_TYPE_BY_KEY = {item.key: item for item in CARE_TYPES}
CARE_TYPE_LABELS = {item.key: item.label for item in CARE_TYPES}
SCHEDULABLE_CARE_TYPES = tuple(item for item in CARE_TYPES if item.key != "arrosage")
QUICK_ACTION_TYPES = (
    "substrat_sec",
    "encore_humide",
    "arrosage",
    "fertilisation",
    "rempotage",
    "taille",
    "traitement",
    "observation",
)

QUICK_ACTION_LABELS = {
    "substrat_sec": "Substrat sec",
    "encore_humide": "Encore humide",
    "arrosage": "Arrosé",
    "fertilisation": "Fertilisé",
    "rempotage": "Rempoté",
    "taille": "Taillé",
    "traitement": "Traité",
    "observation": "Observation",
}

QUICK_ACTION_NOTES = {
    "substrat_sec": "Substrat sec au contrôle",
    "encore_humide": "Substrat encore humide au contrôle",
    "arrosage": "Arrosage validé après contrôle",
    "fertilisation": "Fertilisation enregistrée",
    "rempotage": "Rempotage enregistré",
    "taille": "Taille ou nettoyage enregistré",
    "traitement": "Traitement enregistré",
    "observation": "Observation utilisateur",
}


def care_label(key: str) -> str:
    return CARE_TYPE_LABELS.get(key, QUICK_ACTION_LABELS.get(key, key.replace("_", " ").title()))

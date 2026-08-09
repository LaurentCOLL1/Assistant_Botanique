"""Échéance effective des contrôles d'humidité affichés dans Collection."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping

from core import watering_status

from assistant_botanique.domain.soil_moisture import SOIL_LABELS
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.watering_deferral import latest_deferred_watering_check


@dataclass(frozen=True, slots=True)
class CollectionWateringSchedule:
    plant_id: str
    due_date: date | None
    code: str
    short_label: str
    detail: str
    deferred: bool = False


def _relative_status(due_date: date, current: date) -> tuple[str, str]:
    remaining = (due_date - current).days
    if remaining > 0:
        return "OK", f"🟢 Contrôle dans {remaining} j"
    if remaining == 0:
        return "TODAY", "🟠 Contrôle aujourd'hui"
    return "LATE", f"🔴 Contrôle en retard ({abs(remaining)} j)"


def collection_watering_schedule(
    database: Database,
    plant: Mapping[str, object],
    profile: Mapping[str, object],
    *,
    today: date | None = None,
) -> CollectionWateringSchedule:
    """Retourne l'échéance à afficher, y compris lorsqu'un contrôle a été reporté."""
    current = today or date.today()
    plant_id = str(plant.get("id") or "")
    deferred = latest_deferred_watering_check(database, plant_id)
    if deferred is not None:
        code, label = _relative_status(deferred.due_date, current)
        state_label = SOIL_LABELS.get(deferred.soil_state, deferred.soil_state).lower()
        return CollectionWateringSchedule(
            plant_id=plant_id,
            due_date=deferred.due_date,
            code=code,
            short_label=label,
            detail=(
                f"Contrôle reporté après observation d'un substrat {state_label}. "
                f"Nouvelle échéance : {deferred.due_date.strftime('%d/%m/%Y')}."
            ),
            deferred=True,
        )

    status = watering_status(str(plant.get("date_arrosage") or ""), profile, today=current)
    return CollectionWateringSchedule(
        plant_id=plant_id,
        due_date=status.next_check,
        code=status.code,
        short_label=status.short_label,
        detail=status.detail,
        deferred=False,
    )


def next_due_collection_identifier(
    schedules: Mapping[str, CollectionWateringSchedule],
    ordered_identifiers,
    completed_plant_id: str,
    *,
    today: date | None = None,
) -> str | None:
    """Trouve le prochain contrôle arrivé à échéance dans l'ordre courant du tableau."""
    current = today or date.today()
    for identifier in ordered_identifiers:
        plant_id = str(identifier)
        if plant_id == completed_plant_id:
            continue
        schedule = schedules.get(plant_id)
        if schedule is None or schedule.due_date is None:
            continue
        if schedule.due_date <= current:
            return plant_id
    return None


__all__ = [
    "CollectionWateringSchedule",
    "collection_watering_schedule",
    "next_due_collection_identifier",
]

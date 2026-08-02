"""Report explicite d'un contrôle d'humidité lorsqu'aucun arrosage n'est requis."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Mapping

from core import ValidationError, format_date_fr

from assistant_botanique.domain.adaptive_care import recommend_care
from assistant_botanique.domain.soil_moisture import (
    SOIL_EVENT_TYPES,
    SOIL_LABELS,
    SOIL_MOIST,
    SOIL_WET,
    normalize_soil_state,
    watering_decision,
)
from assistant_botanique.infrastructure.database import Database

DEFERRED_CHECK_EVENT = "controle_reporte"
_SUPERSEDING_EVENTS = (DEFERRED_CHECK_EVENT, *SOIL_EVENT_TYPES.values(), "arrosage")


@dataclass(frozen=True, slots=True)
class DeferredWateringCheck:
    plant_id: str
    due_date: date
    delay_days: int
    soil_state: str
    reason: str


def _payload(raw: object) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        decoded = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def latest_deferred_watering_check(database: Database, plant_id: str) -> DeferredWateringCheck | None:
    """Retourne le report encore pertinent, sauf si un contrôle ou arrosage plus récent l'annule."""
    placeholders = ",".join("?" for _ in _SUPERSEDING_EVENTS)
    with database.connect() as conn:
        row = conn.execute(
            f"SELECT event_type, payload_json FROM care_events "
            f"WHERE plant_id=? AND event_type IN ({placeholders}) ORDER BY rowid DESC LIMIT 1",
            (plant_id, *_SUPERSEDING_EVENTS),
        ).fetchone()
    if not row or str(row["event_type"]) != DEFERRED_CHECK_EVENT:
        return None
    payload = _payload(row["payload_json"])
    try:
        due_date = date.fromisoformat(str(payload.get("next_check") or ""))
        delay_days = int(payload.get("delay_days") or 0)
    except (TypeError, ValueError):
        return None
    state = normalize_soil_state(payload.get("soil_moisture"))
    if state is None or delay_days < 1:
        return None
    return DeferredWateringCheck(
        plant_id=plant_id,
        due_date=due_date,
        delay_days=delay_days,
        soil_state=state,
        reason=str(payload.get("watering_reason") or ""),
    )


def recommended_recheck_delay(
    profile: Mapping[str, Any],
    plant: Mapping[str, Any],
    soil_state: object,
    *,
    today: date | None = None,
) -> int:
    """Calcule un délai prudent avant le prochain contrôle, sans simuler un arrosage."""
    current = today or date.today()
    state = normalize_soil_state(soil_state)
    if state is None:
        raise ValidationError("Indiquez d'abord l'humidité du substrat.")
    decision = watering_decision(profile, state, today=current)
    if decision.can_water:
        raise ValidationError("La plante a besoin d'être arrosée : le contrôle ne peut pas être reporté.")

    recommendation = recommend_care(profile, plant, today=current)
    interval = recommendation.interval_days
    if recommendation.next_check is None or interval <= 0:
        return 14

    if state == SOIL_WET:
        minimum, ratio = 2, 0.35
    elif state == SOIL_MOIST:
        minimum, ratio = 1, 0.25
    else:  # substrat sec mais arrosage bloqué, notamment pendant un repos saisonnier
        minimum, ratio = 7, 0.50
    return max(minimum, min(21, round(interval * ratio)))


def record_deferred_watering_check(
    database: Database,
    plant_id: str,
    profile: Mapping[str, Any],
    plant: Mapping[str, Any],
    soil_state: object,
    *,
    today: date | None = None,
) -> DeferredWateringCheck:
    """Enregistre une nouvelle échéance de contrôle quand l'arrosage n'est pas utile."""
    current = today or date.today()
    active = latest_deferred_watering_check(database, plant_id)
    if active is not None and active.due_date > current:
        raise ValidationError(f"Le contrôle est déjà reporté au {format_date_fr(active.due_date)}.")

    state = normalize_soil_state(soil_state)
    if state is None:
        raise ValidationError("Indiquez d'abord l'humidité du substrat.")
    decision = watering_decision(profile, state, today=current)
    delay_days = recommended_recheck_delay(profile, plant, state, today=current)
    due_date = current + timedelta(days=delay_days)
    database.add_care_event(
        plant_id,
        DEFERRED_CHECK_EVENT,
        event_date=current,
        note=(
            f"Contrôle reporté au {format_date_fr(due_date)} : "
            f"substrat {SOIL_LABELS[state].lower()}, arrosage non requis"
        ),
        payload={
            "soil_moisture": state,
            "next_check": due_date.isoformat(),
            "delay_days": delay_days,
            "watering_recommended": False,
            "watering_policy": decision.policy.code,
            "watering_reason": decision.reason,
        },
    )
    deferred = latest_deferred_watering_check(database, plant_id)
    if deferred is None:
        raise OSError("Le report du contrôle n'a pas pu être relu après son enregistrement.")
    return deferred


__all__ = [
    "DEFERRED_CHECK_EVENT",
    "DeferredWateringCheck",
    "latest_deferred_watering_check",
    "recommended_recheck_delay",
    "record_deferred_watering_check",
]

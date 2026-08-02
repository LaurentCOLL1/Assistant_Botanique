"""Persistance des observations d'humidité du substrat."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from core import ValidationError

from assistant_botanique.domain.soil_moisture import (
    EVENT_TO_SOIL,
    SOIL_EVENT_TYPES,
    SOIL_LABELS,
    SOIL_WET,
    normalize_soil_state,
    watering_decision,
)
from assistant_botanique.infrastructure.database import Database


@dataclass(frozen=True, slots=True)
class SoilMoistureSnapshot:
    plant_id: str
    state: str | None
    label: str
    watered: bool
    event_type: str | None = None
    event_date: str | None = None
    policy_code: str | None = None


_RELEVANT_EVENTS = tuple(EVENT_TO_SOIL) + ("arrosage",)


def _payload(raw: object) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        decoded = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _snapshot_from_row(plant_id: str, row: Mapping[str, Any]) -> SoilMoistureSnapshot | None:
    event_type = str(row.get("event_type") or "")
    payload = _payload(row.get("payload_json"))
    if event_type == "arrosage":
        state = normalize_soil_state(payload.get("soil_moisture_after"))
        if state is None:
            return None
        return SoilMoistureSnapshot(
            plant_id=plant_id,
            state=state,
            label=SOIL_LABELS[state],
            watered=True,
            event_type=event_type,
            event_date=str(row.get("event_date") or ""),
            policy_code=str(payload.get("watering_policy") or "") or None,
        )
    state = EVENT_TO_SOIL.get(event_type) or normalize_soil_state(payload.get("soil_moisture"))
    if state is None:
        return None
    return SoilMoistureSnapshot(
        plant_id=plant_id,
        state=state,
        label=SOIL_LABELS[state],
        watered=False,
        event_type=event_type,
        event_date=str(row.get("event_date") or ""),
        policy_code=str(payload.get("watering_policy") or "") or None,
    )


def latest_soil_moisture(database: Database, plant_id: str) -> SoilMoistureSnapshot:
    placeholders = ",".join("?" for _ in _RELEVANT_EVENTS)
    with database.connect() as conn:
        rows = conn.execute(
            f"SELECT event_type, event_date, payload_json, rowid FROM care_events "
            f"WHERE plant_id=? AND event_type IN ({placeholders}) ORDER BY rowid DESC",
            (plant_id, *_RELEVANT_EVENTS),
        ).fetchall()
    for raw in rows:
        row = dict(raw)
        snapshot = _snapshot_from_row(plant_id, row)
        if snapshot is not None:
            return snapshot
    return SoilMoistureSnapshot(plant_id, None, "Non indiqué", False)


def soil_moisture_by_plant(database: Database) -> dict[str, SoilMoistureSnapshot]:
    placeholders = ",".join("?" for _ in _RELEVANT_EVENTS)
    with database.connect() as conn:
        rows = conn.execute(
            f"SELECT plant_id, event_type, event_date, payload_json, rowid FROM care_events "
            f"WHERE event_type IN ({placeholders}) ORDER BY rowid DESC",
            _RELEVANT_EVENTS,
        ).fetchall()
    result: dict[str, SoilMoistureSnapshot] = {}
    for raw in rows:
        row = dict(raw)
        plant_id = str(row.get("plant_id") or "")
        if not plant_id or plant_id in result:
            continue
        snapshot = _snapshot_from_row(plant_id, row)
        if snapshot is not None:
            result[plant_id] = snapshot
    return result


def record_soil_moisture(
    database: Database,
    plant_id: str,
    state: object,
    profile: Mapping[str, Any],
) -> SoilMoistureSnapshot:
    normalized = normalize_soil_state(state)
    if normalized is None:
        raise ValidationError("État du substrat invalide.")
    decision = watering_decision(profile, normalized)
    database.add_care_event(
        plant_id,
        SOIL_EVENT_TYPES[normalized],
        note=f"Substrat indiqué comme {SOIL_LABELS[normalized].lower()}",
        payload={
            "soil_moisture": normalized,
            "watering_recommended": decision.can_water,
            "watering_policy": decision.policy.code,
            "watering_reason": decision.reason,
        },
    )
    return latest_soil_moisture(database, plant_id)


def record_validated_watering(
    database: Database,
    plant_id: str,
    profile: Mapping[str, Any],
) -> SoilMoistureSnapshot:
    current = latest_soil_moisture(database, plant_id)
    decision = watering_decision(profile, current.state)
    if current.watered:
        raise ValidationError("L'arrosage a déjà été validé après le dernier contrôle.")
    if not decision.can_water:
        raise ValidationError(decision.reason)
    database.add_care_event(
        plant_id,
        "arrosage",
        note=f"Arrosage validé après contrôle : substrat {current.label.lower()}",
        payload={
            "soil_moisture_before": current.state,
            "soil_moisture_after": SOIL_WET,
            "watering_policy": decision.policy.code,
            "watering_reason": decision.reason,
        },
    )
    return latest_soil_moisture(database, plant_id)

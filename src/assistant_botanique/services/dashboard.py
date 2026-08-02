"""Agrégation des contrôles et tâches utiles pour l'écran Aujourd'hui."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Mapping

from assistant_botanique.domain.adaptive_care import recommend_care
from assistant_botanique.domain.care_types import care_label
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.planner import CarePlanner
from assistant_botanique.services.watering_deferral import latest_deferred_watering_check


@dataclass(frozen=True, slots=True)
class DashboardItem:
    identifier: str
    kind: str
    plant_id: str
    plant_name: str
    due_date: date
    label: str
    status: str
    details: str


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    overdue: int
    today: int
    next_seven_days: int
    recent_events: int
    items: tuple[DashboardItem, ...]


def _status(due: date, today: date) -> str:
    delta = (due - today).days
    if delta < 0:
        return f"En retard de {-delta} j"
    if delta == 0:
        return "Aujourd'hui"
    return f"Dans {delta} j"


def build_dashboard_snapshot(
    database: Database,
    profiles_by_id: Mapping[str, Mapping[str, Any]],
    *,
    today: date | None = None,
) -> DashboardSnapshot:
    current = today or date.today()
    horizon = current + timedelta(days=7)
    items: list[DashboardItem] = []

    for plant in database.load_plants():
        profile = profiles_by_id.get(str(plant.get("species_id") or ""))
        if not profile:
            continue
        recommendation = recommend_care(profile, plant, today=current)
        due_date = recommendation.next_check
        deferred = latest_deferred_watering_check(database, str(plant["id"]))
        if deferred is not None and (due_date is None or deferred.due_date > due_date):
            due_date = deferred.due_date
        if due_date is None or due_date > horizon:
            continue

        details = (
            f"Intervalle estimé : {recommendation.interval_days} j · "
            f"confiance {recommendation.confidence_label}"
        )
        if deferred is not None and due_date == deferred.due_date:
            details = (
                f"Contrôle reporté après observation « {deferred.soil_state} » · "
                f"nouvelle échéance dans {deferred.delay_days} j"
            )
        items.append(
            DashboardItem(
                identifier=f"check:{plant['id']}",
                kind="check",
                plant_id=str(plant["id"]),
                plant_name=str(plant.get("surnom") or "Sans nom"),
                due_date=due_date,
                label="Contrôle d'humidité",
                status=_status(due_date, current),
                details=details,
            )
        )

    planner = CarePlanner(database)
    for task in planner.list_tasks(end=horizon, status="pending"):
        due = date.fromisoformat(task["due_date"])
        items.append(
            DashboardItem(
                identifier=f"task:{task['id']}",
                kind="task",
                plant_id=str(task["plant_id"]),
                plant_name=str(task.get("nickname") or "Sans nom"),
                due_date=due,
                label=care_label(str(task.get("care_type") or "soin")),
                status=_status(due, current),
                details=str(task.get("note") or ""),
            )
        )

    items.sort(key=lambda item: (item.due_date, item.plant_name.casefold(), item.label.casefold()))
    overdue = sum(item.due_date < current for item in items)
    due_today = sum(item.due_date == current for item in items)
    next_seven = sum(current < item.due_date <= horizon for item in items)
    recent_cutoff = (current - timedelta(days=7)).isoformat()
    with database.connect() as conn:
        recent_events = conn.execute(
            "SELECT COUNT(*) FROM care_events WHERE created_at >= ?",
            (recent_cutoff,),
        ).fetchone()[0]
    return DashboardSnapshot(overdue, due_today, next_seven, int(recent_events), tuple(items))

"""Moteur de règles personnalisées limité aux alertes et tâches vérifiables.

Aucune règle ne peut arroser, traiter, modifier une plante ou consommer un stock
automatiquement. Les seules actions autorisées sont la création d'une alerte ou
d'une tâche de calendrier.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from core import parse_date
from assistant_botanique.infrastructure.advanced_repository import AdvancedRepository
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.infrastructure.intelligence_repository import IntelligenceRepository
from assistant_botanique.services.planner import CarePlanner

ALLOWED_CONDITIONS = {
    "sensor_below",
    "sensor_above",
    "days_since_watering_gte",
    "active_infestation",
    "location",
}
ALLOWED_ACTIONS = {"create_alert", "create_task"}


@dataclass(frozen=True, slots=True)
class RuleExecution:
    rule_id: str
    rule_name: str
    triggered: bool
    targets: int
    message: str


class RulesEngine:
    def __init__(self, database: Database):
        self.database = database
        self.repository = IntelligenceRepository(database)
        self.advanced = AdvancedRepository(database)
        self.planner = CarePlanner(database)

    @staticmethod
    def validate_rule(condition: Mapping[str, Any], action: Mapping[str, Any]) -> None:
        condition_type = str(condition.get("type") or "")
        action_type = str(action.get("type") or "")
        if condition_type not in ALLOWED_CONDITIONS:
            raise ValueError("Condition non autorisée.")
        if action_type not in ALLOWED_ACTIONS:
            raise ValueError("Action non autorisée.")
        if action_type == "create_task" and not str(action.get("care_type") or "").strip():
            raise ValueError("Le type de tâche est obligatoire.")

    def _cooldown_active(self, rule: Mapping[str, Any], now: datetime) -> bool:
        raw = rule.get("last_triggered_at")
        if not raw:
            return False
        try:
            previous = datetime.fromisoformat(str(raw))
        except ValueError:
            return False
        return now - previous < timedelta(hours=max(1, int(rule.get("cooldown_hours") or 24)))

    def _targets(self, condition: Mapping[str, Any], today: date) -> list[dict[str, Any]]:
        condition_type = str(condition.get("type") or "")
        plants = self.database.load_plants()
        if condition_type == "days_since_watering_gte":
            days = max(0, int(condition.get("days") or 0))
            return [
                plant for plant in plants
                if (today - parse_date(plant.get("date_arrosage"))).days >= days
            ]
        if condition_type == "active_infestation":
            ids = self.repository.active_infestation_plant_ids()
            return [plant for plant in plants if plant["id"] in ids]
        if condition_type == "location":
            location_id = str(condition.get("location_id") or "")
            mapping = self.repository.plant_location_map()
            return [
                plant for plant in plants
                if mapping.get(plant["id"], {}).get("id") == location_id
            ]
        if condition_type in {"sensor_below", "sensor_above"}:
            source_id = str(condition.get("source_id") or "")
            threshold = float(condition.get("value") or 0)
            reading = next(
                (item for item in self.advanced.latest_sensor_readings() if item["id"] == source_id),
                None,
            )
            if not reading or reading.get("value") is None:
                return []
            measured = float(reading["value"])
            matched = measured < threshold if condition_type == "sensor_below" else measured > threshold
            if not matched:
                return []
            plant_id = reading.get("plant_id")
            return [plant for plant in plants if not plant_id or plant["id"] == plant_id]
        return []

    def evaluate_rule(
        self,
        rule: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> RuleExecution:
        current = now or datetime.now()
        condition = rule.get("condition") if isinstance(rule.get("condition"), Mapping) else {}
        action = rule.get("action") if isinstance(rule.get("action"), Mapping) else {}
        self.validate_rule(condition, action)
        if not bool(rule.get("enabled")):
            return RuleExecution(str(rule["id"]), str(rule["name"]), False, 0, "Règle désactivée.")
        if self._cooldown_active(rule, current):
            return RuleExecution(str(rule["id"]), str(rule["name"]), False, 0, "Délai de sécurité actif.")
        targets = self._targets(condition, current.date())
        if not targets:
            return RuleExecution(str(rule["id"]), str(rule["name"]), False, 0, "Condition non satisfaite.")

        template = str(action.get("message") or rule["name"])
        action_type = str(action.get("type"))
        created = 0
        for plant in targets[:500]:
            message = template.replace("{plant}", str(plant.get("surnom") or "Plante"))
            if action_type == "create_alert":
                self.repository.add_rule_alert(str(rule["id"]), message, plant_id=str(plant["id"]))
            else:
                days = max(0, min(int(action.get("due_in_days") or 0), 3650))
                self.planner.schedule(
                    str(plant["id"]),
                    str(action.get("care_type") or "observation"),
                    current.date() + timedelta(days=days),
                    note=message,
                )
            created += 1
        self.repository.mark_rule_triggered(str(rule["id"]), current)
        return RuleExecution(
            str(rule["id"]),
            str(rule["name"]),
            True,
            created,
            f"{created} alerte(s) ou tâche(s) créée(s).",
        )

    def evaluate_all(self, *, now: datetime | None = None) -> list[RuleExecution]:
        return [self.evaluate_rule(rule, now=now) for rule in self.repository.list_rules(enabled_only=True)]

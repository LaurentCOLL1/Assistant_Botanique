"""Notifications regroupées, priorisées, silencieuses et reportables."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Mapping

from assistant_botanique.domain.adaptive_care import recommend_care
from assistant_botanique.infrastructure.advanced_repository import AdvancedRepository
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.planner import CarePlanner


@dataclass(frozen=True)
class NotificationItem:
    key: str
    message: str
    location: str
    priority: int
    plant_id: str


def _parse_clock(value: object, fallback: time) -> time:
    try:
        hour, minute = [int(part) for part in str(value).split(":", 1)]
        return time(hour, minute)
    except (TypeError, ValueError):
        return fallback


def _in_quiet_hours(now: datetime, start: time, end: time) -> bool:
    current = now.time()
    if start == end:
        return False
    if start < end:
        return start <= current < end
    return current >= start or current < end


class NotificationService:
    def __init__(self, app_name: str = "Assistant Botanique"):
        self.app_name = app_name

    def show(self, title: str, message: str) -> None:
        try:
            from plyer import notification

            notification.notify(title=title, message=message, app_name=self.app_name, timeout=12)
        except Exception:
            print(f"{title}: {message}")

    def due_items(
        self,
        database: Database,
        profiles_by_id: Mapping[str, Mapping[str, Any]],
        *,
        now: datetime | None = None,
        include_snoozed: bool = False,
    ) -> list[NotificationItem]:
        current = now or datetime.now()
        today = current.date()
        advanced = AdvancedRepository(database)
        snoozed = set() if include_snoozed else advanced.active_snoozes(current)
        items: list[NotificationItem] = []
        plants = {plant["id"]: plant for plant in database.load_plants()}
        for plant in plants.values():
            profile = profiles_by_id.get(plant["species_id"])
            if not profile:
                continue
            recommendation = recommend_care(profile, plant, today=today)
            if not recommendation.next_check or recommendation.next_check > today:
                continue
            delay = max(0, (today - recommendation.next_check).days)
            key = f"adaptive:{plant['id']}:{recommendation.next_check.isoformat()}"
            if key in snoozed:
                continue
            context = plant.get("contexte") if isinstance(plant.get("contexte"), dict) else {}
            location = str(context.get("emplacement") or "Sans emplacement")
            items.append(
                NotificationItem(
                    key=key,
                    message=(
                        f"{plant['surnom']} : contrôle du substrat"
                        + (f" en retard de {delay} j." if delay else " aujourd'hui.")
                    ),
                    location=location,
                    priority=100 + min(delay, 30),
                    plant_id=plant["id"],
                )
            )
        planner = CarePlanner(database)
        for task in planner.due_tasks(today):
            key = f"task:{task['id']}"
            if key in snoozed:
                continue
            delay = max(0, (today - date.fromisoformat(task["due_date"])).days)
            plant = plants.get(task["plant_id"], {})
            context = plant.get("contexte") if isinstance(plant.get("contexte"), dict) else {}
            location = str(context.get("emplacement") or "Sans emplacement")
            items.append(
                NotificationItem(
                    key=key,
                    message=(
                        f"{task['nickname']} : {task['care_type']}"
                        + (f" en retard de {delay} j." if delay else " prévu aujourd'hui.")
                    ),
                    location=location,
                    priority=80 + min(delay, 30),
                    plant_id=task["plant_id"],
                )
            )
        return sorted(items, key=lambda item: (-item.priority, item.location.casefold(), item.message.casefold()))

    def digest(
        self,
        items: list[NotificationItem],
        settings: Mapping[str, Any] | None = None,
    ) -> tuple[str, str]:
        config = settings.get("notifications", {}) if isinstance(settings, Mapping) else {}
        max_items = max(1, min(int(config.get("max_items", 8)), 30))
        group = bool(config.get("group_by_location", True))
        selected = items[:max_items]
        if not selected:
            return "Contrôles du jour", ""
        if group:
            groups: dict[str, list[str]] = {}
            for item in selected:
                groups.setdefault(item.location, []).append(item.message)
            lines = []
            for location, messages in groups.items():
                lines.append(f"{location} :")
                lines.extend(f"• {message}" for message in messages)
        else:
            lines = [f"• {item.message}" for item in selected]
        if len(items) > len(selected):
            lines.append(f"… et {len(items) - len(selected)} autre(s).")
        urgent = sum(1 for item in items if item.priority >= 100)
        title = f"{len(items)} soin(s) à vérifier"
        if urgent:
            title += f" · {urgent} prioritaire(s)"
        return title, "\n".join(lines)

    def due_messages(
        self,
        database: Database,
        profiles_by_id: dict[str, dict[str, Any]],
    ) -> list[str]:
        return [item.message for item in self.due_items(database, profiles_by_id)]

    def notify_due(
        self,
        database: Database,
        profiles_by_id: dict[str, dict[str, Any]],
        settings: Mapping[str, Any] | None = None,
        *,
        force: bool = False,
        now: datetime | None = None,
    ) -> int:
        current = now or datetime.now()
        config = settings.get("notifications", {}) if isinstance(settings, Mapping) else {}
        if not force:
            start = _parse_clock(config.get("quiet_start", "22:00"), time(22, 0))
            end = _parse_clock(config.get("quiet_end", "07:00"), time(7, 0))
            if _in_quiet_hours(current, start, end):
                return 0
        items = self.due_items(database, profiles_by_id, now=current, include_snoozed=force)
        title, body = self.digest(items, settings)
        if body:
            self.show(title, body)
        return len(items)

    def snooze(
        self,
        database: Database,
        notification_keys: list[str],
        *,
        hours: int = 24,
    ) -> None:
        until = datetime.now() + timedelta(hours=max(1, min(int(hours), 24 * 365)))
        repository = AdvancedRepository(database)
        for key in notification_keys:
            repository.snooze(key, until)

    def install_windows_task(self, time_hhmm: str = "09:00") -> None:
        self.install_windows_tasks([time_hhmm])

    def install_windows_tasks(self, times: list[str]) -> None:
        if sys.platform != "win32":
            raise RuntimeError("La tâche planifiée automatique est actuellement disponible sous Windows.")
        cleaned = []
        for raw in times[:4]:
            parsed = _parse_clock(raw, time(9, 0))
            cleaned.append(f"{parsed.hour:02d}:{parsed.minute:02d}")
        if not cleaned:
            cleaned = ["09:00"]
        if getattr(sys, "frozen", False):
            command = f'"{Path(sys.executable)}" --notify'
        else:
            command = f'"{Path(sys.executable)}" -m assistant_botanique --notify'
        self.remove_windows_task()
        for index, clock in enumerate(cleaned, start=1):
            name = "AssistantBotaniqueNotifications" if index == 1 else f"AssistantBotaniqueNotifications{index}"
            subprocess.run(
                [
                    "schtasks", "/Create", "/F", "/SC", "DAILY", "/TN", name,
                    "/TR", command, "/ST", clock,
                ],
                check=True,
                capture_output=True,
                text=True,
            )

    def remove_windows_task(self) -> None:
        if sys.platform != "win32":
            return
        for index in range(1, 5):
            name = "AssistantBotaniqueNotifications" if index == 1 else f"AssistantBotaniqueNotifications{index}"
            subprocess.run(
                ["schtasks", "/Delete", "/F", "/TN", name],
                check=False,
                capture_output=True,
                text=True,
            )

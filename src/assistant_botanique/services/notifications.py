"""Notifications natives et installation d'une tâche planifiée Windows."""
from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from assistant_botanique.domain.adaptive_care import recommend_care
from assistant_botanique.infrastructure.database import Database


class NotificationService:
    def __init__(self, app_name: str = "Assistant Botanique"):
        self.app_name = app_name

    def show(self, title: str, message: str) -> None:
        try:
            from plyer import notification

            notification.notify(title=title, message=message, app_name=self.app_name, timeout=12)
        except Exception:
            # En mode console ou sur un système sans backend natif, le message reste visible.
            print(f"{title}: {message}")

    def due_messages(self, database: Database, profiles_by_id: dict[str, dict[str, Any]]) -> list[str]:
        messages = []
        for plant in database.load_plants():
            profile = profiles_by_id.get(plant["species_id"])
            if not profile:
                continue
            recommendation = recommend_care(profile, plant)
            if recommendation.next_check and recommendation.next_check <= date.today():
                messages.append(f"{plant['surnom']} : contrôler le substrat aujourd'hui.")
        return messages

    def notify_due(self, database: Database, profiles_by_id: dict[str, dict[str, Any]]) -> int:
        messages = self.due_messages(database, profiles_by_id)
        if messages:
            body = "\n".join(messages[:5])
            if len(messages) > 5:
                body += f"\n… et {len(messages) - 5} autre(s)."
            self.show("Contrôles de plantes", body)
        return len(messages)

    def install_windows_task(self, time_hhmm: str = "09:00") -> None:
        if sys.platform != "win32":
            raise RuntimeError("La tâche planifiée automatique est actuellement disponible sous Windows.")
        hour, minute = [int(part) for part in time_hhmm.split(":", 1)]
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Heure invalide.")
        if getattr(sys, "frozen", False):
            command = f'"{Path(sys.executable)}" --notify'
        else:
            command = f'"{Path(sys.executable)}" -m assistant_botanique --notify'
        subprocess.run(
            [
                "schtasks", "/Create", "/F", "/SC", "DAILY", "/TN", "AssistantBotaniqueNotifications",
                "/TR", command, "/ST", f"{hour:02d}:{minute:02d}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def remove_windows_task(self) -> None:
        if sys.platform != "win32":
            return
        subprocess.run(
            ["schtasks", "/Delete", "/F", "/TN", "AssistantBotaniqueNotifications"],
            check=False,
            capture_output=True,
            text=True,
        )

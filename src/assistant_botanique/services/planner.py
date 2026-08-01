"""Planification SQLite des soins ponctuels et récurrents."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable
from uuid import uuid4

from core import ValidationError, parse_date
from assistant_botanique.domain.care_types import CARE_TYPE_BY_KEY
from assistant_botanique.infrastructure.database import Database

TASK_SCHEMA = """
CREATE TABLE IF NOT EXISTS care_tasks (
    id TEXT PRIMARY KEY,
    plant_id TEXT NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
    care_type TEXT NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    note TEXT NOT NULL DEFAULT '',
    recurrence_days INTEGER,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_care_tasks_due ON care_tasks(status, due_date);
CREATE INDEX IF NOT EXISTS idx_care_tasks_plant ON care_tasks(plant_id, status, due_date);
"""


def _today_iso(value: date | str | None = None) -> str:
    return parse_date(value or date.today()).isoformat()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class CarePlanner:
    def __init__(self, database: Database):
        self.database = database
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.database.connect() as conn:
            conn.executescript(TASK_SCHEMA)

    def schedule(
        self,
        plant_id: str,
        care_type: str,
        due_date: date | str,
        *,
        note: str = "",
        recurrence_days: int | None = None,
    ) -> str:
        care_type = str(care_type).strip()
        if not care_type:
            raise ValidationError("Le type de soin est obligatoire.")
        if recurrence_days is not None and not 1 <= int(recurrence_days) <= 3650:
            raise ValidationError("La récurrence doit être comprise entre 1 et 3650 jours.")
        task_id = str(uuid4())
        with self.database.connect() as conn:
            if not conn.execute("SELECT 1 FROM plants WHERE id=?", (plant_id,)).fetchone():
                raise ValidationError("Plante introuvable.")
            conn.execute(
                """
                INSERT INTO care_tasks(id, plant_id, care_type, due_date, status, note, recurrence_days, created_at)
                VALUES(?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (task_id, plant_id, care_type, _today_iso(due_date), note.strip(), recurrence_days, _now()),
            )
        return task_id

    def list_tasks(
        self,
        *,
        start: date | str | None = None,
        end: date | str | None = None,
        status: str | None = "pending",
        plant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if start is not None:
            conditions.append("t.due_date >= ?")
            params.append(_today_iso(start))
        if end is not None:
            conditions.append("t.due_date <= ?")
            params.append(_today_iso(end))
        if status:
            conditions.append("t.status = ?")
            params.append(status)
        if plant_id:
            conditions.append("t.plant_id = ?")
            params.append(plant_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT t.*, p.nickname, p.species_id
            FROM care_tasks AS t
            JOIN plants AS p ON p.id=t.plant_id
            {where}
            ORDER BY t.due_date, p.nickname COLLATE NOCASE, t.created_at
        """
        with self.database.connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def due_tasks(self, when: date | str | None = None) -> list[dict[str, Any]]:
        return self.list_tasks(end=when or date.today(), status="pending")

    def complete(self, task_id: str, *, completed_on: date | str | None = None) -> str | None:
        when = parse_date(completed_on or date.today())
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM care_tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                raise ValidationError("Tâche introuvable.")
            if row["status"] != "pending":
                return None
            note = str(row["note"] or "").strip()
            event_note = note or CARE_TYPE_BY_KEY[row["care_type"]].default_note if row["care_type"] in CARE_TYPE_BY_KEY else note
            conn.execute(
                "UPDATE care_tasks SET status='completed', completed_at=? WHERE id=?",
                (_now(), task_id),
            )
            event_id = str(uuid4())
            from core import format_date_fr

            event_date = format_date_fr(when)
            conn.execute(
                """
                INSERT INTO care_events(id, plant_id, event_type, event_date, note, payload_json, created_at)
                VALUES(?, ?, ?, ?, ?, '{}', ?)
                """,
                (event_id, row["plant_id"], row["care_type"], event_date, event_note, _now()),
            )
            if row["care_type"] == "arrosage":
                conn.execute(
                    "UPDATE plants SET last_watering=?, updated_at=? WHERE id=?",
                    (event_date, _now(), row["plant_id"]),
                )
            recurrence = row["recurrence_days"]
            next_task_id = None
            if recurrence:
                next_task_id = str(uuid4())
                next_due = when + timedelta(days=int(recurrence))
                conn.execute(
                    """
                    INSERT INTO care_tasks(id, plant_id, care_type, due_date, status, note, recurrence_days, created_at)
                    VALUES(?, ?, ?, ?, 'pending', ?, ?, ?)
                    """,
                    (
                        next_task_id,
                        row["plant_id"],
                        row["care_type"],
                        next_due.isoformat(),
                        note,
                        recurrence,
                        _now(),
                    ),
                )
        return next_task_id

    def postpone(self, task_id: str, days: int = 1) -> None:
        if not 1 <= int(days) <= 3650:
            raise ValidationError("Le report doit être compris entre 1 et 3650 jours.")
        with self.database.connect() as conn:
            row = conn.execute("SELECT due_date FROM care_tasks WHERE id=? AND status='pending'", (task_id,)).fetchone()
            if not row:
                raise ValidationError("Tâche en attente introuvable.")
            due = date.fromisoformat(row["due_date"]) + timedelta(days=int(days))
            conn.execute("UPDATE care_tasks SET due_date=? WHERE id=?", (due.isoformat(), task_id))

    def cancel(self, task_id: str) -> None:
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE care_tasks SET status='cancelled', completed_at=? WHERE id=? AND status='pending'",
                (_now(), task_id),
            )

    def replace_pending(self, tasks: Iterable[dict[str, Any]]) -> None:
        """Utilitaire d'import : remplace uniquement les tâches encore en attente."""
        with self.database.connect() as conn:
            conn.execute("DELETE FROM care_tasks WHERE status='pending'")
        for item in tasks:
            self.schedule(
                str(item.get("plant_id") or ""),
                str(item.get("care_type") or "observation"),
                item.get("due_date") or date.today(),
                note=str(item.get("note") or ""),
                recurrence_days=item.get("recurrence_days"),
            )

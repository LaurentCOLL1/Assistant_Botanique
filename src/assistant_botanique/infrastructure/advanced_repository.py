"""Stockage SQLite des fonctions avancées, sans modifier les tables historiques."""
from __future__ import annotations

import json
import secrets
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from core import ValidationError, parse_date
from assistant_botanique.infrastructure.database import Database

ADVANCED_SCHEMA = """
CREATE TABLE IF NOT EXISTS advanced_action_history (
    id TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    inverse_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    undone_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_advanced_history_created ON advanced_action_history(created_at DESC);

CREATE TABLE IF NOT EXISTS propagation_records (
    id TEXT PRIMARY KEY,
    parent_plant_id TEXT NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
    child_plant_id TEXT REFERENCES plants(id) ON DELETE SET NULL,
    label TEXT NOT NULL,
    method TEXT NOT NULL,
    started_on TEXT NOT NULL,
    rooted_on TEXT,
    status TEXT NOT NULL DEFAULT 'en_cours',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_propagation_parent ON propagation_records(parent_plant_id, started_on DESC);

CREATE TABLE IF NOT EXISTS inventory_items (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 0,
    reorder_level REAL NOT NULL DEFAULT 0,
    expires_on TEXT,
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inventory_name ON inventory_items(name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
    delta REAL NOT NULL,
    reason TEXT NOT NULL,
    movement_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS treatment_protocols (
    id TEXT PRIMARY KEY,
    plant_id TEXT NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    product_item_id TEXT REFERENCES inventory_items(id) ON DELETE SET NULL,
    dose REAL,
    dose_unit TEXT,
    interval_days INTEGER NOT NULL,
    total_steps INTEGER NOT NULL,
    started_on TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'actif',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS treatment_steps (
    id TEXT PRIMARY KEY,
    protocol_id TEXT NOT NULL REFERENCES treatment_protocols(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    due_on TEXT NOT NULL,
    completed_on TEXT,
    status TEXT NOT NULL DEFAULT 'a_faire',
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE(protocol_id, step_number)
);
CREATE INDEX IF NOT EXISTS idx_treatment_steps_due ON treatment_steps(status, due_on);

CREATE TABLE IF NOT EXISTS sensor_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    unit TEXT NOT NULL,
    plant_id TEXT REFERENCES plants(id) ON DELETE SET NULL,
    location TEXT NOT NULL DEFAULT '',
    ingest_token TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sensor_readings (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sensor_sources(id) ON DELETE CASCADE,
    recorded_at TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sensor_readings_source_time
ON sensor_readings(source_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS taxonomy_proposals (
    id TEXT PRIMARY KEY,
    species_id TEXT NOT NULL,
    current_name TEXT NOT NULL,
    current_family TEXT NOT NULL,
    proposed_name TEXT NOT NULL,
    proposed_family TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'a_verifier',
    confidence INTEGER,
    source_url TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    UNIQUE(species_id, proposed_name, proposed_family)
);
CREATE INDEX IF NOT EXISTS idx_taxonomy_status ON taxonomy_proposals(status, checked_at DESC);

CREATE TABLE IF NOT EXISTS notification_snoozes (
    notification_key TEXT PRIMARY KEY,
    snoozed_until TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class AdvancedRepository:
    """Façade transactionnelle pour les fonctions avancées."""

    def __init__(self, database: Database):
        self.database = database
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.database.connect() as conn:
            conn.executescript(ADVANCED_SCHEMA)

    def record_history(
        self,
        action_type: str,
        summary: str,
        inverse: dict[str, Any],
        *,
        connection=None,
    ) -> str:
        identifier = str(uuid4())
        query = (
            "INSERT INTO advanced_action_history"
            "(id, action_type, summary, inverse_json, created_at) VALUES(?, ?, ?, ?, ?)"
        )
        params = (identifier, action_type, summary, _json(inverse), _now())
        if connection is not None:
            connection.execute(query, params)
        else:
            with self.database.connect() as conn:
                conn.execute(query, params)
        return identifier

    def list_history(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM advanced_action_history ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["inverse"] = json.loads(item.pop("inverse_json") or "{}")
            result.append(item)
        return result

    def undo(self, history_id: str) -> str:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT * FROM advanced_action_history WHERE id=?",
                (history_id,),
            ).fetchone()
            if not row:
                raise ValidationError("Action introuvable.")
            if row["undone_at"]:
                raise ValidationError("Cette action a déjà été annulée.")
            inverse = json.loads(row["inverse_json"] or "{}")
            kind = inverse.get("kind")
            if kind == "delete_care_events":
                event_ids = [str(value) for value in inverse.get("event_ids", []) if value]
                if event_ids:
                    placeholders = ",".join("?" for _ in event_ids)
                    conn.execute(f"DELETE FROM care_events WHERE id IN ({placeholders})", event_ids)
                for plant_id, value in dict(inverse.get("last_watering", {})).items():
                    conn.execute(
                        "UPDATE plants SET last_watering=?, updated_at=? WHERE id=?",
                        (value, _now(), plant_id),
                    )
            elif kind == "restore_inventory":
                snapshot = inverse.get("item")
                if not isinstance(snapshot, dict):
                    raise ValidationError("Historique d'inventaire incomplet.")
                conn.execute(
                    """
                    INSERT INTO inventory_items
                    (id, name, category, unit, quantity, reorder_level, expires_on, notes, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name, category=excluded.category, unit=excluded.unit,
                        quantity=excluded.quantity, reorder_level=excluded.reorder_level,
                        expires_on=excluded.expires_on, notes=excluded.notes,
                        updated_at=excluded.updated_at
                    """,
                    (
                        snapshot["id"], snapshot["name"], snapshot["category"], snapshot["unit"],
                        snapshot["quantity"], snapshot["reorder_level"], snapshot.get("expires_on"),
                        snapshot.get("notes", ""), _now(),
                    ),
                )
            elif kind == "delete_propagation":
                conn.execute("DELETE FROM propagation_records WHERE id=?", (inverse["id"],))
            elif kind == "delete_protocol":
                conn.execute("DELETE FROM treatment_protocols WHERE id=?", (inverse["id"],))
            elif kind == "restore_taxonomy_review":
                snapshot = inverse.get("review")
                species_id = str(inverse.get("species_id") or "")
                if snapshot:
                    conn.execute(
                        """
                        INSERT INTO catalog_reviews(
                            species_id, status, confidence, sources_json, notes,
                            reviewed_at, override_json, updated_at
                        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(species_id) DO UPDATE SET
                            status=excluded.status, confidence=excluded.confidence,
                            sources_json=excluded.sources_json, notes=excluded.notes,
                            reviewed_at=excluded.reviewed_at,
                            override_json=excluded.override_json, updated_at=excluded.updated_at
                        """,
                        (
                            species_id, snapshot["status"], snapshot["confidence"],
                            snapshot["sources_json"], snapshot["notes"],
                            snapshot.get("reviewed_at"), snapshot.get("override_json"), _now(),
                        ),
                    )
                else:
                    conn.execute("DELETE FROM catalog_reviews WHERE species_id=?", (species_id,))
            else:
                raise ValidationError("Type d'annulation non pris en charge.")
            conn.execute(
                "UPDATE advanced_action_history SET undone_at=? WHERE id=?",
                (_now(), history_id),
            )
        return str(row["summary"])

    def apply_bulk_care(
        self,
        plant_ids: list[str],
        event_type: str,
        note: str,
        event_date: date | str | None = None,
    ) -> str:
        unique_ids = list(dict.fromkeys(str(value).strip() for value in plant_ids if str(value).strip()))
        if not unique_ids:
            raise ValidationError("Sélectionnez au moins une plante.")
        if len(unique_ids) > 500:
            raise ValidationError("Une action groupée est limitée à 500 plantes.")
        event_type = str(event_type).strip()
        if not event_type:
            raise ValidationError("Le type de soin est obligatoire.")
        when = parse_date(event_date or date.today())
        event_date_fr = when.strftime("%d/%m/%Y")
        created_ids: list[str] = []
        previous_watering: dict[str, str] = {}
        with self.database.connect() as conn:
            placeholders = ",".join("?" for _ in unique_ids)
            rows = conn.execute(
                f"SELECT id, nickname, last_watering FROM plants WHERE id IN ({placeholders})",
                unique_ids,
            ).fetchall()
            found = {row["id"]: row for row in rows}
            missing = [value for value in unique_ids if value not in found]
            if missing:
                raise ValidationError(f"{len(missing)} plante(s) sont introuvables.")
            for plant_id in unique_ids:
                event_id = str(uuid4())
                created_ids.append(event_id)
                row = found[plant_id]
                previous_watering[plant_id] = row["last_watering"]
                conn.execute(
                    """
                    INSERT INTO care_events(
                        id, plant_id, event_type, event_date, note, payload_json, created_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id, plant_id, event_type, event_date_fr, note.strip(),
                        _json({"bulk": True}), _now(),
                    ),
                )
                if event_type == "arrosage":
                    conn.execute(
                        "UPDATE plants SET last_watering=?, updated_at=? WHERE id=?",
                        (event_date_fr, _now(), plant_id),
                    )
            return self.record_history(
                "bulk_care",
                f"{event_type} enregistré pour {len(unique_ids)} plante(s)",
                {
                    "kind": "delete_care_events",
                    "event_ids": created_ids,
                    "last_watering": previous_watering,
                },
                connection=conn,
            )

    def add_propagation(
        self,
        parent_plant_id: str,
        label: str,
        method: str,
        started_on: date | str,
        *,
        child_plant_id: str | None = None,
        status: str = "en_cours",
        notes: str = "",
    ) -> str:
        identifier = str(uuid4())
        started = parse_date(started_on).isoformat()
        with self.database.connect() as conn:
            if not conn.execute("SELECT 1 FROM plants WHERE id=?", (parent_plant_id,)).fetchone():
                raise ValidationError("Plante mère introuvable.")
            if child_plant_id and not conn.execute(
                "SELECT 1 FROM plants WHERE id=?", (child_plant_id,)
            ).fetchone():
                raise ValidationError("Plante fille introuvable.")
            conn.execute(
                """
                INSERT INTO propagation_records(
                    id, parent_plant_id, child_plant_id, label, method,
                    started_on, status, notes, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier, parent_plant_id, child_plant_id, label.strip() or "Bouture",
                    method.strip() or "autre", started, status, notes.strip(), _now(),
                ),
            )
            self.record_history(
                "propagation_create",
                f"Bouture créée : {label.strip() or 'Bouture'}",
                {"kind": "delete_propagation", "id": identifier},
                connection=conn,
            )
        return identifier

    def update_propagation(
        self,
        identifier: str,
        *,
        child_plant_id: str | None = None,
        rooted_on: date | str | None = None,
        status: str | None = None,
        notes: str | None = None,
    ) -> None:
        updates = []
        params: list[Any] = []
        if child_plant_id is not None:
            updates.append("child_plant_id=?")
            params.append(child_plant_id or None)
        if rooted_on is not None:
            updates.append("rooted_on=?")
            params.append(parse_date(rooted_on).isoformat() if rooted_on else None)
        if status is not None:
            updates.append("status=?")
            params.append(status)
        if notes is not None:
            updates.append("notes=?")
            params.append(notes.strip())
        if not updates:
            return
        params.append(identifier)
        with self.database.connect() as conn:
            conn.execute(
                f"UPDATE propagation_records SET {', '.join(updates)} WHERE id=?",
                params,
            )

    def list_propagations(self) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT r.*, p.nickname AS parent_nickname, c.nickname AS child_nickname
                    FROM propagation_records AS r
                    JOIN plants AS p ON p.id=r.parent_plant_id
                    LEFT JOIN plants AS c ON c.id=r.child_plant_id
                    ORDER BY r.started_on DESC, r.created_at DESC
                    """
                ).fetchall()
            ]

    def save_inventory_item(
        self,
        *,
        item_id: str | None,
        name: str,
        category: str,
        unit: str,
        quantity: float,
        reorder_level: float = 0,
        expires_on: date | str | None = None,
        notes: str = "",
    ) -> str:
        if not name.strip():
            raise ValidationError("Le nom du produit est obligatoire.")
        if float(quantity) < 0 or float(reorder_level) < 0:
            raise ValidationError("Les quantités ne peuvent pas être négatives.")
        identifier = item_id or str(uuid4())
        expiry = parse_date(expires_on).isoformat() if expires_on else None
        with self.database.connect() as conn:
            previous = conn.execute(
                "SELECT * FROM inventory_items WHERE id=?", (identifier,)
            ).fetchone()
            conn.execute(
                """
                INSERT INTO inventory_items(
                    id, name, category, unit, quantity, reorder_level,
                    expires_on, notes, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, category=excluded.category, unit=excluded.unit,
                    quantity=excluded.quantity, reorder_level=excluded.reorder_level,
                    expires_on=excluded.expires_on, notes=excluded.notes,
                    updated_at=excluded.updated_at
                """,
                (
                    identifier, name.strip(), category.strip() or "autre",
                    unit.strip() or "unité", float(quantity), float(reorder_level),
                    expiry, notes.strip(), _now(),
                ),
            )
            if previous:
                self.record_history(
                    "inventory_edit",
                    f"Stock modifié : {name.strip()}",
                    {"kind": "restore_inventory", "item": dict(previous)},
                    connection=conn,
                )
        return identifier

    def adjust_inventory(
        self,
        item_id: str,
        delta: float,
        reason: str,
        *,
        movement_date: date | str | None = None,
    ) -> str:
        delta = float(delta)
        if delta == 0:
            raise ValidationError("La variation ne peut pas être nulle.")
        movement_id = str(uuid4())
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
            if not row:
                raise ValidationError("Produit introuvable.")
            new_quantity = float(row["quantity"]) + delta
            if new_quantity < 0:
                raise ValidationError("Le stock ne peut pas devenir négatif.")
            conn.execute(
                "UPDATE inventory_items SET quantity=?, updated_at=? WHERE id=?",
                (new_quantity, _now(), item_id),
            )
            conn.execute(
                """
                INSERT INTO inventory_movements(
                    id, item_id, delta, reason, movement_date, created_at
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    movement_id, item_id, delta, reason.strip() or "Ajustement",
                    parse_date(movement_date or date.today()).isoformat(), _now(),
                ),
            )
            self.record_history(
                "inventory_adjust",
                f"Stock ajusté : {row['name']} ({delta:+g} {row['unit']})",
                {"kind": "restore_inventory", "item": dict(row)},
                connection=conn,
            )
        return movement_id

    def list_inventory(self) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT *,
                    CASE WHEN quantity <= reorder_level THEN 1 ELSE 0 END AS low_stock
                    FROM inventory_items
                    ORDER BY low_stock DESC, name COLLATE NOCASE
                    """
                ).fetchall()
            ]

    def create_treatment_protocol(
        self,
        plant_id: str,
        title: str,
        started_on: date | str,
        *,
        interval_days: int,
        total_steps: int,
        product_item_id: str | None = None,
        dose: float | None = None,
        dose_unit: str | None = None,
        notes: str = "",
    ) -> str:
        if not 1 <= int(interval_days) <= 3650:
            raise ValidationError("L'intervalle doit être compris entre 1 et 3650 jours.")
        if not 1 <= int(total_steps) <= 100:
            raise ValidationError("Le protocole doit comporter entre 1 et 100 étapes.")
        identifier = str(uuid4())
        start = parse_date(started_on)
        with self.database.connect() as conn:
            if not conn.execute("SELECT 1 FROM plants WHERE id=?", (plant_id,)).fetchone():
                raise ValidationError("Plante introuvable.")
            conn.execute(
                """
                INSERT INTO treatment_protocols(
                    id, plant_id, title, product_item_id, dose, dose_unit,
                    interval_days, total_steps, started_on, status, notes, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 'actif', ?, ?)
                """,
                (
                    identifier, plant_id, title.strip() or "Traitement", product_item_id,
                    dose, dose_unit, int(interval_days), int(total_steps),
                    start.isoformat(), notes.strip(), _now(),
                ),
            )
            for index in range(int(total_steps)):
                due = date.fromordinal(start.toordinal() + index * int(interval_days))
                conn.execute(
                    """
                    INSERT INTO treatment_steps(
                        id, protocol_id, step_number, due_on, status
                    ) VALUES(?, ?, ?, ?, 'a_faire')
                    """,
                    (str(uuid4()), identifier, index + 1, due.isoformat()),
                )
            self.record_history(
                "treatment_create",
                f"Protocole créé : {title.strip() or 'Traitement'}",
                {"kind": "delete_protocol", "id": identifier},
                connection=conn,
            )
        return identifier

    def complete_treatment_step(
        self,
        step_id: str,
        *,
        completed_on: date | str | None = None,
        notes: str = "",
        consume_product: bool = True,
    ) -> None:
        when = parse_date(completed_on or date.today())
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT s.*, p.plant_id, p.title, p.product_item_id, p.dose,
                       p.dose_unit, p.id AS protocol_id
                FROM treatment_steps AS s
                JOIN treatment_protocols AS p ON p.id=s.protocol_id
                WHERE s.id=?
                """,
                (step_id,),
            ).fetchone()
            if not row:
                raise ValidationError("Étape de traitement introuvable.")
            if row["status"] == "termine":
                return
            conn.execute(
                """
                UPDATE treatment_steps
                SET status='termine', completed_on=?, notes=?
                WHERE id=?
                """,
                (when.isoformat(), notes.strip(), step_id),
            )
            event_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO care_events(
                    id, plant_id, event_type, event_date, note, payload_json, created_at
                ) VALUES(?, ?, 'traitement', ?, ?, ?, ?)
                """,
                (
                    event_id, row["plant_id"], when.strftime("%d/%m/%Y"),
                    notes.strip() or row["title"],
                    _json({"protocol_id": row["protocol_id"], "step_id": step_id}),
                    _now(),
                ),
            )
            if consume_product and row["product_item_id"] and row["dose"]:
                item = conn.execute(
                    "SELECT quantity FROM inventory_items WHERE id=?",
                    (row["product_item_id"],),
                ).fetchone()
                if item and float(item["quantity"]) >= float(row["dose"]):
                    conn.execute(
                        """
                        UPDATE inventory_items
                        SET quantity=quantity-?, updated_at=?
                        WHERE id=?
                        """,
                        (float(row["dose"]), _now(), row["product_item_id"]),
                    )
            remaining = conn.execute(
                """
                SELECT COUNT(*) FROM treatment_steps
                WHERE protocol_id=? AND status!='termine'
                """,
                (row["protocol_id"],),
            ).fetchone()[0]
            if remaining == 0:
                conn.execute(
                    "UPDATE treatment_protocols SET status='termine' WHERE id=?",
                    (row["protocol_id"],),
                )

    def list_treatment_protocols(self) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT p.*, plants.nickname,
                    SUM(CASE WHEN s.status='termine' THEN 1 ELSE 0 END) AS completed_steps,
                    MIN(CASE WHEN s.status='a_faire' THEN s.due_on END) AS next_due
                    FROM treatment_protocols AS p
                    JOIN plants ON plants.id=p.plant_id
                    LEFT JOIN treatment_steps AS s ON s.protocol_id=p.id
                    GROUP BY p.id
                    ORDER BY p.status, next_due, p.created_at DESC
                    """
                ).fetchall()
            ]

    def list_treatment_steps(self, protocol_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM treatment_steps WHERE protocol_id=? ORDER BY step_number",
                    (protocol_id,),
                ).fetchall()
            ]

    def create_sensor_source(
        self,
        name: str,
        kind: str,
        unit: str,
        *,
        plant_id: str | None = None,
        location: str = "",
    ) -> dict[str, str]:
        identifier = str(uuid4())
        token = secrets.token_urlsafe(24)
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO sensor_sources(
                    id, name, kind, unit, plant_id, location,
                    ingest_token, enabled, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    identifier, name.strip() or "Capteur", kind.strip() or "autre",
                    unit.strip(), plant_id, location.strip(), token, _now(),
                ),
            )
        return {"id": identifier, "token": token}

    def list_sensor_sources(self) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT s.*, p.nickname
                    FROM sensor_sources AS s
                    LEFT JOIN plants AS p ON p.id=s.plant_id
                    ORDER BY s.name COLLATE NOCASE
                    """
                ).fetchall()
            ]

    def add_sensor_reading(
        self,
        source_id: str,
        value: float,
        *,
        recorded_at: datetime | str | None = None,
        unit: str | None = None,
        metadata: dict[str, Any] | None = None,
        ingest_token: str | None = None,
    ) -> str:
        identifier = str(uuid4())
        if isinstance(recorded_at, datetime):
            timestamp = recorded_at.isoformat(timespec="seconds")
        else:
            timestamp = str(recorded_at or _now())
        with self.database.connect() as conn:
            source = conn.execute(
                "SELECT * FROM sensor_sources WHERE id=? AND enabled=1",
                (source_id,),
            ).fetchone()
            if not source:
                raise ValidationError("Capteur introuvable ou désactivé.")
            if ingest_token is not None and not secrets.compare_digest(
                str(source["ingest_token"]), str(ingest_token)
            ):
                raise ValidationError("Jeton de capteur invalide.")
            conn.execute(
                """
                INSERT INTO sensor_readings(
                    id, source_id, recorded_at, value, unit, metadata_json
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier, source_id, timestamp, float(value),
                    unit or source["unit"], _json(metadata or {}),
                ),
            )
        return identifier

    def latest_sensor_readings(self) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT s.id AS source_id, s.name, s.kind, s.unit AS configured_unit,
                           s.location, s.plant_id, p.nickname,
                           r.value, r.unit, r.recorded_at
                    FROM sensor_sources AS s
                    LEFT JOIN plants AS p ON p.id=s.plant_id
                    LEFT JOIN sensor_readings AS r ON r.id=(
                        SELECT r2.id FROM sensor_readings AS r2
                        WHERE r2.source_id=s.id
                        ORDER BY r2.recorded_at DESC LIMIT 1
                    )
                    WHERE s.enabled=1
                    ORDER BY s.name COLLATE NOCASE
                    """
                ).fetchall()
            ]

    def save_taxonomy_proposal(self, proposal: dict[str, Any]) -> str:
        identifier = str(proposal.get("id") or uuid4())
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO taxonomy_proposals(
                    id, species_id, current_name, current_family,
                    proposed_name, proposed_family, status, confidence,
                    source_url, payload_json, checked_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(species_id, proposed_name, proposed_family) DO UPDATE SET
                    confidence=excluded.confidence, source_url=excluded.source_url,
                    payload_json=excluded.payload_json, checked_at=excluded.checked_at
                """,
                (
                    identifier, proposal["species_id"], proposal["current_name"],
                    proposal["current_family"], proposal["proposed_name"],
                    proposal["proposed_family"], proposal.get("status", "a_verifier"),
                    proposal.get("confidence"), proposal["source_url"],
                    _json(proposal.get("payload", {})), _now(),
                ),
            )
        return identifier

    def list_taxonomy_proposals(self, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM taxonomy_proposals"
        params: tuple[Any, ...] = ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        query += " ORDER BY checked_at DESC, current_name COLLATE NOCASE"
        with self.database.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
            result.append(item)
        return result

    def set_taxonomy_status(self, proposal_id: str, status: str) -> None:
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE taxonomy_proposals SET status=? WHERE id=?",
                (status, proposal_id),
            )

    def snooze(self, notification_key: str, until: datetime) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO notification_snoozes(notification_key, snoozed_until, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(notification_key) DO UPDATE SET
                    snoozed_until=excluded.snoozed_until, updated_at=excluded.updated_at
                """,
                (notification_key, until.isoformat(timespec="seconds"), _now()),
            )

    def active_snoozes(self, now: datetime | None = None) -> set[str]:
        current = (now or datetime.now()).isoformat(timespec="seconds")
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT notification_key FROM notification_snoozes WHERE snoozed_until>?",
                (current,),
            ).fetchall()
        return {row["notification_key"] for row in rows}

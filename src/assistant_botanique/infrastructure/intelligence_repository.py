"""Stockage SQLite des fonctions d'intelligence de collection.

Les nouvelles tables sont additives : elles ne modifient ni la collection historique,
ni les photos, ni le calendrier existant.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Mapping
from uuid import uuid4

from core import ValidationError, parse_date
from assistant_botanique.infrastructure.database import Database

INTELLIGENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS location_nodes (
    id TEXT PRIMARY KEY,
    parent_id TEXT REFERENCES location_nodes(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'zone',
    notes TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(parent_id, name)
);
CREATE INDEX IF NOT EXISTS idx_location_parent ON location_nodes(parent_id, sort_order, name);

CREATE TABLE IF NOT EXISTS plant_locations (
    plant_id TEXT PRIMARY KEY REFERENCES plants(id) ON DELETE CASCADE,
    location_id TEXT NOT NULL REFERENCES location_nodes(id) ON DELETE CASCADE,
    assigned_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plant_locations_location ON plant_locations(location_id);

CREATE TABLE IF NOT EXISTS infestation_cases (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    pest TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    severity INTEGER NOT NULL DEFAULT 1,
    detected_on TEXT NOT NULL,
    resolved_on TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_infestation_status ON infestation_cases(status, detected_on DESC);

CREATE TABLE IF NOT EXISTS infestation_plants (
    case_id TEXT NOT NULL REFERENCES infestation_cases(id) ON DELETE CASCADE,
    plant_id TEXT NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'atteinte',
    status TEXT NOT NULL DEFAULT 'surveillance',
    last_checked TEXT,
    notes TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(case_id, plant_id)
);
CREATE INDEX IF NOT EXISTS idx_infestation_plants_plant ON infestation_plants(plant_id, status);

CREATE TABLE IF NOT EXISTS infestation_observations (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES infestation_cases(id) ON DELETE CASCADE,
    plant_id TEXT REFERENCES plants(id) ON DELETE SET NULL,
    observed_on TEXT NOT NULL,
    severity INTEGER NOT NULL DEFAULT 1,
    notes TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_infestation_obs_case ON infestation_observations(case_id, observed_on DESC);

CREATE TABLE IF NOT EXISTS automation_rules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    condition_json TEXT NOT NULL,
    action_json TEXT NOT NULL,
    cooldown_hours INTEGER NOT NULL DEFAULT 24,
    last_triggered_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_automation_enabled ON automation_rules(enabled, name);

CREATE TABLE IF NOT EXISTS rule_alerts (
    id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL REFERENCES automation_rules(id) ON DELETE CASCADE,
    plant_id TEXT REFERENCES plants(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    acknowledged_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_rule_alerts_open ON rule_alerts(acknowledged_at, created_at DESC);

CREATE TABLE IF NOT EXISTS plugin_states (
    plugin_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    settings_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class IntelligenceRepository:
    def __init__(self, database: Database):
        self.database = database
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.database.connect() as conn:
            conn.executescript(INTELLIGENCE_SCHEMA)

    # --- Emplacements -------------------------------------------------
    def add_location(
        self,
        name: str,
        *,
        parent_id: str | None = None,
        kind: str = "zone",
        notes: str = "",
    ) -> str:
        clean = str(name).strip()
        if not clean:
            raise ValidationError("Le nom de l'emplacement est obligatoire.")
        identifier = str(uuid4())
        with self.database.connect() as conn:
            if parent_id and not conn.execute("SELECT 1 FROM location_nodes WHERE id=?", (parent_id,)).fetchone():
                raise ValidationError("Emplacement parent introuvable.")
            conn.execute(
                "INSERT INTO location_nodes(id, parent_id, name, kind, notes, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                (identifier, parent_id or None, clean, str(kind or "zone"), str(notes).strip(), _now()),
            )
        return identifier

    def list_locations(self) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT l.*, COUNT(pl.plant_id) AS plant_count
                FROM location_nodes AS l
                LEFT JOIN plant_locations AS pl ON pl.location_id=l.id
                GROUP BY l.id
                ORDER BY COALESCE(l.parent_id, ''), l.sort_order, l.name COLLATE NOCASE
                """
            ).fetchall()
        items = [dict(row) for row in rows]
        names = {item["id"]: item["name"] for item in items}
        parents = {item["id"]: item.get("parent_id") for item in items}
        for item in items:
            parts = [item["name"]]
            parent = parents.get(item["id"])
            seen = {item["id"]}
            while parent and parent not in seen:
                seen.add(parent)
                if parent in names:
                    parts.append(names[parent])
                parent = parents.get(parent)
            item["path"] = " / ".join(reversed(parts))
        return sorted(items, key=lambda item: item["path"].casefold())

    def assign_plant_location(self, plant_id: str, location_id: str) -> None:
        with self.database.connect() as conn:
            plant = conn.execute("SELECT context_json FROM plants WHERE id=?", (plant_id,)).fetchone()
            location = conn.execute("SELECT 1 FROM location_nodes WHERE id=?", (location_id,)).fetchone()
            if not plant:
                raise ValidationError("Plante introuvable.")
            if not location:
                raise ValidationError("Emplacement introuvable.")
            conn.execute(
                """
                INSERT INTO plant_locations(plant_id, location_id, assigned_at) VALUES(?, ?, ?)
                ON CONFLICT(plant_id) DO UPDATE SET location_id=excluded.location_id, assigned_at=excluded.assigned_at
                """,
                (plant_id, location_id, _now()),
            )
            context = json.loads(plant["context_json"] or "{}")
            path = next(item["path"] for item in self.list_locations() if item["id"] == location_id)
            context["emplacement"] = path
            conn.execute(
                "UPDATE plants SET context_json=?, updated_at=? WHERE id=?",
                (_json(context), _now(), plant_id),
            )

    def plant_location_map(self) -> dict[str, dict[str, Any]]:
        locations = {item["id"]: item for item in self.list_locations()}
        with self.database.connect() as conn:
            rows = conn.execute("SELECT * FROM plant_locations").fetchall()
        return {
            row["plant_id"]: locations[row["location_id"]]
            for row in rows
            if row["location_id"] in locations
        }

    def delete_location(self, location_id: str) -> None:
        with self.database.connect() as conn:
            children = conn.execute("SELECT COUNT(*) FROM location_nodes WHERE parent_id=?", (location_id,)).fetchone()[0]
            plants = conn.execute("SELECT COUNT(*) FROM plant_locations WHERE location_id=?", (location_id,)).fetchone()[0]
            if children or plants:
                raise ValidationError("Déplacez d'abord les sous-emplacements et les plantes.")
            conn.execute("DELETE FROM location_nodes WHERE id=?", (location_id,))

    # --- Infestations -------------------------------------------------
    def create_infestation(
        self,
        title: str,
        pest: str,
        detected_on: date | str,
        *,
        severity: int = 1,
        notes: str = "",
    ) -> str:
        if not str(title).strip() or not str(pest).strip():
            raise ValidationError("Le titre et le ravageur sont obligatoires.")
        level = max(1, min(int(severity), 5))
        identifier = str(uuid4())
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO infestation_cases(id, title, pest, severity, detected_on, notes, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (identifier, str(title).strip(), str(pest).strip(), level, parse_date(detected_on).isoformat(), str(notes).strip(), _now()),
            )
        return identifier

    def add_plant_to_infestation(
        self,
        case_id: str,
        plant_id: str,
        *,
        role: str = "atteinte",
        status: str = "surveillance",
        notes: str = "",
    ) -> None:
        with self.database.connect() as conn:
            if not conn.execute("SELECT 1 FROM infestation_cases WHERE id=?", (case_id,)).fetchone():
                raise ValidationError("Incident introuvable.")
            if not conn.execute("SELECT 1 FROM plants WHERE id=?", (plant_id,)).fetchone():
                raise ValidationError("Plante introuvable.")
            conn.execute(
                """
                INSERT INTO infestation_plants(case_id, plant_id, role, status, notes)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(case_id, plant_id) DO UPDATE SET
                    role=excluded.role, status=excluded.status, notes=excluded.notes
                """,
                (case_id, plant_id, str(role), str(status), str(notes).strip()),
            )

    def add_infestation_observation(
        self,
        case_id: str,
        notes: str,
        *,
        plant_id: str | None = None,
        severity: int = 1,
        observed_on: date | str | None = None,
    ) -> str:
        clean = str(notes).strip()
        if not clean:
            raise ValidationError("Une observation est obligatoire.")
        identifier = str(uuid4())
        when = parse_date(observed_on or date.today()).isoformat()
        with self.database.connect() as conn:
            if not conn.execute("SELECT 1 FROM infestation_cases WHERE id=?", (case_id,)).fetchone():
                raise ValidationError("Incident introuvable.")
            conn.execute(
                """
                INSERT INTO infestation_observations(id, case_id, plant_id, observed_on, severity, notes, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (identifier, case_id, plant_id or None, when, max(1, min(int(severity), 5)), clean, _now()),
            )
            if plant_id:
                conn.execute(
                    "UPDATE infestation_plants SET last_checked=? WHERE case_id=? AND plant_id=?",
                    (when, case_id, plant_id),
                )
        return identifier

    def resolve_infestation(self, case_id: str, *, resolved_on: date | str | None = None) -> None:
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE infestation_cases SET status='resolved', resolved_on=? WHERE id=?",
                (parse_date(resolved_on or date.today()).isoformat(), case_id),
            )

    def list_infestations(self, *, include_resolved: bool = True) -> list[dict[str, Any]]:
        where = "" if include_resolved else "WHERE c.status!='resolved'"
        with self.database.connect() as conn:
            cases = [dict(row) for row in conn.execute(
                f"""
                SELECT c.*, COUNT(ip.plant_id) AS plant_count
                FROM infestation_cases AS c
                LEFT JOIN infestation_plants AS ip ON ip.case_id=c.id
                {where}
                GROUP BY c.id
                ORDER BY CASE c.status WHEN 'active' THEN 0 ELSE 1 END, c.detected_on DESC
                """
            ).fetchall()]
            for case in cases:
                case["plants"] = [dict(row) for row in conn.execute(
                    """
                    SELECT ip.*, p.nickname, p.species_id
                    FROM infestation_plants AS ip JOIN plants AS p ON p.id=ip.plant_id
                    WHERE ip.case_id=? ORDER BY p.nickname COLLATE NOCASE
                    """,
                    (case["id"],),
                ).fetchall()]
                case["observations"] = [dict(row) for row in conn.execute(
                    "SELECT * FROM infestation_observations WHERE case_id=? ORDER BY observed_on DESC, created_at DESC",
                    (case["id"],),
                ).fetchall()]
        return cases

    def active_infestation_plant_ids(self) -> set[str]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT ip.plant_id
                FROM infestation_plants AS ip
                JOIN infestation_cases AS c ON c.id=ip.case_id
                WHERE c.status!='resolved' AND ip.status!='ecartee'
                """
            ).fetchall()
        return {row[0] for row in rows}

    # --- Règles et alertes -------------------------------------------
    def save_rule(
        self,
        *,
        rule_id: str | None,
        name: str,
        condition: Mapping[str, Any],
        action: Mapping[str, Any],
        enabled: bool = True,
        cooldown_hours: int = 24,
    ) -> str:
        clean = str(name).strip()
        if not clean:
            raise ValidationError("Le nom de la règle est obligatoire.")
        identifier = rule_id or str(uuid4())
        now = _now()
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO automation_rules(
                    id, name, enabled, condition_json, action_json,
                    cooldown_hours, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, enabled=excluded.enabled,
                    condition_json=excluded.condition_json, action_json=excluded.action_json,
                    cooldown_hours=excluded.cooldown_hours, updated_at=excluded.updated_at
                """,
                (
                    identifier, clean, 1 if enabled else 0, _json(dict(condition)),
                    _json(dict(action)), max(1, min(int(cooldown_hours), 24 * 365)), now, now,
                ),
            )
        return identifier

    def list_rules(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        where = "WHERE enabled=1" if enabled_only else ""
        with self.database.connect() as conn:
            rows = conn.execute(f"SELECT * FROM automation_rules {where} ORDER BY name COLLATE NOCASE").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["condition"] = json.loads(item.pop("condition_json") or "{}")
            item["action"] = json.loads(item.pop("action_json") or "{}")
            result.append(item)
        return result

    def set_rule_enabled(self, rule_id: str, enabled: bool) -> None:
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE automation_rules SET enabled=?, updated_at=? WHERE id=?",
                (1 if enabled else 0, _now(), rule_id),
            )

    def mark_rule_triggered(self, rule_id: str, when: datetime | None = None) -> None:
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE automation_rules SET last_triggered_at=?, updated_at=? WHERE id=?",
                ((when or datetime.now()).isoformat(timespec="seconds"), _now(), rule_id),
            )

    def add_rule_alert(self, rule_id: str, message: str, *, plant_id: str | None = None) -> str:
        identifier = str(uuid4())
        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO rule_alerts(id, rule_id, plant_id, message, created_at) VALUES(?, ?, ?, ?, ?)",
                (identifier, rule_id, plant_id or None, str(message).strip(), _now()),
            )
        return identifier

    def list_rule_alerts(self, *, open_only: bool = True) -> list[dict[str, Any]]:
        where = "WHERE a.acknowledged_at IS NULL" if open_only else ""
        with self.database.connect() as conn:
            return [dict(row) for row in conn.execute(
                f"""
                SELECT a.*, r.name AS rule_name, p.nickname
                FROM rule_alerts AS a
                JOIN automation_rules AS r ON r.id=a.rule_id
                LEFT JOIN plants AS p ON p.id=a.plant_id
                {where}
                ORDER BY a.created_at DESC
                """
            ).fetchall()]

    def acknowledge_alert(self, alert_id: str) -> None:
        with self.database.connect() as conn:
            conn.execute("UPDATE rule_alerts SET acknowledged_at=? WHERE id=?", (_now(), alert_id))

    # --- Extensions ---------------------------------------------------
    def plugin_state(self, plugin_id: str) -> dict[str, Any]:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM plugin_states WHERE plugin_id=?", (plugin_id,)).fetchone()
        if not row:
            return {"plugin_id": plugin_id, "enabled": 0, "settings": {}}
        item = dict(row)
        item["settings"] = json.loads(item.pop("settings_json") or "{}")
        return item

    def set_plugin_state(
        self,
        plugin_id: str,
        *,
        enabled: bool,
        settings: Mapping[str, Any] | None = None,
    ) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO plugin_states(plugin_id, enabled, settings_json, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(plugin_id) DO UPDATE SET
                    enabled=excluded.enabled, settings_json=excluded.settings_json, updated_at=excluded.updated_at
                """,
                (plugin_id, 1 if enabled else 0, _json(dict(settings or {})), _now()),
            )

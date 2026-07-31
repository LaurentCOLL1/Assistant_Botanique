"""Dépôt SQLite transactionnel et migrations de la version JSON."""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator
from uuid import uuid4

from core import ValidationError, format_date_fr, parse_date

from assistant_botanique.paths import COLLECTION_FILE, DATABASE_FILE, LEGACY_COLLECTION_FILE

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 3

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plants (
    id TEXT PRIMARY KEY,
    species_id TEXT NOT NULL,
    nickname TEXT NOT NULL,
    pot_l REAL NOT NULL CHECK (pot_l > 0),
    last_watering TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS care_events (
    id TEXT PRIMARY KEY,
    plant_id TEXT NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_date TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_care_events_plant_date ON care_events(plant_id, event_date DESC);
CREATE TABLE IF NOT EXISTS photos (
    id TEXT PRIMARY KEY,
    plant_id TEXT NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    caption TEXT NOT NULL DEFAULT '',
    taken_at TEXT NOT NULL,
    checksum TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_photos_plant_date ON photos(plant_id, taken_at DESC);
CREATE TABLE IF NOT EXISTS catalog_reviews (
    species_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'brouillon',
    confidence TEXT NOT NULL DEFAULT 'non_renseignee',
    sources_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT,
    override_json TEXT,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def normalize_plant(item: dict[str, Any]) -> dict[str, Any]:
    plant = dict(item)
    plant["id"] = str(plant.get("id") or uuid4())
    plant["species_id"] = str(plant.get("species_id") or plant.get("nom_sci") or "").strip()
    plant["surnom"] = str(plant.get("surnom") or "Plante sans nom").strip()
    try:
        plant["pot_l"] = float(plant.get("pot_l", plant.get("pot", 1.0)))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Volume de pot invalide pour {plant['surnom']!r}.") from exc
    if not 0 < plant["pot_l"] <= 100000:
        raise ValidationError(f"Volume de pot hors limites pour {plant['surnom']!r}.")
    watering = parse_date(plant.get("date_arrosage") or date.today())
    plant["date_arrosage"] = format_date_fr(watering)
    history = plant.get("historique_soins") if isinstance(plant.get("historique_soins"), list) else []
    if not history:
        history = [{"id": str(uuid4()), "type": "arrosage", "date": plant["date_arrosage"], "note": "Import initial"}]
    normalized_history = []
    for event in history:
        if not isinstance(event, dict):
            continue
        try:
            event_date = format_date_fr(parse_date(event.get("date") or plant["date_arrosage"]))
        except ValidationError:
            event_date = plant["date_arrosage"]
        normalized_history.append(
            {
                "id": str(event.get("id") or uuid4()),
                "type": str(event.get("type") or "observation"),
                "date": event_date,
                "note": str(event.get("note") or ""),
                "payload": event.get("payload") if isinstance(event.get("payload"), dict) else {},
            }
        )
    plant["historique_soins"] = normalized_history
    context = plant.get("contexte") if isinstance(plant.get("contexte"), dict) else {}
    plant["contexte"] = {
        "emplacement": context.get("emplacement", "interieur"),
        "exposition": context.get("exposition", "non_renseignee"),
        "matiere_pot": context.get("matiere_pot", "non_renseignee"),
        "substrat": context.get("substrat", "non_renseigne"),
        "temperature_moyenne": context.get("temperature_moyenne"),
        "hygrometrie": context.get("hygrometrie"),
    }
    return plant


class Database:
    def __init__(self, path: Path | str = DATABASE_FILE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 15000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA_SQL)
            conn.execute(
                "INSERT INTO metadata(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    def checkpoint(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def is_empty(self) -> bool:
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM plants").fetchone()[0] == 0

    def import_legacy_if_needed(
        self,
        defaults: Iterable[dict[str, Any]] = (),
        candidates: Iterable[Path] = (COLLECTION_FILE, LEGACY_COLLECTION_FILE),
    ) -> bool:
        if not self.is_empty():
            return False
        for path in candidates:
            if not path.exists():
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                items = raw.get("plantes", []) if isinstance(raw, dict) else raw
                if isinstance(items, list):
                    self.save_plants([item for item in items if isinstance(item, dict)])
                    self.set_metadata("legacy_json_imported_from", str(path))
                    return True
            except (OSError, json.JSONDecodeError, ValidationError):
                LOGGER.exception("Échec de migration de %s", path)
        default_list = [dict(item) for item in defaults]
        if default_list:
            self.save_plants(default_list)
            return True
        return False

    def set_metadata(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO metadata(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def load_plants(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM plants ORDER BY nickname COLLATE NOCASE").fetchall()
            result = []
            for row in rows:
                events = conn.execute(
                    "SELECT * FROM care_events WHERE plant_id=? ORDER BY event_date, created_at",
                    (row["id"],),
                ).fetchall()
                result.append(
                    {
                        "id": row["id"],
                        "species_id": row["species_id"],
                        "surnom": row["nickname"],
                        "pot_l": row["pot_l"],
                        "date_arrosage": row["last_watering"],
                        "contexte": json.loads(row["context_json"] or "{}"),
                        "historique_soins": [
                            {
                                "id": event["id"],
                                "type": event["event_type"],
                                "date": event["event_date"],
                                "note": event["note"],
                                "payload": json.loads(event["payload_json"] or "{}"),
                            }
                            for event in events
                        ],
                    }
                )
            return result

    def save_plants(self, plants: list[dict[str, Any]]) -> None:
        normalized = [normalize_plant(plant) for plant in plants]
        ids = [plant["id"] for plant in normalized]
        if len(ids) != len(set(ids)):
            raise ValidationError("Des identifiants de plantes sont dupliqués.")
        now = _now()
        with self.connect() as conn:
            if ids:
                placeholders = ",".join("?" for _ in ids)
                conn.execute(f"DELETE FROM plants WHERE id NOT IN ({placeholders})", ids)
            else:
                conn.execute("DELETE FROM plants")
            for plant in normalized:
                existing = conn.execute("SELECT created_at FROM plants WHERE id=?", (plant["id"],)).fetchone()
                created_at = existing[0] if existing else now
                conn.execute(
                    """
                    INSERT INTO plants(id, species_id, nickname, pot_l, last_watering, context_json, created_at, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        species_id=excluded.species_id,
                        nickname=excluded.nickname,
                        pot_l=excluded.pot_l,
                        last_watering=excluded.last_watering,
                        context_json=excluded.context_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        plant["id"], plant["species_id"], plant["surnom"], plant["pot_l"], plant["date_arrosage"],
                        _json(plant["contexte"]), created_at, now,
                    ),
                )
                conn.execute("DELETE FROM care_events WHERE plant_id=?", (plant["id"],))
                for event in plant["historique_soins"]:
                    conn.execute(
                        "INSERT INTO care_events(id, plant_id, event_type, event_date, note, payload_json, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                        (
                            event["id"], plant["id"], event["type"], event["date"], event["note"],
                            _json(event.get("payload", {})), now,
                        ),
                    )

    def add_care_event(
        self,
        plant_id: str,
        event_type: str,
        event_date: date | str | None = None,
        note: str = "",
        payload: dict[str, Any] | None = None,
    ) -> str:
        event_id = str(uuid4())
        when = format_date_fr(parse_date(event_date or date.today()))
        with self.connect() as conn:
            if not conn.execute("SELECT 1 FROM plants WHERE id=?", (plant_id,)).fetchone():
                raise ValidationError("Plante introuvable.")
            conn.execute(
                "INSERT INTO care_events(id, plant_id, event_type, event_date, note, payload_json, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (event_id, plant_id, event_type, when, note, _json(payload or {}), _now()),
            )
            if event_type == "arrosage":
                conn.execute("UPDATE plants SET last_watering=?, updated_at=? WHERE id=?", (when, _now(), plant_id))
        return event_id

    def add_photo_record(
        self,
        plant_id: str,
        path: str,
        caption: str,
        taken_at: str,
        checksum: str,
    ) -> str:
        photo_id = str(uuid4())
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO photos(id, plant_id, path, caption, taken_at, checksum, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (photo_id, plant_id, path, caption, taken_at, checksum, _now()),
            )
        return photo_id

    def list_photos(self, plant_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM photos"
        params: tuple[Any, ...] = ()
        if plant_id:
            query += " WHERE plant_id=?"
            params = (plant_id,)
        query += " ORDER BY taken_at DESC, created_at DESC"
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def delete_photo(self, photo_id: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT path FROM photos WHERE id=?", (photo_id,)).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM photos WHERE id=?", (photo_id,))
            return row[0]

    def timeline(self, plant_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            care = [dict(row) | {"kind": "soin"} for row in conn.execute(
                "SELECT id, plant_id, event_type AS title, event_date AS event_date, note AS details, payload_json FROM care_events WHERE plant_id=?",
                (plant_id,),
            ).fetchall()]
            photos = [dict(row) | {"kind": "photo", "title": "photo", "event_date": row["taken_at"], "details": row["caption"]}
                      for row in conn.execute("SELECT * FROM photos WHERE plant_id=?", (plant_id,)).fetchall()]
        def sort_key(item: dict[str, Any]) -> tuple[date, str]:
            raw = str(item.get("event_date") or "")
            try:
                parsed = date.fromisoformat(raw)
            except ValueError:
                try:
                    parsed = parse_date(raw)
                except ValidationError:
                    parsed = date.min
            return parsed, str(item.get("created_at") or "")

        return sorted(care + photos, key=sort_key, reverse=True)

    def save_catalog_review(
        self,
        species_id: str,
        status: str,
        confidence: str,
        sources: list[str],
        notes: str,
        override: dict[str, Any] | None,
    ) -> None:
        reviewed_at = date.today().isoformat() if status == "valide" else None
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO catalog_reviews(species_id, status, confidence, sources_json, notes, reviewed_at, override_json, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(species_id) DO UPDATE SET
                    status=excluded.status,
                    confidence=excluded.confidence,
                    sources_json=excluded.sources_json,
                    notes=excluded.notes,
                    reviewed_at=excluded.reviewed_at,
                    override_json=excluded.override_json,
                    updated_at=excluded.updated_at
                """,
                (species_id, status, confidence, _json(sources), notes, reviewed_at, _json(override) if override else None, _now()),
            )

    def get_catalog_review(self, species_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM catalog_reviews WHERE species_id=?", (species_id,)).fetchone()
            if not row:
                return None
            item = dict(row)
            item["sources"] = json.loads(item.pop("sources_json") or "[]")
            item["override"] = json.loads(item.pop("override_json")) if item.get("override_json") else None
            return item

    def review_summary(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS count FROM catalog_reviews GROUP BY status").fetchall()
            return {row["status"]: row["count"] for row in rows}

    def stats(self) -> dict[str, int]:
        with self.connect() as conn:
            return {
                "plants": conn.execute("SELECT COUNT(*) FROM plants").fetchone()[0],
                "events": conn.execute("SELECT COUNT(*) FROM care_events").fetchone()[0],
                "photos": conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0],
                "reviews": conn.execute("SELECT COUNT(*) FROM catalog_reviews").fetchone()[0],
            }

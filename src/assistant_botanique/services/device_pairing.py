"""Appairage local de téléphones avec codes temporaires et jetons révocables."""
from __future__ import annotations

import hashlib
import secrets
import threading
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from assistant_botanique.infrastructure.database import Database

PAIRING_SCHEMA = """
CREATE TABLE IF NOT EXISTS companion_devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_seen_at TEXT,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_companion_devices_active
ON companion_devices(revoked_at, last_seen_at DESC);
"""


def _now() -> datetime:
    return datetime.now()


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PairingSession:
    code: str
    url: str
    expires_at: datetime


class DevicePairingService:
    """Crée des appairages éphémères et conserve seulement les empreintes des jetons."""

    def __init__(self, database: Database):
        self.database = database
        self._pending: dict[str, datetime] = {}
        self._lock = threading.Lock()
        with self.database.connect() as conn:
            conn.executescript(PAIRING_SCHEMA)

    def create_session(self, base_url: str, *, ttl_seconds: int = 300) -> PairingSession:
        ttl = max(60, min(int(ttl_seconds), 900))
        current = _now()
        expires_at = current + timedelta(seconds=ttl)
        code = secrets.token_urlsafe(24)
        with self._lock:
            self._discard_expired(current)
            self._pending[code] = expires_at
        url = f"{base_url.rstrip('/')}/pair/{urllib.parse.quote(code)}"
        return PairingSession(code=code, url=url, expires_at=expires_at)

    def session_is_valid(self, code: str, *, now: datetime | None = None) -> bool:
        current = now or _now()
        with self._lock:
            self._discard_expired(current)
            expiry = self._pending.get(str(code))
            return bool(expiry and expiry > current)

    def redeem(self, code: str, device_name: str) -> str:
        current = _now()
        with self._lock:
            self._discard_expired(current)
            expiry = self._pending.pop(str(code), None)
        if not expiry or expiry <= current:
            raise ValueError("Ce QR code a expiré ou a déjà été utilisé.")
        name = str(device_name or "Téléphone").strip()[:80] or "Téléphone"
        token = secrets.token_urlsafe(36)
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO companion_devices(id, name, token_hash, created_at, last_seen_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (str(uuid4()), name, _hash_token(token), _iso(current), _iso(current)),
            )
        return token

    def authenticate(self, token: str) -> dict[str, Any] | None:
        value = str(token or "")
        if not value:
            return None
        digest = _hash_token(value)
        current = _iso(_now())
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT id, name, created_at, last_seen_at FROM companion_devices "
                "WHERE token_hash=? AND revoked_at IS NULL",
                (digest,),
            ).fetchone()
            if not row:
                return None
            conn.execute("UPDATE companion_devices SET last_seen_at=? WHERE id=?", (current, row["id"]))
        result = dict(row)
        result["last_seen_at"] = current
        return result

    def list_devices(self, *, include_revoked: bool = False) -> list[dict[str, Any]]:
        query = "SELECT id, name, created_at, last_seen_at, revoked_at FROM companion_devices"
        if not include_revoked:
            query += " WHERE revoked_at IS NULL"
        query += " ORDER BY COALESCE(last_seen_at, created_at) DESC"
        with self.database.connect() as conn:
            return [dict(row) for row in conn.execute(query).fetchall()]

    def revoke(self, device_id: str) -> bool:
        with self.database.connect() as conn:
            cursor = conn.execute(
                "UPDATE companion_devices SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
                (_iso(_now()), str(device_id)),
            )
        return bool(cursor.rowcount)

    def _discard_expired(self, now: datetime) -> None:
        expired = [code for code, expiry in self._pending.items() if expiry <= now]
        for code in expired:
            self._pending.pop(code, None)

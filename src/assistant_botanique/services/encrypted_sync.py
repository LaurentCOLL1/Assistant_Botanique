"""Synchronisation chiffrée par snapshots dans un dossier choisi par l'utilisateur.

Le mot de passe n'est jamais enregistré. Chaque snapshot contient une archive
`.botanique` complète chiffrée avec Fernet, dont la clé dérive du mot de passe
par PBKDF2-HMAC-SHA256.
"""
from __future__ import annotations

import base64
import json
import os
import struct
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from assistant_botanique.services.backup import BackupService

MAGIC = b"ABSYNC1\0"
ITERATIONS = 480_000


@dataclass(frozen=True, slots=True)
class SyncSnapshot:
    path: Path
    created_at: datetime
    size: int


def _derive_key(password: str, salt: bytes) -> bytes:
    if len(password) < 8:
        raise ValueError("Le mot de passe doit contenir au moins 8 caractères.")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def encrypt_payload(payload: bytes, password: str, metadata: dict[str, Any] | None = None) -> bytes:
    salt = os.urandom(16)
    header = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    token = Fernet(_derive_key(password, salt)).encrypt(payload)
    return MAGIC + salt + struct.pack(">I", len(header)) + header + token


def decrypt_payload(blob: bytes, password: str) -> tuple[dict[str, Any], bytes]:
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 20:
        raise ValueError("Ce fichier n'est pas un snapshot Assistant Botanique valide.")
    offset = len(MAGIC)
    salt = blob[offset:offset + 16]
    offset += 16
    header_size = struct.unpack(">I", blob[offset:offset + 4])[0]
    offset += 4
    if header_size > 1_000_000 or offset + header_size > len(blob):
        raise ValueError("En-tête de snapshot invalide.")
    metadata = json.loads(blob[offset:offset + header_size].decode("utf-8") or "{}")
    token = blob[offset + header_size:]
    try:
        payload = Fernet(_derive_key(password, salt)).decrypt(token)
    except InvalidToken as exc:
        raise ValueError("Mot de passe incorrect ou snapshot endommagé.") from exc
    return metadata, payload


class EncryptedSyncService:
    def __init__(self, backup_service: BackupService):
        self.backup_service = backup_service

    @staticmethod
    def list_snapshots(folder: Path | str) -> list[SyncSnapshot]:
        directory = Path(folder)
        if not directory.exists():
            return []
        result = []
        for path in directory.glob("assistant-botanique-*.absync"):
            try:
                stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                result.append(SyncSnapshot(path=path, created_at=stamp, size=path.stat().st_size))
            except OSError:
                continue
        return sorted(result, key=lambda item: item.created_at, reverse=True)

    def push(self, folder: Path | str, password: str) -> SyncSnapshot:
        directory = Path(folder)
        directory.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        destination = directory / f"assistant-botanique-{now:%Y%m%d-%H%M%S}.absync"
        with tempfile.TemporaryDirectory(prefix="assistant-botanique-sync-") as temp_name:
            archive = Path(temp_name) / "snapshot.botanique"
            self.backup_service.create(archive)
            payload = archive.read_bytes()
            blob = encrypt_payload(
                payload,
                password,
                {
                    "format": 1,
                    "created_at": now.isoformat(),
                    "archive_name": archive.name,
                },
            )
            temporary = destination.with_suffix(".tmp")
            temporary.write_bytes(blob)
            os.replace(temporary, destination)
        return SyncSnapshot(path=destination, created_at=now, size=destination.stat().st_size)

    def inspect(self, snapshot: Path | str, password: str) -> dict[str, Any]:
        metadata, payload = decrypt_payload(Path(snapshot).read_bytes(), password)
        with tempfile.TemporaryDirectory(prefix="assistant-botanique-sync-inspect-") as temp_name:
            archive = Path(temp_name) / "snapshot.botanique"
            archive.write_bytes(payload)
            manifest = self.backup_service.inspect(archive)
        return {"metadata": metadata, "manifest": manifest, "size": len(payload)}

    def pull(self, snapshot: Path | str, password: str) -> dict[str, Any]:
        metadata, payload = decrypt_payload(Path(snapshot).read_bytes(), password)
        with tempfile.TemporaryDirectory(prefix="assistant-botanique-sync-restore-") as temp_name:
            archive = Path(temp_name) / "snapshot.botanique"
            archive.write_bytes(payload)
            result = self.backup_service.restore(archive)
        result["sync_metadata"] = metadata
        return result

    def status(self, folder: Path | str) -> dict[str, Any]:
        snapshots = self.list_snapshots(folder)
        latest = snapshots[0] if snapshots else None
        database_path = self.backup_service.database.path
        local_mtime = (
            datetime.fromtimestamp(database_path.stat().st_mtime, tz=timezone.utc)
            if database_path.exists()
            else None
        )
        if not latest:
            state = "aucun_snapshot"
        elif local_mtime and local_mtime > latest.created_at:
            state = "local_plus_recent"
        elif local_mtime and local_mtime < latest.created_at:
            state = "distant_plus_recent"
        else:
            state = "synchronise"
        return {
            "state": state,
            "latest": latest,
            "local_modified_at": local_mtime,
            "count": len(snapshots),
        }

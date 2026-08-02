"""Planification locale et rotation des sauvegardes automatiques."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from assistant_botanique.infrastructure.backup_config import BackupConfigRepository
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.infrastructure.settings import SettingsRepository
from assistant_botanique.services.backup import BackupService


@dataclass(slots=True)
class BackupRunResult:
    created: bool
    path: Path | None = None
    reason: str = ""


def backup_due(config: dict[str, Any], now: datetime | None = None) -> bool:
    now = now or datetime.now()
    if not bool(config.get("enabled", False)):
        return False
    cadence = str(config.get("cadence") or "daily")
    last_raw = str(config.get("last_run") or "").strip()
    if not last_raw:
        return True
    try:
        last = datetime.fromisoformat(last_raw)
    except ValueError:
        return True
    interval = timedelta(days=7 if cadence == "weekly" else 1)
    return now - last >= interval


def rotate_backups(directory: Path, retention: int) -> list[Path]:
    retention = max(1, min(int(retention), 365))
    files = sorted(
        directory.glob("assistant-botanique-auto-*.botanique"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed: list[Path] = []
    for path in files[retention:]:
        path.unlink(missing_ok=True)
        removed.append(path)
    return removed


class BackupScheduler:
    def __init__(
        self,
        database: Database,
        settings: dict[str, Any],
        settings_repo: SettingsRepository,
        *,
        backup_config: BackupConfigRepository | None = None,
        service: BackupService | None = None,
    ):
        self.database = database
        self.settings = settings
        self.settings_repo = settings_repo
        self.backup_config = backup_config or BackupConfigRepository()
        self.service = service or BackupService(database)

    @property
    def config(self) -> dict[str, Any]:
        return self.settings.setdefault(
            "automatic_backups",
            {
                "enabled": True,
                "cadence": "daily",
                "retention": 14,
                "last_run": "",
                "last_path": "",
                "last_error": "",
            },
        )

    def configured_directory(self) -> Path:
        self.backup_config.ensure_exists()
        directory = self.backup_config.load_directory()
        if directory is None:
            raise ValueError("Aucun dossier de sauvegarde n'est configuré.")
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def run_if_due(self, now: datetime | None = None) -> BackupRunResult:
        now = now or datetime.now()
        if not backup_due(self.config, now):
            return BackupRunResult(False, reason="Sauvegarde non arrivée à échéance.")
        return self.run_now(now)

    def run_now(self, now: datetime | None = None) -> BackupRunResult:
        now = now or datetime.now()
        try:
            directory = self.configured_directory()
            destination = directory / f"assistant-botanique-auto-{now:%Y%m%d-%H%M%S}.botanique"
            path = self.service.create(destination)
            rotate_backups(directory, int(self.config.get("retention", 14)))
        except Exception as exc:
            self.config["last_error"] = str(exc)
            self.settings_repo.save(self.settings)
            return BackupRunResult(False, reason=str(exc))
        self.config["last_run"] = now.isoformat(timespec="seconds")
        self.config["last_path"] = str(path)
        self.config["last_error"] = ""
        self.settings_repo.save(self.settings)
        return BackupRunResult(True, path=path, reason="Sauvegarde automatique créée.")

    def status_text(self) -> str:
        config = self.config
        if config.get("last_error"):
            return f"Dernier échec : {config['last_error']}"
        if config.get("last_run"):
            try:
                timestamp = datetime.fromisoformat(str(config["last_run"]))
                return f"Dernière sauvegarde automatique : {timestamp:%d/%m/%Y %H:%M}"
            except ValueError:
                pass
        return "Aucune sauvegarde automatique n'a encore été créée."

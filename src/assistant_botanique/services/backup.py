"""Création et restauration d'archives complètes et vérifiées."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable

from assistant_botanique import __version__
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.paths import DATA_DIR

ARCHIVE_FORMAT = 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_members(archive: zipfile.ZipFile) -> Iterable[zipfile.ZipInfo]:
    for member in archive.infolist():
        path = Path(member.filename)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Chemin dangereux dans l'archive : {member.filename}")
        yield member


class BackupService:
    def __init__(self, database: Database, data_dir: Path = DATA_DIR):
        self.database = database
        self.data_dir = data_dir

    def create(self, destination: Path | str) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.database.checkpoint()
        files = [path for path in self.data_dir.rglob("*") if path.is_file()]
        files = [
            path for path in files
            if path != destination
            and path.suffix.casefold() != ".botanique"
            and not path.name.endswith(("-wal", "-shm"))
        ]
        manifest = {
            "archive_format": ARCHIVE_FORMAT,
            "app_version": __version__,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "files": {},
        }
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                relative = path.relative_to(self.data_dir).as_posix()
                archive.write(path, f"data/{relative}")
                manifest["files"][relative] = {"sha256": _sha256(path), "size": path.stat().st_size}
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        return destination

    def inspect(self, archive_path: Path | str) -> dict:
        with zipfile.ZipFile(archive_path) as archive:
            list(_safe_members(archive))
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if manifest.get("archive_format") != ARCHIVE_FORMAT:
                raise ValueError("Version d'archive non prise en charge.")
            return manifest

    def restore(self, archive_path: Path | str) -> dict:
        archive_path = Path(archive_path)
        manifest = self.inspect(archive_path)
        with tempfile.TemporaryDirectory(prefix="assistant-botanique-restore-") as temp_name:
            temp = Path(temp_name)
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(temp, members=list(_safe_members(archive)))
            extracted_data = temp / "data"
            for relative, metadata in manifest["files"].items():
                path = extracted_data / relative
                if not path.is_file() or _sha256(path) != metadata["sha256"]:
                    raise ValueError(f"Échec du contrôle d'intégrité : {relative}")
            safety = self.data_dir.parent / f"{self.data_dir.name}-avant-restauration-{datetime.now():%Y%m%d-%H%M%S}"
            if self.data_dir.exists():
                shutil.copytree(self.data_dir, safety)
            for child in (self.data_dir.iterdir() if self.data_dir.exists() else ()):
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            self.data_dir.mkdir(parents=True, exist_ok=True)
            for child in extracted_data.iterdir():
                target = self.data_dir / child.name
                if child.is_dir():
                    shutil.copytree(child, target)
                else:
                    shutil.copy2(child, target)
        Database(self.data_dir / "assistant_botanique.sqlite3").initialize()
        return {"manifest": manifest, "safety_copy": str(safety)}

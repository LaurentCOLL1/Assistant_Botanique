"""Gestion des photos liées aux plantes."""
from __future__ import annotations

import hashlib
import shutil
from datetime import date
from pathlib import Path
from uuid import uuid4

from assistant_botanique.infrastructure.database import Database
from assistant_botanique.paths import PHOTOS_DIR

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class PhotoService:
    def __init__(self, database: Database, root: Path = PHOTOS_DIR):
        self.database = database
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def add_photo(self, plant_id: str, source: Path | str, caption: str = "", taken_at: date | None = None) -> dict:
        source_path = Path(source)
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        extension = source_path.suffix.casefold()
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("Format d'image non pris en charge.")
        target_dir = self.root / plant_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{uuid4()}{extension}"
        shutil.copy2(source_path, target)
        checksum = sha256_file(target)
        photo_id = self.database.add_photo_record(
            plant_id=plant_id,
            path=str(target.relative_to(self.root.parent)),
            caption=caption.strip(),
            taken_at=(taken_at or date.today()).isoformat(),
            checksum=checksum,
        )
        return {"id": photo_id, "plant_id": plant_id, "path": str(target), "caption": caption, "checksum": checksum}

    def resolve_path(self, stored_path: str) -> Path:
        path = Path(stored_path)
        if path.is_absolute():
            return path
        return self.root.parent / path

    def delete_photo(self, photo_id: str) -> bool:
        stored = self.database.delete_photo(photo_id)
        if not stored:
            return False
        self.resolve_path(stored).unlink(missing_ok=True)
        return True

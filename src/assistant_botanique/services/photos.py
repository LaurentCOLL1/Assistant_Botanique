"""Gestion des photos liées aux plantes."""
from __future__ import annotations

import hashlib
import shutil
from datetime import date
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from assistant_botanique.infrastructure.database import Database
from assistant_botanique.paths import PHOTOS_DIR

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_UPLOAD_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000


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

    def _target(self, plant_id: str, extension: str) -> Path:
        target_dir = self.root / plant_id
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"{uuid4()}{extension}"

    def _register(self, plant_id: str, target: Path, caption: str, taken_at: date | None) -> dict:
        checksum = sha256_file(target)
        if any(str(item.get("checksum") or "") == checksum for item in self.database.list_photos(plant_id)):
            target.unlink(missing_ok=True)
            raise ValueError("Cette photo est déjà enregistrée pour cette plante.")
        photo_id = self.database.add_photo_record(
            plant_id=plant_id,
            path=str(target.relative_to(self.root.parent)),
            caption=caption.strip(),
            taken_at=(taken_at or date.today()).isoformat(),
            checksum=checksum,
        )
        return {
            "id": photo_id,
            "plant_id": plant_id,
            "path": str(target),
            "caption": caption,
            "checksum": checksum,
        }

    def add_photo(self, plant_id: str, source: Path | str, caption: str = "", taken_at: date | None = None) -> dict:
        source_path = Path(source)
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        extension = source_path.suffix.casefold()
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("Format d'image non pris en charge.")
        target = self._target(plant_id, extension)
        shutil.copy2(source_path, target)
        return self._register(plant_id, target, caption, taken_at)

    def add_photo_bytes(
        self,
        plant_id: str,
        payload: bytes,
        *,
        filename: str = "photo.jpg",
        caption: str = "",
        taken_at: date | None = None,
    ) -> dict:
        """Vérifie, réoriente et normalise une image reçue depuis le réseau local."""
        if not payload:
            raise ValueError("La photo envoyée est vide.")
        if len(payload) > MAX_UPLOAD_BYTES:
            raise ValueError("La photo dépasse la limite de 12 Mo.")
        if not any(plant["id"] == plant_id for plant in self.database.load_plants()):
            raise ValueError("Plante introuvable.")
        previous_limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
        try:
            with Image.open(BytesIO(payload)) as probe:
                image_format = str(probe.format or "").upper()
                probe.verify()
            if image_format not in ALLOWED_UPLOAD_FORMATS:
                raise ValueError("Format mobile non pris en charge. Utilisez JPEG, PNG ou WebP.")
            with Image.open(BytesIO(payload)) as opened:
                image = ImageOps.exif_transpose(opened)
                image.thumbnail((6000, 6000))
                has_alpha = image.mode in {"RGBA", "LA"} or (
                    image.mode == "P" and "transparency" in image.info
                )
                if has_alpha:
                    image = image.convert("RGBA")
                    extension = ".png"
                    target = self._target(plant_id, extension)
                    image.save(target, format="PNG", optimize=True)
                else:
                    image = image.convert("RGB")
                    extension = ".jpg"
                    target = self._target(plant_id, extension)
                    image.save(target, format="JPEG", quality=90, optimize=True, progressive=True)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError("Le fichier reçu n'est pas une image valide ou sûre.") from exc
        finally:
            Image.MAX_IMAGE_PIXELS = previous_limit
        mobile_caption = caption.strip() or f"Photo mobile — {Path(filename).name}"
        return self._register(plant_id, target, mobile_caption, taken_at)

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

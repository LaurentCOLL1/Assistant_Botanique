"""Génère les ressources PNG/ICO du programme depuis la source versionnée."""
from __future__ import annotations

import argparse
import base64
import io
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "app_icon.png.b64"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def load_source_image(source: Path = SOURCE) -> Image.Image:
    encoded = "".join(source.read_text(encoding="ascii").split())
    raw = base64.b64decode(encoded, validate=True)
    image = Image.open(io.BytesIO(raw))
    image.load()
    return image.convert("RGBA")


def generate_icons(output_dir: Path, source: Path = SOURCE) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    image = load_source_image(source)
    if image.width != image.height:
        raise ValueError("La source de l'icône doit être carrée.")

    png_path = output_dir / "assistant_botanique.png"
    ico_path = output_dir / "assistant_botanique.ico"
    image.save(png_path, format="PNG", optimize=True)
    image.save(ico_path, format="ICO", sizes=[(size, size) for size in ICO_SIZES])
    return png_path, ico_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "installer" / "generated",
        help="Dossier où écrire assistant_botanique.png et assistant_botanique.ico",
    )
    args = parser.parse_args()
    png_path, ico_path = generate_icons(args.output_dir)
    print(png_path)
    print(ico_path)


if __name__ == "__main__":
    main()

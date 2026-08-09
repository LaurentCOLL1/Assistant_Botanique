"""Icône et visuel officiels de l'application, chargés depuis les ressources embarquées."""
from __future__ import annotations

import base64
import io
import logging
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

from assistant_botanique.paths import resource_dir

LOGGER = logging.getLogger(__name__)
ICON_RESOURCE = Path("assets") / "app_icon.png.b64"


def icon_source_path() -> Path:
    """Retourne le chemin de la source PNG encodée, y compris sous PyInstaller."""
    return resource_dir() / ICON_RESOURCE


def load_icon_base64() -> str:
    """Charge la source PNG Base64 sans conserver de séparateurs superflus."""
    return "".join(icon_source_path().read_text(encoding="ascii").split())


def load_brand_photo(master: tk.Misc, size: int = 180) -> ImageTk.PhotoImage:
    """Crée une image Tk redimensionnée à partir de l'identité visuelle officielle."""
    raw = base64.b64decode(load_icon_base64(), validate=True)
    with Image.open(io.BytesIO(raw)) as source:
        image = source.convert("RGBA")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        rendered = image.copy()
    return ImageTk.PhotoImage(rendered, master=master)


def apply_app_icon(root: tk.Tk) -> bool:
    """Applique l'icône à la fenêtre et conserve sa référence Tkinter."""
    try:
        icon = tk.PhotoImage(data=load_icon_base64())
        root.iconphoto(True, icon)
        root._assistant_botanique_icon = icon
    except (OSError, tk.TclError, ValueError):
        LOGGER.exception("Impossible de charger l'icône de l'application")
        return False
    return True


__all__ = [
    "ICON_RESOURCE",
    "apply_app_icon",
    "icon_source_path",
    "load_brand_photo",
    "load_icon_base64",
]

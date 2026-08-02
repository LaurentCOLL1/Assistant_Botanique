"""Visionneuse agrandie pour les dernières photos de l'onglet Collection."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from PIL import Image, ImageOps, ImageTk, UnidentifiedImageError

from .usability_fixes import normalized_photo_preview_count

THUMBNAIL_SIZE = (210, 145)


def fit_photo_size(
    source_width: int,
    source_height: int,
    max_width: int,
    max_height: int,
) -> tuple[int, int]:
    """Adapte une photo à une zone sans la déformer ni dépasser sa taille native."""
    values = (source_width, source_height, max_width, max_height)
    if any(value <= 0 for value in values):
        raise ValueError("Les dimensions de la photo et de la zone doivent être positives.")
    scale = min(max_width / source_width, max_height / source_height, 1.0)
    return max(1, round(source_width * scale)), max(1, round(source_height * scale))


def _load_photo(path: Path) -> Image.Image:
    with Image.open(path) as opened:
        return ImageOps.exif_transpose(opened).convert("RGB")


class CollectionPhotoViewer(tk.Toplevel):
    """Fenêtre redimensionnable affichant une photo adaptée à l'espace disponible."""

    def __init__(
        self,
        parent: tk.Misc,
        path: Path,
        *,
        caption: str = "",
        taken_at: str = "",
    ) -> None:
        owner = parent.winfo_toplevel()
        super().__init__(owner)
        self._source_path = path
        self._source_image = _load_photo(path)
        self._display_image: ImageTk.PhotoImage | None = None
        self._resize_job: str | None = None

        title = caption.strip() or path.name or "Photo"
        self.title(f"Photo — {title}")
        self.transient(owner)
        self.resizable(True, True)
        self.minsize(420, 320)

        self.image_panel = tk.Frame(self, background="#151515")
        self.image_panel.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        self.image_label = tk.Label(
            self.image_panel,
            background="#151515",
            foreground="white",
            text="Chargement de la photo…",
            anchor="center",
        )
        self.image_label.pack(fill="both", expand=True)

        footer = ttk.Frame(self, padding=(10, 4, 10, 10))
        footer.pack(fill="x")
        metadata = " · ".join(part for part in (caption.strip(), taken_at.strip()) if part)
        ttk.Label(
            footer,
            text=metadata or path.name,
            anchor="w",
            justify="left",
            wraplength=760,
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Fermer", command=self.destroy).pack(side="right", padx=(10, 0))

        screen_width = max(640, self.winfo_screenwidth())
        screen_height = max(480, self.winfo_screenheight())
        max_window_width = max(520, round(screen_width * 0.9))
        max_window_height = max(420, round(screen_height * 0.88))
        desired_width = min(max_window_width, max(560, self._source_image.width + 40))
        desired_height = min(max_window_height, max(420, self._source_image.height + 125))
        x = max(0, (screen_width - desired_width) // 2)
        y = max(0, (screen_height - desired_height) // 2)
        self.geometry(f"{desired_width}x{desired_height}+{x}+{y}")

        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Configure>", self._on_configure)
        self.after_idle(self._render_photo)
        self.focus_set()

    def _on_configure(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._render_photo)

    def _render_photo(self) -> None:
        self._resize_job = None
        available_width = max(100, self.image_panel.winfo_width() - 16)
        available_height = max(100, self.image_panel.winfo_height() - 16)
        width, height = fit_photo_size(
            self._source_image.width,
            self._source_image.height,
            available_width,
            available_height,
        )
        if (width, height) == self._source_image.size:
            rendered = self._source_image.copy()
        else:
            rendered = self._source_image.resize(
                (width, height),
                Image.Resampling.LANCZOS,
            )
        self._display_image = ImageTk.PhotoImage(rendered)
        self.image_label.configure(image=self._display_image, text="")


def _patch_collection_photo_preview() -> None:
    from tab_gestion import TabGestion

    if getattr(TabGestion, "_collection_photo_viewer_installed", False):
        return

    def open_photo(
        self,
        path: Path | str,
        caption: str = "",
        taken_at: str = "",
    ) -> None:
        current = getattr(self, "_collection_photo_viewer", None)
        if current is not None:
            try:
                if current.winfo_exists():
                    current.destroy()
            except tk.TclError:
                pass
        try:
            viewer = CollectionPhotoViewer(
                self,
                Path(path),
                caption=caption,
                taken_at=taken_at,
            )
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            messagebox.showerror(
                "Agrandissement de la photo",
                f"La photo ne peut pas être ouverte : {exc}",
                parent=self,
            )
            return
        self._collection_photo_viewer = viewer

    def render_photos(self) -> None:
        frame = getattr(self, "photo_preview_frame", None)
        service = getattr(self, "_photo_service", None)
        if frame is None or service is None:
            return
        frame.configure(text=" Dernières photos — cliquez pour agrandir ")
        for child in frame.winfo_children():
            child.destroy()
        self._photo_images = []
        self._collection_photo_paths: list[Path] = []
        selected = self.tree.selection()
        if len(selected) != 1:
            ttk.Label(frame, text="Sélectionnez une plante pour afficher ses photos.").grid(
                row=0,
                column=0,
                sticky="w",
                padx=6,
                pady=6,
            )
            return

        settings = self._photo_settings_repo.load()
        count = normalized_photo_preview_count(
            settings.get("collection", {}).get("photo_preview_count", 2)
        )
        photos = self.repository.database.list_photos(selected[0])[:count]
        if not photos:
            ttk.Label(frame, text="Aucune photo enregistrée pour cette plante.").grid(
                row=0,
                column=0,
                sticky="w",
                padx=6,
                pady=6,
            )
            return

        ttk.Label(
            frame,
            text="Cliquez sur une vignette, ou sélectionnez-la au clavier puis appuyez sur Entrée.",
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=6, pady=(4, 0))
        for column in range(4):
            frame.columnconfigure(column, weight=1)

        displayed = 0
        for item in photos:
            path = Path(service.resolve_path(str(item.get("path") or "")))
            try:
                image = _load_photo(path)
                image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                photo_image = ImageTk.PhotoImage(image.copy())
            except (OSError, UnidentifiedImageError):
                continue

            self._photo_images.append(photo_image)
            self._collection_photo_paths.append(path)
            caption = str(item.get("caption") or "").strip()
            taken_at = str(item.get("taken_at") or "")
            label_text = caption or taken_at or "Photo"
            label = ttk.Label(
                frame,
                image=photo_image,
                text=label_text,
                compound="top",
                anchor="center",
                wraplength=210,
                cursor="hand2",
                takefocus=True,
                padding=4,
                relief="flat",
            )
            label.grid(
                row=1 + displayed // 4,
                column=displayed % 4,
                padx=6,
                pady=6,
                sticky="n",
            )

            def activate(
                _event: tk.Event | None = None,
                photo_path: Path = path,
                photo_caption: str = caption,
                photo_date: str = taken_at,
            ) -> None:
                self._open_collection_photo(photo_path, photo_caption, photo_date)

            label.bind("<Button-1>", activate)
            label.bind("<Return>", activate)
            label.bind("<space>", activate)
            label.bind("<Enter>", lambda event: event.widget.configure(relief="solid"))
            label.bind("<Leave>", lambda event: event.widget.configure(relief="flat"))
            label.bind("<FocusIn>", lambda event: event.widget.configure(relief="solid"))
            label.bind("<FocusOut>", lambda event: event.widget.configure(relief="flat"))
            displayed += 1

        if not displayed:
            ttk.Label(frame, text="Les fichiers photo sont introuvables ou illisibles.").grid(
                row=0,
                column=0,
                sticky="w",
                padx=6,
                pady=6,
            )

    TabGestion._open_collection_photo = open_photo
    TabGestion._render_collection_photos = render_photos
    TabGestion._collection_photo_viewer_installed = True


def install_collection_photo_viewer() -> None:
    """Installe l'agrandissement au clic après la création des aperçus Collection."""
    _patch_collection_photo_preview()


__all__ = [
    "CollectionPhotoViewer",
    "fit_photo_size",
    "install_collection_photo_viewer",
]

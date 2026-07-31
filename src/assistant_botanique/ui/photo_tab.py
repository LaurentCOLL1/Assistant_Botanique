"""Onglet de journal visuel et photos."""
from __future__ import annotations

from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.photos import PhotoService


class PhotoTimelineTab(ttk.Frame):
    def __init__(self, parent, database: Database):
        super().__init__(parent)
        self.database = database
        self.photo_service = PhotoService(database)
        self.plants: list[dict[str, Any]] = []
        self._image_ref = None
        self._build_ui()
        self.refresh_plants()

    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=10)
        ttk.Label(top, text="Plante").pack(side="left")
        self.combo = ttk.Combobox(top, state="readonly", width=42)
        self.combo.pack(side="left", padx=6)
        self.combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_timeline())
        ttk.Button(top, text="🔄", width=4, command=self.refresh_plants).pack(side="left")
        ttk.Button(top, text="📷 Ajouter une photo", command=self.add_photo, style="Accent.TButton").pack(side="left", padx=8)
        ttk.Button(top, text="Supprimer la photo", command=self.delete_photo).pack(side="left", padx=3)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=3)
        body.add(right, weight=2)

        self.timeline = ttk.Treeview(left, columns=("date", "kind", "details"), show="headings", selectmode="browse")
        self.timeline.heading("date", text="Date")
        self.timeline.heading("kind", text="Type")
        self.timeline.heading("details", text="Détails")
        self.timeline.column("date", width=110)
        self.timeline.column("kind", width=100)
        self.timeline.column("details", width=430)
        self.timeline.pack(fill="both", expand=True)
        self.timeline.bind("<<TreeviewSelect>>", self.show_selected)

        self.preview = ttk.Label(right, text="Sélectionnez une photo", anchor="center")
        self.preview.pack(fill="both", expand=True, padx=8, pady=8)
        self.caption = ttk.Label(right, text="", wraplength=320, justify="left")
        self.caption.pack(fill="x", padx=8, pady=8)

    def refresh_plants(self) -> None:
        self.plants = self.database.load_plants()
        values = [f"{plant['surnom']} — {plant['species_id']}" for plant in self.plants]
        self.combo["values"] = values
        if values:
            current = self.combo.current()
            self.combo.current(current if current >= 0 else 0)
        self.refresh_timeline()

    def _plant_id(self) -> str | None:
        index = self.combo.current()
        return self.plants[index]["id"] if 0 <= index < len(self.plants) else None

    def refresh_timeline(self) -> None:
        self.timeline.delete(*self.timeline.get_children())
        plant_id = self._plant_id()
        if not plant_id:
            return
        for item in self.database.timeline(plant_id):
            identifier = f"{item['kind']}:{item['id']}"
            date_value = item.get("event_date", "")
            self.timeline.insert("", "end", iid=identifier, values=(date_value, item["kind"], item.get("details") or item.get("title", "")))

    def add_photo(self) -> None:
        plant_id = self._plant_id()
        if not plant_id:
            messagebox.showwarning("Photo", "Sélectionnez une plante.")
            return
        source = filedialog.askopenfilename(
            title="Choisir une photo",
            filetypes=(("Images", "*.jpg *.jpeg *.png *.webp *.gif"), ("Tous les fichiers", "*.*")),
        )
        if not source:
            return
        caption = simpledialog.askstring("Photo", "Légende ou observation", parent=self) or ""
        try:
            self.photo_service.add_photo(plant_id, source, caption)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Photo", str(exc))
            return
        self.refresh_timeline()

    def _selected_photo(self) -> dict[str, Any] | None:
        selection = self.timeline.selection()
        if not selection or not selection[0].startswith("photo:"):
            return None
        photo_id = selection[0].split(":", 1)[1]
        return next((photo for photo in self.database.list_photos(self._plant_id()) if photo["id"] == photo_id), None)

    def show_selected(self, _event=None) -> None:
        photo = self._selected_photo()
        self._image_ref = None
        if not photo:
            self.preview.configure(image="", text="Sélectionnez une photo")
            self.caption.configure(text="")
            return
        path = self.photo_service.resolve_path(photo["path"])
        self.caption.configure(text=photo.get("caption", ""))
        try:
            from PIL import Image, ImageTk

            image = Image.open(path)
            image.thumbnail((420, 420))
            self._image_ref = ImageTk.PhotoImage(image)
            self.preview.configure(image=self._image_ref, text="")
        except Exception:
            self.preview.configure(image="", text=f"Photo enregistrée :\n{path}")

    def delete_photo(self) -> None:
        photo = self._selected_photo()
        if not photo:
            messagebox.showwarning("Photo", "Sélectionnez une photo dans la chronologie.")
            return
        if messagebox.askyesno("Photo", "Supprimer définitivement cette photo ?"):
            self.photo_service.delete_photo(photo["id"])
            self.refresh_timeline()
            self.show_selected()

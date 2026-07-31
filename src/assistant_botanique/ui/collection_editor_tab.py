"""Modification sûre des exemplaires déjà enregistrés dans la collection."""
from __future__ import annotations

import tkinter as tk
from copy import deepcopy
from datetime import date
from tkinter import messagebox, ttk
from typing import Any, Callable

from core import ValidationError, format_date_fr, parse_date, scientific_name, vernacular_names
from assistant_botanique.infrastructure.database import Database


def apply_collection_correction(
    plant: dict[str, Any],
    *,
    species_id: str,
    nickname: str,
    pot_l: str | float,
    last_watering: str,
    location: str,
    exposure: str,
    pot_material: str,
    substrate: str,
) -> dict[str, Any]:
    """Retourne une copie corrigée sans perdre l'identifiant ni l'historique."""
    corrected = deepcopy(plant)
    species_id = str(species_id).strip()
    nickname = str(nickname).strip()
    if not species_id:
        raise ValidationError("Sélectionnez une espèce.")
    if not nickname:
        raise ValidationError("Le surnom ne peut pas être vide.")
    try:
        volume = float(str(pot_l).strip().replace(",", "."))
    except ValueError as exc:
        raise ValidationError("Le volume du pot doit être un nombre.") from exc
    if not 0 < volume <= 100000:
        raise ValidationError("Le volume du pot doit être positif et réaliste.")
    watering_date = parse_date(last_watering)
    if watering_date > date.today():
        raise ValidationError("La date du dernier arrosage ne peut pas être dans le futur.")

    context = corrected.get("contexte") if isinstance(corrected.get("contexte"), dict) else {}
    corrected.update(
        {
            "species_id": species_id,
            "surnom": nickname,
            "pot_l": volume,
            "date_arrosage": format_date_fr(watering_date),
            "contexte": {
                **context,
                "emplacement": location or "interieur",
                "exposition": exposure or "non_renseignee",
                "matiere_pot": pot_material or "non_renseignee",
                "substrat": substrate.strip() or "non_renseigne",
            },
        }
    )
    return corrected


class CollectionEditorTab(ttk.Frame):
    LOCATIONS = ("interieur", "exterieur", "serre")
    EXPOSURES = ("non_renseignee", "ombre", "mi_ombre", "lumiere_vive", "soleil_direct")
    POT_MATERIALS = ("non_renseignee", "plastique", "terre_cuite", "ceramique", "autre")

    def __init__(
        self,
        parent,
        database: Database,
        catalogue: list[dict[str, Any]],
        on_collection_refresh: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.catalogue = catalogue
        self.on_collection_refresh = on_collection_refresh
        self.plants: list[dict[str, Any]] = []
        self.species = sorted(
            ((profile["id"], self._profile_label(profile)) for profile in catalogue),
            key=lambda item: item[1].casefold(),
        )
        self.species_by_label = {label: identifier for identifier, label in self.species}
        self.label_by_species = {identifier: label for identifier, label in self.species}
        self._build_ui()
        self.refresh()

    @staticmethod
    def _profile_label(profile: dict[str, Any]) -> str:
        common = ", ".join(vernacular_names(profile))
        return f"{scientific_name(profile)} — {common}" if common else scientific_name(profile)

    def _build_ui(self) -> None:
        ttk.Label(
            self,
            text=(
                "Sélectionnez une plante puis corrigez ses informations. L'identifiant, les photos et l'historique "
                "des soins sont conservés."
            ),
            wraplength=1050,
            justify="left",
        ).pack(fill="x", padx=12, pady=(10, 5))

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        left = ttk.Frame(body)
        right = ttk.LabelFrame(body, text=" Modifier la plante sélectionnée ")
        body.add(left, weight=2)
        body.add(right, weight=3)

        self.tree = ttk.Treeview(left, columns=("name", "species", "watering"), show="headings", selectmode="browse")
        self.tree.heading("name", text="Surnom")
        self.tree.heading("species", text="Espèce")
        self.tree.heading("watering", text="Dernier arrosage")
        self.tree.column("name", width=150)
        self.tree.column("species", width=220)
        self.tree.column("watering", width=110, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.load_selected)

        right.columnconfigure(1, weight=1)
        labels = (
            ("Espèce", 0), ("Surnom", 1), ("Volume du pot (L)", 2),
            ("Dernier arrosage (JJ/MM/AAAA)", 3), ("Emplacement", 4),
            ("Exposition", 5), ("Matière du pot", 6), ("Substrat", 7),
        )
        for text, row in labels:
            ttk.Label(right, text=text).grid(row=row, column=0, sticky="w", padx=8, pady=6)

        self.species_var = tk.StringVar()
        self.species_combo = ttk.Combobox(right, textvariable=self.species_var, state="readonly", values=[label for _, label in self.species])
        self.species_combo.grid(row=0, column=1, sticky="ew", padx=8, pady=6)
        self.nickname = ttk.Entry(right)
        self.nickname.grid(row=1, column=1, sticky="ew", padx=8, pady=6)
        self.pot = ttk.Entry(right)
        self.pot.grid(row=2, column=1, sticky="ew", padx=8, pady=6)
        self.watering = ttk.Entry(right)
        self.watering.grid(row=3, column=1, sticky="ew", padx=8, pady=6)
        self.location = ttk.Combobox(right, state="readonly", values=self.LOCATIONS)
        self.location.grid(row=4, column=1, sticky="ew", padx=8, pady=6)
        self.exposure = ttk.Combobox(right, state="readonly", values=self.EXPOSURES)
        self.exposure.grid(row=5, column=1, sticky="ew", padx=8, pady=6)
        self.pot_material = ttk.Combobox(right, state="readonly", values=self.POT_MATERIALS)
        self.pot_material.grid(row=6, column=1, sticky="ew", padx=8, pady=6)
        self.substrate = ttk.Entry(right)
        self.substrate.grid(row=7, column=1, sticky="ew", padx=8, pady=6)

        actions = ttk.Frame(right)
        actions.grid(row=8, column=0, columnspan=2, sticky="e", padx=8, pady=12)
        ttk.Button(actions, text="Annuler les changements", command=self.load_selected).pack(side="left", padx=3)
        ttk.Button(actions, text="Enregistrer les corrections", command=self.save, style="Accent.TButton").pack(side="left", padx=3)

    def refresh(self) -> None:
        current = self._selected_id()
        self.plants = self.database.load_plants()
        self.tree.delete(*self.tree.get_children())
        for plant in self.plants:
            label = self.label_by_species.get(plant["species_id"], plant["species_id"])
            self.tree.insert("", "end", iid=plant["id"], values=(plant["surnom"], label.split(" — ", 1)[0], plant["date_arrosage"]))
        if current and self.tree.exists(current):
            self.tree.selection_set(current)
        elif self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])
        self.load_selected()

    def _selected_id(self) -> str | None:
        selection = self.tree.selection()
        return selection[0] if selection else None

    def load_selected(self, _event=None) -> None:
        plant_id = self._selected_id()
        plant = next((item for item in self.plants if item["id"] == plant_id), None)
        if not plant:
            return
        context = plant.get("contexte") if isinstance(plant.get("contexte"), dict) else {}
        self.species_var.set(self.label_by_species.get(plant["species_id"], ""))
        for entry, value in (
            (self.nickname, plant["surnom"]),
            (self.pot, f"{float(plant['pot_l']):g}"),
            (self.watering, plant["date_arrosage"]),
            (self.substrate, context.get("substrat", "non_renseigne")),
        ):
            entry.delete(0, tk.END)
            entry.insert(0, value)
        self.location.set(context.get("emplacement", "interieur"))
        self.exposure.set(context.get("exposition", "non_renseignee"))
        self.pot_material.set(context.get("matiere_pot", "non_renseignee"))

    def save(self) -> None:
        plant_id = self._selected_id()
        index = next((i for i, item in enumerate(self.plants) if item["id"] == plant_id), None)
        if index is None:
            messagebox.showwarning("Collection", "Sélectionnez une plante.")
            return
        try:
            corrected = apply_collection_correction(
                self.plants[index],
                species_id=self.species_by_label.get(self.species_var.get(), ""),
                nickname=self.nickname.get(),
                pot_l=self.pot.get(),
                last_watering=self.watering.get(),
                location=self.location.get(),
                exposure=self.exposure.get(),
                pot_material=self.pot_material.get(),
                substrate=self.substrate.get(),
            )
            updated = list(self.plants)
            updated[index] = corrected
            self.database.save_plants(updated)
        except (OSError, ValidationError) as exc:
            messagebox.showerror("Modification de la collection", str(exc))
            return
        self.plants = updated
        if self.on_collection_refresh:
            self.on_collection_refresh()
        self.refresh()
        if plant_id and self.tree.exists(plant_id):
            self.tree.selection_set(plant_id)
        messagebox.showinfo("Collection", "Les corrections ont été enregistrées.")

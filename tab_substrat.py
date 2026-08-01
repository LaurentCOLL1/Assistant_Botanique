"""Générateur de substrat avec ratios validés et volumes explicites."""
from __future__ import annotations

import tkinter as tk
import unicodedata
from tkinter import messagebox, ttk
from typing import Any

from app_data import DATABASE_BY_ID, DATABASE_BY_SCIENTIFIC_NAME, DATABASE_PLANTES, PROFILS_GENERIQUES
from core import ValidationError, scientific_name, vernacular_names
from recipe_engine import build_recipe, forbidden_ingredients


INGREDIENT_CATEGORIES = {
    "Bases organiques et terres": [
        "Tourbe blonde", "Fibre de coco", "Chips de coco", "Sphaigne sèche", "Sphaigne du Chili",
        "Mousse de sphaigne vivante", "Pépites de tourbe", "Humus de lombric", "Terreau de feuilles",
        "Terreau argileux (Aquatique / Nénuphars)", "Terre franche / Terre de jardin", "Terreau de semis",
        "Terreau horticole", "Terreau léger", "Terreau plantes vertes",
    ],
    "Minéraux et drainants": [
        "Sable grossier", "Perlite", "Pumice", "Pouzzolane", "Micro-pouzzolane", "Vermiculite",
        "Zéolite", "Kanuma", "Akadama", "Kiryu", "Seramis", "Argile calcinée (Moler)",
        "Billes d'argile", "Gravier de Quartz", "Sable de quartz",
    ],
    "Additifs et spécialités": [
        "Charbon actif", "Charbon de bambou", "Écorces de pin", "Farine de basalte",
        "Poudre de Calcaire / Dolomie", "Compost mûr",
    ],
}

PRIMARY_INGREDIENT_CATEGORIES = (
    "Bases organiques et terres",
    "Minéraux et drainants",
)
SPECIALTY_INGREDIENT_CATEGORY = "Additifs et spécialités"
DEFAULT_AVAILABLE_INGREDIENTS = {
    "Tourbe blonde",
    "Fibre de coco",
    "Perlite",
    "Pouzzolane",
    "Charbon actif",
    "Écorces de pin",
}


def normalize_profile_search(value: str) -> str:
    """Normalise une recherche pour ignorer casse, accents et ponctuation décorative."""
    decomposed = unicodedata.normalize("NFKD", str(value))
    without_accents = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(without_accents.casefold().split())


def filter_profile_labels(labels: list[str], query: str) -> list[str]:
    """Retourne les libellés contenant chacun des termes de la recherche."""
    terms = normalize_profile_search(query).split()
    if not terms:
        return list(labels)
    return [
        label
        for label in labels
        if all(term in normalize_profile_search(label) for term in terms)
    ]


class TabSubstrat(ttk.Frame):
    def __init__(self, parent, settings: dict[str, Any] | None = None, on_settings_changed=None):
        super().__init__(parent)
        self.settings = settings if settings is not None else {}
        self.on_settings_changed = on_settings_changed
        self.combo_mapping: dict[str, dict] = {}
        self.profile_values: list[str] = []
        self.mes_plantes: list[dict] = []
        self.ing_vars: dict[str, tk.BooleanVar] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        main = ttk.LabelFrame(self, text=" Recette de substrat sur mesure ")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        search_row = ttk.Frame(main)
        search_row.pack(fill="x", padx=8, pady=(8, 3))
        ttk.Label(search_row, text="Rechercher une plante").pack(side="left", padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._profile_search_changed)
        self.entry_profile_search = ttk.Entry(search_row, textvariable=self.search_var, width=48)
        self.entry_profile_search.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_profile_search.bind("<Escape>", lambda _event: self._clear_profile_search())
        ttk.Button(search_row, text="Effacer", command=self._clear_profile_search).pack(side="left", padx=(4, 8))
        self.search_result_label = ttk.Label(search_row, text="0 résultat", style="Muted.TLabel")
        self.search_result_label.pack(side="right")

        top = ttk.Frame(main)
        top.pack(fill="x", padx=8, pady=(3, 6))
        ttk.Label(top, text="Plante ou profil").pack(side="left", padx=(0, 5))
        self.combo_profile = ttk.Combobox(top, state="readonly", width=68)
        self.combo_profile.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Label(top, text="Volume (L)").pack(side="left", padx=(10, 5))
        self.entry_volume = ttk.Entry(top, width=10)
        self.entry_volume.insert(0, "2.0")
        self.entry_volume.pack(side="left")

        ttk.Label(
            main,
            text="Cochez les ingrédients réellement disponibles. Lorsqu'un rôle possède plusieurs ingrédients disponibles, le volume est réparti également.",
            style="Muted.TLabel",
            wraplength=1000,
        ).pack(anchor="w", padx=8, pady=(0, 5))

        ingredient_area = ttk.Frame(main)
        ingredient_area.pack(fill="x", padx=8, pady=4)
        ingredient_area.columnconfigure(0, weight=3)
        ingredient_area.columnconfigure(2, weight=1)

        primary_panel = ttk.Frame(ingredient_area)
        primary_panel.grid(row=0, column=0, sticky="nsew")
        for column in range(4):
            primary_panel.columnconfigure(column, weight=1)

        ttk.Separator(ingredient_area, orient="vertical").grid(
            row=0,
            column=1,
            sticky="ns",
            padx=(12, 16),
            pady=4,
        )

        specialty_panel = ttk.Frame(ingredient_area)
        specialty_panel.grid(row=0, column=2, sticky="nsew")
        specialty_panel.columnconfigure(0, weight=1)
        specialty_panel.columnconfigure(1, weight=1)

        saved_stock = self.settings.get("ingredient_stock", {}) if isinstance(self.settings.get("ingredient_stock"), dict) else {}

        def add_ingredient(parent: ttk.Frame, ingredient: str, row: int, column: int) -> None:
            default = bool(saved_stock.get(ingredient, ingredient in DEFAULT_AVAILABLE_INGREDIENTS))
            variable = tk.BooleanVar(value=default)
            variable.trace_add("write", self._stock_changed)
            self.ing_vars[ingredient] = variable
            ttk.Checkbutton(parent, text=ingredient, variable=variable).grid(
                row=row,
                column=column,
                sticky="w",
                padx=6,
                pady=2,
            )

        row = 0
        for category in PRIMARY_INGREDIENT_CATEGORIES:
            ingredients = INGREDIENT_CATEGORIES[category]
            ttk.Label(primary_panel, text=category, font=("Segoe UI", 9, "bold")).grid(
                row=row,
                column=0,
                columnspan=4,
                sticky="w",
                padx=4,
                pady=(8, 3),
            )
            row += 1
            for index, ingredient in enumerate(ingredients):
                add_ingredient(primary_panel, ingredient, row + index // 4, index % 4)
            row += (len(ingredients) + 3) // 4

        specialty_ingredients = INGREDIENT_CATEGORIES[SPECIALTY_INGREDIENT_CATEGORY]
        ttk.Label(
            specialty_panel,
            text=SPECIALTY_INGREDIENT_CATEGORY,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=4, pady=(8, 3))
        for index, ingredient in enumerate(specialty_ingredients):
            add_ingredient(specialty_panel, ingredient, 1 + index // 2, index % 2)

        action_bar = ttk.Frame(main)
        action_bar.pack(fill="x", padx=8, pady=5)
        ttk.Button(action_bar, text="🧪 Calculer", command=self.calculer_recette, style="Accent.TButton").pack(side="left")
        ttk.Button(action_bar, text="Tout décocher", command=lambda: self._set_all(False)).pack(side="left", padx=4)
        ttk.Button(action_bar, text="Tout cocher", command=lambda: self._set_all(True)).pack(side="left", padx=4)

        self.output = tk.Text(main, height=14, wrap="word", state="disabled", font=("Consolas", 9))
        self.output.pack(fill="both", expand=True, padx=8, pady=(2, 8))

    def _stock_changed(self, *_args) -> None:
        self.settings["ingredient_stock"] = {name: variable.get() for name, variable in self.ing_vars.items()}
        if self.on_settings_changed:
            self.on_settings_changed()

    def _set_all(self, value: bool) -> None:
        for variable in self.ing_vars.values():
            variable.set(value)

    def _profile_search_changed(self, *_args) -> None:
        self._apply_profile_filter()

    def _clear_profile_search(self) -> str:
        self.search_var.set("")
        self.entry_profile_search.focus_set()
        return "break"

    def _apply_profile_filter(self) -> None:
        selected = self.combo_profile.get()
        visible_values = filter_profile_labels(self.profile_values, self.search_var.get())
        self.combo_profile["values"] = visible_values

        count = len(visible_values)
        self.search_result_label.configure(text=f"{count} résultat{'s' if count != 1 else ''}")
        if selected in visible_values:
            self.combo_profile.set(selected)
        elif visible_values:
            self.combo_profile.current(0)
        else:
            self.combo_profile.set("")

    @staticmethod
    def _resolve_profile(identifier: str) -> dict | None:
        return DATABASE_BY_ID.get(identifier) or DATABASE_BY_SCIENTIFIC_NAME.get(identifier)

    def actualiser_combo_substrat(self, plants: list[dict]) -> None:
        self.mes_plantes = plants
        selected = self.combo_profile.get()
        self.combo_mapping.clear()
        values: list[str] = []
        for generic in PROFILS_GENERIQUES:
            label = f"🌐 {generic.get('nom_sci', 'Profil générique')} — {generic.get('nom_vern', '')}"
            values.append(label)
            self.combo_mapping[label] = generic
        for plant in plants:
            profile = self._resolve_profile(str(plant.get("species_id", "")))
            if not profile:
                continue
            vernacular = ", ".join(vernacular_names(profile))
            label = f"🪴 {plant.get('surnom', 'Sans nom')} — {scientific_name(profile)}"
            if vernacular:
                label += f" — {vernacular}"
            values.append(label)
            self.combo_mapping[label] = profile
        for profile in DATABASE_PLANTES:
            label = f"📋 {scientific_name(profile)} — {', '.join(vernacular_names(profile))}"
            values.append(label)
            self.combo_mapping[label] = profile
        self.profile_values = values
        self._apply_profile_filter()
        visible_values = list(self.combo_profile["values"])
        if selected in visible_values:
            self.combo_profile.set(selected)

    def calculer_recette(self) -> None:
        try:
            volume = float(self.entry_volume.get().strip().replace(",", "."))
            if volume <= 0 or volume > 100000:
                raise ValidationError("Le volume doit être positif et réaliste.")
        except (ValueError, ValidationError) as exc:
            messagebox.showerror("Recette", str(exc) if str(exc) else "Volume invalide.")
            return
        profile = self.combo_mapping.get(self.combo_profile.get())
        if not profile:
            messagebox.showwarning("Recette", "Sélectionnez une plante ou un profil.")
            return
        stock = {name: variable.get() for name, variable in self.ing_vars.items()}
        try:
            recipe = build_recipe(profile, volume, stock)
        except ValidationError as exc:
            messagebox.showerror("Recette", str(exc))
            return

        lines = [
            "=" * 72,
            f"RECETTE POUR {volume:.2f} L — {scientific_name(profile).upper()}",
            "=" * 72,
            "",
        ]
        for line in recipe.lines:
            lines.append(f"• {line.role} — {line.ratio * 100:.1f}% = {line.liters:.3f} L")
            if line.ingredients:
                for ingredient, liters in line.ingredients:
                    lines.append(f"    - {ingredient}: {liters:.3f} L")
            else:
                lines.append("    ❌ Aucun ingrédient disponible.")
                if line.missing:
                    lines.append("    Suggestions: " + " / ".join(line.missing[:5]))
            lines.append("")

        selected = [name for name, available in stock.items() if available]
        forbidden = forbidden_ingredients(profile, selected)
        if forbidden:
            lines.append("⚠️ INGRÉDIENTS À NE PAS UTILISER POUR CETTE FICHE")
            lines.extend(f"    - {item}" for item in forbidden)
            lines.append("")

        advice = profile.get("conseil")
        if advice:
            lines.append("CONSEIL")
            lines.append(str(advice))
            lines.append("")
        lines.append("Contrôle: la somme des volumes de rôles correspond au volume demandé.")
        if recipe.warnings:
            lines.append("Avertissements: " + " | ".join(recipe.warnings))

        self.output.configure(state="normal")
        self.output.delete("1.0", tk.END)
        self.output.insert("1.0", "\n".join(lines))
        self.output.configure(state="disabled")

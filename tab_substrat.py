"""Générateur de substrat avec ratios validés et volumes explicites."""
from __future__ import annotations

import tkinter as tk
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


class TabSubstrat(ttk.Frame):
    def __init__(self, parent, settings: dict[str, Any] | None = None, on_settings_changed=None):
        super().__init__(parent)
        self.settings = settings if settings is not None else {}
        self.on_settings_changed = on_settings_changed
        self.combo_mapping: dict[str, dict] = {}
        self.mes_plantes: list[dict] = []
        self.ing_vars: dict[str, tk.BooleanVar] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        main = ttk.LabelFrame(self, text=" Recette de substrat sur mesure ")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        top = ttk.Frame(main)
        top.pack(fill="x", padx=8, pady=6)
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

        canvas_frame = ttk.Frame(main)
        canvas_frame.pack(fill="x", padx=8, pady=4)
        canvas = tk.Canvas(canvas_frame, height=300, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        inside = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=inside, anchor="nw")
        inside.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        saved_stock = self.settings.get("ingredient_stock", {}) if isinstance(self.settings.get("ingredient_stock"), dict) else {}
        row = 0
        for category, ingredients in INGREDIENT_CATEGORIES.items():
            ttk.Label(inside, text=category, font=("Segoe UI", 9, "bold")).grid(row=row, column=0, columnspan=4, sticky="w", padx=4, pady=(8, 3))
            row += 1
            for index, ingredient in enumerate(ingredients):
                default = bool(saved_stock.get(ingredient, ingredient in {"Tourbe blonde", "Fibre de coco", "Perlite", "Pouzzolane", "Charbon actif", "Écorces de pin"}))
                variable = tk.BooleanVar(value=default)
                variable.trace_add("write", self._stock_changed)
                self.ing_vars[ingredient] = variable
                ttk.Checkbutton(inside, text=ingredient, variable=variable).grid(row=row + index // 4, column=index % 4, sticky="w", padx=6, pady=2)
            row += (len(ingredients) + 3) // 4

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

    @staticmethod
    def _resolve_profile(identifier: str) -> dict | None:
        return DATABASE_BY_ID.get(identifier) or DATABASE_BY_SCIENTIFIC_NAME.get(identifier)

    def actualiser_combo_substrat(self, plants: list[dict]) -> None:
        self.mes_plantes = plants
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
            label = f"🪴 {plant.get('surnom', 'Sans nom')} — {scientific_name(profile)}"
            values.append(label)
            self.combo_mapping[label] = profile
        for profile in DATABASE_PLANTES:
            label = f"📋 {scientific_name(profile)} — {', '.join(vernacular_names(profile))}"
            values.append(label)
            self.combo_mapping[label] = profile
        self.combo_profile["values"] = values
        if values and not self.combo_profile.get():
            self.combo_profile.current(0)

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

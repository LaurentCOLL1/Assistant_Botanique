"""Onglet des recommandations de soins adaptatives."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable

from core import format_date_fr, scientific_name
from assistant_botanique.domain.adaptive_care import recommend_care
from assistant_botanique.infrastructure.database import Database


class AdaptiveCareTab(ttk.Frame):
    def __init__(
        self,
        parent,
        database: Database,
        profiles_by_id: dict[str, dict[str, Any]],
        on_collection_refresh: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self.database = database
        self.profiles_by_id = profiles_by_id
        self.on_collection_refresh = on_collection_refresh
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        info = ttk.Label(
            self,
            text=(
                "Les dates proposées sont des contrôles personnalisés. Elles combinent la fiche de l'espèce, "
                "le pot, l'exposition et vos observations ; elles ne déclenchent jamais un arrosage automatique."
            ),
            wraplength=1100,
            justify="left",
        )
        info.pack(fill="x", padx=12, pady=(10, 5))

        columns = ("plant", "interval", "next", "confidence", "status")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        headings = {
            "plant": "Plante",
            "interval": "Intervalle appris",
            "next": "Prochain contrôle",
            "confidence": "Confiance",
            "status": "État",
        }
        widths = {"plant": 230, "interval": 130, "next": 140, "confidence": 100, "status": 260}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="w")
        self.tree.pack(fill="both", expand=True, padx=12, pady=5)
        self.tree.bind("<<TreeviewSelect>>", self._show_details)

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=12, pady=5)
        ttk.Button(actions, text="🔄 Actualiser", command=self.refresh).pack(side="left", padx=3)
        ttk.Button(actions, text="Substrat sec", command=lambda: self._record("substrat_sec", "Substrat sec au contrôle")).pack(side="left", padx=3)
        ttk.Button(actions, text="Encore humide", command=lambda: self._record("encore_humide", "Substrat encore humide au contrôle")).pack(side="left", padx=3)
        ttk.Button(actions, text="💧 Arrosé aujourd'hui", command=lambda: self._record("arrosage", "Arrosage validé après contrôle"), style="Accent.TButton").pack(side="left", padx=3)
        ttk.Button(actions, text="Ajouter une observation", command=self._add_note).pack(side="left", padx=3)

        self.details = tk.Text(self, height=8, wrap="word", state="disabled")
        self.details.pack(fill="x", padx=12, pady=(5, 12))

    def _selected_id(self) -> str | None:
        selected = self.tree.selection()
        return selected[0] if selected else None

    def refresh(self) -> None:
        current = self._selected_id()
        self.tree.delete(*self.tree.get_children())
        today = date.today()
        for plant in self.database.load_plants():
            profile = self.profiles_by_id.get(plant["species_id"])
            if not profile:
                self.tree.insert("", "end", iid=plant["id"], values=(plant["surnom"], "—", "—", "—", "Fiche introuvable"))
                continue
            recommendation = recommend_care(profile, plant, today=today)
            if recommendation.next_check is None:
                next_label = "Repos"
                state = "Repos saisonnier"
            else:
                next_label = format_date_fr(recommendation.next_check)
                delta = (recommendation.next_check - today).days
                if delta < 0:
                    state = f"Contrôle en retard de {-delta} j"
                elif delta == 0:
                    state = "Contrôle aujourd'hui"
                else:
                    state = f"Contrôle dans {delta} j"
            self.tree.insert(
                "", "end", iid=plant["id"],
                values=(plant["surnom"], f"{recommendation.interval_days} jours", next_label, recommendation.confidence_label, state),
            )
        if current and self.tree.exists(current):
            self.tree.selection_set(current)
        elif self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])
        self._show_details()

    def _show_details(self, _event=None) -> None:
        plant_id = self._selected_id()
        text = "Sélectionnez une plante."
        if plant_id:
            plant = next((item for item in self.database.load_plants() if item["id"] == plant_id), None)
            profile = self.profiles_by_id.get(plant["species_id"]) if plant else None
            if plant and profile:
                recommendation = recommend_care(profile, plant)
                text = (
                    f"{plant['surnom']} — {scientific_name(profile)}\n"
                    f"Recommandation : contrôler après environ {recommendation.interval_days} jours.\n"
                    f"Confiance : {recommendation.confidence_label} ({recommendation.confidence:.0%}).\n\n"
                    + "\n".join(f"• {item}" for item in recommendation.explanation)
                )
        self.details.configure(state="normal")
        self.details.delete("1.0", tk.END)
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def _record(self, event_type: str, note: str) -> None:
        plant_id = self._selected_id()
        if not plant_id:
            messagebox.showwarning("Observation", "Sélectionnez une plante.")
            return
        self.database.add_care_event(plant_id, event_type, note=note)
        if self.on_collection_refresh:
            self.on_collection_refresh()
        self.refresh()

    def _add_note(self) -> None:
        plant_id = self._selected_id()
        if not plant_id:
            return
        note = simpledialog.askstring("Observation", "Que souhaitez-vous noter ?", parent=self)
        if note:
            self.database.add_care_event(plant_id, "observation", note=note)
            if self.on_collection_refresh:
                self.on_collection_refresh()
            self.refresh()

"""Assistant de diagnostic botanique prudent et contextualisé."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from app_data import DATABASE_BY_ID, DATABASE_BY_SCIENTIFIC_NAME, DIAGNOSTICS_DATA
from core import scientific_name


class TabDiagnostic(ttk.Frame):
    def __init__(self, parent, collection_provider: Callable[[], list[dict]] | None = None):
        super().__init__(parent)
        self.collection_provider = collection_provider or (lambda: [])
        self.plant_mapping: dict[str, dict] = {}
        self._build_ui()
        self.refresh_plants()
        self.analyser_symptome()

    def _build_ui(self) -> None:
        frame = ttk.LabelFrame(self, text=" Diagnostic d'orientation ")
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        controls = ttk.Frame(frame)
        controls.pack(fill="x", padx=8, pady=8)
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="Plante").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.combo_plant = ttk.Combobox(controls, state="readonly")
        self.combo_plant.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Label(controls, text="Symptôme").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.combo_symptom = ttk.Combobox(controls, values=list(DIAGNOSTICS_DATA.keys()), state="readonly")
        self.combo_symptom.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        if DIAGNOSTICS_DATA:
            self.combo_symptom.current(0)
        ttk.Button(controls, text="Analyser", command=self.analyser_symptome, style="Accent.TButton").grid(row=0, column=2, rowspan=2, padx=6, pady=4)
        self.output = tk.Text(frame, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    @staticmethod
    def _resolve_profile(identifier: str) -> dict | None:
        return DATABASE_BY_ID.get(identifier) or DATABASE_BY_SCIENTIFIC_NAME.get(identifier)

    def refresh_plants(self) -> None:
        current = self.combo_plant.get() if hasattr(self, "combo_plant") else ""
        values = ["— Diagnostic général —"]
        self.plant_mapping = {}
        for plant in self.collection_provider():
            profile = self._resolve_profile(str(plant.get("species_id", "")))
            label = f"{plant.get('surnom', 'Sans nom')} — {scientific_name(profile or {'nom_sci': plant.get('species_id')})}"
            values.append(label)
            self.plant_mapping[label] = plant
        self.combo_plant["values"] = values
        self.combo_plant.set(current if current in values else values[0])

    def analyser_symptome(self) -> None:
        symptom = self.combo_symptom.get()
        data = DIAGNOSTICS_DATA.get(symptom)
        if not data:
            return
        selected_plant = self.plant_mapping.get(self.combo_plant.get())
        context_lines: list[str] = []
        if selected_plant:
            context = selected_plant.get("contexte", {})
            context_lines = [
                f"Plante concernée : {selected_plant.get('surnom')}",
                f"Contexte enregistré : {context.get('emplacement', 'non renseigné')}, exposition {context.get('exposition', 'non renseignée')}, pot {selected_plant.get('pot_l', '?')} L.",
                "",
            ]
        lines = [
            f"DIAGNOSTIC D'ORIENTATION — {symptom}",
            "=" * 72,
            *context_lines,
            "CAUSES POSSIBLES",
            str(data.get("cause", "Non renseigné")),
            "",
            "ACTIONS PRUDENTES",
            str(data.get("action", "Non renseigné")),
            "",
            "IMPORTANT",
            "Ce résultat ne confirme pas une maladie. Vérifiez d'abord l'humidité réelle du substrat, les racines, les ravageurs, la lumière et les changements récents. Isolez la plante en cas de suspicion contagieuse. Pour une espèce rare, toxique ou une atteinte rapide, demandez l'avis d'un professionnel ou d'un service phytosanitaire.",
        ]
        self.output.configure(state="normal")
        self.output.delete("1.0", tk.END)
        self.output.insert("1.0", "\n".join(lines))
        self.output.configure(state="disabled")

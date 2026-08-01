"""Diagnostic guidé, prudent et contextualisé par la collection."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from app_data import DATABASE_BY_ID, DATABASE_BY_SCIENTIFIC_NAME
from core import scientific_name
from assistant_botanique.domain.guided_diagnostic import DiagnosticAnswers, diagnose


class TabDiagnostic(ttk.Frame):
    QUESTIONS = (
        ("affected_part", "Quelle partie est principalement touchée ?", ("feuilles", "jeunes feuilles", "tiges", "racines", "fleurs", "plante entière")),
        ("symptom", "Quel symptôme décrit le mieux le problème ?", ("feuilles jaunies", "bords bruns ou secs", "taches", "tissus mous ou pourris", "feuilles déformées ou enroulées", "chute de feuilles", "croissance pâle ou faible")),
        ("progression", "Comment le problème évolue-t-il ?", ("rapide", "progressif", "stable", "inconnu")),
        ("substrate", "Quel est l'état du substrat en profondeur ?", ("sec", "légèrement humide", "humide depuis longtemps", "inconnu")),
        ("pests", "Voyez-vous des ravageurs ou des traces ?", ("non", "oui", "traces suspectes", "inconnu")),
        ("recent_change", "Un changement récent a-t-il eu lieu ?", ("aucun", "déplacement ou changement de lumière", "rempotage", "changement d'arrosage", "fertilisation ou traitement", "coup de froid ou chaleur")),
    )

    def __init__(self, parent, collection_provider: Callable[[], list[dict]] | None = None):
        super().__init__(parent)
        self.collection_provider = collection_provider or (lambda: [])
        self.plant_mapping: dict[str, dict] = {}
        self.answers: dict[str, str] = {}
        self.step = 0
        self._build_ui()
        self.refresh_plants()
        self._show_step()

    @staticmethod
    def _resolve_profile(identifier: str) -> dict | None:
        return DATABASE_BY_ID.get(identifier) or DATABASE_BY_SCIENTIFIC_NAME.get(identifier)

    def _build_ui(self) -> None:
        header = ttk.LabelFrame(self, text=" Diagnostic guidé d'orientation ")
        header.pack(fill="x", padx=12, pady=(10, 5))
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="Plante concernée").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        self.combo_plant = ttk.Combobox(header, state="readonly")
        self.combo_plant.grid(row=0, column=1, sticky="ew", padx=8, pady=8)
        ttk.Button(header, text="Recommencer", command=self.restart).grid(row=0, column=2, padx=8, pady=8)

        wizard = ttk.LabelFrame(self, text=" Questions ")
        wizard.pack(fill="x", padx=12, pady=5)
        self.progress = ttk.Label(wizard, text="", style="Muted.TLabel")
        self.progress.pack(anchor="w", padx=10, pady=(8, 2))
        self.question = ttk.Label(wizard, text="", font=("Segoe UI", 12, "bold"), wraplength=1000, justify="left")
        self.question.pack(anchor="w", padx=10, pady=6)
        self.answer = ttk.Combobox(wizard, state="readonly", width=58)
        self.answer.pack(anchor="w", padx=10, pady=(0, 8))
        buttons = ttk.Frame(wizard)
        buttons.pack(fill="x", padx=8, pady=(0, 8))
        self.back_button = ttk.Button(buttons, text="Précédent", command=self.previous)
        self.back_button.pack(side="left", padx=3)
        self.next_button = ttk.Button(buttons, text="Suivant", command=self.next, style="Accent.TButton")
        self.next_button.pack(side="right", padx=3)

        result = ttk.LabelFrame(self, text=" Hypothèses et actions prudentes ")
        result.pack(fill="both", expand=True, padx=12, pady=(5, 12))
        self.output = tk.Text(result, wrap="word", state="disabled", padx=10, pady=10)
        self.output.pack(fill="both", expand=True, padx=5, pady=5)

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

    def restart(self) -> None:
        self.answers.clear()
        self.step = 0
        self._set_output(
            "Répondez aux six questions. Le résultat classera plusieurs causes plausibles ; il ne confirmera pas une maladie."
        )
        self._show_step()

    def _show_step(self) -> None:
        key, label, options = self.QUESTIONS[self.step]
        self.progress.configure(text=f"Étape {self.step + 1} sur {len(self.QUESTIONS)}")
        self.question.configure(text=label)
        self.answer["values"] = options
        self.answer.set(self.answers.get(key, options[0]))
        self.back_button.configure(state="normal" if self.step else "disabled")
        self.next_button.configure(text="Analyser" if self.step == len(self.QUESTIONS) - 1 else "Suivant")

    def _store_current(self) -> None:
        key = self.QUESTIONS[self.step][0]
        self.answers[key] = self.answer.get()

    def previous(self) -> None:
        self._store_current()
        if self.step:
            self.step -= 1
            self._show_step()

    def next(self) -> None:
        self._store_current()
        if self.step < len(self.QUESTIONS) - 1:
            self.step += 1
            self._show_step()
            return
        self.analyse()

    def analyse(self) -> None:
        answers = DiagnosticAnswers(**{key: self.answers[key] for key, _label, _options in self.QUESTIONS})
        plant = self.plant_mapping.get(self.combo_plant.get())
        hypotheses = diagnose(answers, plant)
        lines = [
            "DIAGNOSTIC D'ORIENTATION",
            "=" * 72,
            "",
            "Ces hypothèses sont classées à partir de vos réponses et du contexte enregistré. Elles ne remplacent pas l'examen de la plante.",
            "",
        ]
        if plant:
            context = plant.get("contexte") if isinstance(plant.get("contexte"), dict) else {}
            lines.extend(
                [
                    f"Plante : {plant.get('surnom', 'Sans nom')}",
                    f"Contexte : {context.get('emplacement', 'non renseigné')}, exposition {context.get('exposition', 'non renseignée')}, pot {plant.get('pot_l', '?')} L.",
                    "",
                ]
            )
        for rank, hypothesis in enumerate(hypotheses, start=1):
            lines.append(f"{rank}. {hypothesis.title} — score indicatif {hypothesis.score}")
            lines.append(f"   Indices : {hypothesis.explanation}")
            lines.append("   Actions :")
            lines.extend(f"   • {action}" for action in hypothesis.actions)
            lines.append("")
        if not hypotheses:
            lines.append("Aucune hypothèse ne ressort nettement. Vérifiez d'abord l'humidité, les racines, la lumière et les ravageurs.")
        lines.extend(
            [
                "IMPORTANT",
                "Isolez la plante si l'atteinte progresse rapidement ou semble contagieuse. Pour une espèce rare, toxique, comestible ou fortement atteinte, demandez un avis professionnel avant traitement.",
            ]
        )
        self._set_output("\n".join(lines))

    def _set_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", tk.END)
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

"""Aligne l'onglet Collection sur le parcours de contrôle d'humidité d'Aujourd'hui."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from core import ValidationError, format_date_fr

from assistant_botanique.domain.soil_moisture import SOIL_DRY, SOIL_MOIST, SOIL_WET, watering_decision
from assistant_botanique.features.watering_workflow import _record_check_moisture, _set_water_button
from assistant_botanique.services.collection_watering import (
    collection_watering_schedule,
    next_due_collection_identifier,
)
from assistant_botanique.services.soil_moisture import latest_soil_moisture, record_validated_watering


def _walk_widgets(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from _walk_widgets(child)


def install_collection_watering_consistency() -> None:
    """Installe le même contrôle Sec/Humide/Trempé dans l'onglet Collection."""
    from tab_gestion import TabGestion

    if getattr(TabGestion, "_collection_watering_consistency_installed", False):
        return

    previous_init = TabGestion.__init__
    previous_refresh = TabGestion.rafraichir_tableau_collection
    previous_details = TabGestion.afficher_details_plante

    def schedules_for_collection(self) -> dict[str, Any]:
        schedules: dict[str, Any] = {}
        for plant_id in self.tree.get_children(""):
            plant = self.find_instance(str(plant_id))
            if not plant:
                continue
            profile = self.resolve_profile(plant.get("species_id", ""))
            if profile is None:
                continue
            try:
                schedules[str(plant_id)] = collection_watering_schedule(
                    self.repository.database,
                    plant,
                    profile,
                )
            except ValidationError:
                continue
        return schedules

    def enhanced_init(self, *args: Any, **kwargs: Any) -> None:
        previous_init(self, *args, **kwargs)

        legacy_button = None
        actions = None
        first_following_button = None
        for widget in _walk_widgets(self):
            if not isinstance(widget, ttk.Button):
                continue
            text = str(widget.cget("text"))
            if text == "💧 Enregistrer un arrosage":
                legacy_button = widget
                actions = widget.master
            elif text == "📝 Ajouter un soin":
                first_following_button = widget
        if legacy_button is None or actions is None:
            return
        legacy_button.pack_forget()

        self.collection_soil_moisture_var = tk.StringVar(value="")
        self.collection_soil_moisture_buttons: list[ttk.Radiobutton] = []
        pack_options: dict[str, Any] = {"side": "left", "padx": 3}
        if first_following_button is not None:
            pack_options["before"] = first_following_button

        ttk.Label(actions, text="Humidité :").pack(**pack_options)
        for state, label in (
            (SOIL_DRY, "Sec"),
            (SOIL_MOIST, "Humide"),
            (SOIL_WET, "Trempé"),
        ):
            button = ttk.Radiobutton(
                actions,
                text=label,
                value=state,
                variable=self.collection_soil_moisture_var,
                command=self.record_collection_soil_moisture,
            )
            button.pack(**pack_options)
            self.collection_soil_moisture_buttons.append(button)

        self.collection_water_button = tk.Button(
            actions,
            text="Arrosé",
            command=self.record_collection_validated_watering,
            bg="#3f3f46",
            fg="white",
            activebackground="#3f3f46",
            activeforeground="white",
            disabledforeground="#d4d4d8",
            relief="raised",
            borderwidth=1,
            padx=14,
            pady=5,
            state="disabled",
        )
        self.collection_water_button.pack(**pack_options)

        self.collection_watering_hint_var = tk.StringVar(
            value="Sélectionnez une plante puis indiquez l'état de son substrat."
        )
        self.collection_watering_hint_label = ttk.Label(
            self,
            textvariable=self.collection_watering_hint_var,
            wraplength=1120,
            justify="left",
        )
        self.collection_watering_hint_label.pack(
            fill="x",
            padx=12,
            pady=(0, 4),
            after=actions,
        )
        self.tree.bind("<<TreeviewSelect>>", self.update_collection_watering_controls, add="+")
        self.rafraichir_tableau_collection()

    def refresh_collection(self, select_id: str | None = None) -> None:
        previous_refresh(self, select_id=select_id)
        schedules = schedules_for_collection(self)
        for plant_id, schedule in schedules.items():
            if not self.tree.exists(plant_id):
                continue
            self.tree.set(plant_id, "next", format_date_fr(schedule.due_date) if schedule.due_date else "Repos")
            self.tree.set(plant_id, "status", schedule.short_label)
            self.tree.item(plant_id, tags=(schedule.code,))
        if hasattr(self, "collection_soil_moisture_var"):
            self.update_collection_watering_controls()

    def show_details(self, event=None) -> None:
        previous_details(self, event)
        selected = self.tree.selection()
        if len(selected) != 1:
            return
        plant = self.find_instance(str(selected[0]))
        if not plant:
            return
        profile = self.resolve_profile(plant.get("species_id", ""))
        if profile is None:
            return
        try:
            schedule = collection_watering_schedule(self.repository.database, plant, profile)
        except ValidationError:
            return

        text = self.txt_details.get("1.0", "end-1c")
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if line.startswith("Rappel :"):
                lines[index] = f"Rappel : {schedule.detail}"
                break
        self.txt_details.configure(state="normal")
        self.txt_details.delete("1.0", tk.END)
        self.txt_details.insert("1.0", "\n".join(lines))
        self.txt_details.configure(state="disabled")

    def update_controls(self, _event=None) -> None:
        radios = getattr(self, "collection_soil_moisture_buttons", [])
        water_button = getattr(self, "collection_water_button", None)
        hint = getattr(self, "collection_watering_hint_var", None)
        variable = getattr(self, "collection_soil_moisture_var", None)
        if water_button is None or hint is None or variable is None:
            return

        selected = self.tree.selection()
        enabled = len(selected) == 1
        for radio in radios:
            radio.configure(state="normal" if enabled else "disabled")
        if not enabled:
            variable.set("")
            _set_water_button(water_button, "disabled")
            hint.set("Sélectionnez exactement une plante puis indiquez l'état de son substrat.")
            return

        plant_id = str(selected[0])
        plant = self.find_instance(plant_id)
        profile = self.resolve_profile(plant.get("species_id", "")) if plant else None
        if plant is None or profile is None:
            variable.set("")
            _set_water_button(water_button, "disabled")
            hint.set("Fiche botanique introuvable : l'arrosage assisté est désactivé.")
            return

        snapshot = latest_soil_moisture(self.repository.database, plant_id)
        variable.set(snapshot.state or "")
        if snapshot.watered:
            _set_water_button(water_button, "done")
            hint.set("Arrosage validé après le dernier contrôle.")
            return
        decision = watering_decision(profile, snapshot.state)
        _set_water_button(water_button, "ready" if decision.can_water else "disabled")
        hint.set(decision.reason)

    def reload_model(self) -> None:
        self.mes_plantes = self.repository.load()
        if self.on_collection_changed_callback:
            self.on_collection_changed_callback(self.mes_plantes)

    def advance(self, completed_plant_id: str) -> None:
        schedules = schedules_for_collection(self)
        next_identifier = next_due_collection_identifier(
            schedules,
            self.tree.get_children(""),
            completed_plant_id,
        )
        selected = self.tree.selection()
        if selected:
            self.tree.selection_remove(*selected)
        if next_identifier and self.tree.exists(next_identifier):
            self.tree.selection_set(next_identifier)
            self.tree.focus(next_identifier)
            self.tree.see(next_identifier)
            self.afficher_details_plante()
            self.update_collection_watering_controls()
            return
        self.afficher_details_plante()
        self.update_collection_watering_controls()
        self.collection_watering_hint_var.set(
            "Aucun autre contrôle d'humidité arrivé à échéance dans la collection."
        )

    def record_moisture(self) -> None:
        selected = self.tree.selection()
        if len(selected) != 1:
            return
        plant_id = str(selected[0])
        plant = self.find_instance(plant_id)
        profile = self.resolve_profile(plant.get("species_id", "")) if plant else None
        if plant is None or profile is None:
            messagebox.showerror("Humidité du substrat", "Fiche botanique ou plante introuvable.", parent=self)
            return
        try:
            _snapshot, deferred = _record_check_moisture(
                self.repository.database,
                plant_id,
                profile,
                plant,
                self.collection_soil_moisture_var.get(),
            )
        except (ValidationError, OSError) as exc:
            messagebox.showerror("Humidité du substrat", str(exc), parent=self)
            return

        reload_model(self)
        if deferred is not None:
            self.rafraichir_tableau_collection()
            self.advance_collection_watering(plant_id)
        else:
            self.rafraichir_tableau_collection(select_id=plant_id)

    def record_watering(self) -> None:
        selected = self.tree.selection()
        if len(selected) != 1:
            return
        plant_id = str(selected[0])
        plant = self.find_instance(plant_id)
        profile = self.resolve_profile(plant.get("species_id", "")) if plant else None
        if plant is None or profile is None:
            messagebox.showerror("Arrosage", "Fiche botanique introuvable.", parent=self)
            return
        try:
            record_validated_watering(self.repository.database, plant_id, profile)
        except (ValidationError, OSError) as exc:
            messagebox.showwarning("Arrosage", str(exc), parent=self)
            self.update_collection_watering_controls()
            return

        reload_model(self)
        self.rafraichir_tableau_collection()
        self.advance_collection_watering(plant_id)

    TabGestion.__init__ = enhanced_init
    TabGestion.rafraichir_tableau_collection = refresh_collection
    TabGestion.afficher_details_plante = show_details
    TabGestion.update_collection_watering_controls = update_controls
    TabGestion.advance_collection_watering = advance
    TabGestion.record_collection_soil_moisture = record_moisture
    TabGestion.record_collection_validated_watering = record_watering
    TabGestion._collection_watering_consistency_installed = True


__all__ = ["install_collection_watering_consistency"]

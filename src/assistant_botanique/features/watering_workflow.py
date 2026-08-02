"""Intégration du contrôle d'humidité dans les onglets Aujourd'hui et Collection."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Mapping

from core import ValidationError

from assistant_botanique.domain.soil_moisture import (
    SOIL_DRY,
    SOIL_MOIST,
    SOIL_STATES,
    SOIL_WET,
    watering_decision,
)
from assistant_botanique.services.soil_moisture import (
    latest_soil_moisture,
    record_soil_moisture,
    record_validated_watering,
    soil_moisture_by_plant,
)

_BUTTON_GRAY = "#3f3f46"
_BUTTON_BLUE = "#1565c0"
_BUTTON_BLUE_ACTIVE = "#0d47a1"
_BUTTON_GREEN = "#2e7d32"
_BUTTON_GREEN_ACTIVE = "#1b5e20"


def _walk_widgets(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from _walk_widgets(child)


def _profile_for_plant(
    profiles_by_id: Mapping[str, Mapping[str, Any]],
    plants_by_id: Mapping[str, Mapping[str, Any]],
    plant_id: str | None,
) -> Mapping[str, Any] | None:
    if not plant_id:
        return None
    plant = plants_by_id.get(plant_id)
    if not plant:
        return None
    return profiles_by_id.get(str(plant.get("species_id") or ""))


def _set_water_button(button: tk.Button, mode: str) -> None:
    if mode == "ready":
        button.configure(
            text="Arrosé",
            state="normal",
            bg=_BUTTON_BLUE,
            fg="white",
            activebackground=_BUTTON_BLUE_ACTIVE,
            activeforeground="white",
            disabledforeground="white",
        )
    elif mode == "done":
        button.configure(
            text="Arrosé ✓",
            state="disabled",
            bg=_BUTTON_GREEN,
            fg="white",
            activebackground=_BUTTON_GREEN_ACTIVE,
            activeforeground="white",
            disabledforeground="white",
        )
    else:
        button.configure(
            text="Arrosé",
            state="disabled",
            bg=_BUTTON_GRAY,
            fg="white",
            activebackground=_BUTTON_GRAY,
            activeforeground="white",
            disabledforeground="#d4d4d8",
        )


def _patch_today_dashboard() -> None:
    from assistant_botanique.ui.productivity_tabs import TodayDashboardTab

    if getattr(TodayDashboardTab, "_soil_moisture_workflow_installed", False):
        return

    original_build = TodayDashboardTab._build_ui
    original_refresh = TodayDashboardTab.refresh

    def build_ui(self) -> None:
        original_build(self)
        columns = tuple(self.tree["columns"])
        if "moisture" not in columns:
            self.tree.configure(columns=("date", "plant", "care", "status", "moisture", "details"))
            self.tree.heading("moisture", text="Humidité du substrat")
            self.tree.column("moisture", width=145, anchor="center")
            self.tree.column("details", width=380, anchor="w")

        hidden_labels = {"Substrat sec", "Encore humide", "Arrosé"}
        hidden_buttons: list[ttk.Button] = []
        first_following_button: ttk.Button | None = None
        actions = None
        for widget in _walk_widgets(self):
            if not isinstance(widget, ttk.Button):
                continue
            text = str(widget.cget("text"))
            if text in hidden_labels:
                hidden_buttons.append(widget)
                actions = widget.master
            elif text == "Fertilisé":
                first_following_button = widget
        for button in hidden_buttons:
            button.pack_forget()
        if actions is None:
            return

        self.soil_moisture_var = tk.StringVar(value="")
        self.soil_moisture_buttons: list[ttk.Radiobutton] = []
        pack_options: dict[str, Any] = {"side": "left", "padx": 3}
        if first_following_button is not None:
            pack_options["before"] = first_following_button
        ttk.Label(actions, text="Humidité du substrat :").pack(**pack_options)
        for state, label in (
            (SOIL_DRY, "Sec"),
            (SOIL_MOIST, "Humide"),
            (SOIL_WET, "Trempé"),
        ):
            button = ttk.Radiobutton(
                actions,
                text=label,
                value=state,
                variable=self.soil_moisture_var,
                command=self.record_soil_moisture,
            )
            button.pack(**pack_options)
            self.soil_moisture_buttons.append(button)

        self.water_button = tk.Button(
            actions,
            text="Arrosé",
            command=self.record_validated_watering,
            bg=_BUTTON_GRAY,
            fg="white",
            activebackground=_BUTTON_GRAY,
            activeforeground="white",
            disabledforeground="#d4d4d8",
            relief="raised",
            borderwidth=1,
            padx=14,
            pady=5,
            state="disabled",
        )
        self.water_button.pack(**pack_options)
        self.watering_hint_var = tk.StringVar(
            value="Sélectionnez une plante puis indiquez l'état de son substrat."
        )
        self.watering_hint_label = ttk.Label(
            self,
            textvariable=self.watering_hint_var,
            wraplength=1120,
            justify="left",
        )
        self.watering_hint_label.pack(
            fill="x",
            padx=16,
            pady=(0, 8),
            after=actions,
        )
        self.tree.bind("<<TreeviewSelect>>", self.update_watering_controls, add="+")

    def refresh(self) -> None:
        original_refresh(self)
        plants = self.database.load_plants()
        self._watering_plants_by_id = {str(plant["id"]): plant for plant in plants}
        states = soil_moisture_by_plant(self.database)
        for identifier in self.tree.get_children(""):
            values = list(self.tree.item(identifier, "values"))
            if len(values) < 5:
                continue
            item = self.items.get(identifier)
            moisture = states.get(item.plant_id) if item else None
            details = values[4]
            self.tree.item(
                identifier,
                values=(values[0], values[1], values[2], values[3], moisture.label if moisture else "Non indiqué", details),
            )
        self.update_watering_controls()

    def update_controls(self, _event=None) -> None:
        plant_id = self.selected_plant_id()
        enabled = bool(plant_id)
        for radio in getattr(self, "soil_moisture_buttons", []):
            radio.configure(state="normal" if enabled else "disabled")
        if not plant_id:
            self.soil_moisture_var.set("")
            _set_water_button(self.water_button, "disabled")
            self.watering_hint_var.set("Sélectionnez une plante puis indiquez l'état de son substrat.")
            return

        snapshot = latest_soil_moisture(self.database, plant_id)
        self.soil_moisture_var.set(snapshot.state or "")
        profile = _profile_for_plant(
            self.profiles_by_id,
            getattr(self, "_watering_plants_by_id", {}),
            plant_id,
        )
        if profile is None:
            _set_water_button(self.water_button, "disabled")
            self.watering_hint_var.set("Fiche botanique introuvable : l'arrosage assisté est désactivé.")
            return
        if snapshot.watered:
            _set_water_button(self.water_button, "done")
            self.watering_hint_var.set(
                "Arrosage validé après le dernier contrôle. Le substrat est maintenant indiqué comme trempé."
            )
            return
        decision = watering_decision(profile, snapshot.state)
        _set_water_button(self.water_button, "ready" if decision.can_water else "disabled")
        self.watering_hint_var.set(decision.reason)

    def record_moisture(self) -> None:
        plant_id = self.selected_plant_id()
        if not plant_id:
            return
        profile = _profile_for_plant(
            self.profiles_by_id,
            getattr(self, "_watering_plants_by_id", {}),
            plant_id,
        )
        if profile is None:
            messagebox.showerror("Humidité du substrat", "Fiche botanique introuvable.", parent=self)
            return
        try:
            record_soil_moisture(self.database, plant_id, self.soil_moisture_var.get(), profile)
        except (ValidationError, OSError) as exc:
            messagebox.showerror("Humidité du substrat", str(exc), parent=self)
            return
        if self.on_collection_refresh:
            self.on_collection_refresh()
        else:
            self.refresh()

    def record_watering(self) -> None:
        plant_id = self.selected_plant_id()
        if not plant_id:
            return
        profile = _profile_for_plant(
            self.profiles_by_id,
            getattr(self, "_watering_plants_by_id", {}),
            plant_id,
        )
        if profile is None:
            messagebox.showerror("Arrosage", "Fiche botanique introuvable.", parent=self)
            return
        try:
            record_validated_watering(self.database, plant_id, profile)
        except (ValidationError, OSError) as exc:
            messagebox.showwarning("Arrosage", str(exc), parent=self)
            self.update_watering_controls()
            return
        if self.on_collection_refresh:
            self.on_collection_refresh()
        else:
            self.refresh()

    TodayDashboardTab._build_ui = build_ui
    TodayDashboardTab.refresh = refresh
    TodayDashboardTab.update_watering_controls = update_controls
    TodayDashboardTab.record_soil_moisture = record_moisture
    TodayDashboardTab.record_validated_watering = record_watering
    TodayDashboardTab._soil_moisture_workflow_installed = True


def _patch_collection_column() -> None:
    from tab_gestion import TabGestion

    if getattr(TabGestion, "_soil_moisture_column_installed", False):
        return

    previous_init = TabGestion.__init__
    previous_refresh = TabGestion.rafraichir_tableau_collection
    previous_details = TabGestion.afficher_details_plante

    def enhanced_init(self, *args: Any, **kwargs: Any) -> None:
        previous_init(self, *args, **kwargs)
        columns = tuple(self.tree["columns"])
        if "moisture" not in columns:
            self.tree.configure(columns=(*columns, "moisture"))
            self.tree.heading(
                "moisture",
                text="Humidité du substrat",
                command=lambda: self.sort_tree("moisture", False),
            )
            self.tree.column("moisture", width=145, anchor="center")
        self.rafraichir_tableau_collection()

    def refresh_collection(self, select_id: str | None = None) -> None:
        previous_refresh(self, select_id=select_id)
        states = soil_moisture_by_plant(self.repository.database)
        for plant_id in self.tree.get_children(""):
            snapshot = states.get(str(plant_id))
            self.tree.set(plant_id, "moisture", snapshot.label if snapshot else "Non indiqué")

    def show_details(self, event=None) -> None:
        previous_details(self, event)
        selected = self.tree.selection()
        if len(selected) != 1:
            return
        snapshot = latest_soil_moisture(self.repository.database, str(selected[0]))
        self.txt_details.configure(state="normal")
        self.txt_details.insert("end", f"\n\nHumidité du substrat : {snapshot.label}")
        if snapshot.watered:
            self.txt_details.insert("end", " — arrosage validé après le dernier contrôle")
        self.txt_details.configure(state="disabled")

    TabGestion.__init__ = enhanced_init
    TabGestion.rafraichir_tableau_collection = refresh_collection
    TabGestion.afficher_details_plante = show_details
    TabGestion._soil_moisture_column_installed = True


def install_watering_workflow() -> None:
    """Installe le parcours d'observation puis d'arrosage."""
    _patch_today_dashboard()
    _patch_collection_column()


__all__ = ["install_watering_workflow"]

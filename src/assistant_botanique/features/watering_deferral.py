"""Bouton de report du contrôle lorsque l'arrosage n'est pas nécessaire."""
from __future__ import annotations

from datetime import date
from tkinter import messagebox, ttk

from core import ValidationError, format_date_fr

from assistant_botanique.domain.soil_moisture import watering_decision
from assistant_botanique.services.soil_moisture import latest_soil_moisture
from assistant_botanique.services.watering_deferral import (
    latest_deferred_watering_check,
    record_deferred_watering_check,
)


def install_watering_deferral() -> None:
    from assistant_botanique.ui.productivity_tabs import TodayDashboardTab

    if getattr(TodayDashboardTab, "_watering_deferral_installed", False):
        return

    previous_build = TodayDashboardTab._build_ui
    previous_update = TodayDashboardTab.update_watering_controls

    def build_ui(self) -> None:
        previous_build(self)
        water_button = getattr(self, "water_button", None)
        if water_button is None:
            return
        self.defer_watering_button = ttk.Button(
            water_button.master,
            text="Reporter le contrôle",
            command=self.defer_watering_check,
            state="disabled",
        )
        self.defer_watering_button.pack(side="left", padx=3, after=water_button)

    def update_controls(self, _event=None) -> None:
        previous_update(self, _event)
        button = getattr(self, "defer_watering_button", None)
        if button is None:
            return
        button.configure(text="Reporter le contrôle", state="disabled")

        item = self._selected_item()
        plant_id = self.selected_plant_id()
        if item is None or item.kind != "check" or not plant_id:
            return
        plant = getattr(self, "_watering_plants_by_id", {}).get(plant_id)
        if not plant:
            return
        profile = self.profiles_by_id.get(str(plant.get("species_id") or ""))
        if profile is None:
            return

        snapshot = latest_soil_moisture(self.database, plant_id)
        if snapshot.state is None or snapshot.watered:
            return
        deferred = latest_deferred_watering_check(self.database, plant_id)
        if deferred is not None and deferred.due_date > date.today():
            button.configure(text=f"Reporté au {format_date_fr(deferred.due_date)}", state="disabled")
            return
        decision = watering_decision(profile, snapshot.state)
        if not decision.can_water:
            button.configure(state="normal")

    def defer_check(self) -> None:
        item = self._selected_item()
        plant_id = self.selected_plant_id()
        if item is None or item.kind != "check" or not plant_id:
            messagebox.showwarning(
                "Reporter le contrôle",
                "Sélectionnez un contrôle d'humidité de plante.",
                parent=self,
            )
            return
        plant = getattr(self, "_watering_plants_by_id", {}).get(plant_id)
        if not plant:
            messagebox.showerror("Reporter le contrôle", "Plante introuvable.", parent=self)
            return
        profile = self.profiles_by_id.get(str(plant.get("species_id") or ""))
        if profile is None:
            messagebox.showerror("Reporter le contrôle", "Fiche botanique introuvable.", parent=self)
            return
        snapshot = latest_soil_moisture(self.database, plant_id)
        try:
            deferred = record_deferred_watering_check(
                self.database,
                plant_id,
                profile,
                plant,
                snapshot.state,
            )
        except (ValidationError, OSError) as exc:
            messagebox.showwarning("Reporter le contrôle", str(exc), parent=self)
            self.update_watering_controls()
            return

        messagebox.showinfo(
            "Contrôle reporté",
            (
                "Aucun arrosage n'a été enregistré.\n\n"
                f"Le prochain contrôle de cette plante est prévu le {format_date_fr(deferred.due_date)}."
            ),
            parent=self,
        )
        if self.on_collection_refresh:
            self.on_collection_refresh()
        else:
            self.refresh()
        advance = getattr(self, "advance_after_watering_check", None)
        if callable(advance):
            advance(plant_id)

    TodayDashboardTab._build_ui = build_ui
    TodayDashboardTab.update_watering_controls = update_controls
    TodayDashboardTab.defer_watering_check = defer_check
    TodayDashboardTab._watering_deferral_installed = True


__all__ = ["install_watering_deferral"]

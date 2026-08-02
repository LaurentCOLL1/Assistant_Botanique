"""Ajoute le nom scientifique aux lignes de l'onglet Aujourd'hui."""
from __future__ import annotations

from typing import Any, Mapping

from core import format_date_fr

from assistant_botanique.services.soil_moisture import soil_moisture_by_plant

TODAY_COLUMN_KEYS = (
    "date",
    "plant",
    "scientific",
    "care",
    "status",
    "moisture",
    "details",
)


def scientific_name_for_profile(profile: Mapping[str, Any] | None) -> str:
    """Retourne le nom scientifique d'une fiche, avec un libellé explicite en repli."""
    taxonomy = profile.get("taxonomie") if profile else None
    if not isinstance(taxonomy, Mapping):
        return "Non renseigné"
    name = str(taxonomy.get("nom_scientifique") or "").strip()
    return name or "Non renseigné"


def today_row_values(item: Any, profile: Mapping[str, Any] | None, moisture_label: str) -> tuple[str, ...]:
    """Construit une ligne dans l'ordre canonique des colonnes Aujourd'hui."""
    return (
        format_date_fr(item.due_date),
        item.plant_name,
        scientific_name_for_profile(profile),
        item.label,
        item.status,
        moisture_label,
        item.details,
    )


def install_today_scientific_column() -> None:
    """Insère et alimente la colonne entre Plante et Soin / contrôle."""
    from assistant_botanique.ui.productivity_tabs import TodayDashboardTab

    if getattr(TodayDashboardTab, "_scientific_name_column_installed", False):
        return

    previous_build = TodayDashboardTab._build_ui
    previous_refresh = TodayDashboardTab.refresh

    def build_ui(self) -> None:
        previous_build(self)
        self.tree.configure(columns=TODAY_COLUMN_KEYS)
        self.tree.heading("scientific", text="Nom scientifique")
        self.tree.column("scientific", width=190, anchor="w")

    def refresh(self) -> None:
        previous_refresh(self)
        plants_by_id = {str(plant["id"]): plant for plant in self.database.load_plants()}
        moisture_by_plant = soil_moisture_by_plant(self.database)

        for identifier in self.tree.get_children(""):
            item = self.items.get(identifier)
            if item is None:
                continue
            plant = plants_by_id.get(item.plant_id)
            profile = None
            if plant is not None:
                profile = self.profiles_by_id.get(str(plant.get("species_id") or ""))
            moisture = moisture_by_plant.get(item.plant_id)
            values = today_row_values(
                item,
                profile,
                moisture.label if moisture else "Non indiqué",
            )
            self.tree.item(identifier, values=values)

    TodayDashboardTab._build_ui = build_ui
    TodayDashboardTab.refresh = refresh
    TodayDashboardTab._scientific_name_column_installed = True


__all__ = [
    "TODAY_COLUMN_KEYS",
    "install_today_scientific_column",
    "scientific_name_for_profile",
    "today_row_values",
]

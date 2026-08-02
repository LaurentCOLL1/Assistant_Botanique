"""Garanties d'initialisation et textes du nouveau parcours d'arrosage."""
from __future__ import annotations

from tkinter import messagebox, ttk


def _walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from _walk(child)


def install_watering_initialization_guard() -> None:
    from assistant_botanique.ui.productivity_tabs import TodayDashboardTab
    from tab_gestion import TabGestion

    if not getattr(TabGestion, "_soil_moisture_initialization_guard", False):
        previous_refresh = TabGestion.rafraichir_tableau_collection

        def guarded_refresh(self, *args, **kwargs):
            tree = getattr(self, "tree", None)
            if tree is not None:
                columns = tuple(tree["columns"])
                if "moisture" not in columns:
                    tree.configure(columns=(*columns, "moisture"))
                    tree.heading(
                        "moisture",
                        text="Humidité du substrat",
                        command=lambda: self.sort_tree("moisture", False),
                    )
                    tree.column("moisture", width=145, anchor="center")
            return previous_refresh(self, *args, **kwargs)

        TabGestion.rafraichir_tableau_collection = guarded_refresh
        TabGestion._soil_moisture_initialization_guard = True

    if getattr(TodayDashboardTab, "_soil_moisture_texts_installed", False):
        return
    previous_build = TodayDashboardTab._build_ui
    previous_complete = TodayDashboardTab.complete_selected

    def build_ui(self) -> None:
        previous_build(self)
        for widget in _walk(self):
            if not isinstance(widget, ttk.Label):
                continue
            text = str(widget.cget("text"))
            if text.startswith("Les contrôles d'humidité sont proposés"):
                widget.configure(
                    text=(
                        "Le calendrier indique quand contrôler une plante. Sélectionnez ensuite l'état réel du "
                        "substrat : sec, humide ou trempé. Le bouton Arrosé ne s'active que lorsque la fiche "
                        "botanique et l'observation indiquent qu'un arrosage est nécessaire."
                    )
                )
                break

    def complete_selected(self) -> None:
        item = self._selected_item()
        if item and item.kind != "task":
            messagebox.showinfo(
                "Contrôle d'humidité",
                "Indiquez d'abord si le substrat est sec, humide ou trempé. "
                "Le bouton Arrosé s'activera seulement si l'espèce doit être arrosée dans cet état.",
                parent=self,
            )
            return
        previous_complete(self)

    TodayDashboardTab._build_ui = build_ui
    TodayDashboardTab.complete_selected = complete_selected
    TodayDashboardTab._soil_moisture_texts_installed = True


__all__ = ["install_watering_initialization_guard"]

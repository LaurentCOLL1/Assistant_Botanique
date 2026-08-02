"""Garantie d'initialisation de la colonne d'humidité avant le premier chargement."""
from __future__ import annotations


def install_watering_initialization_guard() -> None:
    from tab_gestion import TabGestion

    if getattr(TabGestion, "_soil_moisture_initialization_guard", False):
        return
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


__all__ = ["install_watering_initialization_guard"]

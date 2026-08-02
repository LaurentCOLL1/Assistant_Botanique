"""Restaure les colonnes complètes après les extensions dynamiques de Treeview."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    key: str
    label: str
    width: int
    anchor: str = "w"


TODAY_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("date", "Date", 100),
    ColumnSpec("plant", "Plante", 180),
    ColumnSpec("care", "Soin / contrôle", 180),
    ColumnSpec("status", "État", 130),
    ColumnSpec("moisture", "Humidité du substrat", 145, "center"),
    ColumnSpec("details", "Détails", 380),
)

COLLECTION_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("nickname", "Surnom", 150),
    ColumnSpec("scientific", "Nom scientifique", 190),
    ColumnSpec("family", "Famille", 130),
    ColumnSpec("pot", "Pot (L)", 65, "center"),
    ColumnSpec("last", "Dernier arrosage", 105, "center"),
    ColumnSpec("next", "Prochain contrôle", 110, "center"),
    ColumnSpec("status", "Statut", 180),
    ColumnSpec("moisture", "Humidité du substrat", 145, "center"),
)


def configure_columns(
    tree: Any,
    specs: Iterable[ColumnSpec],
    *,
    sort_callback: Callable[[str, bool], None] | None = None,
) -> None:
    """Configure la liste, les titres et les dimensions sans laisser de titre vide."""
    column_specs = tuple(specs)
    desired = tuple(spec.key for spec in column_specs)
    current = tuple(str(column) for column in tree["columns"])
    if current != desired:
        tree.configure(columns=desired)

    for spec in column_specs:
        heading_options: dict[str, Any] = {"text": spec.label}
        if sort_callback is not None:
            heading_options["command"] = lambda key=spec.key: sort_callback(key, False)
        tree.heading(spec.key, **heading_options)
        tree.column(spec.key, width=spec.width, anchor=spec.anchor)


def configure_today_columns(tree: Any) -> None:
    configure_columns(tree, TODAY_COLUMNS)


def configure_collection_columns(
    tree: Any,
    sort_callback: Callable[[str, bool], None],
) -> None:
    configure_columns(tree, COLLECTION_COLUMNS, sort_callback=sort_callback)


def install_treeview_header_fixes() -> None:
    """Réapplique les en-têtes après toutes les autres extensions d'interface."""
    from assistant_botanique.ui.productivity_tabs import TodayDashboardTab
    from tab_gestion import TabGestion

    if not getattr(TodayDashboardTab, "_complete_column_headers_installed", False):
        previous_build = TodayDashboardTab._build_ui

        def build_ui(self) -> None:
            previous_build(self)
            configure_today_columns(self.tree)

        TodayDashboardTab._build_ui = build_ui
        TodayDashboardTab._complete_column_headers_installed = True

    if not getattr(TabGestion, "_complete_column_headers_installed", False):
        previous_refresh = TabGestion.rafraichir_tableau_collection

        def refresh_collection(self, *args, **kwargs):
            result = previous_refresh(self, *args, **kwargs)
            tree = getattr(self, "tree", None)
            if tree is not None:
                configure_collection_columns(tree, self.sort_tree)
            return result

        TabGestion.rafraichir_tableau_collection = refresh_collection
        TabGestion._complete_column_headers_installed = True


__all__ = [
    "COLLECTION_COLUMNS",
    "TODAY_COLUMNS",
    "ColumnSpec",
    "configure_collection_columns",
    "configure_columns",
    "configure_today_columns",
    "install_treeview_header_fixes",
]

"""Définition testable des onglets visibles selon le niveau d'interface."""
from __future__ import annotations

SIMPLE_TABS = (
    "today",
    "collection",
    "search",
    "calendar",
    "photos",
    "catalogue",
    "maintenance",
)

ADVANCED_TABS = (
    "today",
    "collection",
    "editor",
    "search",
    "calendar",
    "adaptive",
    "photos",
    "catalogue",
    "review",
    "substrate",
    "diagnostic",
    "ecosystem",
    "maintenance",
)


def normalized_ui_mode(value: object) -> str:
    return "simple" if str(value or "").strip().casefold() == "simple" else "advanced"


def visible_tab_keys(mode: object) -> tuple[str, ...]:
    return SIMPLE_TABS if normalized_ui_mode(mode) == "simple" else ADVANCED_TABS

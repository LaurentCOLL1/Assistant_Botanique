"""Correctifs de raccordement appliqués après l'intégration des fonctions."""
from __future__ import annotations


def install_runtime_fixes() -> None:
    """Corrige les liaisons Tkinter et évite de créer une fenêtre d'accueil inutile."""
    from assistant_botanique.features import integration
    from assistant_botanique.ui.advanced_ecosystem_tab import AdvancedEcosystemTab

    if getattr(AdvancedEcosystemTab, "_productivity_runtime_fixes_installed", False):
        return

    current_build = AdvancedEcosystemTab._build_inventory_tab

    def build_inventory_with_safe_binding(self) -> None:
        current_build(self)
        combo = getattr(self, "inventory_category_combo", None)
        if combo is not None and hasattr(self, "_refresh_inventory_subcategories"):
            combo.bind(
                "<<ComboboxSelected>>",
                lambda _event: self._refresh_inventory_subcategories(),
            )

    AdvancedEcosystemTab._build_inventory_tab = build_inventory_with_safe_binding
    AdvancedEcosystemTab._productivity_runtime_fixes_installed = True

    original_wizard = integration.FirstRunWizard

    def guarded_wizard(app, *, force: bool = False):
        if not force and app.settings.get("onboarding", {}).get("completed"):
            return None
        return original_wizard(app, force=force)

    integration.FirstRunWizard = guarded_wizard

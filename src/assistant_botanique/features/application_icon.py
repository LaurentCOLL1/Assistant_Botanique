"""Installe l'icône officielle sur la fenêtre principale."""
from __future__ import annotations

from assistant_botanique.ui.app_icon import apply_app_icon


def install_application_icon() -> None:
    """Applique l'icône avant la construction des widgets de la fenêtre."""
    from assistant_botanique.ui.app import PlantCareApp

    if getattr(PlantCareApp, "_application_icon_installed", False):
        return

    previous_init = PlantCareApp.__init__

    def enhanced_init(self, root) -> None:
        apply_app_icon(root)
        previous_init(self, root)

    PlantCareApp.__init__ = enhanced_init
    PlantCareApp._application_icon_installed = True


__all__ = ["install_application_icon"]

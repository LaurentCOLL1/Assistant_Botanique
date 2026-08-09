"""Fonctions additionnelles de productivité et d'usage mobile."""

from .application_icon import install_application_icon
from .branding_surfaces import install_branding_surfaces
from .collection_photo_viewer import install_collection_photo_viewer
from .collection_watering_consistency import install_collection_watering_consistency
from .followup_fixes import install_followup_fixes
from .integration import install_productivity_features as _install_productivity_features
from .runtime_fixes import install_runtime_fixes
from .today_scientific_column import install_today_scientific_column
from .treeview_headers import install_treeview_header_fixes
from .usability_fixes import install_usability_fixes
from .watering_deferral import install_watering_deferral
from .watering_initialization import install_watering_initialization_guard
from .watering_workflow import install_watering_workflow


def install_productivity_features() -> None:
    _install_productivity_features()
    install_runtime_fixes()
    install_usability_fixes()
    install_followup_fixes()
    install_collection_photo_viewer()
    install_watering_workflow()
    install_watering_initialization_guard()
    install_watering_deferral()
    install_collection_watering_consistency()
    install_today_scientific_column()
    install_treeview_header_fixes()
    install_application_icon()
    install_branding_surfaces()


__all__ = ["install_productivity_features"]

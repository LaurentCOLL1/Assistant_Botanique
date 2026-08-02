"""Fonctions additionnelles de productivité et d'usage mobile."""

from .followup_fixes import install_followup_fixes
from .integration import install_productivity_features as _install_productivity_features
from .runtime_fixes import install_runtime_fixes
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
    install_watering_workflow()
    install_watering_initialization_guard()
    install_watering_deferral()
    install_treeview_header_fixes()


__all__ = ["install_productivity_features"]

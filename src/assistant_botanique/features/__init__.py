"""Fonctions additionnelles de productivité et d'usage mobile."""

from .integration import install_productivity_features as _install_productivity_features
from .runtime_fixes import install_runtime_fixes
from .usability_fixes import install_usability_fixes


def install_productivity_features() -> None:
    _install_productivity_features()
    install_runtime_fixes()
    install_usability_fixes()


__all__ = ["install_productivity_features"]

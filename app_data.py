"""Compatibilité des données historiques avec le chargeur version 3."""
from __future__ import annotations

from assistant_botanique.infrastructure.catalogue import load_catalogue, load_legacy_constants

COLLECTION_INITIALE_DEFAUT, DIAGNOSTICS_DATA, PROFILS_GENERIQUES = load_legacy_constants()
DATABASE_PLANTES: list[dict] = []
CATALOGUE_ERRORS: list[str] = []
DATABASE_BY_ID: dict[str, dict] = {}
DATABASE_BY_SCIENTIFIC_NAME: dict[str, dict] = {}


def reload_catalogue() -> None:
    catalogue, errors = load_catalogue()
    DATABASE_PLANTES.clear()
    DATABASE_PLANTES.extend(catalogue)
    CATALOGUE_ERRORS.clear()
    CATALOGUE_ERRORS.extend(errors)
    DATABASE_BY_ID.clear()
    DATABASE_BY_ID.update({profile["id"]: profile for profile in DATABASE_PLANTES})
    DATABASE_BY_SCIENTIFIC_NAME.clear()
    DATABASE_BY_SCIENTIFIC_NAME.update({profile["nom_sci"]: profile for profile in DATABASE_PLANTES})


reload_catalogue()

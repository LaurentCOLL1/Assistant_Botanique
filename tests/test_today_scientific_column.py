from datetime import date
from types import SimpleNamespace

from assistant_botanique.features.today_scientific_column import (
    TODAY_COLUMN_KEYS,
    scientific_name_for_profile,
    today_row_values,
)


def test_scientific_name_is_read_from_taxonomy():
    profile = {"taxonomie": {"nom_scientifique": "Epipremnum aureum"}}

    assert scientific_name_for_profile(profile) == "Epipremnum aureum"
    assert scientific_name_for_profile({}) == "Non renseigné"
    assert scientific_name_for_profile(None) == "Non renseigné"


def test_today_row_places_scientific_name_between_plant_and_care():
    item = SimpleNamespace(
        due_date=date(2026, 8, 3),
        plant_name="Pothos salon",
        label="Contrôle d'humidité",
        status="Demain",
        details="Intervalle estimé : 7 j",
    )

    values = today_row_values(
        item,
        {"taxonomie": {"nom_scientifique": "Epipremnum aureum"}},
        "Humide",
    )

    assert TODAY_COLUMN_KEYS == (
        "date",
        "plant",
        "scientific",
        "care",
        "status",
        "moisture",
        "details",
    )
    assert values[1:4] == (
        "Pothos salon",
        "Epipremnum aureum",
        "Contrôle d'humidité",
    )
    assert len(values) == len(TODAY_COLUMN_KEYS)

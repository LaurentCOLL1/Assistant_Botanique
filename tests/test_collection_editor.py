from copy import deepcopy

import pytest

from core import ValidationError
from assistant_botanique.ui.collection_editor_tab import apply_collection_correction


PLANT = {
    "id": "plant-1",
    "species_id": "ancienne-espece",
    "surnom": "Ancien nom",
    "pot_l": 1.5,
    "date_arrosage": "01/07/2026",
    "contexte": {"emplacement": "interieur", "exposition": "ombre"},
    "historique_soins": [{"id": "event-1", "type": "arrosage", "date": "01/07/2026", "note": "Initial"}],
}


def test_correction_preserves_identity_and_history():
    original = deepcopy(PLANT)
    corrected = apply_collection_correction(
        PLANT,
        species_id="nouvelle-espece",
        nickname="Nom corrigé",
        pot_l="2,5",
        last_watering="15/07/2026",
        location="exterieur",
        exposure="lumiere_vive",
        pot_material="terre_cuite",
        substrate="terreau drainant",
    )

    assert corrected["id"] == "plant-1"
    assert corrected["historique_soins"] == original["historique_soins"]
    assert corrected["species_id"] == "nouvelle-espece"
    assert corrected["surnom"] == "Nom corrigé"
    assert corrected["pot_l"] == 2.5
    assert corrected["date_arrosage"] == "15/07/2026"
    assert corrected["contexte"]["matiere_pot"] == "terre_cuite"
    assert PLANT == original


def test_future_watering_date_is_rejected():
    with pytest.raises(ValidationError):
        apply_collection_correction(
            PLANT,
            species_id="espece",
            nickname="Test",
            pot_l="2",
            last_watering="01/01/2099",
            location="interieur",
            exposure="ombre",
            pot_material="plastique",
            substrate="terreau",
        )

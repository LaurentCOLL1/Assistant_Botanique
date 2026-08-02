from datetime import date

import pytest

from core import ValidationError
from assistant_botanique.domain.soil_moisture import SOIL_DRY, SOIL_MOIST, SOIL_WET
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.dashboard import build_dashboard_snapshot
from assistant_botanique.services.soil_moisture import record_soil_moisture
from assistant_botanique.services.watering_deferral import (
    latest_deferred_watering_check,
    record_deferred_watering_check,
    recommended_recheck_delay,
)


def profile():
    return {
        "id": "epipremnum-aureum",
        "nom_sci": "Epipremnum aureum",
        "famille": "Araceae",
        "gestion_eau": {"frequence_arrosage": {"aout": 7}},
    }


def plant():
    return {
        "id": "plant-1",
        "species_id": "epipremnum-aureum",
        "surnom": "Pothos",
        "pot_l": 2,
        "date_arrosage": "20/07/2026",
        "contexte": {"emplacement": "interieur"},
        "historique_soins": [
            {"type": "arrosage", "date": "20/07/2026", "note": "Arrosage initial"}
        ],
    }


def test_moist_soil_can_defer_the_check_without_recording_watering(tmp_path):
    database = Database(tmp_path / "collection.sqlite3")
    database.save_plants([plant()])
    botanical_profile = profile()
    current = date(2026, 8, 2)

    record_soil_moisture(database, "plant-1", SOIL_MOIST, botanical_profile)
    stored_plant = database.load_plants()[0]
    deferred = record_deferred_watering_check(
        database,
        "plant-1",
        botanical_profile,
        stored_plant,
        SOIL_MOIST,
        today=current,
    )

    assert deferred.due_date == date(2026, 8, 4)
    assert database.load_plants()[0]["date_arrosage"] == "20/07/2026"
    assert not any(
        event["type"] == "arrosage" and event["date"] == "02/08/2026"
        for event in database.load_plants()[0]["historique_soins"]
    )

    snapshot = build_dashboard_snapshot(
        database,
        {"epipremnum-aureum": botanical_profile},
        today=current,
    )
    check = next(item for item in snapshot.items if item.identifier == "check:plant-1")
    assert check.due_date == date(2026, 8, 4)
    assert check.status == "Dans 2 j"
    assert "Contrôle reporté" in check.details


def test_check_cannot_be_deferred_when_watering_is_required(tmp_path):
    database = Database(tmp_path / "collection.sqlite3")
    database.save_plants([plant()])
    botanical_profile = profile()
    stored_plant = database.load_plants()[0]

    with pytest.raises(ValidationError, match="besoin d'être arrosée"):
        recommended_recheck_delay(
            botanical_profile,
            stored_plant,
            SOIL_DRY,
            today=date(2026, 8, 2),
        )


def test_new_moisture_observation_supersedes_the_previous_deferral(tmp_path):
    database = Database(tmp_path / "collection.sqlite3")
    database.save_plants([plant()])
    botanical_profile = profile()
    current = date(2026, 8, 2)

    record_soil_moisture(database, "plant-1", SOIL_MOIST, botanical_profile)
    record_deferred_watering_check(
        database,
        "plant-1",
        botanical_profile,
        database.load_plants()[0],
        SOIL_MOIST,
        today=current,
    )
    assert latest_deferred_watering_check(database, "plant-1") is not None

    record_soil_moisture(database, "plant-1", SOIL_WET, botanical_profile)
    assert latest_deferred_watering_check(database, "plant-1") is None

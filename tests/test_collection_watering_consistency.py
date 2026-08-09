from datetime import date

from assistant_botanique.domain.soil_moisture import SOIL_DRY, SOIL_MOIST
from assistant_botanique.features.watering_workflow import _record_check_moisture
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.collection_watering import (
    CollectionWateringSchedule,
    collection_watering_schedule,
    next_due_collection_identifier,
)


def profile():
    return {
        "id": "epipremnum-aureum",
        "nom_sci": "Epipremnum aureum",
        "famille": "Araceae",
        "gestion_eau": {"frequence_arrosage": {"aout": 7}},
    }


def plant(plant_id: str = "plant-1", nickname: str = "Pothos"):
    return {
        "id": plant_id,
        "species_id": "epipremnum-aureum",
        "surnom": nickname,
        "pot_l": 2,
        "date_arrosage": "20/07/2026",
        "contexte": {"emplacement": "interieur"},
        "historique_soins": [
            {"type": "arrosage", "date": "20/07/2026", "note": "Arrosage initial"}
        ],
    }


def test_collection_status_uses_deferred_check_after_moist_observation(tmp_path):
    database = Database(tmp_path / "collection.sqlite3")
    specimen = plant()
    botanical_profile = profile()
    database.save_plants([specimen])
    current = date(2026, 8, 9)

    _snapshot, deferred = _record_check_moisture(
        database,
        "plant-1",
        botanical_profile,
        specimen,
        SOIL_MOIST,
        today=current,
    )
    assert deferred is not None

    schedule = collection_watering_schedule(
        database,
        specimen,
        botanical_profile,
        today=current,
    )

    assert schedule.deferred
    assert schedule.due_date == date(2026, 8, 11)
    assert schedule.code == "OK"
    assert schedule.short_label == "🟢 Contrôle dans 2 j"
    assert "Nouvelle échéance : 11/08/2026" in schedule.detail


def test_collection_keeps_due_status_when_dry_soil_requires_watering(tmp_path):
    database = Database(tmp_path / "collection.sqlite3")
    specimen = plant()
    botanical_profile = profile()
    database.save_plants([specimen])
    current = date(2026, 8, 9)

    _snapshot, deferred = _record_check_moisture(
        database,
        "plant-1",
        botanical_profile,
        specimen,
        SOIL_DRY,
        today=current,
    )
    assert deferred is None

    schedule = collection_watering_schedule(
        database,
        specimen,
        botanical_profile,
        today=current,
    )

    assert not schedule.deferred
    assert schedule.due_date == date(2026, 7, 27)
    assert schedule.code == "LATE"
    assert "Contrôle en retard" in schedule.short_label


def test_collection_advances_only_to_another_due_control():
    schedules = {
        "plant-1": CollectionWateringSchedule(
            "plant-1", date(2026, 8, 9), "TODAY", "Aujourd'hui", "", False
        ),
        "plant-2": CollectionWateringSchedule(
            "plant-2", date(2026, 8, 12), "OK", "Dans 3 j", "", False
        ),
        "plant-3": CollectionWateringSchedule(
            "plant-3", date(2026, 8, 8), "LATE", "En retard", "", False
        ),
    }

    next_identifier = next_due_collection_identifier(
        schedules,
        ("plant-1", "plant-2", "plant-3"),
        "plant-1",
        today=date(2026, 8, 9),
    )

    assert next_identifier == "plant-3"

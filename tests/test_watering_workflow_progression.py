from datetime import date
from types import SimpleNamespace

from assistant_botanique.domain.soil_moisture import SOIL_DRY, SOIL_MOIST
from assistant_botanique.features.watering_workflow import (
    _next_check_identifier,
    _record_check_moisture,
)
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.dashboard import build_dashboard_snapshot


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


def test_no_watering_observation_immediately_moves_check_to_next_due_date(tmp_path):
    database = Database(tmp_path / "collection.sqlite3")
    botanical_profile = profile()
    specimen = plant()
    database.save_plants([specimen])
    current = date(2026, 8, 9)

    snapshot, deferred = _record_check_moisture(
        database,
        "plant-1",
        botanical_profile,
        specimen,
        SOIL_MOIST,
        today=current,
    )

    assert snapshot.state == SOIL_MOIST
    assert deferred is not None
    assert deferred.due_date == date(2026, 8, 11)

    dashboard = build_dashboard_snapshot(
        database,
        {"epipremnum-aureum": botanical_profile},
        today=current,
    )
    check = next(item for item in dashboard.items if item.identifier == "check:plant-1")
    assert check.status == "Dans 2 j"
    assert "Contrôle reporté" in check.details


def test_dry_soil_that_requires_watering_stays_on_current_check(tmp_path):
    database = Database(tmp_path / "collection.sqlite3")
    botanical_profile = profile()
    specimen = plant()
    database.save_plants([specimen])

    snapshot, deferred = _record_check_moisture(
        database,
        "plant-1",
        botanical_profile,
        specimen,
        SOIL_DRY,
        today=date(2026, 8, 9),
    )

    assert snapshot.state == SOIL_DRY
    assert deferred is None


def test_next_check_skips_completed_plant_and_non_check_tasks():
    items = {
        "check:plant-1": SimpleNamespace(kind="check", plant_id="plant-1"),
        "task:fertilize": SimpleNamespace(kind="task", plant_id="plant-2"),
        "check:plant-2": SimpleNamespace(kind="check", plant_id="plant-2"),
    }

    next_identifier = _next_check_identifier(
        items,
        ("check:plant-1", "task:fertilize", "check:plant-2"),
        "plant-1",
    )

    assert next_identifier == "check:plant-2"

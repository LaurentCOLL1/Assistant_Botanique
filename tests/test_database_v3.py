import json
from pathlib import Path

from assistant_botanique.infrastructure.database import Database


def sample_plant():
    return {
        "id": "plant-1",
        "species_id": "aloe-vera",
        "surnom": "Aloé",
        "pot_l": 2.5,
        "date_arrosage": "30/07/2026",
        "contexte": {"exposition": "lumiere_vive"},
        "historique_soins": [{"id": "event-1", "type": "arrosage", "date": "30/07/2026", "note": "Initial"}],
    }


def test_sqlite_round_trip_and_event(tmp_path: Path):
    database = Database(tmp_path / "app.sqlite3")
    database.save_plants([sample_plant()])
    database.add_care_event("plant-1", "encore_humide", "31/07/2026", "Encore humide")
    loaded = database.load_plants()
    assert loaded[0]["surnom"] == "Aloé"
    assert [event["type"] for event in loaded[0]["historique_soins"]] == ["arrosage", "encore_humide"]


def test_legacy_json_is_imported_once(tmp_path: Path):
    legacy = tmp_path / "mes_plantes.json"
    legacy.write_text(json.dumps([sample_plant()]), encoding="utf-8")
    database = Database(tmp_path / "app.sqlite3")
    assert database.import_legacy_if_needed(candidates=(legacy,)) is True
    assert database.import_legacy_if_needed(candidates=(legacy,)) is False
    assert database.stats()["plants"] == 1


def test_catalog_review_round_trip(tmp_path: Path):
    database = Database(tmp_path / "app.sqlite3")
    database.save_catalog_review("aloe-vera", "valide", "elevee", ["https://example.org"], "Vérifié", {"id": "aloe-vera"})
    review = database.get_catalog_review("aloe-vera")
    assert review["status"] == "valide"
    assert review["sources"] == ["https://example.org"]

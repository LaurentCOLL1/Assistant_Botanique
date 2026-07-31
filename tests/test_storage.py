import json
from pathlib import Path

from storage import CollectionRepository, atomic_write_json, migrate_item


def test_migration_creates_unique_ids_for_duplicate_nicknames():
    first = migrate_item({"surnom": "Mon Aloe", "nom_sci": "Aloe vera", "pot": "2", "date_arrosage": "30/07/2026"})
    second = migrate_item({"surnom": "Mon Aloe", "nom_sci": "Aloe vera", "pot": "2", "date_arrosage": "30/07/2026"})
    assert first["surnom"] == second["surnom"]
    assert first["id"] != second["id"]


def test_collection_round_trip(tmp_path: Path):
    repository = CollectionRepository(path=tmp_path / "collection.json", legacy_path=tmp_path / "legacy.json")
    plants = [migrate_item({"surnom": "Test", "nom_sci": "Testus plantus", "pot": "1.5", "date_arrosage": "30/07/2026"})]
    repository.save(plants)
    loaded = repository.load()
    assert loaded[0]["id"] == plants[0]["id"]
    assert loaded[0]["pot_l"] == 1.5


def test_atomic_write_replaces_complete_json(tmp_path: Path):
    path = tmp_path / "file.json"
    atomic_write_json(path, {"value": 1})
    atomic_write_json(path, {"value": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"value": 2}
    assert not list(tmp_path.glob("*.tmp"))

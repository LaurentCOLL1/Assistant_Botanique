from pathlib import Path

from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.photos import PhotoService


def test_photo_is_copied_and_indexed(tmp_path: Path):
    database = Database(tmp_path / "data" / "app.sqlite3")
    database.save_plants([{"id": "p1", "species_id": "sp", "surnom": "Test", "pot_l": 1, "date_arrosage": "30/07/2026", "historique_soins": []}])
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fake-jpeg-content")
    service = PhotoService(database, tmp_path / "data" / "photos")
    item = service.add_photo("p1", source, "Première feuille")
    assert Path(item["path"]).exists()
    assert database.list_photos("p1")[0]["caption"] == "Première feuille"
    assert service.delete_photo(item["id"])
    assert not Path(item["path"]).exists()

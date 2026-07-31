from pathlib import Path

from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.backup import BackupService


def test_complete_backup_has_manifest_and_restores(tmp_path: Path):
    data_dir = tmp_path / "data"
    database = Database(data_dir / "assistant_botanique.sqlite3")
    database.save_plants([
        {"id": "p1", "species_id": "sp", "surnom": "Test", "pot_l": 1, "date_arrosage": "30/07/2026", "historique_soins": []}
    ])
    (data_dir / "settings.json").write_text('{"theme":"dark"}', encoding="utf-8")
    service = BackupService(database, data_dir)
    archive = service.create(tmp_path / "backup.botanique")
    manifest = service.inspect(archive)
    assert "assistant_botanique.sqlite3" in manifest["files"]
    (data_dir / "settings.json").write_text('{"theme":"light"}', encoding="utf-8")
    result = service.restore(archive)
    assert '"dark"' in (data_dir / "settings.json").read_text(encoding="utf-8")
    assert Path(result["safety_copy"]).exists()

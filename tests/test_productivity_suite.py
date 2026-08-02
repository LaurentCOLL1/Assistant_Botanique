from datetime import datetime, timedelta
import os

from PIL import Image

from assistant_botanique.features.backup_scheduler import backup_due, rotate_backups
from assistant_botanique.features.inventory import INVENTORY_CATEGORIES, normalize_barcode, subcategories_for
from assistant_botanique.features.photo_diagnostic import analyze_photo
from assistant_botanique.services.updater import _choose_windows_asset


def test_inventory_subcategories_cover_substrates():
    assert "Substrat" in INVENTORY_CATEGORIES
    values = subcategories_for("Substrat")
    assert "Terreau orchidées" in values
    assert "Perlite" in values
    assert "Mélange personnel" in values
    assert len(values) == len(set(values))


def test_barcode_normalization():
    assert normalize_barcode(" 3 760123-456789 ") == "3760123456789"
    assert normalize_barcode("") == ""


def test_photo_diagnostic_detects_yellow_dominance(tmp_path):
    path = tmp_path / "yellow.png"
    Image.new("RGB", (120, 120), (205, 185, 45)).save(path)
    report = analyze_photo(path)
    assert report.metrics["part_jaune"] > 0.5
    assert any("Jaunissement" in finding.title for finding in report.findings)
    assert report.disclaimer


def test_backup_due_respects_cadence():
    now = datetime(2026, 8, 2, 10, 0)
    assert backup_due({"enabled": True, "cadence": "daily", "last_run": ""}, now)
    assert not backup_due(
        {"enabled": True, "cadence": "daily", "last_run": (now - timedelta(hours=2)).isoformat()},
        now,
    )
    assert backup_due(
        {"enabled": True, "cadence": "weekly", "last_run": (now - timedelta(days=8)).isoformat()},
        now,
    )
    assert not backup_due({"enabled": False}, now)


def test_backup_rotation_keeps_requested_count(tmp_path):
    for index in range(5):
        path = tmp_path / f"assistant-botanique-auto-2026080{index}-100000.botanique"
        path.write_text(str(index), encoding="utf-8")
        timestamp = 1_700_000_000 + index
        os.utime(path, (timestamp, timestamp))
    removed = rotate_backups(tmp_path, 2)
    assert len(removed) == 3
    assert len(list(tmp_path.glob("assistant-botanique-auto-*.botanique"))) == 2


def test_updater_prefers_installer_asset():
    asset = _choose_windows_asset(
        [
            {"name": "AssistantBotanique-portable.exe", "size": 200},
            {"name": "AssistantBotanique-Setup.exe", "size": 150},
            {"name": "sources.zip", "size": 500},
        ]
    )
    assert asset is not None
    assert asset["name"] == "AssistantBotanique-Setup.exe"

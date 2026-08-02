from io import BytesIO

import qrcode

from assistant_botanique.features.usability_fixes import (
    install_usability_fixes,
    normalized_photo_preview_count,
)
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.infrastructure.intelligence_repository import IntelligenceRepository
from assistant_botanique.services.barcode_scanner import (
    decode_barcode_image,
    inject_barcode_fallback,
)


def sample_plant():
    return {
        "id": "plant-1",
        "species_id": "epipremnum-aureum",
        "surnom": "Pothos",
        "pot_l": 2,
        "date_arrosage": "01/07/2026",
        "contexte": {"emplacement": "salon"},
        "historique_soins": [],
    }


def test_barcode_photo_is_decoded_locally():
    image = qrcode.make("5901234123457")
    output = BytesIO()
    image.save(output, format="PNG")

    result = decode_barcode_image(output.getvalue())

    assert result["text"] == "5901234123457"
    assert result["format"]


def test_mobile_page_gets_a_photo_fallback():
    source = (
        '<html><body><button type="button" id="scan-barcode">📷 Scanner le code-barres</button>'
        '<p id="scan-status"></p><video id="barcode-video"></video><input id="barcode"></body></html>'
    )

    enhanced = inject_barcode_fallback(source, "http://192.168.1.20:9000/decode?token=test")

    assert 'id="barcode-photo"' in enhanced
    assert "Photographier le code-barres" in enhanced
    assert "192.168.1.20:9000" in enhanced
    assert "abPhoto.click()" in enhanced


def test_photo_preview_count_has_safe_limits():
    assert normalized_photo_preview_count(None) == 2
    assert normalized_photo_preview_count(1) == 2
    assert normalized_photo_preview_count(6) == 6
    assert normalized_photo_preview_count(99) == 12


def test_one_plant_can_be_removed_without_closing_infestation(tmp_path):
    install_usability_fixes()
    database = Database(tmp_path / "test.sqlite3")
    database.save_plants([sample_plant()])
    repository = IntelligenceRepository(database)
    case_id = repository.create_infestation("Cochenilles", "Cochenilles", "2026-08-02")
    repository.add_plant_to_infestation(case_id, "plant-1")

    repository.remove_plant_from_infestation(case_id, "plant-1")

    case = repository.list_infestations()[0]
    assert case["status"] == "active"
    assert case["plant_count"] == 0
    assert case["plants"] == []

from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO

from PIL import Image

from core import format_date_fr
from assistant_botanique.domain.ui_mode import visible_tab_keys
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.infrastructure.intelligence_repository import IntelligenceRepository
from assistant_botanique.services.encrypted_sync import decrypt_payload, encrypt_payload
from assistant_botanique.services.local_web import LocalCompanionServer
from assistant_botanique.services.notifications import NotificationService
from assistant_botanique.services.photos import PhotoService
from assistant_botanique.services.plugin_manager import PluginManager
from assistant_botanique.services.repotting import recommend_repotting
from assistant_botanique.services.rules_engine import RulesEngine


def sample_plant(identifier="p1", nickname="Pothos"):
    return {
        "id": identifier,
        "species_id": "epipremnum-aureum",
        "surnom": nickname,
        "pot_l": 2,
        "date_arrosage": format_date_fr(date.today() - timedelta(days=30)),
        "contexte": {
            "emplacement": "salon",
            "exposition": "lumiere_vive",
            "matiere_pot": "terre_cuite",
            "substrat": "terreau drainant",
        },
        "historique_soins": [],
    }


def sample_profile():
    return {
        "id": "epipremnum-aureum",
        "taxonomie": {"nom_scientifique": "Epipremnum aureum", "famille": "Araceae"},
        "gestion_eau": {"frequence_arrosage": {date.today().strftime("%B").casefold(): 1}},
        "substrat": "mélange aroïde avec écorces",
    }


def database_with_plant(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.save_plants([sample_plant()])
    return database


def test_locations_and_infestations_are_linked_to_collection(tmp_path):
    database = database_with_plant(tmp_path)
    repository = IntelligenceRepository(database)
    home = repository.add_location("Maison", kind="bâtiment")
    salon = repository.add_location("Salon", parent_id=home, kind="pièce")
    repository.assign_plant_location("p1", salon)

    assert repository.plant_location_map()["p1"]["path"] == "Maison / Salon"
    assert database.load_plants()[0]["contexte"]["emplacement"] == "Maison / Salon"

    case_id = repository.create_infestation("Cochenilles du salon", "cochenilles", date.today(), severity=3)
    repository.add_plant_to_infestation(case_id, "p1")
    repository.add_infestation_observation(case_id, "Deux individus retirés", plant_id="p1", severity=2)
    case = repository.list_infestations()[0]
    assert case["plant_count"] == 1
    assert case["observations"][0]["notes"] == "Deux individus retirés"
    assert "p1" in repository.active_infestation_plant_ids()


def test_repotting_assistant_proposes_larger_but_prudent_pot():
    result = recommend_repotting(
        sample_plant(),
        sample_profile(),
        roots_crowded=True,
        growth_state="vigoureuse",
        substrate_age_months=24,
    )
    assert result.urgency == "prioritaire"
    assert 2 < result.target_volume_l <= 3.2
    assert any("écorces" in name for name, _volume in result.mix_liters)


def test_encrypted_snapshot_payload_requires_password():
    blob = encrypt_payload(b"botanical-data", "mot-de-passe-solide", {"format": 1})
    metadata, payload = decrypt_payload(blob, "mot-de-passe-solide")
    assert metadata["format"] == 1
    assert payload == b"botanical-data"
    try:
        decrypt_payload(blob, "mauvais-mot-de-passe")
    except ValueError as exc:
        assert "incorrect" in str(exc)
    else:
        raise AssertionError("Un mauvais mot de passe doit être refusé")


def test_rules_only_create_alerts_or_tasks(tmp_path):
    database = database_with_plant(tmp_path)
    repository = IntelligenceRepository(database)
    rule_id = repository.save_rule(
        rule_id=None,
        name="Arrosage ancien",
        condition={"type": "days_since_watering_gte", "days": 10},
        action={"type": "create_alert", "message": "Contrôler {plant}"},
        cooldown_hours=24,
    )
    result = RulesEngine(database).evaluate_all(now=datetime.now())[0]
    assert result.rule_id == rule_id
    assert result.triggered
    assert repository.list_rule_alerts()[0]["message"] == "Contrôler Pothos"


def test_mobile_photo_is_verified_and_registered(tmp_path):
    database = database_with_plant(tmp_path)
    stream = BytesIO()
    Image.new("RGB", (80, 60), (120, 180, 90)).save(stream, format="JPEG")
    service = PhotoService(database, tmp_path / "photos")
    result = service.add_photo_bytes("p1", stream.getvalue(), filename="camera.jpg", caption="Vue mobile")

    assert result["path"].endswith(".jpg")
    assert len(database.list_photos("p1")) == 1
    server = LocalCompanionServer(database, {"epipremnum-aureum": sample_profile()}, token="secret-token")
    page = server._plant_page("p1", "?token=secret-token")
    assert 'capture="environment"' in page
    assert "/api/photo" in page


def test_manual_due_view_can_include_snoozed_items(tmp_path):
    database = database_with_plant(tmp_path)
    profile = sample_profile()
    service = NotificationService()
    items = service.due_items(database, {"epipremnum-aureum": profile})
    assert items
    service.snooze(database, [items[0].key], hours=24)
    assert service.due_items(database, {"epipremnum-aureum": profile}) == []
    assert service.due_items(database, {"epipremnum-aureum": profile}, include_snoozed=True)


def test_plugin_must_be_explicitly_enabled(tmp_path):
    database = database_with_plant(tmp_path)
    repository = IntelligenceRepository(database)
    plugin_dir = tmp_path / "plugins" / "demo"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        '{"id":"demo.plugin","name":"Demo","version":"1.0","api_version":1,"entrypoint":"plugin.py"}',
        encoding="utf-8",
    )
    (plugin_dir / "plugin.py").write_text(
        "def register(api):\n    api.register_report_section('demo', lambda: 'ok')\n",
        encoding="utf-8",
    )
    manager = PluginManager(repository, tmp_path / "plugins")
    descriptor = manager.discover()[0]
    assert not descriptor.enabled
    manager.set_enabled(descriptor.plugin_id, True)
    assert manager.load_enabled()[descriptor.plugin_id] == "chargée"
    assert manager.api.report_sections["demo"]() == "ok"


def test_intelligence_tab_is_advanced_only():
    assert "intelligence" not in visible_tab_keys("simple")
    assert "intelligence" in visible_tab_keys("advanced")

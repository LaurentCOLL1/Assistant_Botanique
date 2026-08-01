from datetime import date
from urllib.request import urlopen

from assistant_botanique.infrastructure.advanced_repository import AdvancedRepository
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.labels import LabelService
from assistant_botanique.services.local_web import LocalCompanionServer
from assistant_botanique.services.notifications import NotificationItem, NotificationService
from assistant_botanique.services.taxonomy_diff import compare_taxonomy
from assistant_botanique.services.weather import WeatherDay, outdoor_care_advisories


def sample_plant(identifier="p1", nickname="Pothos"):
    return {
        "id": identifier,
        "species_id": "epipremnum-aureum",
        "surnom": nickname,
        "pot_l": 2,
        "date_arrosage": "01/07/2026",
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
        "taxonomie": {
            "nom_scientifique": "Epipremnum aureum",
            "noms_vernaculaires": ["Pothos"],
            "famille": "Araceae",
        },
        "gestion_eau": {"frequence_arrosage": {"aout": 10}},
    }


def test_bulk_action_is_transactional_and_undoable(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.save_plants([sample_plant(), sample_plant("p2", "Second")])
    repository = AdvancedRepository(database)

    history_id = repository.apply_bulk_care(
        ["p1", "p2"],
        "arrosage",
        "Action groupée validée",
        date(2026, 8, 1),
    )

    plants = {item["id"]: item for item in database.load_plants()}
    assert plants["p1"]["date_arrosage"] == "01/08/2026"
    assert any(event["note"] == "Action groupée validée" for event in plants["p2"]["historique_soins"])

    repository.undo(history_id)
    plants = {item["id"]: item for item in database.load_plants()}
    assert plants["p1"]["date_arrosage"] == "01/07/2026"
    assert not any(event["note"] == "Action groupée validée" for event in plants["p1"]["historique_soins"])


def test_propagation_inventory_treatment_and_sensor_workflows(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.save_plants([sample_plant(), sample_plant("p2", "Bouture établie")])
    repository = AdvancedRepository(database)

    propagation_id = repository.add_propagation(
        "p1", "Bouture 1", "bouture_eau", date(2026, 8, 1)
    )
    repository.update_propagation(
        propagation_id,
        child_plant_id="p2",
        rooted_on=date(2026, 8, 20),
        status="plante_etablie",
    )
    assert repository.list_propagations()[0]["child_nickname"] == "Bouture établie"

    product_id = repository.save_inventory_item(
        item_id=None,
        name="Savon noir",
        category="traitement",
        unit="ml",
        quantity=100,
        reorder_level=20,
    )
    protocol_id = repository.create_treatment_protocol(
        "p1",
        "Traitement pucerons",
        date(2026, 8, 1),
        interval_days=7,
        total_steps=2,
        product_item_id=product_id,
        dose=10,
        dose_unit="ml",
    )
    first_step = repository.list_treatment_steps(protocol_id)[0]
    repository.complete_treatment_step(first_step["id"])
    assert repository.list_inventory()[0]["quantity"] == 90

    sensor = repository.create_sensor_source("Hygromètre", "humidite", "%", plant_id="p1")
    repository.add_sensor_reading(sensor["id"], 56.5, ingest_token=sensor["token"])
    assert repository.latest_sensor_readings()[0]["value"] == 56.5


def test_qr_label_sheet_is_printable(tmp_path):
    service = LabelService()
    destination = service.generate_printable_sheet(
        [sample_plant()],
        {"epipremnum-aureum": sample_profile()},
        tmp_path / "labels.html",
        base_url="http://127.0.0.1:8765",
        companion_token="secret",
    )
    content = destination.read_text(encoding="utf-8")
    assert "data:image/png;base64" in content
    assert "Pothos" in content
    assert "/plant/p1?token=secret" not in content


def test_taxonomy_diff_and_weather_advisories_are_explicit():
    proposal = compare_taxonomy(
        "ancienne-espece",
        "Oldus plantus",
        "Oldaceae",
        {
            "acceptedScientificName": "Novus plantus",
            "family": "Novaceae",
            "confidence": 98,
            "acceptedUsageKey": 123,
            "status": "ACCEPTED",
        },
    )
    assert proposal
    assert proposal["proposed_family"] == "Novaceae"
    assert proposal["source_url"].endswith("/123")

    advisories = outdoor_care_advisories(
        [
            WeatherDay(date(2026, 8, 1), -1, 34, 12, 70, 0),
            WeatherDay(date(2026, 8, 2), 4, 31, 0, 20, 0),
        ]
    )
    assert any("Gel" in item for item in advisories)
    assert any("Forte chaleur" in item for item in advisories)
    assert any("Rafales" in item for item in advisories)


def test_notification_digest_groups_by_location():
    service = NotificationService()
    title, body = service.digest(
        [
            NotificationItem("a", "Pothos : contrôle aujourd'hui.", "salon", 100, "p1"),
            NotificationItem("b", "Ficus : fertilisation prévue.", "salon", 80, "p2"),
        ],
        {"notifications": {"group_by_location": True, "max_items": 8}},
    )
    assert "2 soin(s)" in title
    assert "salon :" in body
    assert body.count("•") == 2


def test_local_companion_defaults_to_loopback(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.save_plants([sample_plant()])
    server = LocalCompanionServer(
        database,
        {"epipremnum-aureum": sample_profile()},
        token="test-token",
    )
    try:
        url = server.start(lan=False, port=0)
        assert url.startswith("http://127.0.0.1:")
        with urlopen(server.access_url, timeout=5) as response:
            page = response.read().decode("utf-8")
        assert "Pothos" in page
    finally:
        server.stop()


def test_advanced_mode_exposes_ecosystem():
    from assistant_botanique.domain.ui_mode import visible_tab_keys

    assert "ecosystem" in visible_tab_keys("advanced")
    assert "ecosystem" not in visible_tab_keys("simple")

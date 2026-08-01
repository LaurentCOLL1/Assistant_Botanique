import json
from datetime import date

from assistant_botanique.domain.guided_diagnostic import DiagnosticAnswers, diagnose
from assistant_botanique.domain.search import SearchFilters, global_search
from assistant_botanique.domain.ui_mode import visible_tab_keys
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.exchange import ExchangeService, count_exported_plants
from assistant_botanique.services.planner import CarePlanner


def sample_plant(identifier="p1", nickname="Mon pothos"):
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
        "gestion_eau": {"frequence_arrosage": {"juillet": 10}},
        "photo": {"status": "found"},
    }


def test_planner_records_non_watering_care_and_recurrence(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.save_plants([sample_plant()])
    planner = CarePlanner(database)
    task_id = planner.schedule(
        "p1",
        "fertilisation",
        date(2026, 8, 1),
        note="Engrais dilué",
        recurrence_days=30,
    )

    next_task = planner.complete(task_id, completed_on=date(2026, 8, 2))

    assert next_task
    pending = planner.list_tasks(status="pending")
    assert pending[0]["due_date"] == "2026-09-01"
    events = database.load_plants()[0]["historique_soins"]
    assert any(event["type"] == "fertilisation" and event["note"] == "Engrais dilué" for event in events)


def test_json_and_csv_exchange_are_reimportable(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.save_plants([sample_plant()])
    exchange = ExchangeService(database)
    json_path = exchange.export_json(tmp_path / "collection.json")
    csv_path = exchange.export_csv(tmp_path / "collection.csv")

    assert count_exported_plants(json_path) == 1
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["plants"][0]["surnom"] = "Pothos modifié"
    json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    preview = exchange.preview(json_path)
    exchange.apply(preview, mode="merge")
    assert database.load_plants()[0]["surnom"] == "Pothos modifié"

    csv_preview = exchange.preview(csv_path)
    assert csv_preview.format == "csv"
    assert csv_preview.updated_count == 1
    assert csv_preview.warnings


def test_global_search_combines_collection_and_catalogue():
    profile = sample_profile()
    filters = SearchFilters(query="pothos", scope="all", family="Araceae", location="Tous", due_status="Tous")
    results = global_search(
        [sample_plant()],
        [profile],
        {"epipremnum-aureum": profile},
        filters,
        due_status_by_plant={"p1": "Aujourd'hui"},
        photo_plant_ids={"p1"},
    )
    assert [item.kind for item in results] == ["collection", "catalogue"]
    assert all(item.family == "Araceae" for item in results)


def test_guided_diagnosis_prioritizes_pests_when_seen():
    answers = DiagnosticAnswers(
        affected_part="jeunes feuilles",
        symptom="feuilles déformées ou enroulées",
        progression="rapide",
        substrate="légèrement humide",
        pests="oui",
        recent_change="aucun",
    )
    hypotheses = diagnose(answers, sample_plant())
    assert hypotheses[0].key == "ravageurs"
    assert hypotheses[0].score >= 10


def test_simple_mode_keeps_daily_workflows_visible():
    simple = visible_tab_keys("simple")
    assert simple == ("today", "collection", "search", "calendar", "photos", "catalogue", "maintenance")
    assert "diagnostic" not in simple
    assert "diagnostic" in visible_tab_keys("advanced")

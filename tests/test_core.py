from datetime import date

import pytest

from core import ValidationError, normalize_text, parse_date, toxicity_level, watering_status


def profile(interval=7, toxicity="Non toxique"):
    return {
        "taxonomie": {"nom_scientifique": "Testus plantus", "noms_vernaculaires": ["Plante test"], "famille": "Testaceae"},
        "gestion_eau": {"frequence_arrosage": {month: interval for month in (
            "janvier", "fevrier", "mars", "avril", "mai", "juin",
            "juillet", "aout", "septembre", "octobre", "novembre", "decembre"
        )}},
        "sante_securite": {"toxicite": toxicity},
    }


def test_non_toxique_is_not_toxic():
    assert toxicity_level("Non toxique pour les chats et les chiens") == "aucune"
    assert toxicity_level("Comestible / Non toxique") == "aucune"


def test_toxicity_levels():
    assert toxicity_level("Légèrement toxique") == "faible"
    assert toxicity_level("Hautement toxique et potentiellement mortel") == "elevee"
    assert toxicity_level({"niveau": "faible"}) == "faible"


def test_invalid_date_is_explicit():
    with pytest.raises(ValidationError):
        parse_date("31/02/2026")


def test_future_watering_date_is_rejected():
    with pytest.raises(ValidationError):
        watering_status("02/08/2026", profile(), today=date(2026, 8, 1))


def test_watering_is_a_check_reminder():
    status = watering_status("24/07/2026", profile(7), today=date(2026, 7, 31))
    assert status.code == "TODAY"
    assert "Vérifier" in status.detail


def test_search_is_accent_insensitive():
    assert normalize_text("Épinard de Malabar") == "epinard de malabar"

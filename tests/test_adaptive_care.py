from datetime import date

from assistant_botanique.domain.adaptive_care import recommend_care

PROFILE = {"gestion_eau": {"frequence_arrosage": {"juillet": 10}}}


def plant(history=None, **context):
    return {
        "id": "p1",
        "species_id": "test",
        "surnom": "Test",
        "pot_l": 2,
        "date_arrosage": "01/07/2026",
        "contexte": {"emplacement": "interieur", "exposition": "non_renseignee", "matiere_pot": "non_renseignee"} | context,
        "historique_soins": history or [],
    }


def test_direct_sun_shortens_check_interval():
    neutral = recommend_care(PROFILE, plant(), today=date(2026, 7, 2))
    sunny = recommend_care(PROFILE, plant(exposition="soleil_direct"), today=date(2026, 7, 2))
    assert sunny.interval_days < neutral.interval_days


def test_wet_observations_delay_next_check():
    wet_history = [{"type": "encore_humide", "date": "05/07/2026"} for _ in range(4)]
    neutral = recommend_care(PROFILE, plant(), today=date(2026, 7, 2))
    learned = recommend_care(PROFILE, plant(wet_history), today=date(2026, 7, 2))
    assert learned.interval_days > neutral.interval_days
    assert learned.confidence > neutral.confidence


def test_actual_intervals_contribute_to_learning():
    history = [
        {"type": "arrosage", "date": "01/06/2026"},
        {"type": "arrosage", "date": "16/06/2026"},
        {"type": "arrosage", "date": "01/07/2026"},
    ]
    recommendation = recommend_care(PROFILE, plant(history), today=date(2026, 7, 2))
    assert recommendation.interval_days > 10
    assert any("rythme observé" in reason for reason in recommendation.explanation)

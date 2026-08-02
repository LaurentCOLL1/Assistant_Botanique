from datetime import date

import pytest

from app_data import DATABASE_PLANTES
from core import profile_id
from assistant_botanique.domain.soil_moisture import (
    SOIL_DRY,
    SOIL_MOIST,
    SOIL_WET,
    watering_decision,
    watering_policy,
)
from assistant_botanique.infrastructure.database import Database
from assistant_botanique.services.soil_moisture import (
    latest_soil_moisture,
    record_soil_moisture,
    record_validated_watering,
)


def profile(name: str, family: str = "Araceae", *, water=None, **extra):
    item = {
        "id": name.casefold().replace(" ", "-"),
        "nom_sci": name,
        "famille": family,
        "gestion_eau": water or {"frequence_arrosage": {"aout": 7}},
    }
    item.update(extra)
    return item


def sample_plant(species_id: str = "epipremnum-aureum"):
    return {
        "id": "plant-1",
        "species_id": species_id,
        "surnom": "Pothos",
        "pot_l": 2,
        "date_arrosage": "01/08/2026",
        "contexte": {"emplacement": "interieur"},
        "historique_soins": [
            {"type": "arrosage", "date": "01/08/2026", "note": "Initial"}
        ],
    }


def test_generic_plant_requires_an_observation_then_dry_soil():
    pothos = profile("Epipremnum aureum")

    assert not watering_decision(pothos, None, today=date(2026, 8, 2)).can_water
    assert not watering_decision(pothos, SOIL_MOIST, today=date(2026, 8, 2)).can_water
    assert not watering_decision(pothos, SOIL_WET, today=date(2026, 8, 2)).can_water
    assert watering_decision(pothos, SOIL_DRY, today=date(2026, 8, 2)).can_water


def test_bog_species_can_be_replenished_while_still_moist():
    sarracenia = profile("Sarracenia purpurea", "Sarraceniaceae")

    policy = watering_policy(sarracenia)
    decision = watering_decision(sarracenia, SOIL_MOIST, today=date(2026, 8, 2))

    assert policy.code == "bog_or_aquatic"
    assert policy.trigger == SOIL_MOIST
    assert decision.can_water


def test_nepenthes_is_not_treated_like_a_bog_tray_plant():
    nepenthes = profile("Nepenthes alata", "Nepenthaceae")

    assert watering_policy(nepenthes).code == "aerated_carnivorous"
    assert not watering_decision(nepenthes, SOIL_MOIST, today=date(2026, 8, 2)).can_water
    assert watering_decision(nepenthes, SOIL_DRY, today=date(2026, 8, 2)).can_water


def test_succulents_and_orchids_wait_for_the_dry_level():
    aloe = profile("Aloe vera", "Asphodelaceae")
    orchid = profile("Phalaenopsis amabilis", "Orchidaceae")

    assert watering_policy(aloe).code == "dry_tolerant"
    assert watering_policy(orchid).code == "orchid_aerated"
    assert not watering_decision(aloe, SOIL_MOIST, today=date(2026, 8, 2)).can_water
    assert not watering_decision(orchid, SOIL_WET, today=date(2026, 8, 2)).can_water


def test_seasonal_rest_blocks_watering_even_when_dry():
    dormant = profile(
        "Lithops aucampiae",
        "Aizoaceae",
        water={"frequence_mode": "Aucun arrosage pendant le repos"},
    )

    decision = watering_decision(dormant, SOIL_DRY, today=date(2026, 8, 2))

    assert decision.resting
    assert not decision.can_water


def test_observation_and_validated_watering_are_persisted(tmp_path):
    database = Database(tmp_path / "collection.sqlite3")
    plant = sample_plant()
    database.save_plants([plant])
    pothos = profile("Epipremnum aureum")

    assert latest_soil_moisture(database, "plant-1").state is None

    observed = record_soil_moisture(database, "plant-1", SOIL_DRY, pothos)
    assert observed.state == SOIL_DRY
    assert not observed.watered

    watered = record_validated_watering(database, "plant-1", pothos)
    assert watered.state == SOIL_WET
    assert watered.watered

    with pytest.raises(ValueError, match="déjà été validé"):
        record_validated_watering(database, "plant-1", pothos)


def test_every_catalogue_profile_gets_a_supported_policy():
    assert len(DATABASE_PLANTES) >= 2000
    supported = {
        "catalogue_explicit",
        "bog_or_aquatic",
        "aerated_carnivorous",
        "dry_tolerant",
        "orchid_aerated",
        "evenly_moist",
        "general_container",
    }
    failures = []
    for item in DATABASE_PLANTES:
        policy = watering_policy(item)
        if policy.code not in supported or policy.trigger not in {SOIL_DRY, SOIL_MOIST}:
            failures.append(profile_id(item))

    assert not failures, f"Politiques d'humidité absentes : {failures[:20]}"

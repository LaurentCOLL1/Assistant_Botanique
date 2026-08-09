import json
from pathlib import Path

from tools.enrich_selenicereus_and_vernaculars import (
    ACCEPTED_SELENICEREUS,
    EMBRAPA_CULTIVARS,
    LITERATURE_CULTIVARS,
    UCANR_CULTIVARS,
    USDA_ARS_CULTIVARS,
    base_profile,
    generate_selenicereus,
)

ROOT = Path(__file__).resolve().parents[1]
CULTIVAR_MARKER = "Cultivar de pitaya documenté par une source horticole ou scientifique"


def test_kew_backbone_contains_33_unique_selenicereus_species():
    assert len(ACCEPTED_SELENICEREUS) == 33
    assert len(set(ACCEPTED_SELENICEREUS)) == 33
    assert "Selenicereus undatus" in ACCEPTED_SELENICEREUS
    assert "Selenicereus megalanthus" in ACCEPTED_SELENICEREUS
    assert "Selenicereus monacanthus" in ACCEPTED_SELENICEREUS
    assert "Selenicereus costaricensis" in ACCEPTED_SELENICEREUS


def test_pitaya_sources_cover_institutional_and_literature_collections():
    assert len(UCANR_CULTIVARS) == 19
    assert len(USDA_ARS_CULTIVARS) == 9
    assert len(EMBRAPA_CULTIVARS) == 5
    assert len(LITERATURE_CULTIVARS) == 19
    names = {
        cultivar
        for cultivar, _parent in (*UCANR_CULTIVARS, *EMBRAPA_CULTIVARS, *LITERATURE_CULTIVARS)
    } | set(USDA_ARS_CULTIVARS)
    assert {"Palora", "Tesoro", "American Beauty", "BRS Lua do Cerrado", "Purple Haze"} <= names


def test_generator_adds_missing_species_and_all_documented_cultivars():
    generated = generate_selenicereus({"Selenicereus undatus"})
    scientific = [profile["taxonomie"]["nom_scientifique"] for profile in generated]
    species = [name for name in scientific if "'" not in name]
    cultivar_profiles = [
        profile
        for profile in generated
        if profile.get("sante_securite", {}).get("proprietes_particulieres") == CULTIVAR_MARKER
    ]

    assert len(species) == 32
    assert len(cultivar_profiles) == 52
    assert len(scientific) == len(set(scientific))
    assert "Selenicereus megalanthus 'Palora'" in scientific
    assert "Selenicereus monacanthus 'Tesoro'" in scientific
    assert "Selenicereus undatus 'BRS Lua do Cerrado'" in scientific


def test_generated_profiles_use_cactus_substrate_and_do_not_invent_species_common_names():
    species = base_profile("Selenicereus alliodorus")
    cultivar = base_profile("Selenicereus megalanthus", cultivar="Palora")

    assert species["substrat"]["modele_recherche"] == "succulent_mineral"
    assert species["taxonomie"]["noms_vernaculaires"] == []
    assert cultivar["taxonomie"]["noms_vernaculaires"] == ["Palora"]
    roles = species["substrat"]["roles"]
    ingredients = {ingredient for role in roles for ingredient in role["ing"]}
    assert "Perlite" in ingredients
    assert abs(sum(role["ratio"] for role in roles) - 1.0) < 0.001


def test_catalogue_contains_selenicereus_in_the_single_cactaceae_file():
    canonical_path = ROOT / "familles_plantes" / "cactaceae.json"
    staging_path = ROOT / "familles_plantes" / "cactaceae_selenicereus.json"
    report_path = ROOT / "catalogue_metadata" / "vernacular_name_audit.json"

    assert canonical_path.exists()
    assert not staging_path.exists()
    assert report_path.exists()

    profiles = json.loads(canonical_path.read_text(encoding="utf-8"))
    scientific = {
        str(profile.get("taxonomie", {}).get("nom_scientifique") or "")
        for profile in profiles
    }
    base_species = {name for name in scientific if name and "'" not in name}
    cultivar_profiles = [
        profile
        for profile in profiles
        if profile.get("sante_securite", {}).get("proprietes_particulieres") == CULTIVAR_MARKER
    ]

    assert set(ACCEPTED_SELENICEREUS) <= base_species
    assert len(cultivar_profiles) == 52
    assert any(profile.get("taxonomie", {}).get("nom_scientifique") == "Selenicereus megalanthus 'Palora'" for profile in cultivar_profiles)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["selenicereus_accepted_species_target"] == 33
    assert report["pitaya_cultivars_added"] == 52
    assert report["missing_before"] == 32
    assert report["resolved"] == 23
    assert len(report["remaining_without_attested_name"]) == 9

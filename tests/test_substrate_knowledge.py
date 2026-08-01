from __future__ import annotations

from pathlib import Path

from assistant_botanique.infrastructure.catalogue import load_catalogue
from recipe_engine import build_recipe, forbidden_ingredients, substrate_variants
from substrate_knowledge import (
    CANONICAL_SET,
    canonicalize_ingredient,
    classify_profile,
    enrich_profile,
    resolved_substrate,
    validate_resolved_profile,
)

ROOT = Path(__file__).resolve().parents[1]


def profile(name: str, family: str, **extra):
    value = {
        "taxonomie": {
            "nom_scientifique": name,
            "noms_vernaculaires": [],
            "famille": family,
        },
        "substrat": {},
    }
    value.update(extra)
    return value


def test_lotus_uses_heavy_submerged_soil_and_never_perlite():
    lotus = profile("Nelumbo nucifera", "Nelumbonaceae")
    resolved = resolved_substrate(lotus)

    assert resolved["modele"] == "lotus_heavy"
    assert len(resolved["variantes"]) == 2
    assert len(resolved["variantes"][0]["sources"]) >= 5
    for variant in resolved["variantes"]:
        used = {ingredient for role in variant["roles"] for ingredient in role["ing"]}
        assert "Terreau argileux (Aquatique / Nénuphars)" in used or "Terre franche / Terre de jardin" in used
        assert "Perlite" not in used
        assert "Perlite" in variant["interdits"]


def test_actinidia_uses_only_canonical_compost_and_potting_soil_names():
    actinidia = profile("Actinidia chrysantha", "Actinidiaceae")
    resolved = resolved_substrate(actinidia)
    used = {
        ingredient
        for variant in resolved["variantes"]
        for role in variant["roles"]
        for ingredient in role["ing"]
    }

    assert resolved["modele"] == "actinidia_fruit_vine"
    assert "Compost mûr" in used
    assert "Terreau horticole" in used
    assert "Compost" not in used
    assert "Terreau" not in used


def test_legacy_aliases_are_mapped_to_the_tab_ingredients():
    assert canonicalize_ingredient("Compost / Terreau") in {"Compost mûr", "Terreau horticole"}
    assert canonicalize_ingredient("compost") == "Compost mûr"
    assert canonicalize_ingredient("terreau de qualité") == "Terreau horticole"
    assert canonicalize_ingredient("aquatic compost") == "Terreau argileux (Aquatique / Nénuphars)"
    assert canonicalize_ingredient("orchid bark") == "Écorces de pin"


def test_representative_special_groups_take_priority_over_generic_rules():
    assert classify_profile(profile("Dionaea muscipula", "Droseraceae")) == "carnivorous_bog"
    assert classify_profile(profile("Nepenthes alata", "Nepenthaceae")) == "nepenthes_epiphyte"
    assert classify_profile(profile("Drosophyllum lusitanicum", "Drosophyllaceae")) == "drosophyllum_dry"
    assert classify_profile(profile("Phalaenopsis amabilis", "Orchidaceae")) == "orchid_epiphyte"
    assert classify_profile(profile("Opuntia ficus-indica", "Cactaceae")) == "succulent_mineral"
    assert classify_profile(profile("Citrus limon", "Rutaceae")) == "citrus_loam"


def test_every_catalogue_profile_has_one_or_two_valid_sourced_variants():
    catalogue, catalogue_errors = load_catalogue(ROOT / "familles_plantes")
    assert not catalogue_errors, catalogue_errors
    assert catalogue
    for item in catalogue:
        errors = validate_resolved_profile(item)
        scientific = item.get("taxonomie", {}).get("nom_scientifique", "inconnu")
        assert not errors, f"{scientific}: {errors}"
        variants = substrate_variants(item)
        assert 1 <= len(variants) <= 2
        for variant in variants:
            assert variant["sources"]
            assert abs(sum(role["ratio"] for role in variant["roles"]) - 1.0) <= 0.001
            for role in variant["roles"]:
                assert role["ing"]
                assert set(role["ing"]).issubset(CANONICAL_SET)


def test_enrichment_is_stable_and_persists_the_primary_variant():
    original = profile("Nelumbo nucifera", "Nelumbonaceae")
    first = enrich_profile(original)
    second = enrich_profile(first)

    assert first == second
    assert first["substrat"]["modele_recherche"] == "lotus_heavy"
    assert first["roles"] == first["substrat"]["variantes"][0]["roles"]
    assert "Perlite" in first["interdits"]


def test_recipe_engine_uses_the_selected_variant_and_excludes_forbidden_stock():
    lotus = profile("Nelumbo nucifera", "Nelumbonaceae")
    stock = {ingredient: True for ingredient in CANONICAL_SET}
    result = build_recipe(lotus, 10, stock, variant_index=0)
    allocated = {ingredient for line in result.lines for ingredient, _liters in line.ingredients}

    assert result.variant_name == "Loam aquatique enrichi"
    assert "Perlite" not in allocated
    assert "Terreau argileux (Aquatique / Nénuphars)" in allocated
    assert "Perlite" in forbidden_ingredients(lotus, stock, variant_index=0)

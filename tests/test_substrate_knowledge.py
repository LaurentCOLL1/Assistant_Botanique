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
from substrate_research_2026 import RESEARCH_VERSION, SOURCES

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
    assert len(resolved["variantes"]) == 3
    assert len(resolved["variantes"][0]["sources"]) >= 5
    for variant in resolved["variantes"]:
        used = {
            ingredient
            for role in variant["roles"]
            for ingredient in role["ing"]
        }
        assert (
            "Terreau argileux (Aquatique / Nénuphars)" in used
            or "Terre franche / Terre de jardin" in used
        )
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
    assert canonicalize_ingredient("Compost / Terreau") in {
        "Compost mûr",
        "Terreau horticole",
    }
    assert canonicalize_ingredient("compost") == "Compost mûr"
    assert canonicalize_ingredient("terreau de qualité") == "Terreau horticole"
    assert (
        canonicalize_ingredient("aquatic compost")
        == "Terreau argileux (Aquatique / Nénuphars)"
    )
    assert canonicalize_ingredient("orchid bark") == "Écorces de pin"


def test_representative_special_groups_take_priority_over_generic_rules():
    expected = {
        ("Dionaea muscipula", "Droseraceae"): "carnivorous_bog",
        ("Nepenthes alata", "Nepenthaceae"): "nepenthes_epiphyte",
        ("Drosophyllum lusitanicum", "Drosophyllaceae"): "drosophyllum_dry",
        ("Phalaenopsis amabilis", "Orchidaceae"): "orchid_epiphyte",
        ("Cymbidium ensifolium", "Orchidaceae"): "orchid_terrestrial",
        ("Hoya carnosa", "Apocynaceae"): "hoya_epiphyte",
        ("Chamaedorea elegans", "Arecaceae"): "palm_container",
        ("Dracaena fragrans", "Asparagaceae"): "dracaena_dry",
        ("Tillandsia ionantha", "Bromeliaceae"): "air_plant_mount",
        ("Opuntia ficus-indica", "Cactaceae"): "succulent_mineral",
        ("Citrus limon", "Rutaceae"): "citrus_loam",
    }
    for (name, family), template in expected.items():
        assert classify_profile(profile(name, family)) == template


def test_every_catalogue_profile_has_two_or_three_valid_sourced_variants():
    catalogue, catalogue_errors = load_catalogue(ROOT / "familles_plantes")
    assert not catalogue_errors, catalogue_errors
    assert catalogue

    source_urls: set[str] = set()
    for item in catalogue:
        errors = validate_resolved_profile(item)
        scientific = item.get("taxonomie", {}).get(
            "nom_scientifique", "inconnu"
        )
        assert not errors, f"{scientific}: {errors}"
        variants = substrate_variants(item)
        assert 2 <= len(variants) <= 3
        assert variants[0]["nom"].startswith("Principale")
        for variant in variants:
            assert variant["sources"]
            source_urls.update(
                source["url"] for source in variant["sources"] if source.get("url")
            )
            assert abs(
                sum(role["ratio"] for role in variant["roles"]) - 1.0
            ) <= 0.001
            for role in variant["roles"]:
                assert role["ing"]
                assert set(role["ing"]).issubset(CANONICAL_SET)

    assert len(source_urls) >= 8


def test_primary_recipes_offer_several_compatible_ingredients_when_relevant():
    aroid = profile("Monstera deliciosa", "Araceae")
    primary = resolved_substrate(aroid)["variantes"][0]
    ingredients = {
        ingredient
        for role in primary["roles"]
        for ingredient in role["ing"]
    }
    assert {"Écorces de pin", "Terreau plantes vertes"}.issubset(ingredients)
    assert ingredients.issubset(CANONICAL_SET)


def test_research_source_registry_contains_at_least_eight_authoritative_sources():
    urls = {source["url"] for source in SOURCES.values()}
    assert len(urls) >= 8
    assert any("rhs.org.uk" in url for url in urls)
    assert any("aos.org" in url for url in urls)
    assert any("extension.umn.edu" in url for url in urls)
    assert any("plants.ces.ncsu.edu" in url for url in urls)
    assert any("extension.oregonstate.edu" in url for url in urls)


def test_enrichment_is_stable_and_persists_three_variants():
    original = profile("Nelumbo nucifera", "Nelumbonaceae")
    first = enrich_profile(original)
    second = enrich_profile(first)

    assert first == second
    assert first["substrat"]["modele_recherche"] == "lotus_heavy"
    assert first["substrat"]["version_recherche"] == RESEARCH_VERSION
    assert len(first["substrat"]["variantes"]) == 3
    assert first["roles"] == first["substrat"]["variantes"][0]["roles"]
    assert "Perlite" in first["interdits"]


def test_recipe_engine_uses_the_selected_variant_and_excludes_forbidden_stock():
    lotus = profile("Nelumbo nucifera", "Nelumbonaceae")
    stock = {ingredient: True for ingredient in CANONICAL_SET}
    result = build_recipe(lotus, 10, stock, variant_index=0)
    allocated = {
        ingredient
        for line in result.lines
        for ingredient, _liters in line.ingredients
    }

    assert result.variant_name.startswith("Principale")
    assert "Perlite" not in allocated
    assert "Terreau argileux (Aquatique / Nénuphars)" in allocated
    assert "Perlite" in forbidden_ingredients(
        lotus, stock, variant_index=0
    )


def test_old_persisted_variants_are_replaced_by_the_new_research_version():
    old = profile(
        "Monstera deliciosa",
        "Araceae",
        substrat={
            "version_recherche": "2026.08",
            "modele_recherche": "aroid_chunky",
            "variantes": [
                {
                    "nom": "Ancienne recette",
                    "roles": [
                        {
                            "nom": "Base",
                            "ratio": 1.0,
                            "ing": ["Terreau horticole"],
                        }
                    ],
                    "sources": [{"titre": "Ancienne", "url": "https://example.test"}],
                }
            ],
        },
    )
    result = resolved_substrate(old)
    assert result["version_recherche"] == RESEARCH_VERSION
    assert len(result["variantes"]) == 3
    assert result["variantes"][0]["nom"].startswith("Principale")

from __future__ import annotations

from pathlib import Path

from assistant_botanique.infrastructure.catalogue import load_catalogue
from recipe_engine import build_recipe, forbidden_ingredients, substrate_variants
from substrate_consensus_v2 import (
    DEEP_RESEARCH_SOURCES,
    MIN_RESEARCH_CORPUS,
    MIN_VARIANT_SOURCES,
    REQUESTED_CREATOR_SOURCE_IDS,
)
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


def used_ingredients(variant):
    return {ingredient for role in variant["roles"] for ingredient in role["ing"]}


def variant_signature(variant):
    return tuple(
        (
            role["nom"],
            round(float(role["ratio"]), 5),
            tuple(role["ing"]),
        )
        for role in variant["roles"]
    )


def test_research_corpus_contains_twenty_sources_and_requested_channels():
    assert len(DEEP_RESEARCH_SOURCES) >= MIN_RESEARCH_CORPUS >= 20
    assert REQUESTED_CREATOR_SOURCE_IDS.issubset(DEEP_RESEARCH_SOURCES)
    urls = {source["url"] for source in DEEP_RESEARCH_SOURCES.values()}
    assert "https://www.youtube.com/@Plantidote" in urls
    assert "https://www.youtube.com/@LesDentsdelaTerre44" in urls
    assert "https://www.youtube.com/@lesgloutonnes" in urls
    assert "https://www.youtube.com/@RusticaTV" in urls


def test_lotus_uses_heavy_submerged_soil_and_never_perlite():
    lotus = profile("Nelumbo nucifera", "Nelumbonaceae")
    resolved = resolved_substrate(lotus)

    assert resolved["modele"] == "lotus_heavy"
    assert resolved["version_recherche"] == "2026.08-consensus5"
    assert len(resolved["variantes"]) == 5
    assert resolved["variantes"][0]["nom"] == "Synthèse des quatre variantes"
    for variant in resolved["variantes"]:
        assert len({source["url"] for source in variant["sources"]}) >= MIN_VARIANT_SOURCES
        used = used_ingredients(variant)
        assert "Terreau argileux (Aquatique / Nénuphars)" in used or "Terre franche / Terre de jardin" in used
        assert "Perlite" not in used
        assert "Perlite" in variant["interdits"]


def test_synthesis_contains_every_ingredient_from_the_four_base_variants():
    resolved = resolved_substrate(profile("Philodendron hederaceum", "Araceae"))
    synthesis, *base_variants = resolved["variantes"]

    assert len(base_variants) == 4
    combined = set().union(*(used_ingredients(variant) for variant in base_variants))
    assert combined <= used_ingredients(synthesis)
    assert abs(sum(role["ratio"] for role in synthesis["roles"]) - 1.0) <= 0.001


def test_four_compositions_are_distinct_for_single_variant_templates():
    resolved = resolved_substrate(profile("Citrus limon", "Rutaceae"))
    base_variants = resolved["variantes"][1:]

    assert len(base_variants) == 4
    assert len({variant_signature(variant) for variant in base_variants}) == 4


def test_carnivorous_profiles_offer_perlite_in_multiple_compositions_and_synthesis():
    representatives = (
        profile("Dionaea muscipula", "Droseraceae"),
        profile("Nepenthes alata", "Nepenthaceae"),
        profile("Pinguicula gigantea", "Lentibulariaceae", conseil="Origine Mexique, substrat calcaire"),
        profile("Drosophyllum lusitanicum", "Drosophyllaceae"),
    )
    for item in representatives:
        variants = resolved_substrate(item)["variantes"]
        assert "Perlite" in used_ingredients(variants[0])
        assert sum("Perlite" in used_ingredients(variant) for variant in variants[1:]) >= 2


def test_perlite_is_also_available_for_other_aerated_container_groups():
    representatives = (
        profile("Phalaenopsis amabilis", "Orchidaceae"),
        profile("Opuntia ficus-indica", "Cactaceae"),
        profile("Philodendron hederaceum", "Araceae"),
        profile("Calathea orbifolia", "Marantaceae"),
        profile("Chamaedorea elegans", "Arecaceae"),
    )
    for item in representatives:
        variants = resolved_substrate(item)["variantes"]
        assert any("Perlite" in used_ingredients(variant) for variant in variants[1:])
        assert "Perlite" in used_ingredients(variants[0])


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


def test_every_catalogue_profile_has_four_compositions_plus_synthesis():
    catalogue, catalogue_errors = load_catalogue(ROOT / "familles_plantes")
    assert not catalogue_errors, catalogue_errors
    assert catalogue
    for item in catalogue:
        errors = validate_resolved_profile(item)
        scientific = item.get("taxonomie", {}).get("nom_scientifique", "inconnu")
        assert not errors, f"{scientific}: {errors}"
        variants = substrate_variants(item)
        assert len(variants) == 5
        assert variants[0]["nom"] == "Synthèse des quatre variantes"
        assert len({variant_signature(variant) for variant in variants[1:]}) == 4
        for variant in variants:
            assert len({source["url"] for source in variant["sources"]}) >= MIN_VARIANT_SOURCES
            assert variant["methode_recherche"] == "Corpus approfondi par groupe botanique"
            assert "chaînes vidéo" in variant["portee_recherche"]
            assert abs(sum(role["ratio"] for role in variant["roles"]) - 1.0) <= 0.001
            for role in variant["roles"]:
                assert role["ing"]
                assert set(role["ing"]).issubset(CANONICAL_SET)


def test_enrichment_is_stable_and_persists_the_five_choices():
    original = profile("Nelumbo nucifera", "Nelumbonaceae")
    first = enrich_profile(original)
    second = enrich_profile(first)

    assert first == second
    assert first["substrat"]["modele_recherche"] == "lotus_heavy"
    assert len(first["substrat"]["variantes"]) == 5
    assert first["substrat"]["variantes"][0]["nom"] == "Synthèse des quatre variantes"
    assert first["roles"] == first["substrat"]["variantes"][0]["roles"]
    assert "Perlite" in first["interdits"]


def test_recipe_engine_uses_the_selected_synthesis_and_excludes_forbidden_stock():
    lotus = profile("Nelumbo nucifera", "Nelumbonaceae")
    stock = {ingredient: True for ingredient in CANONICAL_SET}
    result = build_recipe(lotus, 10, stock, variant_index=0)
    allocated = {ingredient for line in result.lines for ingredient, _liters in line.ingredients}

    assert result.variant_name == "Synthèse des quatre variantes"
    assert len(result.sources) >= MIN_VARIANT_SOURCES
    assert "Perlite" not in allocated
    assert "Terreau argileux (Aquatique / Nénuphars)" in allocated
    assert "Perlite" in forbidden_ingredients(lotus, stock, variant_index=0)

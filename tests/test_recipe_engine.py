import pytest

from recipe_engine import build_recipe, normalize_roles


def test_recipe_volume_is_exact_and_legacy_names_are_canonicalized():
    profile = {
        "nom_sci": "Test",
        "roles": [
            {"nom": "Base", "ratio": 0.6, "ing": ["Coco", "Tourbe"]},
            {"nom": "Drainage", "ratio": 0.4, "ing": ["Perlite"]},
        ],
    }
    result = build_recipe(profile, 10, {"Coco": True, "Tourbe": True, "Perlite": True})
    allocated = sum(amount for line in result.lines for _, amount in line.ingredients)
    assert allocated == pytest.approx(10)
    assert result.lines[0].ingredients == (("Fibre de coco", 3.0), ("Tourbe blonde", 3.0))


def test_legacy_ratios_are_normalized_to_100_percent():
    profile = {
        "substrat": {
            "composition_ideale": "40% Tourbe blonde, 40% Perlite",
            "ingredients_recommandes": ["Tourbe blonde", "Perlite"],
        }
    }
    roles = normalize_roles(profile)
    assert sum(role["ratio"] for role in roles) == pytest.approx(1.0)

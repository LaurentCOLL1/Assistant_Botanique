from datetime import date

from assistant_botanique.ui.inventory_form_enhancements import (
    INVENTORY_CATEGORIES,
    INVENTORY_UNITS,
    format_expiry_for_display,
    merge_choice_values,
    remove_internal_substrate_lines,
)


def test_inventory_choices_are_complete_and_unique():
    assert "Engrais" in INVENTORY_CATEGORIES
    assert "Produit phytosanitaire" in INVENTORY_CATEGORIES
    assert "Substrat" in INVENTORY_CATEGORIES
    assert "Pot et contenant" in INVENTORY_CATEGORIES
    assert "Autre" in INVENTORY_CATEGORIES
    assert len(INVENTORY_CATEGORIES) == len(set(INVENTORY_CATEGORIES))

    for unit in ("unité", "g", "kg", "mL", "L", "pot", "sac"):
        assert unit in INVENTORY_UNITS
    assert len(INVENTORY_UNITS) == len(set(INVENTORY_UNITS))


def test_legacy_inventory_choice_is_preserved_once():
    assert merge_choice_values(("Engrais", "Autre"), "Produit maison") == (
        "Engrais",
        "Autre",
        "Produit maison",
    )
    assert merge_choice_values(("Engrais", "Autre"), "Engrais") == ("Engrais", "Autre")


def test_expiry_is_presented_in_french_format():
    assert format_expiry_for_display("2027-04-09") == "09/04/2027"
    assert format_expiry_for_display(date(2028, 1, 2)) == "02/01/2028"
    assert format_expiry_for_display(None) == ""


def test_internal_substrate_control_line_is_removed_only_from_display():
    source = (
        "RECETTE\n"
        "• Drainage — 20 %\n"
        "Contrôle: les ingrédients proviennent exclusivement de la liste de l'onglet Substrats.\n"
        "Avertissements: aucun"
    )
    cleaned = remove_internal_substrate_lines(source)
    assert "Contrôle:" not in cleaned
    assert "• Drainage — 20 %" in cleaned
    assert "Avertissements: aucun" in cleaned

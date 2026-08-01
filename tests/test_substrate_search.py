from tab_substrat import filter_profile_labels, normalize_profile_search


LABELS = [
    "🪴 Monstéra du salon — Monstera deliciosa — Faux philodendron",
    "🪴 Pothos doré — Epipremnum aureum — Pothos",
    "📋 Drosera capensis — Rossolis du Cap",
    "🌐 Profil plantes carnivores — Tourbière acide",
]


def test_profile_search_ignores_accents_and_case():
    assert normalize_profile_search("  MONSTÉRA  ") == "monstera"
    assert filter_profile_labels(LABELS, "monstera") == [LABELS[0]]
    assert filter_profile_labels(LABELS, "POTHOS DORÉ") == [LABELS[1]]


def test_profile_search_matches_all_terms_in_any_label_section():
    assert filter_profile_labels(LABELS, "pothos aureum") == [LABELS[1]]
    assert filter_profile_labels(LABELS, "cap drosera") == [LABELS[2]]


def test_empty_profile_search_restores_every_label():
    assert filter_profile_labels(LABELS, "") == LABELS
    assert filter_profile_labels(LABELS, "   ") == LABELS


def test_unknown_profile_search_returns_no_result():
    assert filter_profile_labels(LABELS, "orchidee vanda") == []

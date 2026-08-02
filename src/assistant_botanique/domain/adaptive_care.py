"""Moteur de recommandations adaptatives fondé sur le contexte et les observations."""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta
from typing import Any, Iterable, Mapping

from core import parse_date, water_interval

from .models import CareRecommendation

EXPOSURE_FACTORS = {
    "ombre": 1.25,
    "mi_ombre": 1.12,
    "non_renseignee": 1.0,
    "lumiere_vive": 0.90,
    "soleil_direct": 0.76,
}
POT_FACTORS = {
    "terre_cuite": 0.82,
    "terracotta": 0.82,
    "plastique": 1.10,
    "ceramique": 1.0,
    "non_renseignee": 1.0,
}
LOCATION_FACTORS = {
    "interieur": 1.0,
    "exterieur": 0.92,
    "serre": 0.82,
}


def _factor(mapping: Mapping[str, float], value: Any) -> float:
    return mapping.get(str(value or "non_renseignee").strip().casefold(), 1.0)


def _actual_watering_intervals(history: Iterable[Mapping[str, Any]]) -> list[int]:
    dates = []
    for event in history:
        if str(event.get("type", "")).casefold() != "arrosage":
            continue
        try:
            dates.append(parse_date(event.get("date")))
        except (TypeError, ValueError):
            continue
    dates = sorted(set(dates))
    return [(b - a).days for a, b in zip(dates, dates[1:]) if 1 <= (b - a).days <= 180]


def _observation_adjustment(history: Iterable[Mapping[str, Any]]) -> tuple[float, int, list[str]]:
    recent = list(history)[-20:]
    dry_types = {"substrat_sec", "controle_sec"}
    moist_types = {"substrat_humide", "encore_humide", "controle_humide"}
    wet_types = {"substrat_trempe", "controle_trempe"}
    dry = sum(1 for event in recent if event.get("type") in dry_types)
    moist = sum(1 for event in recent if event.get("type") in moist_types)
    wet = sum(1 for event in recent if event.get("type") in wet_types)
    factor = max(0.65, min(1.55, 1.0 + moist * 0.04 + wet * 0.08 - dry * 0.05))
    reasons = []
    if dry:
        reasons.append(f"{dry} contrôle(s) récent(s) indiquaient un substrat déjà sec")
    if moist:
        reasons.append(f"{moist} contrôle(s) récent(s) indiquaient un substrat encore humide")
    if wet:
        reasons.append(f"{wet} contrôle(s) récent(s) indiquaient un substrat trempé")
    return factor, dry + moist + wet, reasons


def recommend_care(
    profile: Mapping[str, Any],
    plant: Mapping[str, Any],
    *,
    today: date | None = None,
) -> CareRecommendation:
    """Calcule une date de contrôle personnalisée, jamais un ordre automatique d'arrosage."""
    current = today or date.today()
    base = water_interval(profile, current)
    if base == 0:
        return CareRecommendation(0, None, 0.85, ["repos saisonnier indiqué par la fiche botanique"])

    context = plant.get("contexte") if isinstance(plant.get("contexte"), Mapping) else {}
    factors: list[tuple[str, float]] = [
        ("exposition", _factor(EXPOSURE_FACTORS, context.get("exposition"))),
        ("matière du pot", _factor(POT_FACTORS, context.get("matiere_pot"))),
        ("emplacement", _factor(LOCATION_FACTORS, context.get("emplacement"))),
    ]

    try:
        pot_l = float(plant.get("pot_l", 1.0))
    except (TypeError, ValueError):
        pot_l = 1.0
    pot_factor = max(0.82, min(1.22, 1.0 + math.log10(max(pot_l, 0.2)) * 0.08))
    factors.append(("volume du pot", pot_factor))

    history = plant.get("historique_soins") if isinstance(plant.get("historique_soins"), list) else []
    observation_factor, observation_count, observation_reasons = _observation_adjustment(history)
    factors.append(("observations personnelles", observation_factor))

    actual_intervals = _actual_watering_intervals(history)
    learned_interval = statistics.median(actual_intervals[-8:]) if actual_intervals else None
    contextual = base
    explanations = [f"base saisonnière : {base} jours"]
    for label, factor in factors:
        contextual *= factor
        if abs(factor - 1.0) >= 0.04:
            explanations.append(f"ajustement {label} × {factor:.2f}")
    explanations.extend(observation_reasons)

    if learned_interval is not None:
        sample_weight = min(0.55, 0.12 + len(actual_intervals) * 0.06)
        interval = contextual * (1.0 - sample_weight) + learned_interval * sample_weight
        explanations.append(f"rythme observé médian : {learned_interval:.0f} jours")
    else:
        interval = contextual

    interval_days = max(1, min(120, round(interval)))
    last = parse_date(plant.get("date_arrosage"))
    known_context = sum(1 for key in ("exposition", "matiere_pot", "emplacement") if context.get(key) not in (None, "", "non_renseignee"))
    confidence = min(0.95, 0.35 + known_context * 0.08 + len(actual_intervals) * 0.055 + observation_count * 0.035)
    return CareRecommendation(interval_days, last + timedelta(days=interval_days), confidence, explanations)

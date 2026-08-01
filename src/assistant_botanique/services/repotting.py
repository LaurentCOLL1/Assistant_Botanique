"""Assistant prudent de préparation d'un rempotage.

Le service propose une taille de pot et des volumes de mélange, mais ne remplace
pas l'inspection des racines ni les exigences particulières de l'espèce.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class RepottingRecommendation:
    current_volume_l: float
    target_volume_l: float
    urgency: str
    mix_liters: tuple[tuple[str, float], ...]
    reasons: tuple[str, ...]
    cautions: tuple[str, ...]


def _substrate_components(profile: Mapping[str, Any]) -> tuple[tuple[str, float], ...]:
    substrate = profile.get("substrat") or profile.get("substrat_recommande")
    text = str(substrate or "").casefold()
    if any(marker in text for marker in ("orchid", "ecorce", "épiphy")):
        return (("écorces calibrées", 0.55), ("fibre ou sphaigne", 0.20), ("élément minéral drainant", 0.25))
    if any(marker in text for marker in ("cactus", "succulent", "mineral", "minéral")):
        return (("substrat organique tamisé", 0.30), ("pouzzolane ou pumice", 0.45), ("sable grossier ou gravier", 0.25))
    if any(marker in text for marker in ("carnivore", "tourbe", "sphaigne")):
        return (("tourbe blonde ou sphaigne adaptée", 0.70), ("perlite ou sable non calcaire", 0.30))
    if any(marker in text for marker in ("aroid", "aracée", "araceae")):
        return (("terreau fibreux", 0.45), ("écorces", 0.25), ("perlite ou pumice", 0.20), ("fibre de coco", 0.10))
    return (("terreau adapté", 0.60), ("composant drainant", 0.25), ("matière structurante", 0.15))


def recommend_repotting(
    plant: Mapping[str, Any],
    profile: Mapping[str, Any] | None = None,
    *,
    roots_crowded: bool = False,
    roots_damaged: bool = False,
    unstable: bool = False,
    growth_state: str = "normale",
    substrate_age_months: int = 0,
) -> RepottingRecommendation:
    try:
        current = float(plant.get("pot_l", 1.0))
    except (TypeError, ValueError):
        current = 1.0
    current = max(0.1, current)
    age = max(0, min(int(substrate_age_months), 240))
    growth = str(growth_state or "normale").strip().casefold()

    score = 0
    reasons: list[str] = []
    cautions: list[str] = []
    if roots_crowded:
        score += 4
        reasons.append("racines serrées ou tournant autour de la motte")
    if roots_damaged:
        score += 5
        reasons.append("racines abîmées nécessitant une inspection")
        cautions.append("Ne pas surdimensionner le pot après une perte importante de racines.")
    if unstable:
        score += 2
        reasons.append("plante instable dans son contenant")
    if age >= 24:
        score += 3
        reasons.append(f"substrat âgé d'environ {age} mois")
    elif age >= 12:
        score += 1
        reasons.append(f"substrat âgé d'environ {age} mois")
    if growth in {"rapide", "vigoureuse"}:
        score += 2
        reasons.append("croissance vigoureuse")
    elif growth in {"faible", "ralentie", "arrêtée", "arretee"}:
        score += 1
        reasons.append("croissance ralentie à contextualiser")
        cautions.append("Écarter d'abord un problème d'eau, de lumière, de température ou de ravageurs.")

    if roots_damaged:
        factor = 1.05
    elif roots_crowded and growth in {"rapide", "vigoureuse"}:
        factor = 1.45
    elif roots_crowded or unstable:
        factor = 1.30
    else:
        factor = 1.15
    target = round(max(current, current * factor), 1)
    if target - current > max(5.0, current * 0.60):
        target = round(current * 1.60, 1)
    urgency = "prioritaire" if score >= 7 else "à planifier" if score >= 4 else "à surveiller"

    components = _substrate_components(profile or {})
    usable = max(target * 0.90, 0.1)
    mix = tuple((name, round(usable * ratio, 2)) for name, ratio in components)
    cautions.extend(
        [
            "Choisir un contenant percé et vérifier le drainage avant plantation.",
            "Adapter le mélange à l'espèce et à la qualité réelle des racines.",
            "Éviter une fertilisation forte immédiatement après un rempotage stressant.",
        ]
    )
    if not reasons:
        reasons.append("aucun indicateur fort de rempotage n'a été renseigné")
    return RepottingRecommendation(
        current_volume_l=round(current, 2),
        target_volume_l=target,
        urgency=urgency,
        mix_liters=mix,
        reasons=tuple(reasons),
        cautions=tuple(dict.fromkeys(cautions)),
    )

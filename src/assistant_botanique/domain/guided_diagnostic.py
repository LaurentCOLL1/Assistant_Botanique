"""Moteur prudent de diagnostic guidé, sans prétendre confirmer une maladie."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class DiagnosticAnswers:
    affected_part: str
    symptom: str
    progression: str
    substrate: str
    pests: str
    recent_change: str


@dataclass(frozen=True, slots=True)
class DiagnosticHypothesis:
    key: str
    title: str
    score: int
    explanation: str
    actions: tuple[str, ...]


def _context(plant: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not plant:
        return {}
    value = plant.get("contexte")
    return value if isinstance(value, Mapping) else {}


def diagnose(
    answers: DiagnosticAnswers,
    plant: Mapping[str, Any] | None = None,
) -> list[DiagnosticHypothesis]:
    """Classe plusieurs causes plausibles à partir des réponses et du contexte."""
    scores = {
        "exces_eau": 0,
        "manque_eau": 0,
        "lumiere_forte": 0,
        "manque_lumiere": 0,
        "ravageurs": 0,
        "stress_recent": 0,
        "nutrition": 0,
        "infection": 0,
    }
    reasons: dict[str, list[str]] = {key: [] for key in scores}

    def add(key: str, points: int, reason: str) -> None:
        scores[key] += points
        reasons[key].append(reason)

    part = answers.affected_part.casefold()
    symptom = answers.symptom.casefold()
    progression = answers.progression.casefold()
    substrate = answers.substrate.casefold()
    pests = answers.pests.casefold()
    recent = answers.recent_change.casefold()
    context = _context(plant)
    exposure = str(context.get("exposition") or "").casefold()

    if substrate == "humide depuis longtemps":
        add("exces_eau", 6, "substrat durablement humide")
        add("infection", 2, "l'humidité persistante favorise certaines atteintes")
    elif substrate == "sec":
        add("manque_eau", 6, "substrat sec lors du contrôle")
    elif substrate == "inconnu":
        add("exces_eau", 1, "humidité non vérifiée")
        add("manque_eau", 1, "humidité non vérifiée")

    if "jauni" in symptom:
        add("exces_eau", 3, "jaunissement compatible avec un excès d'eau")
        add("nutrition", 2, "jaunissement parfois lié à une carence")
        add("manque_lumiere", 1, "faible lumière possible")
    if "brun" in symptom or "sec" in symptom:
        add("manque_eau", 3, "bords bruns ou desséchés")
        add("lumiere_forte", 2, "brûlure lumineuse possible")
    if "mou" in symptom or "pourri" in symptom:
        add("exces_eau", 5, "tissus mous ou pourris")
        add("infection", 3, "dégradation rapide des tissus")
    if "tache" in symptom:
        add("infection", 4, "taches pouvant correspondre à une atteinte foliaire")
        add("ravageurs", 1, "certains ravageurs provoquent des ponctuations")
    if "deforme" in symptom or "enroule" in symptom:
        add("ravageurs", 3, "déformation des jeunes organes")
        add("stress_recent", 2, "croissance perturbée")
    if "chute" in symptom:
        add("stress_recent", 3, "chute après changement de conditions")
        add("exces_eau", 2, "racines potentiellement asphyxiées")
        add("manque_eau", 2, "déshydratation possible")

    if pests == "oui":
        add("ravageurs", 8, "insectes, acariens ou traces observés")
    elif pests == "traces suspectes":
        add("ravageurs", 5, "traces compatibles avec des ravageurs")

    if progression == "rapide":
        add("infection", 3, "progression rapide")
        add("exces_eau", 2, "dégradation rapide possible des racines")
        add("ravageurs", 2, "population de ravageurs potentiellement active")
    elif progression == "stable":
        add("stress_recent", 1, "symptôme stable pouvant suivre un stress ponctuel")

    if recent != "aucun":
        add("stress_recent", 5, f"changement récent : {answers.recent_change}")
    if "rempot" in recent:
        add("exces_eau", 1, "substrat ou drainage possiblement modifié")
    if "deplac" in recent or "lumiere" in recent:
        add("lumiere_forte", 2, "exposition récemment augmentée")
        add("manque_lumiere", 2, "exposition récemment réduite")

    if exposure == "soleil_direct" and part in {"feuilles", "jeunes feuilles"}:
        add("lumiere_forte", 3, "exposition enregistrée au soleil direct")
    if exposure in {"ombre", "non_renseignee"} and "pale" in symptom:
        add("manque_lumiere", 3, "exposition faible ou inconnue")

    catalogue = {
        "exces_eau": (
            "Excès d'eau ou manque d'aération",
            (
                "Vérifier l'humidité en profondeur avant tout nouvel arrosage.",
                "Contrôler le drainage, les racines et l'absence d'eau stagnante.",
                "Retirer seulement les tissus manifestement pourris avec un outil propre.",
            ),
        ),
        "manque_eau": (
            "Déshydratation ou arrosage trop espacé",
            (
                "Vérifier l'humidité réelle et l'état des racines.",
                "Réhydrater progressivement si le substrat est très sec.",
                "Observer l'évolution avant de modifier durablement la fréquence.",
            ),
        ),
        "lumiere_forte": (
            "Lumière trop intense ou acclimatation insuffisante",
            (
                "Écarter temporairement la plante du soleil direct.",
                "Réintroduire une lumière plus forte progressivement.",
                "Ne pas retirer toutes les feuilles atteintes si elles restent fonctionnelles.",
            ),
        ),
        "manque_lumiere": (
            "Lumière insuffisante",
            (
                "Comparer l'emplacement aux exigences de l'espèce.",
                "Augmenter progressivement la luminosité sans soleil brutal.",
                "Surveiller l'allongement des tiges et la pâleur des nouvelles feuilles.",
            ),
        ),
        "ravageurs": (
            "Ravageurs possibles",
            (
                "Isoler la plante et inspecter le revers des feuilles, les tiges et le substrat.",
                "Photographier les traces ou organismes avant traitement.",
                "Choisir un traitement adapté uniquement après identification probable.",
            ),
        ),
        "stress_recent": (
            "Stress lié à un changement récent",
            (
                "Stabiliser l'emplacement et éviter de multiplier les corrections simultanées.",
                "Noter la date du changement et suivre les nouvelles pousses.",
                "Maintenir des conditions modérées pendant l'acclimatation.",
            ),
        ),
        "nutrition": (
            "Déséquilibre nutritif ou substrat épuisé",
            (
                "Écarter d'abord un problème d'eau, de racines ou de lumière.",
                "Vérifier la date du dernier rempotage et des fertilisations.",
                "Éviter de fertiliser une plante très stressée ou aux racines abîmées.",
            ),
        ),
        "infection": (
            "Atteinte infectieuse possible",
            (
                "Isoler la plante si les lésions progressent ou se transmettent.",
                "Éviter de mouiller le feuillage et désinfecter les outils.",
                "Demander un avis spécialisé si la progression est rapide.",
            ),
        ),
    }

    hypotheses = []
    for key, score in scores.items():
        if score <= 0:
            continue
        title, actions = catalogue[key]
        explanation = "; ".join(dict.fromkeys(reasons[key])) or "compatibilité générale avec les réponses"
        hypotheses.append(DiagnosticHypothesis(key, title, score, explanation, actions))
    hypotheses.sort(key=lambda item: (-item.score, item.title))
    return hypotheses[:4]

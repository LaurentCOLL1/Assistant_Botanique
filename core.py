"""Logique métier pure et testable de l'Assistant Botanique."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Mapping

DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d")
MONTH_KEYS = {
    1: "janvier", 2: "fevrier", 3: "mars", 4: "avril",
    5: "mai", 6: "juin", 7: "juillet", 8: "aout",
    9: "septembre", 10: "octobre", 11: "novembre", 12: "decembre",
}


class ValidationError(ValueError):
    """Erreur de saisie ou de donnée métier explicite."""


def normalize_text(value: Any) -> str:
    """Normalise casse, accents et espaces pour les recherches."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


def parse_date(value: str | date | datetime, *, allow_empty: bool = False) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw and allow_empty:
        return date.today()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"Date invalide : {raw!r}. Formats acceptés : JJ/MM/AAAA ou AAAA-MM-JJ.")


def format_date_fr(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def scientific_name(profile: Mapping[str, Any]) -> str:
    return str(
        profile.get("nom_sci")
        or profile.get("taxonomie", {}).get("nom_scientifique")
        or "Inconnu"
    ).strip()


def vernacular_names(profile: Mapping[str, Any]) -> list[str]:
    value = profile.get("nom_vern") or profile.get("taxonomie", {}).get("noms_vernaculaires", [])
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value:
        return [part.strip() for part in str(value).split(",") if part.strip()]
    return []


def family_name(profile: Mapping[str, Any]) -> str:
    return str(profile.get("famille") or profile.get("taxonomie", {}).get("famille") or "Non renseignée")


def profile_id(profile: Mapping[str, Any]) -> str:
    explicit = str(profile.get("id") or "").strip()
    if explicit:
        return explicit
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_text(scientific_name(profile))).strip("-")
    return slug or "unknown-species"


def toxicity_level(value: Any) -> str:
    """Classe la toxicité sans confondre « non toxique » avec « toxique »."""
    if isinstance(value, Mapping):
        level = normalize_text(value.get("niveau"))
        aliases = {
            "aucune": "aucune", "non toxique": "aucune", "faible": "faible",
            "moderee": "moderee", "moyenne": "moderee", "elevee": "elevee",
            "inconnue": "inconnue", "variable": "inconnue",
        }
        return aliases.get(level, "inconnue")

    text = normalize_text(value)
    if not text:
        return "inconnue"
    non_toxic_markers = (
        "non toxique", "pas toxique", "sans toxicite", "comestible",
        "inoffensif", "aucune toxicite",
    )
    if any(marker in text for marker in non_toxic_markers):
        return "aucune"
    if any(marker in text for marker in ("mortel", "hautement toxique", "tres toxique", "toxique eleve")):
        return "elevee"
    if any(marker in text for marker in ("legerement toxique", "faiblement toxique", "toxicite faible")):
        return "faible"
    if any(marker in text for marker in ("toxique", "irritant", "dangereux")):
        return "moderee"
    if any(marker in text for marker in ("legerement", "faible")):
        return "faible"
    if any(marker in text for marker in ("variable", "se renseigner", "inconnu")):
        return "inconnue"
    return "inconnue"


def water_interval(profile: Mapping[str, Any], reference_date: date) -> int:
    """Retourne un intervalle indicatif en jours pour le mois donné."""
    water = profile.get("gestion_eau", {})
    water = water if isinstance(water, Mapping) else {}
    frequency = water.get("frequence_arrosage") or profile.get("frequence_arrosage")
    if isinstance(frequency, Mapping):
        raw = frequency.get(MONTH_KEYS[reference_date.month], 7)
        try:
            interval = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Fréquence d'arrosage invalide pour {MONTH_KEYS[reference_date.month]} : {raw!r}") from exc
        if interval < 0:
            raise ValidationError("Une fréquence d'arrosage ne peut pas être négative.")
        return interval

    text = normalize_text(frequency or water.get("frequence_mode"))
    if any(marker in text for marker in ("aucun arrosage", "pas d arrosage", "stopper", "suspendre")):
        return 0
    numbers = [int(number) for number in re.findall(r"\d+", text)]
    if "semaine" in text and numbers:
        return max(1, numbers[0] * 7)
    if "mois" in text and numbers:
        return max(1, numbers[0] * 30)
    if numbers:
        return max(1, numbers[0])
    return 7 if 4 <= reference_date.month <= 9 else 14


@dataclass(frozen=True)
class WateringStatus:
    code: str
    short_label: str
    detail: str
    last_date: date
    next_check: date | None
    interval_days: int


def watering_status(last_watering: str | date, profile: Mapping[str, Any], *, today: date | None = None) -> WateringStatus:
    current = today or date.today()
    last = parse_date(last_watering)
    if last > current:
        raise ValidationError("La date du dernier arrosage ne peut pas être dans le futur.")
    interval = water_interval(profile, current)
    if interval == 0:
        return WateringStatus(
            code="REST",
            short_label="❄️ Repos au sec",
            detail="Repos saisonnier : ne pas arroser automatiquement ; surveiller seulement l'état de la plante.",
            last_date=last,
            next_check=None,
            interval_days=0,
        )
    next_check = last + timedelta(days=interval)
    remaining = (next_check - current).days
    if remaining > 0:
        return WateringStatus(
            code="OK",
            short_label=f"🟢 Contrôle dans {remaining} j",
            detail=f"Vérifier l'humidité du substrat le {format_date_fr(next_check)} avant tout arrosage.",
            last_date=last,
            next_check=next_check,
            interval_days=interval,
        )
    if remaining == 0:
        return WateringStatus(
            code="TODAY",
            short_label="🟠 Contrôle aujourd'hui",
            detail="Vérifier aujourd'hui l'humidité du substrat et l'état de la plante avant d'arroser.",
            last_date=last,
            next_check=next_check,
            interval_days=interval,
        )
    delay = abs(remaining)
    return WateringStatus(
        code="LATE",
        short_label=f"🔴 Contrôle en retard ({delay} j)",
        detail=f"Le contrôle du substrat était prévu le {format_date_fr(next_check)}. Arroser seulement si nécessaire.",
        last_date=last,
        next_check=next_check,
        interval_days=interval,
    )

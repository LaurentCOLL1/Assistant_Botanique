"""Taxonomie partagée du stock horticole."""
from __future__ import annotations

from collections.abc import Iterable

INVENTORY_CATEGORIES = (
    "Engrais",
    "Produit phytosanitaire",
    "Substrat",
    "Amendement",
    "Additif",
    "Paillage",
    "Pot et contenant",
    "Tuteur et support",
    "Outil",
    "Capteur",
    "Éclairage",
    "Irrigation",
    "Protection",
    "Consommable",
    "Autre",
)

INVENTORY_SUBCATEGORIES: dict[str, tuple[str, ...]] = {
    "Engrais": (
        "Universel", "Plantes vertes", "Floraison", "Cactées et succulentes", "Orchidées",
        "Agrumes", "Hydroponie", "Organique", "Minéral", "Biostimulant", "Autre engrais",
    ),
    "Produit phytosanitaire": (
        "Insecticide", "Fongicide", "Acaricide", "Molluscicide", "Désinfectant",
        "Piège", "Auxiliaire biologique", "Traitement naturel", "Autre traitement",
    ),
    "Substrat": (
        "Terreau universel", "Terreau plantes vertes", "Terreau semis", "Terreau horticole",
        "Terreau orchidées", "Terreau cactées et succulentes", "Terreau agrumes",
        "Terreau plantes méditerranéennes", "Terreau plantes carnivores", "Terreau aquatique",
        "Fibre de coco", "Tourbe", "Sphaigne", "Écorces", "Perlite", "Vermiculite",
        "Pouzzolane", "Pumice", "Sable", "Gravier", "Akadama", "Kanuma", "Kiryu",
        "Zéolite", "Seramis", "Argile calcinée", "Mélange personnel", "Autre substrat",
    ),
    "Amendement": (
        "Compost", "Lombricompost", "Fumier", "Chaux et dolomie", "Basalte",
        "Biochar", "Mycorhizes", "Autre amendement",
    ),
    "Additif": (
        "Charbon", "Agent mouillant", "Rétenteur d'eau", "Correcteur de pH",
        "Oligo-éléments", "Enzyme", "Autre additif",
    ),
    "Paillage": (
        "Écorces", "Pouzzolane", "Billes d'argile", "Gravier", "Fibre végétale",
        "Paillage minéral", "Autre paillage",
    ),
    "Pot et contenant": (
        "Pot plastique", "Pot terre cuite", "Pot céramique", "Pot textile", "Cache-pot",
        "Bac", "Jardinière", "Plateau", "Soucoupe", "Pot de culture", "Autre contenant",
    ),
    "Tuteur et support": (
        "Tuteur droit", "Tuteur mousse", "Treillis", "Arceau", "Attache", "Crochet",
        "Support mural", "Autre support",
    ),
    "Outil": (
        "Sécateur", "Ciseaux", "Transplantoir", "Pelle", "Griffe", "Pulvérisateur",
        "Arrosoir", "Balance", "Mesure", "Autre outil",
    ),
    "Capteur": (
        "Humidité du substrat", "Température", "Hygrométrie", "Luminosité", "pH",
        "Conductivité", "Station météo", "Autre capteur",
    ),
    "Éclairage": (
        "Lampe horticole", "Ampoule horticole", "Rampe LED", "Minuterie", "Réflecteur",
        "Support de lampe", "Autre éclairage",
    ),
    "Irrigation": (
        "Goutte-à-goutte", "Réservoir", "Pompe", "Tuyau", "Raccord", "Brumisateur",
        "Mèche", "Programmateur", "Autre irrigation",
    ),
    "Protection": (
        "Gants", "Masque", "Lunettes", "Voile", "Filet", "Housse", "Autre protection",
    ),
    "Consommable": (
        "Étiquette", "Lien", "Sac", "Filtre", "Papier pH", "Seringue", "Pipette",
        "Nettoyant", "Autre consommable",
    ),
    "Autre": ("Non classé",),
}

INVENTORY_UNITS = (
    "unité", "pièce", "pot", "sac", "sachet", "boîte", "flacon", "dose",
    "g", "kg", "mL", "cL", "L", "cm", "m", "m²", "m³",
)


def subcategories_for(category: str | None) -> tuple[str, ...]:
    category = str(category or "Autre").strip()
    return INVENTORY_SUBCATEGORIES.get(category, INVENTORY_SUBCATEGORIES["Autre"])


def merge_choice_values(standard_values: Iterable[str], current_value: str | None) -> tuple[str, ...]:
    values = list(dict.fromkeys(str(value) for value in standard_values if str(value).strip()))
    current = str(current_value or "").strip()
    if current and current not in values:
        values.append(current)
    return tuple(values)


def normalize_barcode(value: str | None) -> str:
    raw = "".join(character for character in str(value or "").strip() if character.isalnum())
    if len(raw) > 64:
        raise ValueError("Le code-barres est trop long.")
    return raw

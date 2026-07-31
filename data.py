# data.py
import os
import json
from pathlib import Path

FILE_JSON = "mes_plantes.json"
DOSSIER_FAMILLES = Path("familles_plantes")

def charger_toutes_les_familles():
    """
    Scanne le dossier 'familles_plantes' et charge tous les fichiers JSON
    pour construire la base de données globale DATABASE_PLANTES.
    Normalise automatiquement les clés nom_sci et nom_vern.
    """
    database = []
    
    if not DOSSIER_FAMILLES.exists():
        DOSSIER_FAMILLES.mkdir(parents=True, exist_ok=True)
        return database

    for fichier_json in DOSSIER_FAMILLES.glob("*.json"):
        try:
            with open(fichier_json, "r", encoding="utf-8") as f:
                plantes = json.load(f)
                if isinstance(plantes, list):
                    for p in plantes:
                        # Rétrocompatibilité automatique avec l'interface GUI
                        if "taxonomie" in p:
                            if "nom_sci" not in p:
                                p["nom_sci"] = p["taxonomie"].get("nom_scientifique", "Inconnu")
                            if "nom_vern" not in p:
                                v = p["taxonomie"].get("noms_vernaculaires", [])
                                p["nom_vern"] = ", ".join(v) if isinstance(v, list) else str(v)
                        database.append(p)
        except Exception as e:
            print(f"Erreur de lecture sur le fichier {fichier_json.name}: {e}")
            
    return database

# Chargement dynamique au lancement
DATABASE_PLANTES = charger_toutes_les_familles()

COLLECTION_INITIALE_DEFAUT = [
    {"surnom": "Mon Zamioculcas", "nom_sci": "Zamioculcas zamiifolia", "pot": "2.5"},
    {"surnom": "Mon Nepenthes", "nom_sci": "Nepenthes spp.", "pot": "2.0"},
    {"surnom": "Mon Euphorbe", "nom_sci": "Euphorbia trigona", "pot": "3.0"},
    {"surnom": "Ma Drosera Alice", "nom_sci": "Drosera aliciae", "pot": "1.0"},
    {"surnom": "Mon Mammillaria", "nom_sci": "Mammillaria spp.", "pot": "0.8"},
    {"surnom": "Ma Sensitive", "nom_sci": "Mimosa pudica", "pot": "1.5"},
    {"surnom": "Ma Sarracenia Pourpre", "nom_sci": "Sarracenia purpurea subsp. venosa", "pot": "2.0"},
    {"surnom": "Mon Aloe Vera", "nom_sci": "Aloe vera", "pot": "2.0"},
    {"surnom": "Mon Héliamphora", "nom_sci": "Heliamphora spp.", "pot": "1.5"},
    {"surnom": "Ma Sarracenia", "nom_sci": "Sarracenia spp.", "pot": "2.0"},
    {"surnom": "Ma Dionée", "nom_sci": "Dionaea muscipula", "pot": "1.2"},
    {"surnom": "Ma Drosera du Cap", "nom_sci": "Drosera capensis", "pot": "1.0"},
    {"surnom": "Mon Amaryllis", "nom_sci": "Hippeastrum spp.", "pot": "3.0"},
    {"surnom": "Mon Orchidée", "nom_sci": "Phalaenopsis spp.", "pot": "1.5"}
]

DIAGNOSTICS_DATA = {
    "Feuilles jaunissantes / Molles / Flétries": {
        "cause": "Excès d'arrosage, substrat compact asphyxiant ou mauvaise qualité d'eau.",
        "action": "1. Suspendre les arrosages immédiatement.\n2. Vérifier que le pot comporte bien un trou de drainage.\n3. Pour les plantes carnivores : utilisez EXCLUSIVEMENT de l'eau de pluie ou déminéralisée.\n4. Si le substrat sent la moisissure, rempotez d'urgence dans un substrat plus aéré."
    },
    "Feuilles / Pièges qui noircissent vite": {
        "cause": "Pourriture racinaire (fongique), choc thermique ou minéralisation trop forte du substrat.",
        "action": "1. Tailler les parties mortes avec des ciseaux désinfectés à l'alcool.\n2. Incorporez du Charbon Actif dans votre mélange pour stopper les bactéries.\n3. Augmentez la circulation d'air autour de la plante."
    },
    "Absence de colle (Drosera) ou d'urnes (Nepenthes / Sarracenia / Heliamphora)": {
        "cause": "Manque critique de luminosité ou hygrométrie trop faible.",
        "action": "1. Rapprochez la plante d'une fenêtre exposée Sud/Est ou installez une lampe horticole LED (6500K).\n2. Pour Nepenthes/Heliamphora : augmentez l'humidité ambiante (brumisation, bac à billes d'argile).\n3. Gardez le terreau constamment humide."
    },
    "Tiges étiolées / Plante qui s'allonge et pâlit": {
        "cause": "Manque de lumière directe (Étiolage).",
        "action": "1. Déplacez progressivement la plante vers un endroit plus ensoleillé.\n2. Taillez les parties trop grêles au printemps pour encourager une repousse dense."
    },
    "Présence de pucerons / Cochenilles farineuses": {
        "cause": "Attaque de parasites piqueurs (souvent favorisée par un air trop sec ou un confinement).",
        "action": "1. Isoler immédiatement la plante touchée.\n2. Nettoyer les tiges et feuilles avec un coton-tige imbibé d'alcool à 70°.\n3. Ne PAS utiliser de savon noir sur les plantes carnivores (risque de brûlure du piège)."
    },
    "Moucherons du terreau (Sciarides) autour du pot": {
        "cause": "Substrat trop détrempé et riche en matière organique en décomposition.",
        "action": "1. Laissez sécher la surface du terreau sur 1-2 cm entre deux arrosages (sauf carnivores semi-aquatiques).\n2. Saupoudrez une couche de sable grossier ou de micro-pouzzolane à la surface du pot.\n3. Posez un piège jaune collant ou utilisez des nématodes (Steinernema feltiae)."
    },
    "Dépôt blanc / Croûte calcaire sur le dessus du pot": {
        "cause": "Eau du robinet trop dure/calcaire ou accumulation de sels minéraux d'engrais.",
        "action": "1. Gratter la croûte superficielle.\n2. Rincer abondamment le substrat à l'eau déminéralisée/de pluie pour lessiver les sels.\n3. Arrêter d'utiliser l'eau du robinet."
    },
    "Moisissure blanche / Feutrage gris sur la terre (Botrytis)": {
        "cause": "Air stagnant et humidité excessive sans ventilation.",
        "action": "1. Retirez la moisissure en surface.\n2. Saupoudrez un peu de Charbon Actif ou de Farine de Basalte en surface.\n3. Améliorez la ventilation de la pièce."
    },
    "Feuilles sèches / Bords brûlés et cassants": {
        "cause": "Air ambiant trop sec, coup de chaud direct ou manque d'arrosage.",
        "action": "1. Bassinez le pot quelques minutes pour réhydrater la motte.\n2. Éloignez de la source de chaleur directe (radiateur)."
    },
    "Taches foliaires brunes/noires avec halo jaune": {
        "cause": "Infection fongique ou bactérienne.",
        "action": "1. Coupez les feuilles atteintes.\n2. Évitez de mouiller le feuillage lors des arrosages.\n3. Appliquez de la farine de basalte ou un fongicide doux."
    }
}

PROFILS_GENERIQUES = [
    {
        "nom_sci": "Lithops, Conophytum & Mesembs (Minéral Pur)",
        "nom_vern": "Lithops (Plantes-cailloux), Conophytum, Pleiospilos, Titanopsis...",
        "roles": [
            {"nom": "DRAINANT MINÉRAL EXTRÊME", "ratio": 0.90, "ing": ["Pumice", "Pouzzolane", "Sable grossier", "Akadama", "Micro-pouzzolane"]},
            {"nom": "BASE LÉGÈRE RÉTENTRICE", "ratio": 0.05, "ing": ["Fibre de coco", "Tourbe blonde"]},
            {"nom": "AMENDEMENT & STABILISATION", "ratio": 0.05, "ing": ["Charbon actif", "Zéolite"]}
        ],
        "interdits": ["Humus de lombric", "Vermiculite", "Sphaigne du Chili", "Chips de coco"],
        "conseil": "Substrat quasiment 100% minéral inerte. Arrosage quasi-nul une grande partie de l'année."
    },
    {
        "nom_sci": "Cactées Désertiques (Drainage Extrême)",
        "nom_vern": "Ariocarpus, Astrophytum, Copiapoa, Mammillaria, Echinocactus...",
        "roles": [
            {"nom": "DRAINANT MINÉRAL MASSIF", "ratio": 0.80, "ing": ["Pumice", "Pouzzolane", "Sable grossier", "Perlite", "Akadama", "Micro-pouzzolane"]},
            {"nom": "BASE AÉRÉE LÉGÈRE", "ratio": 0.15, "ing": ["Fibre de coco", "Tourbe blonde"]},
            {"nom": "AMENDEMENT MINÉRAL & PURIFICATION", "ratio": 0.05, "ing": ["Charbon actif", "Zéolite", "Farine de basalte"]}
        ],
        "interdits": ["Humus de lombric", "Vermiculite", "Sphaigne du Chili"],
        "conseil": "Mélange quasiment 100% minéral pour éviter tout risque de pourriture du collet."
    },
    {
        "nom_sci": "Caudiciformes & Succulentes à Caudex",
        "nom_vern": "Adenium (Rose du désert), Pachypodium, Stephania, Dioscorea, Euphorbia à caudex...",
        "roles": [
            {"nom": "DRAINANT STRUCTURAL LOURD", "ratio": 0.65, "ing": ["Pumice", "Pouzzolane", "Sable grossier", "Perlite", "Akadama"]},
            {"nom": "BASE NUTRITIVE AÉRÉE", "ratio": 0.30, "ing": ["Fibre de coco", "Tourbe blonde"]},
            {"nom": "NUTRITION & SANTÉ", "ratio": 0.05, "ing": ["Humus de lombric", "Charbon actif", "Farine de basalte"]}
        ],
        "interdits": ["Vermiculite"],
        "conseil": "Exige de la nutrition en période de végétation, mais un drainage parfait pour protéger le caudex."
    },
    {
        "nom_sci": "Succulentes & Crassulacées",
        "nom_vern": "Echeveria, Crassula, Aloe, Haworthia, Sansevieria, Sedum...",
        "roles": [
            {"nom": "DRAINANT MINÉRAL", "ratio": 0.55, "ing": ["Pumice", "Pouzzolane", "Sable grossier", "Perlite", "Micro-pouzzolane"]},
            {"nom": "BASE ORGANIQUE AÉRÉE", "ratio": 0.40, "ing": ["Fibre de coco", "Tourbe blonde"]},
            {"nom": "PROTECTION & SANTE", "ratio": 0.05, "ing": ["Charbon actif", "Farine de basalte"]}
        ],
        "interdits": ["Humus de lombric"],
        "conseil": "Arrosage uniquement lorsque le substrat est entièrement sec."
    },
    {
        "nom_sci": "Cactus Épiphytes & jungle",
        "nom_vern": "Schlumbergera (Cactus de Noël), Epiphyllum, Rhipsalis...",
        "roles": [
            {"nom": "BASE RETENTRICE AÉRÉE", "ratio": 0.50, "ing": ["Fibre de coco", "Sphaigne du Chili", "Tourbe blonde"]},
            {"nom": "AÉRATEUR STRUCTURANT", "ratio": 0.45, "ing": ["Écorces de pin", "Perlite", "Pumice", "Chips de coco"]},
            {"nom": "PURIFICATION", "ratio": 0.05, "ing": ["Charbon actif"]}
        ],
        "interdits": ["Sable grossier"],
        "conseil": "Ces cactus vivent dans les arbres : ils demandent de l'humidité sans eau stagnante."
    },
    {
        "nom_sci": "Carnivores Tempérées (Classique)",
        "nom_vern": "Dionaea (Attrape-mouche), Sarracenia, Drosera tempérés...",
        "roles": [
            {"nom": "BASE ACIDOPHILE RETENTRICE", "ratio": 0.65, "ing": ["Tourbe blonde", "Sphaigne du Chili"]},
            {"nom": "DRAINANT AÉRATEUR INERTE", "ratio": 0.30, "ing": ["Perlite", "Sable grossier"]},
            {"nom": "PURIFICATION", "ratio": 0.05, "ing": ["Charbon actif", "Charbon de bambou"]}
        ],
        "interdits": ["Vermiculite", "Humus de lombric", "Farine de basalte", "Akadama", "Zéolite", "Billes d'argile"],
        "conseil": "Garder les pieds dans l'eau déminéralisée en saison de pousse. Pas d'engrais."
    },
    {
        "nom_sci": "Carnivores - Nepenthes (Tropicales Épiphytes)",
        "nom_vern": "Nepenthes (Altitude & Plaine)",
        "roles": [
            {"nom": "SUPPORT FIBREUX ULTRA-AÉRÉ", "ratio": 0.50, "ing": ["Sphaigne du Chili", "Mousse de sphaigne vivante", "Chips de coco", "Écorces de pin"]},
            {"nom": "AÉRATEUR MINÉRAL INERTE", "ratio": 0.45, "ing": ["Perlite", "Pumice"]},
            {"nom": "PURIFICATION", "ratio": 0.05, "ing": ["Charbon actif"]}
        ],
        "interdits": ["Tourbe blonde", "Humus de lombric", "Vermiculite", "Farine de basalte", "Sable grossier"],
        "conseil": "Les racines de Nepenthes ont besoin d'énormément d'oxygène. Le substrat doit rester très aéré et jamais compacté."
    },
    {
        "nom_sci": "Carnivores - Heliamphora & Cephalotus",
        "nom_vern": "Heliamphora (Tepuis), Cephalotus follicularis",
        "roles": [
            {"nom": "MINÉRAL DRAINANT D'ALTITUDE", "ratio": 0.50, "ing": ["Pumice", "Perlite", "Pouzzolane"]},
            {"nom": "RÉTENTEUR D'AIR & D'EAU", "ratio": 0.45, "ing": ["Sphaigne du Chili", "Mousse de sphaigne vivante"]},
            {"nom": "PURIFICATION", "ratio": 0.05, "ing": ["Charbon actif"]}
        ],
        "interdits": ["Tourbe blonde", "Humus de lombric", "Farine de basalte", "Vermiculite"],
        "conseil": "Mélange très drainant et frais. Éviter la chaleur au niveau du substrat."
    },
    {
        "nom_sci": "Carnivores - Pinguicula Mexicaines (Grassettes)",
        "nom_vern": "Pinguicula esseriana, moranensis, ehlersiae...",
        "roles": [
            {"nom": "MINÉRAL DRAINANT PORO-CALCAIRE", "ratio": 0.70, "ing": ["Pumice", "Pouzzolane", "Perlite", "Vermiculite", "Sable grossier"]},
            {"nom": "BASE RETENTRICE LÉGÈRE", "ratio": 0.25, "ing": ["Tourbe blonde", "Fibre de coco"]},
            {"nom": "AMENDEMENT SANITAIRE", "ratio": 0.05, "ing": ["Charbon actif"]}
        ],
        "interdits": ["Humus de lombric"],
        "conseil": "Substrat majoritairement minéral. Réduire fortement les arrosages pendant la phase de rosette d'hiver."
    },
    {
        "nom_sci": "Aracées Gourmandes & Aroïdes (Aroid Mix)",
        "nom_vern": "Alocasia, Anthurium, Monstera de collection, Philodendron...",
        "roles": [
            {"nom": "AÉRATEUR GROSSIER (Structure)", "ratio": 0.45, "ing": ["Chips de coco", "Écorces de pin", "Pumice", "Perlite"]},
            {"nom": "BASE RETENTRICE FRAÎCHE", "ratio": 0.40, "ing": ["Fibre de coco", "Sphaigne du Chili", "Tourbe blonde"]},
            {"nom": "NUTRITION & PROTECTION", "ratio": 0.15, "ing": ["Humus de lombric", "Charbon actif", "Farine de basalte", "Zéolite"]}
        ],
        "interdits": ["Sable grossier"],
        "conseil": "Substrat très grossier (« Aroid Mix ») pour éviter l'asphyxie des racines épaisses."
    },
    {
        "nom_sci": "Plantes Vertes & Tropicales (Classique)",
        "nom_vern": "Monstera deliciosa, Pothos, Ficus, Syngonium, Pilea...",
        "roles": [
            {"nom": "BASE NUTRITIVE & RETENTRICE", "ratio": 0.50, "ing": ["Fibre de coco", "Tourbe blonde", "Chips de coco"]},
            {"nom": "AÉRATEUR & DRAINANT", "ratio": 0.40, "ing": ["Perlite", "Pumice", "Écorces de pin", "Pouzzolane", "Sable grossier"]},
            {"nom": "AMENDEMENT & VIE DU SOL", "ratio": 0.10, "ing": ["Humus de lombric", "Charbon actif", "Farine de basalte"]}
        ],
        "interdits": [],
        "conseil": "Arroser quand les premiers centimètres du substrat sont secs en surface."
    },
    {
        "nom_sci": "Fougères, Calatheas & Begonias",
        "nom_vern": "Calathea, Maranta, Begonia, Nephrolepis, Asplenium...",
        "roles": [
            {"nom": "BASE HUMIFÈRE & RETENTRICE", "ratio": 0.55, "ing": ["Fibre de coco", "Tourbe blonde", "Sphaigne du Chili"]},
            {"nom": "DRAINANT FIN & AÉRÉ", "ratio": 0.35, "ing": ["Perlite", "Vermiculite", "Sable grossier", "Pumice"]},
            {"nom": "AMENDEMENT DOUX", "ratio": 0.10, "ing": ["Humus de lombric", "Charbon actif"]}
        ],
        "interdits": [],
        "conseil": "Maintenir une fraîcheur constante sans gorger le pot d'eau."
    },
    {
        "nom_sci": "Orchidées Bijoux & Plantes de Terrarium",
        "nom_vern": "Macodes petola, Anoectochilus, Ludisia, Peperomia prostrata, Fittonia...",
        "roles": [
            {"nom": "BASE SPHAIGNE & FIBREUSE", "ratio": 0.60, "ing": ["Sphaigne du Chili", "Mousse de sphaigne vivante", "Fibre de coco"]},
            {"nom": "AÉRATEUR FIN", "ratio": 0.35, "ing": ["Perlite", "Pumice", "Écorces de pin"]},
            {"nom": "PURIFICATION", "ratio": 0.05, "ing": ["Charbon actif"]}
        ],
        "interdits": ["Sable grossier", "Pouzzolane"],
        "conseil": "Milieu très aéré à forte rétention d'humidité atmosphérique et racinaire."
    },
    {
        "nom_sci": "Orchidées Épiphytes",
        "nom_vern": "Phalaenopsis, Vanda, Dendrobium, Cattleya...",
        "roles": [
            {"nom": "SUPPORT GROSSIER AÉRÉ", "ratio": 0.60, "ing": ["Écorces de pin", "Chips de coco"]},
            {"nom": "RÉTENTEUR D'EAU & D'AIR", "ratio": 0.35, "ing": ["Sphaigne du Chili", "Mousse de sphaigne vivante", "Pumice", "Billes d'argile"]},
            {"nom": "PURIFICATION", "ratio": 0.05, "ing": ["Charbon actif", "Charbon de bambou"]}
        ],
        "interdits": ["Sable grossier", "Humus de lombric", "Tourbe blonde"],
        "conseil": "Oxygénation maximale des racines demandée."
    },
    {
        "nom_sci": "Orchidées Terrestres & Semi-terrestres",
        "nom_vern": "Cymbidium, Paphiopedilum (Sabot de Vénus)...",
        "roles": [
            {"nom": "BASE HUMIFÈRE RETENTRICE", "ratio": 0.45, "ing": ["Fibre de coco", "Tourbe blonde", "Sphaigne du Chili"]},
            {"nom": "DRAINANT STRUCTURANT", "ratio": 0.45, "ing": ["Écorces de pin", "Perlite", "Pumice"]},
            {"nom": "NUTRITION DOUCE", "ratio": 0.10, "ing": ["Humus de lombric", "Charbon actif"]}
        ],
        "interdits": ["Sable grossier"],
        "conseil": "Préfère un milieu plus humifère et retenant l'humidité que les orchidées épiphytes."
    },
    {
        "nom_sci": "Bonsaïs (Standard Caducs / Conifères)",
        "nom_vern": "Ficus, Érable, Ulmus, Pinus, Juniperus...",
        "roles": [
            {"nom": "MINÉRAL STRUCTURANT DRAINANT", "ratio": 0.65, "ing": ["Akadama", "Pumice", "Pouzzolane", "Kiryu"]},
            {"nom": "BASE RETENTRICE ÉQUILIBRÉE", "ratio": 0.30, "ing": ["Fibre de coco", "Tourbe blonde", "Écorces de pin"]},
            {"nom": "AMENDEMENT MINÉRAL", "ratio": 0.05, "ing": ["Charbon actif", "Farine de basalte"]}
        ],
        "interdits": ["Vermiculite"],
        "conseil": "Mélange granuleux favorisant la ramification fine des racines."
    },
    {
        "nom_sci": "Bonsaïs Acidophiles (Satsuki / Azalées)",
        "nom_vern": "Rhododendron indicum (Azalée Satsuki), Camellia...",
        "roles": [
            {"nom": "MINÉRAL EXCLUSIF ACIDOPHILE", "ratio": 0.70, "ing": ["Kanuma", "Pumice"]},
            {"nom": "BASE ACIDOPHILE RETENTRICE", "ratio": 0.25, "ing": ["Tourbe blonde", "Sphaigne du Chili"]},
            {"nom": "PROTECTION", "ratio": 0.05, "ing": ["Charbon actif"]}
        ],
        "interdits": ["Akadama", "Argile calcinée", "Billes d'argile"],
        "conseil": "Nécessite impérativement un substrat très acide (Kanuma)."
    },
    {
        "nom_sci": "Palmiers d'Intérieur & Cycadales",
        "nom_vern": "Cycas, Phoenix, Chamaedorea, Kentia, Areca, Rhapis...",
        "roles": [
            {"nom": "BASE NUTRITIVE DENSE", "ratio": 0.50, "ing": ["Fibre de coco", "Tourbe blonde"]},
            {"nom": "DRAINANT MINÉRAL STRUCTURANT", "ratio": 0.40, "ing": ["Pouzzolane", "Sable grossier", "Pumice", "Perlite"]},
            {"nom": "NUTRITION EN PROFONDEUR", "ratio": 0.10, "ing": ["Humus de lombric", "Farine de basalte", "Zéolite"]}
        ],
        "interdits": [],
        "conseil": "Utiliser un pot profond. Les racines pivotantes nécessitent un mélange lourd et bien drainé."
    },
    {
        "nom_sci": "Plantes Bulbeuses & À Tubercules",
        "nom_vern": "Amaryllis, Cyclamen, Dahlia en pot, Oxalis, Zantedeschia...",
        "roles": [
            {"nom": "BASE NUTRITIVE AÉRÉE", "ratio": 0.50, "ing": ["Fibre de coco", "Tourbe blonde", "Chips de coco"]},
            {"nom": "DRAINANT ANTI-POURRITURE", "ratio": 0.40, "ing": ["Perlite", "Sable grossier", "Pumice", "Pouzzolane"]},
            {"nom": "AMENDEMENT SANITAIRE", "ratio": 0.10, "ing": ["Humus de lombric", "Charbon actif", "Farine de basalte"]}
        ],
        "interdits": [],
        "conseil": "Le drainage est crucial pour éviter le pourrissement du bulbe pendant le repos végétatif."
    },
    {
        "nom_sci": "Plantes Méditerranéennes & Agrumes",
        "nom_vern": "Citronnier, Kumquat, Olivier, Laurier-rose, Bougainvillier...",
        "roles": [
            {"nom": "BASE STRUCTURÉE DENSE", "ratio": 0.50, "ing": ["Fibre de coco", "Tourbe blonde"]},
            {"nom": "DRAINANT LOURD MINÉRAL", "ratio": 0.40, "ing": ["Pouzzolane", "Sable grossier", "Pumice", "Micro-pouzzolane"]},
            {"nom": "NUTRITION & RÉTENTION MINÉRALE", "ratio": 0.10, "ing": ["Humus de lombric", "Farine de basalte", "Zéolite", "Charbon actif"]}
        ],
        "interdits": [],
        "conseil": "Exige un substrat lourd mais très drainant pour éviter le tassement lors de l'hivernage."
    },
    {
        "nom_sci": "Plantes Acidophiles / Terre de Bruyère",
        "nom_vern": "Azalée, Rhododendron, Hortensia, Bruyère...",
        "roles": [
            {"nom": "BASE STRICTEMENT ACIDOPHILE", "ratio": 0.60, "ing": ["Tourbe blonde", "Pépites de tourbe", "Kanuma", "Fibre de coco"]},
            {"nom": "DRAINANT AÉRÉ", "ratio": 0.35, "ing": ["Sable grossier", "Perlite", "Pumice", "Écorces de pin"]},
            {"nom": "SANTÉ & PROTECTION", "ratio": 0.05, "ing": ["Charbon actif", "Farine de basalte"]}
        ],
        "interdits": ["Argile calcinée", "Billes d'argile"],
        "conseil": "Conserver un pH bas. Arroser avec une eau non calcaire."
    },
    {
        "nom_sci": "Plantes Palustres & Semi-aquatiques",
        "nom_vern": "Cyperus (Papyrus), Equisetum, Typha, Iris de marais, Thalia...",
        "roles": [
            {"nom": "BASE DENSE HUMIFÈRE & ARGILEUSE", "ratio": 0.65, "ing": ["Fibre de coco", "Tourbe blonde", "Humus de lombric"]},
            {"nom": "RÉTENTEUR MINÉRAL & LESTAGE", "ratio": 0.30, "ing": ["Pouzzolane", "Sable grossier", "Argile calcinée"]},
            {"nom": "AMENDEMENT NUTRITIF", "ratio": 0.05, "ing": ["Farine de basalte", "Charbon actif"]}
        ],
        "interdits": ["Perlite"],
        "conseil": "Substrat devant résister à l'immersion constante ou au détrempage sans flotter."
    }
]
# Recherche sur l'humidité du substrat et la décision d'arroser

## Objectif

Le calendrier de l'application ne doit plus être interprété comme un ordre d'arroser. Il indique uniquement **quand contrôler** une plante. La décision finale repose ensuite sur l'état observé du substrat et sur les exigences de l'espèce.

L'interface utilise trois niveaux volontairement simples :

- **Sec** : le substrat ne présente plus d'humidité perceptible ;
- **Humide** : le substrat contient encore de l'eau, sans être saturé ;
- **Trempé** : le substrat est saturé ou vient d'être arrosé abondamment.

Ces niveaux ne remplacent pas une mesure scientifique en potentiel hydrique ou en teneur volumique en eau. Ils permettent une décision prudente et compréhensible sans imposer un capteur calibré.

## Principes retenus

### 1. Ne jamais arroser uniquement selon une date

Les besoins dépendent de l'espèce, de la lumière, de la température, de l'humidité de l'air, du pot et du mélange de culture. Les guides universitaires recommandent de vérifier le substrat plutôt que de suivre un calendrier fixe.

Sources :

- University of Illinois Extension — *Watering Houseplants* : https://extension.illinois.edu/houseplants/watering
- University of Connecticut Extension — *Watering Houseplants* : https://extension.uconn.edu/2013/12/24/watering-houseplants/
- University of Maryland Extension — *Watering Indoor Plants* : https://www.extension.umd.edu/resource/watering-indoor-plants
- Royal Horticultural Society — *How to grow houseplants* : https://www.rhs.org.uk/plants/types/houseplants/growing-guide

### 2. Un substrat trempé bloque toujours l'arrosage

Dans un pot ordinaire, l'eau en excès chasse l'air des pores du substrat et favorise l'asphyxie ou la pourriture racinaire. Même les plantes qui aiment l'humidité n'ont pas besoin d'un nouvel apport lorsque leur milieu est déjà saturé.

Sources :

- University of Connecticut Extension : https://extension.uconn.edu/2013/12/24/watering-houseplants/
- RHS — *How to help a poorly houseplant* : https://www.rhs.org.uk/plants/types/houseplants/how-to-help-a-poorly-houseplant

### 3. Plantes succulentes et xérophytes : attendre le niveau sec

Les cactus, Crassulaceae, Aizoaceae, Agave, Aloe, Haworthia, Lithops et autres plantes stockant l'eau supportent le dessèchement et sont particulièrement vulnérables à un substrat humide prolongé. Le bouton d'arrosage n'est donc disponible qu'au niveau **Sec**, hors repos saisonnier.

Source :

- RHS — *How to grow cacti and succulent houseplants* : https://www.rhs.org.uk/plants/types/cacti-succulents/houseplants/growing-guide/

### 4. Plantes de tourbière, palustres ou aquatiques : intervenir avant le dessèchement

Les Sarracenia, Dionaea, de nombreux Drosera et plusieurs plantes aquatiques vivent dans des milieux durablement mouillés. Pour ces groupes, le niveau **Humide** peut déjà justifier un réapprovisionnement en eau afin d'éviter que le milieu ne sèche complètement. Le niveau **Trempé** bloque néanmoins un nouvel apport immédiat.

Sources :

- RHS — *Carnivorous plants* : https://www.rhs.org.uk/plants/types/carnivorous
- RHS — *How to grow carnivorous plants* : https://www.rhs.org.uk/plants/types/carnivorous/growing-guide

Les Nepenthes et Cephalotus sont exclus de cette règle de soucoupe permanente : leur substrat doit rester aéré et ne pas être saturé.

### 5. Plantes appréciant une humidité régulière : humide signifie encore suffisamment arrosé

Les fougères, Marantaceae, Begoniaceae et autres plantes sensibles au dessèchement apprécient un substrat humide mais non détrempé. Avec seulement trois niveaux, **Humide** correspond à leur zone correcte : l'arrosage est conseillé dès que le niveau devient **Sec**.

Sources :

- RHS — *How to grow ferns* : https://www.rhs.org.uk/plants/types/ferns/growing-guide
- RHS — *Tender ferns — houseplants* : https://www.rhs.org.uk/plants/types/ferns/tender-ferns-houseplants

### 6. Orchidées épiphytes : privilégier l'air autour des racines

Les orchidées cultivées en écorces peuvent demander une humidité régulière, mais leurs racines pourrissent dans un milieu détrempé. Le niveau simplifié retenu est donc **Sec**, avec un texte précisant qu'il correspond à un substrat aéré presque sec plutôt qu'à une dessiccation prolongée.

Sources :

- RHS — *Moth orchids (Phalaenopsis)* : https://www.rhs.org.uk/plants/phalaenopsis
- RHS — *Phalaenopsis details* : https://www.rhs.org.uk/plants/12596/phalaenopsis/details

## Couverture du catalogue

Le moteur examine chaque fiche dans l'ordre suivant :

1. seuil d'humidité explicite déjà présent dans la fiche ;
2. vocabulaire horticole de la section `gestion_eau` et du reste de la fiche ;
3. genre et famille botanique pour les groupes bien documentés ;
4. règle prudente générale pour les plantes en pot.

Ainsi, chaque fiche du catalogue reçoit toujours une politique parmi :

- `catalogue_explicit` ;
- `bog_or_aquatic` ;
- `aerated_carnivorous` ;
- `dry_tolerant` ;
- `orchid_aerated` ;
- `evenly_moist` ;
- `general_container`.

Un test d'audit parcourt l'intégralité du catalogue à chaque exécution de la CI et échoue si une fiche ne reçoit pas de politique valide.

## Limites et prudence

- Une observation tactile reste subjective ; un capteur doit être calibré pour le substrat utilisé.
- Le moteur bloque l'arrosage pendant un repos saisonnier explicitement indiqué par la fiche.
- L'utilisateur conserve la décision finale : le système formule un conseil et ne déclenche jamais une pompe ou un arrosage automatique.
- Une plante flétrie dans un substrat humide ou trempé peut souffrir d'un problème racinaire ; ajouter de l'eau serait alors contre-productif.

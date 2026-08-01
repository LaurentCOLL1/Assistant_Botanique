# Atelier avancé — Assistant Botanique 3.1

Cette évolution ajoute un atelier unique afin de ne pas multiplier les onglets principaux.

## Fonctions

- **Étiquettes QR** : génération d'une feuille HTML A4 imprimable. Le QR ouvre le compagnon local lorsqu'il est actif, sinon il contient un lien applicatif local.
- **Actions groupées sécurisées** : sélection multiple, prévisualisation, confirmation et journal d'annulation.
- **Historique d'annulation** : restauration des arrosages groupés, des ajustements de stock, des créations de boutures, des protocoles et des révisions taxonomiques locales.
- **Boutures et généalogie** : plante mère, méthode, date, enracinement, état et lien facultatif vers une plante fille.
- **Stock horticole** : produits, catégories, unités, seuils d'alerte, expiration et mouvements.
- **Protocoles de traitement** : étapes datées, progression, consommation facultative du produit et journalisation du soin.
- **Notifications intelligentes** : plusieurs heures, heures silencieuses, regroupement par emplacement, priorité et report de 24 heures.
- **Météo facultative** : recherche de lieu et prévisions Open-Meteo. Les résultats produisent uniquement des points de vigilance.
- **Capteurs** : sources locales, mesures manuelles, import CSV et endpoint HTTP protégé par un jeton propre au capteur.
- **Compagnon web local** : lecture de la collection et actions rapides depuis un téléphone. Le serveur reste sur `127.0.0.1` par défaut ; le mode LAN exige une confirmation.
- **Mise à jour botanique différentielle** : comparaison GBIF, proposition, rejet ou application comme révision locale `a_verifier`.

## Sécurité

- aucune ouverture LAN par défaut ;
- jeton d'accès aléatoire pour le compagnon ;
- jeton distinct par capteur ;
- liste fermée d'actions autorisées depuis le web ;
- limite de taille des requêtes ;
- aucune modification taxonomique silencieuse ;
- aucune décision automatique d'arrosage ou de traitement ;
- confirmation avant toute action groupée ou application d'une proposition GBIF.

## Import de capteurs

CSV UTF-8 avec au minimum :

```csv
source_id,value,recorded_at,unit
identifiant-du-capteur,54.2,2026-08-01T15:30:00,%
```

Les colonnes commençant par `meta_` sont conservées dans les métadonnées de la mesure.

## API locale

Une fois le compagnon démarré :

- `GET /api/plants?token=...`
- `GET /api/sensors?token=...`
- `POST /api/care?token=...`
- `POST /api/sensor/<source_id>` avec un JSON contenant `token` et `value`

Le mode réseau local doit uniquement être utilisé sur un réseau privé de confiance.

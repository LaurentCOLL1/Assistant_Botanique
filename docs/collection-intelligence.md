# Collection & analyse — Assistant Botanique 3.2

Le nouvel onglet **Collection & analyse**, disponible en mode avancé, complète l'atelier existant.

## Fonctions

- **Plan des emplacements** : arborescence maison, pièces, fenêtres, étagères, serre ou jardin. L'affectation met également à jour l'emplacement historique de la plante afin que les filtres et notifications existants restent cohérents.
- **Suivi des infestations** : incident, ravageur suspecté, gravité, plantes atteintes ou exposées, observations successives et clôture.
- **Assistant de rempotage** : estimation prudente du volume du prochain pot et des volumes indicatifs de mélange à partir du pot actuel, des racines, de la stabilité, de la croissance et de l'âge du substrat.
- **Moteur de règles personnalisées** : conditions sur les capteurs, les infestations, les emplacements et l'ancienneté de l'arrosage. Une règle peut uniquement créer une alerte ou une tâche ; elle ne réalise jamais un soin automatiquement.
- **Comparateur photographique** : page locale avec superposition réglable et vue côte à côte de deux photos.
- **Synchronisation chiffrée** : snapshots complets `.absync` placés dans un dossier choisi par l'utilisateur, par exemple OneDrive, Dropbox, Syncthing ou un dossier réseau. Le mot de passe n'est jamais enregistré.
- **Accessibilité renforcée** : taille du texte, contraste, focus clavier et réduction des changements automatiques.
- **Architecture d'extensions** : dossier local `plugins`, manifeste `plugin.json`, API versionnée et activation explicite avant tout chargement de code.

## Photos depuis un téléphone

1. Sur l'ordinateur, ouvrir **Atelier avancé → QR & compagnon**.
2. Cliquer sur **Activer sur le réseau local** et confirmer uniquement sur un réseau privé de confiance.
3. Ouvrir l'adresse affichée depuis le téléphone connecté à la même box Internet ou au même réseau Wi-Fi.
4. Choisir une plante, toucher **Prendre une photo**, prendre ou sélectionner l'image, puis l'envoyer.
5. La photo est vérifiée, réorientée, compressée si nécessaire, stockée dans le dossier de données de l'ordinateur et ajoutée à la chronologie SQLite de la plante.

Formats acceptés : JPEG, PNG et WebP, avec une limite de 12 Mo par envoi. Le lien contient un jeton secret ; il ne doit pas être partagé hors du réseau de confiance.

## Synchronisation chiffrée

La synchronisation utilise des snapshots complets plutôt qu'une fusion silencieuse :

- **Envoyer un snapshot** crée une archive `.botanique`, puis la chiffre avec une clé dérivée du mot de passe ;
- **Restaurer le plus récent** vérifie le mot de passe et l'intégrité, crée une copie de sécurité locale, puis restaure l'archive ;
- l'utilisateur doit redémarrer l'application après une restauration.

Ce fonctionnement évite les fusions automatiques ambiguës entre deux ordinateurs. Un seul appareil doit écrire à la fois dans le dossier synchronisé.

## Extensions

Chaque extension se trouve dans un sous-dossier de `plugins` :

```text
plugins/
└── mon-extension/
    ├── plugin.json
    └── plugin.py
```

Exemple de manifeste :

```json
{
  "id": "exemple.extension",
  "name": "Extension exemple",
  "version": "1.0",
  "api_version": 1,
  "entrypoint": "plugin.py"
}
```

Le module doit exposer `register(api)`. Une extension est du code Python local : elle doit uniquement être activée si son origine est connue et son contenu a été vérifié.

## Contrôles du jour

**Outils → Afficher les contrôles du jour** est désormais une consultation manuelle. Elle affiche toujours une fenêtre :

- elle ignore le réglage d'activation des notifications automatiques ;
- elle ignore les heures silencieuses et les reports ;
- elle indique explicitement lorsqu'aucun contrôle ou soin n'est arrivé à échéance.

Les notifications de fond continuent, elles, à respecter les réglages, les heures silencieuses et les reports.

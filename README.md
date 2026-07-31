# Assistant Botanique

Application de bureau Python/Tkinter pour gérer une collection de plantes, consulter un catalogue botanique, préparer des recettes de substrat et enregistrer les soins.

## Nouveautés de la version 2

- chaque exemplaire de plante possède un UUID indépendant de son surnom ;
- les données personnelles sont enregistrées hors du dépôt, dans le dossier utilisateur du système ;
- les sauvegardes JSON sont atomiques et une copie `.backup` est conservée ;
- l'ancien `mes_plantes.json` est migré automatiquement au premier lancement ;
- les dates et volumes sont validés explicitement ;
- les rappels indiquent de **contrôler le substrat**, plutôt que d'ordonner un arrosage automatique ;
- chaque plante conserve un historique d'arrosages, rempotages, tailles, engrais et observations ;
- le catalogue dispose d'une recherche sans accents, de filtres famille/toxicité et d'une traçabilité des données ;
- « Non toxique » n'est plus interprété comme toxique ;
- le générateur de substrat répartit clairement les volumes et normalise les ratios ;
- export de la collection en CSV et des contrôles en iCalendar ;
- thèmes clair et sombre, fenêtre responsive et géométrie mémorisée ;
- schémas JSON, audit du catalogue, tests automatisés et GitHub Actions.

## Prérequis

- Python 3.11 ou plus récent ;
- Tkinter, généralement inclus avec Python sous Windows et macOS.

Sous Debian/Ubuntu :

```bash
sudo apt install python3-tk
```

## Lancement

```bash
python main.py
```

Le catalogue est lu depuis `familles_plantes/`. La collection et les réglages sont enregistrés dans :

- Windows : `%APPDATA%/AssistantBotanique/`
- macOS : `~/Library/Application Support/AssistantBotanique/`
- Linux : `$XDG_DATA_HOME/AssistantBotanique/` ou `~/.local/share/AssistantBotanique/`

Pour les tests, il est possible d'isoler les données :

```bash
ASSISTANT_BOTANIQUE_DATA_DIR=/chemin/temporaire python main.py
```

## Développement

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff check .
python validate_data.py
```

Le mode strict de l'audit échoue en cas d'anomalie structurelle :

```bash
python validate_data.py --strict
```

## Structure

```text
app_paths.py          chemins portables
app_data.py           chargement et normalisation du catalogue
core.py               logique métier pure
storage.py            migration et sauvegarde atomique
recipe_engine.py      calcul des recettes de substrat
main.py               fenêtre principale
tab_*.py              onglets Tkinter
schemas/              schémas JSON
validate_data.py      audit des fiches botaniques
tests/                tests unitaires
```

## Qualité des données botaniques

Les fiches historiques restent compatibles. Le nouveau format accepte également :

- `id` stable par espèce ;
- `metadata.sources`, `metadata.last_reviewed` et `metadata.confidence` ;
- une toxicité structurée avec un niveau normalisé ;
- des rôles de substrat structurés avec ratios et ingrédients ;
- une séparation entre ingrédients interdits et conditions de culture à éviter.

L'audit signale les mois manquants, fréquences invalides, identifiants dupliqués, ratios incohérents, sources absentes, coquilles probables et blocs de contenu répétés.

## Avertissement

Les calendriers d'arrosage sont des rappels indicatifs. La décision d'arroser doit tenir compte de l'humidité réelle du substrat, du pot, de la température, de la lumière, de l'hygrométrie et de l'état de la plante. Les diagnostics sont des orientations et ne remplacent pas une expertise phytosanitaire.

## Licence

MIT — voir [LICENSE](LICENSE).

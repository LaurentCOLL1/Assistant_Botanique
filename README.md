# Assistant Botanique 3

Application de bureau Python/Tkinter pour gérer une collection de plantes, apprendre leur rythme réel de soins, documenter leur évolution par des photos et réviser un catalogue botanique sourcé.

## Nouveautés de la version 3

### Soins adaptatifs

Le calendrier combine désormais la fréquence saisonnière de l'espèce avec l'exposition, l'emplacement, la matière et le volume du pot, puis apprend à partir des contrôles « substrat sec », « encore humide » et des intervalles réellement observés. Il propose toujours un **contrôle**, jamais un arrosage automatique.

### Validation botanique

Un onglet de révision permet de modifier une fiche, associer plusieurs sources, choisir un niveau de confiance et suivre les statuts `brouillon`, `à vérifier`, `validé` ou `rejeté`. Les révisions locales surchargent le catalogue sans modifier les fichiers historiques.

### Installation Windows et mises à jour

Le workflow `Release Windows` construit un exécutable PyInstaller puis un installateur Inno Setup. Une release GitHub créée avec un tag `v*` reçoit automatiquement l'installateur. L'application peut vérifier volontairement la dernière release publiée.

### Notifications natives

Les contrôles arrivés à échéance peuvent être affichés via les notifications du système. Sous Windows, l'application peut installer une tâche planifiée quotidienne, ou l'installateur peut l'activer à 09:00.

### Photos et chronologie

Chaque plante peut recevoir des photos et des légendes. La chronologie réunit soins, observations et images. Les photos restent dans le dossier de données local et ne sont jamais envoyées automatiquement.

### SQLite

La collection, les événements, les photos et les révisions sont stockés dans SQLite avec transactions, clés étrangères, index, mode WAL et migration automatique depuis l'ancien JSON.

### Sauvegarde complète

Une archive `.botanique` contient la base, les réglages, les photos et les révisions. Chaque fichier est contrôlé avec SHA-256 avant restauration. Une copie de sécurité des données existantes est conservée.

### Architecture

Le nouveau code métier est organisé dans `src/assistant_botanique/` :

```text
src/assistant_botanique/
├── domain/          moteur adaptatif et modèles
├── infrastructure/ SQLite, catalogue, réglages
├── services/        photos, sauvegardes, notifications, mises à jour
└── ui/              fenêtre et onglets version 3
```

Les modules historiques à la racine restent disponibles comme façades de compatibilité pendant la migration progressive.

## Prérequis et lancement

- Python 3.11 ou plus récent ;
- Tkinter ;
- Pillow et Plyer, installés automatiquement avec le projet.

```bash
python -m pip install -e .
assistant-botanique
```

Le lancement historique reste disponible :

```bash
python main.py
```

Afficher uniquement les notifications arrivées à échéance :

```bash
assistant-botanique --notify
```

## Données locales

- Windows : `%APPDATA%/AssistantBotanique/`
- macOS : `~/Library/Application Support/AssistantBotanique/`
- Linux : `$XDG_DATA_HOME/AssistantBotanique/` ou `~/.local/share/AssistantBotanique/`

Le dossier contient notamment :

```text
assistant_botanique.sqlite3
settings.json
photos/
catalogue_overrides/
backups/
```

Pour isoler les données pendant les tests :

```bash
ASSISTANT_BOTANIQUE_DATA_DIR=/chemin/temporaire python main.py
```

## Développement

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff check .
python validate_data.py --strict
```

La CI exécute les tests sous Windows et Linux avec Python 3.11 et 3.13.

## Construire l'installateur Windows

Le plus simple est de déclencher le workflow `Release Windows`. Localement, avec PyInstaller et Inno Setup :

```powershell
pyinstaller --noconfirm --clean --windowed --name AssistantBotanique `
  --collect-all plyer --collect-all PIL `
  --add-data "familles_plantes;familles_plantes" `
  --add-data "data.py;." --add-data "schemas;schemas" main.py
iscc installer/AssistantBotanique.iss
```

## Avertissement horticole

Les recommandations dépendent de données génériques et d'observations personnelles. Vérifiez toujours l'humidité réelle du substrat, l'état des racines et les conditions locales avant d'arroser ou de traiter une plante.

## Licence

MIT.

# Assistant Botanique 3

Application de bureau Python/Tkinter pour gérer une collection de plantes, apprendre leur rythme réel de soins, documenter leur évolution par des photos et réviser un catalogue botanique sourcé.

## Installation Windows en un seul copier-coller

Cette procédure fonctionne sous **Windows 10 ou Windows 11** avec une connexion Internet. Elle ne nécessite ni Git ni téléchargement manuel du dépôt.

1. Fermez Assistant Botanique s'il est déjà ouvert.
2. Ouvrez le menu **Démarrer**, recherchez **PowerShell**, puis lancez-le normalement. Les droits administrateur ne sont pas nécessaires.
3. Copiez la totalité du bloc ci-dessous, collez-le dans PowerShell et appuyez sur **Entrée**.

```powershell
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryArchive = "https://github.com/LaurentCOLL1/Assistant_Botanique/archive/refs/heads/main.zip"
$InstallDirectory = Join-Path $env:LOCALAPPDATA "Programs\AssistantBotanique"
$TemporaryDirectory = Join-Path $env:TEMP ("AssistantBotanique-" + [guid]::NewGuid().ToString("N"))
$ArchiveFile = "$TemporaryDirectory.zip"
$PythonVersion = $null
$PythonExecutable = $null

function Test-PythonLauncherVersion {
    param([Parameter(Mandatory = $true)][string]$Version)

    & py "-$Version" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    return $LASTEXITCODE -eq 0
}

Write-Host "Installation d'Assistant Botanique..." -ForegroundColor Cyan

# Recherche d'une installation Python compatible.
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($Candidate in @("3.14", "3.13", "3.12", "3.11")) {
        if (Test-PythonLauncherVersion -Version $Candidate) {
            $PythonVersion = $Candidate
            break
        }
    }
}

# Installation automatique de Python 3.11 si nécessaire.
if (-not $PythonVersion) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Python 3.11 ou plus récent est absent et Winget est indisponible. Installez d'abord « App Installer » depuis le Microsoft Store, puis relancez ce bloc."
    }

    Write-Host "Installation de Python 3.11..." -ForegroundColor Yellow
    winget install --exact --id Python.Python.3.11 --scope user `
        --accept-package-agreements --accept-source-agreements `
        --silent --disable-interactivity

    if ($LASTEXITCODE -ne 0) {
        throw "L'installation automatique de Python a échoué."
    }

    $PythonExecutable = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
    if (-not (Test-Path $PythonExecutable)) {
        $PythonExecutable = Get-ChildItem `
            -Path (Join-Path $env:LOCALAPPDATA "Programs\Python") `
            -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1 -ExpandProperty FullName
    }

    if (-not $PythonExecutable -or -not (Test-Path $PythonExecutable)) {
        throw "Python a été installé, mais son exécutable est introuvable. Fermez PowerShell, rouvrez-le et relancez ce bloc."
    }
}

# Téléchargement propre de la version actuelle.
New-Item -ItemType Directory -Path $TemporaryDirectory -Force | Out-Null
Write-Host "Téléchargement du programme..." -ForegroundColor Yellow
Invoke-WebRequest -Uri $RepositoryArchive -OutFile $ArchiveFile
Expand-Archive -Path $ArchiveFile -DestinationPath $TemporaryDirectory -Force

$ExtractedDirectory = Join-Path $TemporaryDirectory "Assistant_Botanique-main"
if (-not (Test-Path $ExtractedDirectory)) {
    throw "Le contenu téléchargé est incomplet."
}

# Remplacement du programme uniquement. Les données personnelles restent dans
# %APPDATA%\AssistantBotanique et ne sont donc pas supprimées lors d'une mise à jour.
if (Test-Path $InstallDirectory) {
    Remove-Item -Path $InstallDirectory -Recurse -Force
}
New-Item -ItemType Directory -Path (Split-Path $InstallDirectory -Parent) -Force | Out-Null
Move-Item -Path $ExtractedDirectory -Destination $InstallDirectory

# Création d'un environnement Python isolé.
$VirtualEnvironment = Join-Path $InstallDirectory ".venv"
if ($PythonVersion) {
    & py "-$PythonVersion" -m venv $VirtualEnvironment
}
else {
    & $PythonExecutable -m venv $VirtualEnvironment
}

$ApplicationPython = Join-Path $VirtualEnvironment "Scripts\python.exe"
$ApplicationPythonW = Join-Path $VirtualEnvironment "Scripts\pythonw.exe"

Write-Host "Installation des composants..." -ForegroundColor Yellow
& $ApplicationPython -m pip install --upgrade pip
& $ApplicationPython -m pip install -e $InstallDirectory

if ($LASTEXITCODE -ne 0) {
    throw "L'installation des composants Python a échoué."
}

# Création des raccourcis Bureau et menu Démarrer.
$Shell = New-Object -ComObject WScript.Shell
$ShortcutPaths = @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Assistant Botanique.lnk"),
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Assistant Botanique.lnk")
)

foreach ($ShortcutPath in $ShortcutPaths) {
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $ApplicationPythonW
    $Shortcut.Arguments = "-m assistant_botanique"
    $Shortcut.WorkingDirectory = $InstallDirectory
    $Shortcut.Description = "Assistant Botanique"
    $Shortcut.Save()
}

# Activation du contrôle quotidien à 09:00. Cette étape n'empêche pas
# l'installation de réussir si le Planificateur de tâches est indisponible.
& $ApplicationPython -m assistant_botanique --install-notifications "09:00"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Le programme est installé, mais le rappel quotidien n'a pas pu être créé."
}

# Nettoyage et premier lancement.
Remove-Item -Path $TemporaryDirectory -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path $ArchiveFile -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Installation terminée." -ForegroundColor Green
Write-Host "Un raccourci « Assistant Botanique » a été ajouté au Bureau et au menu Démarrer."
Write-Host "Pour mettre le programme à jour plus tard, fermez-le puis réexécutez exactement ce même bloc."
Start-Process -FilePath $ApplicationPythonW -ArgumentList "-m assistant_botanique" -WorkingDirectory $InstallDirectory
```

Le programme est installé dans :

`%LOCALAPPDATA%\Programs\AssistantBotanique`

Les données personnelles restent séparées dans :

`%APPDATA%\AssistantBotanique`

Réexécuter le même bloc met à jour le programme sans supprimer la collection, les photos, les sauvegardes ou les réglages.

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

## Installation manuelle et lancement

Prérequis :

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
python validate_data.py --strict --baseline data_quality_baseline.json
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

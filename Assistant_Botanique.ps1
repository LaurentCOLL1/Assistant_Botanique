# On se positionne dans le dossier où se trouve ce script .ps1
Set-Location -Path $PSScriptRoot

# On lance main.py
python main.py

# Pause facultative pour voir les messages de console avant fermeture
Read-Host -Prompt "Appuyez sur Entrée pour fermer"
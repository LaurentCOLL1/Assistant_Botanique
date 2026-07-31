& {
    $ErrorActionPreference = "Stop"
    Set-StrictMode -Version Latest

    [Net.ServicePointManager]::SecurityProtocol = `
        [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $RepositoryArchive = "https://github.com/LaurentCOLL1/Assistant_Botanique/archive/refs/heads/main.zip"
    $DefaultInstallDirectory = Join-Path $env:LOCALAPPDATA "Programs\AssistantBotanique"
    $DataDirectory = Join-Path $env:APPDATA "AssistantBotanique"
    $TemporaryDirectory = Join-Path $env:TEMP ("AssistantBotanique-" + [guid]::NewGuid().ToString("N"))
    $ArchiveFile = "$TemporaryDirectory.zip"

    $InstallDirectory = $null
    $BackupDirectory = $null
    $NewInstallPlaced = $false
    $InstallationSucceeded = $false

    function Get-NormalizedPath {
        param([Parameter(Mandatory = $true)][string]$Path)

        return ([System.IO.Path]::GetFullPath($Path)).TrimEnd([char[]]"\/")
    }

    function Test-SupportedPython {
        param([Parameter(Mandatory = $true)][string]$Executable)

        if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
            return $false
        }

        & $Executable -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3, 11), (3, 12), (3, 13)) else 1)" *> $null
        $ExitCode = $LASTEXITCODE
        return [bool]($ExitCode -eq 0)
    }

    function Find-SupportedPython {
        $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($null -ne $Launcher) {
            foreach ($Version in @("3.13", "3.12", "3.11")) {
                $Output = & $Launcher.Source "-$Version" -c "import sys; print(sys.executable)" 2>$null
                $ExitCode = $LASTEXITCODE

                if ($ExitCode -eq 0 -and $null -ne $Output) {
                    $Executable = ([string]($Output | Select-Object -Last 1)).Trim()
                    if (Test-SupportedPython -Executable $Executable) {
                        return $Executable
                    }
                }
            }
        }

        foreach ($CommandName in @("python.exe", "python3.exe")) {
            $Command = Get-Command $CommandName -ErrorAction SilentlyContinue
            if ($null -ne $Command -and (Test-SupportedPython -Executable $Command.Source)) {
                return $Command.Source
            }
        }

        $KnownRoots = @(
            (Join-Path $env:LOCALAPPDATA "Programs\Python"),
            (Join-Path $env:ProgramFiles "Python")
        )

        foreach ($Root in $KnownRoots) {
            if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
                continue
            }

            $Executables = Get-ChildItem -LiteralPath $Root -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending

            foreach ($Executable in $Executables) {
                if (Test-SupportedPython -Executable $Executable.FullName) {
                    return $Executable.FullName
                }
            }
        }

        return $null
    }

    function Select-InstallDirectory {
        param(
            [Parameter(Mandatory = $true)][string]$DefaultPath,
            [Parameter(Mandatory = $true)][string]$ProtectedDataPath
        )

        Write-Host ""
        Write-Host "Choisissez le mode d'installation :" -ForegroundColor Cyan
        Write-Host "  1 - Installation standard" -ForegroundColor White
        Write-Host "      $DefaultPath" -ForegroundColor DarkGray
        Write-Host "  2 - Emplacement personnalise" -ForegroundColor White
        Write-Host "      Exemple : E:\AssistantBotanique" -ForegroundColor DarkGray

        $Choice = Read-Host "Votre choix [1]"
        if ([string]::IsNullOrWhiteSpace($Choice)) {
            $Choice = "1"
        }

        if ($Choice.Trim() -eq "1") {
            return [System.IO.Path]::GetFullPath($DefaultPath)
        }

        if ($Choice.Trim() -ne "2") {
            throw "Choix invalide. Relancez l'installation et selectionnez 1 ou 2."
        }

        while ($true) {
            $CustomPath = Read-Host "Saisissez le chemin complet d'installation"
            if ([string]::IsNullOrWhiteSpace($CustomPath)) {
                Write-Warning "Le chemin ne peut pas etre vide."
                continue
            }

            $ExpandedPath = [Environment]::ExpandEnvironmentVariables($CustomPath.Trim().Trim('"'))
            if (-not [System.IO.Path]::IsPathRooted($ExpandedPath)) {
                Write-Warning "Utilisez un chemin absolu, par exemple E:\AssistantBotanique."
                continue
            }

            try {
                $FullPath = [System.IO.Path]::GetFullPath($ExpandedPath)
                $DriveRoot = [System.IO.Path]::GetPathRoot($FullPath)
                $NormalizedPath = Get-NormalizedPath -Path $FullPath
                $NormalizedRoot = Get-NormalizedPath -Path $DriveRoot
                $NormalizedData = Get-NormalizedPath -Path $ProtectedDataPath
            }
            catch {
                Write-Warning "Ce chemin n'est pas valide."
                continue
            }

            if (-not $DriveRoot -or -not (Test-Path -LiteralPath $DriveRoot)) {
                Write-Warning "Le lecteur choisi n'est pas disponible : $DriveRoot"
                continue
            }

            if ($NormalizedPath.Equals($NormalizedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
                Write-Warning "Choisissez un dossier sur le lecteur, pas sa racine. Exemple : $DriveRoot`AssistantBotanique"
                continue
            }

            $Separator = [System.IO.Path]::DirectorySeparatorChar
            $InstallPrefix = $NormalizedPath + $Separator
            $DataPrefix = $NormalizedData + $Separator

            $ConflictsWithData = `
                $NormalizedPath.Equals($NormalizedData, [System.StringComparison]::OrdinalIgnoreCase) -or `
                $NormalizedPath.StartsWith($DataPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or `
                $NormalizedData.StartsWith($InstallPrefix, [System.StringComparison]::OrdinalIgnoreCase)

            if ($ConflictsWithData) {
                Write-Warning "Ce chemin chevauche le dossier des donnees personnelles. Choisissez un autre emplacement."
                continue
            }

            return $FullPath
        }
    }

    function Confirm-ExistingDirectoryReplacement {
        param([Parameter(Mandatory = $true)][string]$Path)

        if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
            return
        }

        $Items = Get-ChildItem -LiteralPath $Path -Force -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $Items) {
            return
        }

        $LooksLikeAssistantBotanique = `
            (Test-Path -LiteralPath (Join-Path $Path "pyproject.toml") -PathType Leaf) -and `
            (Test-Path -LiteralPath (Join-Path $Path "src\assistant_botanique") -PathType Container)

        if ($LooksLikeAssistantBotanique) {
            return
        }

        Write-Warning "Le dossier existe et ne semble pas etre une installation d'Assistant Botanique : $Path"
        $Confirmation = Read-Host "Tapez REMPLACER pour autoriser son remplacement"
        if ($Confirmation -cne "REMPLACER") {
            throw "Installation annulee afin de proteger le contenu du dossier."
        }
    }

    try {
        Write-Host "Installation d'Assistant Botanique..." -ForegroundColor Cyan

        $InstallDirectory = Select-InstallDirectory `
            -DefaultPath $DefaultInstallDirectory `
            -ProtectedDataPath $DataDirectory

        Confirm-ExistingDirectoryReplacement -Path $InstallDirectory
        Write-Host "Installation choisie : $InstallDirectory" -ForegroundColor Green

        $PythonExecutable = Find-SupportedPython
        if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
            $Winget = Get-Command winget.exe -ErrorAction SilentlyContinue
            if ($null -eq $Winget) {
                throw "Python 3.11 a 3.13 est absent et Winget est indisponible. Installez App Installer depuis le Microsoft Store, puis relancez l'installation."
            }

            Write-Host "Installation de Python 3.11..." -ForegroundColor Yellow
            & $Winget.Source install --exact --id Python.Python.3.11 --scope user `
                --accept-package-agreements --accept-source-agreements `
                --silent --disable-interactivity
            $WingetExitCode = $LASTEXITCODE

            $PythonExecutable = Find-SupportedPython
            if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
                $ExpectedPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
                if (Test-SupportedPython -Executable $ExpectedPython) {
                    $PythonExecutable = $ExpectedPython
                }
            }

            if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
                throw "L'installation de Python a echoue ou son executable est introuvable (code Winget : $WingetExitCode)."
            }
        }

        $PythonDescription = & $PythonExecutable -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
        if ($LASTEXITCODE -ne 0) {
            throw "Impossible d'utiliser Python : $PythonExecutable"
        }
        Write-Host "Python detecte : $PythonDescription" -ForegroundColor Green

        New-Item -ItemType Directory -Path $TemporaryDirectory -Force | Out-Null
        Write-Host "Telechargement du programme..." -ForegroundColor Yellow
        Invoke-WebRequest -UseBasicParsing -Uri $RepositoryArchive -OutFile $ArchiveFile
        Expand-Archive -Path $ArchiveFile -DestinationPath $TemporaryDirectory -Force

        $ExtractedDirectory = Join-Path $TemporaryDirectory "Assistant_Botanique-main"
        if (-not (Test-Path -LiteralPath $ExtractedDirectory -PathType Container)) {
            throw "Le contenu telecharge est incomplet."
        }

        $InstallParent = Split-Path $InstallDirectory -Parent
        New-Item -ItemType Directory -Path $InstallParent -Force | Out-Null

        if (Test-Path -LiteralPath $InstallDirectory) {
            $BackupDirectory = "$InstallDirectory.previous-$([guid]::NewGuid().ToString('N'))"
            Write-Host "Mise en securite de l'installation existante..." -ForegroundColor Yellow
            Move-Item -LiteralPath $InstallDirectory -Destination $BackupDirectory
        }

        Move-Item -LiteralPath $ExtractedDirectory -Destination $InstallDirectory
        $NewInstallPlaced = $true

        $VirtualEnvironment = Join-Path $InstallDirectory ".venv"
        $ApplicationPython = Join-Path $VirtualEnvironment "Scripts\python.exe"
        $ApplicationPythonW = Join-Path $VirtualEnvironment "Scripts\pythonw.exe"

        Write-Host "Creation de l'environnement Python isole..." -ForegroundColor Yellow
        & $PythonExecutable -m venv $VirtualEnvironment
        $VenvExitCode = $LASTEXITCODE
        if ($VenvExitCode -ne 0 -or -not (Test-Path -LiteralPath $ApplicationPython -PathType Leaf)) {
            throw "La creation de l'environnement Python a echoue (code : $VenvExitCode)."
        }

        Write-Host "Installation des composants..." -ForegroundColor Yellow
        & $ApplicationPython -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            throw "La mise a jour de pip a echoue."
        }

        & $ApplicationPython -m pip install -e $InstallDirectory
        if ($LASTEXITCODE -ne 0) {
            throw "L'installation des composants Python a echoue."
        }

        & $ApplicationPython -c "import assistant_botanique"
        if ($LASTEXITCODE -ne 0) {
            throw "La verification finale de l'application a echoue."
        }

        $Shell = New-Object -ComObject WScript.Shell
        $StartMenuDirectory = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
        New-Item -ItemType Directory -Path $StartMenuDirectory -Force | Out-Null

        $ShortcutPaths = @(
            (Join-Path ([Environment]::GetFolderPath("Desktop")) "Assistant Botanique.lnk"),
            (Join-Path $StartMenuDirectory "Assistant Botanique.lnk")
        )

        foreach ($ShortcutPath in $ShortcutPaths) {
            $Shortcut = $Shell.CreateShortcut($ShortcutPath)
            $Shortcut.TargetPath = $ApplicationPythonW
            $Shortcut.Arguments = "-m assistant_botanique"
            $Shortcut.WorkingDirectory = $InstallDirectory
            $Shortcut.Description = "Assistant Botanique"
            $Shortcut.Save()
        }

        & $ApplicationPython -m assistant_botanique --install-notifications "09:00"
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Le programme est installe, mais le rappel quotidien de 09:00 n'a pas pu etre cree."
        }

        $InstallationSucceeded = $true

        if ($null -ne $BackupDirectory -and (Test-Path -LiteralPath $BackupDirectory)) {
            try {
                Remove-Item -LiteralPath $BackupDirectory -Recurse -Force
            }
            catch {
                Write-Warning "L'ancienne installation n'a pas pu etre supprimee : $BackupDirectory"
            }
        }

        Write-Host ""
        Write-Host "Installation terminee dans : $InstallDirectory" -ForegroundColor Green
        Write-Host "Les raccourcis Bureau et menu Demarrer ont ete crees."
        Write-Host "Pour mettre a jour le programme, relancez la commande du README et choisissez le meme dossier."

        Start-Process -FilePath $ApplicationPythonW `
            -ArgumentList "-m assistant_botanique" `
            -WorkingDirectory $InstallDirectory
    }
    catch {
        Write-Host ""
        Write-Host "ECHEC DE L'INSTALLATION : $($_.Exception.Message)" -ForegroundColor Red

        if ($NewInstallPlaced -and $null -ne $InstallDirectory -and (Test-Path -LiteralPath $InstallDirectory)) {
            Remove-Item -LiteralPath $InstallDirectory -Recurse -Force -ErrorAction SilentlyContinue
        }

        if ($null -ne $BackupDirectory -and (Test-Path -LiteralPath $BackupDirectory)) {
            try {
                Move-Item -LiteralPath $BackupDirectory -Destination $InstallDirectory
                Write-Host "L'installation precedente a ete restauree." -ForegroundColor Yellow
            }
            catch {
                Write-Warning "La restauration automatique a echoue. Copie de securite : $BackupDirectory"
            }
        }

        throw
    }
    finally {
        Remove-Item -LiteralPath $TemporaryDirectory -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $ArchiveFile -Force -ErrorAction SilentlyContinue
    }
}
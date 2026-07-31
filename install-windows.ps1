param(
    [switch]$SelfTest
)

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
$InstallContentTouched = $false
$ExitCode = 0
$Stage = "initialisation"

function Quote-NativeArgument {
    param([Parameter(Mandatory = $true)][string]$Value)

    if ($Value.Contains('"')) {
        throw "Un argument contient un guillemet non pris en charge : $Value"
    }

    return '"' + $Value + '"'
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string]$Arguments
    )

    $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $FilePath
    $StartInfo.Arguments = $Arguments
    $StartInfo.UseShellExecute = $false
    $StartInfo.CreateNoWindow = $true
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true

    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $StartInfo

    try {
        if (-not $Process.Start()) {
            throw "Impossible de demarrer : $FilePath"
        }

        $StandardOutputTask = $Process.StandardOutput.ReadToEndAsync()
        $StandardErrorTask = $Process.StandardError.ReadToEndAsync()
        $Process.WaitForExit()

        return [pscustomobject]@{
            ExitCode = $Process.ExitCode
            StdOut = $StandardOutputTask.Result
            StdErr = $StandardErrorTask.Result
        }
    }
    finally {
        $Process.Dispose()
    }
}

function Write-NativeResult {
    param([Parameter(Mandatory = $true)]$Result)

    if (-not [string]::IsNullOrWhiteSpace($Result.StdOut)) {
        Write-Host $Result.StdOut.TrimEnd()
    }

    if (-not [string]::IsNullOrWhiteSpace($Result.StdErr)) {
        Write-Host $Result.StdErr.TrimEnd() -ForegroundColor DarkGray
    }
}

function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage,
        [switch]$ShowOutput
    )

    $Result = Invoke-NativeCommand -FilePath $FilePath -Arguments $Arguments
    if ($ShowOutput) {
        Write-NativeResult -Result $Result
    }

    if ($Result.ExitCode -ne 0) {
        $Detail = $Result.StdErr.Trim()
        if ([string]::IsNullOrWhiteSpace($Detail)) {
            $Detail = $Result.StdOut.Trim()
        }

        if ([string]::IsNullOrWhiteSpace($Detail)) {
            throw "$FailureMessage (code : $($Result.ExitCode))."
        }

        throw "$FailureMessage (code : $($Result.ExitCode)). $Detail"
    }

    return $Result
}

function Get-NormalizedPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    return ([System.IO.Path]::GetFullPath($Path)).TrimEnd([char[]]"\/")
}

function Test-SupportedPython {
    param([Parameter(Mandatory = $true)][string]$Executable)

    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        return $false
    }

    try {
        $Arguments = '-c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12), (3, 13)) else 1)"'
        $Result = Invoke-NativeCommand -FilePath $Executable -Arguments $Arguments
        return [bool]($Result.ExitCode -eq 0)
    }
    catch {
        return $false
    }
}

function Find-SupportedPython {
    $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($null -ne $Launcher) {
        foreach ($Version in @("3.13", "3.12", "3.11")) {
            $Arguments = "-$Version -c `"import sys; print(sys.executable)`""
            $Result = Invoke-NativeCommand -FilePath $Launcher.Source -Arguments $Arguments

            if ($Result.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($Result.StdOut)) {
                continue
            }

            $Executable = $Result.StdOut.Trim()
            if (Test-SupportedPython -Executable $Executable) {
                return $Executable
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
        return Get-NormalizedPath -Path $DefaultPath
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
            $FullPath = Get-NormalizedPath -Path $ExpandedPath
            $DriveRoot = [System.IO.Path]::GetPathRoot($FullPath)
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

        if ($FullPath.Equals($NormalizedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            Write-Warning "Choisissez un dossier sur le lecteur, pas sa racine. Exemple : $DriveRoot`AssistantBotanique"
            continue
        }

        $Separator = [System.IO.Path]::DirectorySeparatorChar
        $InstallPrefix = $FullPath + $Separator
        $DataPrefix = $NormalizedData + $Separator

        $ConflictsWithData = `
            $FullPath.Equals($NormalizedData, [System.StringComparison]::OrdinalIgnoreCase) -or `
            $FullPath.StartsWith($DataPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or `
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

if ($SelfTest) {
    $DetectedPython = Find-SupportedPython
    if ([string]::IsNullOrWhiteSpace($DetectedPython)) {
        throw "Auto-test en echec : aucun Python 3.11, 3.12 ou 3.13 detecte."
    }

    $Tar = Get-Command tar.exe -ErrorAction SilentlyContinue
    if ($null -eq $Tar) {
        throw "Auto-test en echec : tar.exe est introuvable."
    }

    Write-Host "Auto-test reussi. Python : $DetectedPython ; extraction : $($Tar.Source)" -ForegroundColor Green
    exit 0
}

try {
    Write-Host "Installation d'Assistant Botanique..." -ForegroundColor Cyan

    $Stage = "choix du dossier"
    $InstallDirectory = Select-InstallDirectory `
        -DefaultPath $DefaultInstallDirectory `
        -ProtectedDataPath $DataDirectory

    Confirm-ExistingDirectoryReplacement -Path $InstallDirectory
    Write-Host "Installation choisie : $InstallDirectory" -ForegroundColor Green

    $Stage = "detection de Python"
    $PythonExecutable = Find-SupportedPython
    if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
        $Winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if ($null -eq $Winget) {
            throw "Python 3.11 a 3.13 est absent et Winget est indisponible. Installez App Installer depuis le Microsoft Store, puis relancez l'installation."
        }

        Write-Host "Installation de Python 3.11..." -ForegroundColor Yellow
        $WingetArguments = "install --exact --id Python.Python.3.11 --scope user --accept-package-agreements --accept-source-agreements --silent --disable-interactivity"
        $WingetResult = Invoke-NativeCommand -FilePath $Winget.Source -Arguments $WingetArguments
        Write-NativeResult -Result $WingetResult

        $PythonExecutable = Find-SupportedPython
        if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
            $ExpectedPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
            if (Test-SupportedPython -Executable $ExpectedPython) {
                $PythonExecutable = $ExpectedPython
            }
        }

        if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
            throw "L'installation de Python a echoue ou son executable est introuvable (code Winget : $($WingetResult.ExitCode))."
        }
    }

    $VersionResult = Invoke-NativeChecked `
        -FilePath $PythonExecutable `
        -Arguments '-c "import sys; print(\"{}.{}.{}\".format(*sys.version_info[:3]))"' `
        -FailureMessage "Impossible d'utiliser Python"

    $PythonDescription = $VersionResult.StdOut.Trim()
    Write-Host "Python detecte : $PythonDescription" -ForegroundColor Green

    $Stage = "telechargement"
    New-Item -ItemType Directory -Path $TemporaryDirectory -Force | Out-Null
    Write-Host "Telechargement du programme..." -ForegroundColor Yellow
    Invoke-WebRequest -UseBasicParsing -Uri $RepositoryArchive -OutFile $ArchiveFile

    if (-not (Test-Path -LiteralPath $ArchiveFile -PathType Leaf)) {
        throw "L'archive telechargee est introuvable."
    }

    $Stage = "extraction de l'archive"
    $Tar = Get-Command tar.exe -ErrorAction SilentlyContinue
    if ($null -eq $Tar) {
        throw "tar.exe est introuvable. Windows 10 ou Windows 11 est requis pour l'extraction automatique."
    }

    Write-Host "Extraction du programme..." -ForegroundColor Yellow
    $TarArguments = "-xf $(Quote-NativeArgument -Value $ArchiveFile) -C $(Quote-NativeArgument -Value $TemporaryDirectory)"
    Invoke-NativeChecked `
        -FilePath $Tar.Source `
        -Arguments $TarArguments `
        -FailureMessage "L'extraction de l'archive a echoue" `
        -ShowOutput | Out-Null

    $ExtractedDirectory = Join-Path $TemporaryDirectory "Assistant_Botanique-main"
    if (-not (Test-Path -LiteralPath $ExtractedDirectory -PathType Container)) {
        $ExtractedDirectory = Get-ChildItem -LiteralPath $TemporaryDirectory -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "pyproject.toml") -PathType Leaf } |
            Select-Object -First 1 -ExpandProperty FullName
    }

    if ([string]::IsNullOrWhiteSpace($ExtractedDirectory) -or -not (Test-Path -LiteralPath $ExtractedDirectory -PathType Container)) {
        throw "Le contenu extrait est incomplet."
    }

    $Stage = "remplacement du programme"
    $InstallParent = Split-Path -Path $InstallDirectory -Parent
    if ([string]::IsNullOrWhiteSpace($InstallParent)) {
        throw "Le dossier parent de l'installation est invalide : $InstallDirectory"
    }

    New-Item -ItemType Directory -Path $InstallParent -Force | Out-Null

    if (Test-Path -LiteralPath $InstallDirectory) {
        $BackupDirectory = "$InstallDirectory.previous-$([guid]::NewGuid().ToString('N'))"
        Write-Host "Mise en securite de l'installation existante..." -ForegroundColor Yellow
        Move-Item -LiteralPath $InstallDirectory -Destination $BackupDirectory
    }

    $InstallContentTouched = $true
    Move-Item -LiteralPath $ExtractedDirectory -Destination $InstallDirectory

    $VirtualEnvironment = Join-Path $InstallDirectory ".venv"
    $ApplicationPython = Join-Path $VirtualEnvironment "Scripts\python.exe"
    $ApplicationPythonW = Join-Path $VirtualEnvironment "Scripts\pythonw.exe"

    $Stage = "creation de l'environnement Python"
    Write-Host "Creation de l'environnement Python isole..." -ForegroundColor Yellow
    $VenvArguments = "-m venv $(Quote-NativeArgument -Value $VirtualEnvironment)"
    Invoke-NativeChecked `
        -FilePath $PythonExecutable `
        -Arguments $VenvArguments `
        -FailureMessage "La creation de l'environnement Python a echoue" `
        -ShowOutput | Out-Null

    if (-not (Test-Path -LiteralPath $ApplicationPython -PathType Leaf)) {
        throw "La creation de l'environnement Python n'a pas produit python.exe."
    }

    $Stage = "installation des composants"
    Write-Host "Installation des composants..." -ForegroundColor Yellow
    Invoke-NativeChecked `
        -FilePath $ApplicationPython `
        -Arguments "-m pip install --upgrade pip --disable-pip-version-check" `
        -FailureMessage "La mise a jour de pip a echoue" `
        -ShowOutput | Out-Null

    $InstallArguments = "-m pip install --disable-pip-version-check -e $(Quote-NativeArgument -Value $InstallDirectory)"
    Invoke-NativeChecked `
        -FilePath $ApplicationPython `
        -Arguments $InstallArguments `
        -FailureMessage "L'installation des composants Python a echoue" `
        -ShowOutput | Out-Null

    $Stage = "verification de l'application"
    Invoke-NativeChecked `
        -FilePath $ApplicationPython `
        -Arguments '-c "import assistant_botanique, tkinter, PIL, plyer"' `
        -FailureMessage "La verification finale de l'application a echoue" | Out-Null

    $Stage = "creation des raccourcis"
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

    $Stage = "activation des notifications"
    $NotificationResult = Invoke-NativeCommand `
        -FilePath $ApplicationPython `
        -Arguments '-m assistant_botanique --install-notifications "09:00"'

    if ($NotificationResult.ExitCode -ne 0) {
        Write-Warning "Le programme est installe, mais le rappel quotidien de 09:00 n'a pas pu etre cree."
        Write-NativeResult -Result $NotificationResult
    }

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

    $Stage = "premier lancement"
    try {
        Start-Process -FilePath $ApplicationPythonW `
            -ArgumentList "-m assistant_botanique" `
            -WorkingDirectory $InstallDirectory
    }
    catch {
        Write-Warning "L'application est installee, mais son lancement automatique a echoue. Utilisez le raccourci du Bureau."
    }
}
catch {
    $ExitCode = 1
    Write-Host ""
    Write-Host "ECHEC DE L'INSTALLATION pendant l'etape '$Stage' : $($_.Exception.Message)" -ForegroundColor Red

    if ($null -ne $BackupDirectory -and (Test-Path -LiteralPath $BackupDirectory)) {
        if ($null -ne $InstallDirectory -and (Test-Path -LiteralPath $InstallDirectory)) {
            Remove-Item -LiteralPath $InstallDirectory -Recurse -Force -ErrorAction SilentlyContinue
        }

        try {
            Move-Item -LiteralPath $BackupDirectory -Destination $InstallDirectory
            Write-Host "L'installation precedente a ete restauree." -ForegroundColor Yellow
        }
        catch {
            Write-Warning "La restauration automatique a echoue. Copie de securite : $BackupDirectory"
        }
    }
    elseif ($InstallContentTouched -and $null -ne $InstallDirectory -and (Test-Path -LiteralPath $InstallDirectory)) {
        Remove-Item -LiteralPath $InstallDirectory -Recurse -Force -ErrorAction SilentlyContinue
    }
}
finally {
    Remove-Item -LiteralPath $TemporaryDirectory -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ArchiveFile -Force -ErrorAction SilentlyContinue
}

exit $ExitCode
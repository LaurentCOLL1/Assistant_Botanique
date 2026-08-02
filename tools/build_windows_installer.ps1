param(
    [Parameter(Mandatory = $true)][string]$DisplayVersion,
    [Parameter(Mandatory = $true)][string]$OutputBaseFilename,
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepositoryRoot

try {
    & pyinstaller `
        --noconfirm `
        --clean `
        --windowed `
        --name AssistantBotanique `
        --collect-all plyer `
        --collect-all PIL `
        --collect-all zxingcpp `
        --add-data "familles_plantes;familles_plantes" `
        --add-data "catalogue_metadata;catalogue_metadata" `
        --add-data "data.py;." `
        --add-data "schemas;schemas" `
        main.py
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller a échoué avec le code $LASTEXITCODE."
    }

    $IsccCommand = Get-Command iscc.exe -ErrorAction SilentlyContinue
    $IsccPath = if ($null -ne $IsccCommand) { $IsccCommand.Source } else { $null }
    if ([string]::IsNullOrWhiteSpace($IsccPath)) {
        $Candidates = @(
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
        )
        foreach ($Candidate in $Candidates) {
            if ([System.IO.File]::Exists($Candidate)) {
                $IsccPath = $Candidate
                break
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($IsccPath)) {
        throw "ISCC.exe est introuvable. Installez Inno Setup 6."
    }

    & $IsccPath `
        "/DMyAppVersion=$DisplayVersion" `
        "/DMyAppOutputBaseFilename=$OutputBaseFilename" `
        "installer/AssistantBotanique.iss"
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup a échoué avec le code $LASTEXITCODE."
    }

    $Installer = Join-Path $RepositoryRoot "installer\output\$OutputBaseFilename.exe"
    if (-not [System.IO.File]::Exists($Installer)) {
        throw "L'installateur attendu est introuvable : $Installer"
    }

    if ($SmokeTest) {
        $InstallDirectory = Join-Path $env:RUNNER_TEMP "AssistantBotanique-installer-smoke"
        if ([System.IO.Directory]::Exists($InstallDirectory)) {
            [System.IO.Directory]::Delete($InstallDirectory, $true)
        }

        $SetupArguments = @(
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/DIR=$InstallDirectory",
            "/MERGETASKS=!desktopicon,!notifications"
        )
        $SetupProcess = Start-Process -FilePath $Installer -ArgumentList $SetupArguments -Wait -PassThru
        if ($SetupProcess.ExitCode -ne 0) {
            throw "L'installation silencieuse a échoué avec le code $($SetupProcess.ExitCode)."
        }

        $Application = Join-Path $InstallDirectory "AssistantBotanique.exe"
        if (-not [System.IO.File]::Exists($Application)) {
            throw "L'exécutable installé est introuvable : $Application"
        }

        $VersionProcess = Start-Process -FilePath $Application -ArgumentList "--version" -Wait -PassThru
        if ($VersionProcess.ExitCode -ne 0) {
            throw "L'exécutable installé n'a pas validé --version (code $($VersionProcess.ExitCode))."
        }

        $Uninstaller = Join-Path $InstallDirectory "unins000.exe"
        if (-not [System.IO.File]::Exists($Uninstaller)) {
            throw "Le désinstalleur de test est introuvable."
        }
        $UninstallProcess = Start-Process `
            -FilePath $Uninstaller `
            -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") `
            -Wait `
            -PassThru
        if ($UninstallProcess.ExitCode -ne 0) {
            throw "La désinstallation de test a échoué avec le code $($UninstallProcess.ExitCode)."
        }
    }

    Write-Output $Installer
}
finally {
    Pop-Location
}

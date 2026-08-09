param(
    [Parameter(Mandatory = $true)][string]$DisplayVersion,
    [Parameter(Mandatory = $true)][string]$OutputBaseFilename,
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-ProcessWithTimeout {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)][string]$Description
    )

    $StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $StartInfo.FileName = $FilePath
    $StartInfo.UseShellExecute = $false
    foreach ($Argument in $ArgumentList) {
        $StartInfo.ArgumentList.Add($Argument)
    }

    $Process = [System.Diagnostics.Process]::new()
    $Process.StartInfo = $StartInfo
    try {
        if (-not $Process.Start()) {
            throw "$Description n'a pas démarré."
        }
        if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
            $Process.Kill($true)
            throw "$Description a dépassé le délai de $TimeoutSeconds secondes."
        }
        if ($Process.ExitCode -ne 0) {
            throw "$Description a échoué avec le code $($Process.ExitCode)."
        }
    }
    finally {
        $Process.Dispose()
    }
}

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepositoryRoot

try {
    $GeneratedIconDirectory = Join-Path $RepositoryRoot "installer\generated"
    & python tools/generate_app_icon.py --output-dir $GeneratedIconDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "La génération de l'icône a échoué avec le code $LASTEXITCODE."
    }
    $GeneratedIcon = Join-Path $GeneratedIconDirectory "assistant_botanique.ico"
    if (-not [System.IO.File]::Exists($GeneratedIcon)) {
        throw "L'icône générée est introuvable : $GeneratedIcon"
    }

    & pyinstaller `
        --noconfirm `
        --clean `
        --windowed `
        --name AssistantBotanique `
        --icon $GeneratedIcon `
        --paths src `
        --collect-all plyer `
        --collect-all PIL `
        --collect-all zxingcpp `
        --add-data "familles_plantes;familles_plantes" `
        --add-data "catalogue_metadata;catalogue_metadata" `
        --add-data "data.py;." `
        --add-data "schemas;schemas" `
        --add-data "assets;assets" `
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

        Invoke-ProcessWithTimeout `
            -FilePath $Installer `
            -ArgumentList @(
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                "/DIR=$InstallDirectory",
                "/MERGETASKS=!desktopicon,!notifications"
            ) `
            -TimeoutSeconds 180 `
            -Description "L'installation silencieuse"

        $Application = Join-Path $InstallDirectory "AssistantBotanique.exe"
        if (-not [System.IO.File]::Exists($Application)) {
            throw "L'exécutable installé est introuvable : $Application"
        }

        Invoke-ProcessWithTimeout `
            -FilePath $Application `
            -ArgumentList @("--version") `
            -TimeoutSeconds 60 `
            -Description "La vérification de l'exécutable installé"

        $Uninstaller = Join-Path $InstallDirectory "unins000.exe"
        if (-not [System.IO.File]::Exists($Uninstaller)) {
            throw "Le désinstalleur de test est introuvable."
        }
        Invoke-ProcessWithTimeout `
            -FilePath $Uninstaller `
            -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") `
            -TimeoutSeconds 120 `
            -Description "La désinstallation de test"
    }

    Write-Output $Installer
}
finally {
    Pop-Location
}

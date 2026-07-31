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
$TemporaryWorkDirectory = Join-Path $env:TEMP ("AssistantBotanique-" + [guid]::NewGuid().ToString("N"))
$ArchiveFile = Join-Path $TemporaryWorkDirectory "AssistantBotanique.zip"

$InstallDirectory = $null
$InstallParent = $null
$InstallLeaf = $null
$BackupDirectory = $null
$StagingRoot = $null
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

function Get-NormalizedDirectoryPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $ExpandedPath = [Environment]::ExpandEnvironmentVariables($Path.Trim().Trim('"'))
    $FullPath = [System.IO.Path]::GetFullPath($ExpandedPath)
    return $FullPath.TrimEnd([char[]]"\/")
}

function Get-InstallPathInfo {
    param([Parameter(Mandatory = $true)][string]$Path)

    $FullPath = Get-NormalizedDirectoryPath -Path $Path
    $Parent = [System.IO.Path]::GetDirectoryName($FullPath)
    $Leaf = [System.IO.Path]::GetFileName($FullPath)

    if ([string]::IsNullOrWhiteSpace($Parent) -or [string]::IsNullOrWhiteSpace($Leaf)) {
        throw "Le chemin d'installation n'est pas exploitable : $FullPath"
    }

    return [pscustomobject]@{
        FullPath = $FullPath
        Parent = $Parent
        Leaf = $Leaf
    }
}

function Remove-DirectoryIfExists {
    param([string]$Path)

    if (-not [string]::IsNullOrWhiteSpace($Path) -and [System.IO.Directory]::Exists($Path)) {
        [System.IO.Directory]::Delete($Path, $true)
    }
}

function Test-SupportedPython {
    param([Parameter(Mandatory = $true)][string]$Executable)

    if (-not [System.IO.File]::Exists($Executable)) {
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
        if (-not [System.IO.Directory]::Exists($Root)) {
            continue
        }

        foreach ($Executable in [System.IO.Directory]::GetFiles($Root, "python.exe", [System.IO.SearchOption]::AllDirectories)) {
            if (Test-SupportedPython -Executable $Executable) {
                return $Executable
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
        return (Get-InstallPathInfo -Path $DefaultPath).FullPath
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

        try {
            $Info = Get-InstallPathInfo -Path $CustomPath
            $FullPath = $Info.FullPath
            $DriveRoot = [System.IO.Path]::GetPathRoot($FullPath)
            $NormalizedRoot = $DriveRoot.TrimEnd([char[]]"\/")
            $NormalizedData = Get-NormalizedDirectoryPath -Path $ProtectedDataPath
        }
        catch {
            Write-Warning "Ce chemin n'est pas valide."
            continue
        }

        if ([string]::IsNullOrWhiteSpace($DriveRoot) -or -not [System.IO.Directory]::Exists($DriveRoot)) {
            Write-Warning "Le lecteur choisi n'est pas disponible : $DriveRoot"
            continue
        }

        if ($FullPath.Equals($NormalizedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            Write-Warning "Choisissez un dossier sur le lecteur, pas sa racine."
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

    if ([System.IO.File]::Exists($Path)) {
        throw "Un fichier existe deja a l'emplacement choisi : $Path"
    }

    if (-not [System.IO.Directory]::Exists($Path)) {
        return
    }

    $Items = [System.IO.Directory]::GetFileSystemEntries($Path)
    if ($Items.Count -eq 0) {
        return
    }

    $LooksLikeAssistantBotanique = `
        [System.IO.File]::Exists([System.IO.Path]::Combine($Path, "pyproject.toml")) -and `
        [System.IO.Directory]::Exists([System.IO.Path]::Combine($Path, "src", "assistant_botanique"))

    if ($LooksLikeAssistantBotanique) {
        return
    }

    Write-Warning "Le dossier existe et ne semble pas etre une installation d'Assistant Botanique : $Path"
    $Confirmation = Read-Host "Tapez REMPLACER pour autoriser son remplacement"
    if ($Confirmation -cne "REMPLACER") {
        throw "Installation annulee afin de proteger le contenu du dossier."
    }
}

function Invoke-PathSwapSelfTest {
    $Root = [System.IO.Path]::Combine($env:TEMP, "AssistantBotanique-path-test-" + [guid]::NewGuid().ToString("N"))
    $Target = [System.IO.Path]::Combine($Root, "AssistantBotanique")
    $Incoming = [System.IO.Path]::Combine($Root, "Incoming")
    $Backup = [System.IO.Path]::Combine($Root, "AssistantBotanique.previous-test")

    try {
        [System.IO.Directory]::CreateDirectory($Target) | Out-Null
        [System.IO.Directory]::CreateDirectory($Incoming) | Out-Null
        [System.IO.File]::WriteAllText([System.IO.Path]::Combine($Target, "old.txt"), "old")
        [System.IO.File]::WriteAllText([System.IO.Path]::Combine($Incoming, "new.txt"), "new")

        [System.IO.Directory]::Move($Target, $Backup)
        [System.IO.Directory]::Move($Incoming, $Target)

        if (-not [System.IO.File]::Exists([System.IO.Path]::Combine($Target, "new.txt"))) {
            throw "Le test de remplacement n'a pas trouve le nouveau contenu."
        }

        Remove-DirectoryIfExists -Path $Target
        [System.IO.Directory]::Move($Backup, $Target)

        if (-not [System.IO.File]::Exists([System.IO.Path]::Combine($Target, "old.txt"))) {
            throw "Le test de restauration n'a pas retrouve l'ancien contenu."
        }
    }
    finally {
        Remove-DirectoryIfExists -Path $Root
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

    Invoke-PathSwapSelfTest
    Write-Host "Auto-test reussi. Python : $DetectedPython ; extraction : $($Tar.Source) ; chemins : OK" -ForegroundColor Green
    exit 0
}

try {
    Write-Host "Installation d'Assistant Botanique..." -ForegroundColor Cyan

    $Stage = "choix du dossier"
    $InstallDirectory = Select-InstallDirectory `
        -DefaultPath $DefaultInstallDirectory `
        -ProtectedDataPath $DataDirectory

    Confirm-ExistingDirectoryReplacement -Path $InstallDirectory

    $InstallInfo = Get-InstallPathInfo -Path $InstallDirectory
    $InstallDirectory = $InstallInfo.FullPath
    $InstallParent = $InstallInfo.Parent
    $InstallLeaf = $InstallInfo.Leaf

    Write-Host "Installation choisie : $InstallDirectory" -ForegroundColor Green

    $Stage = "detection de Python"
    $PythonExecutable = Find-SupportedPython
    if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
        $Winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if ($null -eq $Winget) {
            throw "Python 3.11 a 3.13 est absent et Winget est indisponible."
        }

        Write-Host "Installation de Python 3.11..." -ForegroundColor Yellow
        $WingetArguments = "install --exact --id Python.Python.3.11 --scope user --accept-package-agreements --accept-source-agreements --silent --disable-interactivity"
        $WingetResult = Invoke-NativeCommand -FilePath $Winget.Source -Arguments $WingetArguments
        Write-NativeResult -Result $WingetResult

        $PythonExecutable = Find-SupportedPython
        if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
            throw "L'installation de Python a echoue ou son executable est introuvable (code Winget : $($WingetResult.ExitCode))."
        }
    }

    $VersionResult = Invoke-NativeChecked `
        -FilePath $PythonExecutable `
        -Arguments '-c "import sys; print(\"{}.{}.{}\".format(*sys.version_info[:3]))"' `
        -FailureMessage "Impossible d'utiliser Python"

    Write-Host "Python detecte : $($VersionResult.StdOut.Trim())" -ForegroundColor Green

    $Stage = "preparation du lecteur cible"
    [System.IO.Directory]::CreateDirectory($InstallParent) | Out-Null
    $StagingRoot = [System.IO.Path]::Combine(
        $InstallParent,
        "." + $InstallLeaf + ".staging-" + [guid]::NewGuid().ToString("N")
    )
    [System.IO.Directory]::CreateDirectory($StagingRoot) | Out-Null
    [System.IO.Directory]::CreateDirectory($TemporaryWorkDirectory) | Out-Null

    $Stage = "telechargement"
    Write-Host "Telechargement du programme..." -ForegroundColor Yellow
    Invoke-WebRequest -UseBasicParsing -Uri $RepositoryArchive -OutFile $ArchiveFile

    if (-not [System.IO.File]::Exists($ArchiveFile)) {
        throw "L'archive telechargee est introuvable."
    }

    $Stage = "extraction de l'archive"
    $Tar = Get-Command tar.exe -ErrorAction SilentlyContinue
    if ($null -eq $Tar) {
        throw "tar.exe est introuvable. Windows 10 ou Windows 11 est requis."
    }

    Write-Host "Extraction du programme sur le lecteur cible..." -ForegroundColor Yellow
    $TarArguments = "-xf $(Quote-NativeArgument -Value $ArchiveFile) -C $(Quote-NativeArgument -Value $StagingRoot)"
    Invoke-NativeChecked `
        -FilePath $Tar.Source `
        -Arguments $TarArguments `
        -FailureMessage "L'extraction de l'archive a echoue" `
        -ShowOutput | Out-Null

    $ExtractedDirectory = [System.IO.Path]::Combine($StagingRoot, "Assistant_Botanique-main")
    if (-not [System.IO.Directory]::Exists($ExtractedDirectory)) {
        $ExtractedDirectory = $null
        foreach ($Candidate in [System.IO.Directory]::GetDirectories($StagingRoot)) {
            if ([System.IO.File]::Exists([System.IO.Path]::Combine($Candidate, "pyproject.toml"))) {
                $ExtractedDirectory = $Candidate
                break
            }
        }
    }

    if ([string]::IsNullOrWhiteSpace($ExtractedDirectory) -or -not [System.IO.Directory]::Exists($ExtractedDirectory)) {
        throw "Le contenu extrait est incomplet."
    }

    $Stage = "mise en securite de l'installation existante"
    if ([System.IO.Directory]::Exists($InstallDirectory)) {
        $BackupDirectory = [System.IO.Path]::Combine(
            $InstallParent,
            $InstallLeaf + ".previous-" + [guid]::NewGuid().ToString("N")
        )

        Write-Host "Mise en securite de l'installation existante..." -ForegroundColor Yellow
        [System.IO.Directory]::Move($InstallDirectory, $BackupDirectory)
    }

    $Stage = "installation du nouveau programme"
    $InstallContentTouched = $true
    [System.IO.Directory]::Move($ExtractedDirectory, $InstallDirectory)

    $VirtualEnvironment = [System.IO.Path]::Combine($InstallDirectory, ".venv")
    $ApplicationPython = [System.IO.Path]::Combine($VirtualEnvironment, "Scripts", "python.exe")
    $ApplicationPythonW = [System.IO.Path]::Combine($VirtualEnvironment, "Scripts", "pythonw.exe")

    $Stage = "creation de l'environnement Python"
    Write-Host "Creation de l'environnement Python isole..." -ForegroundColor Yellow
    $VenvArguments = "-m venv $(Quote-NativeArgument -Value $VirtualEnvironment)"
    Invoke-NativeChecked `
        -FilePath $PythonExecutable `
        -Arguments $VenvArguments `
        -FailureMessage "La creation de l'environnement Python a echoue" `
        -ShowOutput | Out-Null

    if (-not [System.IO.File]::Exists($ApplicationPython)) {
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
    [System.IO.Directory]::CreateDirectory($StartMenuDirectory) | Out-Null

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

    if (-not [string]::IsNullOrWhiteSpace($BackupDirectory) -and [System.IO.Directory]::Exists($BackupDirectory)) {
        try {
            [System.IO.Directory]::Delete($BackupDirectory, $true)
        }
        catch {
            Write-Warning "L'ancienne installation n'a pas pu etre supprimee : $BackupDirectory"
        }
    }

    Remove-DirectoryIfExists -Path $StagingRoot

    Write-Host ""
    Write-Host "Installation terminee dans : $InstallDirectory" -ForegroundColor Green
    Write-Host "Les raccourcis Bureau et menu Demarrer ont ete crees."

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
    $LineNumber = $_.InvocationInfo.ScriptLineNumber
    $ExceptionType = $_.Exception.GetType().FullName

    Write-Host ""
    Write-Host "ECHEC DE L'INSTALLATION pendant l'etape '$Stage'." -ForegroundColor Red
    Write-Host "Ligne : $LineNumber" -ForegroundColor Red
    Write-Host "Type : $ExceptionType" -ForegroundColor Red
    Write-Host "Message : $($_.Exception.Message)" -ForegroundColor Red

    if (-not [string]::IsNullOrWhiteSpace($BackupDirectory) -and [System.IO.Directory]::Exists($BackupDirectory)) {
        try {
            Remove-DirectoryIfExists -Path $InstallDirectory
            [System.IO.Directory]::Move($BackupDirectory, $InstallDirectory)
            Write-Host "L'installation precedente a ete restauree." -ForegroundColor Yellow
        }
        catch {
            Write-Warning "La restauration automatique a echoue. Copie de securite : $BackupDirectory"
        }
    }
    elseif ($InstallContentTouched) {
        try {
            Remove-DirectoryIfExists -Path $InstallDirectory
        }
        catch {
            Write-Warning "Le dossier incomplet n'a pas pu etre supprime : $InstallDirectory"
        }
    }
}
finally {
    try {
        Remove-DirectoryIfExists -Path $StagingRoot
    }
    catch {
    }

    try {
        Remove-DirectoryIfExists -Path $TemporaryWorkDirectory
    }
    catch {
    }
}

exit $ExitCode

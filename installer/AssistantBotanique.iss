#define MyAppName "Assistant Botanique"
#define MyAppVersion "3.0.0"
#define MyAppPublisher "Laurent COLL1"
#define MyAppExeName "AssistantBotanique.exe"

[Setup]
AppId={{A92C0C99-B80B-4DF8-AB41-E8A45C58BA61}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Assistant Botanique
DefaultGroupName={#MyAppName}
OutputDir=output
OutputBaseFilename=AssistantBotanique-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\dist\AssistantBotanique\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"
Name: "notifications"; Description: "Activer le contrôle quotidien des plantes à 09:00"; GroupDescription: "Notifications :"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#MyAppExeName}"; Parameters: "--install-notifications 09:00"; Flags: runhidden; Tasks: notifications

[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /F /TN AssistantBotaniqueNotifications"; Flags: runhidden

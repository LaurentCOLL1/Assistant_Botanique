#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#ifndef MyAppOutputBaseFilename
  #define MyAppOutputBaseFilename "AssistantBotanique-Setup"
#endif

#define MyAppName "Assistant Botanique"
#define MyAppPublisher "Laurent COLL1"
#define MyAppExeName "AssistantBotanique.exe"
#define MyAppIconName "AssistantBotanique-" + MyAppVersion + ".ico"

[Setup]
AppId={{A92C0C99-B80B-4DF8-AB41-E8A45C58BA61}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\AssistantBotanique
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename={#MyAppOutputBaseFilename}
SetupIconFile=generated\assistant_botanique.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName} {#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppIconName}
UsePreviousAppDir=yes
CloseApplications=force
RestartApplications=no
SetupLogging=yes

[InstallDelete]
Type: files; Name: "{app}\AssistantBotanique-*.ico"

[Files]
Source: "..\dist\AssistantBotanique\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "generated\assistant_botanique.ico"; DestDir: "{app}"; DestName: "{#MyAppIconName}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIconName}"; IconIndex: 0
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIconName}"; IconIndex: 0; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"
Name: "notifications"; Description: "Activer le contrôle quotidien des plantes à 09:00"; GroupDescription: "Notifications :"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#MyAppExeName}"; Parameters: "--install-notifications 09:00"; Flags: runhidden; Tasks: notifications

[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /F /TN AssistantBotaniqueNotifications"; Flags: runhidden

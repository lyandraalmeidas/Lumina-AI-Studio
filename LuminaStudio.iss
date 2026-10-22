#define MyAppName "Lumina AI Studio"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Lumina AI Studio"
#define MyAppExeName "LuminaStudio.exe"

[Setup]
AppId={{BCA92A70-CE1F-4C8C-AD34-8B7EF31E44C4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Lumina AI Studio
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=assets\lumina.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=LuminaStudio-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"

[Files]
Source: "dist\installer-build\LuminaStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Lumina AI Studio"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\assets\lumina.ico"; AppUserModelID: "LuminaStudio.Desktop"
Name: "{autodesktop}\Lumina AI Studio"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\assets\lumina.ico"; AppUserModelID: "LuminaStudio.Desktop"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent

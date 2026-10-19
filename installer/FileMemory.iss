; File Memory per-user installer.
; PrivilegesRequired=lowest means setup does not request administrator elevation.
; The selected folder access and optional startup task are explicitly user-driven.

#define MyAppName "File Memory"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "File Memory"
#define MyAppExeName "FileMemory.exe"

[Setup]
AppId={{9D80A9E2-7916-4F7E-9D8E-0D4A4E1D86B2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\File Memory
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=FileMemory-Setup
SetupIconFile=..\assets\filememory.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "startupicon"; Description: "Launch File Memory in the background when I sign in to Windows"; GroupDescription: "Startup options:"; Flags: checkedonce

[Files]
; Build the onedir artifact before compiling this installer.
Source: "..\dist\FileMemory\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\File Memory"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\File Memory"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{userstartup}\File Memory"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--minimized"; WorkingDir: "{app}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch File Memory"; Flags: nowait postinstall skipifsilent runascurrentuser

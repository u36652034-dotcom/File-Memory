; File Memory Windows x64 installer.
; Installs the standalone onedir app under Program Files. Administrator approval
; is required by Windows for that location; File Memory never requests access to
; user folders until the user selects them inside the app.

#define MyAppName "File Memory"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "UsmanAutomates (usmanautomates.com)"
#define MyAppPublisherURL "https://usmanautomates.com"
#define MyAppExeName "FileMemory.exe"
#ifndef MyAppVariant
  #define MyAppVariant "online"
#endif
#if MyAppVariant == "offline"
  #define MyAppDist "..\dist\offline\FileMemory"
#else
  #define MyAppDist "..\dist\online\FileMemory"
#endif

[Setup]
AppId={{9D80A9E2-7916-4F7E-9D8E-0D4A4E1D86B2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppPublisherURL}
AppSupportURL={#MyAppPublisherURL}
AppUpdatesURL={#MyAppPublisherURL}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} {#MyAppVariant} installer
DefaultDirName={autopf}\File Memory
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=FileMemory-Setup-{#MyAppVariant}
SetupIconFile=..\assets\filememory.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardImageFile=wizard.bmp
WizardSmallImageFile=wizard-small.bmp

[Tasks]
Name: "startupicon"; Description: "Launch File Memory in the background when I sign in to Windows"; GroupDescription: "Startup options:"; Flags: checkedonce

[Files]
; Build the onedir artifact before compiling this installer.
Source: "{#MyAppDist}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\File Memory"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\File Memory"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Registry]
; HKCU Run is visible in Windows Startup Apps/Task Manager and can be disabled
; by the user without reinstalling or changing administrator policy.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "File Memory"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Flags: uninsdeletevalue; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch File Memory"; Flags: nowait postinstall skipifsilent runascurrentuser

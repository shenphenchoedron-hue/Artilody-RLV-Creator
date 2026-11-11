; Inno Setup script for Artilody RLV Creator
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppName "Artilody RLV Creator"
#define MyAppExe "Artilody RLV Creator.exe"

[Setup]
AppId={{6A3E1B52-6D0C-4C1E-9E0B-4B7B3F2C9A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Artilody
AppPublisherURL=https://github.com/shenphenchoedron-hue/Artilody-RLV-Creator
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\release
OutputBaseFilename=Artilody-RLV-Creator-{#MyAppVersion}-Windows-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "danish"; MessagesFile: "compiler:Languages\Danish.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\artilody-rlv-creator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
[Setup]
AppId={{4F17E709-1B41-4D55-8C89-CE2F27B07029}
AppName=QuadView
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\QuadView
DefaultGroupName=QuadView
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=QuadViewSetup-{#AppVersion}
SetupIconFile=..\build\quadview.ico
UninstallDisplayIcon={app}\QuadView.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\dist\QuadView\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\QuadView"; Filename: "{app}\QuadView.exe"
Name: "{autodesktop}\QuadView"; Filename: "{app}\QuadView.exe"

[Run]
Filename: "{app}\QuadView.exe"; Description: "Open QuadView"; Flags: nowait postinstall skipifsilent

#ifndef AppVersion
  #error AppVersion must be supplied by build_windows.py
#endif
#ifndef RuntimeDir
  #error RuntimeDir must be supplied by build_windows.py
#endif
#ifndef OutputDir
  #error OutputDir must be supplied by build_windows.py
#endif
#ifndef AppName
  #define AppName "PNC Counter"
#endif
#ifndef AppIdentity
  #define AppIdentity "{{B9C4DC6E-A44E-4862-8DA6-14983A6C7773}"
#endif
#ifndef WindowsVersion
  #define WindowsVersion AppVersion
#endif
#ifndef FileBaseName
  #define FileBaseName "PNC-Counter-" + AppVersion + "-Setup-x64"
#endif

[Setup]
AppId={#AppIdentity}
AppName={#AppName}
AppVersion={#AppVersion}
VersionInfoVersion={#WindowsVersion}
AppPublisher=Nucleus Analysis contributors
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename={#FileBaseName}
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\runtime\pythonw.exe
CloseApplications=yes
RestartApplications=no
LicenseFile=..\..\LICENSE
InfoBeforeFile=welcome.txt

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#RuntimeDir}\*"; DestDir: "{app}\runtime"; Excludes: "*.pyc,*.pyo,*.pdb"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\docs\windows-installer.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-I -m nucleus_analysis.desktop_launcher"; WorkingDir: "{userdocs}"
Name: "{group}\{#AppName} setup and repair"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-I -m nucleus_analysis.desktop_launcher --setup"; WorkingDir: "{userdocs}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-I -m nucleus_analysis.desktop_launcher"; WorkingDir: "{userdocs}"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-I -m nucleus_analysis.desktop_launcher"; Description: "Open PNC Counter and complete first-time analysis setup"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove generated Python bytecode as well as installed runtime files. User
; preferences, models, engines and analysis results are stored outside this directory.
Type: filesandordirs; Name: "{app}\runtime"

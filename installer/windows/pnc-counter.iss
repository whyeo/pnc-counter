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
Source: "..\..\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\docs\windows-installer.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\..\docs\manual-review.md"; DestDir: "{app}\docs"; Flags: ignoreversion

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

[Code]
var
  ExistingVersion, ExistingDirectory, MaintenanceAction: String;
  ExistingInstallation, MachineInstallation: Boolean;

function ParseAppVersion(Value: String; var Base: Int64; var Development: Integer): Boolean;
var
  Position: Integer;
begin
  Position := Pos('.dev', Value);
  Development := MaxInt;
  if Position > 0 then begin
    Development := StrToIntDef(Copy(Value, Position + 4, Length(Value)), -1);
    Value := Copy(Value, 1, Position - 1);
  end;
  Result := (Development >= 0) and StrToVersion(Value, Base);
end;

function CompareAppVersions(Left, Right: String; var Comparison: Integer): Boolean;
var
  LeftBase, RightBase: Int64;
  LeftDevelopment, RightDevelopment: Integer;
begin
  Result := ParseAppVersion(Left, LeftBase, LeftDevelopment) and
            ParseAppVersion(Right, RightBase, RightDevelopment);
  if not Result then exit;
  Comparison := ComparePackedVersion(LeftBase, RightBase);
  if Comparison = 0 then begin
    if LeftDevelopment < RightDevelopment then Comparison := -1;
    if LeftDevelopment > RightDevelopment then Comparison := 1;
  end;
end;

function ReadExistingInstallation: Boolean;
var
  Key: String;
begin
  Key := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppIdentity}_is1');
  MachineInstallation := False;
  Result := RegKeyExists(HKCU, Key);
  if Result then begin
    RegQueryStringValue(HKCU, Key, 'DisplayVersion', ExistingVersion);
    RegQueryStringValue(HKCU, Key, 'InstallLocation', ExistingDirectory);
  end else if RegKeyExists(HKLM, Key) then begin
    MachineInstallation := True;
    Result := True;
    RegQueryStringValue(HKLM, Key, 'DisplayVersion', ExistingVersion);
    RegQueryStringValue(HKLM, Key, 'InstallLocation', ExistingDirectory);
  end;
end;

function OtherEditionNotice: String;
var
  Key, Name, Version: String;
begin
  Result := '';
  { These editions intentionally have independent identities and preferences. }
  if '{#AppName}' = 'PNC Counter Preview' then begin
    Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B9C4DC6E-A44E-4862-8DA6-14983A6C7773}_is1';
    Name := 'PNC Counter';
  end else if '{#AppName}' = 'PNC Counter' then begin
    Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{D397F5FC-A509-4C44-8959-18247B83FDF1}_is1';
    Name := 'PNC Counter Preview';
  end else exit;
  if RegQueryStringValue(HKCU, Key, 'DisplayVersion', Version) or
     RegQueryStringValue(HKLM, Key, 'DisplayVersion', Version) then
    Result := Name + ' ' + Version + ' is also installed. This setup only changes {#AppName}.';
end;

function InitializeSetup: Boolean;
var
  Comparison: Integer;
  Message, OtherNotice: String;
begin
  Result := False;
  MaintenanceAction := 'install';
  ExistingVersion := '';
  ExistingDirectory := '';
  { Registry helpers use the 64-bit view in this installer's x64 install mode. }
  ExistingInstallation := ReadExistingInstallation;
  if ExistingInstallation then begin
    Log('PNC existing version: ' + ExistingVersion);
    Log('PNC existing directory: ' + ExistingDirectory);
    if MachineInstallation then begin
      Log('PNC maintenance blocked: machine-wide installation');
      if not WizardSilent then
        MsgBox('A machine-wide installation of {#AppName} was found. Use its installer or contact your administrator to update or repair it.', mbError, MB_OK);
      exit;
    end;
    if not CompareAppVersions(ExistingVersion, '{#AppVersion}', Comparison) then begin
      Log('PNC maintenance blocked: unrecognized installed version');
      if not WizardSilent then
        MsgBox('An installation of {#AppName} was found, but its version could not be identified. Use its original installer to repair it before updating.', mbError, MB_OK);
      exit;
    end;
    if Comparison > 0 then begin
      Log('PNC maintenance blocked: newer version installed');
      if not WizardSilent then
        MsgBox('{#AppName} ' + ExistingVersion + ' is newer than this installer ({#AppVersion}). Use that version''s installer to repair it. No files have been changed.', mbError, MB_OK);
      exit;
    end;
    if Comparison < 0 then begin
      MaintenanceAction := 'upgrade';
      Message := 'Upgrade {#AppName} from ' + ExistingVersion + ' to {#AppVersion}?';
    end else begin
      MaintenanceAction := 'repair';
      Message := 'Repair {#AppName} {#AppVersion} by reinstalling its application files?';
    end;
    if ExistingDirectory = '' then begin
      Log('PNC maintenance blocked: missing registered installation folder');
      if not WizardSilent then
        MsgBox('The registered folder for {#AppName} is missing. Use its original installer or uninstall entry before installing again.', mbError, MB_OK);
      exit;
    end;
    Message := Message + #13#10#13#10 + 'Folder: ' + ExistingDirectory + #13#10#13#10 +
      'Your preferences, downloaded models and analysis results will be kept. Choose No to cancel.';
  end else
    Message := '';
  Log('PNC maintenance action: ' + MaintenanceAction);
  OtherNotice := OtherEditionNotice;
  if OtherNotice <> '' then begin
    Log(OtherNotice);
    if Message = '' then
      Message := OtherNotice + #13#10#13#10 + 'Install {#AppName} separately?'
    else
      Message := Message + #13#10#13#10 + OtherNotice;
  end;
  if (Message <> '') and not WizardSilent then begin
    Result := MsgBox(Message, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
    if not Result then Log('PNC maintenance cancelled: no application files changed');
  end else Result := True;
end;

procedure InitializeWizard;
begin
  if ExistingInstallation then
    WizardForm.DirEdit.Text := RemoveBackslashUnlessRoot(ExistingDirectory);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := ExistingInstallation and (PageID = wpSelectDir);
end;

procedure CurPageChanged(PageID: Integer);
begin
  if PageID = wpReady then begin
    if MaintenanceAction = 'upgrade' then WizardForm.NextButton.Caption := '&Upgrade';
    if MaintenanceAction = 'repair' then WizardForm.NextButton.Caption := '&Repair';
  end;
end;

; Live Translator setup (packaging; spec §11). Built by `python -m tools.build_installer`,
; which passes AppVersion, SourceDir (the PyInstaller app folder), OutputDir and IconFile.
;
; Per-user install by default (no admin prompt); people can pick "all users" or another
; folder. Shortcuts are offered but left unticked (user request 2026-10-19: people make their
; own). Uninstalling asks before deleting settings and downloaded models (several GB).

#ifndef AppVersion
  #error AppVersion must be passed: /DAppVersion=x.y.z
#endif
#ifndef SourceDir
  #error SourceDir must be passed: /DSourceDir=<app folder>
#endif

#define AppName "Live Translator"
#define AppExe "LiveTranslator.exe"
#define AppUserModelId "LiveTranslator.App"
#define ProjectUrl "https://github.com/Unbakedcookie/Live-Translator-pc-app"

[Setup]
AppId={{6F1C5A2E-4B7D-4E1A-9C3F-2D8B7A41E5C9}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Unbakedcookie
AppPublisherURL={#ProjectUrl}
AppSupportURL={#ProjectUrl}/issues
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
UsedUserAreasWarning=no
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
OutputDir={#OutputDir}
OutputBaseFilename=LiveTranslator-Setup-{#AppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}

[Tasks]
Name: "startmenu"; Description: "Add {#AppName} to the Start menu"; GroupDescription: "Shortcuts (optional, you can make your own later):"; Flags: unchecked
Name: "desktopicon"; Description: "Put a shortcut on the desktop"; GroupDescription: "Shortcuts (optional, you can make your own later):"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppUserModelId}"; Tasks: startmenu
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppUserModelId}"; Tasks: desktopicon

[Registry]
; The app registers its notification name here when it runs (D-037); remove it on uninstall.
Root: HKCU; Subkey: "Software\Classes\AppUserModelId\{#AppUserModelId}"; Flags: uninsdeletekey dontcreatekey

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent

[Code]
function DataFolder(const Name: String): String;
begin
  Result := ExpandConstant('{' + Name + '}\LiveTranslator');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  if not (DirExists(DataFolder('userappdata')) or DirExists(DataFolder('localappdata'))) then
    Exit;
  if SuppressibleMsgBox('Also delete your settings and downloaded models?' + #13#10#13#10 +
      'Choose No if you might install {#AppName} again: the models are several GB to ' +
      'download. A models folder you moved somewhere else is never deleted.',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
  begin
    DelTree(DataFolder('userappdata'), True, True, True);
    DelTree(DataFolder('localappdata'), True, True, True);
  end;
end;

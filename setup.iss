; ArtoDownloader kurulum betiği (Inno Setup 6)
[Setup]
AppId={{7A1C3F52-5E0B-4B7D-9C35-1D2E3F4A5B6C}
AppName=ArtoDownloader
AppVersion=1.0
AppPublisher=ArtoDownloader
DefaultDirName={localappdata}\Programs\ArtoDownloader
DefaultGroupName=ArtoDownloader
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=ArtoDownloader-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\ArtoDownloader\ArtoDownloader.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Files]
Source: "build\dist\ArtoDownloader\*"; DestDir: "{app}\ArtoDownloader"; Flags: recursesubdirs ignoreversion
Source: "build\dist\ArtoHost\*"; DestDir: "{app}\ArtoHost"; Flags: recursesubdirs ignoreversion
Source: "artodownloader.xpi"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\ArtoDownloader"; Filename: "{app}\ArtoDownloader\ArtoDownloader.exe"
Name: "{autodesktop}\ArtoDownloader"; Filename: "{app}\ArtoDownloader\ArtoDownloader.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Masaüstü kısayolu oluştur"; Flags: unchecked

[Registry]
; Native messaging host kaydı (LibreWolf ve Firefox)
Root: HKCU; Subkey: "Software\LibreWolf\NativeMessagingHosts\artodownloader"; ValueType: string; ValueData: "{app}\artodownloader.json"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Mozilla\NativeMessagingHosts\artodownloader"; ValueType: string; ValueData: "{app}\artodownloader.json"; Flags: uninsdeletekey

[Run]
Filename: "{code:LibreWolfPath}"; Parameters: """{app}\artodownloader.xpi"""; Description: "Eklentiyi LibreWolf'a yükle"; Flags: nowait postinstall skipifsilent; Check: LibreWolfFound

[UninstallDelete]
Type: files; Name: "{app}\artodownloader.json"

[Code]
function LibreWolfPath(Param: String): String;
begin
  Result := ExpandConstant('{commonpf}\LibreWolf\librewolf.exe');
  if not FileExists(Result) then
    Result := ExpandConstant('{localappdata}\LibreWolf\librewolf.exe');
  if not FileExists(Result) then
    Result := ExpandConstant('{commonpf32}\LibreWolf\librewolf.exe');
end;

function LibreWolfFound: Boolean;
begin
  Result := FileExists(LibreWolfPath(''));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  HostPath, Json: String;
begin
  if CurStep = ssPostInstall then
  begin
    HostPath := ExpandConstant('{app}\ArtoHost\ArtoHost.exe');
    StringChangeEx(HostPath, '\', '\\', True);
    Json := '{' + #13#10 +
      '  "name": "artodownloader",' + #13#10 +
      '  "description": "ArtoDownloader native host",' + #13#10 +
      '  "path": "' + HostPath + '",' + #13#10 +
      '  "type": "stdio",' + #13#10 +
      '  "allowed_extensions": ["artodownloader@local"]' + #13#10 +
      '}';
    SaveStringToFile(ExpandConstant('{app}\artodownloader.json'), Json, False);
  end;
end;


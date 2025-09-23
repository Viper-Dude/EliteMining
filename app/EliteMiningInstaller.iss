[Setup]
AppName=EliteMining
AppVersion=3.9.5 Beta
AppPublisher=CMDR ViperDude
DefaultDirName={code:GetVAPath}
AppendDefaultDirName=no
DisableDirPage=no
DefaultGroupName=EliteMining
OutputBaseFilename=EliteMiningSetup
Compression=lzma
SolidCompression=yes
SetupIconFile=logo_multi.ico

; Place uninstaller in Apps folder
UninstallFilesDir={app}\Apps
UninstallDisplayName=EliteMining
UninstallDisplayIcon={app}\Apps\EliteMining\app\Images\logo_multi.ico

[Files]
; Only include needed subfolders
Source: "app\Images\*";    DestDir: "{app}\Apps\EliteMining\app\Images";    Flags: recursesubdirs createallsubdirs ignoreversion
Source: "app\Settings\*";  DestDir: "{app}\Apps\EliteMining\app\Settings";  Flags: recursesubdirs createallsubdirs ignoreversion
Source: "app\Reports\*";   DestDir: "{app}\Apps\EliteMining\app\Reports";   Flags: recursesubdirs createallsubdirs ignoreversion

; New Configurator executable
Source: "dist\Configurator.exe"; DestDir: "{app}\Apps\EliteMining\Configurator"; Flags: ignoreversion

; Documentation, variables, profile
Source: "Doc\*"; DestDir: "{app}\Apps\EliteMining\Doc"; Flags: recursesubdirs createallsubdirs uninsneveruninstall
Source: "Variables\*"; DestDir: "{app}\Apps\EliteMining\Variables"; Flags: recursesubdirs createallsubdirs onlyifdoesntexist
Source: "EliteMining-Profile.vap"; DestDir: "{app}\Apps\EliteMining"; Flags: uninsneveruninstall skipifsourcedoesntexist

; Config files - handled intelligently by installer script
Source: "app\config.json"; DestDir: "{tmp}"; DestName: "new_config.json"; Flags: ignoreversion
Source: "app\config_installer.py"; DestDir: "{tmp}"; Flags: ignoreversion
Source: "app\config_installer.bat"; DestDir: "{tmp}"; Flags: ignoreversion

[Tasks]
; Offer optional desktop icon
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"

[Icons]
; Start Menu shortcut
Name: "{group}\EliteMining"; Filename: "{app}\Apps\EliteMining\Configurator\Configurator.exe"; WorkingDir: "{app}\Apps\EliteMining\Configurator"
; Desktop shortcut (optional)
Name: "{commondesktop}\EliteMining"; Filename: "{app}\Apps\EliteMining\Configurator\Configurator.exe"; WorkingDir: "{app}\Apps\EliteMining\Configurator"; Tasks: desktopicon
; Uninstall shortcut
Name: "{group}\Uninstall EliteMining"; Filename: "{app}\Apps\unins000.exe"

[Run]
; Handle config.json migration intelligently - try Python first, then batch fallback
Filename: "python"; Parameters: """{tmp}\config_installer.py"" ""{tmp}\new_config.json"" ""{app}\Apps\EliteMining"""; Description: "Configuring application settings"; Flags: runhidden skipifdoesntexist
Filename: "{tmp}\config_installer.bat"; Parameters: """{tmp}\new_config.json"" ""{app}\Apps\EliteMining"""; Description: "Configuring application settings"; Flags: runhidden

; Create symbolic link to uninstaller  
Filename: "{cmd}"; Parameters: "/C mklink ""{app}\Apps\Uninstall_EliteMining.exe"" ""{app}\Apps\unins000.exe"""; Description: "Creating custom uninstaller link"; Flags: runhidden

; Clean up old installations and shortcuts AFTER successful installation
Filename: "{cmd}"; Parameters: "/C if exist ""C:\Program Files\Elite Mining"" rmdir /s /q ""C:\Program Files\Elite Mining"""; Description: "Cleaning up old installation"; Flags: runhidden skipifdoesntexist
Filename: "{cmd}"; Parameters: "/C if exist ""C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Elite Mining"" rmdir /s /q ""C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Elite Mining"""; Description: "Cleaning up old shortcuts"; Flags: runhidden skipifdoesntexist

; Launch application after installation
Filename: "{app}\Apps\EliteMining\Configurator\Configurator.exe"; Description: "&Launch EliteMining"; Flags: nowait postinstall skipifsilent unchecked

[UninstallRun]
; Remove symbolic link on uninstall
Filename: "{cmd}"; Parameters: "/C del ""{app}\Apps\Uninstall_EliteMining.exe"""; Flags: runhidden

[Messages]
SelectDirDesc=Setup will install [name] into the VoiceAttack folder.\n\nIf your VoiceAttack folder was not auto-detected, please click [b]Browse[/b] and select the correct root folder (…\VoiceAttack or …\VoiceAttack 2). The installer will then place files into Apps\EliteMining automatically.

[Code]
function GetVAPath(Default: String): String;
begin
  { Auto-detect VoiceAttack installation root (without \Apps) }
  if DirExists('D:\SteamLibrary\steamapps\common\VoiceAttack 2') then
    Result := 'D:\SteamLibrary\steamapps\common\VoiceAttack 2'
  else if DirExists('D:\SteamLibrary\steamapps\common\VoiceAttack') then
    Result := 'D:\SteamLibrary\steamapps\common\VoiceAttack'
  else if DirExists('C:\Program Files (x86)\VoiceAttack') then
    Result := 'C:\Program Files (x86)\VoiceAttack'
  else
    Result := ExpandConstant('{pf}\VoiceAttack');
end;

procedure InitializeWizard;
begin
  WizardForm.DirEdit.Text := GetVAPath('');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    { Ensure path doesn't include duplicate \Apps\EliteMining }
    if Pos('\Apps\EliteMining', WizardForm.DirEdit.Text) > 0 then
    begin
      WizardForm.DirEdit.Text := Copy(WizardForm.DirEdit.Text, 1, Pos('\Apps\EliteMining', WizardForm.DirEdit.Text) - 1);
    end;
  end;
end;

{ Clean up old installations before installing new version }
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  
  { Remove old installation directory if it exists }
  if DirExists('C:\Program Files\Elite Mining') then
  begin
    if not DelTree('C:\Program Files\Elite Mining', True, True, True) then
      Result := 'Warning: Could not completely remove old installation. Some files may remain.';
  end;
  
  { Remove old Start Menu shortcuts }
  if DirExists(ExpandConstant('{commonprograms}\Elite Mining')) then
    DelTree(ExpandConstant('{commonprograms}\Elite Mining'), True, True, True);
end;

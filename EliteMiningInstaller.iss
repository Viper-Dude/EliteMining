[Setup]
AppName=EliteMining
AppVersion=v4.6.6
AppPublisher=CMDR ViperDude
DefaultDirName={code:GetDefaultInstallDir}\EliteMining
DisableDirPage=no
DefaultGroupName=EliteMining
OutputBaseFilename=EliteMiningSetup
Compression=lzma
SolidCompression=yes
SetupIconFile=app\Images\logo_multi.ico
CloseApplications=force
RestartApplications=no
; Close running EliteMining processes (handles both old Configurator.exe and new EliteMining.exe)
CloseApplicationsFilter=*.exe

; Place uninstaller in app folder
UninstallFilesDir={app}
UninstallDisplayName=EliteMining
UninstallDisplayIcon={app}\Configurator\EliteMining.exe

[InstallDelete]
; Delete old Configurator.exe before installing new EliteMining.exe (v4.3.2+ rename)
Type: files; Name: "{app}\Configurator\Configurator.exe"
; Delete old MIT LICENSE.txt (replaced with GPLv3 LICENSE in v4.4.1+)
Type: files; Name: "{app}\LICENSE.txt"

[Files]
; Only include specific file types from needed subfolders (exclude .py files)
Source: "app\Images\*";    DestDir: "{app}\app\Images";    Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "*.py,*.pyc,__pycache__"
; Localization files (v4.6.7+) - required for UI translations
Source: "app\localization\*.json";  DestDir: "{app}\app\localization";  Flags: ignoreversion
; VoiceAttack-specific files (only installed if VA detected)
Source: "app\Ship Presets\*";  DestDir: "{app}\app\Ship Presets";  Flags: recursesubdirs createallsubdirs onlyifdoesntexist; Excludes: "*.py,*.pyc,__pycache__"; Check: IsVADetected
; Reports folder intentionally excluded - users must earn their reports by mining! 😉

; New Configurator executable
Source: "dist\EliteMining.exe"; DestDir: "{app}\Configurator"; Flags: ignoreversion

; Local systems database (~14 MB) - populated systems within the bubble for fast searches
Source: "app\data\galaxy_systems.db"; DestDir: "{app}\app\data"; Flags: ignoreversion skipifsourcedoesntexist
Source: "app\data\database_metadata.json"; DestDir: "{app}\app\data"; Flags: ignoreversion skipifsourcedoesntexist

; v4.6.0+: Overlap and RES site data CSV files for migration
Source: "app\data\overlaps.csv"; DestDir: "{app}\app\data"; Flags: ignoreversion skipifsourcedoesntexist
Source: "app\data\res_sites.csv"; DestDir: "{app}\app\data"; Flags: ignoreversion skipifsourcedoesntexist

; v4.1.8+: Use smart version checking instead of forced overwrite
; Database will only update if new version > existing version, with automatic backup
Source: "app\data\UserDb for install\user_data.db"; DestDir: "{app}\app\data"; Flags: onlyifdoesntexist

; Version checking utilities
Source: "scripts\installer\config_installer.py"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "scripts\installer\check_db_version.py"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "scripts\installer\set_db_version.py"; DestDir: "{tmp}"; Flags: deleteafterinstall

; Documentation (always installed)
Source: "Doc\*"; DestDir: "{app}\Doc"; Flags: recursesubdirs createallsubdirs uninsneveruninstall skipifsourcedoesntexist
; VoiceAttack-specific files (only installed if VA detected)
Source: "Variables\*"; DestDir: "{app}\Variables"; Flags: recursesubdirs createallsubdirs onlyifdoesntexist; Check: IsVADetected
; v4.1.9+: Force update VoiceAttack profile to apply command behavior corrections
Source: "EliteMining-Profile.vap"; DestDir: "{app}"; Flags: uninsneveruninstall skipifsourcedoesntexist; Check: IsVADetected
; v4.1.5+: Never overwrite config.json - preserves user settings
; NOTE: Use template file to avoid including developer's personal paths
Source: "app\config.json.template"; DestDir: "{app}"; DestName: "config.json"; Flags: onlyifdoesntexist
Source: "app\mining_bookmarks.json"; DestDir: "{app}\app"; Flags: onlyifdoesntexist skipifsourcedoesntexist
Source: "app\EliteVA\*"; DestDir: "{app}\..\EliteVA"; Flags: recursesubdirs createallsubdirs; Check: IsVADetected
Source: "LICENSE"; DestDir: "{app}"
Source: "NOTICE"; DestDir: "{app}"

[Tasks]
; Offer optional desktop icon
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"

[Icons]
; Start Menu shortcut
Name: "{group}\EliteMining"; Filename: "{app}\Configurator\EliteMining.exe"; WorkingDir: "{app}\Configurator"
; Desktop shortcut (optional)
Name: "{commondesktop}\EliteMining"; Filename: "{app}\Configurator\EliteMining.exe"; WorkingDir: "{app}\Configurator"; Tasks: desktopicon
; Uninstall shortcut
Name: "{group}\Uninstall EliteMining"; Filename: "{app}\Apps\unins000.exe"

[Dirs]
; Create Cards folder for mining card PNGs (v4.4.3+)
Name: "{app}\app\Reports\Cards"; Permissions: users-modify

[Run]
; Create symbolic link to uninstaller
Filename: "{cmd}"; Parameters: "/C mklink ""{app}\Apps\Uninstall_EliteMining.exe"" ""{app}\Apps\unins000.exe"""; Description: "Creating custom uninstaller link"; Flags: runhidden

; Clean up old installations and shortcuts AFTER successful installation
Filename: "{cmd}"; Parameters: "/C if exist ""C:\Program Files\Elite Mining"" rmdir /s /q ""C:\Program Files\Elite Mining"""; Description: "Cleaning up old installation"; Flags: runhidden skipifdoesntexist
Filename: "{cmd}"; Parameters: "/C if exist ""C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Elite Mining"" rmdir /s /q ""C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Elite Mining"""; Description: "Cleaning up old shortcuts"; Flags: runhidden skipifdoesntexist

; Launch application after installation
Filename: "{app}\Configurator\EliteMining.exe"; Description: "&Launch EliteMining"; Flags: nowait postinstall skipifsilent unchecked

[UninstallRun]
; Remove symbolic link on uninstall
Filename: "{cmd}"; Parameters: "/C del ""{app}\Apps\Uninstall_EliteMining.exe"""; Flags: runhidden

[Messages]
SelectDirDesc=Install EliteMining to your VoiceAttack folder. If auto-detection failed, click Browse and select your VoiceAttack root folder (contains VoiceAttack.exe).
UninstalledAll=EliteMining has been successfully uninstalled.%n%nNOTE: Some files have been intentionally left behind to preserve your data:%n• Mining reports and detailed reports%n• Configuration files (config.json, mining_bookmarks.json)%n• Settings folder%n• Variables folder%n• Documentation folder%n• VoiceAttack profile (EliteMining-Profile.vap)%n%nTo completely remove all EliteMining data, manually delete the folder:%n%1

[Code]
var
  VADetected: Boolean;

function IsVADetected: Boolean;
begin
  Result := VADetected;
end;

function GetDefaultInstallDir(Default: String): String;
var
  SteamPath: String;
  Drive: String;
  I: Integer;
begin
  { Initialize VA detection flag }
  VADetected := False;
  
  { Method 1: Check Windows Registry for VoiceAttack installation }
  if RegQueryStringValue(HKLM, 'SOFTWARE\VoiceAttack', 'InstallPath', Result) then
  begin
    if DirExists(Result) and FileExists(Result + '\VoiceAttack.exe') then
    begin
      VADetected := True;
      Result := Result + '\Apps';
      Exit;
    end;
  end;
  
  if RegQueryStringValue(HKCU, 'SOFTWARE\VoiceAttack', 'InstallPath', Result) then
  begin
    if DirExists(Result) and FileExists(Result + '\VoiceAttack.exe') then
    begin
      VADetected := True;
      Result := Result + '\Apps';
      Exit;
    end;
  end;
  
  { Method 2: Check Steam registry for library folders }
  if RegQueryStringValue(HKCU, 'SOFTWARE\Valve\Steam', 'SteamPath', SteamPath) then
  begin
    StringChangeEx(SteamPath, '/', '\', True);
    if DirExists(SteamPath + '\steamapps\common\VoiceAttack 2') then
    begin
      VADetected := True;
      Result := SteamPath + '\steamapps\common\VoiceAttack 2\Apps';
      Exit;
    end
    else if DirExists(SteamPath + '\steamapps\common\VoiceAttack') then
    begin
      VADetected := True;
      Result := SteamPath + '\steamapps\common\VoiceAttack\Apps';
      Exit;
    end;
  end;
  
  { Method 3: Scan common drives (C, D, E, F) for VoiceAttack installations }
  for I := 0 to 3 do
  begin
    case I of
      0: Drive := 'C';
      1: Drive := 'D';
      2: Drive := 'E';
      3: Drive := 'F';
    end;
    
    { Check Steam locations }
    if DirExists(Drive + ':\Program Files (x86)\Steam\steamapps\common\VoiceAttack 2') then
    begin
      VADetected := True;
      Result := Drive + ':\Program Files (x86)\Steam\steamapps\common\VoiceAttack 2\Apps';
      Exit;
    end
    else if DirExists(Drive + ':\Program Files\Steam\steamapps\common\VoiceAttack 2') then
    begin
      VADetected := True;
      Result := Drive + ':\Program Files\Steam\steamapps\common\VoiceAttack 2\Apps';
      Exit;
    end
    else if DirExists(Drive + ':\SteamLibrary\steamapps\common\VoiceAttack 2') then
    begin
      VADetected := True;
      Result := Drive + ':\SteamLibrary\steamapps\common\VoiceAttack 2\Apps';
      Exit;
    end
    else if DirExists(Drive + ':\Program Files (x86)\Steam\steamapps\common\VoiceAttack') then
    begin
      VADetected := True;
      Result := Drive + ':\Program Files (x86)\Steam\steamapps\common\VoiceAttack\Apps';
      Exit;
    end
    else if DirExists(Drive + ':\Program Files\Steam\steamapps\common\VoiceAttack') then
    begin
      VADetected := True;
      Result := Drive + ':\Program Files\Steam\steamapps\common\VoiceAttack\Apps';
      Exit;
    end
    else if DirExists(Drive + ':\SteamLibrary\steamapps\common\VoiceAttack') then
    begin
      VADetected := True;
      Result := Drive + ':\SteamLibrary\steamapps\common\VoiceAttack\Apps';
      Exit;
    end;
  end;
  
  { Method 4: Check standard Program Files locations }
  { Check 64-bit Program Files explicitly first (C:\Program Files) }
  if DirExists('C:\Program Files\VoiceAttack 2') then
  begin
    VADetected := True;
    Result := 'C:\Program Files\VoiceAttack 2\Apps';
  end
  else if DirExists('C:\Program Files\VoiceAttack') then
  begin
    VADetected := True;
    Result := 'C:\Program Files\VoiceAttack\Apps';
  end
  { Then check using Inno Setup constants }
  else if DirExists(ExpandConstant('{pf}\VoiceAttack 2')) then
  begin
    VADetected := True;
    Result := ExpandConstant('{pf}\VoiceAttack 2\Apps');
  end
  else if DirExists(ExpandConstant('{pf32}\VoiceAttack 2')) then
  begin
    VADetected := True;
    Result := ExpandConstant('{pf32}\VoiceAttack 2\Apps');
  end
  else if DirExists(ExpandConstant('{pf}\VoiceAttack')) then
  begin
    VADetected := True;
    Result := ExpandConstant('{pf}\VoiceAttack\Apps');
  end
  else if DirExists(ExpandConstant('{pf32}\VoiceAttack')) then
  begin
    VADetected := True;
    Result := ExpandConstant('{pf32}\VoiceAttack\Apps');
  end
  else
  begin
    { Fallback to standalone installation in user AppData (no admin rights required) }
    VADetected := False;
    Result := ExpandConstant('{localappdata}');
  end;
end;

procedure InitializeWizard;
begin
  { Installer automatically appends \EliteMining to base directory }
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  SelectedPath: String;
  ParentPath: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    SelectedPath := WizardForm.DirEdit.Text;
    
    { Remove trailing \EliteMining if present to check parent folder }
    if Copy(SelectedPath, Length(SelectedPath) - Length('EliteMining') + 1, Length('EliteMining')) = 'EliteMining' then
      ParentPath := Copy(SelectedPath, 1, Length(SelectedPath) - Length('\EliteMining'))
    else
      ParentPath := SelectedPath;
    
    { Validate if user selected a VoiceAttack folder }
    if FileExists(ParentPath + '\VoiceAttack.exe') then
    begin
      { Valid VoiceAttack installation - update detection flag }
      VADetected := True;
    end
    else if (Pos('VoiceAttack', SelectedPath) > 0) and (Pos('\Apps\EliteMining', SelectedPath) > 0) then
    begin
      { VA install path detected - keep VA flag as-is }
      { VADetected already set by GetDefaultInstallDir }
    end
    else if Pos('EliteMining', SelectedPath) > 0 then
    begin
      { Standalone installation - ensure VA flag is false }
      VADetected := False;
    end
    else
    begin
      { User selected custom path without VoiceAttack.exe - confirm }
      if MsgBox('The selected folder does not appear to be a VoiceAttack installation (VoiceAttack.exe not found).' + #13#13 +
                'Voice command features will not work unless you install to your VoiceAttack folder.' + #13#13 +
                'VoiceAttack-specific files (Ship Presets, Variables, EliteVA) will NOT be installed.' + #13#13 +
                'Selected path: ' + SelectedPath + #13#13 +
                'Do you want to continue with this location anyway?',
                mbConfirmation, MB_YESNO) = IDNO then
      begin
        Result := False;
        Exit;
      end
      else
      begin
        { User confirmed - this is a standalone installation }
        VADetected := False;
      end;
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

{ Show information about preserved files during uninstall }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  LeftoverPath: String;
  MsgText: String;
  ErrorCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    LeftoverPath := ExpandConstant('{app}');
    
    { Only show message if the directory still exists (contains preserved files) }
    if DirExists(LeftoverPath) then
    begin
      MsgText := 'EliteMining has been uninstalled, but some files were left behind to preserve your data:' + #13#13 +
                 '• Mining reports and detailed reports' + #13 +
                 '• Screenshots from mining sessions' + #13 +
                 '• Mining performance graphs and charts' + #13 +
                 '• Configuration files (config.json, mining_bookmarks.json)' + #13 +
                 '• Settings folder' + #13 +
                 '• Variables folder' + #13 +
                 '• Documentation folder' + #13 +
                 '• VoiceAttack profile (EliteMining-Profile.vap)' + #13#13 +
                 'These files are located at:' + #13 +
                 LeftoverPath + #13#13 +
                 'To completely remove all EliteMining data, manually delete this folder.' + #13#13 +
                 'Would you like to open the folder location now?';
                 
      if MsgBox(MsgText, mbInformation, MB_YESNO) = IDYES then
      begin
        Exec('explorer.exe', '/select,"' + LeftoverPath + '"', '', SW_SHOW, ewNoWait, ErrorCode);
      end;
    end;
  end;
end;

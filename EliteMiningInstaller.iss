[Setup]
AppName=EliteMining
AppVersion=v4.1.5
AppPublisher=CMDR ViperDude
DefaultDirName={code:GetVAPath}
AppendDefaultDirName=no
DisableDirPage=no
DefaultGroupName=EliteMining
OutputBaseFilename=EliteMiningSetup
Compression=lzma
SolidCompression=yes
SetupIconFile=app\Images\logo_multi.ico
CloseApplications=force
RestartApplications=no
CloseApplicationsFilter=*.exe

; Place uninstaller in Apps folder
UninstallFilesDir={app}\Apps
UninstallDisplayName=EliteMining
UninstallDisplayIcon={app}\Apps\EliteMining\Configurator\Configurator.exe

[Files]
; Only include specific file types from needed subfolders (exclude .py files)
Source: "app\Images\*";    DestDir: "{app}\Apps\EliteMining\app\Images";    Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "*.py,*.pyc,__pycache__"
Source: "app\Ship Presets\*";  DestDir: "{app}\Apps\EliteMining\app\Ship Presets";  Flags: recursesubdirs createallsubdirs onlyifdoesntexist; Excludes: "*.py,*.pyc,__pycache__"
; Reports folder intentionally excluded - users must earn their reports by mining! 😉

; New Configurator executable
Source: "dist\Configurator.exe"; DestDir: "{app}\Apps\EliteMining\Configurator"; Flags: ignoreversion

; Local systems database (~14 MB) - populated systems within the bubble for fast searches
Source: "app\data\galaxy_systems.db"; DestDir: "{app}\Apps\EliteMining\app\data"; Flags: ignoreversion skipifsourcedoesntexist
Source: "app\data\database_metadata.json"; DestDir: "{app}\Apps\EliteMining\app\data"; Flags: ignoreversion skipifsourcedoesntexist

; User database - use pre-populated database for new installs, preserve existing for updates
Source: "app\data\UserDb for install\user_data.db"; DestDir: "{app}\Apps\EliteMining\app\data"; Flags: onlyifdoesntexist

; Documentation, variables, profile
Source: "Doc\*"; DestDir: "{app}\Apps\EliteMining\Doc"; Flags: recursesubdirs createallsubdirs uninsneveruninstall skipifsourcedoesntexist
Source: "Variables\*"; DestDir: "{app}\Apps\EliteMining\Variables"; Flags: recursesubdirs createallsubdirs onlyifdoesntexist
; v4.1.5+: Never overwrite VoiceAttack profile - preserves user modifications
Source: "EliteMining-Profile.vap"; DestDir: "{app}\Apps\EliteMining"; Flags: uninsneveruninstall skipifsourcedoesntexist onlyifdoesntexist
; v4.1.5+: Never overwrite config.json - preserves user settings
; NOTE: Remove "onlyifdoesntexist" flag if critical config updates are needed in future versions
Source: "app\config.json"; DestDir: "{app}\Apps\EliteMining"; Flags: onlyifdoesntexist
Source: "app\mining_bookmarks.json"; DestDir: "{app}\Apps\EliteMining\app"; Flags: onlyifdoesntexist skipifsourcedoesntexist
Source: "app\EliteVA\*"; DestDir: "{app}\Apps\EliteVA"; Flags: recursesubdirs createallsubdirs
Source: "LICENSE.txt"; DestDir: "{app}\Apps\EliteMining"

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
SelectDirDesc=Install EliteMining to your VoiceAttack folder. If auto-detection failed, click Browse and select your VoiceAttack root folder (contains VoiceAttack.exe).
UninstalledAll=EliteMining has been successfully uninstalled.%n%nNOTE: Some files have been intentionally left behind to preserve your data:%n• Mining reports and detailed reports%n• Configuration files (config.json, mining_bookmarks.json)%n• Settings folder%n• Variables folder%n• Documentation folder%n• VoiceAttack profile (EliteMining-Profile.vap)%n%nTo completely remove all EliteMining data, manually delete the folder:%n%1\Apps\EliteMining

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

{ Show information about preserved files during uninstall }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  LeftoverPath: String;
  MsgText: String;
  ErrorCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    LeftoverPath := ExpandConstant('{app}\Apps\EliteMining');
    
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

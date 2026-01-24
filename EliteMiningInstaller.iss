[Setup]
AppName=EliteMining
AppVersion=v4.80
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
; Close running EliteMining and VoiceAttack processes
CloseApplicationsFilter=*.exe,VoiceAttack.exe,VoiceAttackEngine.exe

; Place uninstaller in app folder
UninstallFilesDir={app}
UninstallDisplayName=EliteMining
UninstallDisplayIcon={app}\Configurator\EliteMining.exe

[InstallDelete]
; Delete old Configurator.exe before installing new EliteMining.exe (v4.3.2+ rename)
Type: files; Name: "{app}\Configurator\Configurator.exe"
; Delete old MIT LICENSE.txt (replaced with GPLv3 LICENSE in v4.4.1+)
Type: files; Name: "{app}\LICENSE.txt"
; NOTE: Never delete profile files - user's choice what to keep
; The app handles profile version detection and keybind preservation
; v4.7.6+: Clean EliteAPI folder completely to ensure fresh install of all files (only if user confirmed)
Type: filesandordirs; Name: "{app}\..\EliteAPI\*"; Check: ShouldInstallEliteAPI

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

; EliteMiningPlugin.dll (VoiceAttack plugin for variable access) - only update if version changed
Source: "EliteMiningPlugin\bin\Release\net48\EliteMiningPlugin.dll"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist; Check: ShouldInstallPlugin
; Plugin version file
Source: "app\elitemining_plugin_version.txt"; DestDir: "{app}\app"; Flags: ignoreversion; Check: IsVADetected

; Local systems database (~14 MB) - populated systems within the bubble for fast searches
Source: "app\data\galaxy_systems.db"; DestDir: "{app}\app\data"; Flags: ignoreversion skipifsourcedoesntexist
Source: "app\data\database_metadata.json"; DestDir: "{app}\app\data"; Flags: ignoreversion skipifsourcedoesntexist

; v4.6.0+: Overlap and RES site data CSV files for migration
Source: "app\data\overlaps.csv"; DestDir: "{app}\app\data"; Flags: ignoreversion skipifsourcedoesntexist
Source: "app\data\res_sites.csv"; DestDir: "{app}\app\data"; Flags: ignoreversion skipifsourcedoesntexist

; v4.7.7+: Trade commodities data
Source: "app\data\commodities.json"; DestDir: "{app}\app\data"; Flags: ignoreversion skipifsourcedoesntexist

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
; v4.7.6+: Update profile only if newer - app detects version changes and prompts user
; Profile filename includes version for clarity (EliteMining v4.76-Profile.vap)
; v4.7.8+: Use profile from Voiceattack Profile folder instead of root
Source: "Voiceattack Profile\EliteMining v*-Profile.vap"; DestDir: "{app}"; Flags: uninsneveruninstall; Check: IsVADetected
; v4.1.5+: Never overwrite config.json - preserves user settings
; NOTE: Use template file to avoid including developer's personal paths
Source: "app\config.json.template"; DestDir: "{app}"; DestName: "config.json"; Flags: onlyifdoesntexist
Source: "app\mining_bookmarks.json"; DestDir: "{app}\app"; Flags: onlyifdoesntexist skipifsourcedoesntexist
; EliteAPI files - v4.7.6+: Force complete replacement of all files (only if user confirmed)
; Destination is dynamic - uses existing installation path if found, otherwise defaults to EliteAPI
Source: "app\EliteAPI\*"; DestDir: "{code:GetEliteAPIDestDir}"; Flags: recursesubdirs createallsubdirs ignoreversion; Check: ShouldInstallEliteAPI
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
  InstallEliteAPI: Boolean;
  InstallPlugin: Boolean;
  VABasePath: String;  { Store VoiceAttack base path for EliteAPI checking }
  ExistingEliteAPIPath: String;  { Store actual path where EliteAPI.dll was found }
  VersionFile: String;  { Path to EliteAPI_Version.txt }
  ExistingVersion: AnsiString;  { Version string from EliteAPI_Version.txt }
  PluginVersionFile: String;  { Path to elitemining_plugin_version.txt }
  ExistingPluginVersion: AnsiString;  { Version string from plugin version file }
  NewPluginVersion: AnsiString;  { New plugin version being installed }

function IsVADetected: Boolean;
begin
  Result := VADetected;
end;

function BoolToStr(Value: Boolean): String;
begin
  if Value then
    Result := 'True'
  else
    Result := 'False';
end;

function ShouldInstallEliteAPI: Boolean;
begin
  Result := InstallEliteAPI;
end;

function ShouldInstallPlugin: Boolean;
begin
  Result := InstallPlugin and IsVADetected;
end;

function IsVoiceAttackRunning: Boolean;
var
  ResultCode: Integer;
  FindHandle: HWND;
begin
  { Check if VoiceAttack window is open using FindWindowByClassName }
  { VoiceAttack's main window class is typically "WindowsForms10.Window" but we can also check by title }
  FindHandle := FindWindowByWindowName('VoiceAttack');
  Result := (FindHandle <> 0);
end;

function GetEliteAPIDestDir(Param: String): String;
begin
  { If we found existing installation, use that path; otherwise default to EliteAPI }
  if ExistingEliteAPIPath <> '' then
    Result := ExistingEliteAPIPath
  else
    Result := ExpandConstant('{app}\..\EliteAPI');
end;

function FindEliteAPIInDirectory(const BasePath: String): String;
var
  FindRec: TFindRec;
  SubPath: String;
begin
  Result := '';
  
  { Search for EliteAPI.dll in base directory }
  if FileExists(BasePath + '\EliteAPI.dll') then
  begin
    Result := BasePath;
    Exit;
  end;
  
  { Search recursively in subdirectories }
  if FindFirst(BasePath + '\*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY <> 0) and
           (FindRec.Name <> '.') and (FindRec.Name <> '..') then
        begin
          SubPath := BasePath + '\' + FindRec.Name;
          
          { Check for EliteAPI.dll or EliteVA.dll in this subdirectory }
          if FileExists(SubPath + '\EliteAPI.dll') or FileExists(SubPath + '\EliteVA.dll') then
          begin
            Result := SubPath;
            Exit;
          end;
          
          { Recursively search deeper }
          Result := FindEliteAPIInDirectory(SubPath);
          if Result <> '' then
            Exit;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

function GetDefaultInstallDir(Default: String): String;
var
  SteamPath: String;
  Drive: String;
  I: Integer;
begin
  { Initialize VA detection flag }
  VADetected := False;
  VABasePath := '';
  
  { Method 1: Check Windows Registry for VoiceAttack installation }
  if RegQueryStringValue(HKLM, 'SOFTWARE\VoiceAttack', 'InstallPath', Result) then
  begin
    if DirExists(Result) and FileExists(Result + '\VoiceAttack.exe') then
    begin
      VADetected := True;
      VABasePath := Result;
      Result := Result + '\Apps';
      Exit;
    end;
  end;
  
  if RegQueryStringValue(HKCU, 'SOFTWARE\VoiceAttack', 'InstallPath', Result) then
  begin
    if DirExists(Result) and FileExists(Result + '\VoiceAttack.exe') then
    begin
      VADetected := True;
      VABasePath := Result;
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
      VABasePath := SteamPath + '\steamapps\common\VoiceAttack 2';
      Result := VABasePath + '\Apps';
      Exit;
    end
    else if DirExists(SteamPath + '\steamapps\common\VoiceAttack') then
    begin
      VADetected := True;
      VABasePath := SteamPath + '\steamapps\common\VoiceAttack';
      Result := VABasePath + '\Apps';
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
      VABasePath := Drive + ':\Program Files (x86)\Steam\steamapps\common\VoiceAttack 2';
      Result := VABasePath + '\Apps';
      Exit;
    end
    else if DirExists(Drive + ':\Program Files\Steam\steamapps\common\VoiceAttack 2') then
    begin
      VADetected := True;
      VABasePath := Drive + ':\Program Files\Steam\steamapps\common\VoiceAttack 2';
      Result := VABasePath + '\Apps';
      Exit;
    end
    else if DirExists(Drive + ':\SteamLibrary\steamapps\common\VoiceAttack 2') then
    begin
      VADetected := True;
      VABasePath := Drive + ':\SteamLibrary\steamapps\common\VoiceAttack 2';
      Result := VABasePath + '\Apps';
      Exit;
    end
    else if DirExists(Drive + ':\Program Files (x86)\Steam\steamapps\common\VoiceAttack') then
    begin
      VADetected := True;
      VABasePath := Drive + ':\Program Files (x86)\Steam\steamapps\common\VoiceAttack';
      Result := VABasePath + '\Apps';
      Exit;
    end
    else if DirExists(Drive + ':\Program Files\Steam\steamapps\common\VoiceAttack') then
    begin
      VADetected := True;
      VABasePath := Drive + ':\Program Files\Steam\steamapps\common\VoiceAttack';
      Result := VABasePath + '\Apps';
      Exit;
    end
    else if DirExists(Drive + ':\SteamLibrary\steamapps\common\VoiceAttack') then
    begin
      VADetected := True;
      VABasePath := Drive + ':\SteamLibrary\steamapps\common\VoiceAttack';
      Result := VABasePath + '\Apps';
      Exit;
    end;
  end;
  
  { Method 4: Check standard Program Files locations }
  { Check 64-bit Program Files explicitly first (C:\Program Files) }
  if DirExists('C:\Program Files\VoiceAttack 2') then
  begin
    VADetected := True;
    VABasePath := 'C:\Program Files\VoiceAttack 2';
    Result := VABasePath + '\Apps';
  end
  else if DirExists('C:\Program Files\VoiceAttack') then
  begin
    VADetected := True;
    VABasePath := 'C:\Program Files\VoiceAttack';
    Result := VABasePath + '\Apps';
  end
  { Then check using Inno Setup constants }
  else if DirExists(ExpandConstant('{pf}\VoiceAttack 2')) then
  begin
    VADetected := True;
    VABasePath := ExpandConstant('{pf}\VoiceAttack 2');
    Result := VABasePath + '\Apps';
  end
  else if DirExists(ExpandConstant('{pf32}\VoiceAttack 2')) then
  begin
    VADetected := True;
    VABasePath := ExpandConstant('{pf32}\VoiceAttack 2');
    Result := VABasePath + '\Apps';
  end
  else if DirExists(ExpandConstant('{pf}\VoiceAttack')) then
  begin
    VADetected := True;
    VABasePath := ExpandConstant('{pf}\VoiceAttack');
    Result := VABasePath + '\Apps';
  end
  else if DirExists(ExpandConstant('{pf32}\VoiceAttack')) then
  begin
    VADetected := True;
    VABasePath := ExpandConstant('{pf32}\VoiceAttack');
    Result := VABasePath + '\Apps';
  end
  else
  begin
    { Fallback to standalone installation in user AppData (no admin rights required) }
    VADetected := False;
    VABasePath := '';
    Result := ExpandConstant('{localappdata}');
  end;
end;

procedure InitializeWizard;
var
  MsgResult: Integer;
  FolderName: String;
begin
  { Installer automatically appends \EliteMining to base directory }
  
  { Default: Install EliteAPI if VoiceAttack is detected }
  InstallEliteAPI := VADetected;
  ExistingEliteAPIPath := '';
  
  { Default: Install plugin if VoiceAttack detected }
  InstallPlugin := VADetected;
  
  Log('VADetected: ' + BoolToStr(VADetected));
  Log('VABasePath: ' + VABasePath);
  
  { Check if plugin version needs updating (only if VA detected) }
  { NOTE: New version is HARDCODED here - update when plugin changes! }
  if VADetected and (VABasePath <> '') then
  begin
    { Get the installation directory - use VABasePath + Apps\EliteMining }
    PluginVersionFile := VABasePath + '\Apps\EliteMining\app\elitemining_plugin_version.txt';
    
    Log('Checking plugin version file: ' + PluginVersionFile);
    
    if FileExists(PluginVersionFile) then
    begin
      { Load existing version }
      if LoadStringFromFile(PluginVersionFile, ExistingPluginVersion) then
      begin
        ExistingPluginVersion := Trim(ExistingPluginVersion);
        Log('Existing plugin version: ' + String(ExistingPluginVersion));
        
        { Compare with hardcoded new version (same approach as EliteAPI) }
        if ExistingPluginVersion = '1.0.0' then
        begin
          Log('Plugin version unchanged (1.0.0) - skipping plugin update');
          InstallPlugin := False;
        end
        else
        begin
          Log('Plugin version different - will update plugin');
          InstallPlugin := True;
        end;
      end
      else
      begin
        Log('Could not read existing plugin version - will install');
        InstallPlugin := True;
      end;
    end
    else
    begin
      Log('No existing plugin version file - will install');
      InstallPlugin := True;
    end;
  end;
  
  Log('InstallPlugin: ' + BoolToStr(InstallPlugin));
  
  { If plugin needs updating and VoiceAttack is running, warn user }
  if InstallPlugin and VADetected and IsVoiceAttackRunning then
  begin
    MsgResult := MsgBox(
      '⚠️ WARNING: VoiceAttack is currently running!' + #13#10 + #13#10 +
      'EliteMining plugin DLL needs to be updated.' + #13#10 +
      'VoiceAttack must be CLOSED before updating the plugin.' + #13#10 +
      'Files cannot be updated while VoiceAttack is using them.' + #13#10 + #13#10 +
      'Please close VoiceAttack now and click OK to continue.' + #13#10 +
      'Click Cancel to exit the installer.',
      mbError, MB_OKCANCEL);
    
    if MsgResult = IDCANCEL then
    begin
      WizardForm.Close;
      Exit;
    end;
  end;
  
  { If VoiceAttack detected, search for existing EliteAPI installation }
  if VADetected and (VABasePath <> '') then
  begin
    Log('Searching for EliteAPI in: ' + VABasePath);
    { Search for EliteAPI.dll or EliteVA.dll in VoiceAttack directory }
    ExistingEliteAPIPath := FindEliteAPIInDirectory(VABasePath);
    Log('ExistingEliteAPIPath: ' + ExistingEliteAPIPath);
    
    { Check version of existing installation }
    if ExistingEliteAPIPath <> '' then
    begin
      VersionFile := ExistingEliteAPIPath + '\EliteAPI_Version.txt';
      if FileExists(VersionFile) then
      begin
        if LoadStringFromFile(VersionFile, ExistingVersion) then
        begin
          ExistingVersion := Trim(ExistingVersion);
          Log('Existing EliteAPI version: ' + ExistingVersion);
          
          { If already v5.0.7, skip - no need to update }
          if ExistingVersion = '5.0.7' then
          begin
            Log('EliteAPI v5.0.7 already installed - skipping EliteAPI update');
            InstallEliteAPI := False;
            { Skip to end - no dialog needed }
          end
          else
          begin
            { Older version - ask about update, but first check if VoiceAttack is running }
            if IsVoiceAttackRunning then
            begin
              MsgResult := MsgBox(
                '⚠️ WARNING: VoiceAttack is currently running!' + #13#10 + #13#10 +
                'VoiceAttack must be CLOSED before installing EliteMining.' + #13#10 +
                'Files cannot be updated while VoiceAttack is using them.' + #13#10 + #13#10 +
                'Please close VoiceAttack now and click OK to continue.' + #13#10 +
                'Click Cancel to exit the installer.',
                mbError, MB_OKCANCEL);
              
              if MsgResult = IDCANCEL then
              begin
                WizardForm.Close;
                Exit;
              end;
            end;
            
            FolderName := ExtractFileName(ExistingEliteAPIPath);
            
            MsgResult := MsgBox(
              'EliteAPI v' + ExistingVersion + ' found in: ' + FolderName + #13#10 +
              'Path: ' + ExistingEliteAPIPath + #13#10 + #13#10 +
              'Update to v5.0.7 (RECOMMENDED)?'  + #13#10 + #13#10 +
              'YES:' + #13#10 +
              '  ✔ Latest features & bug fixes' + #13#10 +
              '  ✔ Full VoiceAttack support' + #13#10 +
              '  • Existing files replaced' + #13#10 + #13#10 +
              'NO:' + #13#10 +
              '  ⚠️ Voice commands may fail' + #13#10 +
              '  • Only if you have custom mods' + #13#10 + #13#10 +
              'ⓘ EliteAPI by Somfic | Only one EliteAPI/EliteVA installation allowed',
              mbConfirmation, MB_YESNO);
              
            if MsgResult = IDYES then
              InstallEliteAPI := True
            else
              InstallEliteAPI := False;
          end;
        end;  { End of if LoadStringFromFile }
      end
      else
      begin
        { No version file - old installation, ask about update, but first check if VoiceAttack is running }
        if IsVoiceAttackRunning then
        begin
          MsgResult := MsgBox(
            '⚠️ WARNING: VoiceAttack is currently running!' + #13#10 + #13#10 +
            'VoiceAttack must be CLOSED before installing EliteMining.' + #13#10 +
            'Files cannot be updated while VoiceAttack is using them.' + #13#10 + #13#10 +
            'Please close VoiceAttack now and click OK to continue.' + #13#10 +
            'Click Cancel to exit the installer.',
            mbError, MB_OKCANCEL);
          
          if MsgResult = IDCANCEL then
          begin
            WizardForm.Close;
            Exit;
          end;
        end;
        
        FolderName := ExtractFileName(ExistingEliteAPIPath);
        Log('No version file found - old EliteAPI installation');
        
        MsgResult := MsgBox(
          'EliteAPI found in: ' + FolderName + #13#10 +
          'Path: ' + ExistingEliteAPIPath + #13#10 + #13#10 +
          'Update to v5.0.7 (RECOMMENDED)?'  + #13#10 + #13#10 +
          'YES:' + #13#10 +
          '  ✔ Latest features & bug fixes' + #13#10 +
          '  ✔ Full VoiceAttack support' + #13#10 +
          '  • Existing files replaced' + #13#10 + #13#10 +
          'NO:' + #13#10 +
          '  ⚠️ Voice commands may fail' + #13#10 +
          '  • Only if you have custom mods' + #13#10 + #13#10 +
          'ⓘ EliteAPI by Somfic | Only one EliteAPI/EliteVA installation allowed',
          mbConfirmation, MB_YESNO);
          
        if MsgResult = IDYES then
          InstallEliteAPI := True
        else
          InstallEliteAPI := False;
      end;
    end
    else
    begin
      { No existing installation - ask about fresh INSTALL }
      { Check if VoiceAttack is running before installing EliteAPI }
      if IsVoiceAttackRunning then
      begin
        MsgResult := MsgBox(
          '⚠️ WARNING: VoiceAttack is currently running!' + #13#10 + #13#10 +
          'VoiceAttack must be CLOSED before installing EliteMining.' + #13#10 +
          'Files cannot be updated while VoiceAttack is using them.' + #13#10 + #13#10 +
          'Please close VoiceAttack now and click OK to continue.' + #13#10 +
          'Click Cancel to exit the installer.',
          mbError, MB_OKCANCEL);
        
        if MsgResult = IDCANCEL then
        begin
          WizardForm.Close;
          Exit;
        end;
      end;
      
      MsgResult := MsgBox(
        'VoiceAttack detected!' + #13#10 +
        'EliteAPI v5.0.7 not found.' + #13#10 + #13#10 +
        'Install EliteAPI (RECOMMENDED)?' + #13#10 + #13#10 +
        'YES:' + #13#10 +
        '  ✔ Enables voice commands' + #13#10 +
        '  ✔ Full mining automation' + #13#10 +
        '  ✔ Real-time game integration' + #13#10 + #13#10 +
        'NO:' + #13#10 +
        '  ⚠️ No voice automation' + #13#10 + #13#10 +
        'ⓘ EliteAPI by Somfic | Only one EliteAPI/EliteVA installation allowed',
        mbConfirmation, MB_YESNO);
        
      if MsgResult = IDYES then
        InstallEliteAPI := True
      else
        InstallEliteAPI := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  OldEliteVAPath: String;
  StateFilePath: String;
  OldProfilePath: String;
  StateContent: AnsiString;
  ProfileVersion: String;
  FindRec: TFindRec;
  ProfileFilename: String;
begin
  { Rename old EliteVA or EliteApi folders to EliteAPI (standardize naming) }
  if (CurStep = ssInstall) and (VABasePath <> '') then
  begin
    { Check for EliteVA folder }
    OldEliteVAPath := VABasePath + '\Apps\EliteVA';
    if DirExists(OldEliteVAPath) then
    begin
      Log('Found old EliteVA folder, renaming to EliteAPI: ' + OldEliteVAPath);
      if RenameFile(OldEliteVAPath, VABasePath + '\Apps\EliteAPI') then
      begin
        Log('Successfully renamed EliteVA to EliteAPI');
        ExistingEliteAPIPath := VABasePath + '\Apps\EliteAPI';
      end
      else
        Log('Warning: Failed to rename EliteVA folder, will try to delete and reinstall');
    end;
    
    { Also check for EliteApi folder (wrong casing) }
    OldEliteVAPath := VABasePath + '\Apps\EliteApi';
    if DirExists(OldEliteVAPath) and not DirExists(VABasePath + '\Apps\EliteAPI') then
    begin
      Log('Found EliteApi folder (wrong casing), renaming to EliteAPI: ' + OldEliteVAPath);
      if RenameFile(OldEliteVAPath, VABasePath + '\Apps\EliteAPI') then
      begin
        Log('Successfully renamed EliteApi to EliteAPI');
        ExistingEliteAPIPath := VABasePath + '\Apps\EliteAPI';
      end
      else
        Log('Warning: Failed to rename EliteApi folder');
    end;
  end;
  
  { Create VA profile state file only on TRUE FIRST INSTALL }
  { If old profile (EliteMining-Profile.vap) exists, this is an upgrade - let app handle it }
  if (CurStep = ssPostInstall) and IsVADetected then
  begin
    StateFilePath := ExpandConstant('{app}\app\va_profile_state.json');
    OldProfilePath := ExpandConstant('{app}\EliteMining-Profile.vap');
    
    { Only create state file if:
      1. State file doesn't already exist
      2. AND no old profile exists (true first install, not upgrade from v4.75) }
    if (not FileExists(StateFilePath)) and (not FileExists(OldProfilePath)) then
    begin
      ProfileVersion := '';
      
      { Find installed profile file and extract version from filename }
      { Pattern: EliteMining v4.76-Profile.vap -> extract "4.76" }
      { Skip Dev profiles - only use production profiles }
      if FindFirst(ExpandConstant('{app}\EliteMining v*-Profile.vap'), FindRec) then
      begin
        try
          ProfileFilename := FindRec.Name;
          
          { Skip if this is a Dev profile }
          if Pos('Dev', ProfileFilename) > 0 then
          begin
            Log('Skipping Dev profile: ' + ProfileFilename);
          end
          else
          begin
            Log('Found production profile file: ' + ProfileFilename);
          
            { Extract version between "v" and "-Profile.vap" }
            { Example: "EliteMining v4.76-Profile.vap" -> "4.76" }
            if Pos('v', ProfileFilename) > 0 then
            begin
              ProfileVersion := Copy(ProfileFilename, Pos('v', ProfileFilename) + 1, Length(ProfileFilename));
              ProfileVersion := Copy(ProfileVersion, 1, Pos('-Profile.vap', ProfileVersion) - 1);
              Log('Extracted profile version: ' + ProfileVersion);
            end;
          end;
        finally
          FindClose(FindRec);
        end;
      end;
      
      { Fallback to app version if profile version extraction failed }
      if ProfileVersion = '' then
      begin
        ProfileVersion := '4.76';
        Log('Warning: Could not extract profile version from filename, using default: ' + ProfileVersion);
      end;
      
      StateContent := '{"installed_version": "' + ProfileVersion + '"}';
      Log('True first install - Creating VA profile state file: ' + StateFilePath);
      if SaveStringToFile(StateFilePath, StateContent, False) then
        Log('Successfully created va_profile_state.json with version ' + ProfileVersion)
      else
        Log('Warning: Failed to create va_profile_state.json');
    end
    else if FileExists(OldProfilePath) then
    begin
      Log('Upgrade detected - Old profile exists (EliteMining-Profile.vap), app will handle keybind preservation');
    end
    else
    begin
      Log('Update detected - Preserving existing va_profile_state.json, app will detect profile changes');
    end;
  end;
  
  { Clean existing EliteAPI folder before installing new version }
  if (CurStep = ssInstall) and ShouldInstallEliteAPI and (ExistingEliteAPIPath <> '') then
  begin
    if DirExists(ExistingEliteAPIPath) then
    begin
      Log('Cleaning existing EliteAPI installation at: ' + ExistingEliteAPIPath);
      
      { Delete all files and subdirectories in the existing folder }
      { Parameters: Path, DeleteFiles, DeleteSubdirs, BreakOnError }
      if not DelTree(ExistingEliteAPIPath + '\*', True, True, True) then
      begin
        Log('Warning: Failed to completely clean EliteAPI folder');
        { Continue anyway - installer will overwrite what it can }
      end
      else
        Log('Successfully cleaned EliteAPI folder');
    end;
  end;
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

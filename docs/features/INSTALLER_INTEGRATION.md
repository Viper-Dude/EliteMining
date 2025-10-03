# EliteMining Installer Integration Guide

## 🎉 **INSTALLER ENHANCEMENT COMPLETE** - September 6, 2025

✅ **Root Cause Identified**: Old shortcuts pointing to cached executable at `C:\Program Files\Elite Mining\`  
✅ **Enhanced Installer Created**: Automatic cleanup of old installations and shortcuts  
✅ **Problem Solved**: Users will no longer launch old cached versions

### Key Improvements Made:
- **Pre-installation cleanup** removes old installations and shortcuts
- **Automatic detection** of VoiceAttack installation paths
- **Complete uninstall support** with no traces left behind
- **Single source of truth** - only current version remains after installation

---

## Reports Protection Integration

### For Inno Setup Installer (.iss file)

Add these sections to your `EliteMiningInstaller.iss` file:

#### 1. Add Files Section
```ini
[Files]
; Existing files...
Source: "app\reports_protector.py"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "app\protect_reports.bat"; DestDir: "{app}\app"; Flags: ignoreversion  
Source: "app\protect_reports.ps1"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "app\REPORTS_PROTECTION.md"; DestDir: "{app}\app"; Flags: ignoreversion
```

#### 2. Add Code Section for Backup
```pascal
[Code]
procedure BackupReports();
var
  BackupScript: String;
  ResultCode: Integer;
begin
  BackupScript := ExpandConstant('{app}\app\protect_reports.ps1');
  
  if FileExists(BackupScript) then
  begin
    // Try PowerShell first
    if Exec('powershell.exe', '-ExecutionPolicy Bypass -File "' + BackupScript + '" -Action backup', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      if ResultCode = 0 then
        Log('Reports backup completed successfully')
      else
        Log('Reports backup failed with PowerShell, trying batch...');
    end;
    
    // Fallback to batch script if PowerShell fails
    if ResultCode <> 0 then
    begin
      BackupScript := ExpandConstant('{app}\app\protect_reports.bat');
      if FileExists(BackupScript) then
      begin
        Exec(BackupScript, '"' + ExpandConstant('{app}') + '" backup', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        if ResultCode = 0 then
          Log('Reports backup completed with batch script')
        else
          Log('Reports backup failed');
      end;
    end;
  end;
end;

procedure RestoreReports();
var
  RestoreScript: String;
  ResultCode: Integer;
begin
  RestoreScript := ExpandConstant('{app}\app\protect_reports.ps1');
  
  if FileExists(RestoreScript) then
  begin
    // Try PowerShell first
    if Exec('powershell.exe', '-ExecutionPolicy Bypass -File "' + RestoreScript + '" -Action restore', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      if ResultCode = 0 then
        Log('Reports restore completed successfully')
      else
        Log('Reports restore failed with PowerShell, trying batch...');
    end;
    
    // Fallback to batch script if PowerShell fails
    if ResultCode <> 0 then
    begin
      RestoreScript := ExpandConstant('{app}\app\protect_reports.bat');
      if FileExists(RestoreScript) then
      begin
        Exec(RestoreScript, '"' + ExpandConstant('{app}') + '" restore', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        if ResultCode = 0 then
          Log('Reports restore completed with batch script')
        else
          Log('Reports restore failed');
      end;
    end;
  end;
end;
```

#### 3. Add Event Procedures
```pascal
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    // Backup Reports before installation
    BackupReports();
  end;
  
  if CurStep = ssPostInstall then
  begin
    // Restore Reports after installation
    RestoreReports();
  end;
end;
```

#### 4. Smart Uninstall with User Data Preservation
```pascal
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  InstallDir: String;
  UserChoice: Integer;
  BackupPath: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    InstallDir := ExpandConstant('{app}');
    
    // Ask user what type of uninstall they want
    UserChoice := MsgBox(
      'How would you like to uninstall EliteMining?' + #13#10 + #13#10 +
      'YES = Keep my settings and reports (Recommended)' + #13#10 +
      'NO = Complete removal (includes all user data)' + #13#10 +
      'CANCEL = Cancel uninstall',
      mbConfirmation, MB_YESNOCANCEL
    );
    
    case UserChoice of
      IDYES: begin
        // Smart uninstall - preserve user data
        Log('User chose smart uninstall');
        BackupPath := ExpandConstant('{localappdata}\EliteMining_UserData_Backup');
        
        // Create backup
        CreateDir(BackupPath);
        
        // Backup user data
        if DirExists(InstallDir + '\app\Reports') then
        begin
          Log('Backing up Reports folder');
          CreateDir(BackupPath + '\Reports');
          CopyDir(InstallDir + '\app\Reports', BackupPath + '\Reports');
        end;
        
        if DirExists(InstallDir + '\app\Settings') then
        begin
          Log('Backing up Settings folder');
          CreateDir(BackupPath + '\Settings');
          CopyDir(InstallDir + '\app\Settings', BackupPath + '\Settings');
        end;
        
        if FileExists(InstallDir + '\config.json') then
        begin
          Log('Backing up config.json');
          FileCopy(InstallDir + '\config.json', BackupPath + '\config.json', False);
        end;
        
        if DirExists(InstallDir + '\Variables') then
        begin
          Log('Backing up Variables folder');
          CreateDir(BackupPath + '\Variables');
          CopyDir(InstallDir + '\Variables', BackupPath + '\Variables');
        end;
        
        // After normal uninstall, restore user data
        RegisterExtraCloseApplicationsResource(
          ExpandConstant('{tmp}\restore_userdata.bat'),
          'call powershell.exe -Command "' +
          'Start-Sleep 2; ' +
          'if (Test-Path ''' + BackupPath + ''') { ' +
          '  New-Item -Path ''' + InstallDir + ''' -ItemType Directory -Force; ' +
          '  New-Item -Path ''' + InstallDir + '\app'' -ItemType Directory -Force; ' +
          '  if (Test-Path ''' + BackupPath + '\Reports'') { Copy-Item ''' + BackupPath + '\Reports'' ''' + InstallDir + '\app\Reports'' -Recurse -Force } ' +
          '  if (Test-Path ''' + BackupPath + '\Settings'') { Copy-Item ''' + BackupPath + '\Settings'' ''' + InstallDir + '\app\Settings'' -Recurse -Force } ' +
          '  if (Test-Path ''' + BackupPath + '\config.json'') { Copy-Item ''' + BackupPath + '\config.json'' ''' + InstallDir + '\config.json'' -Force } ' +
          '  if (Test-Path ''' + BackupPath + '\Variables'') { Copy-Item ''' + BackupPath + '\Variables'' ''' + InstallDir + '\Variables'' -Recurse -Force } ' +
          '  Remove-Item ''' + BackupPath + ''' -Recurse -Force; ' +
          '  ''EliteMining uninstalled but user data preserved:'' + [Environment]::NewLine + ' +
          '  ''- Mining session reports and history'' + [Environment]::NewLine + ' +
          '  ''- Personal settings and configurations'' + [Environment]::NewLine + ' +
          '  ''- Ship setup presets'' + [Environment]::NewLine + [Environment]::NewLine + ' +
          '  ''You can safely delete this folder if you no longer need this data.'' + [Environment]::NewLine + ' +
          '  ''To reinstall EliteMining, your settings will be restored automatically.'' ' +
          '  | Out-File ''' + InstallDir + '\USER_DATA_PRESERVED.txt'' -Encoding UTF8 ' +
          '}"'
        );
      end;
      
      IDNO: begin
        // Complete removal - confirm with scary warning
        if MsgBox('This will delete ALL your mining reports and settings!' + #13#10 +
                  'This includes months of valuable mining session data!' + #13#10 + #13#10 +
                  'Are you absolutely sure?', mbError, MB_YESNO) = IDNO then
          Abort;
        Log('User chose complete removal');
        // Normal uninstall proceeds - everything gets deleted
      end;
      
      IDCANCEL: begin
        Log('User cancelled uninstall');
        Abort;
      end;
    end;
  end;
end;
```

### Alternative: NSIS Installer

For NSIS installers, add these sections:

#### Install Section
```nsis
Section "Main Installation"
  ; Backup Reports before installation
  nsExec::Exec 'powershell.exe -ExecutionPolicy Bypass -File "$INSTDIR\app\protect_reports.ps1" -Action backup'
  
  ; Install files...
  SetOutPath "$INSTDIR\app"
  File "app\reports_protector.py"
  File "app\protect_reports.bat"
  File "app\protect_reports.ps1"
  File "app\REPORTS_PROTECTION.md"
  
  ; Restore Reports after installation
  nsExec::Exec 'powershell.exe -ExecutionPolicy Bypass -File "$INSTDIR\app\protect_reports.ps1" -Action restore'
SectionEnd
```

#### Uninstall Section
```nsis
Section "Uninstall"
  ; Optional backup before uninstall
  MessageBox MB_YESNO "Do you want to backup your mining session reports?" IDNO +3
    nsExec::Exec 'powershell.exe -ExecutionPolicy Bypass -File "$INSTDIR\app\protect_reports.ps1" -Action backup'
    MessageBox MB_OK "Reports backup completed!"
  
  ; Remove files...
  RMDir /r "$INSTDIR"
SectionEnd
```

## Testing the Integration

### 1. Test Backup Functionality
```batch
# Manual test
cd "C:\Program Files\EliteMining\app"
powershell.exe -ExecutionPolicy Bypass -File "protect_reports.ps1" -Action backup
```

### 2. Test Restore Functionality
```batch
# Manual test
powershell.exe -ExecutionPolicy Bypass -File "protect_reports.ps1" -Action restore
```

### 3. Verify Installation
1. Install EliteMining with existing Reports folder
2. Check that Reports data is preserved
3. Verify all session files are intact
4. Test that new installations work correctly

## Troubleshooting Integration

### Common Issues

#### PowerShell Execution Policy
**Problem**: Scripts don't run due to execution policy
**Solution**: Use `-ExecutionPolicy Bypass` parameter in installer

#### Permission Issues  
**Problem**: Scripts can't access folders
**Solution**: Ensure installer runs with appropriate privileges

#### Path Issues
**Problem**: Scripts can't find installation directory
**Solution**: Pass installation directory as parameter to scripts

### Debug Mode
Enable debug logging in installer to trace backup/restore operations:

```pascal
// Add to installer code
Log('Starting Reports backup...');
Log('Installation directory: ' + ExpandConstant('{app}'));
Log('Backup script path: ' + BackupScript);
```

## Deployment Checklist

- [ ] Protection scripts included in installer package
- [ ] Backup procedure called before installation
- [ ] Restore procedure called after installation  
- [ ] Uninstall backup option implemented
- [ ] Error handling for script failures
- [ ] User messaging for backup operations
- [ ] Testing on clean and existing installations
- [ ] Documentation provided to users

## User Experience

### What Users See
1. **During Installation**: Brief pause while Reports are backed up
2. **Post Installation**: All their session data preserved
3. **On Uninstall**: Option to backup Reports before removal
4. **Error Cases**: Clear messages about backup status

### What Users Should Know
- Reports are automatically protected during updates
- Manual backup scripts are available for additional protection
- Session history is preserved across installations
- Backup location is saved for manual recovery if needed

This integration ensures your users never lose their valuable mining session data during application updates or reinstallations.

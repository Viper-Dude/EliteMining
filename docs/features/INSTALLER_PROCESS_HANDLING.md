# Inno Setup Process Handling

Add this to your EliteMining installer script (.iss file) to handle running processes during installation/uninstallation:

## Pre-Installation Process Check

```pascal
[Code]
function IsEliteMiningRunning: Boolean;
var
  ProcessList: TStringList;
  I: Integer;
begin
  Result := False;
  ProcessList := TStringList.Create;
  try
    // Check for EliteMining.exe
    if GetProcessList(ProcessList, 'EliteMining.exe') then
    begin
      if ProcessList.Count > 0 then
        Result := True;
    end;
    
    // Check for Configurator.exe
    if GetProcessList(ProcessList, 'Configurator.exe') then
    begin
      if ProcessList.Count > 0 then
        Result := True;
    end;
  finally
    ProcessList.Free;
  end;
end;

function CloseEliteMiningProcesses: Boolean;
var
  ProcessList: TStringList;
  I: Integer;
  ProcessID: Cardinal;
  ProcessHandle: THandle;
begin
  Result := True;
  ProcessList := TStringList.Create;
  try
    // Close EliteMining.exe processes
    if GetProcessList(ProcessList, 'EliteMining.exe') then
    begin
      for I := 0 to ProcessList.Count - 1 do
      begin
        ProcessID := StrToIntDef(ProcessList[I], 0);
        if ProcessID <> 0 then
        begin
          ProcessHandle := OpenProcess(PROCESS_TERMINATE, False, ProcessID);
          if ProcessHandle <> 0 then
          begin
            TerminateProcess(ProcessHandle, 0);
            CloseHandle(ProcessHandle);
          end;
        end;
      end;
    end;
    
    // Close Configurator.exe processes
    if GetProcessList(ProcessList, 'Configurator.exe') then
    begin
      for I := 0 to ProcessList.Count - 1 do
      begin
        ProcessID := StrToIntDef(ProcessList[I], 0);
        if ProcessID <> 0 then
        begin
          ProcessHandle := OpenProcess(PROCESS_TERMINATE, False, ProcessID);
          if ProcessHandle <> 0 then
          begin
            TerminateProcess(ProcessHandle, 0);
            CloseHandle(ProcessHandle);
          end;
        end;
      end;
    end;
    
    // Wait for processes to close
    Sleep(2000);
  finally
    ProcessList.Free;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  
  if IsEliteMiningRunning then
  begin
    if MsgBox('EliteMining is currently running and must be closed before installation can continue.' + #13#10 + 
              'Would you like Setup to automatically close EliteMining?', 
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      if not CloseEliteMiningProcesses then
      begin
        Result := 'Failed to close EliteMining. Please close the application manually and try again.';
        Exit;
      end;
    end
    else
    begin
      Result := 'Installation cancelled. Please close EliteMining and run Setup again.';
      Exit;
    end;
  end;
end;
```

## Pre-Uninstallation Process Check

```pascal
function InitializeUninstall(): Boolean;
begin
  Result := True;
  
  if IsEliteMiningRunning then
  begin
    if MsgBox('EliteMining is currently running and must be closed before uninstallation can continue.' + #13#10 + 
              'Would you like to automatically close EliteMining?', 
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      if not CloseEliteMiningProcesses then
      begin
        MsgBox('Failed to close EliteMining. Please close the application manually and try uninstalling again.', 
               mbError, MB_OK);
        Result := False;
        Exit;
      end;
    end
    else
    begin
      MsgBox('Uninstallation cancelled. Please close EliteMining and try again.', 
             mbInformation, MB_OK);
      Result := False;
      Exit;
    end;
  end;
end;
```

## Required Helper Functions

Add these helper functions to get process lists (requires external DLL or Windows API calls):

```pascal
// Add to [Code] section top
const
  PROCESS_TERMINATE = $0001;

function OpenProcess(dwDesiredAccess: DWORD; bInheritHandle: BOOL; dwProcessId: DWORD): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function TerminateProcess(hProcess: THandle; uExitCode: UINT): BOOL;
  external 'TerminateProcess@kernel32.dll stdcall';
function CloseHandle(hObject: THandle): BOOL;
  external 'CloseHandle@kernel32.dll stdcall';
```

## Benefits

This integration provides:
- **Automatic Process Detection**: Checks for running EliteMining processes before install/uninstall
- **User Choice**: Asks user whether to automatically close or cancel
- **Graceful Termination**: Attempts clean shutdown before force termination
- **Error Handling**: Provides clear feedback if processes can't be closed
- **Professional Behavior**: Eliminates the file-locking error you encountered

## Alternative: Using PowerShell Script

You can also call the PowerShell uninstaller from Inno Setup:

```pascal
function ExecutePowerShellUninstaller: Boolean;
var
  ResultCode: Integer;
  PowerShellCmd: String;
begin
  PowerShellCmd := 'powershell.exe -ExecutionPolicy Bypass -File "' + 
                   ExpandConstant('{app}') + '\app\smart_uninstaller.ps1" -Silent';
  
  Result := Exec('cmd.exe', '/c ' + PowerShellCmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := Result and (ResultCode = 0);
end;
```

This ensures your installer handles running processes professionally, just like commercial software!

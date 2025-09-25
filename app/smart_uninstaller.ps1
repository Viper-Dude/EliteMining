# EliteMining Smart Uninstaller
# Provides intelligent uninstall with user data preservation options

param(
    [string]$InstallPath = "",
    [switch]$Complete = $false,
    [switch]$Silent = $false
)

$ErrorActionPreference = "Stop"

# Auto-detect installation path if not provided
if (-not $InstallPath) {
    Write-Host "Auto-detecting EliteMining installation path..." -ForegroundColor Yellow
    
    # Method 1: Check for running processes to detect path
    $runningProcesses = Get-Process -Name "EliteMining", "Configurator" -ErrorAction SilentlyContinue
    if ($runningProcesses) {
        foreach ($proc in $runningProcesses) {
            if ($proc.Path) {
                Write-Host "  Found process: $($proc.ProcessName) at $($proc.Path)" -ForegroundColor Gray
                $processDir = Split-Path $proc.Path -Parent
                
                # For Configurator, go up one level to get EliteMining root
                if ($proc.ProcessName -eq "Configurator") {
                    $processDir = Split-Path $processDir -Parent
                }
                
                # Verify this looks like an EliteMining installation
                $configFile = Join-Path $processDir "config.json"
                $appFolder = Join-Path $processDir "app"
                if ((Test-Path $configFile) -or (Test-Path $appFolder)) {
                    $InstallPath = $processDir
                    Write-Host "  ✅ Detected installation at: $InstallPath" -ForegroundColor Green
                    break
                }
            }
        }
    }
    
    # Method 2: Check if running from within an EliteMining installation
    if (-not $InstallPath) {
        $currentDir = $PWD.Path
        Write-Host "  Checking current directory: $currentDir" -ForegroundColor Gray
        
        # Look for parent directories that contain EliteMining files
        $checkDir = $currentDir
        while ($checkDir) {
            $configFile = Join-Path $checkDir "config.json"
            $appFolder = Join-Path $checkDir "app"
            if ((Test-Path $configFile) -or (Test-Path $appFolder)) {
                $InstallPath = $checkDir
                Write-Host "  ✅ Found installation in parent: $InstallPath" -ForegroundColor Green
                break
            }
            $parent = Split-Path $checkDir -Parent
            if ($parent -eq $checkDir) { break }  # Reached root
            $checkDir = $parent
        }
    }
    
    # Method 3: Default to current directory
    if (-not $InstallPath) {
        $InstallPath = $PWD.Path
        Write-Host "  ⚠️  Using current directory as fallback: $InstallPath" -ForegroundColor Yellow
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "EliteMining Smart Uninstaller" -ForegroundColor Cyan  
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Detected Installation Path: $InstallPath" -ForegroundColor Gray
Write-Host ""

function Get-UserChoice {
    if ($Silent) {
        return "smart"  # Default to smart uninstall in silent mode
    }
    
    if ($Complete) {
        return "complete"
    }
    
    Write-Host "Uninstall Options:" -ForegroundColor Yellow
    Write-Host "1. Smart Uninstall (Recommended)" -ForegroundColor Green
    Write-Host "   - Removes application files"
    Write-Host "   - Preserves Reports, Ship Presets, config.json"
    Write-Host "   - Clean removal with data safety"
    Write-Host ""
    Write-Host "2. Complete Removal" -ForegroundColor Red
    Write-Host "   - Deletes everything including user data"
    Write-Host "   - WARNING: All mining reports will be lost!"
    Write-Host ""
    Write-Host "3. Cancel" -ForegroundColor Gray
    Write-Host ""
    
    do {
        $choice = Read-Host "Choose option (1, 2, or 3)"
        switch ($choice) {
            "1" { return "smart" }
            "2" { return "complete" }
            "3" { return "cancel" }
            default { Write-Host "Invalid choice. Please enter 1, 2, or 3." -ForegroundColor Red }
        }
    } while ($true)
}

function Backup-UserData {
    param([string]$BackupPath)
    
    Write-Host "Creating backup of user data..." -ForegroundColor Yellow
    
    # Create backup directory
    New-Item -Path $BackupPath -ItemType Directory -Force | Out-Null
    
    $backedUp = @()
    
    # Backup Reports
    $reportsPath = Join-Path $InstallPath "app\Reports"
    if (Test-Path $reportsPath) {
        $backupReports = Join-Path $BackupPath "Reports"
        Copy-Item $reportsPath $backupReports -Recurse -Force
        $backedUp += "Reports folder"
        Write-Host "  ✅ Reports folder backed up" -ForegroundColor Green
    }
    
    # Backup Ship Presets
    $settingsPath = Join-Path $InstallPath "app\Ship Presets"
    if (Test-Path $settingsPath) {
        $backupSettings = Join-Path $BackupPath "Ship Presets"
        Copy-Item $settingsPath $backupSettings -Recurse -Force
        $backedUp += "Ship Presets folder"
        Write-Host "  ✅ Ship Presets folder backed up" -ForegroundColor Green
    }
    
    # Backup config.json
    $configPath = Join-Path $InstallPath "config.json"
    if (Test-Path $configPath) {
        $backupConfig = Join-Path $BackupPath "config.json"
        Copy-Item $configPath $backupConfig -Force
        $backedUp += "config.json"
        Write-Host "  ✅ config.json backed up" -ForegroundColor Green
    }
    
    # Backup Variables
    $variablesPath = Join-Path $InstallPath "Variables"
    if (Test-Path $variablesPath) {
        $backupVariables = Join-Path $BackupPath "Variables"
        Copy-Item $variablesPath $backupVariables -Recurse -Force
        $backedUp += "Variables folder"
        Write-Host "  ✅ Variables folder backed up" -ForegroundColor Green
    }
    
    return $backedUp
}

function Remove-ApplicationFiles {
    Write-Host "Removing application files..." -ForegroundColor Yellow
    
    $removed = @()
    $failed = @()
    
    # Remove main executable
    $mainExe = Join-Path $InstallPath "EliteMining.exe"
    if (Test-Path $mainExe) {
        try {
            Remove-Item $mainExe -Force
            $removed += "EliteMining.exe"
            Write-Host "  ✅ EliteMining.exe removed" -ForegroundColor Green
        } catch {
            $failed += "EliteMining.exe (Error: $($_.Exception.Message))"
            Write-Host "  ❌ Failed to remove EliteMining.exe" -ForegroundColor Red
        }
    }
    
    # Remove Configurator executable
    $configuratorExe = Join-Path $InstallPath "Configurator\Configurator.exe"
    if (Test-Path $configuratorExe) {
        try {
            Remove-Item $configuratorExe -Force
            $removed += "Configurator\Configurator.exe"
            Write-Host "  ✅ Configurator\Configurator.exe removed" -ForegroundColor Green
        } catch {
            $failed += "Configurator\Configurator.exe (Error: $($_.Exception.Message))"
            Write-Host "  ❌ Failed to remove Configurator\Configurator.exe" -ForegroundColor Red
        }
    }
    
    # Remove Python files
    $appPath = Join-Path $InstallPath "app"
    if (Test-Path $appPath) {
        try {
            Get-ChildItem $appPath -Filter "*.py" | Remove-Item -Force
            Get-ChildItem $appPath -Filter "*.pyc" | Remove-Item -Force
            Get-ChildItem $appPath -Filter "*.bat" | Remove-Item -Force
            Get-ChildItem $appPath -Filter "*.spec" | Remove-Item -Force
            Get-ChildItem $appPath -Filter "*.md" | Remove-Item -Force
            $removed += "Python and script files"
            Write-Host "  ✅ Python and script files removed" -ForegroundColor Green
        } catch {
            $failed += "Some Python/script files (Error: $($_.Exception.Message))"
            Write-Host "  ❌ Failed to remove some Python/script files" -ForegroundColor Red
        }
    }
    
    # Remove build artifacts and temporary folders
    $buildPaths = @("app\__pycache__", "app\build", "app\dist", "app\Images")
    foreach ($buildPath in $buildPaths) {
        $fullPath = Join-Path $InstallPath $buildPath
        if (Test-Path $fullPath) {
            try {
                Remove-Item $fullPath -Recurse -Force
                $removed += $buildPath
                Write-Host "  ✅ $buildPath removed" -ForegroundColor Green
            } catch {
                $failed += "$buildPath (Error: $($_.Exception.Message))"
                Write-Host "  ❌ Failed to remove $buildPath" -ForegroundColor Red
            }
        }
    }
    
    # Remove Configurator directory (keeping user data)
    $configuratorPath = Join-Path $InstallPath "Configurator"
    if (Test-Path $configuratorPath) {
        try {
            Remove-Item $configuratorPath -Recurse -Force
            $removed += "Configurator directory"
            Write-Host "  ✅ Configurator directory removed" -ForegroundColor Green
        } catch {
            $failed += "Configurator directory (Error: $($_.Exception.Message))"
            Write-Host "  ❌ Failed to remove Configurator directory" -ForegroundColor Red
        }
    }
    
    # Remove Doc folder (documentation)
    $docPath = Join-Path $InstallPath "Doc"
    if (Test-Path $docPath) {
        try {
            Remove-Item $docPath -Recurse -Force
            $removed += "Doc directory"
            Write-Host "  ✅ Doc directory removed" -ForegroundColor Green
        } catch {
            $failed += "Doc directory (Error: $($_.Exception.Message))"
            Write-Host "  ❌ Failed to remove Doc directory" -ForegroundColor Red
        }
    }
    
    Write-Host "  ✅ Application file removal completed" -ForegroundColor Green
    return @{
        "Removed" = $removed
        "Failed" = $failed
    }
}

function Restore-UserData {
    param([string]$BackupPath)
    
    Write-Host "Restoring user data..." -ForegroundColor Yellow
    
    # Ensure base directories exist
    New-Item -Path $InstallPath -ItemType Directory -Force | Out-Null
    New-Item -Path (Join-Path $InstallPath "app") -ItemType Directory -Force | Out-Null
    
    $restored = @()
    
    # Restore Reports
    $backupReports = Join-Path $BackupPath "Reports"
    if (Test-Path $backupReports) {
        $reportsPath = Join-Path $InstallPath "app\Reports"
        Copy-Item $backupReports $reportsPath -Recurse -Force
        $restored += "Reports"
        Write-Host "  ✅ Reports restored" -ForegroundColor Green
    }
    
    # Restore Ship Presets
    $backupSettings = Join-Path $BackupPath "Ship Presets"
    if (Test-Path $backupSettings) {
        $settingsPath = Join-Path $InstallPath "app\Ship Presets"
        Copy-Item $backupSettings $settingsPath -Recurse -Force
        $restored += "Ship Presets"
        Write-Host "  ✅ Ship Presets restored" -ForegroundColor Green
    }
    
    # Restore config.json
    $backupConfig = Join-Path $BackupPath "config.json"
    if (Test-Path $backupConfig) {
        $configPath = Join-Path $InstallPath "config.json"
        Copy-Item $backupConfig $configPath -Force
        $restored += "config.json"
        Write-Host "  ✅ config.json restored" -ForegroundColor Green
    }
    
    # Restore Variables
    $backupVariables = Join-Path $BackupPath "Variables"
    if (Test-Path $backupVariables) {
        $variablesPath = Join-Path $InstallPath "Variables"
        Copy-Item $backupVariables $variablesPath -Recurse -Force
        $restored += "Variables"
        Write-Host "  ✅ Variables restored" -ForegroundColor Green
    }
    
    # Create explanation file
    $readmePath = Join-Path $InstallPath "USER_DATA_PRESERVED.txt"
    $readmeContent = @"
EliteMining has been uninstalled but your user data was preserved:

- Mining session reports and history
- Personal settings and configurations  
- Ship setup presets
- VoiceAttack variables

This folder now contains only your personal data.

You can safely delete this folder if you no longer need this data.
To reinstall EliteMining, your settings will be automatically restored.

Uninstalled on: $(Get-Date)
Preserved items: $($restored -join ', ')
"@
    $readmeContent | Out-File $readmePath -Encoding UTF8
    
    # Clean up backup
    Remove-Item $BackupPath -Recurse -Force
    
    return $restored
}

function Stop-EliteMiningProcesses {
    Write-Host "Checking for running EliteMining processes..." -ForegroundColor Yellow
    
    $processes = @("EliteMining", "Configurator")
    $foundProcesses = @()
    
    foreach ($processName in $processes) {
        $runningProcesses = Get-Process -Name $processName -ErrorAction SilentlyContinue
        if ($runningProcesses) {
            $foundProcesses += $runningProcesses
            Write-Host "  Found: $($processName).exe (PID: $($runningProcesses.Id -join ', '))" -ForegroundColor Yellow
        }
    }
    
    if ($foundProcesses.Count -eq 0) {
        Write-Host "  ✅ No EliteMining processes running" -ForegroundColor Green
        return $true
    }
    
    Write-Host ""
    Write-Host "  ⚠️  Found running processes that must be closed:" -ForegroundColor Yellow
    foreach ($proc in $foundProcesses) {
        Write-Host "    - $($proc.ProcessName).exe (PID: $($proc.Id))" -ForegroundColor White
    }
    
    if (-not $Silent) {
        Write-Host ""
        Write-Host "EliteMining must be closed before uninstalling." -ForegroundColor Yellow
        Write-Host "Would you like to:" -ForegroundColor Yellow
        Write-Host "1. Automatically close EliteMining" -ForegroundColor Green
        Write-Host "2. Cancel uninstall (close manually)" -ForegroundColor Gray
        Write-Host ""
        
        do {
            $choice = Read-Host "Choose option (1 or 2)"
            switch ($choice) {
                "1" { 
                    Write-Host ""
                    Write-Host "Closing EliteMining processes..." -ForegroundColor Yellow
                    
                    $closeSuccess = $true
                    foreach ($proc in $foundProcesses) {
                        try {
                            Write-Host "  Closing $($proc.ProcessName).exe..." -ForegroundColor Gray
                            
                            # Try graceful close first
                            if ($proc.CloseMainWindow()) {
                                Write-Host "    Sent close signal, waiting..." -ForegroundColor Gray
                                $proc.WaitForExit(5000)  # Wait up to 5 seconds
                            }
                            
                            # Check if still running
                            $stillRunning = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
                            if ($stillRunning) {
                                Write-Host "    Process still running, force terminating..." -ForegroundColor Yellow
                                $stillRunning.Kill()
                                $stillRunning.WaitForExit(3000)  # Wait up to 3 seconds
                            }
                            
                            # Final check
                            $finalCheck = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
                            if (-not $finalCheck) {
                                Write-Host "  ✅ Successfully closed $($proc.ProcessName).exe" -ForegroundColor Green
                            } else {
                                Write-Host "  ❌ Failed to close $($proc.ProcessName).exe" -ForegroundColor Red
                                $closeSuccess = $false
                            }
                            
                        } catch {
                            Write-Host "  ❌ Error closing $($proc.ProcessName).exe: $($_.Exception.Message)" -ForegroundColor Red
                            $closeSuccess = $false
                        }
                    }
                    
                    if (-not $closeSuccess) {
                        Write-Host ""
                        Write-Host "⚠️  Some processes could not be closed automatically." -ForegroundColor Yellow
                        Write-Host "Please close them manually and run the uninstaller again." -ForegroundColor Yellow
                        return $false
                    }
                    
                    # Wait a bit more for file handles to release
                    Write-Host "  Waiting for file handles to release..." -ForegroundColor Gray
                    Start-Sleep -Seconds 3
                    return $true
                }
                "2" { 
                    Write-Host "Uninstall cancelled. Please close EliteMining manually and try again." -ForegroundColor Yellow
                    return $false
                }
                default { Write-Host "Invalid choice. Please enter 1 or 2." -ForegroundColor Red }
            }
        } while ($true)
    } else {
        # Silent mode - automatically close processes
        Write-Host ""
        Write-Host "Automatically closing EliteMining processes..." -ForegroundColor Yellow
        
        $closeSuccess = $true
        foreach ($proc in $foundProcesses) {
            try {
                Write-Host "  Closing $($proc.ProcessName).exe..." -ForegroundColor Gray
                
                # Try graceful close first
                if ($proc.CloseMainWindow()) {
                    $proc.WaitForExit(5000)  # Wait up to 5 seconds
                }
                
                # Check if still running
                $stillRunning = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
                if ($stillRunning) {
                    $stillRunning.Kill()
                    $stillRunning.WaitForExit(3000)  # Wait up to 3 seconds
                }
                
                # Final check
                $finalCheck = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
                if (-not $finalCheck) {
                    Write-Host "  ✅ Successfully closed $($proc.ProcessName).exe" -ForegroundColor Green
                } else {
                    Write-Host "  ❌ Failed to close $($proc.ProcessName).exe" -ForegroundColor Red
                    $closeSuccess = $false
                }
                
            } catch {
                Write-Host "  ❌ Error closing $($proc.ProcessName).exe: $($_.Exception.Message)" -ForegroundColor Red
                $closeSuccess = $false
            }
        }
        
        if (-not $closeSuccess) {
            return $false
        }
        
        Start-Sleep -Seconds 3
        return $true
    }
}

# Main execution
try {
    # First, handle running processes
    if (-not (Stop-EliteMiningProcesses)) {
        exit 0
    }
    
    $choice = Get-UserChoice
    
    switch ($choice) {
        "smart" {
            Write-Host "Performing smart uninstall..." -ForegroundColor Green
            
            # Create temporary backup
            $backupPath = Join-Path $env:TEMP "EliteMining_UserData_Backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
            
            # Backup user data
            $backedUp = Backup-UserData -BackupPath $backupPath
            
            # Remove application files
            $removalResult = Remove-ApplicationFiles
            $removed = $removalResult.Removed
            $failed = $removalResult.Failed
            
            # Restore user data to clean structure
            $restored = Restore-UserData -BackupPath $backupPath
            
            Write-Host ""
            Write-Host "Smart uninstall completed!" -ForegroundColor Green
            Write-Host "Preserved user data:" -ForegroundColor Cyan
            foreach ($item in $restored) {
                Write-Host "  - $item" -ForegroundColor White
            }
            
            # Show manual cleanup message if needed
            if ($failed.Count -gt 0) {
                Write-Host ""
                Write-Host "⚠️  MANUAL CLEANUP REQUIRED" -ForegroundColor Yellow -BackgroundColor DarkRed
                Write-Host "Some files could not be automatically removed and must be deleted manually:" -ForegroundColor Yellow
                foreach ($item in $failed) {
                    Write-Host "  - $item" -ForegroundColor Red
                }
                Write-Host ""
                Write-Host "Please delete these files manually from:" -ForegroundColor Yellow
                Write-Host "  $InstallPath" -ForegroundColor White
                Write-Host ""
                Write-Host "Common causes:" -ForegroundColor Gray
                Write-Host "  • Files are still in use by another process" -ForegroundColor Gray
                Write-Host "  • Insufficient permissions" -ForegroundColor Gray
                Write-Host "  • Files are locked by Windows" -ForegroundColor Gray
                Write-Host ""
            }
            
            Write-Host ""
            Write-Host "See USER_DATA_PRESERVED.txt for details." -ForegroundColor Gray
        }
        
        "complete" {
            # Double confirmation for complete removal
            if (-not $Silent) {
                Write-Host ""
                Write-Host "⚠️  WARNING: COMPLETE REMOVAL" -ForegroundColor Red -BackgroundColor Yellow
                Write-Host "This will delete ALL your mining reports and settings!" -ForegroundColor Red
                Write-Host "This includes months of valuable mining session data!" -ForegroundColor Red
                Write-Host ""
                $confirm = Read-Host "Type 'DELETE ALL' to confirm complete removal"
                
                if ($confirm -ne "DELETE ALL") {
                    Write-Host "Complete removal cancelled." -ForegroundColor Yellow
                    exit 0
                }
            }
            
            Write-Host "Performing complete removal..." -ForegroundColor Red
            
            # Remove everything
            if (Test-Path $InstallPath) {
                Remove-Item $InstallPath -Recurse -Force
                Write-Host "✅ Complete removal finished" -ForegroundColor Green
            }
        }
        
        "cancel" {
            Write-Host "Uninstall cancelled." -ForegroundColor Yellow
            exit 0
        }
    }
    
    Write-Host ""
    Write-Host "Uninstall process completed." -ForegroundColor Cyan
    
} catch {
    Write-Host ""
    Write-Host "❌ Error during uninstall: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

if (-not $Silent) {
    Write-Host ""
    Write-Host "Press any key to continue..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

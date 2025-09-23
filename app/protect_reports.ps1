# EliteMining Reports Protection Script (PowerShell)
# Protects Reports folder during installation/uninstallation

param(
    [string]$InstallDir = $PWD,
    [string]$Action = "backup",
    [string]$BackupLocation = ""
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "EliteMining Reports Protection" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Installation Directory: $InstallDir"
Write-Host "Action: $Action"
Write-Host ""

# Normalize paths
$InstallDir = Resolve-Path $InstallDir -ErrorAction SilentlyContinue
if (-not $InstallDir) {
    Write-Host "❌ Invalid installation directory" -ForegroundColor Red
    exit 1
}

$ReportsDir = Join-Path $InstallDir "app\Reports"
$BackupInfoFile = Join-Path $InstallDir "reports_backup_info.json"

function Create-ReportsBackup {
    param([string]$BackupPath = "")
    
    if (-not (Test-Path $ReportsDir)) {
        Write-Host "No Reports folder found to backup" -ForegroundColor Yellow
        return $null
    }
    
    # Generate backup location if not provided
    if ([string]::IsNullOrEmpty($BackupPath)) {
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $BackupPath = Join-Path $env:TEMP "EliteMining_Reports_Backup_$timestamp"
    }
    
    try {
        # Create backup directory
        New-Item -Path $BackupPath -ItemType Directory -Force | Out-Null
        
        # Copy Reports folder
        $BackupReports = Join-Path $BackupPath "Reports"
        Copy-Item -Path $ReportsDir -Destination $BackupReports -Recurse -Force
        
        # Count files
        $FileCount = (Get-ChildItem -Path $BackupReports -Recurse -File).Count
        
        # Save backup info
        $BackupInfo = @{
            backup_time = (Get-Date).ToString("o")
            backup_location = $BackupPath
            original_location = $ReportsDir
            files_count = $FileCount
        }
        
        $BackupInfo | ConvertTo-Json -Depth 2 | Out-File -FilePath $BackupInfoFile -Encoding UTF8
        
        Write-Host "✅ Reports backup created at: $BackupPath" -ForegroundColor Green
        Write-Host "   Files backed up: $FileCount" -ForegroundColor Green
        
        return $BackupPath
    }
    catch {
        Write-Host "❌ Error creating backup: $($_.Exception.Message)" -ForegroundColor Red
        return $null
    }
}

function Restore-ReportsBackup {
    param([string]$BackupPath = "")
    
    # Load backup info if available
    if ([string]::IsNullOrEmpty($BackupPath) -and (Test-Path $BackupInfoFile)) {
        try {
            $BackupInfo = Get-Content $BackupInfoFile | ConvertFrom-Json
            $BackupPath = $BackupInfo.backup_location
        }
        catch {
            Write-Host "Warning: Could not read backup info: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
    
    if ([string]::IsNullOrEmpty($BackupPath)) {
        Write-Host "❌ No backup location specified and no backup info found" -ForegroundColor Red
        return $false
    }
    
    $BackupReports = Join-Path $BackupPath "Reports"
    
    if (-not (Test-Path $BackupReports)) {
        Write-Host "❌ Backup not found at: $BackupReports" -ForegroundColor Red
        return $false
    }
    
    try {
        # Create app directory if it doesn't exist
        $AppDir = Split-Path $ReportsDir -Parent
        New-Item -Path $AppDir -ItemType Directory -Force | Out-Null
        
        # Remove existing Reports if present
        if (Test-Path $ReportsDir) {
            Remove-Item -Path $ReportsDir -Recurse -Force
        }
        
        # Restore from backup
        Copy-Item -Path $BackupReports -Destination $ReportsDir -Recurse -Force
        
        $FilesRestored = (Get-ChildItem -Path $ReportsDir -Recurse -File).Count
        Write-Host "✅ Reports folder restored successfully" -ForegroundColor Green
        Write-Host "   Files restored: $FilesRestored" -ForegroundColor Green
        
        # Clean up backup info file
        if (Test-Path $BackupInfoFile) {
            Remove-Item $BackupInfoFile -Force
        }
        
        return $true
    }
    catch {
        Write-Host "❌ Error restoring backup: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

function Merge-ReportsWithBackup {
    param([string]$BackupPath = "")
    
    # Load backup info if available
    if ([string]::IsNullOrEmpty($BackupPath) -and (Test-Path $BackupInfoFile)) {
        try {
            $BackupInfo = Get-Content $BackupInfoFile | ConvertFrom-Json
            $BackupPath = $BackupInfo.backup_location
        }
        catch {
            Write-Host "Warning: Could not read backup info" -ForegroundColor Yellow
        }
    }
    
    if ([string]::IsNullOrEmpty($BackupPath)) {
        Write-Host "❌ No backup location specified" -ForegroundColor Red
        return $false
    }
    
    $BackupReports = Join-Path $BackupPath "Reports"
    
    if (-not (Test-Path $BackupReports)) {
        Write-Host "❌ Backup not found at: $BackupReports" -ForegroundColor Red
        return $false
    }
    
    try {
        # Ensure Reports directory exists
        New-Item -Path $ReportsDir -ItemType Directory -Force | Out-Null
        
        # Merge files from backup
        $FilesMerged = 0
        $BackupFiles = Get-ChildItem -Path $BackupReports -Recurse -File
        
        foreach ($BackupFile in $BackupFiles) {
            $RelativePath = $BackupFile.FullName.Substring($BackupReports.Length + 1)
            $TargetFile = Join-Path $ReportsDir $RelativePath
            
            # Create parent directories if needed
            $TargetDir = Split-Path $TargetFile -Parent
            New-Item -Path $TargetDir -ItemType Directory -Force | Out-Null
            
            # Copy if file doesn't exist or backup is newer
            if (-not (Test-Path $TargetFile) -or $BackupFile.LastWriteTime -gt (Get-Item $TargetFile).LastWriteTime) {
                Copy-Item -Path $BackupFile.FullName -Destination $TargetFile -Force
                $FilesMerged++
            }
        }
        
        Write-Host "✅ Reports folders merged successfully" -ForegroundColor Green
        Write-Host "   Files merged: $FilesMerged" -ForegroundColor Green
        
        # Clean up backup info file
        if (Test-Path $BackupInfoFile) {
            Remove-Item $BackupInfoFile -Force
        }
        
        return $true
    }
    catch {
        Write-Host "❌ Error merging backup: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

# Main execution
switch ($Action.ToLower()) {
    "backup" {
        $BackupPath = Create-ReportsBackup -BackupPath $BackupLocation
        if ($BackupPath) {
            Write-Host ""
            Write-Host "Backup created successfully!" -ForegroundColor Green
            Write-Host "To restore later, run:" -ForegroundColor Cyan
            Write-Host "  .\protect_reports.ps1 -Action restore -BackupLocation '$BackupPath'" -ForegroundColor Cyan
        } else {
            Write-Host ""
            Write-Host "Failed to create backup" -ForegroundColor Red
            exit 1
        }
    }
    
    "restore" {
        if (Restore-ReportsBackup -BackupPath $BackupLocation) {
            Write-Host ""
            Write-Host "Reports folder restored successfully!" -ForegroundColor Green
        } else {
            Write-Host ""
            Write-Host "Failed to restore Reports folder" -ForegroundColor Red
            exit 1
        }
    }
    
    "merge" {
        if (Merge-ReportsWithBackup -BackupPath $BackupLocation) {
            Write-Host ""
            Write-Host "Reports folders merged successfully!" -ForegroundColor Green
        } else {
            Write-Host ""
            Write-Host "Failed to merge Reports folders" -ForegroundColor Red
            exit 1
        }
    }
    
    default {
        Write-Host "❌ Unknown action: $Action" -ForegroundColor Red
        Write-Host "Use: backup, restore, or merge" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host ""
Write-Host "Reports protection script completed." -ForegroundColor Cyan

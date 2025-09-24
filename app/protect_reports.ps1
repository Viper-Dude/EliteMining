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

function New-ReportsBackup {
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
        
        # Count files by type for detailed reporting
        $FileCounts = Get-FileCountsByType -Path $BackupReports
        $TotalFiles = ($FileCounts.Values | Measure-Object -Sum).Sum
        
        # Save backup info with file breakdown
        $BackupInfo = @{
            backup_time = (Get-Date).ToString("o")
            backup_location = $BackupPath
            original_location = $ReportsDir
            files_count = $TotalFiles
            file_breakdown = $FileCounts
        }
        
        $BackupInfo | ConvertTo-Json -Depth 2 | Out-File -FilePath $BackupInfoFile -Encoding UTF8
        
        Write-Host "✅ Reports backup created at: $BackupPath" -ForegroundColor Green
        Write-Host "   Total files backed up: $TotalFiles" -ForegroundColor Green
        Write-FileBreakdown -FileCounts $FileCounts
        
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
        
        # Count restored files with breakdown
        $FileCounts = Get-FileCountsByType -Path $ReportsDir
        $TotalFiles = ($FileCounts.Values | Measure-Object -Sum).Sum
        
        Write-Host "✅ Reports folder restored successfully" -ForegroundColor Green
        Write-Host "   Total files restored: $TotalFiles" -ForegroundColor Green
        Write-FileBreakdown -FileCounts $FileCounts
        
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

function Get-FileCountsByType {
    param([string]$Path)
    
    $FileCounts = @{
        session_reports = 0
        screenshots = 0
        graphs = 0
        csv_files = 0
        json_files = 0
        other = 0
    }
    
    $AllFiles = Get-ChildItem -Path $Path -Recurse -File
    
    foreach ($File in $AllFiles) {
        $FileName = $File.Name.ToLower()
        $FileExt = $File.Extension.ToLower()
        $FilePath = $File.FullName.ToLower()
        
        if ($FilePath -like "*mining session*" -and $FileExt -eq ".txt") {
            $FileCounts.session_reports++
        }
        elseif ($FilePath -like "*screenshot*" -and $FileExt -in @(".png", ".jpg", ".jpeg")) {
            $FileCounts.screenshots++
        }
        elseif ($File.Directory.Name -eq "Graphs" -and $FileExt -eq ".png") {
            $FileCounts.graphs++
        }
        elseif ($FileExt -eq ".csv") {
            $FileCounts.csv_files++
        }
        elseif ($FileExt -eq ".json") {
            $FileCounts.json_files++
        }
        else {
            $FileCounts.other++
        }
    }
    
    return $FileCounts
}

function Write-FileBreakdown {
    param($FileCounts)
    
    if ($FileCounts.session_reports -gt 0) {
        Write-Host "   • Session reports: $($FileCounts.session_reports)" -ForegroundColor Green
    }
    if ($FileCounts.screenshots -gt 0) {
        Write-Host "   • Screenshots: $($FileCounts.screenshots)" -ForegroundColor Green
    }
    if ($FileCounts.graphs -gt 0) {
        Write-Host "   • Mining graphs: $($FileCounts.graphs)" -ForegroundColor Green
    }
    if ($FileCounts.csv_files -gt 0) {
        Write-Host "   • CSV index files: $($FileCounts.csv_files)" -ForegroundColor Green
    }
    if ($FileCounts.json_files -gt 0) {
        Write-Host "   • Configuration files: $($FileCounts.json_files)" -ForegroundColor Green
    }
    if ($FileCounts.other -gt 0) {
        Write-Host "   • Other files: $($FileCounts.other)" -ForegroundColor Green
    }
}

# Main execution
switch ($Action.ToLower()) {
    "backup" {
        $BackupPath = New-ReportsBackup -BackupPath $BackupLocation
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

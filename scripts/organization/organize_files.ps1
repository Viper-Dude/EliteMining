# EliteMining File Organization Script
# This script organizes development/test files into proper folders
# A rollback script will be created automatically

$ErrorActionPreference = "Stop"
$rootDir = $PSScriptRoot
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $rootDir "organization_log_$timestamp.txt"
$rollbackFile = Join-Path $rootDir "ROLLBACK_organization.ps1"

function Write-Log {
    param($Message)
    $logMessage = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Host $logMessage
    Add-Content -Path $logFile -Value $logMessage
}

function Move-FileWithLogging {
    param(
        [string]$Source,
        [string]$Destination
    )
    
    $sourcePath = Join-Path $rootDir $Source
    $destPath = Join-Path $rootDir $Destination
    
    if (Test-Path $sourcePath) {
        # Create destination directory if it doesn't exist
        $destDir = Split-Path -Parent $destPath
        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            Write-Log "Created directory: $destDir"
        }
        
        # Move the file
        Move-Item -Path $sourcePath -Destination $destPath -Force
        Write-Log "MOVED: $Source -> $Destination"
        
        # Add to rollback script
        $rollbackLine = "Move-Item -Path `"$destPath`" -Destination `"$sourcePath`" -Force"
        Add-Content -Path $rollbackFile -Value $rollbackLine
        
        return $true
    } else {
        Write-Log "SKIPPED (not found): $Source"
        return $false
    }
}

# Initialize
Write-Log "=== EliteMining File Organization Started ==="
Write-Log "Root directory: $rootDir"
Write-Log "Log file: $logFile"
Write-Log "Rollback script: $rollbackFile"

# Create rollback script header
@"
# ROLLBACK SCRIPT - Generated $timestamp
# Run this script to undo the file organization
`$ErrorActionPreference = "Stop"
Write-Host "Rolling back file organization..." -ForegroundColor Yellow

"@ | Set-Content -Path $rollbackFile

Write-Log "`n=== Creating folder structure ==="

# Create folder structure
$folders = @(
    "scripts",
    "scripts\database",
    "scripts\database\checks",
    "scripts\database\maintenance",
    "scripts\cleanup",
    "scripts\tools",
    "scripts\build",
    "scripts\installer",
    "scripts\testing",
    "docs",
    "docs\implementation",
    "docs\debug",
    "docs\features"
)

foreach ($folder in $folders) {
    $folderPath = Join-Path $rootDir $folder
    if (-not (Test-Path $folderPath)) {
        New-Item -ItemType Directory -Path $folderPath -Force | Out-Null
        Write-Log "Created folder: $folder"
    }
}

Write-Log "`n=== Moving database check scripts ==="
Move-FileWithLogging "check_backup.py" "scripts\database\checks\check_backup.py"
Move-FileWithLogging "check_current_materials.py" "scripts\database\checks\check_current_materials.py"
Move-FileWithLogging "check_db_status.py" "scripts\database\checks\check_db_status.py"
Move-FileWithLogging "check_excel_body_names.py" "scripts\database\checks\check_excel_body_names.py"
Move-FileWithLogging "check_hr4977.py" "scripts\database\checks\check_hr4977.py"
Move-FileWithLogging "check_lowercase_bodies.py" "scripts\database\checks\check_lowercase_bodies.py"
Move-FileWithLogging "check_opals.py" "scripts\database\checks\check_opals.py"
Move-FileWithLogging "check_ring_data.py" "scripts\database\checks\check_ring_data.py"
Move-FileWithLogging "check_system.py" "scripts\database\checks\check_system.py"

Write-Log "`n=== Moving database maintenance scripts ==="
Move-FileWithLogging "run_fix.py" "scripts\database\maintenance\run_fix.py"
Move-FileWithLogging "find_any_lowercase.py" "scripts\database\maintenance\find_any_lowercase.py"
Move-FileWithLogging "find_lowercase_rings.py" "scripts\database\maintenance\find_lowercase_rings.py"
Move-FileWithLogging "fix_body_names.py" "scripts\database\maintenance\fix_body_names.py"
Move-FileWithLogging "fix_material_names.py" "scripts\database\maintenance\fix_material_names.py"

Write-Log "`n=== Moving database creation scripts ==="
Move-FileWithLogging "import_excel_to_database.py" "scripts\database\import_excel_to_database.py"
Move-FileWithLogging "init_database.py" "scripts\database\init_database.py"
Move-FileWithLogging "app\create_bubble_database.py" "scripts\database\create_bubble_database.py"
Move-FileWithLogging "app\migrate_excel_to_db.py" "scripts\database\migrate_excel_to_db.py"
Move-FileWithLogging "app\add_hotspot_columns.py" "scripts\database\add_hotspot_columns.py"

Write-Log "`n=== Moving cleanup scripts ==="
Move-FileWithLogging "app\clear_user_data_db.py" "scripts\cleanup\clear_user_data_db.py"

Write-Log "`n=== Moving tools ==="
Move-FileWithLogging "app\check_versions.py" "scripts\tools\check_versions.py"
Move-FileWithLogging "app\process_journals.py" "scripts\tools\process_journals.py"

Write-Log "`n=== Moving build scripts ==="
Move-FileWithLogging "app\build_executable.py" "scripts\build\build_executable.py"
Move-FileWithLogging "app\verify_installer.py" "scripts\build\verify_installer.py"

Write-Log "`n=== Moving installer scripts ==="
Move-FileWithLogging "app\config_installer.py" "scripts\installer\config_installer.py"
Move-FileWithLogging "app\config_installer.bat" "scripts\installer\config_installer.bat"

Write-Log "`n=== Moving test scripts ==="
Move-FileWithLogging "test_auto_scan.py" "scripts\testing\test_auto_scan.py"

Write-Log "`n=== Moving documentation - Implementation ==="
Move-FileWithLogging "ENHANCED_RING_FINDER_IMPLEMENTATION.md" "docs\implementation\ENHANCED_RING_FINDER_IMPLEMENTATION.md"
Move-FileWithLogging "ENHANCED_RING_FINDER.md" "docs\implementation\ENHANCED_RING_FINDER.md"
Move-FileWithLogging "GALAXY_DATABASE_IMPLEMENTATION.md" "docs\implementation\GALAXY_DATABASE_IMPLEMENTATION.md"
Move-FileWithLogging "RING_DENSITY_IMPLEMENTATION.md" "docs\implementation\RING_DENSITY_IMPLEMENTATION.md"
Move-FileWithLogging "JOURNAL_PATH_CHANGE_IMPLEMENTATION.md" "docs\implementation\JOURNAL_PATH_CHANGE_IMPLEMENTATION.md"
Move-FileWithLogging "JOURNAL_PATH_IMPLEMENTATION_COMPLETE.md" "docs\implementation\JOURNAL_PATH_IMPLEMENTATION_COMPLETE.md"
Move-FileWithLogging "LOGGING_IMPLEMENTATION.md" "docs\implementation\LOGGING_IMPLEMENTATION.md"
Move-FileWithLogging "MIGRATION_NOTES.md" "docs\implementation\MIGRATION_NOTES.md"
Move-FileWithLogging "ICON_STANDARDS.md" "docs\implementation\ICON_STANDARDS.md"
Move-FileWithLogging "INSTALLER_COMPLETENESS_CHECK.md" "docs\implementation\INSTALLER_COMPLETENESS_CHECK.md"

Write-Log "`n=== Moving documentation - Debug/Analysis ==="
Move-FileWithLogging "RING_SEARCH_ANALYSIS.md" "docs\debug\RING_SEARCH_ANALYSIS.md"
Move-FileWithLogging "RING_SEARCH_SORT_ORDER_ANALYSIS.md" "docs\debug\RING_SEARCH_SORT_ORDER_ANALYSIS.md"
Move-FileWithLogging "RING_FINDER_DEBUG_SESSION_SUMMARY.md" "docs\debug\RING_FINDER_DEBUG_SESSION_SUMMARY.md"
Move-FileWithLogging "JOURNAL_PATH_BUG_ANALYSIS.md" "docs\debug\JOURNAL_PATH_BUG_ANALYSIS.md"
Move-FileWithLogging "OLD_ANNOUNCEMENT_BUG_ANALYSIS.md" "docs\debug\OLD_ANNOUNCEMENT_BUG_ANALYSIS.md"

Write-Log "`n=== Moving documentation - Features ==="
Move-FileWithLogging "app\CONFIG_MANAGEMENT.md" "docs\features\CONFIG_MANAGEMENT.md"
Move-FileWithLogging "app\INSTALLER_INTEGRATION.md" "docs\features\INSTALLER_INTEGRATION.md"
Move-FileWithLogging "app\INSTALLER_PROCESS_HANDLING.md" "docs\features\INSTALLER_PROCESS_HANDLING.md"
Move-FileWithLogging "app\REPORTS_PROTECTION.md" "docs\features\REPORTS_PROTECTION.md"
Move-FileWithLogging "app\SMART_UNINSTALLER_README.md" "docs\features\SMART_UNINSTALLER_README.md"

# Finalize rollback script
Add-Content -Path $rollbackFile -Value "`nWrite-Host 'Rollback complete!' -ForegroundColor Green"
Add-Content -Path $rollbackFile -Value "Write-Host 'Files restored to original locations.' -ForegroundColor Green"

Write-Log "`n=== Organization Complete ==="
Write-Log "Total operations logged to: $logFile"
Write-Log "Rollback script created: $rollbackFile"
Write-Log "`nTo undo these changes, run: .\$rollbackFile"

Write-Host "`n===============================================" -ForegroundColor Green
Write-Host "File organization complete!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host "Log file: $logFile" -ForegroundColor Cyan
Write-Host "Rollback script: $rollbackFile" -ForegroundColor Yellow
Write-Host "`nIf anything breaks, run:" -ForegroundColor Yellow
Write-Host "  .\ROLLBACK_organization.ps1" -ForegroundColor Yellow
Write-Host "===============================================`n" -ForegroundColor Green

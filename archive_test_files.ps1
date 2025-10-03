# Archive Test Files Script
# Moves development/test files to _archived_test_files folder
# Run this script from the project root directory

$archiveFolder = "_archived_test_files"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$archivePath = Join-Path $archiveFolder $timestamp

# Create archive directory
Write-Host "Creating archive directory: $archivePath" -ForegroundColor Cyan
New-Item -Path $archivePath -ItemType Directory -Force | Out-Null

# List of files to archive
$filesToArchive = @(
    # Database Testing/Cleanup
    "analyze_journal_ring_data.py",
    "check_all_7a_records.py",
    "check_columns.py",
    "check_data_source.py",
    "check_density_status.py",
    "check_excel_delkar.py",
    "check_malformed_rings.py",
    "check_ring_mass.py",
    "check_ring_types.py",
    "check_serpentis.py",
    "check_tollan.py",
    "cleanup_hotspot_data.py",
    "cleanup_user_db.py",
    "cleanup_user_db_v2.py",
    "clean_database.py",
    "clean_import_corrected.py",
    "combine_corrected_materials.py",
    "combine_materials.py",
    "complete_database_update.py",
    "comprehensive_merge.py",
    "create_clean_user_database.py",
    "create_new_user_db.py",
    "fix_malformed_ring_names.py",
    "fresh_import_corrected.py",
    "normalize_database_body_names.py",
    "validate_cleaning.py",
    
    # Debug/Search Scripts
    "debug_coord_source.py",
    "debug_ltd_search.py",
    "debug_paesia_search.py",
    "search_coalsack.py",
    "search_excel.py",
    "search_tollan_journals.py",
    "investigate_delkar.py",
    "query_paesia.py",
    
    # Data Extraction Scripts
    "extract_alexandrite_43urls.py",
    "extract_alexandrite_new_refs.py",
    "extract_all_corrected_urls.py",
    "extract_all_materials.py",
    "extract_all_materials_complete.py",
    "extract_all_materials_corrected.py",
    "extract_complete_gaps.py",
    "extract_edtools_data.py",
    "extract_edtools_improved.py",
    "extract_gaps_strategic.py",
    "extract_lhs501_data.py",
    "extract_platinum_paesia.py",
    "extract_platinum_proper.py",
    "extract_priority_test.py",
    "extract_remaining_corrected.py",
    "extract_user_db.py",
    "merge_alexandrite_data.py",
    "merge_gaps_to_excel.py",
    "merge_parsed_data.py",
    "parse_all_gaps.py",
    "remove_journal_imports.py",
    "show_results.py",
    "step1_final.py",
    "step1_remove_imports.py",
    
    # Test Files
    "test_coalsack_density.py",
    "test_coalsack_search.py",
    "test_database_cleaned.py",
    "test_database_direct.py",
    "test_database_schema.py",
    "test_density_calculation.py",
    "test_fixed_parsing.py",
    "test_journal_density.py",
    "test_ls_column.py",
    "test_material_dropdown.py",
    "test_material_filter.py",
    "test_material_filtering.py",
    "test_material_matching.py",
    "test_new_database.py",
    "test_ring_finder_cleaned.py",
    "test_ring_finder_complete.py",
    "test_ring_name_cleaning.py",
    "test_user_db_search.py",
    "test_user_data.db",
    
    # Temporary/Data Files
    "temp_coalsack_api.json",
    "temp_coalsack_api2.json",
    "painite_urls.txt",
    "Platinum_extracted.xlsx",
    "user_db_hotspot_data_20250928_235427.csv",
    "user_db_sqlite_sequence_20250928_235427.csv",
    "user_db_visited_systems_20250928_235427.csv"
)

# Counter for statistics
$movedCount = 0
$notFoundCount = 0
$errorCount = 0

Write-Host "`nStarting to archive files..." -ForegroundColor Green
Write-Host "Total files to process: $($filesToArchive.Count)" -ForegroundColor Yellow

foreach ($file in $filesToArchive) {
    if (Test-Path $file) {
        try {
            Move-Item -Path $file -Destination $archivePath -Force
            Write-Host "✓ Moved: $file" -ForegroundColor Green
            $movedCount++
        }
        catch {
            Write-Host "✗ Error moving: $file - $($_.Exception.Message)" -ForegroundColor Red
            $errorCount++
        }
    }
    else {
        Write-Host "⊘ Not found: $file" -ForegroundColor DarkGray
        $notFoundCount++
    }
}

# Create a README in the archive folder
$readmeContent = @"
# Archived Test Files - $timestamp

This folder contains development and test files that were archived to clean up the project workspace.

## Statistics
- Files moved: $movedCount
- Files not found: $notFoundCount
- Errors: $errorCount

## Important Files Kept in Project Root
- import_excel_to_database.py (utility script)
- All build scripts
- All documentation (.md files)
- Production configuration files

## Archive Date
$(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

## Note
These files can be safely deleted if not needed, or kept for reference.
They are primarily:
- Database testing/cleanup scripts
- Debug/search utilities
- Data extraction scripts
- Unit test files
- Temporary data files
"@

Set-Content -Path (Join-Path $archivePath "README.md") -Value $readmeContent

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Archive Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Files moved:     $movedCount" -ForegroundColor Green
Write-Host "Files not found: $notFoundCount" -ForegroundColor DarkGray
Write-Host "Errors:          $errorCount" -ForegroundColor $(if ($errorCount -gt 0) { "Red" } else { "Green" })
Write-Host "`nArchived to: $archivePath" -ForegroundColor Yellow
Write-Host "`nYou can safely delete the archive folder if you don't need these files." -ForegroundColor Cyan

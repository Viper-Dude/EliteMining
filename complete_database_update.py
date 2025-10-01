#!/usr/bin/env python3
"""
Complete Merge Process - Runs both steps automatically
Step 1: Merge gap files → all_materials_hotspots.xlsx
Step 2: Import Excel → user_data.db
"""

import subprocess
import sys
from pathlib import Path

def run_script(script_name, description):
    """Run a Python script and return success status"""
    print(f"\n{'='*60}")
    print(f"RUNNING: {description}")
    print(f"{'='*60}")
    
    try:
        # Use the same Python executable we're running with
        python_exe = sys.executable
        result = subprocess.run([python_exe, script_name], 
                              capture_output=False, 
                              text=True, 
                              cwd=Path.cwd())
        
        if result.returncode == 0:
            print(f"✓ SUCCESS: {description}")
            return True
        else:
            print(f"✗ FAILED: {description} (exit code: {result.returncode})")
            return False
            
    except Exception as e:
        print(f"✗ ERROR running {script_name}: {e}")
        return False

def check_extraction_complete():
    """Check if the extraction has completed"""
    gap_dir = Path("app/data/Hotspots/all_materials_gaps")
    
    if not gap_dir.exists():
        print("❌ Extraction not complete - gap directory not found")
        return False
    
    # Check for expected gap files
    expected_materials = [
        "Alexandrite", "Painite", "Platinum", "LowTemperatureDiamond", "Tritium",
        "Osmium", "Rhodplumsite", "Serendibite", "Monazite", "Musgravite", 
        "Bixbite", "Jadeite", "Opal", "Bromellite"
    ]
    
    gap_files = list(gap_dir.glob("*_complete_gaps.xlsx"))
    found_materials = [f.stem.replace('_complete_gaps', '') for f in gap_files]
    
    print(f"Gap extraction status:")
    print(f"  Expected materials: {len(expected_materials)}")
    print(f"  Found gap files: {len(gap_files)}")
    
    missing_materials = set(expected_materials) - set(found_materials)
    if missing_materials:
        print(f"  Missing materials: {missing_materials}")
        print("❌ Extraction not complete - some materials missing")
        return False
    else:
        print("✅ All materials have gap files - extraction appears complete")
        return True

def main():
    """Run complete merge process"""
    print("🚀 COMPLETE DATABASE UPDATE PROCESS")
    print("="*60)
    
    # Check if extraction is complete
    if not check_extraction_complete():
        print("\n⚠️  WAITING: Extraction still in progress")
        print("Please wait for the extraction to complete all 14 materials")
        print("You can run this script again once extraction finishes")
        return
    
    print("\n✅ EXTRACTION COMPLETE - Proceeding with merge")
    
    # Step 1: Merge gap data into Excel
    step1_success = run_script("merge_gaps_to_excel.py", "Merge gap data to Excel")
    
    if not step1_success:
        print("\n❌ ABORTED: Excel merge failed")
        return
    
    # Step 2: Import Excel to database
    step2_success = run_script("import_excel_to_database.py", "Import Excel to database")
    
    if not step2_success:
        print("\n❌ PARTIAL SUCCESS: Excel merged but database import failed")
        return
    
    # Success!
    print(f"\n{'='*60}")
    print("🎉 COMPLETE SUCCESS!")
    print(f"{'='*60}")
    print("✅ Gap data merged into all_materials_hotspots.xlsx")
    print("✅ Updated Excel imported into user_data.db")
    print("✅ Ring finder now has complete hotspot coverage!")
    print("\nTest: Search for Alexandrite in Paesia - should now appear with LS distances!")

if __name__ == "__main__":
    main()
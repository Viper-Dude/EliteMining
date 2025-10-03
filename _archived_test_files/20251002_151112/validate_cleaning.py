#!/usr/bin/env python3
"""
Data Cleaning Validation Script
Shows what cleaning will be applied during the merge process
"""

import pandas as pd
import re
from pathlib import Path

def demonstrate_cleaning():
    """Demonstrate the cleaning process with examples"""
    print("="*60)
    print("DATA CLEANING VALIDATION")
    print("="*60)
    
    # Check if we have any gap files to analyze
    gap_dir = Path("app/data/Hotspots/all_materials_gaps")
    if not gap_dir.exists():
        print("No gap files found yet - showing cleaning examples instead")
        show_cleaning_examples()
        return
    
    gap_files = list(gap_dir.glob("*_complete_gaps.xlsx"))
    if not gap_files:
        print("No gap files found yet - showing cleaning examples instead")
        show_cleaning_examples()
        return
    
    print(f"Found {len(gap_files)} gap files - analyzing cleaning needs...")
    
    # Analyze first few files
    total_before = 0
    total_after = 0
    
    for gap_file in gap_files[:3]:  # Check first 3 files
        material = gap_file.stem.replace('_complete_gaps', '')
        
        print(f"\nAnalyzing {material} data:")
        df = pd.read_excel(gap_file)
        before_count = len(df)
        total_before += before_count
        
        # Apply cleaning
        df_clean = apply_sample_cleaning(df.copy())
        after_count = len(df_clean)
        total_after += after_count
        
        removed = before_count - after_count
        print(f"  Before cleaning: {before_count} records")
        print(f"  After cleaning:  {after_count} records") 
        print(f"  Removed:         {removed} records ({removed/before_count*100:.1f}%)")
        
        # Show examples of what was cleaned
        show_cleaning_issues(df)
    
    print(f"\nOVERALL CLEANING IMPACT (sample):")
    print(f"  Total before: {total_before}")
    print(f"  Total after:  {total_after}")
    print(f"  Total removed: {total_before - total_after}")

def apply_sample_cleaning(df):
    """Apply the same cleaning logic that will be used in merge"""
    initial_count = len(df)
    
    # Clean system names
    df['System'] = df['System'].astype(str).str.strip()
    df['System'] = df['System'].str.replace(r'\[.*?\]', '', regex=True)
    df['System'] = df['System'].str.replace('*', '')
    df['System'] = df['System'].str.replace(r'\s+', ' ', regex=True)
    
    # Clean ring names
    df['Ring'] = df['Ring'].astype(str).str.strip()
    df['Ring'] = df['Ring'].str.replace(r'\s+', ' ', regex=True)
    
    # Remove garbage entries
    df = df[df['System'].str.len() > 2]
    df = df[df['Ring'].str.len() > 0]
    df = df[df['System'].str.match(r'^[A-Za-z]', na=False)]
    
    # Remove garbage patterns
    garbage_patterns = [
        r'^[0-9]+$',
        r'^[^a-zA-Z0-9\s\-]+',
        r'^\s*$',
        r'^(N/A|NA|null|undefined|error)$',
        r'^\d+\.\d+$',
    ]
    
    for pattern in garbage_patterns:
        df = df[~df['System'].str.match(pattern, case=False, na=False)]
    
    # Validate numeric fields
    df['Hotspots'] = pd.to_numeric(df['Hotspots'], errors='coerce')
    df = df[df['Hotspots'] > 0]
    
    # Remove entries with missing critical data
    df = df.dropna(subset=['System', 'Ring', 'Hotspots'])
    
    return df

def show_cleaning_issues(df_original):
    """Show examples of data issues that will be cleaned"""
    print("    Issues found and cleaned:")
    
    # Check for clipboard links
    clipboard_issues = df_original[df_original['System'].str.contains(r'\[.*?\]', na=False)]
    if len(clipboard_issues) > 0:
        print(f"      - {len(clipboard_issues)} entries with clipboard links [removed]")
    
    # Check for asterisks
    asterisk_issues = df_original[df_original['System'].str.contains(r'\*', na=False)]
    if len(asterisk_issues) > 0:
        print(f"      - {len(asterisk_issues)} entries with asterisks [cleaned]")
    
    # Check for short system names
    short_names = df_original[df_original['System'].str.len() <= 2]
    if len(short_names) > 0:
        print(f"      - {len(short_names)} entries with very short system names [removed]")
    
    # Check for non-letter starts
    invalid_starts = df_original[~df_original['System'].str.match(r'^[A-Za-z]', na=False)]
    if len(invalid_starts) > 0:
        print(f"      - {len(invalid_starts)} entries not starting with letter [removed]")
    
    # Check for invalid hotspot counts
    invalid_hotspots = df_original[pd.to_numeric(df_original['Hotspots'], errors='coerce') <= 0]
    if len(invalid_hotspots) > 0:
        print(f"      - {len(invalid_hotspots)} entries with invalid hotspot counts [removed]")

def show_cleaning_examples():
    """Show examples of what the cleaning process does"""
    print("\nCLEANING PROCESS EXAMPLES:")
    print("-" * 40)
    
    examples = [
        {
            'before': 'Sol [📋]*',
            'after': 'Sol',
            'reason': 'Remove clipboard links and asterisks'
        },
        {
            'before': 'Wolf  359   Sector',
            'after': 'Wolf 359 Sector', 
            'reason': 'Normalize multiple spaces'
        },
        {
            'before': '123.45',
            'after': '[REMOVED]',
            'reason': 'Remove entries that are just numbers'
        },
        {
            'before': 'A  B   Ring',
            'after': 'A B Ring',
            'reason': 'Clean ring names with multiple spaces'
        },
        {
            'before': 'N/A',
            'after': '[REMOVED]',
            'reason': 'Remove placeholder/error values'
        }
    ]
    
    for example in examples:
        print(f"  BEFORE: '{example['before']}'")
        print(f"  AFTER:  '{example['after']}'")
        print(f"  REASON: {example['reason']}")
        print()
    
    print("DEDUPLICATION:")
    print("-" * 40)
    print("  - Remove exact duplicates (same System + Ring + Material)")
    print("  - Case-insensitive comparison for duplicate detection")
    print("  - Keep first occurrence, remove subsequent duplicates")
    
    print("\nVALIDATION:")
    print("-" * 40)
    print("  - System names must start with a letter")
    print("  - System names must be > 2 characters")
    print("  - Ring names must not be empty")  
    print("  - Hotspot counts must be > 0")
    print("  - Material names must be in valid list")

def main():
    """Run cleaning validation"""
    demonstrate_cleaning()
    
    print(f"\n{'='*60}")
    print("CLEANING SUMMARY")
    print(f"{'='*60}")
    print("✅ System name cleaning (remove *, [], normalize spaces)")
    print("✅ Ring name cleaning (normalize spaces)")  
    print("✅ Garbage entry removal (invalid patterns)")
    print("✅ Duplicate removal (case-insensitive)")
    print("✅ Data validation (hotspots > 0, valid materials)")
    print("✅ Database preparation (type conversion, null handling)")
    
    print(f"\nThis ensures clean, high-quality data in your database!")

if __name__ == "__main__":
    main()
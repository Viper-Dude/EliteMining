"""
Fix Material Name Duplicates in Ring Finder Database

This script normalizes all material names in user_data.db to match the canonical
names defined in journal_parser.py, eliminating duplicates caused by inconsistent
capitalization from Elite Dangerous journal files.

Database: app/data/user_data.db
Table: hotspot_data
Affected Column: material_name

Before running: Creates backup at user_data.db.backup_YYYYMMDD_HHMMSS
"""

import os
import sqlite3
import shutil
from datetime import datetime
from typing import Dict

# Material name normalization map (from journal_parser.py)
MATERIAL_NAME_MAP = {
    # Tritium variants
    'tritium': 'Tritium',
    'Tritium': 'Tritium',
    
    # Low Temperature Diamonds variants
    'low temperature diamonds': 'Low Temperature Diamonds',
    'Low Temperature Diamonds': 'Low Temperature Diamonds',
    'low temp diamonds': 'Low Temperature Diamonds',
    'Low Temp Diamonds': 'Low Temperature Diamonds',
    'low temp. diamonds': 'Low Temperature Diamonds',
    'Low Temp. Diamonds': 'Low Temperature Diamonds',
    'LowTemperatureDiamond': 'Low Temperature Diamonds',
    'lowtemperaturediamond': 'Low Temperature Diamonds',
    
    # Void Opals variants (confirmed in database: "Opal" should be "Void Opals")
    'void opals': 'Void Opals',
    'Void Opals': 'Void Opals',
    'void opal': 'Void Opals',
    'Void opal': 'Void Opals',
    'Void Opal': 'Void Opals',
    'opal': 'Void Opals',
    'Opal': 'Void Opals',
    
    # Other materials - standard capitalization
    'alexandrite': 'Alexandrite',
    'Alexandrite': 'Alexandrite',
    'benitoite': 'Benitoite',
    'Benitoite': 'Benitoite',
    'bromellite': 'Bromellite',
    'Bromellite': 'Bromellite',
    'grandidierite': 'Grandidierite',
    'Grandidierite': 'Grandidierite',
    'monazite': 'Monazite',
    'Monazite': 'Monazite',
    'musgravite': 'Musgravite',
    'Musgravite': 'Musgravite',
    'painite': 'Painite',
    'Painite': 'Painite',
    'platinum': 'Platinum',
    'Platinum': 'Platinum',
    'rhodplumsite': 'Rhodplumsite',
    'Rhodplumsite': 'Rhodplumsite',
    'serendibite': 'Serendibite',
    'Serendibite': 'Serendibite',
    'palladium': 'Palladium',
    'Palladium': 'Palladium',
    'gold': 'Gold',
    'Gold': 'Gold',
    'osmium': 'Osmium',
    'Osmium': 'Osmium',
}


def normalize_material_name(material_name: str) -> str:
    """Normalize material name to canonical form"""
    # Try exact match first
    normalized = MATERIAL_NAME_MAP.get(material_name)
    if normalized:
        return normalized
    
    # Try lowercase match
    normalized = MATERIAL_NAME_MAP.get(material_name.lower())
    if normalized:
        return normalized
    
    # If not in map, return with first letter capitalized
    return material_name.strip().capitalize()


def create_backup(db_path: str) -> str:
    """Create timestamped backup of database"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    
    shutil.copy2(db_path, backup_path)
    print(f"✓ Backup created: {backup_path}")
    print(f"  Size: {os.path.getsize(backup_path) / (1024*1024):.1f} MB\n")
    
    return backup_path


def analyze_database(db_path: str) -> Dict[str, int]:
    """Analyze current material name issues"""
    print("📊 Analyzing database...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all unique material names and their counts
    cursor.execute("""
        SELECT material_name, COUNT(*) 
        FROM hotspot_data 
        GROUP BY material_name 
        ORDER BY material_name
    """)
    
    material_counts = {}
    issues = {}
    
    for material_name, count in cursor.fetchall():
        material_counts[material_name] = count
        normalized = normalize_material_name(material_name)
        
        # Track if this material needs fixing
        if material_name != normalized:
            if normalized not in issues:
                issues[normalized] = []
            issues[normalized].append((material_name, count))
    
    conn.close()
    
    # Display analysis
    print(f"Total unique material names: {len(material_counts)}")
    print(f"Total hotspot records: {sum(material_counts.values())}\n")
    
    if issues:
        print("⚠️  Issues found:")
        for canonical_name, variants in issues.items():
            print(f"\n  {canonical_name}:")
            for variant, count in variants:
                if variant != canonical_name:
                    print(f"    • '{variant}' ({count} records) → '{canonical_name}'")
        print()
    else:
        print("✓ No material name issues found!\n")
    
    return material_counts


def fix_material_names(db_path: str, dry_run: bool = False, specific_material: str = None) -> int:
    """Fix all material names in database (or one specific material)
    
    Args:
        db_path: Path to database file
        dry_run: If True, only show what would be changed without modifying DB
        specific_material: If provided, only fix this specific old material name
        
    Returns:
        Number of records updated
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all unique material names
    cursor.execute("SELECT DISTINCT material_name FROM hotspot_data")
    material_names = [row[0] for row in cursor.fetchall()]
    
    updates_needed = {}
    for material_name in material_names:
        normalized = normalize_material_name(material_name)
        if material_name != normalized:
            # If specific material requested, only add if it matches
            if specific_material:
                if material_name == specific_material:
                    updates_needed[material_name] = normalized
            else:
                updates_needed[material_name] = normalized
    
    if not updates_needed:
        print("✓ No updates needed - all material names already normalized!")
        conn.close()
        return 0
    
    total_updated = 0
    
    if dry_run:
        print("🔍 DRY RUN - No changes will be made\n")
    else:
        print("🔧 Updating material names...\n")
    
    for old_name, new_name in updates_needed.items():
        # Count records that will be updated
        cursor.execute(
            "SELECT COUNT(*) FROM hotspot_data WHERE material_name = ?",
            (old_name,)
        )
        count = cursor.fetchone()[0]
        
        print(f"  '{old_name}' → '{new_name}' ({count} records)")
        
        if not dry_run:
            # First, check for potential duplicates
            cursor.execute("""
                SELECT DISTINCT h1.system_name, h1.body_name
                FROM hotspot_data h1
                WHERE h1.material_name = ?
                AND EXISTS (
                    SELECT 1 FROM hotspot_data h2
                    WHERE h2.system_name = h1.system_name
                    AND h2.body_name = h1.body_name
                    AND h2.material_name = ?
                )
            """, (old_name, new_name))
            
            potential_duplicates = cursor.fetchall()
            
            # Delete old entries that would create duplicates (keep the normalized one)
            for system, body in potential_duplicates:
                cursor.execute("""
                    DELETE FROM hotspot_data
                    WHERE system_name = ? AND body_name = ? AND material_name = ?
                """, (system, body, old_name))
            
            # Update remaining entries
            cursor.execute(
                "UPDATE hotspot_data SET material_name = ? WHERE material_name = ?",
                (new_name, old_name)
            )
            total_updated += count
    
    if not dry_run:
        conn.commit()
        print(f"\n✓ Updated {total_updated} records")
        
        # Handle potential duplicates after normalization
        print("\n🔍 Checking for duplicate entries after normalization...")
        cursor.execute("""
            SELECT system_name, body_name, material_name, COUNT(*) as count
            FROM hotspot_data
            GROUP BY system_name, body_name, material_name
            HAVING count > 1
        """)
        
        duplicates = cursor.fetchall()
        if duplicates:
            print(f"⚠️  Found {len(duplicates)} duplicate combinations:")
            for system, body, material, count in duplicates:
                print(f"    • {system} / {body} / {material} ({count} entries)")
            
            print("\n🔧 Merging duplicates (keeping most recent scan)...")
            
            for system, body, material, _ in duplicates:
                # Keep the most recent entry (latest scan_date)
                cursor.execute("""
                    DELETE FROM hotspot_data
                    WHERE rowid NOT IN (
                        SELECT rowid FROM hotspot_data
                        WHERE system_name = ? AND body_name = ? AND material_name = ?
                        ORDER BY scan_date DESC
                        LIMIT 1
                    )
                    AND system_name = ? AND body_name = ? AND material_name = ?
                """, (system, body, material, system, body, material))
            
            conn.commit()
            print(f"✓ Merged {len(duplicates)} duplicate entries")
        else:
            print("✓ No duplicates found")
    
    conn.close()
    return total_updated


def main():
    """Main execution"""
    print("=" * 60)
    print("Material Name Cleanup for Ring Finder Database")
    print("=" * 60)
    print()
    
    # Determine database path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "app", "data", "user_data.db")
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return
    
    print(f"Database: {db_path}")
    print(f"Size: {os.path.getsize(db_path) / (1024*1024):.1f} MB\n")
    
    # Analyze current state
    material_counts = analyze_database(db_path)
    
    # Get list of materials that need fixing
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT material_name FROM hotspot_data ORDER BY material_name")
    all_materials = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    materials_to_fix = []
    for material in all_materials:
        normalized = normalize_material_name(material)
        if material != normalized:
            materials_to_fix.append((material, normalized))
    
    if not materials_to_fix:
        print("✓ All material names already normalized - nothing to fix!")
        return
    
    # Show menu for one-by-one fixing
    print("=" * 60)
    print("Materials requiring normalization:")
    print("=" * 60)
    for idx, (old_name, new_name) in enumerate(materials_to_fix, 1):
        count = material_counts.get(old_name, 0)
        print(f"{idx}. '{old_name}' → '{new_name}' ({count} records)")
    print(f"{len(materials_to_fix) + 1}. Fix ALL materials at once")
    print("0. Cancel")
    
    print("\n" + "=" * 60)
    choice = input("Select material to fix (or 'all'): ").strip()
    
    if choice == '0':
        print("Operation cancelled.")
        return
    
    # Determine which materials to fix
    specific_material = None
    if choice == str(len(materials_to_fix) + 1) or choice.lower() == 'all':
        print(f"\n→ Fixing ALL {len(materials_to_fix)} materials")
        specific_material = None
    else:
        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(materials_to_fix):
                old_name, new_name = materials_to_fix[choice_idx]
                print(f"\n→ Fixing only: '{old_name}' → '{new_name}'")
                specific_material = old_name
            else:
                print("Invalid selection.")
                return
        except ValueError:
            print("Invalid selection.")
            return
    
    # Create backup
    print()
    backup_path = create_backup(db_path)
    
    # Fix material names
    print("=" * 60)
    updated_count = fix_material_names(db_path, dry_run=False, specific_material=specific_material)
    
    # Show final state
    print("\n" + "=" * 60)
    print("Final Database State")
    print("=" * 60)
    analyze_database(db_path)
    
    print("=" * 60)
    print("✓ Cleanup complete!")
    print(f"  Backup saved at: {backup_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()

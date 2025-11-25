#!/usr/bin/env python3
"""
Analyze unique hotspots in user_data.db
"""

import sqlite3
import os

# Database path
DB_PATH = r"d:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db"

def analyze_unique_hotspots():
    """Analyze unique hotspots breakdown"""
    print("\n" + "="*80)
    print("UNIQUE HOTSPOTS ANALYSIS")
    print("="*80 + "\n")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Total rows
        cursor.execute("SELECT COUNT(*) FROM hotspot_data")
        total_rows = cursor.fetchone()[0]
        print(f"Total hotspot_data rows: {total_rows:,}")
        
        # Unique system+body combinations (unique rings)
        cursor.execute("""
            SELECT COUNT(DISTINCT system_name || '|' || body_name)
            FROM hotspot_data
        """)
        unique_rings = cursor.fetchone()[0]
        print(f"Unique system+body combinations (rings): {unique_rings:,}")
        
        # Unique systems
        cursor.execute("""
            SELECT COUNT(DISTINCT system_name)
            FROM hotspot_data
        """)
        unique_systems = cursor.fetchone()[0]
        print(f"Unique systems with hotspots: {unique_systems:,}")
        
        # Materials distribution
        print(f"\n{'Material Distribution:'}")
        print("-" * 80)
        cursor.execute("""
            SELECT material_name, COUNT(*) as count
            FROM hotspot_data
            GROUP BY material_name
            ORDER BY count DESC
        """)
        
        materials = cursor.fetchall()
        for material, count in materials:
            percentage = (count / total_rows) * 100
            bar = "█" * int(percentage / 2)
            print(f"  {material:<30} {count:>6,} rows ({percentage:>5.1f}%) {bar}")
        
        # Average materials per ring
        cursor.execute("""
            SELECT AVG(material_count) FROM (
                SELECT COUNT(*) as material_count
                FROM hotspot_data
                GROUP BY system_name, body_name
            )
        """)
        avg_materials = cursor.fetchone()[0]
        print(f"\nAverage materials per ring: {avg_materials:.2f}")
        
        # Rings with most materials
        print(f"\n{'Top 10 Rings by Material Count:'}")
        print("-" * 80)
        cursor.execute("""
            SELECT system_name, body_name, COUNT(*) as material_count
            FROM hotspot_data
            GROUP BY system_name, body_name
            ORDER BY material_count DESC
            LIMIT 10
        """)
        
        for system, body, count in cursor.fetchall():
            print(f"  {system:<50} {body:<20} {count} materials")
        
        # Most common materials
        print(f"\n{'Most Common Materials by Frequency:'}")
        print("-" * 80)
        cursor.execute("""
            SELECT material_name, COUNT(DISTINCT system_name || '|' || body_name) as ring_count
            FROM hotspot_data
            GROUP BY material_name
            ORDER BY ring_count DESC
        """)
        
        for material, ring_count in cursor.fetchall():
            print(f"  {material:<30} Found in {ring_count:>6,} rings")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error analyzing hotspots: {e}")

if __name__ == "__main__":
    analyze_unique_hotspots()

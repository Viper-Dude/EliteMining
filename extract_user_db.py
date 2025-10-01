#!/usr/bin/env python3
"""
Extract and analyze all data from user_data.db
This script will show you exactly what's in your database
"""

import sqlite3
import os
import csv
from datetime import datetime

def extract_database():
    """Extract all data from user_data.db"""
    
    # Database path
    db_path = r"d:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db"
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found at: {db_path}")
        return
    
    print(f"📊 Analyzing database: {db_path}")
    print(f"📅 Analysis time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Get all table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            print(f"🗂️  Found {len(tables)} tables:")
            for table in tables:
                print(f"   - {table[0]}")
            print()
            
            # Analyze each table
            for table_name in [t[0] for t in tables]:
                print(f"📋 TABLE: {table_name}")
                print("-" * 50)
                
                # Get table schema
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = cursor.fetchall()
                
                print("📝 Schema:")
                for col in columns:
                    print(f"   {col[1]} ({col[2]}) - {'NOT NULL' if col[3] else 'NULLABLE'}")
                
                # Get row count
                cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
                row_count = cursor.fetchone()[0]
                print(f"📊 Total rows: {row_count}")
                
                if row_count > 0:
                    # Show sample data
                    cursor.execute(f"SELECT * FROM {table_name} LIMIT 10;")
                    sample_rows = cursor.fetchall()
                    
                    print("🔍 Sample data (first 10 rows):")
                    col_names = [col[1] for col in columns]
                    print(f"   {' | '.join(col_names)}")
                    print(f"   {'-' * (len(' | '.join(col_names)))}")
                    
                    for row in sample_rows:
                        # Truncate long values for display
                        display_row = []
                        for val in row:
                            str_val = str(val) if val is not None else "NULL"
                            if len(str_val) > 30:
                                str_val = str_val[:27] + "..."
                            display_row.append(str_val)
                        print(f"   {' | '.join(display_row)}")
                
                print()
            
            # Specific analysis for hotspot_data table
            if any(t[0] == 'hotspot_data' for t in tables):
                print("🎯 HOTSPOT DATA ANALYSIS")
                print("=" * 50)
                
                # Material distribution
                cursor.execute("""
                    SELECT material_name, COUNT(*) as count 
                    FROM hotspot_data 
                    GROUP BY material_name 
                    ORDER BY count DESC
                """)
                materials = cursor.fetchall()
                
                print("📊 Materials in database:")
                for material, count in materials:
                    print(f"   {material}: {count} entries")
                print()
                
                # System distribution (top 20)
                cursor.execute("""
                    SELECT system_name, COUNT(*) as count 
                    FROM hotspot_data 
                    GROUP BY system_name 
                    ORDER BY count DESC 
                    LIMIT 20
                """)
                systems = cursor.fetchall()
                
                print("🌌 Top 20 systems by hotspot count:")
                for system, count in systems:
                    print(f"   {system}: {count} hotspots")
                print()
                
                # Check for LTD specifically
                cursor.execute("""
                    SELECT system_name, body_name, material_name, hotspot_count 
                    FROM hotspot_data 
                    WHERE material_name LIKE '%Diamond%' OR material_name LIKE '%LTD%' OR material_name LIKE '%Low Temp%'
                    ORDER BY system_name
                """)
                ltd_data = cursor.fetchall()
                
                print(f"💎 Low Temperature Diamonds entries ({len(ltd_data)} found):")
                for system, body, material, count in ltd_data:
                    print(f"   {system} - {body} - {material} ({count})")
                print()
                
                # Check coordinate availability
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(x_coord) as with_coords,
                        COUNT(*) - COUNT(x_coord) as without_coords
                    FROM hotspot_data
                """)
                coord_stats = cursor.fetchone()
                
                print("📍 Coordinate availability:")
                print(f"   Total entries: {coord_stats[0]}")
                print(f"   With coordinates: {coord_stats[1]}")
                print(f"   Without coordinates: {coord_stats[2]}")
                print()
    
    except Exception as e:
        print(f"❌ Error accessing database: {e}")
        return
    
    # Export to CSV for detailed analysis
    export_to_csv(db_path)

def export_to_csv(db_path):
    """Export all tables to CSV files for detailed analysis"""
    print("💾 EXPORTING TO CSV FILES")
    print("=" * 50)
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Get all table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            for table_name in [t[0] for t in tables]:
                csv_filename = f"user_db_{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                
                cursor.execute(f"SELECT * FROM {table_name};")
                rows = cursor.fetchall()
                
                # Get column names
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = cursor.fetchall()
                col_names = [col[1] for col in columns]
                
                # Write to CSV
                with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(col_names)  # Header
                    writer.writerows(rows)      # Data
                
                print(f"   ✅ Exported {table_name}: {csv_filename} ({len(rows)} rows)")
        
        print("\n📁 CSV files created in current directory")
        print("   You can open these in Excel or any text editor for detailed analysis")
        
    except Exception as e:
        print(f"❌ Error exporting to CSV: {e}")

if __name__ == "__main__":
    print("🔍 EliteMining User Database Analyzer")
    print("=" * 80)
    extract_database()
    print("\n✅ Analysis complete!")
import sqlite3
import json
import os
from datetime import datetime

def extract_lhs501_data():
    """Extract all data for LHS 501 system from the user database"""
    
    # Database path
    db_path = os.path.join("app", "data", "user_data.db")
    
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("=" * 50)
        print("EXTRACTING DATA FOR LHS 501")
        print("=" * 50)
        
        # Check visited systems
        print("\n1. VISITED SYSTEMS DATA:")
        cursor.execute("""
            SELECT system_name, timestamp, system_address, coordinates 
            FROM visited_systems 
            WHERE system_name LIKE '%LHS 501%' OR system_name = 'LHS 501'
            ORDER BY timestamp DESC
        """)
        
        visited_data = cursor.fetchall()
        if visited_data:
            for row in visited_data:
                system_name, timestamp, system_address, coordinates = row
                print(f"  System: {system_name}")
                print(f"  Timestamp: {timestamp}")
                print(f"  System Address: {system_address}")
                if coordinates:
                    try:
                        coords = json.loads(coordinates)
                        print(f"  Coordinates: X={coords.get('x')}, Y={coords.get('y')}, Z={coords.get('z')}")
                    except:
                        print(f"  Coordinates: {coordinates}")
                print()
        else:
            print("  No visited systems data found for LHS 501")
        
        # Check hotspots data
        print("\n2. HOTSPOTS DATA:")
        cursor.execute("""
            SELECT system_name, body_name, ring_name, material_type, hotspot_data 
            FROM hotspots 
            WHERE system_name LIKE '%LHS 501%' OR system_name = 'LHS 501'
            ORDER BY system_name, body_name
        """)
        
        hotspot_data = cursor.fetchall()
        if hotspot_data:
            for row in hotspot_data:
                system_name, body_name, ring_name, material_type, hotspot_data_json = row
                print(f"  System: {system_name}")
                print(f"  Body: {body_name}")
                print(f"  Ring: {ring_name}")
                print(f"  Material: {material_type}")
                if hotspot_data_json:
                    try:
                        hotspot_info = json.loads(hotspot_data_json)
                        print(f"  Hotspot Data: {json.dumps(hotspot_info, indent=4)}")
                    except:
                        print(f"  Hotspot Data: {hotspot_data_json}")
                print()
        else:
            print("  No hotspot data found for LHS 501")
        
        # Check for any similar system names
        print("\n3. SIMILAR SYSTEM NAMES:")
        cursor.execute("""
            SELECT DISTINCT system_name 
            FROM visited_systems 
            WHERE system_name LIKE '%LHS%' AND system_name LIKE '%501%'
        """)
        
        similar_systems = cursor.fetchall()
        if similar_systems:
            print("  Found systems with LHS and 501:")
            for row in similar_systems:
                print(f"    - {row[0]}")
        else:
            print("  No similar system names found")
        
        # Database statistics
        print("\n4. DATABASE STATISTICS:")
        cursor.execute("SELECT COUNT(*) FROM visited_systems")
        total_systems = cursor.fetchone()[0]
        print(f"  Total visited systems: {total_systems}")
        
        cursor.execute("SELECT COUNT(*) FROM hotspots")
        total_hotspots = cursor.fetchone()[0]
        print(f"  Total hotspots: {total_hotspots}")
        
        # Check table structure
        print("\n5. TABLE STRUCTURES:")
        cursor.execute("PRAGMA table_info(visited_systems)")
        visited_columns = cursor.fetchall()
        print("  visited_systems columns:")
        for col in visited_columns:
            print(f"    - {col[1]} ({col[2]})")
        
        cursor.execute("PRAGMA table_info(hotspots)")
        hotspot_columns = cursor.fetchall()
        print("  hotspots columns:")
        for col in hotspot_columns:
            print(f"    - {col[1]} ({col[2]})")
        
        conn.close()
        
        print("\n" + "=" * 50)
        print("EXTRACTION COMPLETE")
        print("=" * 50)
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    extract_lhs501_data()

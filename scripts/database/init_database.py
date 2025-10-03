"""Initialize database to add missing columns"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# Now import after path is set
from user_database import UserDatabase

print("\nInitializing database...")
db = UserDatabase()
print("✅ Database initialized!")

# Check schema again
import sqlite3
conn = sqlite3.connect(db.db_path)
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(hotspot_data)")
columns = cursor.fetchall()

col_names = [col[1] for col in columns]
print(f"\nColumn check:")
print(f"  ring_mass: {'✅ EXISTS' if 'ring_mass' in col_names else '❌ MISSING'}")
print(f"  density:   {'✅ EXISTS' if 'density' in col_names else '❌ MISSING'}")

conn.close()

#!/usr/bin/env python3
"""
Strip personal data from a user_data.db working copy before shipping it as
the bundled install/reference database ('UserDb for install/user_data.db').

Removes visit history (visited_systems) and leftover schema cruft. Leaves
hotspot_data and the migration bookkeeping tables untouched, since they
describe the shared community dataset, not personal data.
"""

import argparse
import shutil
import sqlite3


def strip_personal_data(db_path: str, database_version: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM visited_systems")
        visited_count = cursor.fetchone()[0]
        cursor.execute("DELETE FROM visited_systems")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hotspot_data_new'")
        if cursor.fetchone():
            cursor.execute("DROP TABLE hotspot_data_new")

        cursor.execute("DELETE FROM database_version")
        cursor.execute(
            "INSERT INTO database_version (version, updated_date) VALUES (?, datetime('now'))",
            (database_version,)
        )

        conn.commit()
        conn.execute("VACUUM")

        cursor.execute("SELECT COUNT(*) FROM hotspot_data")
        hotspot_count = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(hotspot_count) FROM hotspot_data")
        total_hotspots = cursor.fetchone()[0]

        print(f"Removed {visited_count} personal visit records")
        print(f"Database version set to {database_version}")
        print(f"hotspot_data: {hotspot_count} rows, {total_hotspots} total hotspots")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Path to the personal working copy to strip")
    parser.add_argument("--output", help="Write result here instead of stripping in place")
    parser.add_argument("--version", required=True, help="Database version to stamp, e.g. 5.2.5")
    args = parser.parse_args()

    target = args.output or args.source
    if args.output:
        shutil.copy2(args.source, args.output)

    strip_personal_data(target, args.version)

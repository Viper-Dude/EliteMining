"""Check cache index upgrades using temporary databases and offline searches."""

import ast
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from eddn_listener import EDDNListener
from marketplace_api import MarketplaceAPI
from system_finder_api import SystemFinderAPI


class CacheIndexChecks(unittest.TestCase):
    indexes = ('idx_commodity_name_lower_updated', 'idx_powerplay_system_nocase')

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = str(Path(folder.name) / 'marketplace_cache.db')
        original_connect = sqlite3.connect

        def connect(*args, **kwargs):
            conn = original_connect(*args, **kwargs)
            self.addCleanup(conn.close)
            return conn

        connections = patch.object(sqlite3, 'connect', side_effect=connect)
        connections.start()
        self.addCleanup(connections.stop)
        self.listener = EDDNListener(self.path)
        for api in (MarketplaceAPI, SystemFinderAPI):
            setting = patch.object(api, 'EDDN_CACHE_PATH', self.path)
            setting.start()
            self.addCleanup(setting.stop)
        coordinates = patch.object(MarketplaceAPI, '_get_system_coords', return_value=(0, 0, 0))
        coordinates.start()
        self.addCleanup(coordinates.stop)
        self.now = datetime.now(timezone.utc).isoformat()
        self.old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('INSERT INTO system_coords(name,x,y,z,updated_at) VALUES (?,?,?,?,?)',
                         ('Sol', 0, 0, 0, self.now))
            conn.executemany('INSERT INTO system_powerplay VALUES (?,?,?,?,?)', [
                ('Sol', 'Test Power', 'Fortified', '["Test Power"]', self.now),
                ('sOL', 'Other Power', 'Exploited', None, self.now),
                ('Unoccupied', '~none~', 'Unoccupied', None, self.old),
            ])
            conn.execute('INSERT INTO station_metadata VALUES (?,?,?,?,?,?,?)',
                         (1, 'Station 1', 'Sol', 'Coriolis', 3, 150.5, self.now))
            for market_id, commodity, stamp, station_type in (
                (1, 'platinum', self.now, 'Unknown'),
                (2, 'PlAtInUm', self.now, 'Outpost'),
                (3, 'Platinum', self.old, 'Coriolis'),
                (4, 'PLATINUM', self.now, 'FleetCarrier'),
                (5, 'painite', self.now, 'Coriolis'),
            ):
                conn.execute('''INSERT INTO commodity_prices_data
                    (system_name,system_x,system_y,system_z,station_name,station_type,
                     commodity_name,sell_price,buy_price,demand,stock,market_id,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    ('Sol', 0, 0, 0, f'Station {market_id}', station_type, commodity,
                     100 + market_id, 50, 1000, 2000, market_id, stamp))
            conn.commit()

    def drop_indexes(self):
        with closing(sqlite3.connect(self.path)) as conn:
            for name in self.indexes:
                conn.execute(f'DROP INDEX {name}')
            conn.commit()

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            return {name: conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
                    for (name,) in tables}

    def assert_queries_use_indexes(self):
        cases = [
            ('app/marketplace_api.py', 'LOWER(c.commodity_name)',
             ('platinum', 'Platinum', self.old), self.indexes[0]),
            ('app/system_finder_api.py', ' WHERE system_name = ? COLLATE NOCASE',
             ('sOl',), self.indexes[1]),
        ]
        with closing(sqlite3.connect(self.path)) as conn:
            for filename, marker, args, index in cases:
                tree = ast.parse((ROOT / filename).read_text(encoding='utf-8-sig'))
                query = next(n.value for n in ast.walk(tree)
                             if isinstance(n, ast.Constant) and isinstance(n.value, str)
                             and n.value.lstrip().startswith('SELECT') and marker in n.value)
                plan = conn.execute('EXPLAIN QUERY PLAN ' + query, args).fetchall()
                self.assertTrue(any(index in row[-1] for row in plan), plan)

    def test_fresh_cache_uses_indexes_for_actual_queries(self):
        self.assert_queries_use_indexes()

    def test_existing_cache_upgrade_preserves_every_record(self):
        self.drop_indexes()
        before = self.snapshot()
        EDDNListener(self.path)
        self.assertEqual(self.snapshot(), before)
        self.assert_queries_use_indexes()

    def test_repeated_initialization_preserves_records_and_schema(self):
        before = self.snapshot()
        with closing(sqlite3.connect(self.path)) as conn:
            schema = conn.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall()
        EDDNListener(self.path)
        EDDNListener(self.path)
        self.assertEqual(self.snapshot(), before)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall(), schema)

    def test_powerplay_case_duplicates_and_unknown_results_are_unchanged(self):
        self.drop_indexes()
        names = ['Sol', 'sol', 'sOL', 'SOL', 'Unoccupied', 'UNOCCUPIED', 'Missing']
        before = [SystemFinderAPI._get_powerplay_from_cache(name) for name in names]
        batch = SystemFinderAPI._batch_get_powerplay(names)
        self.assertEqual(before[0]['controlling_power'], 'Test Power')
        self.assertIsNone(before[-1])
        EDDNListener(self.path)
        self.assertEqual([SystemFinderAPI._get_powerplay_from_cache(name) for name in names], before)
        self.assertEqual(SystemFinderAPI._batch_get_powerplay(names), batch)

    def test_market_case_age_metadata_carriers_and_distances_are_unchanged(self):
        def search(commodity, exclude_carriers):
            rows = MarketplaceAPI._fetch_eddn_cache(commodity, 'Sol', 'buy',
                                                   max_days_ago=7, exclude_carriers=exclude_carriers)
            return sorted(rows, key=lambda row: row['marketId'])

        self.drop_indexes()
        choices = [('platinum', False), ('platinum', True), ('painite', False), ('missing', False)]
        before = [search(*args) for args in choices]
        self.assertEqual([row['marketId'] for row in before[0]], [1, 2, 4])
        self.assertEqual([row['marketId'] for row in before[1]], [1, 2])
        self.assertEqual(before[0][0]['stationType'], 'Coriolis')
        self.assertEqual(before[0][0]['distanceToArrival'], 150.5)
        self.assertTrue(all(row['distance'] == 0 for row in before[0]))
        self.assertEqual(before[-1], [])
        EDDNListener(self.path)
        self.assertEqual([search(*args) for args in choices], before)

    def test_incoming_prices_and_powerplay_replace_existing_records(self):
        self.listener._update_commodity_prices('Sol', 'Station 1', 'Coriolis', 1, [
            dict(name='platinum', sellPrice=250000, buyPrice=200000, demand=500, stock=25),
        ], self.now)
        self.listener._process_powerplay_from_event(
            dict(StarSystem='Unoccupied', ControllingPower='New Power', PowerplayState='Stronghold'), self.now)
        rows = MarketplaceAPI._fetch_eddn_cache('platinum', 'Sol', 'buy', max_days_ago=7)
        station = next(row for row in rows if row['marketId'] == 1)
        self.assertEqual((station['sellPrice'], station['buyPrice'], station['demand'], station['stock']),
                         (250000, 200000, 500, 25))
        self.assertEqual(SystemFinderAPI._get_powerplay_from_cache('UNOCCUPIED')['controlling_power'], 'New Power')
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM commodity_prices_data WHERE market_id=1').fetchone()[0], 1)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchall(), [('ok',)])

    def test_cleanup_removes_old_prices_but_preserves_powerplay(self):
        self.assertEqual(self.listener._cleanup_old_data(), 1)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM commodity_prices_data WHERE market_id=3').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT count(*) FROM system_powerplay').fetchone()[0], 3)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchall(), [('ok',)])


if __name__ == '__main__':
    unittest.main()

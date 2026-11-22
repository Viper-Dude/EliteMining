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

    def test_colony_settlements_are_not_labelled_as_carriers(self):
        cases = (
            (3863986688, 'FleetCarrier', 'OnFootSettlement'),  # old wrong guess, details known
            (3877460224, 'FleetCarrier', None),                # old wrong guess, no details
            (3863979264, 'Unknown', None),                     # new settlement, no details
            (3790455808, 'FleetCarrier', None),                # settlement in the 37xx range
            (3791197696, 'Unknown', None),
            (3712345678, 'Unknown', None),                     # real carrier ID, type missing
            (3712345679, 'FleetCarrier', None),                # real carrier
            (3912345678, 'StrongholdCarrier', None),
        )
        with closing(sqlite3.connect(self.path)) as conn:
            for market_id, station_type, meta_type in cases:
                conn.execute('''INSERT INTO commodity_prices_data
                    (system_name,system_x,system_y,system_z,station_name,station_type,
                     commodity_name,sell_price,buy_price,demand,stock,market_id,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    ('Sol', 0, 0, 0, f'Station {market_id}', station_type, 'platinum',
                     100, 50, 1000, 2000, market_id, self.now))
                if meta_type:
                    conn.execute('INSERT INTO station_metadata VALUES (?,?,?,?,?,?,?)',
                                 (market_id, f'Station {market_id}', 'Sol', meta_type, 1, 10, self.now))
            conn.commit()
        rows = {r['marketId']: r for r in MarketplaceAPI._fetch_eddn_cache('platinum', 'Sol', 'buy', max_days_ago=7)}
        self.assertEqual(rows[3863986688]['stationType'], 'OnFootSettlement')
        self.assertEqual(rows[3877460224]['stationType'], 'Unknown')
        self.assertEqual(rows[3863979264]['stationType'], 'Unknown')
        self.assertEqual(rows[3712345678]['stationType'], 'FleetCarrier')
        self.assertEqual(rows[3712345679]['stationType'], 'FleetCarrier')
        self.assertEqual(rows[3912345678]['stationType'], 'StrongholdCarrier')
        kept = {r['marketId'] for r in MarketplaceAPI._fetch_eddn_cache(
            'platinum', 'Sol', 'buy', max_days_ago=7, exclude_carriers=True)}
        self.assertEqual(rows[3790455808]['stationType'], 'Unknown')
        self.assertEqual(rows[3791197696]['stationType'], 'Unknown')
        self.assertTrue({3863986688, 3877460224, 3863979264, 3790455808, 3791197696, 3912345678} <= kept)
        self.assertFalse({3712345678, 3712345679, 4} & kept)

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

    def test_jump_reports_give_distances_to_systems_missing_from_the_galaxy_database(self):
        def price(system, market_id):
            self.listener._update_commodity_prices(system, f'Port {market_id}', 'Coriolis', market_id, [
                dict(name='platinum', sellPrice=1000, buyPrice=0, demand=10, stock=0)], self.now)

        def journal(event, system, star_pos, **extra):
            self.listener._process_journal_message({'message': dict(
                event=event, StarSystem=system, StarPos=star_pos, timestamp=self.now, **extra)})

        def search():
            return {r['marketId']: r for r in MarketplaceAPI._fetch_eddn_cache(
                'platinum', 'Sol', 'buy', max_distance=500, max_days_ago=7)}

        price('Colony Alpha', 10)
        price('Far Colony', 11)
        self.assertFalse({10, 11} & search().keys())

        journal('FSDJump', 'Colony Alpha', [30, 40, 0])
        journal('CarrierJump', 'Far Colony', [1000, 0, 0])
        journal('Docked', 'Colony Beta', [0, 0, 12])
        journal('Location', 'Docked Here', [1, 1, 1], Docked=True)
        journal('Location', 'Floating', [2, 2, 2], Docked=False)
        journal('FSDJump', 'Explorer Jump', [3, 3, 3])
        journal('Docked', 'Broken Pos', [1, 2])
        journal('Docked', 'Bad Pos', ['x', 0, 0])
        journal('Scan', 'Not A Jump', [5, 5, 5])
        with closing(sqlite3.connect(self.path)) as conn:
            coords = {name: (x, y, z) for name, x, y, z in conn.execute('SELECT name, x, y, z FROM system_coords')}
            plan = conn.execute('EXPLAIN QUERY PLAN SELECT 1 FROM commodity_prices_data '
                                'WHERE system_name = ? LIMIT 1', ('Sol',)).fetchall()
        self.assertEqual(coords, {'Sol': (0, 0, 0), 'Colony Alpha': (30, 40, 0), 'Far Colony': (1000, 0, 0),
                                  'Colony Beta': (0, 0, 12), 'Docked Here': (1, 1, 1)})
        self.assertTrue(any('USING' in row[-1] and 'INDEX' in row[-1] for row in plan), plan)

        price('Colony Alpha', 12)
        price('Colony Beta', 13)
        rows = search()
        self.assertEqual((rows[10]['distance'], rows[12]['distance'], rows[13]['distance']), (50, 50, 12))
        self.assertNotIn(11, rows)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('SELECT system_x FROM commodity_prices_data WHERE market_id=12').fetchone()[0], 30)

        # A second report for the same system replaces the first, one row per system
        journal('FSDJump', 'Colony Alpha', [30, 40, 0])
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM system_coords WHERE name='Colony Alpha'").fetchone()[0], 1)

    def test_systems_without_jump_reports_use_coordinates_from_other_price_records(self):
        with closing(sqlite3.connect(self.path)) as conn:
            for market_id, coords in ((20, (6, 8, 0)), (21, (None, None, None))):
                conn.execute('''INSERT INTO commodity_prices_data
                    (system_name,system_x,system_y,system_z,station_name,station_type,
                     commodity_name,sell_price,buy_price,demand,stock,market_id,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    ('Colony Gamma', *coords, f'Station {market_id}', 'Coriolis', 'platinum',
                     100, 50, 1000, 2000, market_id, self.now))
            conn.commit()
        rows = {r['marketId']: r for r in MarketplaceAPI._fetch_eddn_cache('platinum', 'Sol', 'buy', max_days_ago=7)}
        self.assertEqual((rows[20]['distance'], rows[21]['distance']), (10, 10))

    def test_saved_prices_keep_their_original_source(self):
        self.listener._update_commodity_prices('Sol', 'Station 1', 'Coriolis', 1, [
            dict(name='platinum', sellPrice=250000, buyPrice=200000, demand=500, stock=25),
        ], self.now)
        MarketplaceAPI._backfill_eddn_cache([dict(
            marketId=2, systemName='Sol', stationName='Station 2', stationType='Outpost',
            commodityName='platinum', sellPrice=300, updatedAt=self.now, _source='Ardent')])
        rows = {row['marketId']: row for row in MarketplaceAPI._fetch_eddn_cache('platinum', 'Sol', 'buy', max_days_ago=7)}
        self.assertEqual((rows[1]['_source'], rows[2]['_source'], rows[4]['_source']), ('EDDN', 'Ardent', None))
        self.assertTrue(all(row['_saved'] for row in rows.values()))

    def test_cache_without_source_column_is_upgraded_and_keeps_records(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('ALTER TABLE commodity_prices_data DROP COLUMN source')
            conn.commit()
            before = conn.execute('SELECT * FROM commodity_prices_data ORDER BY id').fetchall()
        EDDNListener(self.path)
        with closing(sqlite3.connect(self.path)) as conn:
            after = conn.execute('SELECT * FROM commodity_prices_data ORDER BY id').fetchall()
        self.assertEqual([row[:-1] for row in after], before)
        self.assertTrue(all(row[-1] is None for row in after))

    def test_cache_uses_wal_and_readers_are_not_blocked_by_a_writer(self):
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
        with closing(sqlite3.connect(self.path, timeout=0.2)) as writer:
            writer.execute('BEGIN IMMEDIATE')
            writer.execute("UPDATE system_powerplay SET power_state='Stronghold' WHERE system_name='Sol'")
            with closing(sqlite3.connect(self.path, timeout=0.2)) as reader:
                state = reader.execute("SELECT power_state FROM system_powerplay WHERE system_name='Sol'").fetchone()[0]
            self.assertEqual(state, 'Fortified')
            writer.rollback()

    def test_wal_switch_failure_does_not_block_init(self):
        real_connect = sqlite3.connect

        class NoWal:
            def __init__(self, conn): self.conn = conn
            def execute(self, sql, *a):
                if 'journal_mode' in sql:
                    raise sqlite3.OperationalError('database is locked')
                return self.conn.execute(sql, *a)
            def close(self): self.conn.close()

        calls = []
        def connect(*args, **kwargs):
            calls.append(1)
            conn = real_connect(*args, **kwargs)
            return NoWal(conn) if len(calls) == 1 else conn

        with patch.object(sqlite3, 'connect', side_effect=connect):
            EDDNListener(self.path)
        self.assertGreater(len(calls), 1)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM system_powerplay').fetchone()[0], 3)

    def test_cleanup_removes_old_prices_but_preserves_powerplay(self):
        self.assertEqual(self.listener._cleanup_old_data(), 1)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM commodity_prices_data WHERE market_id=3').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT count(*) FROM system_powerplay').fetchone()[0], 3)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchall(), [('ok',)])


if __name__ == '__main__':
    unittest.main()

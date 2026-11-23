"""Check that a saved price is only replaced by a newer report (EDDN listener and search backfill)."""

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


class PriceNewestWinsChecks(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = str(Path(self._folder.name) / 'c.db')
        self.listener = EDDNListener(self.db)

    def tearDown(self):
        self._folder.cleanup()

    def listener_price(self, price, timestamp):
        self.listener._update_commodity_prices('Sol', 'Abraham Lincoln', 'Orbis', 128016640,
                                               [{'name': 'painite', 'sellPrice': price, 'demand': 10}],
                                               timestamp)

    def backfill_price(self, price, timestamp, source='Ardent'):
        with patch.object(MarketplaceAPI, 'EDDN_CACHE_PATH', self.db):
            MarketplaceAPI._backfill_eddn_cache([{
                'marketId': 128016640, 'systemName': 'Sol', 'stationName': 'Abraham Lincoln',
                'stationType': 'Orbis', 'commodityName': 'Painite', 'sellPrice': price,
                'demand': 10, 'updatedAt': timestamp, '_source': source}])

    def stored(self):
        with sqlite3.connect(self.db) as conn:
            return conn.execute('SELECT sell_price, updated_at, source FROM commodity_prices_data').fetchall()

    def test_older_listener_message_keeps_newer_price(self):
        self.listener_price(500000, '2026-11-23T12:00:00Z')
        self.listener_price(100000, '2026-11-23T11:00:00Z')
        self.assertEqual(self.stored(), [(500000, '2026-11-23T12:00:00Z', 'EDDN')])

    def test_newer_listener_message_replaces_price(self):
        self.listener_price(100000, '2026-11-23T11:00:00Z')
        self.listener_price(500000, '2026-11-23T12:00:00Z')
        self.assertEqual(self.stored(), [(500000, '2026-11-23T12:00:00Z', 'EDDN')])

    def test_older_backfill_row_keeps_newer_live_price(self):
        self.listener_price(500000, '2026-11-23T12:00:00Z')
        self.backfill_price(100000, '2026-11-23T11:59:59.000Z')
        self.assertEqual(self.stored(), [(500000, '2026-11-23T12:00:00Z', 'EDDN')])

    def test_newer_backfill_row_replaces_price(self):
        self.listener_price(100000, '2026-11-23T11:00:00Z')
        self.backfill_price(500000, '2026-11-23T11:00:00.500Z', 'Spansh')
        self.assertEqual(self.stored(), [(500000, '2026-11-23T11:00:00.500Z', 'Spansh')])

    def test_mixed_formats_compare_as_times(self):
        # As text '13:00:00+02:00' sorts after '12:00:00Z', but it is 11:00 UTC
        self.backfill_price(300000, '2026-11-23T13:00:00+02:00')  # 11:00 UTC
        self.listener_price(400000, '2026-11-23T12:00:00Z')
        self.assertEqual(self.stored()[0][0], 400000)
        self.backfill_price(200000, '2026-11-23 11:59:00')
        self.assertEqual(self.stored()[0][0], 400000)

    def test_equal_dates_keep_stored_row(self):
        self.listener_price(500000, '2026-11-23T12:00:00Z')
        self.backfill_price(100000, '2026-11-23T12:00:00.000Z')
        self.assertEqual(self.stored(), [(500000, '2026-11-23T12:00:00Z', 'EDDN')])

    def test_missing_or_unreadable_stored_date_is_replaced(self):
        for bad in (None, 'not a date'):
            with self.subTest(stored=bad):
                with sqlite3.connect(self.db) as conn:
                    conn.execute('DELETE FROM commodity_prices_data')
                self.backfill_price(100000, bad)
                self.listener_price(500000, '2026-11-23T12:00:00Z')
                self.assertEqual(self.stored(), [(500000, '2026-11-23T12:00:00Z', 'EDDN')])

    def test_report_without_date_keeps_dated_price(self):
        self.listener_price(500000, '2026-11-23T12:00:00Z')
        self.backfill_price(100000, None)
        self.assertEqual(self.stored(), [(500000, '2026-11-23T12:00:00Z', 'EDDN')])

    def details(self):
        with sqlite3.connect(self.db) as conn:
            return conn.execute('SELECT station_type, distance_to_arrival, system_x, system_y, system_z '
                                'FROM commodity_prices_data').fetchone()

    def test_older_or_equal_report_still_fills_missing_station_details(self):
        self.listener._update_commodity_prices('Sol', 'Abraham Lincoln', 'Unknown', 128016640,
                                               [{'name': 'painite', 'sellPrice': 500000}], '2026-11-23T12:00:00Z')
        with patch.object(MarketplaceAPI, 'EDDN_CACHE_PATH', self.db):
            MarketplaceAPI._backfill_eddn_cache([{
                'marketId': 128016640, 'systemName': 'Sol', 'stationName': 'Abraham Lincoln',
                'stationType': 'Orbis', 'commodityName': 'painite', 'sellPrice': 1, 'distanceToArrival': 506.5,
                'systemX': 0.0, 'systemY': 0.0, 'systemZ': 0.0,
                'updatedAt': '2026-11-23T12:00:00.000Z', '_source': 'Ardent'}])
        self.assertEqual(self.stored(), [(500000, '2026-11-23T12:00:00Z', 'EDDN')])
        self.assertEqual(self.details(), ('Orbis', 506.5, 0.0, 0.0, 0.0))

    def test_newer_report_without_type_keeps_known_type_and_details(self):
        self.backfill_price(100000, '2026-11-23T11:00:00.000Z')
        with sqlite3.connect(self.db) as conn:
            conn.execute('UPDATE commodity_prices_data SET distance_to_arrival = 506.5')
        self.listener._update_commodity_prices('Sol', 'Abraham Lincoln', 'Unknown', 128016640,
                                               [{'name': 'painite', 'sellPrice': 500000}], '2026-11-23T12:00:00Z')
        self.assertEqual(self.stored()[0][0], 500000)
        self.assertEqual(self.details()[:2], ('Orbis', 506.5))

    def test_known_type_is_only_changed_by_a_newer_report(self):
        self.backfill_price(100000, '2026-11-23T11:00:00.000Z')  # Orbis
        self.listener._update_commodity_prices('Sol', 'Abraham Lincoln', 'Coriolis', 128016640,
                                               [{'name': 'painite', 'sellPrice': 1}], '2026-11-23T10:00:00Z')
        self.assertEqual(self.details()[0], 'Orbis')
        self.listener._update_commodity_prices('Sol', 'Abraham Lincoln', 'Coriolis', 128016640,
                                               [{'name': 'painite', 'sellPrice': 1}], '2026-11-23T13:00:00Z')
        self.assertEqual(self.details()[0], 'Coriolis')

    def test_other_stations_and_commodities_are_still_added(self):
        self.listener_price(500000, '2026-11-23T12:00:00Z')
        self.listener._update_commodity_prices('Sol', 'Daedalus', 'Orbis', 1, [
            {'name': 'painite', 'sellPrice': 1}, {'name': 'platinum', 'sellPrice': 2}], '2026-11-23T10:00:00Z')
        self.assertEqual(len(self.stored()), 3)


if __name__ == '__main__':
    unittest.main()

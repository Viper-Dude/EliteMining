import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import carrier_names as names
from cargo_monitor import CargoMonitor
from commodity_market_tab import CommodityMarketTabMixin
from eddn_listener import EDDNListener


def signal(name, timestamp='2026-11-01T00:00:00Z', **fields):
    return dict(event='FSSSignalDiscovered', IsStation=True, SignalName=name, timestamp=timestamp, **fields)


class CarrierNamesTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.db = str(self.folder / 'cache.db')
        with closing(sqlite3.connect(self.db)) as conn, conn:
            names.ensure_tables(conn)
        names.load_names(self.db)

    def display(self, raw, kind='Unknown'):
        return names.station_display_name(dict(stationName=raw, stationType=kind))

    def test_signal_formats(self):
        for text, callsign, name in [
                ('[MMCO]EliteMining V0W-W7T', 'V0W-W7T', '[MMCO]EliteMining'),
                ('Bebop W1N-68Z', 'W1N-68Z', 'Bebop'),
                ("KING ED'S HAREM PALACE | MMC0", 'MMC0', "KING ED'S HAREM PALACE"),
                ('[TAG]  My Ship | GURS', 'GURS', '[TAG]  My Ship')]:
            with self.subTest(text=text):
                self.assertEqual(names.from_signal(signal(text))[:2], (callsign, name))

    def test_ordinary_stations_and_megaships(self):
        for event in [signal('STERLING PORT'), signal('MAN-154 Hogan-class Hauler'),
                      signal('Hauler ABC-123', SignalType='Megaship'), signal('W1N-68Z'),
                      dict(signal('Bebop W1N-68Z'), IsStation=False),
                      signal('Name | MMC0', timestamp='invalid')]:
            with self.subTest(event=event):
                self.assertIsNone(names.from_signal(event))

    def test_newest_wins_in_database_and_display(self):
        def seen(name, stamp):
            return names.from_signal(signal(name + ' W1N-68Z', stamp))
        old = seen('Old', '2026-11-01T02:00:00+02:00')
        new = seen('New', '2026-11-01T00:00:00.010Z')
        names.store_names(self.db, [old, new, old])
        names.store_names(self.db, [old, seen('Tie', '2026-11-01T00:00:00.010Z')])
        self.assertEqual(self.display('W1N-68Z'), 'New (W1N-68Z)')
        names.load_names(self.db)
        self.assertEqual(self.display('W1N-68Z'), 'New (W1N-68Z)')

    def test_failed_write_does_not_publish_or_advance_journal(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute('DROP TABLE carrier_journal_offsets')
        with self.assertRaises(sqlite3.OperationalError):
            names.store_names(self.db, [names.from_signal(signal('Name | MMC0'))], ('journal', 9))
        self.assertEqual(self.display('MMC0'), 'MMC0')
        names.load_names(self.db)
        self.assertEqual(self.display('MMC0'), 'MMC0')

    def test_journal_history_resumes_after_partial_record(self):
        path = self.folder / 'Journal.1.log'
        first = json.dumps(signal('Bebop W1N-68Z')).encode() + b'\n'
        second = json.dumps(dict(event='CarrierStats', Name='Squad Ship', Callsign='GURS',
                                 CarrierType='SquadronCarrier', timestamp='2026-11-01T00:00:00Z')).encode()
        path.write_bytes(first + second[:20])
        names.backfill(self.db, self.folder)
        self.assertEqual(self.display('W1N-68Z'), 'Bebop (W1N-68Z)')
        self.assertEqual(self.display('GURS'), 'GURS')
        with path.open('ab') as stream:
            stream.write(second[20:] + b'\n')
        names.backfill(self.db, self.folder)
        self.assertEqual(self.display('GURS'), 'Squad Ship (GURS)')
        with patch.object(names, 'from_journal', side_effect=AssertionError('replayed history')):
            names.backfill(self.db, self.folder)

    def test_live_journal_defers_db_work(self):
        jobs, listeners = [], []
        monitor = SimpleNamespace(_queue_background_job=jobs.append, add_journal_listener=listeners.append,
                                  backfill_carrier_names=Mock(), journal_dir=self.folder)
        CargoMonitor.start_carrier_names(monitor, self.db)
        listeners[0]([signal('Name | MMC0'), dict(event='Docked')])
        self.assertEqual(self.display('MMC0'), 'MMC0')
        for job in jobs:
            job()
        self.assertEqual(self.display('MMC0'), 'Name (MMC0)')

    def test_eddn_uses_individual_observation_times(self):
        listener = SimpleNamespace(database_path=self.db)
        message = {'$schemaRef': 'https://eddn.edcd.io/schemas/fsssignaldiscovered/1',
                   'header': {'gameversion': '4.0'}, 'message': {'signals': [
                       signal('Older | GURS'), signal('Newer | GURS', '2026-11-02T00:00:00Z')]}}
        EDDNListener._process_message(listener, message)
        self.assertEqual(self.display('GURS'), 'Newer (GURS)')
        message['header']['gameversion'] = '3.8'
        message['message']['signals'] = [signal('Legacy | GURS', '2026-11-03T00:00:00Z')]
        EDDNListener._process_message(listener, message)
        self.assertEqual(self.display('GURS'), 'Newer (GURS)')

    def test_display_and_market_action_target(self):
        names.store_names(self.db, [names.from_signal(signal('[TAG] Bebop W1N-68Z'))])
        row = dict(stationName='W1N-68Z', stationType='FleetCarrier')
        with patch('sqlite3.connect', side_effect=AssertionError('database access during display')):
            label = names.station_display_name(row)
            self.assertEqual(label, '[TAG] Bebop (W1N-68Z)')
            self.assertEqual(self.display('GURS', 'SquadronCarrier'), 'GURS')
            self.assertEqual(self.display('Jameson Memorial', 'Orbis'), 'Jameson Memorial')
        self.assertEqual(row['stationName'], 'W1N-68Z')
        tree = SimpleNamespace(item=Mock(return_value=(' Sol ', label)), _raw_station_names={'id': 'W1N-68Z'})
        self.assertEqual(CommodityMarketTabMixin._row_system_station(tree, 'id'), ('Sol', 'W1N-68Z'))


if __name__ == '__main__':
    unittest.main()

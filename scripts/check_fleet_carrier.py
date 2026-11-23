from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from journal_parser import JournalParser
from fleet_carrier_tab import FleetCarrierTab
from check_ring_finder_search import load_methods

App = load_methods('app/main.py', 'App', {
    '_process_journals_for_catchup', '_process_journals_for_catchup_with_progress',
})
App._process_journals_for_catchup.__globals__.update(os=os, log=logging.getLogger('fc-test'))
Monitor = load_methods('app/cargo_monitor.py', 'CargoMonitor', {'_process_journal_event_impl'})
Monitor._process_journal_event_impl.__globals__.update(json=json)


class CarrierChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        with patch('path_utils.get_app_data_dir', return_value=self.folder.name):
            self.parser = JournalParser(self.folder.name, user_db=Mock())
        self.parser.carrier_data.update(carrier_id=111, name='Own Carrier', callsign='OWN-111', system='Sol')

    def event(self, kind, **fields):
        return dict(event=kind, timestamp='2026-11-01T12:00:00Z', **fields)

    def test_foreign_carrier_does_not_change_own_state(self):
        for kind in ('Docked', 'Location', 'CarrierJump', 'CarrierDepositFuel'):
            with self.subTest(kind=kind):
                before = deepcopy(self.parser.carrier_data)
                self.parser.process_carrier_event(self.event(
                    kind, StationType='FleetCarrier', Docked=True, MarketID=222,
                    CarrierID=222, StationName='OTHER-222', StarSystem='Achenar', Total=900))
                self.assertEqual(self.parser.carrier_data, before)

    def test_own_docking_and_jump(self):
        for kind in ('Docked', 'Location', 'CarrierJump'):
            with self.subTest(kind=kind):
                self.parser.process_carrier_event(self.event(
                    kind, StationType='FleetCarrier', Docked=True, MarketID=111,
                    StationName='OWN-111', StarSystem=kind))
                self.assertEqual(self.parser.carrier_data['system'], kind)
                self.assertEqual(self.parser.carrier_data['jump_history'][0]['exact'], kind == 'CarrierJump')

    def test_unknown_owner_is_not_inferred_from_docking(self):
        self.parser.carrier_data.update(carrier_id=None, callsign=None)
        self.parser.process_carrier_event(self.event('Location', StationType='FleetCarrier',
            Docked=True, MarketID=222, StationName='OTHER-222', StarSystem='Achenar'))
        self.assertEqual(self.parser.carrier_data['system'], 'Sol')
        self.assertIsNone(self.parser.carrier_data['carrier_id'])

    def test_callsign_fallback_and_id_mismatch(self):
        self.assertTrue(self.parser._is_own_carrier({'StationName': 'OWN-111'}))
        self.assertFalse(self.parser._is_own_carrier({'MarketID': 222, 'StationName': 'OWN-111'}))

    def test_undocked_location_is_ignored(self):
        self.parser.process_carrier_event(self.event('Location', StationType='FleetCarrier',
            Docked=False, MarketID=111, StarSystem='Achenar'))
        self.assertEqual(self.parser.carrier_data['system'], 'Sol')

    def test_remote_carrier_location_does_not_move_commander(self):
        monitor = Monitor()
        monitor.journal_parser = self.parser
        monitor.main_app_ref = SimpleNamespace(update_current_system=Mock())
        monitor._process_journal_event_impl(json.dumps(self.event(
            'CarrierLocation', CarrierID=111, CarrierType='FleetCarrier', StarSystem='Achenar')))
        self.assertEqual(self.parser.carrier_data['system'], 'Achenar')
        monitor.main_app_ref.update_current_system.assert_not_called()

    def test_foreign_carrier_jump_still_moves_commander(self):
        monitor = Monitor()
        monitor.journal_parser = self.parser
        monitor.main_app_ref = SimpleNamespace(update_current_system=Mock())
        monitor._queue_cache_upserts = Mock()
        monitor._process_journal_event_impl(json.dumps(self.event(
            'CarrierJump', MarketID=222, StarSystem='Achenar', StarPos=[3, 4, 0])))
        self.assertEqual(self.parser.carrier_data['system'], 'Sol')
        monitor.main_app_ref.update_current_system.assert_called_once_with(
            'Achenar', (3, 4, 0), count_visit=True, event_timestamp='2026-11-01T12:00:00Z')

    def test_parser_reader_replays_fuel_and_bank_events(self):
        events = [self.event('CarrierDepositFuel', CarrierID=111, Total=900),
                  self.event('CarrierBankTransfer', CarrierID=111, CarrierBalance=5000)]
        with patch.object(self.parser, 'find_journal_files', return_value=['Journal.log']), \
                patch.object(self.parser, 'parse_journal_file', return_value=events), \
                patch.object(self.parser, '_fix_missing_ring_coordinates', return_value=0):
            stats = self.parser.parse_all_journals()
        self.assertEqual(stats['events_processed'], 2)
        self.assertEqual(self.parser.carrier_data['fuel_level'], 900)
        self.assertEqual(self.parser.carrier_data['balance'], 5000)

    def test_finance_snapshot_and_update_share_fields(self):
        finance = dict(CarrierBalance=1000, ReserveBalance=200, AvailableBalance=800,
                       ReservePercent=20, TaxRate_rearm=0, TaxRate_refuel=5, TaxRate_repair=10)
        self.parser.process_carrier_event(self.event('CarrierStats', CarrierID=111, Finance=finance))
        self.assertEqual(self.parser.carrier_data['available_balance'], 800)
        self.parser.process_carrier_event(self.event('CarrierFinance', CarrierID=111, AvailableBalance=900))
        self.assertEqual(self.parser.carrier_data['available_balance'], 900)
        self.assertEqual(self.parser.carrier_data['tax_rearm'], 0)

    def test_batch_only_writes_at_completion(self):
        with patch.object(self.parser, '_save_carrier_data') as save:
            self.parser._suppress_carrier_notifications = True
            for _ in range(100):
                self.parser._notify_carrier_updated()
            save.assert_not_called()
            self.parser._suppress_carrier_notifications = False
            self.parser._notify_carrier_updated()
            save.assert_called_once()

    def test_failed_atomic_replace_preserves_saved_data(self):
        self.parser._save_carrier_data()
        path = Path(self.parser._carrier_save_path)
        original = path.read_bytes()
        self.parser.carrier_data['system'] = 'Achenar'
        with patch('journal_parser.os.replace', side_effect=OSError('test failure')):
            self.parser._save_carrier_data()
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_squadron_carrier_events_are_ignored(self):
        before = deepcopy(self.parser.carrier_data)
        for kind in ('CarrierStats', 'CarrierLocation', 'CarrierFinance', 'CarrierJumpRequest',
                     'CarrierJumpCancelled', 'CarrierBankTransfer'):
            with self.subTest(kind=kind):
                self.parser.process_carrier_event(self.event(
                    kind, CarrierType='SquadronCarrier', CarrierID=333, Name='Squadron',
                    Callsign='SQD-333', StarSystem='Achenar', SystemName='Achenar',
                    DepartureTime='2026-11-01T12:15:00Z', CarrierBalance=1))
                self.assertEqual(self.parser.carrier_data, before)
        self.parser.process_carrier_event(self.event(
            'CarrierStats', CarrierType='FleetCarrier', CarrierID=111, Name='Renamed'))
        self.assertEqual(self.parser.carrier_data['name'], 'Renamed')

    def test_pending_jump_survives_restart(self):
        self.parser.process_carrier_event(self.event(
            'CarrierJumpRequest', CarrierID=111, SystemName='Achenar', Body='Achenar 1',
            DepartureTime='2026-11-01T12:15:00Z'))
        with patch('path_utils.get_app_data_dir', return_value=self.folder.name):
            restarted = JournalParser(self.folder.name, user_db=Mock())
        self.assertEqual(restarted.carrier_data['jump_destination'], 'Achenar')
        self.assertEqual(restarted.carrier_data['jump_body'], 'Achenar 1')
        self.assertEqual(restarted.carrier_data['jump_departure_time'], '2026-11-01T12:15:00Z')

    def test_failed_catchup_scan_restores_carrier_updates(self):
        for method in ('_process_journals_for_catchup', '_process_journals_for_catchup_with_progress'):
            with self.subTest(method=method):
                app = App()
                app.cargo_monitor = SimpleNamespace(journal_parser=self.parser, user_db=Mock(),
                                                    _catchup_scan_in_progress=False)
                app.after = Mock(side_effect=RuntimeError('main loop gone'))
                callback = Mock(side_effect=RuntimeError('main loop gone'))
                with patch.dict(sys.modules, mining_missions=SimpleNamespace(
                        MISSIONS_AVAILABLE=False, get_mission_tracker=lambda: None)), \
                        patch.object(self.parser, '_save_carrier_data') as save, \
                        self.assertRaises(RuntimeError):
                    kwargs = {'progress_callback': callback} if method.endswith('progress') else {}
                    getattr(app, method)(['missing.log'], **kwargs)
                self.assertFalse(self.parser._suppress_carrier_notifications)
                self.assertFalse(app.cargo_monitor._catchup_scan_in_progress)
                save.assert_called_once()

    def test_both_catchup_readers_replay_fuel_and_balance_and_save_once(self):
        events = [self.event('CarrierDepositFuel', CarrierID=111, Total=900),
                  self.event('CarrierBankTransfer', CarrierID=111, CarrierBalance=5000)]
        journal = Path(self.folder.name) / 'Journal.log'
        journal.write_text('\n'.join(map(json.dumps, events)), encoding='utf-8')
        for method in ('_process_journals_for_catchup', '_process_journals_for_catchup_with_progress'):
            with self.subTest(method=method):
                self.parser.carrier_data.update(fuel_level=0, balance=0)
                app = App()
                app.cargo_monitor = SimpleNamespace(journal_parser=self.parser, user_db=Mock())
                app.after = Mock()
                app._ensure_current_system_visited = Mock()
                app._trigger_ring_auto_search = Mock()
                with patch.dict(sys.modules, mining_missions=SimpleNamespace(
                        MISSIONS_AVAILABLE=False, get_mission_tracker=lambda: None)), \
                        patch('path_utils.get_app_data_dir', return_value=self.folder.name), \
                        patch.object(self.parser, '_save_carrier_data') as save:
                    getattr(app, method)([str(journal)])
                self.assertEqual(self.parser.carrier_data['fuel_level'], 900)
                self.assertEqual(self.parser.carrier_data['balance'], 5000)
                save.assert_called_once()


class CarrierUIChecks(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.global_binding = self.root.bind_all('<MouseWheel>')
        with patch('config.load_theme', return_value='dark_gray'):
            self.tab = FleetCarrierTab(self.root)
        self.cd = dict(name='Own Carrier', system='Sol', space_total=25000,
                       space_cargo=0, space_crew=0, space_free=25000)

    def test_zero_and_unknown_cargo(self):
        self.tab._refresh(self.cd)
        self.assertNotEqual(self.tab._sv['cargo_used'].get(), '-')
        self.assertNotEqual(self.tab._sv['cargo_crew'].get(), '-')
        self.assertEqual(self.tab._sv['cargo_used_total'].get(), '0 / 25,000')
        self.cd['space_cargo'] = None
        self.tab._refresh(self.cd)
        self.assertEqual(self.tab._sv['cargo_used'].get(), '-')
        self.cd['space_free'] = None
        self.tab._refresh(self.cd)
        self.assertEqual(self.tab._sv['cargo_used_total'].get(), '-')

    def test_used_space_includes_reserved_space_and_packs(self):
        self.cd.update(space_cargo=10000, space_crew=1000, space_free=9000)
        self.tab._refresh(self.cd)
        self.assertEqual(self.tab._sv['cargo_used_total'].get(), '16,000 / 25,000')

    def test_messages_sit_under_help_banner(self):
        self.tab._refresh(dict(system='Sol'))
        children = self.tab._scroll_frame.pack_slaves()
        self.assertEqual(children.index(self.tab._hint_lbl), children.index(self.tab._help_frame) + 1)
        fresh = FleetCarrierTab(self.root)
        children = fresh._scroll_frame.pack_slaves()
        self.assertEqual(children.index(fresh._no_data_lbl), children.index(fresh._help_frame) + 1)

    def test_history_widgets_survive_unchanged_refresh(self):
        self.cd['jump_history'] = [dict(system='Sol', timestamp='2026-11-01T12:00:00Z')]
        self.tab._refresh(self.cd)
        row = self.tab._history_rows[0]
        self.tab._refresh(self.cd)
        self.assertIs(self.tab._history_rows[0], row)
        self.cd['jump_history'][0]['system'] = 'Achenar'
        self.tab._refresh(self.cd)
        self.assertIsNot(self.tab._history_rows[0], row)

    def test_mousewheel_is_local_including_history(self):
        self.tab._refresh(self.cd)
        self.assertEqual(self.root.bind_all('<MouseWheel>'), self.global_binding)
        self.assertTrue(self.tab._canvas.bind('<MouseWheel>'))
        self.assertTrue(self.tab._history_rows[0].bind('<MouseWheel>'))

    def test_expired_tick_clears_display_without_mutating_parser(self):
        self.cd.update(jump_destination='Achenar', jump_body='A 1',
                       jump_departure_time=(datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat())
        self.tab._tracker = SimpleNamespace(carrier_data=self.cd, set_on_updated=Mock())
        before = deepcopy(self.cd)
        self.tab._tick_countdown()
        self.assertEqual(self.cd, before)
        self.assertEqual(self.tab._sv['jump_countdown'].get(), '-')
        self.assertEqual(self.tab._sv['jump_departure'].get(), '-')
        self.assertIsNone(self.tab._countdown_job)

    def test_cancel_and_destroy_remove_pending_timer(self):
        self.cd['jump_departure_time'] = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        self.tab._refresh(self.cd)
        first = self.tab._countdown_job
        self.assertIn(first, self.root.tk.call('after', 'info'))
        self.cd['jump_departure_time'] = None
        self.tab._refresh(self.cd)
        self.assertNotIn(first, self.root.tk.call('after', 'info'))
        self.cd['jump_departure_time'] = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        self.tab._refresh(self.cd)
        pending = self.tab._countdown_job
        self.tab.destroy()
        self.assertNotIn(pending, self.root.tk.call('after', 'info'))


if __name__ == '__main__':
    unittest.main(verbosity=2)

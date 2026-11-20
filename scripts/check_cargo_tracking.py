"""Check cargo tracking and callbacks without the removed popup UI."""

import ast
import contextlib
import io
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'app/main.py').read_text(encoding='utf-8-sig')
TREE = ast.parse(SOURCE)
CARGO_TREE = ast.parse((ROOT / 'app/cargo_monitor.py').read_text(encoding='utf-8-sig'))
CARGO = next(n for n in CARGO_TREE.body if isinstance(n, ast.ClassDef) and n.name == 'CargoMonitor')
APP = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'App')
NAMES = {
    'read_cargo_json', '_finish_read_cargo_json', '_process_journal_event_impl',
    '_check_status_for_ship_changes', '_update_limpet_count_in_cargo_json',
    'update_cargo', 'set_total_cargo', 'clear_cargo', 'reset_materials',
    'set_max_cargo', '_get_prospector_count', 'cleanup',
}


class CargoTrackingChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        ns = dict(json=json, os=os, time=time, threading=threading, logging=logging)
        module = ast.Module(body=[ast.ClassDef(name='Monitor', bases=[], keywords=[], decorator_list=[],
            body=[n for n in CARGO.body if isinstance(n, ast.FunctionDef) and n.name in NAMES])], type_ignores=[])
        ast.fix_missing_locations(module)
        exec(compile(module, str(ROOT / 'app/cargo_monitor.py'), 'exec'), ns)
        self.monitor = m = ns['Monitor']()
        m.cargo_json_path = str(Path(self.folder.name) / 'Cargo.json')
        m.status_json_path = str(Path(self.folder.name) / 'Status.json')
        m.cargo_items = {}; m.current_cargo = 0; m.max_cargo = 200
        m.materials_collected = {}; m.materials_localized_names = {}; m.MATERIAL_GRADES = {'Iron': 1}
        m.session_start_snapshot = {'active': True}
        m.session_minerals_mined = {}; m.session_materials_collected = {}; m.refinery_contents = {}
        m.last_cargo_mtime = 0; m.last_status_mtime = 0
        m.last_transfer_time = 0; m.transfer_exclusion_window = 3
        m.refinery_prompt_shown_for_this_transfer = False
        m.update_callback = Mock(); m.capacity_changed_callback = Mock(); m.ship_info_changed_callback = Mock()
        m.journal_parser = types.SimpleNamespace(process_carrier_event=Mock())
        m._update_ship_info = Mock(); m._update_mission_progress_from_cargo = Mock()
        m.record_mining_activity = Mock(); m._prompt_for_refinery_contents_multi_session = Mock()

    def event(self, name, **fields):
        self.monitor._process_journal_event_impl(json.dumps(dict(event=name, **fields)))

    def write_cargo(self, platinum=10, limpets=4):
        data = {'Count': platinum + limpets, 'Inventory': [
            {'Name': 'platinum', 'Name_Localised': 'Platinum', 'Count': platinum},
            {'Name': 'drones', 'Name_Localised': 'Limpet', 'Count': limpets},
        ]}
        Path(self.monitor.cargo_json_path).write_text(json.dumps(data), encoding='utf-8')

    def test_cargo_file_updates_counters_missions_and_callback(self):
        m = self.monitor
        self.write_cargo()
        self.assertTrue(m.read_cargo_json())
        self.assertEqual(m.cargo_items, {'Platinum': 10, 'Limpet': 4})
        self.assertEqual(m.current_cargo, 14)
        self.assertEqual(m.session_minerals_mined, {'Platinum': 10})
        m._update_mission_progress_from_cargo.assert_called_once()
        m.update_callback.assert_called_once_with()
        self.assertFalse(m.read_cargo_json())
        m.update_callback.assert_called_once()

    def test_background_cargo_read_marshals_callback_to_main_thread(self):
        m = self.monitor
        self.write_cargo()
        m.main_app_ref = types.SimpleNamespace(after=Mock())
        worker = threading.Thread(target=m.read_cargo_json)
        worker.start(); worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        m.update_callback.assert_not_called()
        m.main_app_ref.after.assert_called_once_with(0, m._finish_read_cargo_json)
        m.main_app_ref.after.call_args.args[1]()
        m.update_callback.assert_called_once_with()

    def test_sales_ejections_and_transfers_preserve_session_totals(self):
        m = self.monitor
        m.cargo_items = {'Platinum': 20, 'Limpet': 4}; m.current_cargo = 24
        m.session_minerals_mined = {'Platinum': 20}
        self.event('MarketSell', Type='platinum', Type_Localised='Platinum', Count=5)
        self.assertEqual(m.current_cargo, 19)
        m.update_callback.assert_called_with(event_type='MarketSell', count=5)
        self.event('EjectCargo', Type='platinum', Type_Localised='Platinum', Count=3)
        self.assertEqual(m.cargo_items['Platinum'], 12)
        self.assertEqual(m.session_minerals_mined['Platinum'], 17)
        m.update_callback.assert_called_with(event_type='EjectCargo', count=3)
        self.event('CargoTransfer', Transfers=[{'Type': 'platinum', 'Count': 12, 'Direction': 'tocarrier'}])
        self.assertEqual(m.cargo_items, {'Limpet': 4})
        self.assertEqual(m.session_minerals_mined['Platinum'], 17)
        m._prompt_for_refinery_contents_multi_session.assert_called_once()
        self.event('CargoTransfer', Transfers=[{'Type': 'platinum', 'Count': 8, 'Direction': 'toship'}])
        self.assertEqual(m.current_cargo, 12)
        self.assertEqual(m.session_minerals_mined['Platinum'], 17)

    def test_materials_and_loadout_callbacks_work_without_widgets(self):
        m = self.monitor
        self.event('MaterialCollected', Category='Raw', Name='iron', Name_Localised='Eisen', Count=3)
        self.assertEqual(m.materials_collected, {'Iron': 3})
        self.assertEqual(m.session_materials_collected, {'Iron': 3})
        self.assertEqual(m.materials_localized_names, {'Iron': 'Eisen'})
        m.update_callback.assert_called_once_with()
        self.event('Loadout', CargoCapacity=512)
        self.assertEqual(m.max_cargo, 512)
        m.capacity_changed_callback.assert_called_once_with(512)
        m.ship_info_changed_callback.assert_called_once_with()

    def test_status_capacity_refresh_and_module_changes(self):
        m = self.monitor
        m.read_cargo_json = Mock()
        Path(m.status_json_path).write_text(json.dumps({'CargoCapacity': 384}))
        m._check_status_for_ship_changes()
        self.assertEqual(m.max_cargo, 384)
        m.capacity_changed_callback.assert_called_once_with(384)
        m.read_cargo_json.assert_called_once_with()
        m.refresh_ship_capacity = Mock(return_value=False)
        m._force_loadout_scan = Mock()
        self.event('ModuleBuy', Slot='Slot01_Size8', Item='int_cargorack_size8_class1')
        m.refresh_ship_capacity.assert_called_once_with()
        m._force_loadout_scan.assert_called_once_with()

    def test_limpet_adjustment_keeps_other_cargo(self):
        m = self.monitor
        self.write_cargo(); m.cargo_items = {'Platinum': 10, 'Limpet': 4}
        for count in (7, 0, 2):
            with self.subTest(count=count):
                self.assertTrue(m._update_limpet_count_in_cargo_json(count))
                data = json.loads(Path(m.cargo_json_path).read_text())
                self.assertEqual(data['Count'], 10 + count)
                self.assertEqual(m._get_prospector_count(), count)
                self.assertEqual(m.cargo_items['Platinum'], 10)

    def test_direct_updates_reset_and_shutdown_need_no_popup(self):
        m = self.monitor
        m.update_cargo('Platinum', 5)
        m.update_cargo('Limpet', 3)
        self.assertEqual(m.current_cargo, 8)
        self.assertEqual(m.session_minerals_mined, {'Platinum': 5})
        m.update_callback.assert_called_with()
        m.reset_materials()
        self.assertEqual(m.current_cargo, 8)
        self.assertEqual(m.session_minerals_mined, {})
        m.set_max_cargo(256)
        self.assertEqual(m.max_cargo, 256)
        m._stop_event = threading.Event(); m.journal_monitor_active = True
        m.cleanup()
        self.assertTrue(m._stop_event.is_set())
        self.assertFalse(m.journal_monitor_active)

    def test_old_popup_preferences_are_ignored_and_active_settings_save(self):
        methods = [n for n in APP.body if isinstance(n, ast.FunctionDef)
                   and n.name in {'_load_cargo_preferences', '_save_cargo_preferences'}]
        values = {name: Mock(get=Mock(return_value=value)) for name, value in {
            'cargo_max_capacity': 256, 'cargo_show_in_overlay': True, 'overlay_only_game_focused': False,
            'hide_overlays_in_supercruise': True, 'overlay_only_mining_session': False,
        }.items()}
        a = types.SimpleNamespace(**values, cargo_text_overlay=types.SimpleNamespace(set_enabled=Mock()))
        cfg = {name: value.get() for name, value in values.items()}
        cfg.update(cargo_enabled=True, cargo_display_mode='Compact', cargo_position='Custom', cargo_transparency=1)
        ns = {'_load_cfg': lambda: cfg}
        exec(compile(ast.Module(body=methods, type_ignores=[]), 'cargo_preferences', 'exec'), ns)
        ns['_load_cargo_preferences'](a)
        a.cargo_max_capacity.set.assert_called_once_with(256)
        a.cargo_text_overlay.set_enabled.assert_called_once_with(True)
        config = types.ModuleType('config'); config.update_config_values = Mock()
        with patch.dict('sys.modules', {'config': config}):
            ns['_save_cargo_preferences'](a)
        self.assertEqual(config.update_config_values.call_args.args[0], {name: value.get() for name, value in values.items()})


if __name__ == '__main__':
    unittest.main(verbosity=2)

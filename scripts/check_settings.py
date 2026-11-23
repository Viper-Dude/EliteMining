"""Exercise Settings callbacks and backup/restore against temporary user data."""

import ast
import copy
import datetime as dt
import importlib.util
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import tkinter as tk
import types
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / 'app/main.py').read_text(encoding='utf-8-sig'))
APP = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'App')
METHODS = {n.name: n for n in APP.body if isinstance(n, ast.FunctionDef)}


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class SettingsChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'app'
        (self.data / 'data').mkdir(parents=True)
        self.profile_dir = self.root / 'Voiceattack Profile'
        self.profile_dir.mkdir()
        spec = importlib.util.spec_from_file_location('settings_test_config', ROOT / 'app/config.py')
        self.config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.config)
        self.config.CONFIG_FILE = str(self.root / 'config.json')
        self.config._save_cfg({'language': 'en', 'ui_scale': 1.0, 'old': True})
        self.events = []
        self.dialogs = []
        self.zip_path = self.root / 'backup.zip'
        utils = types.SimpleNamespace(
            centered_message=lambda *args: self.dialogs.append(args),
            centered_askyesno=lambda *args: False,
        )
        materials = types.SimpleNamespace(KNOWN_MATERIALS=['Platinum', 'New mineral'], CORE_ONLY=set())
        self.modules = patch.dict(sys.modules, {'config': self.config, 'app_utils': utils, 'prospector_panel': materials})
        self.modules.start()
        self.addCleanup(self.modules.stop)

        def fail(*args):
            self.fail(str(args))

        self.ns = dict(
            os=os, sys=sys, json=json, zipfile=zipfile, dt=dt, APP_VERSION='test',
            _load_cfg=self.config._load_cfg, _save_cfg=self.config._save_cfg,
            flush_config=self.config.flush_config,
            t=lambda key: key + ' {num}',
            filedialog=types.SimpleNamespace(asksaveasfilename=lambda **kw: str(self.zip_path)),
            messagebox=types.SimpleNamespace(showerror=fail, showwarning=fail),
        )
        self.app = types.SimpleNamespace(
            _get_app_data_dir=lambda: str(self.data),
            _set_status=lambda text: None,
            _restart_app=lambda: self.events.append('restart'),
            prospector_panel=types.SimpleNamespace(session_active=False),
        )

    def compile(self, node, extra=None):
        ns = self.ns.copy()
        ns.update(extra or {})
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<settings checks>', 'exec'), ns)
        return ns[node.name]

    def method(self, name):
        return self.compile(METHODS[name])

    def nested(self, name, extra):
        node = next(n for n in ast.walk(METHODS['_build_interface_options_tab'])
                    if isinstance(n, ast.FunctionDef) and n.name == name)
        return self.compile(node, extra)

    def backup(self, **flags):
        self.method('_create_backup')(self.app, False, False, False,
                                      flags.get('profile', False),
                                      flags.get('database', False), False,
                                      flags.get('config', False))

    def restore(self, **flags):
        self.method('_restore_from_backup')(self.app, str(self.zip_path), False, False, False,
                                            flags.get('profile', False),
                                            flags.get('database', False), False,
                                            flags.get('config', False))

    def test_all_preset_slots_keep_saved_maps_independent(self):
        for num in range(1, 7):
            with self.subTest(slot=num):
                original = {'announce_map': {'Platinum': True}, 'min_pct_map': {'Platinum': 20.0}}
                saved = copy.deepcopy(original)
                panel = types.SimpleNamespace(
                    _load_cfg=lambda: {f'announce_preset_{num}': saved},
                    announce_map={'New mineral': False}, min_pct_map={'New mineral': 30},
                    threshold=Var(20), _save_announce_map=lambda: None,
                    _save_min_pct_map=lambda: None, _save_threshold_value=lambda: None,
                )
                self.app.prospector_panel = panel
                self.app._ann_update_display = lambda: None
                self.app._ann_set_active_preset = lambda n: None
                self.app._ann_preset_notice = None
                self.app._show_notice = lambda label, msg: None
                self.method('_ann_load_preset')(self.app, num)
                self.assertFalse(panel.announce_map['New mineral'])
                panel.min_pct_map['Platinum'] = 45
                panel.announce_map['Platinum'] = False
                self.assertEqual(saved, original)

    def test_scale_can_revert_without_restart(self):
        self.app.ui_scale_var = Var('120%')
        callback = self.nested('_on_ui_scale_change', dict(
            self=self.app, _current_ui_scale_display='100%', _current_ui_scale=1.0,
            _ui_scale_options={'100%': 1.0, '120%': 1.2},
            load_ui_scale=self.config.load_ui_scale, save_ui_scale=self.config.save_ui_scale,
            scrollable_frame=types.SimpleNamespace(winfo_toplevel=lambda: None),
        ))
        callback()
        self.app.ui_scale_var.set('100%')
        callback()
        self.assertEqual(self.config.load_ui_scale(), 1.0)

    def test_language_can_revert_without_restart(self):
        self.app.language_var = Var('Deutsch')
        self.app._lang_name_to_code = {'English': 'en', 'Deutsch': 'de'}
        self.app.lang_display_label = types.SimpleNamespace(config=lambda **kw: None)
        callback = self.nested('_on_language_change', dict(
            self=self.app, saved_lang='en', load_config_func=self.config._load_cfg,
            save_config_func=self.config._save_cfg,
            scrollable_frame=types.SimpleNamespace(winfo_toplevel=lambda: None),
        ))
        callback()
        self.app.language_var.set('English')
        callback()
        self.assertEqual(self.config._load_cfg()['language'], 'en')

    def test_auto_search_uses_ring_finder_toggle(self):
        self.app.auto_search_enabled = Var(False)
        self.app.ring_finder = types.SimpleNamespace(
            auto_search_var=Var(True),
            _on_auto_search_toggle=lambda: self.events.append('toggle'),
        )
        self.nested('_on_auto_search_toggle', {'self': self.app})()
        self.assertFalse(self.app.ring_finder.auto_search_var.get())
        self.assertEqual(self.events, ['toggle'])

    def test_material_edits_update_startup_snapshot(self):
        tree = ast.parse((ROOT / 'app/prospector_panel.py').read_text(encoding='utf-8-sig'))
        panel_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and
                           any(isinstance(m, ast.FunctionDef) and m.name == '_save_min_pct_map' for m in n.body))
        methods = {n.name: n for n in panel_class.body if isinstance(n, ast.FunctionDef)}
        panel = types.SimpleNamespace(
            announce_map={'Platinum': False}, min_pct_map={'Platinum': 42}, threshold=Var(25),
            _load_cfg=self.config._load_cfg, _save_cfg=self.config._save_cfg,
        )
        panel._save_last_material_settings = lambda: self.compile(methods['_save_last_material_settings'])(panel)
        for name in ('_save_announce_map', '_save_min_pct_map'):
            self.compile(methods[name])(panel)
        saved = self.config._load_cfg()['last_material_settings']
        self.assertEqual(saved['min_pct_map'], {'Platinum': 42})
        self.assertEqual(saved['announce_map'], {'Platinum': False})

    def test_announcement_toggle_saves_snapshot_once(self):
        calls = []
        self.app.announcement_vars = {'Core Asteroids': Var(1)}
        self.app.prospector_panel._save_last_material_settings = lambda: calls.append('snapshot')
        self.app._ann_update_preset_buttons = lambda: calls.append('buttons')
        self.app._save_announcement_preferences = lambda: self.method('_save_announcement_preferences')(self.app)
        self.ns['ANNOUNCEMENT_TOGGLES'] = {'Core Asteroids': (None, '')}
        self.method('_on_announcement_change')(self.app)
        self.assertEqual(calls, ['snapshot', 'buttons'])

    def test_typed_threshold_is_clamped_and_saved(self):
        panel = types.SimpleNamespace(threshold=Var(150), _save_threshold_value=lambda: self.events.append('saved'))
        self.app.prospector_panel = panel
        self.app._ann_check_modified = lambda: None
        node = next(n for n in ast.walk(METHODS['_build_announcements_tab'])
                    if isinstance(n, ast.FunctionDef) and n.name == '_ann_threshold_changed')
        callback = self.compile(node, {'self': self.app, 'tk': tk})
        callback()
        self.assertEqual(panel.threshold.get(), 100)
        panel.threshold.set('invalid')
        callback()
        self.assertEqual(panel.threshold.get(), 20)
        self.assertEqual(self.events, ['saved', 'saved'])

    def test_restart_flushes_pending_settings_before_launch(self):
        self.config.update_config_value('pending', 'keep')
        self.app.ui_scale = 1.0
        self.app.state = lambda: 'normal'
        self.app.geometry = lambda: '1000x700+0+0'
        self.app._save_sash_positions_now = lambda: None
        self.app.destroy = lambda: None
        self.app._confirm_unsaved_presets = lambda: True

        def launch(*args, **kwargs):
            disk = json.loads(Path(self.config.CONFIG_FILE).read_text())
            self.assertEqual(disk['pending'], 'keep')
            self.events.append('launch')

        with patch('subprocess.Popen', side_effect=launch), patch('sys.exit', side_effect=SystemExit):
            with self.assertRaises(SystemExit):
                self.compile(METHODS['_restart_app'], {'log': logging.getLogger('settings checks')})(self.app)
        self.assertEqual(self.events, ['launch'])

    def test_restore_stops_session_before_replacing_config(self):
        self.app.prospector_panel.session_active = True

        def stop():
            self.assertTrue(self.config._load_cfg()['old'])
            self.events.append('stop')
            self.app.prospector_panel.session_active = False

        self.app.prospector_panel._session_stop = stop
        with zipfile.ZipFile(self.zip_path, 'w') as archive:
            archive.writestr('config.json', '{"restored": true}')
        self.restore(config=True)
        self.assertEqual(self.events, ['stop', 'restart'])

    def test_backup_includes_unflushed_configuration(self):
        self.config.update_config_value('pending', 'saved')
        self.backup(config=True)
        with zipfile.ZipFile(self.zip_path) as archive:
            self.assertEqual(json.loads(archive.read('config.json'))['pending'], 'saved')

    def test_restore_replaces_cache_and_survives_shutdown_flush(self):
        with zipfile.ZipFile(self.zip_path, 'w') as archive:
            archive.writestr('config.json', json.dumps({'language': 'de', 'restored': True}))
        self.config.update_config_value('pending', 'old')
        self.restore(config=True)
        self.config.flush_config()
        restored = json.loads(Path(self.config.CONFIG_FILE).read_text())
        self.assertEqual(restored, {'language': 'de', 'restored': True})
        self.assertEqual(self.events, ['restart'])

    def test_profile_round_trip_preserves_versioned_name(self):
        name = 'EliteMining v5.6.2-Profile.vap'
        profile = self.profile_dir / name
        profile.write_bytes(b'profile contents')
        self.backup(profile=True)
        profile.unlink()
        self.restore(profile=True)
        self.assertEqual(profile.read_bytes(), b'profile contents')
        self.assertEqual(self.events, [])

    def test_legacy_profile_restores(self):
        with zipfile.ZipFile(self.zip_path, 'w') as archive:
            archive.writestr('EliteMining-Profile.vap', b'legacy')
        self.restore(profile=True)
        self.assertEqual((self.profile_dir / 'EliteMining-Profile.vap').read_bytes(), b'legacy')

    def test_database_round_trip_includes_wal_commits(self):
        db = self.data / 'data/user_data.db'
        conn = sqlite3.connect(db)
        self.addCleanup(conn.close)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA wal_autocheckpoint=0')
        conn.execute('CREATE TABLE entries (value TEXT)')
        conn.execute("INSERT INTO entries VALUES ('in WAL')")
        conn.commit()
        self.assertGreater(Path(str(db) + '-wal').stat().st_size, 0)
        self.backup(database=True)
        conn.execute("UPDATE entries SET value='later'")
        conn.commit()
        self.restore(database=True)
        self.assertEqual(conn.execute('SELECT value FROM entries').fetchall(), [('in WAL',)])
        self.assertEqual(self.events, ['restart'])


if __name__ == '__main__':
    unittest.main()

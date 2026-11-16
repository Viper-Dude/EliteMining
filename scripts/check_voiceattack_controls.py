"""Check VoiceAttack settings without starting the app or writing user settings."""

import ast
import contextlib
import io
from pathlib import Path
import sys
import tkinter as tk
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / 'app/main.py').read_text(encoding='utf-8-sig'))
APP = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'App')
METHODS = {n.name: n for n in APP.body if isinstance(n, ast.FunctionDef)}
SELECTED = {
    '_on_voice_set_toggle', '_reset_sound_events', '_save_sound_events',
    '_clear_voice_set', '_apply_mapping', '_save_timer',
}


class VoiceAttackChecks(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            'sound_events': {'first': 'Set Male', 'second': 'tts', 'ship': ''},
            'tts_voice': 'Default Voice',
        }
        self.config_saves = []
        config = types.ModuleType('config')

        def update(values):
            self.config_saves.append(values.copy())
            self.cfg.update(values)

        config.update_config_value = lambda key, value: update({key: value})
        config.update_config_values = update
        self.modules = patch.dict(sys.modules, {'config': config})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.confirm = True
        self.dialog_parents = []

        def confirm(parent, *args):
            self.dialog_parents.append(parent)
            return self.confirm

        self.ns = {
            'Dict': dict, 'Any': object,
            'SOUND_EVENT_CATEGORIES': {'first': 'mining', 'second': 'mining', 'ship': 'ship'},
            'PRESET_EXCLUDED_TOGGLES': {'Voice Feedback'},
            '_load_cfg': lambda: self.cfg,
            'centered_yesno_dialog': confirm,
            't': lambda key: {
                'voiceattack.sound_event_off': 'Off',
                'voiceattack.sound_event_tts': 'TTS',
            }.get(key, key),
        }
        module = ast.Module(body=[ast.ClassDef(
            name='Harness', bases=[], keywords=[], decorator_list=[],
            body=[METHODS[name] for name in sorted(SELECTED)],
        )], type_ignores=[])
        ast.fix_missing_locations(module)
        exec(compile(module, str(ROOT / 'app/main.py'), 'exec'), self.ns)
        self.app = self.ns['Harness']()
        self.tcl = tk.Tcl()
        string = lambda value: tk.StringVar(master=self.tcl, value=value)
        self.app.sound_event_vars = {e: string('Set Female') for e in self.cfg['sound_events']}
        self.app.sound_event_tts_vars = {e: string('Custom Voice') for e in self.cfg['sound_events']}
        self.app._sound_event_packs = {e: ['Set Female', 'Set Male'] for e in self.cfg['sound_events']}
        self.app._voice_set_active = {}
        self.app._voice_set_vars = {
            ('mining', label): tk.BooleanVar(master=self.tcl, value=False)
            for label in ('Set Female', 'Set Male', 'TTS', 'Off')
        }
        self.path_writes = []
        self.app._write_sound_event_paths = lambda: self.path_writes.append({
            e: var.get() for e, var in self.app.sound_event_vars.items()
        })
        for var in (*self.app.sound_event_vars.values(), *self.app.sound_event_tts_vars.values()):
            var.trace_add('write', lambda *args: self.app._save_sound_events())

    def test_voice_set_saves_once_and_restores_custom_choices(self):
        original = self.cfg['sound_events'].copy()
        for label in ('Set Female', 'Set Male', 'TTS', 'Off'):
            with self.subTest(label=label):
                self.path_writes.clear()
                self.app._voice_set_vars[('mining', label)].set(True)
                self.app._on_voice_set_toggle('mining', label)
                self.assertEqual(len(self.path_writes), 1)
                self.assertEqual(self.app.sound_event_vars['first'].get(), label)
                self.assertEqual(self.cfg['sound_events']['first'], original['first'])
                self.app._voice_set_vars[('mining', label)].set(False)
                self.app._on_voice_set_toggle('mining', label)
                self.assertEqual(len(self.path_writes), 2)
                self.assertEqual(self.app.sound_event_vars['first'].get(), 'Set Male')
                self.assertEqual(self.app.sound_event_vars['second'].get(), 'TTS')

    def test_reset_all_uses_app_parent_and_saves_once(self):
        self.app._voice_set_active = {'mining': 'TTS', 'ship': 'Off'}
        self.app._reset_sound_events()
        self.assertEqual(self.dialog_parents, [self.app])
        self.assertEqual(len(self.path_writes), 1)
        self.assertEqual(self.app._voice_set_active, {})
        self.assertTrue(all(var.get() == 'Set Female' for var in self.app.sound_event_vars.values()))
        self.assertTrue(all(var.get() == 'Default Voice' for var in self.app.sound_event_tts_vars.values()))

    def test_reset_category_preserves_other_category(self):
        self.app.sound_event_vars['ship'].set('Off')
        self.path_writes.clear()
        self.app._voice_set_active = {'mining': 'TTS', 'ship': 'Off'}
        self.app._reset_sound_events('mining')
        self.assertEqual(len(self.path_writes), 1)
        self.assertEqual(self.app.sound_event_vars['ship'].get(), 'Off')
        self.assertEqual(self.app.sound_event_tts_vars['ship'].get(), 'Custom Voice')
        self.assertEqual(self.app._voice_set_active, {'ship': 'Off'})

    def test_cancel_reset_preserves_settings(self):
        self.confirm = False
        self.app._reset_sound_events()
        self.assertEqual(self.path_writes, [])
        self.assertEqual(self.config_saves, [])

    def test_single_event_saves_immediately_in_one_config_update(self):
        self.app.sound_event_vars['first'].set('TTS')
        self.assertEqual(self.cfg['sound_events']['first'], 'tts')
        self.assertEqual(len(self.path_writes), 1)
        self.assertEqual(len(self.config_saves), 1)
        self.app.sound_event_tts_vars['first'].set('Other Voice')
        self.assertEqual(self.cfg['sound_event_tts']['first'], 'Other Voice')

    def test_switch_to_custom_keeps_displayed_choices(self):
        self.app._voice_set_active = {'mining': 'Set Female'}
        self.app.sound_event_vars['first'].set('Off')
        self.app._clear_voice_set('mining')
        self.assertNotIn('mining', self.app._voice_set_active)
        self.assertEqual(self.cfg['sound_events']['first'], '')
        self.assertEqual(self.cfg['sound_events']['second'], 'Set Female')

    def test_preset_preserves_subsecond_closed_thrust(self):
        app = self.app
        app.tool_fg = {}; app.tool_btn = {}; app.toggle_vars = {}
        app.announcement_vars = {}; app.timer_vars = {}
        app.thrust_closed_var = tk.DoubleVar(master=self.tcl, value=1.6)
        app._save_thrust_closed = lambda: None
        app._save_all_to_txt = lambda: None
        app._set_status = lambda *args: None
        for saved, expected in ((0.0, 0.0), (0.4, 0.4), (1.6, 1.6), (-1, 0.0), (6, 5.0)):
            with self.subTest(saved=saved), contextlib.redirect_stdout(io.StringIO()):
                app._apply_mapping({'ThrustClosed': saved})
                self.assertEqual(app.thrust_closed_var.get(), expected)

    def test_open_thrust_wheel_stops_at_one_second(self):
        node = next(n for n in ast.walk(METHODS['_build_timers_tab'])
                    if isinstance(n, ast.FunctionDef) and n.name == 'on_thrust_open_scroll')
        self.app.thrust_open_var = tk.DoubleVar(master=self.tcl, value=1.0)
        saves = []
        self.app._save_thrust_open = lambda: saves.append(self.app.thrust_open_var.get())
        ns = dict(self.ns, self=self.app)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'wheel_check', 'exec'), ns)
        ns['on_thrust_open_scroll'](types.SimpleNamespace(delta=-120))
        self.assertEqual(saves, [1.0])


if __name__ == '__main__':
    unittest.main(verbosity=2)

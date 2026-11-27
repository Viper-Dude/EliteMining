"""Check VoiceAttack settings without starting the app or writing user settings."""

import ast
import contextlib
import io
from pathlib import Path
import sys
import tkinter as tk
import types
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from ui.stepper import Stepper
from va_keybind_applier import COMMAND_ELEMENT_ORDER


TREE = ast.parse((ROOT / 'app/main.py').read_text(encoding='utf-8-sig'))
APP = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'App')
METHODS = {n.name: n for n in APP.body if isinstance(n, ast.FunctionDef)}
VA_TAB_TREE = ast.parse((ROOT / 'app/voiceattack_controls_tab.py').read_text(encoding='utf-8-sig'))
VA_TAB_METHODS = {n.name: n for n in next(n for n in VA_TAB_TREE.body if isinstance(n, ast.ClassDef)).body
                  if isinstance(n, ast.FunctionDef)}
SELECTED = {
    '_on_voice_set_toggle', '_reset_sound_events', '_save_sound_events',
    '_clear_voice_set', '_apply_mapping', '_save_timer', '_execute_va_command', '_va_switch_tab',
    'switch_to_tab',
}


class VoiceAttackProfileChecks(unittest.TestCase):
    def test_plot_next_waypoint_element_order_and_condition_pairing(self):
        profiles = list((ROOT / 'Voiceattack Profile').glob('EliteMining v*-Profile.vap'))
        self.assertEqual(len(profiles), 1, profiles)
        profile = ET.parse(profiles[0])
        commands = [c for c in profile.iter('Command')
                    if (c.findtext('CommandString') or '').split(';')[0] == 'Plot next waypoint']
        self.assertEqual(len(commands), 1)
        command = commands[0]
        tags = [element.tag for element in command]
        self.assertEqual(tags, [tag for tag in COMMAND_ELEMENT_ORDER if tag in tags])

        actions = command.findall('ActionSequence/CommandAction')
        for flag in (actions[0], actions[-1]):
            self.assertEqual(flag.findtext('ActionType'), 'BooleanSet')
            self.assertEqual(flag.findtext('Context'), 'plotRoute')
        self.assertEqual([action.findtext('ActionType') for action in actions[1:9]], [
            'ConditionStart', 'TextSet', 'ConditionElse', 'TextSet', 'ConditionEnd',
            'ConditionStart', 'Say', 'ConditionElse',
        ])
        self.assertEqual(actions[1].findtext('ConditionStartNameFrom'), '~passedText1')
        self.assertEqual(actions[2].findtext('Context4'),
                         r'{VA_APPS}\EliteMining\Variables\routeNextSystem.txt')
        self.assertEqual(actions[4].findtext('Context4'), '{TXT:~passedText1}')
        self.assertEqual(actions[7].findtext('Context'), 'No route')
        self.assertEqual(command.findtext('UseProcessOverride'), 'true')
        self.assertEqual(command.findtext('ProcessOverride'), 'EliteDangerous64.exe')

        keys = [action for action in actions if action.findtext('ActionType') == 'PressKey']
        self.assertEqual([action.findtext('Context') for action in keys], [
            'EliteAPI.GalaxyMapOpen', 'EliteAPI.CamZoomIn', 'EliteAPI.UI_Up', 'EliteAPI.UI_Select',
            'EliteAPI.UI_Right', 'EliteAPI.UI_Select', 'EliteAPI.CamZoomOut', 'EliteAPI.UI_Select',
            'EliteAPI.GalaxyMapOpen',
        ])
        self.assertTrue(all(action.findtext('X') == '1' for action in keys))
        self.assertEqual(keys[-2].findtext('Duration'), '1')
        close_index = actions.index(keys[-1])
        plot_pause = actions[actions.index(keys[-2]) - 1]
        self.assertEqual(plot_pause.findtext('ActionType'), 'Pause')
        self.assertEqual(plot_pause.findtext('Duration'), '2')
        close_check = actions[close_index - 1]
        self.assertEqual(close_check.findtext('ActionType'), 'ConditionStart')
        self.assertEqual(close_check.findtext('ConditionStartNameFrom'), 'EliteAPI.GuiFocus')
        self.assertEqual(close_check.findtext('ConditionStartValue'), '6')
        self.assertEqual(close_check.findtext('ConditionStartOperator'), '0')
        self.assertEqual(int(close_check.findtext('ConditionPairing')), close_index + 1)

        groups = {}
        for index, action in enumerate(actions):
            group = int(action.findtext('ConditionGroup'))
            if group:
                groups.setdefault(group, []).append(index)
        self.assertEqual(len(groups), 5)
        for indices in groups.values():
            self.assertEqual(actions[indices[0]].findtext('ActionType'), 'ConditionStart')
            self.assertEqual(actions[indices[-1]].findtext('ActionType'), 'ConditionEnd')
            self.assertEqual([int(actions[index].findtext('ConditionPairing')) for index in indices],
                             indices[1:] + indices[:1])


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
            'log': types.SimpleNamespace(info=lambda *args: None,
                                         warning=lambda *args: None,
                                         error=lambda *args: self.fail(str(args))),
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

    def test_sidebar_commands_preserve_requested_state_when_repeated(self):
        toggles = []
        self.app._sidebar_visible = True

        def toggle():
            self.app._sidebar_visible = not self.app._sidebar_visible
            toggles.append(self.app._sidebar_visible)

        self.app._toggle_sidebar_visibility = toggle
        for command, expected in (
            ('SIDEBAR:SHOW', True), ('SIDEBAR:HIDE', False),
            ('SIDEBAR:HIDE', False), ('sidebar:show', True),
            ('SIDEBAR:SHOW', True), ('SIDEBAR', True), ('SIDEBAR:UNKNOWN', True),
        ):
            with self.subTest(command=command):
                self.app._execute_va_command(command)
                self.assertEqual(self.app._sidebar_visible, expected)
        self.assertEqual(toggles, [False, True])

    def test_mining_subtab_commands_select_parent_and_named_frame(self):
        selected = []
        self.app.switch_to_tab = lambda tab: selected.append(tab)
        self.app.prospector_panel = types.SimpleNamespace(
            nb=types.SimpleNamespace(select=lambda frame: selected.append(frame)),
            _reports_tab_frame='reports-frame', _statistics_tab_frame='statistics-frame',
            _missions_tab_frame='missions-frame')
        for name in ('REPORTS', 'STATISTICS', 'MISSIONS'):
            selected.clear()
            self.app._execute_va_command(f'TAB:{name}')
            self.assertEqual(selected, ['mining_session', f'{name.lower()}-frame'])

    def test_tab_commands_select_frames_by_name(self):
        selected = []
        self.app.notebook = types.SimpleNamespace(select=selected.append)
        self.app._set_status = lambda *args: None
        self.app._main_tabs = {'route': 'route-frame', 'system_finder': 'systems-frame',
                               'fleet_carrier': None}
        for command, frame in (('TAB:ROUTE', 'route-frame'), ('TAB:SYSTEMS', 'systems-frame')):
            selected.clear()
            self.app._execute_va_command(command)
            self.assertEqual(selected, [frame])
        selected.clear()
        self.app._execute_va_command('TAB:FLEETCARRIER')
        self.assertEqual(selected, [])

    def test_sidebar_swap_requires_visible_sidebar(self):
        swaps = []
        self.app._swap_sidebar_panes = lambda: swaps.append(True)
        for visible in (False, True):
            self.app._sidebar_visible = visible
            self.app._execute_va_command('SIDEBAR:SWAP')
            self.assertEqual(len(swaps), int(visible))

    def test_search_and_bookmark_open_existing_dialogs(self):
        calls = []
        self.app.switch_to_tab = lambda tab: calls.append(tab)
        self.app.ring_finder = types.SimpleNamespace(
            _bm_show_view=lambda: calls.append('search-view'))
        self.app.prospector_panel = types.SimpleNamespace(
            last_system='Sol', last_body='Sol A 1 A Ring',
            _show_bookmark_dialog=lambda data: calls.append(data))
        self.app._execute_va_command('SEARCH:BEST_MINING_SYSTEM')
        self.assertEqual(calls, ['hotspots_finder', 'search-view'])
        calls.clear()
        self.app._execute_va_command('BOOKMARK:ADD')
        self.assertEqual(calls, ['bookmarks', {'system': 'Sol', 'body': 'Sol A 1 A Ring'}])

    def test_app_profile_commands_write_matching_actions(self):
        profiles = list((ROOT / 'Voiceattack Profile').glob('EliteMining v*-Profile.vap'))
        self.assertEqual(len(profiles), 1, profiles)
        profile = ET.parse(profiles[0])
        phrases = {
            'SIDEBAR:HIDE': 'Hide sidebar', 'SIDEBAR:SHOW': 'Show sidebar',
            'SIDEBAR:SWAP': 'Swap sidebar panels', 'TAB:REPORTS': 'Show mining reports',
            'TAB:STATISTICS': 'Show mining statistics', 'TAB:MISSIONS': 'Show mining missions',
            'SEARCH:BEST_MINING_SYSTEM': 'Find best mining system',
            'BOOKMARK:ADD': 'Bookmark this location',
        }
        for action, phrase in phrases.items():
            commands = [command for command in profile.findall('.//Command')
                        if command.findtext('ActionSequence/CommandAction/Context') == action]
            self.assertEqual(len(commands), 1)
            command = commands[0]
            self.assertIn(phrase, [part.strip() for part in command.findtext('CommandString').split(';')])
            self.assertEqual(command.findtext('Category'), 'EliteMining App Commands')
            if action not in ('SIDEBAR:HIDE', 'SIDEBAR:SHOW'):
                self.assertEqual(command.findtext('keyValue'), '0')
            self.assertEqual(command.findtext('UseSpokenPhrase'), 'true')
            actions = command.findall('ActionSequence/CommandAction')
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0].findtext('ActionType'), 'WriteText')
            self.assertEqual(actions[0].findtext('X'), '1')
            self.assertEqual(actions[0].findtext('ConditionPairing'), '0')
            self.assertEqual(actions[0].findtext('Context2'),
                             r'{VA_APPS}\EliteMining\Variables\eliteMiningCommand.txt')

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
        app._ship_preset_done = lambda key: None
        for saved, expected in ((0.0, 0.0), (0.4, 0.4), (1.6, 1.6), (-1, 0.0), (6, 5.0)):
            with self.subTest(saved=saved), contextlib.redirect_stdout(io.StringIO()):
                app._apply_mapping({'ThrustClosed': saved})
                self.assertEqual(app.thrust_closed_var.get(), expected)

    def test_open_thrust_wheel_stops_at_one_second(self):
        call = next(n for n in ast.walk(VA_TAB_METHODS['_build_timers_tab'])
                    if isinstance(n, ast.Call) and getattr(n.func, 'attr', '') == '_make_stepper'
                    and ast.unparse(n.args[3]) == 'self.thrust_open_var')
        self.assertEqual(ast.literal_eval(call.args[1]), 1.0)
        keywords = {k.arg: ast.unparse(k.value) for k in call.keywords}
        self.assertEqual(keywords.get('command'), 'self._save_thrust_open')

        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        var = tk.DoubleVar(master=root, value=1.0)
        saves = []
        with patch('ui.stepper.load_theme', return_value='dark_gray'):
            stepper = Stepper(root, ast.literal_eval(call.args[1]), ast.literal_eval(call.args[2]), var,
                              increment=0.1, command=lambda: saves.append(var.get()))
        stepper._on_wheel(types.SimpleNamespace(delta=-120))
        self.assertEqual(saves, [1.0])


if __name__ == '__main__':
    unittest.main(verbosity=2)

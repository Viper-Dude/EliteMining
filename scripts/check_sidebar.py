"""Check sidebar behavior with isolated widgets and temporary preset files."""

import ast
import json
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'app/main.py').read_text(encoding='utf-8-sig')
TREE = ast.parse(SOURCE)
APP = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'App')
METHODS = {n.name: n for n in APP.body if isinstance(n, ast.FunctionDef)}
SELECTED = {
    '_apply_mapping', '_on_preset_double_click', '_ask_new_preset_name',
    '_ask_edit_preset_name', '_ask_import_preset_name', '_load_ship_preset',
    '_apply_modern_sidebar_sash', '_save_modern_sidebar_sash', '_sidebar_sash_position',
    '_create_integrated_cargo_monitor', '_update_integrated_cargo_display',
}


class SidebarChecks(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.strings = json.loads((ROOT / 'app/localization/strings_en.json').read_text(encoding='utf-8'))

        def translate(key):
            section, name = key.split('.', 1)
            return self.strings.get(section, {}).get(name, key)

        self.ns = {
            'tk': tk, 'ttk': ttk, 'Dict': dict, 'Any': object, 'Optional': __import__('typing').Optional,
            'PRESET_EXCLUDED_TOGGLES': {'Voice Feedback'}, 'SHIP_TYPES': ('Adder', 'Python Mk II'),
            't': translate, 'get_app_icon_path': lambda: None,
            'center_window': lambda *args: None, 'json': json,
            'ToolTip': lambda *args: types.SimpleNamespace(text=''),
            'log': types.SimpleNamespace(info=lambda *args: None, debug=lambda *args: None,
                                         exception=lambda *args: None),
        }
        module = ast.Module(body=[ast.ClassDef(name='Harness', bases=[], keywords=[], decorator_list=[],
                                              body=[METHODS[name] for name in sorted(SELECTED)])], type_ignores=[])
        ast.fix_missing_locations(module)
        exec(compile(module, str(ROOT / 'app/main.py'), 'exec'), self.ns)
        self.app = self.ns['Harness']()

    def mapping_setup(self):
        a = self.app
        a.tool_fg = {}; a.tool_btn = {}; a.timer_vars = {}; a.announcement_vars = {}
        a.toggle_vars = {key: tk.IntVar(self.root, value=value) for key, value in
                         [('Auto Deselect Prospector', 0), ('Other', 1), ('Voice Feedback', 1)]}
        a._save_all_to_txt = lambda: None
        a._set_status = lambda *args: None

    def test_legacy_toggle_aliases_and_current_key_precedence(self):
        self.mapping_setup()
        for values, expected in [({'Target': 1}, 1), ({'Auto Deselect Target': 1}, 1),
                                 ({'Target': 1, 'Auto Deselect Prospector': 0}, 0), ({}, 0)]:
            with self.subTest(values=values):
                data = {'Toggles': values.copy()}
                self.app._apply_mapping(data)
                self.assertEqual(self.app.toggle_vars['Auto Deselect Prospector'].get(), expected)
                self.assertEqual(self.app.toggle_vars['Other'].get(), 0)
                self.assertEqual(self.app.toggle_vars['Voice Feedback'].get(), 1)
                self.assertEqual(data['Toggles'], values)

    def test_group_double_click_toggles_once_and_loads_leaves(self):
        a = self.app
        a.preset_list = ttk.Treeview(self.root)
        group = a.preset_list.insert('', 'end', text='Ship', open=False)
        leaf = a.preset_list.insert(group, 'end', text='Build')
        saves = []; loads = []
        a._save_preset_expanded_state = lambda: saves.append(True)
        a._load_selected_preset = lambda: loads.append(True)
        with patch.object(a.preset_list, 'identify_row', return_value=group):
            for expected in (True, False):
                self.assertEqual(a._on_preset_double_click(types.SimpleNamespace(y=10)), 'break')
                self.assertEqual(bool(a.preset_list.item(group, 'open')), expected)
        with patch.object(a.preset_list, 'identify_row', return_value=leaf):
            self.assertEqual(a._on_preset_double_click(types.SimpleNamespace(y=10)), 'break')
        self.assertEqual(len(saves), 2)
        self.assertEqual(len(loads), 1)

    def test_load_uses_linked_announcement_before_snapshot_and_respects_cancel(self):
        a = self.app
        calls = []
        a._ship_is_preset_modified = lambda: False
        a._apply_mapping = lambda data: calls.append('ship')
        a._ann_load_preset = lambda slot: calls.append(('announcement', slot))
        a._ship_set_active_preset = lambda name: calls.append(('snapshot', name))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'preset.json'
            path.write_text(json.dumps({'AnnouncementPresetSlot': 3}))
            a._settings_path = lambda name: path
            a._load_ship_preset('Ship Build')
            self.assertEqual(calls, ['ship', ('announcement', 3), ('snapshot', 'Ship Build')])
            a._ship_is_preset_modified = lambda: True
            a._show_unsaved_ship_preset_dialog = lambda: 'cancel'
            calls.clear()
            a._load_ship_preset('Ship Build')
            self.assertEqual(calls, [])
        # Startup must take this same path rather than apply only the ship mapping.
        sidebar = ast.get_source_segment(SOURCE, METHODS['_create_main_sidebar'])
        self.assertIn('self._load_ship_preset(active_name)', sidebar)

    def test_modern_sash_saved_positions_restore_at_scales_and_orders(self):
        a = self.app
        config = types.ModuleType('config')
        saved = []
        config.save_modern_sidebar_sash_position = saved.append
        config.load_modern_sidebar_sash_position = lambda: saved[-1]
        a._sidebar_sash_initialized = True
        a._sidebar_default_cargo_on_top = True
        a._ui_scale_resize_ratio = 1.0
        a._cargo_pane = types.SimpleNamespace(winfo_reqheight=lambda: 200)
        for scale in (1, 1.5, 1.75):
            a._scaled_px = lambda value: round(value * scale)
            height = round(800 * scale)
            for reversed_order in (False, True):
                a._sidebar_cargo_on_top = not reversed_order
                for canonical in (a._scaled_px(80), height - a._scaled_px(150)):
                    position = [height - canonical if reversed_order else canonical]
                    def sashpos(index, value=None):
                        if value is not None: position[0] = value
                        return position[0]
                    a.sidebar_paned = types.SimpleNamespace(winfo_height=lambda: height,
                                                           sashpos=sashpos, update_idletasks=lambda: None)
                    with patch.dict('sys.modules', {'config': config}):
                        a._save_modern_sidebar_sash()
                        self.assertEqual(saved[-1], canonical)
                        self.assertTrue(a._apply_modern_sidebar_sash())
                        self.assertEqual(a._sidebar_sash_position(position[0]), canonical)
        # A position leaving only 120px for presets must not overwrite the saved valid height.
        position[0] = height - a._scaled_px(120)
        a._sidebar_cargo_on_top = True
        count = len(saved)
        with patch.dict('sys.modules', {'config': config}):
            a._save_modern_sidebar_sash()
        self.assertEqual(len(saved), count)

    def test_cargo_refresh_does_not_accumulate_callbacks(self):
        a = self.app
        a.current_theme = 'dark_gray'; a.ui_scale = 1
        a.theme_colors = {'bg': '#1e1e1e', 'fg': '#eeeeee', 'fg_muted': '#888888'}
        a._scaled_font = lambda size, *args: ('Arial', size, *args)
        a._scaled_px = lambda value: value
        a.after = lambda *args: None
        a._periodic_integrated_cargo_update = lambda: None
        clicks = []
        a.cargo_monitor = types.SimpleNamespace(current_cargo=2, max_cargo=200, cargo_items={'limpet': 2},
                                               materials_collected={}, adjust_limpet_count=lambda: clicks.append(True))
        a._create_integrated_cargo_monitor(ttk.Frame(self.root))
        commands = tuple(a.integrated_cargo_text._tclCommands)
        for amount in range(3, 15):
            a.cargo_monitor.current_cargo = amount
            a.cargo_monitor.cargo_items['limpet'] = amount
            a._update_integrated_cargo_display()
            self.assertEqual(tuple(a.integrated_cargo_text._tclCommands), commands)
            self.assertIn(f'{amount:>4}t', a.integrated_cargo_text.get('1.0', 'end'))
        binding = self.root.tk.call(str(a.integrated_cargo_text), 'tag', 'bind', 'limpet_clickable', '<Button-1>')
        command = binding.split('[', 1)[1].split()[0]
        self.root.tk.call(command, *(['0'] * 19))
        self.assertEqual(clicks, [True])

    def test_shared_dialog_modes_locales_scales_and_dropdown(self):
        root = self.root
        root.theme_colors = {'bg': '#1e1e1e', 'fg': '#eeeeee', 'bg_accent': '#2d2d2d', 'fg_muted': '#888888'}
        for name in ('_ask_edit_preset_name', '_ask_new_preset_name', '_ask_import_preset_name'):
            setattr(root, name, types.MethodType(getattr(type(self.app), name), root))
        errors = []
        root.report_callback_exception = lambda *args: errors.append(args)
        root.deiconify()

        def descendants(widget):
            return [child for w in widget.winfo_children() for child in [w, *descendants(w)]]

        for lang in ('en', 'de'):
            self.strings = json.loads((ROOT / f'app/localization/strings_{lang}.json').read_text(encoding='utf-8'))
            for theme in ('elite_orange', 'dark_gray', 'modern', 'modern_slate', 'modern_orange'):
                root.current_theme = theme
                for scale in (1, 1.75):
                    root._scaled_font = lambda size, *args: ('Arial', round(size * scale), *args)
                    root._scaled_px = lambda value: round(value * scale)
                    for mode in ('new', 'edit', 'import', 'cancel'):
                        with self.subTest(lang=lang, theme=theme, scale=scale, mode=mode):
                            def finish():
                                try:
                                    dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
                                    widgets = descendants(dialog)
                                    combo = next(w for w in widgets if isinstance(w, ttk.Combobox))
                                    entry = next(w for w in widgets if isinstance(w, tk.Entry) and not isinstance(w, ttk.Combobox))
                                    self.assertEqual(combo.get(), 'Python Mk II')
                                    if mode == 'new':
                                        self.assertEqual(entry.get(), '')
                                        entry.insert(0, 'Mining')
                                    if mode == 'cancel':
                                        label = self.strings['common']['cancel']
                                    else:
                                        label = self.strings['common']['import' if mode == 'import' else 'save']
                                    self.root.tk.call('ttk::combobox::Post', str(combo))

                                    def complete():
                                        try:
                                            popdown = root.tk.call('ttk::combobox::PopdownWindow', str(combo))
                                            self.assertTrue(root.tk.getboolean(root.tk.call('winfo', 'ismapped', popdown)))
                                            root.tk.call('ttk::combobox::Unpost', str(combo))
                                            next(w for w in widgets if isinstance(w, tk.Button) and w.cget('text') == label).invoke()
                                        except Exception:
                                            dialog.destroy()
                                            raise
                                    root.after(150, complete)
                                except Exception:
                                    for w in root.winfo_children():
                                        if isinstance(w, tk.Toplevel): w.destroy()
                                    raise

                            root.after(10, finish)
                            if mode == 'new':
                                result = root._ask_new_preset_name('Python Mk II')
                            elif mode == 'import':
                                result = root._ask_import_preset_name('Python Mk II', 'Mining', 'Old')
                            else:
                                result = root._ask_edit_preset_name('Python Mk II', 'Mining', 'Old')
                            self.assertEqual(result, None if mode == 'cancel' else 'Python Mk II Mining')
                            self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)

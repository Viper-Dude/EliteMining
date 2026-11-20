import ast
from copy import deepcopy
from contextlib import closing
import datetime as dt
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from check_ring_finder_search import load_methods

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import localization
from mining_statistics import session_date
from column_visibility_helper import ColumnVisibilityMixin, displayed_column
from user_database import UserDatabase
from journal_parser import JournalParser
from ui.striped_treeview import StripedTreeview

Panel = load_methods('app/prospector_panel.py', 'ProspectorPanel', {
    '_save_bookmarks', '_bookmark_location_key', '_find_bookmark', '_bookmark_ring_type',
    '_bookmark_yield', '_bookmark_material_key', '_bookmark_screenshot_folder', '_bookmark_screenshot_paths',
    '_cleanup_bookmark_screenshots', '_commit_bookmark', '_refresh_bookmarks',
    '_sort_bookmarks', '_bookmark_note_text', '_edit_bookmark_dialog', '_delete_bookmark',
    '_on_bookmark_search_changed', '_on_bookmark_filter_changed', '_sync_bookmark_last_mined',
    '_show_bookmark_dialog', '_on_bookmark_single_click', '_on_bookmark_double_click',
    '_add_bookmark_dialog', '_setup_bookmark_context_menu', '_show_bookmark_context_menu',
    '_copy_system_to_clipboard',
})
G = Panel._save_bookmarks.__globals__
G.update(os=os, json=json, tempfile=tempfile, re=re, dt=dt, tk=tk, ttk=ttk,
         log=logging.getLogger('bookmarks-check'), centered_message=Mock(),
         centered_askyesno=Mock(return_value=True), session_date=session_date, JournalParser=JournalParser,
         displayed_column=displayed_column, get_app_icon_path=lambda: None, StripedTreeview=StripedTreeview,
         t=localization.t, get_material=localization.get_material,
         get_abbr=localization.get_abbr, to_english=localization.to_english,
         scaled_font=lambda size, *style: ('Segoe UI', size, *style), scaled_px=lambda n: n)

# Load the UI builder with its Tk annotation, without importing or starting main.py.
source = ast.parse((ROOT / 'app/prospector_panel.py').read_text(encoding='utf-8-sig'))
original = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'ProspectorPanel')
builder = next(n for n in original.body if isinstance(n, ast.FunctionDef) and n.name == '_create_bookmarks_panel')
exec(compile(ast.Module(body=[builder], type_ignores=[]), '<bookmarks-ui>', 'exec'), G)
Panel._create_bookmarks_panel = G['_create_bookmarks_panel']

Database = load_methods('app/user_database.py', 'UserDatabase', {
    '_normalize_body_name', 'bulk_get_reserve_levels_for_rings',
})
Database.bulk_get_reserve_levels_for_rings.__globals__.update(sqlite3=sqlite3, log=logging.getLogger('bookmarks-db'))

COLUMNS = ('last_visited', 'last_mined', 'system', 'body', 'distance', 'sol_dist', 'hotspot',
           'reserve', 'density', 'materials', 'avg_yield', 'overlap', 'res_site', 'visits', 'rating', 'notes')


class Tree:
    def __init__(self):
        self.rows = {}
        self.order = []
        self.selected = ()
        self.widths = {col: 120 for col in COLUMNS}
        self.headers = {}
        self.tags = {}

    def get_children(self, *args):
        return tuple(self.order)

    def delete(self, item):
        del self.rows[item]
        self.order.remove(item)

    def heading(self, col, **kwargs):
        self.headers.update({col: kwargs['text']} if 'text' in kwargs else {})

    def column(self, col, option=None, **kwargs):
        if option == 'width':
            return self.widths[col]
        self.widths[col] = kwargs.get('width', self.widths[col])

    def insert(self, parent, where, iid, values, tags):
        self.rows[iid] = values
        self.tags[iid] = tags
        self.order.append(iid)

    def set(self, item, col):
        return self.rows[item][COLUMNS.index(col)]

    def move(self, item, parent, index):
        self.order.remove(item)
        self.order.insert(index, item)

    def item(self, item, option=None, **kwargs):
        if option == 'values':
            return self.rows[item]
        self.tags[item] = kwargs.get('tags', self.tags.get(item))

    def selection(self):
        return self.selected

    def selection_set(self, item):
        self.selected = (item,)


class UiPanel(ttk.Frame, Panel, ColumnVisibilityMixin):
    pass


class BookmarkChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.screenshots = self.folder / 'screenshots'
        self.screenshots.mkdir()
        self.addCleanup(patch.stopall)
        patch('path_utils.get_bookmark_screenshots_dir', return_value=str(self.screenshots)).start()
        self.font_patch = patch('tkinter.font.Font', return_value=SimpleNamespace(measure=lambda s: len(s) * 8))
        self.font_patch.start()
        localization.init('en')
        ring = ModuleType('ring_finder')
        ring.translate_reserve_level = lambda value: value
        ring.translate_ring_type = lambda value: localization.t('ring_finder.' + {
            'Metallic': 'metallic', 'Rocky': 'rocky', 'Icy': 'icy', 'Metal Rich': 'metal_rich',
        }[value]) if value else ''
        patch.dict(sys.modules, {'ring_finder': ring}).start()
        patch('ui.sort_indicator.apply_sort_arrow').start()
        patch('ui.dialogs.centered_yesno_dialog', return_value=True).start()
        G['centered_message'].reset_mock()
        G['centered_askyesno'].reset_mock(return_value=True)
        self.p = Panel()
        self.p.bookmarks_file = str(self.folder / 'bookmarks.json')
        self.p.bookmarks_data = []
        self.p.winfo_toplevel = Mock(return_value=None)
        self.p.bookmarks_tree = Tree()
        self.p._bookmark_sort_col = None
        self.p._bookmark_sort_dirs = {}
        self.p.bookmark_filter_var = Mock(get=lambda: self.filter)
        self.p.bookmark_mineral_var = Mock(get=lambda: self.mineral)
        self.p.bookmark_ring_type_var = Mock(get=lambda: self.ring_type)
        self.p.bookmark_search_var = Mock(get=lambda: self.search)
        self.filter, self.mineral, self.ring_type, self.search = 'all', 'All Minerals', 'Ring Type', ''
        self.p._bookmark_filter_display_to_key = {key: key for key in (
            'high_yield', 'medium_yield', 'low_yield', 'hotspot_locations')}
        self.db = Mock()
        for method in ('bulk_get_last_visit_dates', 'bulk_get_visit_counts',
                       'bulk_get_ring_density_for_rings', 'bulk_get_reserve_levels_for_rings'):
            getattr(self.db, method).return_value = {}
        self.db._normalize_body_name.side_effect = Database._normalize_body_name
        self.db._get_coordinates_from_visited_systems.return_value = None
        self.finder = Mock(systems_data={})
        self.finder._get_system_coords_from_galaxy_db.return_value = None
        self.p.main_app = SimpleNamespace(cargo_monitor=SimpleNamespace(user_db=self.db),
                                          ring_finder=self.finder, get_current_system=lambda: 'Sol')

    def bookmark(self, **fields):
        result = dict(system='Sol', body='A Ring', hotspot='Metallic', materials='Platinum',
                      avg_yield='1,649.0 T/hr', last_mined='2026-11-01', notes='kept', rating=4)
        result.update(fields)
        return result

    def refresh(self, **kwargs):
        self.p._refresh_bookmarks(**kwargs)
        return self.p.bookmarks_tree

    def test_missing_mineral_rate_stays_unknown_and_total_is_preserved(self):
        self.p.bookmarks_data = [self.bookmark()]
        self.mineral = 'Platinum'
        self.assertEqual(self.refresh().set('0', 'avg_yield'), '')
        self.mineral = 'All Minerals'
        self.assertEqual(self.refresh().set('0', 'avg_yield'), '1649.0 T/hr')

    def test_zero_rate_is_known(self):
        self.assertEqual(self.p._bookmark_yield(self.bookmark(mineral_tph={'Platinum': 0}), 'Platinum'), 0)

    def test_total_is_not_sum_of_minerals(self):
        b = self.bookmark(mineral_tph={'Platinum': 754.9, 'Painite': 80.4})
        self.assertEqual(self.p._bookmark_yield(b), 1649)

    def test_diamond_spelling_and_abbreviations_match_without_changing_rates(self):
        self.p.bookmarks_data = [self.bookmark(materials='Low-Temperature Diamonds',
                                              mineral_tph={'Low-Temperature Diamonds': 234.5})]
        self.mineral = 'Low Temperature Diamonds'
        self.assertEqual(self.refresh().set('0', 'avg_yield'), '234.5 T/hr')
        self.assertEqual(self.p._bookmark_material_key('LTD'), self.p._bookmark_material_key(self.mineral))

    def test_mineral_filter_matches_whole_material_names(self):
        self.p.bookmarks_data = [self.bookmark(materials='Not Platinum'), self.bookmark(materials='Plat')]
        self.mineral = 'Platinum'
        self.assertEqual(self.refresh().get_children(), ('1',))

    def test_yield_boundaries_match_labels(self):
        self.p.bookmarks_data = [self.bookmark(avg_yield=str(v)) for v in (99.9, 100, 499.9, 500, 999.9, 1000)]
        for choice, expected in [('low_yield', ('1', '2')), ('medium_yield', ('3', '4')), ('high_yield', ('5',))]:
            with self.subTest(choice=choice):
                self.filter = choice
                self.assertEqual(set(self.refresh().get_children()), set(expected))

    def test_yield_filter_uses_selected_mineral(self):
        self.p.bookmarks_data = [self.bookmark(mineral_tph={'Platinum': 20}), self.bookmark()]
        self.mineral, self.filter = 'Platinum', 'high_yield'
        self.assertFalse(self.refresh().get_children())

    def test_hotspot_filter_uses_minerals(self):
        self.p.bookmarks_data = [self.bookmark(materials=''), self.bookmark(hotspot='')]
        self.filter = 'hotspot_locations'
        self.assertEqual(self.refresh().get_children(), ('1',))

    def test_ring_types_work_in_both_languages_and_for_legacy_values(self):
        for lang in ('en', 'de'):
            localization.init(lang)
            self.mineral, self.ring_type = localization.t('bookmarks.all_minerals'), localization.t('ring_finder.metallic')
            self.p.bookmarks_data = [self.bookmark(hotspot='Metallic'), self.bookmark(hotspot='Metallisch'), self.bookmark(hotspot='Icy')]
            self.assertEqual(set(self.refresh().get_children()), {'0', '1'})

    def test_duplicate_rows_edit_and_tooltip_exact_record(self):
        self.p.bookmarks_data = [self.bookmark(notes='first'), self.bookmark(notes='second')]
        tree = self.refresh()
        tree.selected = ('1',)
        self.p._show_bookmark_dialog = Mock()
        self.p._edit_bookmark_dialog()
        self.p._show_bookmark_dialog.assert_called_once_with(self.p.bookmarks_data[1], 1)
        self.assertEqual(self.p._bookmark_note_text('1'), 'second')

    def test_location_normalization_preserves_distinct_parent_bodies(self):
        a = self.p._bookmark_location_key(' Sol ', 'Sol 2 A Ring')
        self.assertEqual(a, self.p._bookmark_location_key('sol', ' 2  A Ring '))
        self.assertNotEqual(a, self.p._bookmark_location_key('Sol', '2 a A Ring'))

    def test_new_duplicate_is_rejected(self):
        self.p.bookmarks_data = [self.bookmark()]
        self.assertFalse(self.p._commit_bookmark(self.bookmark(system='sol', body='sol A Ring'), None, []))
        self.assertEqual(len(self.p.bookmarks_data), 1)

    def test_existing_duplicate_can_be_edited_without_merging(self):
        self.p.bookmarks_data = [self.bookmark(notes='first'), self.bookmark(notes='second')]
        self.assertTrue(self.p._commit_bookmark(self.bookmark(notes='changed'), 1, []))
        self.assertEqual([b['notes'] for b in self.p.bookmarks_data], ['first', 'changed'])

    def test_rename_to_another_bookmark_is_rejected(self):
        self.p.bookmarks_data = [self.bookmark(), self.bookmark(body='B Ring')]
        self.assertFalse(self.p._commit_bookmark(self.bookmark(body='B Ring'), 0, []))

    def test_atomic_save_failure_preserves_file_and_memory(self):
        self.p.bookmarks_data = [self.bookmark()]
        self.assertTrue(self.p._save_bookmarks())
        before = Path(self.p.bookmarks_file).read_bytes()
        with patch('os.replace', side_effect=PermissionError('locked')), self.assertLogs('bookmarks-check', level='ERROR'):
            self.assertFalse(self.p._commit_bookmark(self.bookmark(notes='changed'), 0, []))
        self.assertEqual(Path(self.p.bookmarks_file).read_bytes(), before)
        self.assertEqual(self.p.bookmarks_data[0]['notes'], 'kept')
        G['centered_message'].assert_called_once()
        self.assertFalse(list(self.folder.glob('tmp*')))

    def screenshot(self, bookmark, filename='image.png', data=b'original'):
        folder = Path(self.p._bookmark_screenshot_folder(bookmark))
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / filename
        path.write_bytes(data)
        return path

    def test_delete_one_duplicate_keeps_other_screenshot(self):
        b = self.bookmark(screenshots=['image.png'])
        path = self.screenshot(b)
        self.p.bookmarks_data = [dict(b, notes='first'), dict(b, notes='second')]
        self.refresh().selected = ('1',)
        self.p._delete_bookmark()
        self.assertEqual([b['notes'] for b in self.p.bookmarks_data], ['first'])
        self.assertTrue(path.exists())

    def test_delete_last_reference_removes_screenshot(self):
        b = self.bookmark(screenshots=['image.png'])
        path = self.screenshot(b)
        self.p.bookmarks_data = [b]
        self.refresh().selected = ('0',)
        self.p._delete_bookmark()
        self.assertFalse(path.exists())

    def test_failed_delete_preserves_screenshot_and_record(self):
        b = self.bookmark(screenshots=['image.png'])
        path = self.screenshot(b)
        self.p.bookmarks_data = [b]
        self.refresh().selected = ('0',)
        with patch.object(self.p, '_save_bookmarks', return_value=False):
            self.p._delete_bookmark()
        self.assertTrue(path.exists())
        self.assertEqual(self.p.bookmarks_data, [b])

    def test_rename_keeps_legacy_screenshot_folder(self):
        b = self.bookmark(screenshots=['image.png'])
        path = self.screenshot(b)
        self.p.bookmarks_data = [b]
        entry = dict(filename='image.png', path=str(path), is_pending_add=False)
        self.assertTrue(self.p._commit_bookmark(dict(b, system='Other'), 0, [entry]))
        self.assertEqual(self.p._bookmark_screenshot_paths(self.p.bookmarks_data[0]), [str(path)])

    def test_new_bookmarks_have_independent_screenshot_folders(self):
        self.assertTrue(self.p._commit_bookmark(self.bookmark(), None, []))
        self.assertTrue(self.p._commit_bookmark(self.bookmark(body='B Ring'), None, []))
        self.assertNotEqual(*[b['screenshot_folder'] for b in self.p.bookmarks_data])

    def test_screenshot_copy_failure_rolls_back_new_files(self):
        source = self.folder / 'source.png'
        source.write_bytes(b'new')
        entries = [dict(filename='one.png', path=str(source), is_pending_add=True),
                   dict(filename='two.png', path=str(self.folder / 'missing.png'), is_pending_add=True)]
        with self.assertLogs('bookmarks-check', level='ERROR'):
            self.assertFalse(self.p._commit_bookmark(self.bookmark(), None, entries))
        self.assertFalse(self.p.bookmarks_data)
        self.assertFalse(list(self.screenshots.rglob('*.png')))
        self.assertEqual(source.read_bytes(), b'new')

    def test_save_failure_preserves_removed_screenshots_and_rolls_back_additions(self):
        b = self.bookmark(screenshots=['image.png'])
        old = self.screenshot(b)
        source = self.folder / 'new.png'
        source.write_bytes(b'new')
        self.p.bookmarks_data = [b]
        with patch.object(self.p, '_save_bookmarks', return_value=False):
            self.assertFalse(self.p._commit_bookmark(b, 0, [dict(filename='new.png', path=str(source), is_pending_add=True)]))
        self.assertTrue(old.exists())
        self.assertFalse((old.parent / 'new.png').exists())

    def test_existing_disk_filename_is_not_overwritten(self):
        b = self.bookmark(screenshots=[])
        old = self.screenshot(b)
        source = self.folder / 'source.png'
        source.write_bytes(b'new')
        self.p.bookmarks_data = [b]
        self.assertTrue(self.p._commit_bookmark(b, 0, [dict(filename='image.png', path=str(source), is_pending_add=True)]))
        self.assertEqual(old.read_bytes(), b'original')
        self.assertEqual(self.p.bookmarks_data[0]['screenshots'], ['image_1.png'])

    def test_missing_image_does_not_resolve_to_unrelated_folder(self):
        other = self.bookmark(system='Other', screenshots=['image.png'])
        self.screenshot(other)
        missing = self.p._bookmark_screenshot_paths(self.bookmark(screenshots=['image.png']))[0]
        self.assertFalse(Path(missing).exists())

    def test_search_reuses_derived_data_and_tab_refresh_reloads(self):
        self.p.bookmarks_data = [self.bookmark()]
        self.refresh()
        self.refresh(reuse_derived=True)
        self.db.bulk_get_reserve_levels_for_rings.assert_called_once()
        self.finder._get_system_coords_from_galaxy_db.assert_called_once()
        self.refresh()
        self.assertEqual(self.db.bulk_get_reserve_levels_for_rings.call_count, 2)

    def test_search_is_debounced(self):
        self.p.after = Mock(side_effect=['first', 'second'])
        self.p.after_cancel = Mock()
        self.p._on_bookmark_search_changed()
        self.p._on_bookmark_search_changed()
        self.p.after_cancel.assert_called_once_with('first')
        self.assertEqual(self.p._bookmark_search_after, 'second')

    def test_sort_refresh_keeps_direction_and_restripes(self):
        self.p.bookmarks_data = [self.bookmark(avg_yield=v) for v in ('10', '100', '')]
        tree = self.refresh()
        self.p._sort_bookmarks('avg_yield')
        self.assertEqual(tree.order, ['2', '0', '1'])
        self.refresh(reuse_derived=True)
        self.assertEqual(tree.order, ['2', '0', '1'])
        self.p._sort_bookmarks('avg_yield')
        self.assertEqual(tree.order, ['1', '0', '2'])
        self.assertEqual([tree.tags[i] for i in tree.order], [('evenrow',), ('oddrow',), ('evenrow',)])

    def test_last_mined_sync_keeps_memory_on_failed_save(self):
        self.p.bookmarks_data = [self.bookmark(last_mined='2026-01-01')]
        self.p.get_last_mined_lookup = Mock(return_value={('sol', 'sol A Ring'): ('', '2026-11-01T12:00:00Z')})
        with patch.object(self.p, '_save_bookmarks', return_value=False):
            self.p._sync_bookmark_last_mined()
        self.assertEqual(self.p.bookmarks_data[0]['last_mined'], '2026-01-01')

    def test_last_mined_sync_uses_normalized_location(self):
        self.p.bookmarks_data = [self.bookmark(last_mined='2026-01-01')]
        self.p.get_last_mined_lookup = Mock(return_value={('sol', 'sol A Ring'): ('', '2026-11-01T12:00:00Z')})
        self.p._sync_bookmark_last_mined()
        self.assertEqual(self.p.bookmarks_data[0]['last_mined'], '2026-11-01')

    def test_bulk_reserves_support_large_lists_and_ignore_empty_values(self):
        db = Database()
        db.db_path = str(self.folder / 'test.db')
        with closing(sqlite3.connect(db.db_path)) as conn:
            conn.execute('CREATE TABLE hotspot_data (system_name TEXT, body_name TEXT, reserve_level TEXT)')
            conn.executemany('INSERT INTO hotspot_data VALUES (?, ?, ?)',
                             [(f'S{i}', 'A Ring', 'Pristine') for i in range(1100)] + [('Empty', 'A Ring', '')])
            conn.commit()
        result = db.bulk_get_reserve_levels_for_rings([f'S{i}' for i in range(1100)] + ['Empty'])
        self.assertEqual(len(result), 1100)
        self.assertEqual(result[('S1099', 'A Ring')], 'Pristine')

    def ui_panel(self):
        self.font_patch.stop()
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        ui = UiPanel(root)
        for key, value in vars(self.p).items():
            if key != 'winfo_toplevel':
                setattr(ui, key, value)
        return root, ui

    def descendants(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self.descendants(child)

    def save_button(self, dialog):
        return next(w for w in self.descendants(dialog)
                    if isinstance(w, tk.Button) and w.cget('text') == localization.t('dialogs.save'))

    def test_report_update_preserves_notes_rating_screenshots_and_saved_fields(self):
        b = self.bookmark(screenshots=['image.png'], date_added='2020-01-01', extra='preserved')
        path = self.screenshot(b)
        self.p.bookmarks_data = [b]
        root, ui = self.ui_panel()
        with patch('tkinter.Toplevel.deiconify'):
            ui._show_bookmark_dialog(self.bookmark(avg_yield='2000', mineral_tph={'Platinum': 1200}, notes=''))
        dialog = next(w for w in self.descendants(root) if isinstance(w, tk.Toplevel))
        self.save_button(dialog).invoke()
        self.assertEqual(len(ui.bookmarks_data), 1)
        saved = ui.bookmarks_data[0]
        self.assertEqual((saved['notes'], saved['rating'], saved['date_added'], saved['extra']),
                         ('kept', 4, '2020-01-01', 'preserved'))
        self.assertEqual(saved['mineral_tph'], {'Platinum': 1200})
        self.assertEqual(ui._bookmark_screenshot_paths(saved), [str(path)])

    def test_failed_save_keeps_edit_dialog_open(self):
        self.p.bookmarks_data = [self.bookmark()]
        root, ui = self.ui_panel()
        with patch('tkinter.Toplevel.deiconify'):
            ui._show_bookmark_dialog(ui.bookmarks_data[0], 0)
        dialog = next(w for w in self.descendants(root) if isinstance(w, tk.Toplevel))
        with patch.object(ui, '_save_bookmarks', return_value=False):
            self.save_button(dialog).invoke()
        self.assertTrue(dialog.winfo_exists())

    def test_cancelled_duplicate_update_does_not_open_or_change_record(self):
        self.p.bookmarks_data = [self.bookmark()]
        before = deepcopy(self.p.bookmarks_data)
        G['centered_askyesno'].return_value = False
        with patch('tkinter.Toplevel') as constructor:
            self.p._show_bookmark_dialog(self.bookmark(avg_yield='2000'))
        constructor.assert_not_called()
        self.assertEqual(self.p.bookmarks_data, before)

    def test_real_table_preserves_widths_visibility_order_and_bindings(self):
        root, ui = self.ui_panel()
        ui.ToolTip = Mock()
        ui.get_last_mined_lookup = Mock(return_value={})
        ui._set_status = Mock()
        ui._deselect_on_empty_click = Mock()
        with patch('config.load_bookmarks_column_widths', return_value={'system': 320}), \
             patch('config.load_column_visibility', return_value={'notes': False}), \
             patch('config.load_column_order', return_value=['system', 'body']), \
             patch('config.save_column_visibility'), patch('config.save_column_order'):
            ui._create_bookmarks_panel(ui)
            tree = ui.bookmarks_tree
            root.update_idletasks()
            self.assertEqual(tree.column('system', 'width'), 320)
            self.assertNotIn('notes', tree['displaycolumns'])
            self.assertEqual(tree['displaycolumns'][:2], ('system', 'body'))
            self.assertEqual(displayed_column(tree, '#1'), 'system')
            tree.column('system', width=400)
            ui._refresh_bookmarks()
            self.assertEqual(tree.column('system', 'width'), 400)
            ui._cv_toggle('notes', 'bookmarks')
            self.assertIn('notes', tree['displaycolumns'])
            self.assertTrue(tree.cget('xscrollcommand'))
            self.assertTrue(tree.cget('yscrollcommand'))
            self.assertGreaterEqual(tree.bind('<Button-1>').count('\n'), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)

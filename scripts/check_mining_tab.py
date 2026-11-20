import contextlib
import csv
from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from localization import t
from mining_statistics import (SessionAnalytics, session_date, read_session_report,
                               _read_session_report)
from prospector_panel import ProspectorPanel
from mining_missions_tab import MiningMissionsTab
from ring_guide_tab import RingGuideTab
from mining_charts import MiningChartsPanel, MATPLOTLIB_AVAILABLE


def bind_methods(obj, *names):
    for name in names:
        setattr(obj, name, getattr(ProspectorPanel, name).__get__(obj))
    return obj


def row(stamp, body='A Ring'):
    return dict(timestamp_utc=stamp, system='Sol', body=body, elapsed='01:00:00',
                total_tons='100', overall_tph='100', asteroids_prospected='20',
                materials_tracked='1', hit_rate_percent='50', avg_quality_percent='30',
                materials_breakdown='Platinum: 100t', material_tph_breakdown='Platinum: 100',
                prospectors_used='20', engineering_materials='', comment='')


def write_index(folder, rows):
    with (Path(folder) / 'sessions_index.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class ReportChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        columns = ('date', 'duration', 'session_type', 'ship', 'system', 'body', 'ring_type',
                   'tons', 'tph', 'tons_per', 'asteroids', 'materials', 'total_hits',
                   'core_hits', 'hit_rate', 'quality', 'cargo', 'prospects', 'eng_materials',
                   'comment', 'enhanced')
        self.tree = ttk.Treeview(self.root, columns=columns, show='headings')
        self.owner = bind_methods(SimpleNamespace(
            reports_dir=self.folder.name, main_app=None, reports_tree_tab=self.tree,
            _enhanced_migration_done=True, _reports_limit=None,
            reports_tab_word_wrap_enabled=SimpleNamespace(get=lambda: False),
            _get_detailed_report_indicator=lambda report_id: '',
            _update_reports_summary=Mock(), _update_reports_paging=Mock()),
            '_get_csv_path', '_clear_reports_cache', '_get_ship_name_from_session',
            '_extract_session_type_from_data', '_enhance_materials_with_yields_and_tph',
            '_abbreviate_material_for_stats', '_ensure_comment_and_eng_cells',
            '_refresh_reports_tab')

    def refresh(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.owner._refresh_reports_tab()
        self.assertNotIn('Failed to refresh', output.getvalue())
        self.assertNotIn('Loading CSV failed', output.getvalue())

    def test_embedded_reports_panel_constructs(self):
        panel = ProspectorPanel.__new__(ProspectorPanel)
        ttk.Frame.__init__(panel, self.root)
        panel.main_app = None
        panel.reports_dir = self.folder.name
        panel.ToolTip = lambda *args: None
        panel._refresh_reports_tab = Mock()
        parent = ttk.Frame(panel)
        with patch('config._save_cfg'):
            panel._create_reports_panel(parent)
        self.assertIn('total_hits', panel.reports_tree_tab['columns'])
        self.assertIn('core_hits', panel.reports_tree_tab['columns'])
        panel._refresh_reports_tab.assert_called_once()

    def test_mining_tab_and_all_subtabs_construct(self):
        tracker = Mock()
        tracker.get_active_missions.return_value = []
        with patch('prospector_panel.get_reports_dir', return_value=self.folder.name), \
             patch('prospector_panel.get_variables_dir', return_value=self.folder.name), \
             patch('path_utils.get_bookmarks_file', return_value=str(Path(self.folder.name) / 'bookmarks.json')), \
             patch('prospector_panel._load_cfg', return_value={}), \
             patch.object(ProspectorPanel, '_detect_journal_dir_default', return_value=None), \
             patch('mining_missions.get_mission_tracker', return_value=tracker), \
             patch('config._save_cfg'), contextlib.redirect_stdout(io.StringIO()):
            panel = ProspectorPanel(self.root, self.folder.name, lambda message: None, {})
        self.assertEqual(len(panel.nb.tabs()), 6)
        self.assertIsNotNone(panel.missions_tab)
        self.assertIsNotNone(panel.ring_guide_tab)
        self.assertIsNotNone(panel.session_statistics_panel)
        self.assertTrue(panel.reports_tree_tab.winfo_exists())
        for callback in self.root.tk.call('after', 'info'):
            self.root.tk.call('after', 'cancel', callback)

    def test_utc_and_local_reports_obey_time_filters(self):
        now = datetime.now().astimezone()
        rows = [row('2000-01-01T12:00:00Z'),
                row(now.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')),
                row(now.replace(tzinfo=None).isoformat(), 'B Ring')]
        write_index(self.folder.name, rows)
        self.owner._time_filter_var = SimpleNamespace(get=lambda: 'week')
        self.owner._time_display_to_key = {'week': 'last_7_days'}
        self.refresh()
        self.assertEqual(len(self.tree.get_children()), 2)
        self.assertEqual(self.owner._update_reports_paging.call_args.args, (2, 2))

    def test_naive_session_dates_are_local_and_offsets_remain_correct(self):
        local = datetime(2026, 7, 4, 12, 30)
        self.assertEqual(session_date(local.isoformat()), local.astimezone(timezone.utc))
        self.assertEqual(session_date('2026-07-04T12:30:00+02:00'),
                         datetime(2026, 7, 4, 10, 30, tzinfo=timezone.utc))
        self.assertEqual(session_date('2026-07-04T10:30:00Z'),
                         datetime(2026, 7, 4, 10, 30, tzinfo=timezone.utc))
        self.assertIsNone(session_date('bad'))
        self.assertIsNone(session_date(None))

    def test_report_reads_reused_and_edits_invalidate_cache(self):
        # A changed body in the index must still use the report resolved by timestamp/system.
        write_index(self.folder.name, [row('2026-11-16T12:00:00', 'Edited Ring')])
        path = Path(self.folder.name) / 'Session_2026-11-16_12-00-00_Sol_A_Ring.txt'
        text = ('Session: Sol — A Ring — 01:00:00 — Total 100t (Multi-Session)\n'
                'Ship: My Cutter (ABC-123) - Cutter\nTotal Material Hits: 10\n'
                '--- Mineral Performance ---\nPlatinum:\n  • Hits: 10\n  • Core Hits: 2\n')
        path.write_text(text, encoding='utf-8')
        _read_session_report.cache_clear()
        self.refresh()
        item = self.tree.get_children()[0]
        self.assertEqual(self.tree.set(item, 'total_hits'), '10')
        self.assertEqual(self.tree.set(item, 'core_hits'), '2')
        self.assertEqual(self.tree.set(item, 'tons_per'), '10.0')
        self.assertEqual(self.tree.set(item, 'session_type'), 'Multi')
        self.assertIn('My Cutter', self.tree.set(item, 'ship'))
        self.assertEqual(_read_session_report.cache_info().misses, 1)
        self.refresh()
        self.assertEqual(_read_session_report.cache_info().misses, 1)
        path.write_text(text.replace('Hits: 10', 'Hits: 20'), encoding='utf-8')
        stamp = path.stat().st_mtime_ns + 1_000_000_000
        os.utime(path, ns=(stamp, stamp))
        self.refresh()
        self.assertEqual(self.tree.set(self.tree.get_children()[0], 'total_hits'), '20')
        self.assertEqual(_read_session_report.cache_info().misses, 2)
        path.unlink()
        self.assertEqual(read_session_report(path), '')

    def test_legacy_core_blocks_still_work(self):
        write_index(self.folder.name, [row('2026-11-16T12:00:00')])
        path = Path(self.folder.name) / 'Session_2026-11-16_12-00-00_Sol_A_Ring.txt'
        path.write_text('Session: Sol — A Ring — 01:00:00 — Total 100t\n'
                        'Total Material Finds: 5\nMonazite (Core):\n  • Hits: 3\n', encoding='utf-8')
        self.refresh()
        item = self.tree.get_children()[0]
        self.assertEqual(self.tree.set(item, 'total_hits'), '5')
        self.assertEqual(self.tree.set(item, 'core_hits'), '3')

    def test_stop_saves_without_rebuilding_and_refreshes_once(self):
        cargo = dict(materials_mined={'Platinum': 100}, total_tons_mined=100,
                     session_duration=3600, prospectors_used=0, engineering_materials={})
        monitor = SimpleNamespace(get_live_session_materials=lambda: {'Platinum': 100},
                                  end_session_tracking=lambda: cargo,
                                  user_db=SimpleNamespace(get_ring_type=lambda system, body: None))
        obj = bind_methods(SimpleNamespace(
            reports_dir=self.folder.name, session_active=True, session_paused=False,
            session_start=datetime.now(), main_app=SimpleNamespace(cargo_monitor=monitor),
            _active_seconds=lambda: 3600, session_analytics=SessionAnalytics(),
            _set_status=Mock(), start_btn=Mock(), stop_btn=Mock(), cancel_btn=Mock(),
            pause_resume_btn=Mock(), session_system=SimpleNamespace(get=lambda: 'Sol'),
            session_body=SimpleNamespace(get=lambda: 'A Ring'), session_mining_body='',
            session_mining_system='',
            session_elapsed=SimpleNamespace(get=lambda: '01:00:00'),
            multi_session_var=SimpleNamespace(get=lambda: False),
            session_ship_name='Cutter', _write_var_text=Mock(), charts_panel=None,
            _refresh_reports_tab=Mock(), _refresh_session_statistics=Mock(),
            _set_pending_ring_finder_switch=Mock(),
            _rebuild_csv_from_files_tab=Mock(side_effect=AssertionError('Unexpected rebuild'))),
            '_session_stop', '_save_session_report_with_timestamp', '_update_csv_with_session')
        with contextlib.redirect_stdout(io.StringIO()):
            obj._session_stop(silent=True)
        files = list(Path(self.folder.name).glob('Session_*.txt'))
        self.assertEqual(len(files), 1)
        with (Path(self.folder.name) / 'sessions_index.csv').open(encoding='utf-8') as stream:
            records = list(csv.DictReader(stream))
        self.assertEqual(len(records), 1)
        self.assertEqual(float(records[0]['total_tons']), 100)
        self.assertIn('Platinum', records[0]['materials_breakdown'])
        obj._refresh_reports_tab.assert_called_once()
        obj._refresh_session_statistics.assert_called_once()
        obj._rebuild_csv_from_files_tab.assert_not_called()
        self.assertFalse(obj.session_active)

    def test_incremental_index_preserves_history_and_prospector_metrics(self):
        write_index(self.folder.name, [row('2026-11-15T12:00:00')])
        analytics = Mock()
        analytics.get_live_summary.return_value = {
            'Platinum': {'find_count': 2, 'avg_percentage': 30.0}}
        analytics.get_session_info.return_value = {
            'asteroids_prospected': 4, 'asteroids_with_materials': 2}
        obj = bind_methods(SimpleNamespace(
            reports_dir=self.folder.name, session_analytics=analytics,
            _calculate_yield_from_prospector_reports=lambda: {'Platinum': 30.0},
            _calculate_total_average_yield=lambda: 15.0),
            '_update_csv_with_session', '_format_yield_display')
        cargo = dict(materials_mined={'Platinum': 100}, session_duration=3600,
                     prospectors_used=4, engineering_materials={'Iron': 2})
        with contextlib.redirect_stdout(io.StringIO()):
            obj._update_csv_with_session('Sol', 'A Ring', '01:00:00', 100, 100,
                                         cargo, 'Keep this comment', '2026-11-16_12-00-00')
        with (Path(self.folder.name) / 'sessions_index.csv').open(encoding='utf-8') as stream:
            records = list(csv.DictReader(stream))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]['timestamp_utc'], '2026-11-15T12:00:00')
        self.assertEqual(records[1]['hit_rate_percent'], '50.0')
        self.assertEqual(records[1]['material_tph_breakdown'], 'Platinum: 100.0')
        self.assertEqual(records[1]['engineering_materials'], 'Iron:2')
        self.assertEqual(records[1]['comment'], 'Keep this comment')


class PanelChecks(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('1000x700+-3000+-3000')
        self.addCleanup(self.close_root)
        self.tracker = Mock()
        self.tracker.get_active_missions.return_value = [dict(
            mission_id=1, commodity='Platinum', count=100, delivered=0,
            expiry=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())]
        patcher = patch('mining_missions.get_mission_tracker', return_value=self.tracker)
        patcher.start()
        self.addCleanup(patcher.stop)

    def close_root(self):
        for callback in self.root.tk.call('after', 'info'):
            self.root.tk.call('after', 'cancel', callback)
        self.root.destroy()
        for callback in self.root.tk.call('after', 'info'):
            self.root.tk.call('after', 'cancel', callback)

    def test_mission_countdown_updates_in_place_and_timer_is_cancelled(self):
        panel = MiningMissionsTab(self.root)
        panel.pack(fill='both', expand=True)
        self.root.update()
        card = panel._mission_cards[1]
        label = card['time_label']
        card['expiry'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        panel.after_cancel(panel._countdown_after_id)
        panel._tick_countdowns()
        self.assertIs(card['time_label'], label)
        self.assertEqual(label.cget('text'), t('mining_missions.expired'))
        self.assertEqual(label.cget('fg'), '#ff6666')
        timer = panel._countdown_after_id
        panel.destroy()
        self.assertNotIn(timer, self.root.tk.call('after', 'info'))
        self.tracker.remove_callback.assert_called_once()

    def test_scrolling_stays_in_panel_and_preserves_global_bindings(self):
        global_wheel = Mock()
        self.root.bind_all('<MouseWheel>', global_wheel)
        saved = self.root.bind_all('<MouseWheel>')
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True)
        missions = MiningMissionsTab(notebook)
        with patch.object(RingGuideTab, '_load_expanded_state', return_value={
                **dict.fromkeys(RingGuideTab.RING_DATA, True), 'RES Sites': True}):
            reference = RingGuideTab(notebook)
        other = ttk.Frame(notebook)
        notebook.add(missions, text='Missions')
        notebook.add(reference, text='Reference')
        notebook.add(other, text='Other')
        label = ttk.Label(other, text='Other')
        label.pack()
        notebook.select(missions)
        self.root.update()
        with patch.object(missions.canvas, 'yview_scroll') as scroll:
            missions._mission_cards[1]['commodity_label'].event_generate('<MouseWheel>', delta=-120)
            self.root.update()
            scroll.assert_called_once_with(1, 'units')
        global_wheel.assert_not_called()
        notebook.select(reference)
        self.root.update()
        with patch.object(reference.canvas, 'yview_scroll') as scroll:
            reference._expand_labels['Icy'].event_generate('<MouseWheel>', delta=-120)
            self.root.update()
            scroll.assert_called_once_with(1, 'units')
        notebook.select(other)
        self.root.update()
        label.event_generate('<MouseWheel>', delta=-120)
        self.root.update()
        global_wheel.assert_called_once()
        reference.destroy()
        missions.destroy()
        self.assertEqual(self.root.bind_all('<MouseWheel>'), saved)

    @unittest.skipUnless(MATPLOTLIB_AVAILABLE, 'Matplotlib unavailable')
    def test_hidden_charts_defer_refresh_and_visible_updates_coalesce(self):
        frame = ttk.Frame(self.root)
        panel = MiningChartsPanel(frame, SessionAnalytics())
        panel.pack(fill='both', expand=True)
        with patch.object(panel, 'refresh_charts') as refresh:
            panel.update_charts()
            self.assertIsNone(panel._chart_refresh_id)
            refresh.assert_not_called()
            frame.pack(fill='both', expand=True)
            self.root.update()
            timer = panel._chart_refresh_id
            self.assertIsNotNone(timer)
            panel.update_charts()
            panel.update_charts()
            self.assertEqual(panel._chart_refresh_id, timer)
            panel.frame.after_cancel(timer)
            panel._refresh_visible_charts()
            refresh.assert_called_once()

    @unittest.skipUnless(MATPLOTLIB_AVAILABLE, 'Matplotlib unavailable')
    def test_autosave_refreshes_hidden_dirty_charts(self):
        panel = MiningChartsPanel(ttk.Frame(self.root), SessionAnalytics())
        panel._charts_dirty = True
        with patch.object(panel, 'refresh_charts') as refresh:
            self.assertFalse(panel.auto_save_graphs())
            refresh.assert_called_once()


if __name__ == '__main__':
    unittest.main()

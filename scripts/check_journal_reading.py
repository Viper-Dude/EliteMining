"""Check live journal cursors and catch-up checkpoints using temporary files."""

import ast
import contextlib
import glob
import io
import itertools
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from typing import Optional
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from journal_reader import journal_resume_offset, read_complete_journal_lines


def load_methods(filename, class_name, names):
    tree = ast.parse((ROOT / filename).read_text(encoding='utf-8-sig'))
    original = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    module = ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(
        name=class_name, bases=[], keywords=[], decorator_list=[],
        body=[n for n in original.body if isinstance(n, ast.FunctionDef) and n.name in names],
    )], type_ignores=[]))
    namespace = dict(os=os, glob=glob, json=json, time=time, threading=threading, Optional=Optional, MISSIONS_AVAILABLE=False,
                     logging=logging, log=logging.getLogger('journal-check'),
                     t=lambda key: key,
                     journal_resume_offset=journal_resume_offset,
                     read_complete_journal_lines=read_complete_journal_lines)
    exec(compile(module, filename, 'exec'), namespace)
    return namespace[class_name]


Monitor = load_methods('app/main.py', 'CargoMonitor', {
    'start_journal_monitoring', 'find_latest_journal', '_poll_journal',
    'read_new_journal_entries', '_read_new_journal_entries',
    'add_journal_listener', '_dispatch_journal_events', '_deliver_journal_events',
    '_start_background_monitoring',
})
Panel = load_methods('app/prospector_panel.py', 'ProspectorPanel', {'_attach_journal', '_handle_journal_events'})
App = load_methods('app/main.py', 'App', {
    '_process_journals_for_catchup', '_get_new_journals_since_checkpoint',
})


def record(number, **fields):
    return (json.dumps(dict(event='JournalHealthCheck', number=number) | fields,
                       ensure_ascii=False) + '\r\n').encode('utf-8')


class ReaderCases:
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)
        self.path = Path(self.folder.name) / 'Journal.2026-11-17T100000.01.log'
        self.events = []
        # Each clock read moves past the 5-second folder-listing throttle
        clock = itertools.count(1000, 10)
        clock_patch = patch.object(time, 'time', side_effect=lambda: next(clock))
        clock_patch.start()
        self.addCleanup(clock_patch.stop)
        self.make_reader()

    def append(self, data, path=None):
        with (path or self.path).open('ab') as stream:
            stream.write(data)

    def capture(self, line):
        try:
            event = json.loads(line)
        except ValueError:
            return None
        self.events.append(event)
        return event

    def capture_batch(self, events):
        self.events.extend(events)

    def numbers(self):
        return [event['number'] for event in self.events]

    def test_startup_skips_history_but_reads_new_events_once(self):
        self.path.write_bytes(record(0))
        self.start()
        self.assertEqual(self.events, [])
        self.append(record(1))
        self.poll(); self.poll()
        self.assertEqual(self.numbers(), [1])

    def test_partial_record_is_retained_until_completed(self):
        self.path.write_bytes(record(0))
        self.start()
        data = record(1, name='Jørgen')
        cut = data.index('ø'.encode('utf-8')) + 1
        self.append(data[:cut])
        self.poll(); self.poll()
        self.assertEqual(self.events, [])
        self.append(data[cut:] + record(2))
        self.poll(); self.poll()
        self.assertEqual(self.numbers(), [1, 2])
        self.assertEqual(self.events[0]['name'], 'Jørgen')

    def test_startup_during_partial_write_preserves_record(self):
        data = record(1)
        self.path.write_bytes(record(0) + data[:15])
        self.start()
        self.append(data[15:])
        self.poll(); self.poll()
        self.assertEqual(self.numbers(), [1])

    def test_locked_file_at_startup_does_not_replay_history_after_retry(self):
        self.path.write_bytes(record(0))
        namespace = self.start.__func__.__globals__
        with patch.dict(namespace, journal_resume_offset=Mock(side_effect=PermissionError('locked'))):
            self.start()
        self.poll(); self.poll()
        self.assertEqual(self.events, [])
        self.append(record(1))
        self.poll(); self.poll()
        self.assertEqual(self.numbers(), [1])

    def test_folder_is_not_relisted_within_five_seconds(self):
        self.path.write_bytes(record(0))
        self.start()
        self.poll()
        new = self.path.with_name('Journal.2026-11-17T110000.01.log')
        new.write_bytes(record(1))
        with patch.object(time, 'time', return_value=0.0):
            self.poll(); self.poll()
        self.assertEqual(self.events, [])
        with patch.object(time, 'time', return_value=1e9):
            self.poll(); self.poll()
        self.assertEqual(self.numbers(), [1])

    def test_first_file_created_after_startup_is_read(self):
        self.start()
        self.path.write_bytes(record(1))
        self.poll(); self.poll()
        self.assertEqual(self.numbers(), [1])

    def test_rotation_drains_old_tail_and_new_files_in_order(self):
        self.path.write_bytes(record(0))
        self.start()
        self.append(record(1))
        new = self.path.with_name('Journal.2026-11-17T110000.01.log')
        new.write_bytes(record(2, event='LaunchDrone', Type='Prospector'))
        newer = self.path.with_name('Journal.2026-11-17T120000.01.log')
        newer.write_bytes(record(3))
        self.poll(); self.poll()
        self.assertEqual(self.numbers(), [1, 2, 3])
        self.assertEqual(self.events[1]['event'], 'LaunchDrone')

    def test_deleted_old_file_does_not_skip_new_file(self):
        self.path.write_bytes(record(0))
        self.start()
        self.path.unlink()
        new = self.path.with_name('Journal.2026-11-17T110000.01.log')
        new.write_bytes(record(1))
        self.poll(); self.poll()
        self.assertEqual(self.numbers(), [1])

    def test_locked_file_retries_without_losing_or_replaying_events(self):
        self.path.write_bytes(record(0))
        self.start()
        self.append(record(1))
        namespace = self.poll.__func__.__globals__
        with patch.dict(namespace, read_complete_journal_lines=Mock(side_effect=PermissionError('locked'))), \
                patch.object(time, 'sleep'):
            self.poll()
        self.assertEqual(self.events, [])
        self.poll(); self.poll()
        self.assertEqual(self.numbers(), [1])

    def test_locked_old_file_delays_rotation_until_retry(self):
        self.path.write_bytes(record(0))
        self.start()
        self.append(record(1))
        new = self.path.with_name('Journal.2026-11-17T110000.01.log')
        new.write_bytes(record(2))
        namespace = self.poll.__func__.__globals__
        def locked(path, offset):
            if str(path) == str(self.path):
                raise PermissionError('locked')
            return read_complete_journal_lines(path, offset)
        with patch.dict(namespace, read_complete_journal_lines=locked), patch.object(time, 'sleep'):
            self.poll()
        self.assertEqual(self.events, [])
        self.poll(); self.poll()
        self.assertEqual(self.numbers(), [1, 2])

    def test_truncated_file_restarts_at_beginning(self):
        self.path.write_bytes(record(0, padding='x' * 1000))
        self.start()
        self.path.write_bytes(record(1))
        self.poll(); self.poll()
        self.assertEqual(self.numbers(), [1])

    def test_invalid_complete_line_does_not_block_following_event(self):
        self.path.write_bytes(record(0))
        self.start()
        self.append(b'{"event": invalid}\r\n' + record(1))
        self.poll(); self.poll()
        self.assertEqual(self.numbers(), [1])


class CargoReaderChecks(ReaderCases, unittest.TestCase):
    def make_reader(self):
        self.reader = Monitor()
        self.reader.journal_dir = self.folder.name
        self.reader.last_journal_file = None
        self.reader.last_file_size = 0
        self.reader._lock = threading.RLock()
        self.reader.scan_journal_for_cargo_capacity = Mock()
        self.reader._dispatch_journal_events = self.capture_batch
        self.start = self.reader.start_journal_monitoring
        self.poll = self.reader._poll_journal

    def test_concurrent_reads_do_not_duplicate_events_or_dispatch_under_lock(self):
        self.path.write_bytes(record(0))
        self.start()
        self.append(record(1))
        entered, release = threading.Event(), threading.Event()
        namespace = self.reader.read_new_journal_entries.__func__.__globals__
        def delayed_read(path, offset):
            entered.set()
            self.assertTrue(release.wait(3))
            return read_complete_journal_lines(path, offset)
        errors = []
        def dispatch(events):
            if self.reader._lock._is_owned():
                errors.append('dispatch owns cursor lock')
            self.capture_batch(events)
        self.reader._dispatch_journal_events = dispatch
        with patch.dict(namespace, read_complete_journal_lines=delayed_read):
            first = threading.Thread(target=self.reader.read_new_journal_entries)
            second = threading.Thread(target=self.reader.read_new_journal_entries)
            first.start()
            try:
                self.assertTrue(entered.wait(3))
                second.start()
            finally:
                release.set()
                first.join(3)
                if second.ident is not None:
                    second.join(3)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(self.numbers(), [1])
        self.assertEqual(errors, [])

    def test_bytes_added_during_read_are_not_replayed_on_next_poll(self):
        self.path.write_bytes(record(0))
        self.start()
        self.append(record(1))
        namespace = self.reader.read_new_journal_entries.__func__.__globals__
        def growing_read(path, offset):
            self.append(record(2))
            return read_complete_journal_lines(path, offset)
        with patch.dict(namespace, read_complete_journal_lines=growing_read):
            self.poll()
        self.poll()
        self.assertEqual(self.numbers(), [1, 2])

    def test_journal_folder_change_reattaches_without_replaying_old_events(self):
        self.path.write_bytes(record(0))
        self.start()
        other = Path(self.folder.name) / 'another-folder'
        other.mkdir()
        new = other / self.path.name
        new.write_bytes(record(10))
        self.reader.journal_dir = str(other)
        self.poll(); self.poll()
        self.assertEqual(self.events, [])
        self.append(record(11), path=new)
        self.poll(); self.poll()
        self.assertEqual(self.numbers(), [11])

    def test_dispatch_cannot_recursively_replay_or_reorder_the_batch(self):
        self.path.write_bytes(record(0))
        self.start()
        self.append(record(1) + record(2))
        def dispatch(events):
            self.capture_batch(events)
            if any(event['number'] == 1 for event in events):
                self.append(record(3))
                self.assertFalse(self.reader.read_new_journal_entries())
        self.reader._dispatch_journal_events = dispatch
        self.poll(); self.poll()
        self.assertEqual(self.numbers(), [1, 2, 3])


class SharedReaderChecks(ReaderCases, unittest.TestCase):
    """One reader feeds the cargo monitor and then each listener, such as the prospector panel."""

    def make_reader(self):
        self.reader = Monitor()
        self.reader.journal_dir = self.folder.name
        self.reader.last_journal_file = None
        self.reader.last_file_size = 0
        self.reader._lock = threading.RLock()
        self.reader._journal_listeners = []
        self.reader.scan_journal_for_cargo_capacity = Mock()
        self.reader._process_journal_event_impl = Mock()
        self.panel = Panel()
        self.panel.journal_dir = self.folder.name
        self.panel._journal_attached = False
        self.panel.auto_start_on_prospector = True
        self.panel.session_active = False
        self.panel.after = Mock()
        self.panel._session_start = Mock()
        self.panel._auto_switch_to_mining_tab = Mock()
        self.panel._read_initial_location_from_journal = Mock()
        self.panel.last_system = self.panel.last_body = None
        def to_panel(events):
            self.capture_batch(events)
            self.panel._handle_journal_events(events)
        self.reader.add_journal_listener(to_panel)
        self.poll = self.reader._poll_journal

    def start(self):
        self.reader.start_journal_monitoring()
        self.panel._attach_journal()

    def test_cargo_sees_the_same_events_before_listeners(self):
        self.path.write_bytes(record(0))
        self.start()
        order = []
        self.reader._process_journal_event_impl.side_effect = lambda event: order.append(('cargo', event['number']))
        self.reader.add_journal_listener(lambda events: order.extend(('listener', e['number']) for e in events))
        self.append(record(1) + record(2))
        self.poll()
        self.assertEqual(order, [('cargo', 1), ('cargo', 2), ('listener', 1), ('listener', 2)])

    def test_first_prospector_launch_in_new_file_still_auto_starts(self):
        self.path.write_bytes(record(0))
        self.start()
        new = self.path.with_name('Journal.2026-11-17T110000.01.log')
        new.write_bytes(record(1, event='LaunchDrone', Type='Prospector'))
        self.poll(); self.poll()
        self.panel.after.assert_called_once_with(100, self.panel._session_start)
        self.panel._auto_switch_to_mining_tab.assert_called_once_with()

    def test_panel_ignores_events_until_attached(self):
        self.panel._handle_journal_events([dict(event='LaunchDrone', Type='Prospector')])
        self.panel.after.assert_not_called()
        self.panel._attach_journal()
        self.panel._attach_journal()
        self.panel._read_initial_location_from_journal.assert_called_once_with()

    def test_failing_listener_does_not_block_cargo_or_other_listeners(self):
        reader = Monitor()
        reader._journal_listeners = []
        reader._process_journal_event_impl = Mock(side_effect=[RuntimeError('cargo'), None])
        received = []
        reader.add_journal_listener(Mock(side_effect=RuntimeError('listener')))
        reader.add_journal_listener(received.extend)
        events = [dict(event='A'), dict(event='B')]
        with self.assertLogs('journal-check', level='ERROR'):
            reader._deliver_journal_events(events)
        self.assertEqual(reader._process_journal_event_impl.call_count, 2)
        self.assertEqual(received, events)

    def test_listener_is_added_once(self):
        reader = Monitor()
        reader._journal_listeners = []
        reader.add_journal_listener(self.panel._handle_journal_events)
        reader.add_journal_listener(self.panel._handle_journal_events)
        self.assertEqual(len(reader._journal_listeners), 1)

    def test_background_batch_is_one_main_thread_callback(self):
        reader = Monitor()
        reader.main_app_ref = Mock()
        reader._deliver_journal_events = Mock()
        events = [dict(event='A'), dict(event='B')]
        worker = threading.Thread(target=reader._dispatch_journal_events, args=(events,))
        worker.start(); worker.join(3)
        reader.main_app_ref.after.assert_called_once_with(0, reader._deliver_journal_events, events)
        reader._deliver_journal_events.assert_not_called()


class BackgroundMonitorChecks(unittest.TestCase):
    def test_paused_monitoring_does_not_end_the_monitor_thread(self):
        monitor = Monitor()
        monitor._stop_event = threading.Event()
        monitor._lock = threading.RLock()
        monitor.materials_collected = {}
        monitor.journal_monitor_active = False
        monitor._check_status_for_ship_changes = Mock()
        monitor._validate_cargo_capacity = Mock(return_value=True)
        monitor.read_cargo_json = Mock()
        polled = threading.Event()
        def poll():
            polled.set()
            monitor._stop_event.set()
        monitor._poll_journal = Mock(side_effect=poll)
        real_sleep = time.sleep
        paused_ticks = []
        def fast_sleep(seconds):
            if not monitor.journal_monitor_active:
                paused_ticks.append(seconds)
                if len(paused_ticks) >= 3:
                    monitor.journal_monitor_active = True
            real_sleep(0.001)
        self.addCleanup(monitor._stop_event.set)
        with patch.object(time, 'sleep', fast_sleep):
            monitor._start_background_monitoring()
            self.assertTrue(polled.wait(3))
        self.assertGreaterEqual(len(paused_ticks), 3)
        monitor._check_status_for_ship_changes.assert_called()


class CatchupCheckpointChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)
        self.path = Path(self.folder.name) / 'Journal.2026-11-17T100000.01.log'
        self.app = App()
        self.parser = Mock(carrier_data={})
        self.app.cargo_monitor = SimpleNamespace(journal_parser=self.parser)
        self.app.after = Mock()
        self.app._ensure_current_system_visited = Mock()
        self.app._trigger_ring_auto_search = Mock()
        self.disabled_missions = patch.dict(sys.modules, mining_missions=SimpleNamespace(
            MISSIONS_AVAILABLE=False, get_mission_tracker=lambda: None))
        self.disabled_missions.start()
        self.addCleanup(self.disabled_missions.stop)

    def scan(self, paths=None, offset=0):
        return self.app._process_journals_for_catchup(
            paths or [str(self.path)], resume_offsets={str(self.path): offset})

    def test_partial_tail_is_not_included_in_checkpoint(self):
        first, second = record(1), record(2)
        self.path.write_bytes(first + second[:12])
        self.assertEqual(self.scan(), (self.path.name, len(first)))
        self.parser.process_carrier_event.assert_called_once_with(json.loads(first))
        with self.path.open('ab') as stream:
            stream.write(second[12:])
        self.scan(offset=len(first))
        self.assertEqual(self.parser.process_carrier_event.call_count, 2)
        self.parser.process_carrier_event.assert_called_with(json.loads(second))

    def test_data_written_after_scan_is_not_marked_as_already_read(self):
        first, second = record(1), record(2)
        self.path.write_bytes(first)
        def append_after_scan():
            with self.path.open('ab') as stream:
                stream.write(second)
        self.parser._notify_carrier_updated.side_effect = append_after_scan
        checkpoint = self.scan()
        self.assertEqual(checkpoint, (self.path.name, len(first)))
        paths, offsets = self.app._get_new_journals_since_checkpoint(
            [str(self.path)], dict(last_file=checkpoint[0], last_offset=checkpoint[1]))
        self.assertEqual(paths, [str(self.path)])
        self.assertEqual(offsets, {str(self.path): len(first)})

    def test_complete_historical_record_without_newline_remains_supported(self):
        data = record(1).rstrip()
        self.path.write_bytes(data)
        self.assertEqual(self.scan(), (self.path.name, len(data)))
        self.parser.process_carrier_event.assert_called_once_with(json.loads(data))

    def test_checkpoint_does_not_advance_past_unreadable_file(self):
        self.path.write_bytes(record(1))
        missing = self.path.with_name('Journal.2026-11-17T110000.01.log')
        newer = self.path.with_name('Journal.2026-11-17T120000.01.log')
        newer.write_bytes(record(3))
        self.assertEqual(self.scan([str(self.path), str(missing), str(newer)]),
                         (self.path.name, self.path.stat().st_size))

    def test_truncated_checkpoint_file_is_scheduled_from_beginning(self):
        self.path.write_bytes(record(1))
        paths, offsets = self.app._get_new_journals_since_checkpoint(
            [str(self.path)], dict(last_file=self.path.name, last_offset=10000))
        self.assertEqual(paths, [str(self.path)])
        self.assertEqual(offsets, {str(self.path): 0})


class JournalOffsetChecks(unittest.TestCase):
    def test_unchanged_journal_does_not_get_opened_again(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Journal.log'
            path.write_bytes(record(1))
            offset = path.stat().st_size
            with patch('builtins.open', side_effect=AssertionError('unexpected file read')):
                self.assertEqual(read_complete_journal_lines(path, offset), ([], offset))

    def test_startup_offset_handles_empty_file_and_long_unfinished_record(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Journal.log'
            for data, expected in ((b'', 0), (b'x' * 10000, 0),
                                   (record(1) + b'x' * 10000, len(record(1))),
                                   (record(1), len(record(1)))):
                with self.subTest(size=len(data)):
                    path.write_bytes(data)
                    self.assertEqual(journal_resume_offset(path), expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)

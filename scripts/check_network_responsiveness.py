"""Check slow requests using mocked networking and temporary user data."""

import ast
import contextlib
import gzip
import io
import json
import logging
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import tkinter as tk
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, Optional
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

import api_uploader
from api_uploader import APIUploader
from eddn_sender import EDDNSender
from journal_parser import JournalParser


def load_methods(class_name, names, filename='app/main.py'):
    tree = ast.parse((ROOT / filename).read_text(encoding='utf-8-sig'))
    original = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    module = ast.fix_missing_locations(ast.Module(body=[
        ast.ClassDef(name=class_name, bases=[], keywords=[], decorator_list=[],
                     body=[n for n in original.body if isinstance(n, ast.FunctionDef) and n.name in names])
    ], type_ignores=[]))
    namespace = dict(threading=threading, tk=tk, log=logging.getLogger('network-check'),
                     json=json, os=os, Dict=Dict, Optional=Optional, Any=Any)
    exec(compile(module, filename, 'exec'), namespace)
    return namespace[class_name]


App = load_methods('App', {
    '_test_api_connection', '_finish_api_connection_test',
    '_fetch_reserve_levels_for_system', '_trigger_ring_auto_search',
})
Monitor = load_methods('CargoMonitor', {'_process_scan_event', '_process_journal_event_impl'})
Panel = load_methods('ProspectorPanel', {'_share_to_discord', '_finish_discord_share'},
                     'app/prospector_panel.py')


class UploadChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.settings = dict(enabled=True, api_key='test', endpoint_url='https://invalid.test', cmdr_name='Test')
        for item in (patch.object(APIUploader, '_get_config', side_effect=lambda: self.settings.copy()),
                     patch('api_uploader.get_app_data_dir', return_value=self.folder.name)):
            item.start()
            self.addCleanup(item.stop)
        self.uploader = APIUploader()
        self.addCleanup(self.uploader.stop)

    def queued(self, number=1):
        self.uploader._add_to_queue({'id': number}, 'session')
        return self.uploader.upload_queue[-1]

    def test_failed_retries_retain_one_original_item(self):
        failures = [
            SimpleNamespace(status_code=500, text='unavailable'),
            SimpleNamespace(status_code=429, text='rate limited'),
            api_uploader.requests.exceptions.Timeout('slow'),
            api_uploader.requests.exceptions.ConnectionError('offline'),
            RuntimeError('unexpected failure'),
        ]
        for failure in failures:
            with self.subTest(failure=failure):
                self.uploader.upload_queue.clear()
                original = self.queued()
                kwargs = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': failure}
                with patch('api_uploader.requests.post', **kwargs) as post, \
                        patch.object(self.uploader._stop_event, 'wait', return_value=False) as wait:
                    self.uploader.retry_queued_uploads()
                attempts = 1 if isinstance(failure, RuntimeError) else 4
                self.assertEqual(post.call_count, attempts)
                self.assertEqual(len(self.uploader.upload_queue), 1)
                self.assertIs(self.uploader.upload_queue[0], original)
                self.assertEqual(len(json.loads(self.uploader.queue_file.read_text(encoding='utf-8'))), 1)
                self.assertEqual(sum(c.args[0] for c in wait.call_args_list), 0 if attempts == 1 else 450)

    def test_new_failed_upload_is_queued_once(self):
        with patch('api_uploader.requests.post', return_value=SimpleNamespace(status_code=500, text='offline')) as post, \
                patch.object(self.uploader._stop_event, 'wait', return_value=False):
            self.assertFalse(self.uploader.upload_session({'id': 7}))
        self.assertEqual(post.call_count, 4)
        self.assertEqual([item['data'] for item in self.uploader.upload_queue], [{'id': 7}])

    def test_retry_removes_success_and_preserves_new_items(self):
        self.queued()

        def post(*args, **kwargs):
            self.queued(2)
            return SimpleNamespace(status_code=200)

        with patch('api_uploader.requests.post', side_effect=post) as request:
            self.uploader.retry_queued_uploads()
        self.assertEqual(request.call_count, 1)
        self.assertEqual([item['data'] for item in self.uploader.upload_queue], [{'id': 2}])
        self.assertEqual(self.uploader.sessions_uploaded, 1)

    def test_disabled_upload_keeps_queue(self):
        original = self.queued()
        self.settings['enabled'] = False
        with patch('api_uploader.requests.post') as request:
            self.uploader.retry_queued_uploads()
        request.assert_not_called()
        self.assertIs(self.uploader.upload_queue[0], original)

    def test_background_retry_returns_during_slow_request_and_prevents_overlap(self):
        self.queued()
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def post(*args, **kwargs):
            started.set()
            release.wait(3)
            return SimpleNamespace(status_code=200)

        with patch('api_uploader.requests.post', side_effect=post) as request:
            first = self.uploader.retry_queued_uploads(background=True)
            try:
                self.assertTrue(first.daemon)
                self.assertTrue(started.wait(1))
                second = self.uploader.retry_queued_uploads(background=True)
                second.join(1)
                self.assertFalse(second.is_alive())
                self.assertTrue(first.is_alive())
                self.assertEqual(request.call_count, 1)
            finally:
                release.set()
                first.join(3)
            self.assertFalse(first.is_alive())
        self.assertEqual(self.uploader.upload_queue, [])

    def test_stop_interrupts_backoff_and_keeps_item(self):
        original = self.queued()
        waiting = threading.Event()
        real_wait = self.uploader._stop_event.wait

        def wait(delay):
            waiting.set()
            return real_wait(delay)

        with patch('api_uploader.requests.post', return_value=SimpleNamespace(status_code=500, text='offline')) as post, \
                patch.object(self.uploader._stop_event, 'wait', side_effect=wait):
            worker = self.uploader.retry_queued_uploads(background=True)
            try:
                self.assertTrue(waiting.wait(1))
            finally:
                self.uploader.stop()
                worker.join(2)
            self.assertFalse(worker.is_alive())
        self.assertEqual(post.call_count, 1)
        self.assertIs(self.uploader.upload_queue[0], original)


class EDDNChecks(unittest.TestCase):
    def setUp(self):
        self.sender = EDDNSender('Test', 'EliteMining', 'test')
        self.sender.update_game_info({'gameversion': 'version', 'build': 'build', 'Commander': 'Before'})
        self.sender.set_enabled(True)
        self.addCleanup(self.stop)

    def stop(self):
        self.sender.stop()
        if self.sender._journal_worker:
            self.sender._journal_worker.join(3)

    def test_slow_delivery_keeps_order_payload_snapshot_and_game_info(self):
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        sent = []

        def send(message):
            if not sent:
                started.set()
                release.wait(3)
            sent.append(message)
            return True

        event = dict(event='FSDJump', StarSystem='Sol', FuelLevel=15, SystemFaction={'Name': 'Original'})
        with patch.object(self.sender, '_send_message', side_effect=send):
            self.assertTrue(self.sender.send_journal_event('FSDJump', event, background=True))
            self.assertTrue(started.wait(1))
            self.assertTrue(self.sender.send_journal_event('FSDJump', dict(event, StarSystem='Achenar'), background=True))
            self.assertEqual(self.sender.messages_sent, 0)
            event['SystemFaction']['Name'] = 'Changed'
            self.sender.commander_name = 'After'
            release.set()
            self.sender._journal_queue.join()
        self.assertEqual([m['message']['StarSystem'] for m in sent], ['Sol', 'Achenar'])
        self.assertEqual([m['header']['uploaderID'] for m in sent], ['Before', 'Before'])
        self.assertEqual(sent[0]['message']['SystemFaction']['Name'], 'Original')
        self.assertNotIn('FuelLevel', sent[0]['message'])
        self.assertEqual(self.sender.messages_sent, 2)

    def test_failed_delivery_does_not_stop_following_messages(self):
        with patch.object(self.sender, '_send_message', side_effect=[False, True]) as send:
            for name in ('Sol', 'Achenar'):
                self.sender.send_journal_event('Location', {'event': 'Location', 'StarSystem': name}, background=True)
            self.sender._journal_queue.join()
        self.assertEqual(send.call_count, 2)
        self.assertEqual(self.sender.messages_sent, 1)

    def test_disabled_or_unprimed_sender_does_not_queue(self):
        self.sender.set_enabled(False)
        self.assertFalse(self.sender.send_journal_event('Location', {}, background=True))
        self.sender.set_enabled(True)
        self.sender.game_version = ''
        self.assertFalse(self.sender.send_journal_event('Location', {}, background=True))
        self.assertIsNone(self.sender._journal_worker)

    def test_stop_cancels_pending_messages_without_joining_slow_request(self):
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def send(message):
            started.set()
            release.wait(3)
            return True

        with patch.object(self.sender, '_send_message', side_effect=send) as request:
            self.sender.send_journal_event('Location', {'event': 'Location'}, background=True)
            self.assertTrue(started.wait(1))
            self.sender.send_journal_event('FSDJump', {'event': 'FSDJump'}, background=True)
            self.sender.stop()
            self.assertTrue(self.sender._journal_worker.is_alive())
            self.assertFalse(self.sender.send_journal_event('Location', {}, background=True))
            release.set()
            self.sender._journal_worker.join(3)
        self.assertFalse(self.sender._journal_worker.is_alive())
        self.assertEqual(request.call_count, 1)

    def test_sync_callers_keep_actual_result_and_gzip_payload(self):
        with patch('eddn_sender.requests.post', return_value=SimpleNamespace(status_code=200)) as post:
            self.assertTrue(self.sender.send_journal_event('Location', {'event': 'Location', 'StarSystem': 'Sol'}))
        payload = json.loads(gzip.decompress(post.call_args.kwargs['data']).decode('utf-8'))
        self.assertEqual(payload['message']['StarSystem'], 'Sol')
        self.assertEqual(payload['header']['gamebuild'], 'build')
        self.assertEqual(self.sender.messages_sent, 1)
        self.assertIsNone(self.sender._journal_worker)


class AppChecks(unittest.TestCase):
    def setUp(self):
        self.app = App()
        self.pending = queue.Queue()
        self.app.after = lambda delay, callback, *args: self.pending.put((callback, args))
        self.app.winfo_exists = lambda: True
        self.jp = SimpleNamespace(system_reserve_levels={'Known Ring': 'Pristine'},
                                  _fetch_system_reserve_levels_from_spansh=Mock(return_value={'Sol 1 A Ring': 'Major'}))
        self.app.cargo_monitor = SimpleNamespace(journal_parser=self.jp, user_db=Mock(), current_system='Sol')
        self.workers = []
        real_thread = threading.Thread

        def thread(**kwargs):
            result = real_thread(**kwargs)
            self.workers.append(result)
            return result

        patches = patch('threading.Thread', side_effect=thread)
        patches.start()
        self.addCleanup(patches.stop)
        self.addCleanup(self.join_workers)
        self.dialog = Mock()
        helpers = ModuleType('app_utils')
        helpers.centered_message = self.dialog
        self.uploader = Mock()
        self.uploader.test_connection.return_value = True, 'Connection successful'
        uploaders = ModuleType('api_uploader')
        uploaders.APIUploader = Mock(return_value=self.uploader)
        modules = patch.dict(sys.modules, app_utils=helpers, api_uploader=uploaders)
        modules.start()
        self.addCleanup(modules.stop)
        self.app._save_api_settings = Mock()

    def join_workers(self):
        for worker in self.workers:
            worker.join(3)
            self.assertFalse(worker.is_alive())

    def flush(self):
        self.join_workers()
        while not self.pending.empty():
            callback, args = self.pending.get_nowait()
            callback(*args)

    def test_reserve_fetch_shares_request_and_publishes_only_on_tk_callback(self):
        first, second = Mock(), Mock()
        self.app._fetch_reserve_levels_for_system('Sol', first)
        self.app._fetch_reserve_levels_for_system('Sol', second)
        self.join_workers()
        self.jp._fetch_system_reserve_levels_from_spansh.assert_called_once_with('Sol')
        self.assertEqual(self.jp.system_reserve_levels, {'Known Ring': 'Pristine'})
        first.assert_not_called()
        self.flush()
        self.assertEqual(self.jp.system_reserve_levels['Sol 1 A Ring'], 'Major')
        self.app.cargo_monitor.user_db.bulk_update_reserve_levels.assert_called_once_with('Sol', {'Sol 1 A Ring': 'Major'})
        first.assert_called_once_with({'Sol 1 A Ring': 'Major'}, None)
        second.assert_called_once_with({'Sol 1 A Ring': 'Major'}, None)
        self.assertEqual(self.app._reserve_requests, {})

    def test_reserve_failure_clears_pending_and_allows_retry(self):
        completed = Mock()
        self.jp._fetch_system_reserve_levels_from_spansh.side_effect = RuntimeError('offline')
        self.app._fetch_reserve_levels_for_system('Sol', completed)
        self.flush()
        completed.assert_called_once_with({}, 'offline')
        self.assertEqual(self.jp.system_reserve_levels, {'Known Ring': 'Pristine'})
        self.app._fetch_reserve_levels_for_system('Sol')
        self.flush()
        self.assertEqual(self.jp._fetch_system_reserve_levels_from_spansh.call_count, 2)

    def test_slow_reserve_lookup_returns_before_response_and_late_close_skips_ui(self):
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def fetch(system):
            started.set()
            release.wait(3)
            return {'Sol 1 A Ring': 'Major'}

        completed = Mock()
        self.jp._fetch_system_reserve_levels_from_spansh.side_effect = fetch
        self.app._fetch_reserve_levels_for_system('Sol', completed)
        try:
            self.assertTrue(started.wait(1))
            self.assertTrue(self.workers[0].is_alive())
            self.assertEqual(self.jp.system_reserve_levels, {'Known Ring': 'Pristine'})
            self.app._network_closing = True
        finally:
            release.set()
            self.join_workers()
        self.assertTrue(self.pending.empty())
        completed.assert_not_called()
        self.app.cargo_monitor.user_db.bulk_update_reserve_levels.assert_not_called()

    def test_startup_delegates_and_ignores_old_system_status(self):
        self.app.ring_finder = SimpleNamespace(auto_search_var=SimpleNamespace(get=lambda: True),
                                             _startup_auto_search=Mock(), status_var=Mock())
        self.app.current_system = 'Sol'
        self.app._fetch_reserve_levels_for_system = Mock()
        self.app._trigger_ring_auto_search()
        self.app.ring_finder._startup_auto_search.assert_called_once_with(force=True)
        callback = self.app._fetch_reserve_levels_for_system.call_args.kwargs['on_complete']
        callback({'Sol 1 A Ring': 'Major'}, None)
        self.app.ring_finder.status_var.set.assert_called_with('Fetched 1 reserve levels for Sol')
        self.app.current_system = 'Achenar'
        self.app.ring_finder.status_var.reset_mock()
        callback({}, 'offline')
        self.app.ring_finder.status_var.set.assert_not_called()

    def test_connection_result_waits_for_tk_and_duplicate_tests_are_ignored(self):
        self.app._test_api_connection()
        self.app._test_api_connection()
        self.join_workers()
        self.dialog.assert_not_called()
        self.uploader.test_connection.assert_called_once()
        self.flush()
        self.dialog.assert_called_once_with(self.app, 'Connection Test', '✓ Connection successful')
        self.assertFalse(self.app._api_test_in_progress)

    def test_connection_failure_and_close_do_not_touch_destroyed_ui(self):
        self.uploader.test_connection.side_effect = RuntimeError('offline')
        self.app._test_api_connection()
        self.flush()
        self.dialog.assert_called_once_with(self.app, 'Connection Test', 'Error: offline')
        self.dialog.reset_mock()
        self.app._test_api_connection()
        self.app._network_closing = True
        self.flush()
        self.dialog.assert_not_called()

class ZZHeartbeatChecks(unittest.TestCase):
    """Create the real Tcl interpreter after the other worker tests."""

    setUp = AppChecks.setUp
    join_workers = AppChecks.join_workers

    def test_slow_connection_keeps_real_tk_heartbeat_running(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        beats, worker_ids = [], []
        self.app.after = root.after

        def connection():
            worker_ids.append(threading.get_ident())
            started.set()
            release.wait(2)
            return True, 'Connection successful'

        def heartbeat():
            beats.append(threading.get_ident())
            if len(beats) == 3:
                release.set()
            else:
                root.after(10, heartbeat)

        self.uploader.test_connection.side_effect = connection
        self.dialog.side_effect = lambda *args: root.after_idle(root.quit)
        self.app._test_api_connection()
        root.after(10, heartbeat)
        timeout = root.after(1500, lambda: (release.set(), root.quit()))
        root.mainloop()
        root.after_cancel(timeout)
        self.join_workers()
        self.assertTrue(started.is_set())
        self.assertEqual(len(beats), 3)
        self.assertTrue(all(tid == threading.get_ident() for tid in beats))
        self.assertNotEqual(worker_ids, [threading.get_ident()])
        self.dialog.assert_called_once()


class DiscordChecks(unittest.TestCase):
    def setUp(self):
        self.panel = Panel()
        self.pending = queue.Queue()
        self.parent = SimpleNamespace(after=lambda delay, callback, *args: self.pending.put((callback, args)))
        self.panel.winfo_toplevel = lambda: self.parent
        self.panel.winfo_exists = lambda: True
        self.panel._set_status = Mock()
        self.panel.reports_tree_tab = SimpleNamespace(selection=lambda: ['one'])
        self.session = dict(system='Sol', body='1 A Ring', tph=100)
        self.panel.reports_tab_session_lookup = {'one': self.session}
        self.panel._get_discord_username = Mock(return_value=('CMDR', 'Comment'))
        self.dialog, self.send = Mock(), Mock(return_value=(True, 'Posted'))
        helpers = ModuleType('app_utils')
        helpers.centered_message = self.dialog
        discord = ModuleType('discord_integration')
        discord.is_discord_enabled = lambda: True
        discord.send_discord_report = self.send
        modules = patch.dict(sys.modules, app_utils=helpers, discord_integration=discord)
        modules.start()
        self.addCleanup(modules.stop)
        self.workers = []
        real_thread = threading.Thread

        def thread(**kwargs):
            result = real_thread(**kwargs)
            self.workers.append(result)
            return result

        threads = patch('threading.Thread', side_effect=thread)
        threads.start()
        self.addCleanup(threads.stop)
        self.addCleanup(self.join_workers)

    def join_workers(self):
        for worker in self.workers:
            worker.join(3)
            self.assertFalse(worker.is_alive())

    def flush(self):
        self.join_workers()
        while not self.pending.empty():
            callback, args = self.pending.get_nowait()
            callback(*args)

    def test_slow_share_preserves_snapshot_and_rejects_duplicate_clicks(self):
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def send(data):
            started.set()
            release.wait(3)
            return True, 'Posted'

        self.send.side_effect = send
        self.panel._share_to_discord()
        try:
            self.assertTrue(started.wait(1))
            self.assertTrue(self.workers[0].is_alive())
            self.panel._share_to_discord()
            self.panel._get_discord_username.assert_called_once()
            self.assertEqual(self.send.call_count, 1)
            self.dialog.assert_not_called()
            self.session['system'] = 'Achenar'
        finally:
            release.set()
            self.flush()
        data = self.send.call_args.args[0]
        self.assertEqual((data['system'], data['discord_username'], data['discord_comment']),
                         ('Sol', 'CMDR', 'Comment'))
        self.dialog.assert_called_once_with(self.parent, 'Discord Share', 'Posted')
        self.panel._set_status.assert_called_once_with('Report shared to Discord successfully!')
        self.assertFalse(self.panel._discord_share_in_progress)

    def test_failed_share_keeps_existing_error_message(self):
        self.send.return_value = False, 'Request timed out'
        self.panel._share_to_discord()
        self.flush()
        self.dialog.assert_called_once_with(self.parent, 'Discord Error', 'Request timed out')
        self.panel._set_status.assert_called_once_with('Discord share failed: Request timed out')
        self.assertFalse(self.panel._discord_share_in_progress)

    def test_cancel_does_not_send_and_close_suppresses_late_dialog(self):
        self.panel._get_discord_username.return_value = None, None
        self.panel._share_to_discord()
        self.send.assert_not_called()
        self.panel._get_discord_username.return_value = 'CMDR', None
        self.panel._share_to_discord()
        self.join_workers()
        self.parent._network_closing = True
        self.flush()
        self.dialog.assert_not_called()


class ScanChecks(unittest.TestCase):
    def setUp(self):
        self.parser = object.__new__(JournalParser)
        self.parser.user_db = Mock()
        self.parser.ring_info = {}
        self.parser.system_reserve_levels = {}
        self.parser.is_live_monitoring = True
        self.parser._fetch_system_reserve_levels_from_spansh = Mock(return_value={'Sol 1 A Ring': 'Major'})
        self.monitor = Monitor()
        self.monitor.journal_parser = self.parser
        self.monitor.main_app_ref = SimpleNamespace(after=Mock(), _fetch_reserve_levels_for_system=Mock())
        self.event = dict(event='Scan', StarSystem='Sol', SystemAddress=1, BodyID=2,
                          Rings=[dict(Name='Sol 1 A Ring', RingClass='eRingClass_Metallic')])

    def test_live_scan_stores_metadata_without_network_and_schedules_enrichment(self):
        self.monitor._process_scan_event(self.event)
        self.parser._fetch_system_reserve_levels_from_spansh.assert_not_called()
        self.assertIn((1, 'Sol 1 A Ring'), self.parser.ring_info)
        self.parser.user_db.update_ring_metadata.assert_called_once()
        self.monitor.main_app_ref.after.assert_called_once_with(
            0, self.monitor.main_app_ref._fetch_reserve_levels_for_system, 'Sol')

    def test_authoritative_cached_and_historical_reserves_skip_requests(self):
        for kind in ('journal', 'cache', 'historical'):
            with self.subTest(kind=kind):
                self.setUp()
                if kind == 'journal':
                    self.event['ReserveLevel'] = 'PristineResources'
                elif kind == 'cache':
                    self.parser.system_reserve_levels['Sol 1 A Ring'] = 'Pristine'
                else:
                    self.parser.is_live_monitoring = False
                self.monitor._process_scan_event(self.event)
                self.parser._fetch_system_reserve_levels_from_spansh.assert_not_called()
                self.monitor.main_app_ref.after.assert_not_called()

    def test_existing_background_parser_callers_keep_reserve_fallback(self):
        self.parser.process_scan(self.event)
        self.parser._fetch_system_reserve_levels_from_spansh.assert_called_once_with('Sol')
        self.assertEqual(self.parser.system_reserve_levels['Sol 1 A Ring'], 'Major')

    def test_live_dispatch_uses_nonblocking_scan_path(self):
        self.parser.process_carrier_event = Mock()
        self.monitor._process_scan_event = Mock()
        self.monitor._process_journal_event_impl(json.dumps(self.event))
        self.monitor._process_scan_event.assert_called_once_with(self.event)


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    with contextlib.redirect_stdout(io.StringIO()):
        unittest.main(verbosity=2)

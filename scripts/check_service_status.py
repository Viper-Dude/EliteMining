import ast
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

import requests
import config
import service_status
from marketplace_api import MarketplaceAPI
from system_finder_api import SystemFinderAPI


def setUpModule():
    directory = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(directory.cleanup)
    config_file = Path(directory.name) / 'config.json'
    config_file.write_text('{}', encoding='utf-8')
    config_patch = patch.object(config, 'CONFIG_FILE', str(config_file))
    config_patch.start()
    unittest.addModuleCleanup(config_patch.stop)


class ServiceStatusChecks(unittest.TestCase):
    def setUp(self):
        self.callback = Mock()
        self.callback_patch = patch.object(service_status, 'status_callback', self.callback)
        self.callback_patch.start()
        self.addCleanup(self.callback_patch.stop)

    def response(self, status=200, data=None):
        response = Mock(status_code=status)
        response.json.return_value = {'results': []} if data is None else data
        if status >= 400:
            response.raise_for_status.side_effect = requests.HTTPError(response=response)
        return response

    def test_success_preserves_response_and_request_arguments(self):
        response = self.response()
        send = Mock(return_value=response)
        result = service_status.tracked_request('spansh', send, 'url', json={'a': 1}, timeout=30)
        self.assertIs(result, response)
        send.assert_called_once_with('url', json={'a': 1}, timeout=30)
        self.callback.assert_called_once_with('spansh', 'online')

    def test_http_failure_preserves_response(self):
        for status in (400, 429, 500, 503):
            with self.subTest(status=status):
                self.callback.reset_mock()
                response = self.response(status)
                self.assertIs(service_status.tracked_request('market', Mock(return_value=response)), response)
                self.callback.assert_called_once_with('market', 'offline')

    def test_network_failure_is_reported_and_reraised(self):
        for error in (requests.Timeout('timeout'), requests.ConnectionError('connection')):
            with self.subTest(error=error):
                self.callback.reset_mock()
                with self.assertRaises(type(error)) as raised:
                    service_status.tracked_request('spansh', Mock(side_effect=error))
                self.assertIs(raised.exception, error)
                self.callback.assert_called_once_with('spansh', 'offline')

    def test_standalone_api_use_needs_no_callback(self):
        with patch.object(service_status, 'status_callback', None):
            response = self.response()
            self.assertIs(service_status.tracked_request('market', Mock(return_value=response)), response)

    def test_ardent_empty_results_are_online_without_extra_request(self):
        with patch('marketplace_api.requests.get', return_value=self.response(data=[])) as send:
            self.assertEqual(MarketplaceAPI._fetch_ardent('/test', {}), [])
        self.assertEqual(send.call_count, 1)
        self.callback.assert_called_once_with('market', 'online')

    def test_ardent_failure_keeps_existing_empty_result_behavior(self):
        with patch('marketplace_api.requests.get', side_effect=requests.Timeout()):
            self.assertEqual(MarketplaceAPI._fetch_ardent('/test', {}), [])
        self.callback.assert_called_once_with('market', 'offline')

    def test_cancelled_ardent_request_does_not_change_status(self):
        with patch('marketplace_api.requests.get') as send:
            self.assertEqual(MarketplaceAPI._fetch_ardent('/test', {}, is_cancelled=lambda: True), [])
        send.assert_not_called()
        self.callback.assert_not_called()

    def test_commodity_spansh_empty_pages_are_online(self):
        with patch.object(MarketplaceAPI, '_spansh_available', return_value=True), \
                patch.object(MarketplaceAPI, '_spansh_record_result'), \
                patch('marketplace_api.requests.post', return_value=self.response()) as send:
            self.assertEqual(MarketplaceAPI._fetch_spansh('platinum', 'Sol', 'imports'), [])
        self.assertEqual(send.call_count, 3)
        self.assertEqual(self.callback.call_count, 3)
        self.assertTrue(all(call.args == ('spansh', 'online') for call in self.callback.call_args_list))

    def test_spansh_circuit_breaker_skip_does_not_change_status(self):
        with patch.object(MarketplaceAPI, '_spansh_available', return_value=False), \
                patch('marketplace_api.requests.post') as send:
            self.assertEqual(MarketplaceAPI._fetch_spansh('platinum', 'Sol', 'imports'), [])
        send.assert_not_called()
        self.callback.assert_not_called()

    def test_system_search_empty_results_are_online(self):
        with patch('system_finder_api.requests.post', return_value=self.response()) as send:
            self.assertEqual(SystemFinderAPI.search_systems('Sol'), [])
        self.assertEqual(send.call_count, 1)
        self.callback.assert_called_once_with('spansh', 'online')

    def test_system_search_failure_still_raises(self):
        with patch('system_finder_api.requests.post', return_value=self.response(503)):
            with self.assertRaises(requests.HTTPError):
                SystemFinderAPI.search_systems('Sol')
        self.callback.assert_called_once_with('spansh', 'offline')

    def load_method(self, filename, method_name):
        tree = ast.parse((ROOT / filename).read_text(encoding='utf-8-sig'))
        node = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == method_name)
        namespace = {'tk': tk, 'threading': threading}
        exec(compile(ast.Module(body=[node], type_ignores=[]), filename, 'exec'), namespace)
        return namespace[node.name]

    def test_status_updates_wait_for_ui_thread_and_use_existing_updaters(self):
        queued = []
        app = SimpleNamespace(after=lambda delay, callback: queued.append((delay, callback)),
                              _update_market_api_status=Mock(),
                              ring_finder=SimpleNamespace(_update_spansh_status=Mock()))
        queue = self.load_method('app/main.py', '_queue_search_service_status')
        queue(app, 'market', 'offline')
        queue(app, 'spansh', 'online')
        app._update_market_api_status.assert_not_called()
        app.ring_finder._update_spansh_status.assert_not_called()
        for delay, callback in queued:
            self.assertEqual(delay, 0)
            callback()
        app._update_market_api_status.assert_called_once_with('offline')
        app.ring_finder._update_spansh_status.assert_called_once_with('online')

    def test_shutdown_does_not_break_requests(self):
        queue = self.load_method('app/main.py', '_queue_search_service_status')
        for error in (RuntimeError(), tk.TclError()):
            app = SimpleNamespace(after=Mock(side_effect=error))
            queue(app, 'market', 'online')

    def test_eddn_timeout_reaches_one_shot_callback_as_offline(self):
        check = self.load_method('app/ring_finder.py', '_check_eddn_status')
        queued = []
        ring_finder = SimpleNamespace(parent=SimpleNamespace(after=lambda delay, cb: queued.append(cb)))
        with patch('requests.get', side_effect=requests.ReadTimeout), \
                patch.object(threading, 'Thread', side_effect=lambda target, daemon: SimpleNamespace(start=target)):
            check(ring_finder, self.callback)
        self.callback.assert_not_called()
        self.assertEqual(len(queued), 1)
        queued[0]()
        self.callback.assert_called_once_with('offline')

    def test_ardent_one_shot_does_not_start_a_periodic_timer(self):
        check = self.load_method('app/main.py', '_check_market_api_status')
        publish = Mock()
        app = SimpleNamespace(after=Mock(), _update_market_api_status=publish,
                              _check_market_api_status=Mock())
        with patch('requests.get', return_value=self.response()), \
                patch.object(threading, 'Thread', side_effect=lambda target, daemon: SimpleNamespace(start=target)):
            check(app, self.callback)
            self.assertEqual([call.args[0] for call in app.after.call_args_list], [0])
            app.after.call_args.args[1]()
            self.callback.assert_called_once_with('online')
            publish.assert_not_called()

            app.after.reset_mock()
            check(app)
            self.assertEqual([call.args[0] for call in app.after.call_args_list], [0, 300_000])
            app.after.call_args_list[0].args[1]()
            publish.assert_called_once_with('online')

    def test_footer_placement_and_status_in_both_languages_and_all_themes(self):
        source = (ROOT / 'app/main.py').read_text(encoding='utf-8-sig')
        start = source.index('        _ind_frame = tk.Frame(actions, bg=_info_bg)')
        end = source.index('        # Load CMDR name in background', start)
        block = '\n'.join(line[8:] for line in source[start:end].splitlines())
        tree = ast.parse(source)
        names = ('_update_market_api_status', '_update_footer_indicator')
        methods = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in names]
        from ui.theme import get_theme_colors

        class Tip:
            def __init__(self, widget, text, **kwargs):
                self.text = text
                self.tooltip_window = None

        root = tk.Tk()
        root.withdraw()
        try:
            for language in ('en', 'de'):
                strings = json.loads((ROOT / f'app/localization/strings_{language}.json').read_text(encoding='utf-8-sig'))
                def translate(key):
                    section, name = key.split('.')
                    return strings[section][name]
                for theme in ('modern', 'modern_slate', 'modern_orange', 'dark_gray', 'elite_orange'):
                    with self.subTest(language=language, theme=theme):
                        actions = tk.Frame(root)
                        app = SimpleNamespace(_scaled_font=lambda size: ('Segoe UI', size), current_theme=theme,
                                              _show_service_status=Mock())
                        scope = dict(self=app, actions=actions, _info_bg='#14171B', tk=tk, t=translate,
                                     ToolTip=Tip, get_theme_colors=get_theme_colors)
                        exec(compile(ast.Module(body=methods, type_ignores=[]), 'app/main.py', 'exec'), scope)
                        app._update_footer_indicator = lambda *args: scope['_update_footer_indicator'](app, *args)
                        exec(block, scope)
                        label = app._footer_services_label
                        footer = label.master
                        self.assertIs(footer.master, actions)
                        self.assertEqual(int(footer.grid_info()['column']), 1)
                        self.assertEqual(footer.pack_slaves()[-1], label)
                        self.assertEqual(label.cget('text'), translate('status_bar.services_checking'))
                        market = translate('status_bar.market_api')
                        for statuses, overall, color in (
                                (('online', 'online', 'online'), 'online', '#4FB87A'),
                                (('online', 'online', 'offline'), 'partial', '#D9A441'),
                                (('offline', 'offline', 'offline'), 'offline', '#C06060')):
                            app._update_footer_indicator('eddn', statuses[0])
                            app._update_footer_indicator('spansh', statuses[1])
                            scope['_update_market_api_status'](app, statuses[2])
                            self.assertEqual(label.cget('text'), translate('status_bar.services_' + overall))
                            self.assertEqual(label.cget('fg'), color)
                            self.assertEqual(app._footer_services_tip.text.splitlines()[-1],
                                             translate('system_finder.service_' + statuses[2]).format(service=market))
                        actions.destroy()
        finally:
            root.destroy()

    def test_database_visited_total_survives_footer_removal(self):
        from unittest.mock import MagicMock
        from session_statistics_panel import SessionStatisticsPanel
        for total, expected in ((8199, '8,199'), (0, '0'), (None, '—')):
            with self.subTest(total=total):
                parser = SimpleNamespace(get_systems_visited=lambda: total)
                app = SimpleNamespace(cargo_monitor=SimpleNamespace(journal_parser=parser))
                tree = MagicMock(_sort_column=None)
                tree.__getitem__.return_value = ('mineral', 'rings')
                tree.get_children.return_value = ()
                panel = SimpleNamespace(rows=[], database_records=[], owner=SimpleNamespace(main_app=app),
                                        database_summary=Mock(), database_heading=Mock(), database_tree=tree)
                with patch('session_statistics_panel.t', side_effect=lambda key: '{visited}' if key.endswith('database_totals') else 'Total'), \
                        patch('session_statistics_panel.scaled_font', return_value=('Segoe UI', 9)):
                    SessionStatisticsPanel._show_database(panel)
                panel.database_summary.configure.assert_called_once_with(text=expected)


class ServiceWakeChecks(unittest.TestCase):
    def setUp(self):
        self.timers = {}
        self.checks = [(Mock(), Mock()) for _ in range(3)]
        self.wake = service_status.ServiceWakeChecks(self.timers.__setitem__, self.checks)

    def test_checks_all_at_ten_seconds_and_only_failures_at_thirty(self):
        self.wake.resume()
        self.assertEqual(set(self.timers), {10_000, 30_000})
        for probe, publish in self.checks:
            probe.assert_not_called()
            publish.assert_not_called()

        self.timers[10_000]()
        for (probe, publish), status in zip(self.checks, ('online', 'offline', 'online')):
            self.assertEqual(probe.call_count, 1)
            probe.call_args.args[0](status)
            publish.assert_called_once_with(status)

        self.timers[30_000]()
        self.assertEqual([probe.call_count for probe, _ in self.checks], [1, 2, 1])
        probe, publish = self.checks[1]
        probe.call_args.args[0]('online')
        publish.assert_called_with('online')

    def test_late_failure_retries_once_without_repeating_an_in_flight_check(self):
        self.wake.resume()
        self.timers[10_000]()
        self.timers[30_000]()
        probe, publish = self.checks[0]
        self.assertEqual(probe.call_count, 1)
        probe.call_args.args[0]('offline')
        self.assertEqual(probe.call_count, 2)
        probe.call_args.args[0]('offline')
        self.assertEqual(probe.call_count, 2)
        self.assertEqual(publish.call_count, 2)

    def test_suspend_and_new_wake_ignore_old_results_and_retry_timer(self):
        self.wake.resume()
        self.timers[10_000]()
        old_retry = self.timers[30_000]
        probe, publish = self.checks[0]
        old_result = probe.call_args.args[0]
        self.wake.suspend()
        self.wake.resume()
        old_result('offline')
        old_retry()
        publish.assert_not_called()
        self.assertEqual(probe.call_count, 1)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows power messages require Windows')
    def test_windows_suspend_and_resume_messages_reach_the_app(self):
        from windows_resume import watch_windows_resume

        root = tk.Tk()
        try:
            root.attributes('-alpha', 0)
            root.update_idletasks()
            suspend, resume = Mock(), Mock()
            callback = watch_windows_resume(root, resume, suspend)
            self.assertIsNotNone(callback)
            user32 = ctypes.WinDLL('user32')
            user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
            user32.GetAncestor.restype = wintypes.HWND
            user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t)
            user32.SendMessageW.restype = ctypes.c_ssize_t
            hwnd = user32.GetAncestor(root.winfo_id(), 2)
            self.assertNotEqual(hwnd, root.winfo_id())
            user32.SendMessageW(hwnd, 0x0218, 0x0004, 0)
            user32.SendMessageW(hwnd, 0x0218, 0x0012, 0)
            user32.SendMessageW(hwnd, 0x0218, 0x0007, 0)
            suspend.assert_called_once_with()
            resume.assert_called_once_with()
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()

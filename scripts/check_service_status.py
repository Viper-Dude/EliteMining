import ast
import json
from pathlib import Path
import sys
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

import requests
import service_status
from marketplace_api import MarketplaceAPI
from system_finder_api import SystemFinderAPI


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

    def queue_method(self):
        tree = ast.parse((ROOT / 'app/main.py').read_text(encoding='utf-8-sig'))
        node = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == '_queue_search_service_status')
        namespace = {'tk': tk}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'app/main.py', 'exec'), namespace)
        return namespace[node.name]

    def test_status_updates_wait_for_ui_thread_and_use_existing_updaters(self):
        queued = []
        app = SimpleNamespace(after=lambda delay, callback: queued.append((delay, callback)),
                              _update_market_api_status=Mock(),
                              ring_finder=SimpleNamespace(_update_spansh_status=Mock()))
        queue = self.queue_method()
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
        for error in (RuntimeError(), tk.TclError()):
            app = SimpleNamespace(after=Mock(side_effect=error))
            self.queue_method()(app, 'market', 'online')

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


if __name__ == '__main__':
    unittest.main()

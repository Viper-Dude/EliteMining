"""Check interrupted and overlapping settings saves using temporary files."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_config(path):
    spec = importlib.util.spec_from_file_location('saving_test_config', ROOT / 'app/config.py')
    config = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(config)
    config.CONFIG_FILE = str(path)
    return config


class ConfigSaveChecks(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.path = self.root / 'config.json'
        self.config = load_config(self.path)
        self.now = 1000.0
        self.config.time = SimpleNamespace(time=lambda: self.now)
        self.base = {'language': 'en', 'ui_scale': 1.0, 'nested': {'material': ['Platinum']}}
        self.config._save_cfg(self.base)

    def disk(self):
        return json.loads(self.path.read_text(encoding='utf-8'))

    def assert_no_temporary_files(self):
        self.assertEqual(list(self.root.glob('config.json.*.tmp')), [])

    def test_replacement_receives_complete_closed_file_in_same_directory(self):
        before = self.path.read_bytes()
        desired = {'language': 'de', 'name': 'Grüße', 'values': [0, False, None]}
        replace = self.config.os.replace

        def inspect(source, destination):
            self.assertEqual(Path(source).parent, self.path.parent)
            self.assertEqual(Path(destination), self.path)
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(json.loads(Path(source).read_text(encoding='utf-8')), desired)
            replace(source, destination)

        self.now += 1
        with patch.object(self.config.os, 'replace', side_effect=inspect) as replacement:
            self.config._save_cfg(desired)
        replacement.assert_called_once()
        self.assertEqual(self.disk(), desired)
        self.assertFalse(self.config._cache_dirty)
        self.assert_no_temporary_files()

    def test_failed_serialization_creation_sync_and_replacement_keep_previous_file(self):
        failures = [
            (self.config.json, 'dumps', TypeError('serialization failed')),
            (self.config.tempfile, 'NamedTemporaryFile', PermissionError('creation denied')),
            (self.config.os, 'fsync', OSError('sync failed')),
            (self.config.os, 'replace', PermissionError('file locked')),
            (self.config.os, 'replace', OSError('replacement failed')),
        ]
        for number, (target, method, error) in enumerate(failures):
            with self.subTest(stage=method, error=type(error).__name__):
                before = self.path.read_bytes()
                last_save = self.config._last_save_time
                desired = dict(self.base, change=number)
                self.now += 1
                with patch.object(target, method, side_effect=error), self.assertLogs(self.config.log, 'ERROR'):
                    self.config._save_cfg(desired)
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(self.config._last_save_time, last_save)
                self.assertTrue(self.config._cache_dirty)
                self.assert_no_temporary_files()
                self.now += 3
                self.assertEqual(self.config._load_cfg(), desired)
                self.config.flush_config()
                self.assertEqual(load_config(self.path)._load_cfg(), desired)
                self.assertFalse(self.config._cache_dirty)

    def test_partial_write_and_flush_failure_keep_previous_file(self):
        temporary_file = self.config.tempfile.NamedTemporaryFile
        for stage in ('write', 'flush'):
            with self.subTest(stage=stage):
                before = self.path.read_bytes()

                class FailingStream:
                    def __init__(self, *args, **kwargs):
                        self.stream = temporary_file(*args, **kwargs)
                        self.name = self.stream.name

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return self.stream.__exit__(*args)

                    def write(self, text):
                        if stage == 'write':
                            self.stream.write(text[:10])
                            raise OSError('partial write')
                        return self.stream.write(text)

                    def flush(self):
                        raise OSError('flush failed')

                self.now += 1
                with patch.object(self.config.tempfile, 'NamedTemporaryFile', FailingStream), \
                        self.assertLogs(self.config.log, 'ERROR'):
                    self.config._save_cfg(dict(self.base, stage=stage))
                self.assertEqual(self.path.read_bytes(), before)
                self.assertTrue(self.config._cache_dirty)
                self.assert_no_temporary_files()
                self.config.flush_config()
                self.assertEqual(self.disk()['stage'], stage)

    def test_rapid_changes_remain_cached_until_flush_and_survive_reload(self):
        self.config.update_config_value('first', 1)
        self.now += 0.1
        self.config.update_config_values({'second': 2, 'language': 'de'})
        self.assertEqual(self.disk(), self.base)
        self.now += 3
        self.assertEqual(self.config._load_cfg()['first'], 1)
        self.config.flush_config()
        expected = dict(self.base, first=1, second=2, language='de')
        self.assertEqual(load_config(self.path)._load_cfg(), expected)
        self.assertFalse(self.config._cache_dirty)

    def test_failed_flush_preserves_pending_changes_for_retry(self):
        self.config.update_config_value('pending', 'keep')
        before = self.path.read_bytes()
        with patch.object(self.config.os, 'replace', side_effect=PermissionError('locked')), \
                self.assertLogs(self.config.log, 'INFO') as messages:
            self.config.flush_config()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(self.config._cache_dirty)
        self.assertFalse(any('flushed to disk' in message for message in messages.output))
        self.config.flush_config()
        self.assertEqual(self.disk()['pending'], 'keep')
        self.assert_no_temporary_files()

    def test_empty_pending_configuration_does_not_reload_old_values(self):
        self.config._save_cfg({})
        self.now += 3
        self.assertEqual(self.config._load_cfg(), {})
        self.config.flush_config()
        self.assertEqual(self.disk(), {})

    def test_pending_snapshot_is_independent_of_nested_caller_changes(self):
        desired = {'preset': {'materials': ['Platinum']}}
        self.config._save_cfg(desired)
        desired['preset']['materials'].append('Painite')
        self.config.flush_config()
        self.assertEqual(self.disk(), {'preset': {'materials': ['Platinum']}})

    def test_fresh_directory_is_created_without_changing_settings_location(self):
        path = self.root / 'new install' / 'config.json'
        self.config.CONFIG_FILE = str(path)
        self.now += 1
        self.config._save_cfg(self.base)
        self.assertEqual(load_config(path)._load_cfg(), self.base)
        self.assertEqual(self.disk(), self.base)

    def test_template_defaults_remain_available_on_first_launch(self):
        path = self.root / 'first-launch.json'
        Path(str(path) + '.template').write_text(json.dumps(self.base), encoding='utf-8')
        fresh = load_config(path)
        self.assertEqual(fresh._load_cfg(), self.base)
        fresh.update_config_value('language', 'de')
        fresh.flush_config()
        self.assertEqual(load_config(path)._load_cfg(), dict(self.base, language='de'))

    def run_overlapping(self, operation):
        entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
        replace = self.config.os.replace
        self.config._save_throttle_seconds = 0
        failures = []

        def delayed_replace(source, destination):
            if threading.current_thread().name == 'first-save':
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('test did not release first save')
            replace(source, destination)

        def worker(first):
            try:
                if not first:
                    second_started.set()
                operation(first)
            except BaseException as error:
                failures.append(error)

        first = threading.Thread(target=worker, args=(True,), name='first-save', daemon=True)
        second = threading.Thread(target=worker, args=(False,), name='second-save', daemon=True)
        with patch.object(self.config.os, 'replace', side_effect=delayed_replace), \
                patch.object(self.config.log, 'exception') as errors:
            try:
                first.start()
                self.assertTrue(entered.wait(3))
                second.start()
                self.assertTrue(second_started.wait(3))
                acquired = self.config._config_lock.acquire(blocking=False)
                if acquired:
                    self.config._config_lock.release()
                self.assertFalse(acquired)
            finally:
                release.set()
                first.join(5)
                if second.ident is not None:
                    second.join(5)
            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(failures, [])
            errors.assert_not_called()

    def test_older_overlapping_save_cannot_replace_newer_save(self):
        self.run_overlapping(lambda first: self.config._save_cfg({'value': 'older' if first else 'newer'}))
        self.assertEqual(self.disk(), {'value': 'newer'})
        self.assertEqual(self.config._load_cfg(), {'value': 'newer'})
        self.assert_no_temporary_files()

    def test_overlapping_key_updates_preserve_both_changes(self):
        self.run_overlapping(lambda first: self.config.update_config_value('first' if first else 'second', True))
        self.assertEqual(self.disk(), dict(self.base, first=True, second=True))

    def test_flush_waits_for_in_progress_save(self):
        self.run_overlapping(lambda first: self.config._save_cfg({'value': 'keep'}) if first
                             else self.config.flush_config())
        self.assertEqual(self.disk(), {'value': 'keep'})

    def test_process_exit_before_replacement_leaves_previous_settings_intact(self):
        before = self.path.read_bytes()
        code = '''
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location('config_test', sys.argv[1])
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)
config.CONFIG_FILE = sys.argv[2]
config.os.replace = lambda *args: os._exit(17)
config._save_cfg({'interrupted': True})
'''
        result = subprocess.run([sys.executable, '-B', '-c', code, str(ROOT / 'app/config.py'), str(self.path)],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(load_config(self.path)._load_cfg(), self.base)

    def test_voiceattack_text_write_and_existing_fallback_are_preserved(self):
        path = self.root / 'ttsSpeaking.txt'
        self.config._atomic_write_text(str(path), '1')
        self.assertEqual(path.read_text(), '1')
        with patch.object(self.config.os, 'replace', side_effect=PermissionError('locked')), \
                self.assertLogs(self.config.log, 'ERROR'):
            self.config._atomic_write_text(str(path), '0')
        self.assertEqual(path.read_text(), '0')


if __name__ == '__main__':
    unittest.main()

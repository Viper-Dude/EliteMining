"""Isolate settings for route checks, including direct config saves."""

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


def _mtime(path):
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None


@contextmanager
def isolated_route_config():
    real_config = Path(__file__).resolve().parents[1] / "app" / "config.json"
    before = _mtime(real_config)
    import config

    with TemporaryDirectory() as folder:
        temp_config = Path(folder) / "config.json"
        temp_config.write_text("{}", encoding="utf-8")
        with patch.multiple(
            config, CONFIG_FILE=str(temp_config), _cached_config={}, _cache_dirty=False,
            _last_load_time=0, _last_save_time=0,
        ):
            try:
                yield
            finally:
                if _mtime(real_config) != before:
                    raise AssertionError("app/config.json changed during the route checks")

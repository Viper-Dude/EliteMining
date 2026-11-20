"""
Logging setup for EliteMining.

The installer version writes one timestamped log file per session and keeps
the last 15. The dev run configures its own rotating log in main.py.
"""

import os
import sys
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s [%(threadName)s]: %(message)s'


def setup_logging(force_enable: bool = False) -> Optional[str]:
    """
    Set up logging for the installer version of EliteMining.

    Creates a timestamped log file per session and keeps the last 15 sessions.
    Only activates when running as a frozen executable (installer version).

    Args:
        force_enable: If True, enable logging even in development mode (for testing)

    Returns:
        str: Path to the log file if logging was set up, None otherwise
    """
    # Only enable logging for frozen executables (installer version) or if forced
    if not force_enable and not getattr(sys, 'frozen', False):
        return None

    try:
        # Determine log directory (AppData/Local/EliteMining/logs)
        if sys.platform == 'win32':
            app_data = os.getenv('LOCALAPPDATA', os.path.expanduser('~'))
            log_dir = Path(app_data) / 'EliteMining' / 'logs'
        else:
            log_dir = Path.home() / '.elitemining' / 'logs'

        # Create log directory if it doesn't exist
        log_dir.mkdir(parents=True, exist_ok=True)

        # Generate timestamped log filename
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        log_file = log_dir / f'elitemining_{timestamp}.log'

        # Clean up old logs (keep last 15)
        _cleanup_old_logs(log_dir, keep_count=15)

        handlers = [logging.FileHandler(log_file, encoding='utf-8')]
        # The windowed exe has no console (sys.stdout is None)
        if sys.stdout is not None:
            handlers.append(logging.StreamHandler(sys.stdout))

        logging.basicConfig(
            level=logging.INFO,  # INFO level - skip verbose DEBUG messages
            format=LOG_FORMAT,
            handlers=handlers
        )

        # Silence noisy third-party loggers
        logging.getLogger('matplotlib').setLevel(logging.WARNING)
        logging.getLogger('PIL').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)

        # Without a console, traceback.print_exc() and other stderr output would be
        # lost. stdout stays unredirected: print() volume is too high for the log.
        if sys.stderr is None:
            sys.stderr = _LoggerWriter(logging.getLogger('stderr'), logging.ERROR)
            logging.captureWarnings(True)

        logging.info("="*60)
        logging.info("EliteMining Logging Started")
        logging.info(f"Version: {_get_version()}")
        logging.info(f"Log file: {log_file}")
        logging.info(f"Python version: {sys.version}")
        logging.info(f"Platform: {sys.platform}")
        logging.info("="*60)

        print(f"[LOGGING] Session log: {log_file}")

        return str(log_file)

    except Exception as e:
        # If logging setup fails, don't crash the app
        print(f"Warning: Could not set up logging: {e}")
        return None


def install_exception_hooks() -> None:
    """Log uncaught exceptions from the main thread, background threads and Tk callbacks."""
    import tkinter

    crash_log = logging.getLogger('EliteMining.Uncaught')
    prev_sys_hook = sys.excepthook
    prev_thread_hook = threading.excepthook
    prev_tk_report = tkinter.Tk.report_callback_exception

    def _console_available():
        # When stderr is redirected into the log, the default hooks would log it twice
        return sys.stderr is not None and not isinstance(sys.stderr, _LoggerWriter)

    def _sys_hook(exc_type, exc_value, exc_tb):
        crash_log.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        if _console_available():
            prev_sys_hook(exc_type, exc_value, exc_tb)

    def _thread_hook(args):
        if args.exc_type is not SystemExit:
            name = args.thread.name if args.thread else 'unknown'
            crash_log.error(f"Unhandled exception in thread {name}",
                            exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        if _console_available():
            prev_thread_hook(args)

    def _tk_report(self, exc_type, exc_value, exc_tb):
        crash_log.error("Unhandled exception in Tk callback", exc_info=(exc_type, exc_value, exc_tb))
        if _console_available():
            prev_tk_report(self, exc_type, exc_value, exc_tb)

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook
    tkinter.Tk.report_callback_exception = _tk_report


def _cleanup_old_logs(log_dir: Path, keep_count: int = 15) -> None:
    """
    Remove old log files, keeping only the most recent ones.

    Args:
        log_dir: Directory containing log files
        keep_count: Number of most recent log files to keep
    """
    try:
        # Find all elitemining log files
        log_files = sorted(
            log_dir.glob('elitemining_*.log'),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        # Delete old logs beyond keep_count
        for old_log in log_files[keep_count:]:
            try:
                old_log.unlink()
                print(f"Deleted old log: {old_log.name}")
            except Exception as e:
                print(f"Could not delete old log {old_log.name}: {e}")

    except Exception as e:
        print(f"Warning: Could not clean up old logs: {e}")


def _get_version() -> str:
    """Get the application version."""
    try:
        from version import __version__
        return __version__
    except ImportError:
        return "Unknown"


class _LoggerWriter:
    """File-like stand-in for a missing sys.stderr that writes each chunk to a logger."""
    encoding = 'utf-8'
    errors = 'replace'

    def __init__(self, logger, level):
        self._logger = logger
        self._level = level
        self._local = threading.local()

    def write(self, message):
        """Write message to log."""
        if not message:
            return 0
        # A failing log handler reports through sys.stderr; drop that to avoid recursion
        if message.strip() and not getattr(self._local, 'busy', False):
            self._local.busy = True
            try:
                self._logger.log(self._level, message.rstrip())
            except Exception:
                pass
            finally:
                self._local.busy = False
        return len(message)

    def flush(self):
        """Flush buffer (required for file-like object)."""
        pass

    def isatty(self):
        """Return False to indicate this is not a terminal."""
        return False

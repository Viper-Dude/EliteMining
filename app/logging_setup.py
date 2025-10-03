"""
Logging setup for EliteMining installer version.

Creates per-session log files with timestamps, automatic rotation,
and cleanup of old logs. Only active when running as packaged executable.
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional


def setup_logging(force_enable: bool = False) -> Optional[str]:
    """
    Set up logging for the installer version of EliteMining.
    
    Creates timestamped log files, rotates at 2MB, keeps last 15 sessions.
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
        
        # Preserve original stdout/stderr before redirecting
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        # Configure logging (using original stdout before we replace it)
        logging.basicConfig(
            level=logging.INFO,  # INFO level - skip verbose DEBUG messages
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(original_stdout)  # Use original stdout
            ]
        )
        
        # Silence noisy third-party loggers
        logging.getLogger('matplotlib').setLevel(logging.WARNING)
        logging.getLogger('PIL').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        
        # NOTE: stdout/stderr redirection disabled to prevent issues
        # Print statements will NOT be logged, but app will be stable
        # sys.stdout = _LoggerWriter(logging.info)
        # sys.stderr = _LoggerWriter(logging.error)
        
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
    """
    Redirect print() statements to logging.
    """
    def __init__(self, log_func):
        self.log_func = log_func
        self.buffer = []
    
    def write(self, message):
        """Write message to log."""
        try:
            if message and message.strip():
                self.log_func(message.rstrip())
        except Exception:
            # Silently ignore errors during logging to prevent recursion
            pass
    
    def flush(self):
        """Flush buffer (required for file-like object)."""
        pass
    
    def isatty(self):
        """Return False to indicate this is not a terminal."""
        return False

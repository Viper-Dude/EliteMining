"""
Event-driven file monitoring system for EliteMining
Replaces constant polling with efficient file change detection
"""

import os
import time
import threading
from typing import Callable, Optional, Dict, Any
from pathlib import Path

# Try to import watchdog, fall back to polling if not available
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = object  # Dummy base class for fallback
    print("[FileWatcher] Watchdog not available, using optimized polling fallback")


def _is_elite_file(file_path: str) -> bool:
    """Check if file is an Elite Dangerous file we care about"""
    file_name = os.path.basename(file_path).lower()
    if file_name.startswith("journal.") and file_name.endswith(".log"):
        return True
    return file_name in ("status.json", "cargo.json", "market.json", "outfitting.json", "navroute.json")


class EliteFileHandler(FileSystemEventHandler):
    """Handles file system events for Elite Dangerous files"""

    def __init__(self, callback: Callable[[str], None]):
        super().__init__()
        self.callback = callback
        self.last_event_time = {}
        self.debounce_delay = 0.1  # 100ms debounce for rapid file changes
        self._pending = {}
        self._lock = threading.Lock()

    def on_modified(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        if not _is_elite_file(file_path):
            return

        current_time = time.time()
        with self._lock:
            last = self.last_event_time.get(file_path)
            if last is not None and current_time - last < self.debounce_delay:
                # Elite can write a file several times in a burst. Defer instead of dropping, so the
                # final change is always handled (the callback reads the file when it fires).
                if file_path not in self._pending:
                    timer = threading.Timer(self.debounce_delay, self._fire_pending, args=(file_path,))
                    timer.daemon = True
                    self._pending[file_path] = timer
                    timer.start()
                return
            self.last_event_time[file_path] = current_time

        self._run_callback(file_path)

    def _fire_pending(self, file_path: str):
        with self._lock:
            self._pending.pop(file_path, None)
            self.last_event_time[file_path] = time.time()
        self._run_callback(file_path)

    def _run_callback(self, file_path: str):
        try:
            self.callback(file_path)
        except Exception as e:
            print(f"[FileWatcher] Error in callback for {file_path}: {e}")


class EliteFileWatcher:
    """
    Event-driven file monitoring system for Elite Dangerous files
    Uses watchdog when available, falls back to optimized polling
    """
    
    def __init__(self):
        self.observer = None
        self.polling_thread = None
        self.stop_event = threading.Event()
        self.callbacks = {}
        self.watched_directories = set()
        self.watches = {}
        self.use_watchdog = WATCHDOG_AVAILABLE
        self.last_poll_times = {}
        self.polling_interval = 2.0  # Optimized polling interval (vs 0.5s)
        
    def add_watch(self, directory: str, callback: Callable[[str], None]) -> bool:
        """
        Add a directory to watch for file changes
        
        Args:
            directory: Path to directory to watch
            callback: Function to call when files change
            
        Returns:
            bool: True if watch was added successfully
        """
        try:
            directory = str(Path(directory).resolve())
            
            if not os.path.exists(directory):
                print(f"[FileWatcher] Directory does not exist: {directory}")
                return False
            
            self.callbacks[directory] = callback
            self.watched_directories.add(directory)
            
            if self.use_watchdog and self.observer is None:
                self._start_watchdog()
            elif not self.use_watchdog and self.polling_thread is None:
                self._start_polling()
            
            if self.use_watchdog and self.observer:
                handler = EliteFileHandler(callback)
                self.watches[directory] = self.observer.schedule(handler, directory, recursive=False)
                print(f"[FileWatcher] Added watchdog watch for: {directory}")
            
            return True
            
        except Exception as e:
            print(f"[FileWatcher] Error adding watch for {directory}: {e}")
            return False
    
    def _start_watchdog(self):
        """Start the watchdog observer"""
        try:
            self.observer = Observer()
            self.observer.start()
            print("[FileWatcher] Started watchdog file monitoring")
        except Exception as e:
            print(f"[FileWatcher] Failed to start watchdog: {e}")
            print("[FileWatcher] Falling back to optimized polling")
            self.use_watchdog = False
            self._start_polling()
    
    def _start_polling(self):
        """Start optimized polling fallback"""
        if self.polling_thread is None or not self.polling_thread.is_alive():
            self.polling_thread = threading.Thread(target=self._polling_worker, daemon=True)
            self.polling_thread.start()
            print(f"[FileWatcher] Started optimized polling (every {self.polling_interval}s)")
    
    def _polling_worker(self):
        """Optimized polling worker thread"""
        file_mtimes = {}
        
        while not self.stop_event.is_set():
            try:
                for directory in list(self.watched_directories):
                    if directory not in self.callbacks:
                        continue
                        
                    callback = self.callbacks[directory]
                    
                    try:
                        # Check for Elite files in directory
                        for file_name in os.listdir(directory):
                            file_path = os.path.join(directory, file_name)
                            
                            if not os.path.isfile(file_path):
                                continue
                            
                            if not _is_elite_file(file_path):
                                continue
                            
                            try:
                                current_mtime = os.path.getmtime(file_path)
                                
                                if file_path not in file_mtimes:
                                    file_mtimes[file_path] = current_mtime
                                    continue
                                
                                if current_mtime > file_mtimes[file_path]:
                                    file_mtimes[file_path] = current_mtime
                                    callback(file_path)
                                    
                            except (OSError, FileNotFoundError):
                                # File might have been deleted or is locked
                                continue
                                
                    except (OSError, FileNotFoundError):
                        # Directory might not exist anymore
                        continue
                
                # Sleep for polling interval
                self.stop_event.wait(self.polling_interval)
                
            except Exception as e:
                print(f"[FileWatcher] Polling error: {e}")
                self.stop_event.wait(1.0)  # Wait before retrying
    
    def remove_watch(self, directory: str):
        """Remove a directory watch"""
        directory = str(Path(directory).resolve())
        
        if directory in self.callbacks:
            del self.callbacks[directory]
        
        if directory in self.watched_directories:
            self.watched_directories.remove(directory)

        watch = self.watches.pop(directory, None)
        if watch is not None and self.observer:
            try:
                self.observer.unschedule(watch)
            except Exception as e:
                print(f"[FileWatcher] Error unscheduling watch for {directory}: {e}")
        
        print(f"[FileWatcher] Removed watch for: {directory}")
    
    def stop(self):
        """Stop the file watcher"""
        self.stop_event.set()
        
        if self.observer:
            try:
                self.observer.stop()
                self.observer.join(timeout=5.0)
                print("[FileWatcher] Stopped watchdog observer")
            except Exception as e:
                print(f"[FileWatcher] Error stopping watchdog: {e}")
        
        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=5.0)
            print("[FileWatcher] Stopped polling thread")
        
        self.callbacks.clear()
        self.watched_directories.clear()
        self.watches.clear()


# Global file watcher instance
_global_watcher: Optional[EliteFileWatcher] = None


def get_file_watcher() -> EliteFileWatcher:
    """Get the global file watcher instance"""
    global _global_watcher
    if _global_watcher is None:
        _global_watcher = EliteFileWatcher()
    return _global_watcher


def cleanup_file_watcher():
    """Clean up the global file watcher"""
    global _global_watcher
    if _global_watcher:
        _global_watcher.stop()
        _global_watcher = None
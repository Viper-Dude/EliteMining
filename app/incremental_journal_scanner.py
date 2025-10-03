"""
Incremental Journal Scanner

Scans only new journal entries since last run, with fallback to recent journals.
"""

import os
import glob
from datetime import datetime, timedelta
from typing import Optional, Callable, List, Tuple
import logging

from journal_parser import JournalParser
from user_database import UserDatabase
from journal_scan_state import JournalScanState

log = logging.getLogger(__name__)


class IncrementalJournalScanner:
    """Scans journals incrementally since last run"""
    
    def __init__(self, journal_dir: str, user_db: UserDatabase):
        """
        Initialize incremental scanner
        
        Args:
            journal_dir: Path to Elite Dangerous journal directory
            user_db: User database instance
        """
        self.journal_dir = journal_dir
        self.user_db = user_db
        self.parser = JournalParser(journal_dir, user_db)
        self.state = JournalScanState()
    
    def scan_new_entries(self, 
                        progress_callback: Optional[Callable[[int, int, str], None]] = None,
                        fallback_days: int = 7) -> Tuple[int, int]:
        """
        Scan new journal entries since last run
        
        Args:
            progress_callback: Optional callback(files_processed, total_files, current_file)
            fallback_days: Days to scan if state is missing/stale
            
        Returns:
            Tuple of (files_processed, events_processed)
        """
        # Get journals to scan
        journals_to_scan = self._get_journals_to_scan(fallback_days)
        
        if not journals_to_scan:
            log.info("No new journals to scan")
            return (0, 0)
        
        log.info(f"Found {len(journals_to_scan)} journal file(s) to scan")
        
        files_processed = 0
        events_processed = 0
        
        for i, journal_path in enumerate(journals_to_scan):
            # Check if this is the last processed file (resume from position)
            start_position = 0
            if journal_path == self.state.get_last_journal_file():
                start_position = self.state.get_last_file_position()
                log.info(f"Resuming from position {start_position} in {os.path.basename(journal_path)}")
            
            # Process journal
            events = self._process_journal_file(journal_path, start_position)
            events_processed += events
            files_processed += 1
            
            # Update progress
            if progress_callback:
                progress_callback(i + 1, len(journals_to_scan), os.path.basename(journal_path))
            
            # Save state after each file
            file_size = os.path.getsize(journal_path)
            self.state.save_state(journal_path, file_size)
        
        log.info(f"Incremental scan complete: {files_processed} files, {events_processed} events")
        return (files_processed, events_processed)
    
    def _get_journals_to_scan(self, fallback_days: int) -> List[str]:
        """
        Get list of journal files to scan
        
        Args:
            fallback_days: Days to scan if state is stale
            
        Returns:
            List of journal file paths in chronological order
        """
        # Get all journal files
        pattern = os.path.join(self.journal_dir, "Journal.*.log")
        all_journals = sorted(glob.glob(pattern))
        
        if not all_journals:
            log.warning(f"No journal files found in {self.journal_dir}")
            return []
        
        last_journal = self.state.get_last_journal_file()
        
        # If no state exists (new install), scan ALL journals to build complete database
        if not last_journal:
            log.info("No previous state found (new install), scanning ALL journals")
            return all_journals
        
        # If state is stale (>30 days old), scan recent journals as safety fallback
        if self.state.is_state_stale(30):
            log.info(f"State is stale, scanning last {fallback_days} days")
            return self._get_recent_journals(all_journals, fallback_days)
        
        # Check if last journal file still exists
        if not os.path.exists(last_journal):
            log.warning(f"Last processed journal not found: {last_journal}")
            return self._get_recent_journals(all_journals, fallback_days)
        
        # Find journals newer than or equal to last processed
        try:
            last_index = all_journals.index(last_journal)
            # Include last journal (to resume from position) and all newer ones
            new_journals = all_journals[last_index:]
            log.info(f"Found {len(new_journals)} journal(s) to scan (including resume)")
            return new_journals
        except ValueError:
            log.warning(f"Last processed journal not in current list: {last_journal}")
            return self._get_recent_journals(all_journals, fallback_days)
    
    def _get_recent_journals(self, all_journals: List[str], days: int) -> List[str]:
        """
        Get journals from the last N days
        
        Args:
            all_journals: All available journal files
            days: Number of days to look back
            
        Returns:
            List of recent journal files
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        recent = []
        
        for journal in all_journals:
            try:
                # Get file modification time
                mtime = os.path.getmtime(journal)
                file_date = datetime.fromtimestamp(mtime)
                
                if file_date >= cutoff_date:
                    recent.append(journal)
            except Exception as e:
                log.error(f"Failed to check journal file date: {e}")
        
        log.info(f"Found {len(recent)} journal file(s) from last {days} days")
        return recent
    
    def _process_journal_file(self, journal_path: str, start_position: int = 0) -> int:
        """
        Process a single journal file from given position
        
        Args:
            journal_path: Path to journal file
            start_position: Byte position to start reading from
            
        Returns:
            Number of relevant events processed
        """
        events_processed = 0
        
        try:
            with open(journal_path, 'r', encoding='utf-8') as f:
                # Skip to start position
                if start_position > 0:
                    f.seek(start_position)
                
                current_system = None
                
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        import json
                        event = json.loads(line)
                        event_type = event.get('event', '')
                        
                        # Track current system
                        if event_type in ['FSDJump', 'Location', 'CarrierJump']:
                            current_system = event.get('StarSystem')
                        
                        # Process relevant events
                        if event_type == 'Scan':
                            self.parser.process_scan(event)
                            events_processed += 1
                        elif event_type == 'SAASignalsFound':
                            self.parser.process_saa_signals_found(event, current_system)
                            events_processed += 1
                        elif event_type in ['FSDJump', 'Location', 'CarrierJump']:
                            self.parser.process_fsd_jump(event)
                            events_processed += 1
                        
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        log.error(f"Error processing journal event: {e}")
                        continue
        
        except Exception as e:
            log.error(f"Failed to process journal file {journal_path}: {e}")
        
        return events_processed
    
    def reset_state(self):
        """Reset scanning state (force full rescan next time)"""
        self.state.reset()
        log.info("Journal scan state reset")

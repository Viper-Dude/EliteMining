"""
VoiceAttack Variables Manager
Handles reading/writing VoiceAttack variable text files and monitoring game state
"""

import os
import json
import logging
from typing import Optional

log = logging.getLogger(__name__)


class VAVariablesManager:
    """Manages VoiceAttack variable text files"""
    
    def __init__(self, vars_dir: str, journal_dir: str):
        """
        Initialize VA Variables Manager
        
        Args:
            vars_dir: Path to Variables directory
            journal_dir: Path to Elite Dangerous journal directory
        """
        self.vars_dir = vars_dir
        self.journal_dir = journal_dir
        self.last_jumps_value = None
    
    def write_variable(self, var_name: str, value: str) -> None:
        """
        Write a variable to text file
        
        Args:
            var_name: Variable name (without .txt extension)
            value: Value to write
        """
        try:
            file_path = os.path.join(self.vars_dir, f"{var_name}.txt")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(value)
            log.debug(f"VA Variable written: {var_name} = {value}")
        except Exception as e:
            log.error(f"Error writing VA variable {var_name}: {e}")
    
    def read_variable(self, var_name: str) -> Optional[str]:
        """
        Read a variable from text file
        
        Args:
            var_name: Variable name (without .txt extension)
            
        Returns:
            Variable value or None if not found
        """
        try:
            file_path = os.path.join(self.vars_dir, f"{var_name}.txt")
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
        except Exception as e:
            log.error(f"Error reading VA variable {var_name}: {e}")
        return None
    
    def update_jumps_left(self, jumps: int) -> None:
        """
        Update jumpsleft.txt variable
        
        Args:
            jumps: Number of jumps remaining (0 = at destination)
        """
        if self.last_jumps_value != jumps:
            self.write_variable("jumpsleft", str(jumps))
            self.last_jumps_value = jumps
            log.info(f"Jumps remaining: {jumps}")
    
    def initialize_jumps_left(self) -> None:
        """Initialize jumpsleft.txt by scanning current journal for active route"""
        try:
            if not self.journal_dir or not os.path.exists(self.journal_dir):
                self.update_jumps_left(0)
                return
            
            # Find most recent journal file
            journal_files = [f for f in os.listdir(self.journal_dir) 
                           if f.startswith('Journal.') and f.endswith('.log')]
            if not journal_files:
                self.update_jumps_left(0)
                return
            
            journal_files.sort(reverse=True)
            latest_journal = os.path.join(self.journal_dir, journal_files[0])
            
            # Scan backwards for most recent route event
            jumps_remaining = 0
            try:
                with open(latest_journal, 'r', encoding='utf-8') as f:
                    # Read last 50KB
                    f.seek(0, 2)
                    file_size = f.tell()
                    f.seek(max(0, file_size - 51200))
                    lines = f.readlines()
                    
                    for line in reversed(lines):
                        if not line.strip():
                            continue
                        try:
                            event = json.loads(line)
                            event_type = event.get('event')
                            
                            if event_type == 'FSDTarget':
                                jumps_remaining = event.get('RemainingJumpsInRoute', 0)
                                log.info(f"Found active route on startup: {jumps_remaining} jumps")
                                break
                            elif event_type in ['NavRouteClear', 'Docked', 'Touchdown']:
                                jumps_remaining = 0
                                break
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                log.error(f"Error reading journal for route info: {e}")
            
            self.update_jumps_left(jumps_remaining)
            
        except Exception as e:
            log.error(f"Error initializing jumpsleft: {e}")
            self.update_jumps_left(0)
    
    def poll_route_status(self) -> None:
        """Poll journal and NavRoute for route changes"""
        try:
            if not self.journal_dir or not os.path.exists(self.journal_dir):
                return
            
            # Check NavRoute.json for cleared route
            navroute_path = os.path.join(self.journal_dir, "NavRoute.json")
            if os.path.exists(navroute_path):
                try:
                    with open(navroute_path, 'r', encoding='utf-8') as f:
                        navroute_data = json.load(f)
                        route = navroute_data.get('Route', [])
                        if len(route) == 0:
                            current_value = self.read_variable("jumpsleft")
                            if current_value != "0":
                                self.update_jumps_left(0)
                                log.debug("Route cleared via NavRoute.json")
                except Exception:
                    pass
            
            # Check latest journal for FSDTarget
            journal_files = [f for f in os.listdir(self.journal_dir) 
                           if f.startswith('Journal.') and f.endswith('.log')]
            if journal_files:
                journal_files.sort(reverse=True)
                latest_journal = os.path.join(self.journal_dir, journal_files[0])
                
                try:
                    with open(latest_journal, 'r', encoding='utf-8') as f:
                        f.seek(0, 2)
                        file_size = f.tell()
                        f.seek(max(0, file_size - 5120))  # Last 5KB
                        lines = f.readlines()
                        
                        for line in reversed(lines):
                            if not line.strip():
                                continue
                            try:
                                event = json.loads(line)
                                event_type = event.get('event')
                                
                                if event_type == 'FSDTarget':
                                    jumps = event.get('RemainingJumpsInRoute')
                                    if jumps is not None:
                                        current_value = self.read_variable("jumpsleft")
                                        if current_value != str(jumps):
                                            self.update_jumps_left(jumps)
                                    break
                                elif event_type in ['NavRouteClear', 'Docked', 'Touchdown']:
                                    current_value = self.read_variable("jumpsleft")
                                    if current_value != "0":
                                        self.update_jumps_left(0)
                                    break
                            except json.JSONDecodeError:
                                continue
                except Exception:
                    pass
        
        except Exception as e:
            log.error(f"Error polling route status: {e}")

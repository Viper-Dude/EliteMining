"""
Elite Dangerous Journal Parser for EliteMining
Extracts hotspot and visited system data from journal files
"""

import os
import json
import glob
import logging
from typing import List, Dict, Any, Optional, Generator, Tuple
from datetime import datetime
import re

from user_database import UserDatabase

log = logging.getLogger("EliteMining.JournalParser")


class JournalParser:
    """Parses Elite Dangerous journal files to extract mining-relevant data"""
    
    # Canonical material name mapping - normalizes all variants to standard forms
    MATERIAL_NAME_MAP = {
        # Tritium variants
        'tritium': 'Tritium',
        'Tritium': 'Tritium',
        
    # Low Temperature Diamonds variants
    'low temperature diamonds': 'Low Temperature Diamonds',
    'Low Temperature Diamonds': 'Low Temperature Diamonds',
    'low temp diamonds': 'Low Temperature Diamonds',
    'Low Temp Diamonds': 'Low Temperature Diamonds',
    'low temp. diamonds': 'Low Temperature Diamonds',
    'Low Temp. Diamonds': 'Low Temperature Diamonds',
    'LowTemperatureDiamond': 'Low Temperature Diamonds',
    'lowtemperaturediamond': 'Low Temperature Diamonds',        # Void Opals variants
        'void opals': 'Void Opals',
        'Void Opals': 'Void Opals',
        'void opal': 'Void Opals',
        'Void opal': 'Void Opals',
        'Void Opal': 'Void Opals',
        'opal': 'Void Opals',
        'Opal': 'Void Opals',
        
        # Other materials - standard capitalization
        'alexandrite': 'Alexandrite',
        'Alexandrite': 'Alexandrite',
        'benitoite': 'Benitoite',
        'Benitoite': 'Benitoite',
        'bromellite': 'Bromellite',
        'Bromellite': 'Bromellite',
        'grandidierite': 'Grandidierite',
        'Grandidierite': 'Grandidierite',
        'monazite': 'Monazite',
        'Monazite': 'Monazite',
        'musgravite': 'Musgravite',
        'Musgravite': 'Musgravite',
        'painite': 'Painite',
        'Painite': 'Painite',
        'platinum': 'Platinum',
        'Platinum': 'Platinum',
        'rhodplumsite': 'Rhodplumsite',
        'Rhodplumsite': 'Rhodplumsite',
        'serendibite': 'Serendibite',
        'Serendibite': 'Serendibite',
        'palladium': 'Palladium',
        'Palladium': 'Palladium',
        'gold': 'Gold',
        'Gold': 'Gold',
        'osmium': 'Osmium',
        'Osmium': 'Osmium',
    }
    
    def __init__(self, journal_dir: str, user_db: Optional[UserDatabase] = None, on_hotspot_added: Optional[callable] = None):
        """Initialize the journal parser
        
        Args:
            journal_dir: Path to Elite Dangerous journal directory
            user_db: UserDatabase instance. If None, creates a new one.
            on_hotspot_added: Optional callback function called when a hotspot is added to database
        """
        self.journal_dir = journal_dir
        self.user_db = user_db or UserDatabase()
        self.on_hotspot_added = on_hotspot_added
        
        # Regex pattern to identify ring bodies from their names
        self.ring_pattern = re.compile(r'.* [A-Z]+ Ring$', re.IGNORECASE)
        
        # Dictionary to store ring information from Scan events
        # Key: (SystemAddress, RingName), Value: {'ring_class': str, 'ls_distance': float}
        self.ring_info = {}
    
    @classmethod
    def normalize_material_name(cls, material_name: str) -> str:
        """Normalize material name to canonical form
        
        Args:
            material_name: Raw material name from journal
            
        Returns:
            Normalized material name
        """
        # Try exact match first (case-insensitive)
        normalized = cls.MATERIAL_NAME_MAP.get(material_name)
        if normalized:
            return normalized
        
        # Try lowercase match
        normalized = cls.MATERIAL_NAME_MAP.get(material_name.lower())
        if normalized:
            return normalized
        
        # If not in map, return with first letter capitalized (best effort)
        return material_name.strip().capitalize()
        
    def find_journal_files(self) -> List[str]:
        """Find all journal files in the configured directory
        
        Returns:
            List of journal file paths sorted by modification time (oldest first)
        """
        if not os.path.exists(self.journal_dir):
            log.warning(f"Journal directory does not exist: {self.journal_dir}")
            return []
            
        pattern = os.path.join(self.journal_dir, "Journal.*.log")
        files = glob.glob(pattern)
        
        # Sort by modification time (oldest first) for chronological processing
        files.sort(key=os.path.getmtime)
        
        log.info(f"Found {len(files)} journal files in {self.journal_dir}")
        return files
    
    def parse_journal_file(self, file_path: str) -> Generator[Dict[str, Any], None, None]:
        """Parse a single journal file and yield events
        
        Args:
            file_path: Path to journal file
            
        Yields:
            Dictionary containing parsed journal event
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        event = json.loads(line)
                        yield event
                    except json.JSONDecodeError as e:
                        log.warning(f"Invalid JSON in {file_path}:{line_num}: {e}")
                        continue
                        
        except Exception as e:
            log.error(f"Error reading journal file {file_path}: {e}")
    
    def is_ring_body(self, body_name: str) -> bool:
        """Check if a body name represents a ring
        
        Args:
            body_name: Name of the celestial body
            
        Returns:
            True if the body is a ring
        """
        return bool(self.ring_pattern.match(body_name))
    
    def extract_system_and_body_from_ring_name(self, body_name: str) -> Tuple[Optional[str], str]:
        """Extract system name and ring designation from ring body name
        
        Args:
            body_name: Full ring body name (e.g., "Coalsack Sector RI-T c3-22 6 A Ring")
            
        Returns:
            Tuple of (system_name, ring_designation) or (None, body_name) if not parseable
        """
        # Pattern to match ring names: "System Name Body Ring"
        # Examples:
        # "Coalsack Sector RI-T c3-22 6 A Ring" -> ("Coalsack Sector RI-T c3-22", "6 A Ring")
        # "HIP 12345 A Ring" -> ("HIP 12345", "A Ring")
        
        if not self.is_ring_body(body_name):
            return None, body_name
            
        # Try to extract system name by removing the ring part
        # Ring patterns typically end with: "Number Letter Ring" or "Letter Ring"
        ring_match = re.search(r'\s+([0-9]*\s*[A-Z]+\s+Ring)$', body_name, re.IGNORECASE)
        if ring_match:
            ring_part = ring_match.group(1)
            system_name = body_name[:ring_match.start()].strip()
            return system_name, ring_part
            
        # Fallback: assume everything before the last part is the system name
        parts = body_name.split()
        if len(parts) >= 2 and parts[-1].lower() == 'ring':
            system_name = ' '.join(parts[:-2])  # Everything except "X Ring"
            ring_part = ' '.join(parts[-2:])    # "X Ring"
            return system_name, ring_part
            
        return None, body_name
    
    def process_scan(self, event: Dict[str, Any]) -> None:
        """Process Scan event to extract ring class information
        
        Args:
            event: Journal Scan event data
        """
        try:
            rings = event.get('Rings', [])
            if not rings:
                return
            
            system_address = event.get('SystemAddress')
            body_id = event.get('BodyID')
            ls_distance = event.get('DistanceFromArrivalLS')
            
            if not system_address or body_id is None:
                return
            
            # Store ring class, LS distance, radius, and mass for each ring
            for ring in rings:
                ring_name = ring.get('Name', '')
                ring_class = ring.get('RingClass', '')
                inner_radius = ring.get('InnerRad')  # In meters
                outer_radius = ring.get('OuterRad')  # In meters
                ring_mass = ring.get('MassMT')  # Mass in Megatons
                
                if ring_name and ring_class:
                    # Convert Elite's ring class to our format
                    # eRingClass_Rocky -> Rocky
                    # eRingClass_Metallic -> Metallic
                    # eRingClass_MetalRich -> Metal Rich
                    # eRingClass_Icy -> Icy
                    clean_ring_class = ring_class.replace('eRingClass_', '').replace('MetalRich', 'Metal Rich')
                    
                    # Store with key: (SystemAddress, RingName)
                    key = (system_address, ring_name)
                    self.ring_info[key] = {
                        'ring_class': clean_ring_class,
                        'ls_distance': ls_distance,
                        'inner_radius': inner_radius,
                        'outer_radius': outer_radius,
                        'ring_mass': ring_mass
                    }
                    log.debug(f"Stored ring info: {ring_name} -> Class: {clean_ring_class}, LS: {ls_distance}, Mass: {ring_mass}")
                    
        except Exception as e:
            log.error(f"Error processing Scan event: {e}")
    
    def process_saa_signals_found(self, event: Dict[str, Any], current_system: str) -> None:
        """Process SAASignalsFound event to extract hotspot data
        
        Args:
            event: Journal event data
            current_system: Current star system name
        """
        try:
            body_name = event.get('BodyName', '')
            if not self.is_ring_body(body_name):
                return
            
            # Filter out phantom rings that were removed by Frontier
            # Paesia "2 C Ring" was removed but exists in old data
            if current_system == 'Paesia' and '2 C Ring' in body_name:
                log.info(f"Skipping phantom ring (removed by Frontier): {current_system} - {body_name}")
                return
                
            signals = event.get('Signals', [])
            if not signals:
                return
                
            timestamp = event.get('timestamp', '')
            system_address = event.get('SystemAddress')
            body_id = event.get('BodyID')
            
            # Extract system name from ring body name if current_system not available
            extracted_system, ring_designation = self.extract_system_and_body_from_ring_name(body_name)
            system_name = current_system or extracted_system
            
            if not system_name:
                log.warning(f"Could not determine system name for ring: {body_name}")
                return
            
            log.debug(f"Processing ring scan: {system_name} - {body_name}")
            
            # Look up ring info from previously stored Scan event
            ring_class = None
            ls_distance = None
            inner_radius = None
            outer_radius = None
            ring_mass = None
            if system_address and body_name:
                key = (system_address, body_name)
                ring_data = self.ring_info.get(key)
                if ring_data:
                    ring_class = ring_data.get('ring_class')
                    ls_distance = ring_data.get('ls_distance')
                    inner_radius = ring_data.get('inner_radius')
                    outer_radius = ring_data.get('outer_radius')
                    ring_mass = ring_data.get('ring_mass')
                    log.debug(f"Found ring info for {body_name}: Class={ring_class}, LS={ls_distance}, Inner={inner_radius}, Outer={outer_radius}, Mass={ring_mass}")
                else:
                    # Ring info not in cache - try to get LS distance from database
                    log.debug(f"Ring info not in cache for: {key}, attempting database lookup")
                    ls_distance = self.user_db.get_ls_distance(system_name, body_name)
                    if ls_distance:
                        log.info(f"Retrieved LS distance from database: {body_name} = {ls_distance} Ls")
                    else:
                        log.warning(f"LS distance not available for {system_name} - {body_name}")
            
            # Process each signal (material hotspot)
            for signal in signals:
                signal_type = signal.get('Type', '')
                count = signal.get('Count', 0)
                
                # For ring scans, the Type field contains the material name directly
                # (e.g., "Platinum", "Monazite"), not "Material"
                if signal_type and count > 0:
                    # Use Type_Localised if available, otherwise use Type
                    raw_material_name = signal.get('Type_Localised', signal_type)
                    
                    # Normalize material name to prevent duplicates (e.g., "tritium" -> "Tritium")
                    material_name = self.normalize_material_name(raw_material_name)
                    
                    self.user_db.add_hotspot_data(
                        system_name=system_name,
                        body_name=body_name,
                        material_name=material_name,
                        hotspot_count=count,
                        scan_date=timestamp,
                        system_address=system_address,
                        body_id=body_id,
                        ring_type=ring_class,
                        ls_distance=ls_distance,
                        inner_radius=inner_radius,
                        outer_radius=outer_radius,
                        ring_mass=ring_mass
                    )
                    
                    log.debug(f"Added hotspot: {system_name} - {body_name} - {material_name} ({count})")
                    
                    # Trigger callback if provided (for UI updates)
                    if self.on_hotspot_added:
                        self.on_hotspot_added()
                    
        except Exception as e:
            log.error(f"Error processing SAASignalsFound event: {e}")
    
    def process_fsd_jump(self, event: Dict[str, Any]) -> Optional[str]:
        """Process FSDJump event to track visited systems
        
        Args:
            event: Journal event data
            
        Returns:
            System name that was jumped to
        """
        try:
            system_name = event.get('StarSystem', '')
            if not system_name:
                return None
                
            timestamp = event.get('timestamp', '')
            system_address = event.get('SystemAddress')
            star_pos = event.get('StarPos', [])
            
            coordinates = None
            if len(star_pos) >= 3:
                coordinates = (star_pos[0], star_pos[1], star_pos[2])
            
            self.user_db.add_visited_system(
                system_name=system_name,
                visit_date=timestamp,
                system_address=system_address,
                coordinates=coordinates
            )
            
            log.debug(f"Added visited system: {system_name}")
            return system_name
            
        except Exception as e:
            log.error(f"Error processing FSDJump event: {e}")
            return None
    
    def process_location(self, event: Dict[str, Any]) -> Optional[str]:
        """Process Location event (current system on game start)
        
        Args:
            event: Journal event data
            
        Returns:
            System name of current location
        """
        # Location events have the same structure as FSDJump for our purposes
        return self.process_fsd_jump(event)
    
    def parse_all_journals(self, progress_callback: Optional[callable] = None) -> Dict[str, int]:
        """Parse all journal files to populate the user database
        
        Args:
            progress_callback: Optional callback function(current_file, total_files, stats)
            
        Returns:
            Dictionary with parsing statistics
        """
        journal_files = self.find_journal_files()
        if not journal_files:
            return {'files_processed': 0, 'hotspots_found': 0, 'systems_visited': 0}
        
        stats = {
            'files_processed': 0,
            'hotspots_found': 0,
            'systems_visited': 0,
            'events_processed': 0
        }
        
        current_system = None
        
        for i, file_path in enumerate(journal_files):
            log.info(f"Processing journal file {i+1}/{len(journal_files)}: {os.path.basename(file_path)}")
            
            file_stats = {'hotspots': 0, 'visits': 0, 'events': 0}
            
            for event in self.parse_journal_file(file_path):
                stats['events_processed'] += 1
                file_stats['events'] += 1
                
                event_type = event.get('event', '')
                
                if event_type == 'FSDJump':
                    current_system = self.process_fsd_jump(event)
                    if current_system:
                        stats['systems_visited'] += 1
                        file_stats['visits'] += 1
                        
                elif event_type == 'Location':
                    current_system = self.process_location(event)
                    if current_system:
                        stats['systems_visited'] += 1
                        file_stats['visits'] += 1
                        
                elif event_type == 'CarrierJump':
                    # Fleet carrier jumps also change current system
                    carrier_system = event.get('StarSystem', '')
                    if carrier_system:
                        current_system = carrier_system
                
                elif event_type == 'Scan':
                    # Process Scan events to extract ring class information
                    self.process_scan(event)
                        
                elif event_type == 'SAASignalsFound':
                    initial_hotspots = stats['hotspots_found']
                    self.process_saa_signals_found(event, current_system)
                    # Count how many hotspots were added (all signals for rings are materials)
                    signals = event.get('Signals', [])
                    if signals and self.is_ring_body(event.get('BodyName', '')):
                        stats['hotspots_found'] += len(signals)
                        file_stats['hotspots'] += len(signals)
            
            stats['files_processed'] += 1
            
            log.info(f"File {os.path.basename(file_path)}: {file_stats['events']} events, "
                    f"{file_stats['hotspots']} hotspots, {file_stats['visits']} visits")
            
            if progress_callback:
                progress_callback(i + 1, len(journal_files), stats)
        
        log.info(f"Journal parsing complete: {stats['files_processed']} files, "
                f"{stats['events_processed']} events, {stats['hotspots_found']} hotspots, "
                f"{stats['systems_visited']} systems visited")
        
        return stats
    
    def get_recent_ring_scans(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get recent ring scans from the database
        
        Args:
            days: Number of days back to look
            
        Returns:
            List of recent hotspot data
        """
        try:
            # This would be implemented in the user database
            # For now, return empty list
            return []
        except Exception as e:
            log.error(f"Error getting recent ring scans: {e}")
            return []


def create_journal_parser_from_config(prospector_panel) -> Optional[JournalParser]:
    """Create a JournalParser instance using the configuration from prospector panel
    
    Args:
        prospector_panel: ProspectorPanel instance with journal_dir attribute
        
    Returns:
        JournalParser instance or None if journal directory not configured
    """
    journal_dir = getattr(prospector_panel, 'journal_dir', None)
    
    if not journal_dir or not os.path.exists(journal_dir):
        log.warning("Journal directory not configured or doesn't exist")
        return None
    
    return JournalParser(journal_dir)


if __name__ == "__main__":
    # Test script
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python journal_parser.py <journal_directory>")
        sys.exit(1)
        
    journal_dir = sys.argv[1]
    parser = JournalParser(journal_dir)
    
    print(f"Parsing journals from: {journal_dir}")
    
    def progress(current, total, stats):
        print(f"Progress: {current}/{total} files, "
              f"Hotspots: {stats['hotspots_found']}, "
              f"Systems: {stats['systems_visited']}")
    
    stats = parser.parse_all_journals(progress)
    print(f"Complete! Final stats: {stats}")
    
    # Show database stats
    db_stats = parser.user_db.get_database_stats()
    print(f"Database: {db_stats}")
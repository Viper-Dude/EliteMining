"""
Elite Dangerous Journal Ring Data Analyzer
Analyzes journal files to determine what ring physical properties are available
"""

import json
import glob
import os
from pathlib import Path

def analyze_journal_ring_events(journal_dir=None):
    """Analyze journal files for ring-related events and their data fields"""
    
    # Default journal directory for Windows
    if not journal_dir:
        journal_dir = os.path.expanduser("~/Saved Games/Frontier Developments/Elite Dangerous")
    
    print("ELITE DANGEROUS JOURNAL RING DATA ANALYSIS")
    print("=" * 60)
    print(f"Searching journal directory: {journal_dir}")
    
    if not os.path.exists(journal_dir):
        print("❌ Journal directory not found!")
        print("Please provide the correct path to your Elite Dangerous journal folder")
        return
    
    # Find journal files
    journal_files = glob.glob(os.path.join(journal_dir, "Journal.*.log"))
    if not journal_files:
        print("❌ No journal files found!")
        return
    
    print(f"Found {len(journal_files)} journal files")
    
    # Events that might contain ring data
    ring_related_events = {
        'FSSDiscoveryScan': [],
        'FSSBodySignals': [],
        'FSSAllBodiesFound': [],
        'SAASignalsFound': [],
        'SAAScanComplete': [],
        'Scan': [],
        'AutoScan': [],
        'DetailedSurfaceScan': []
    }
    
    # Process recent journal files (last 5 for performance)
    recent_files = sorted(journal_files)[-5:]
    print(f"Analyzing {len(recent_files)} most recent journal files...")
    
    total_events = 0
    ring_events_found = 0
    
    for journal_file in recent_files:
        print(f"\nProcessing: {os.path.basename(journal_file)}")
        
        try:
            with open(journal_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                        
                    try:
                        event = json.loads(line.strip())
                        event_type = event.get('event', '')
                        total_events += 1
                        
                        # Check for ring-related events
                        if event_type in ring_related_events:
                            ring_events_found += 1
                            
                            # Check for ring-related content
                            is_ring_related = False
                            
                            # Check for ring bodies in various fields
                            body_name = event.get('BodyName', '')
                            if body_name and 'Ring' in body_name:
                                is_ring_related = True
                            
                            # Check for ring data in Scan events
                            if event_type == 'Scan' or event_type == 'AutoScan':
                                rings = event.get('Rings', [])
                                if rings:
                                    is_ring_related = True
                            
                            # Check SAASignalsFound for ring signals
                            if event_type == 'SAASignalsFound':
                                if body_name and 'Ring' in body_name:
                                    is_ring_related = True
                            
                            if is_ring_related:
                                ring_related_events[event_type].append({
                                    'file': os.path.basename(journal_file),
                                    'line': line_num,
                                    'event': event
                                })
                                
                    except json.JSONDecodeError:
                        continue
                        
        except Exception as e:
            print(f"Error processing {journal_file}: {e}")
    
    print(f"\n" + "=" * 60)
    print("ANALYSIS RESULTS")
    print("=" * 60)
    print(f"Total events processed: {total_events:,}")
    print(f"Ring-related events found: {ring_events_found}")
    
    # Analyze each event type
    for event_type, events in ring_related_events.items():
        if events:
            print(f"\n📊 {event_type} Events ({len(events)} found):")
            
            # Analyze the structure of the first few events
            for i, event_data in enumerate(events[:3]):  # Show first 3 examples
                event = event_data['event']
                print(f"\n  Example {i+1} ({event_data['file']}, line {event_data['line']}):")
                
                # Key fields we're interested in
                interesting_fields = [
                    'BodyName', 'SystemName', 'StarSystem', 
                    'Rings', 'RingData', 'MassMT', 'Mass',
                    'InnerRadius', 'OuterRadius', 'InnerRad', 'OuterRad',
                    'Signals', 'Materials', 'RingComposition',
                    'BodyType', 'PlanetClass', 'Rings'
                ]
                
                found_fields = {}
                for field in interesting_fields:
                    if field in event:
                        found_fields[field] = event[field]
                
                if found_fields:
                    for field, value in found_fields.items():
                        if isinstance(value, list) and len(value) > 0:
                            print(f"    {field}: [{len(value)} items] {value[0] if value else 'empty'}")
                        elif isinstance(value, dict):
                            print(f"    {field}: {{...}} (dict with {len(value)} keys)")
                        else:
                            print(f"    {field}: {value}")
                else:
                    print(f"    No interesting ring fields found")
                
                # Special handling for Rings data
                if 'Rings' in event:
                    rings = event['Rings']
                    if rings and len(rings) > 0:
                        ring = rings[0]
                        print(f"    First Ring Data:")
                        for key, value in ring.items():
                            print(f"      {key}: {value}")
    
    return ring_related_events

def main():
    """Main analysis function"""
    print("JOURNAL RING DATA ANALYZER")
    print("This will analyze your Elite Dangerous journal files for ring data")
    print("including Mass, Inner Radius, and Outer Radius information.\n")
    
    # Try default journal location first
    default_journal_dir = os.path.expanduser("~/Saved Games/Frontier Developments/Elite Dangerous")
    
    if os.path.exists(default_journal_dir):
        print(f"Using default journal directory: {default_journal_dir}")
        analyze_journal_ring_events(default_journal_dir)
    else:
        print("Default journal directory not found.")
        custom_dir = input("Enter path to your Elite Dangerous journal folder: ").strip()
        if custom_dir and os.path.exists(custom_dir):
            analyze_journal_ring_events(custom_dir)
        else:
            print("Invalid directory. Please check the path and try again.")

if __name__ == "__main__":
    main()
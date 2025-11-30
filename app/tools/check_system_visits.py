"""Check actual visits to a system from journal files"""
import os
import glob
import json
import sys

def check_visits(system_name):
    journal_dir = os.path.join(os.path.expanduser('~'), 'Saved Games', 
                               'Frontier Developments', 'Elite Dangerous')
    
    all_events = []
    arrivals = []
    journal_files = sorted(glob.glob(os.path.join(journal_dir, 'Journal.*.log')))
    
    print(f"Scanning {len(journal_files)} journal files...")
    
    for jf in journal_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        if event.get('event') in ['FSDJump', 'Location', 'CarrierJump']:
                            if event.get('StarSystem') == system_name:
                                entry = {
                                    'timestamp': event.get('timestamp'),
                                    'event': event.get('event'),
                                    'file': os.path.basename(jf)
                                }
                                all_events.append(entry)
                                if event.get('event') in ['FSDJump', 'CarrierJump']:
                                    arrivals.append(entry)
                    except:
                        pass
        except:
            pass
    
    print(f"\nSystem: {system_name}")
    print(f"\n=== ALL EVENTS (including Location) ===")
    print(f"Total: {len(all_events)}")
    for v in all_events:
        print(f"  {v['timestamp']} - {v['event']} ({v['file']})")
    
    print(f"\n=== ARRIVALS ONLY (FSDJump/CarrierJump) ===")
    print(f"Total arrivals: {len(arrivals)}")
    unique_timestamps = set(v['timestamp'] for v in arrivals)
    print(f"Unique timestamps: {len(unique_timestamps)}")
    print()
    for v in arrivals:
        print(f"  {v['timestamp']} - {v['event']} ({v['file']})")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        system_name = " ".join(sys.argv[1:])
    else:
        system_name = "Col 173 Sector RR-O b37-3"
    
    check_visits(system_name)

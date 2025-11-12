import os
import json
import glob
from datetime import datetime

journal_dir = os.path.expanduser('~/Saved Games/Frontier Developments/Elite Dangerous')
journals = sorted(glob.glob(os.path.join(journal_dir, 'Journal.*.log')), key=os.path.getmtime, reverse=True)[:3]

print('Scanning recent journals for Fleet Carrier events...\n')

fc_events = []

for journal_file in journals:
    print(f"Scanning: {os.path.basename(journal_file)}")
    try:
        with open(journal_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    event = json.loads(line)
                    event_type = event.get('event')
                    
                    # Look for CarrierJump (completed jump)
                    if event_type == 'CarrierJump':
                        fc_events.append({
                            'timestamp': event['timestamp'],
                            'system': event['StarSystem'],
                            'type': 'CarrierJump'
                        })
                    
                    # Look for CarrierLocation (after jump completes)
                    elif event_type == 'CarrierLocation':
                        fc_events.append({
                            'timestamp': event['timestamp'],
                            'system': event['StarSystem'],
                            'type': 'CarrierLocation'
                        })
                    
                    # Look for CarrierJumpRequest (scheduled jump)
                    elif event_type == 'CarrierJumpRequest':
                        fc_events.append({
                            'timestamp': event['timestamp'],
                            'system': event.get('SystemName'),
                            'departure_time': event.get('DepartureTime'),
                            'type': 'CarrierJumpRequest'
                        })
                    
                    # Look for docking at FC
                    elif event_type == 'Docked' and event.get('StationType') == 'FleetCarrier':
                        fc_events.append({
                            'timestamp': event['timestamp'],
                            'system': event['StarSystem'],
                            'carrier_name': event.get('StationName'),
                            'type': 'Docked'
                        })
                    
                    # Look for location at FC
                    elif event_type == 'Location' and event.get('Docked') and event.get('StationType') == 'FleetCarrier':
                        fc_events.append({
                            'timestamp': event['timestamp'],
                            'system': event['StarSystem'],
                            'carrier_name': event.get('StationName'),
                            'type': 'Location'
                        })
                        
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        print(f"Error reading {journal_file}: {e}")

print(f"\nFound {len(fc_events)} Fleet Carrier events\n")

if fc_events:
    # Sort by timestamp (most recent first)
    fc_events.sort(key=lambda x: x['timestamp'], reverse=True)
    
    print("=" * 70)
    print("MOST RECENT FLEET CARRIER EVENT:")
    print("=" * 70)
    latest = fc_events[0]
    print(f"Type:      {latest['type']}")
    print(f"System:    {latest['system']}")
    print(f"Timestamp: {latest['timestamp']}")
    if 'carrier_name' in latest:
        print(f"Carrier:   {latest['carrier_name']}")
    if 'departure_time' in latest:
        print(f"Scheduled: {latest['departure_time']}")
    print("=" * 70)
    
    print("\nAll Fleet Carrier Events (most recent first):")
    for i, event in enumerate(fc_events[:10], 1):  # Show last 10
        print(f"\n{i}. {event['type']} - {event['system']} @ {event['timestamp']}")
        if 'carrier_name' in event:
            print(f"   Carrier: {event['carrier_name']}")
else:
    print("No Fleet Carrier events found in recent journals")

import json
import os

journal_dir = os.path.expanduser(r"~\Saved Games\Frontier Developments\Elite Dangerous")
today_file = os.path.join(journal_dir, "Journal.2026-02-03T093756.01.log")

scan_count = 0
saa_count = 0
hip_scans = []

with open(today_file, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            event_type = event.get('event', '')
            
            if event_type == 'Scan':
                scan_count += 1
                body_name = event.get('BodyName', '')
                if 'HIP 51994' in body_name:
                    hip_scans.append(body_name)
            
            elif event_type == 'SAASignalsFound':
                saa_count += 1
                body_name = event.get('BodyName', '')
                if 'HIP 51994' in body_name:
                    print(f"Found SAASignalsFound for: {body_name}")
        except:
            pass

print(f"Total Scan events: {scan_count}")
print(f"Total SAASignalsFound events: {saa_count}")
print(f"HIP 51994 Scan events: {len(hip_scans)}")
if hip_scans:
    print("HIP 51994 bodies scanned:")
    for body in hip_scans:
        print(f"  - {body}")

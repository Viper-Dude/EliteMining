import csv
import re
from pathlib import Path

reports_dir = Path(r"d:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\Reports\Mining Session")
csv_path = reports_dir / "sessions_index.csv"

rows = []
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames or []
    for row in reader:
        rows.append(row)

# Ensure total_finds column
if 'total_finds' not in fieldnames:
    fieldnames = fieldnames[:]
    # Insert after avg_quality_percent if present, otherwise append
    try:
        idx = fieldnames.index('avg_quality_percent') + 1
    except ValueError:
        idx = len(fieldnames)
    fieldnames.insert(idx, 'total_finds')

# For each row, try to find matching TXT file and parse total finds
for r in rows:
    ts = r.get('timestamp_utc', '')
    total_finds_val = ''
    if ts:
        # ts like 2025-11-05T16:32:51 -> filename part Session_2025-11-05_16-32-51
        m = re.match(r'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})', ts)
        if m:
            date_part = m.group(1)
            time_part = m.group(2).replace(':', '-')
            pattern = f"Session_{date_part}_{time_part}"
            # find file
            candidates = list(reports_dir.glob(f"{pattern}*.txt"))
            if candidates:
                txt = candidates[0].read_text(encoding='utf-8')
                tf = re.search(r'Total Material Hits:\s*(\d+)', txt)
                if not tf:
                    tf = re.search(r'Total Material Finds:\s*(\d+)', txt)
                if tf:
                    total_finds_val = tf.group(1)
                else:
                    # sum per-material lines
                    per_hits = re.findall(r'•\s*(?:Hits|Finds):\s*(\d+)', txt)
                    if per_hits:
                        total_finds_val = str(sum(int(x) for x in per_hits))
    r['total_finds'] = total_finds_val

# Write updated CSV to a temp file then replace
out_path = reports_dir / 'sessions_index.updated.csv'
with open(out_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        # Ensure all keys exist
        out = {k: r.get(k, '') for k in fieldnames}
        writer.writerow(out)

# Replace original
backup = reports_dir / 'sessions_index.csv.bak'
csv_path.replace(backup)
out_path.replace(csv_path)
print(f"Updated CSV written to {csv_path} (backup at {backup})")

"""Fleet carrier names observed in station signals and carrier statistics."""
import json
import logging
import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from journal_reader import read_complete_journal_lines

_PERSONAL = r'[A-Z0-9]{3}-[A-Z0-9]{3}'
_SQUADRON = r'[A-Z0-9]{4}'
_CALLSIGN = re.compile(f'{_PERSONAL}|{_SQUADRON}')
_SUFFIX = re.compile(rf'(?:\s+({_PERSONAL})|\s*\|\s*({_SQUADRON}))$')
_names = {}
_write_lock = threading.Lock()
log = logging.getLogger('EliteMining.CarrierNames')


def ensure_tables(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS carrier_names (
        callsign TEXT PRIMARY KEY, name TEXT NOT NULL, updated_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS carrier_journal_offsets (
        path TEXT PRIMARY KEY, offset INTEGER NOT NULL)''')


def from_signal(signal):
    if signal.get('IsStation') is not True or signal.get('SignalType') not in (
            None, 'FleetCarrier', 'SquadronCarrier'):
        return None
    text = signal.get('SignalName') or ''
    match = _SUFFIX.search(text)
    if match and text[:match.start()].strip():
        return _observation(match.group(1) or match.group(2), text[:match.start()], signal)


def _observation(callsign, name, event):
    if not name or not name.strip() or not _CALLSIGN.fullmatch(callsign or ''):
        return None
    try:
        seen = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
        seen = seen.replace(tzinfo=timezone.utc) if seen.tzinfo is None else seen
        return callsign, name, seen.astimezone(timezone.utc).isoformat(timespec='microseconds')
    except (AttributeError, KeyError, ValueError, OverflowError):
        return None


def from_journal(event):
    if event.get('event') == 'FSSSignalDiscovered':
        return from_signal(event)
    if event.get('event') == 'CarrierStats':
        return _observation(event.get('Callsign'), event.get('Name'), event)


def load_names(db_path):
    global _names
    with _write_lock, closing(sqlite3.connect(db_path)) as conn:
        _names = dict(conn.execute('SELECT callsign, name FROM carrier_names'))


def store_names(db_path, observations, checkpoint=None):
    latest = {}
    for obs in observations:
        if obs and (obs[0] not in latest or obs[2] > latest[obs[0]][2]):
            latest[obs[0]] = obs
    if not latest and checkpoint is None:
        return
    # Serialize commit and publication so a late worker cannot roll back the display.
    with _write_lock:
        changed = {}
        with closing(sqlite3.connect(db_path)) as conn, conn:
            for callsign, name, seen in latest.values():
                cursor = conn.execute('''INSERT INTO carrier_names VALUES (?, ?, ?)
                    ON CONFLICT(callsign) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at
                    WHERE excluded.updated_at > carrier_names.updated_at''', (callsign, name, seen))
                if cursor.rowcount:
                    changed[callsign] = name
            if checkpoint:
                conn.execute('INSERT OR REPLACE INTO carrier_journal_offsets VALUES (?, ?)', checkpoint)
        _names.update(changed)


def backfill(db_path, folder):
    if not folder:
        return
    with closing(sqlite3.connect(db_path)) as conn:
        offsets = dict(conn.execute('SELECT path, offset FROM carrier_journal_offsets'))
    for path in sorted(Path(folder).glob('Journal.*.log'), reverse=True):
        key = str(path.resolve())
        offset = offsets.get(key, 0)
        try:
            lines, end = read_complete_journal_lines(path, offset)
            if offset == end and not lines:
                continue
            observations = []
            for line in lines:
                if '"FSSSignalDiscovered"' in line or '"CarrierStats"' in line:
                    try:
                        observations.append(from_journal(json.loads(line)))
                    except json.JSONDecodeError:
                        continue
            store_names(db_path, observations, (key, end))
        except (OSError, sqlite3.Error):
            log.exception('Could not read carrier names from %s', path.name)


def station_display_name(row, default=''):
    raw = row.get('stationName', default)
    if not raw:
        return raw
    callsign = raw.upper() if 'carrier' in (row.get('stationType') or '').lower() else raw
    name = _names.get(callsign)
    return f'{name} ({callsign})' if name else raw

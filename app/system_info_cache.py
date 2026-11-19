"""System status (security, allegiance, government, economy, population, controlling faction
and its active states) cached from EDDN, the player's own journal and Inara.

Each row keeps the time of the report it came from; a write only replaces an older report,
and readers compare that time with Spansh's updated_at so the newest source wins.
"""
import datetime
import json
import re
import sqlite3
from typing import Dict, List, Optional

_COLUMNS = ('system_name', 'security', 'allegiance', 'government', 'economy', 'second_economy',
            'population', 'controlling_faction', 'active_states', 'updated_at')


def ensure_table(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS system_info (
            system_name TEXT PRIMARY KEY,
            security TEXT,
            allegiance TEXT,
            government TEXT,
            economy TEXT,
            second_economy TEXT,
            population INTEGER,
            controlling_faction TEXT,
            active_states TEXT,
            updated_at TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_system_info_nocase '
                 'ON system_info(system_name COLLATE NOCASE)')


def normalize_timestamp(ts) -> Optional[str]:
    """Return ts as 'YYYY-MM-DDTHH:MM:SSZ' in UTC so stored times compare as strings."""
    if not ts:
        return None
    try:
        if isinstance(ts, datetime.datetime):
            dt = ts
        else:
            dt = datetime.datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception:
        return None


def _split_camel(value: str) -> str:
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', value)


def _token(raw) -> Optional[str]:
    """'$economy_HighTech;' -> 'HighTech'; plain values pass through."""
    if not raw:
        return None
    raw = str(raw)
    if raw.startswith('$'):
        raw = raw.strip('$;').rsplit('_', 1)[-1]
    return raw or None


def _security(raw) -> Optional[str]:
    token = (_token(raw) or '').lower()
    if token in ('high', 'medium', 'low'):
        return token.capitalize()
    if token in ('anarchy', 'lawless'):
        return 'Anarchy'
    return None


def _economy(raw) -> Optional[str]:
    token = _token(raw)
    if not token or token == 'None':
        return None
    return 'Agriculture' if token == 'Agri' else _split_camel(token)


def _government(raw) -> Optional[str]:
    token = _token(raw)
    if not token or token == 'None':
        return None
    return _split_camel(token)


def _allegiance(raw) -> Optional[str]:
    if not raw or raw == 'None':
        return None
    return _split_camel(str(raw))


def order_active_states(active: List[str], leftover: Optional[str]) -> List[str]:
    """Put the faction's reported main state first when it is still active."""
    active = [s for s in active if s and s != 'None']
    if leftover in active:
        active.remove(leftover)
        active.insert(0, leftover)
    return active


def info_from_journal_event(event: Dict) -> Optional[Dict]:
    """Build a system_info row from an FSDJump, Location or CarrierJump event (journal or EDDN)."""
    system_name = event.get('StarSystem')
    updated_at = normalize_timestamp(event.get('timestamp'))
    if not system_name or not updated_at or 'SystemSecurity' not in event:
        return None

    controlling = (event.get('SystemFaction') or {}).get('Name')
    active_states = [] if not controlling else None
    factions = event.get('Factions')
    if controlling and isinstance(factions, list):
        for faction in factions:
            if faction.get('Name') == controlling:
                active = [_split_camel(a.get('State', '')) for a in faction.get('ActiveStates') or []]
                leftover = faction.get('FactionState')
                active_states = order_active_states(active, _split_camel(leftover) if leftover else None)
                break

    population = event.get('Population')
    return {
        'system_name': system_name,
        'security': _security(event.get('SystemSecurity')),
        'allegiance': _allegiance(event.get('SystemAllegiance')),
        'government': _government(event.get('SystemGovernment')),
        'economy': _economy(event.get('SystemEconomy')),
        'second_economy': _economy(event.get('SystemSecondEconomy')),
        'population': int(population) if isinstance(population, (int, float)) else None,
        'controlling_faction': controlling,
        'active_states': active_states,
        'updated_at': updated_at,
    }


def upsert(conn, info: Dict):
    """Insert info, or replace the stored row only if info comes from a newer report."""
    values = [info.get(c) for c in _COLUMNS]
    states = info.get('active_states')
    values[_COLUMNS.index('active_states')] = json.dumps(states) if states is not None else None
    updates = ', '.join(f'{c} = excluded.{c}' for c in _COLUMNS[1:])
    conn.execute(
        f'INSERT INTO system_info ({", ".join(_COLUMNS)}) VALUES ({", ".join("?" * len(_COLUMNS))}) '
        f'ON CONFLICT(system_name) DO UPDATE SET {updates} '
        f'WHERE excluded.updated_at > system_info.updated_at',
        values
    )


def upsert_powerplay(conn, rows) -> int:
    """Write system_powerplay rows (system_name, controlling_power, power_state, powers_json,
    updated_at), replacing a stored row only when the incoming report is newer.
    Returns the number of rows inserted or replaced."""
    # Stored times come in several formats (Spansh uses '2026-11-14 03:18:29+00'),
    # so compare parsed times rather than strings.
    written = 0
    for name, power, state, powers_json, updated_at in rows:
        incoming = normalize_timestamp(updated_at)
        existing = conn.execute('SELECT updated_at FROM system_powerplay WHERE system_name = ?',
                                (name,)).fetchone()
        stored = normalize_timestamp(existing[0]) if existing else None
        if stored and (not incoming or incoming <= stored):
            continue
        conn.execute(
            'INSERT OR REPLACE INTO system_powerplay '
            '(system_name, controlling_power, power_state, powers, updated_at) VALUES (?, ?, ?, ?, ?)',
            (name, power, state, powers_json, incoming or updated_at))
        written += 1
    return written


def store(db_path: str, info: Dict) -> Optional[Dict]:
    """Create the table if needed, upsert info, and return the stored (newest) row."""
    if not db_path or not info:
        return None
    with sqlite3.connect(db_path) as conn:
        ensure_table(conn)
        upsert(conn, info)
        conn.commit()
    return batch_get(db_path, [info['system_name']]).get(info['system_name'])


def batch_get(db_path: str, system_names: List[str]) -> Dict[str, Dict]:
    """Return {system_name: row} for cached systems; empty if the cache or table is missing."""
    if not db_path or not system_names:
        return {}
    try:
        placeholders = ','.join('?' * len(system_names))
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                f'SELECT {", ".join(_COLUMNS)} FROM system_info '
                f'WHERE system_name COLLATE NOCASE IN ({placeholders})',
                system_names
            ).fetchall()
    except sqlite3.Error:
        return {}
    by_lower = {name.lower(): name for name in system_names}
    result = {}
    for row in rows:
        info = dict(zip(_COLUMNS, row))
        info['active_states'] = json.loads(info['active_states']) if info['active_states'] else (
            None if info['controlling_faction'] else [])
        result[by_lower.get(info['system_name'].lower(), info['system_name'])] = info
    return result

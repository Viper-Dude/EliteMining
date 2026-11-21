"""
System Finder API - Spansh API integration for system searches
Provides nearby system lookup with full server-side filtering (security, allegiance, state, etc.)
"""
import requests
from service_status import tracked_request
import logging
import sqlite3
import re
import datetime
from typing import List, Dict, Optional, Tuple

from localization import t
import system_info_cache

log = logging.getLogger(__name__)


class SystemFinderAPI:
    """Spansh API integration for system finder functionality with server-side filtering"""

    # Spansh API URLs
    SPANSH_URL = "https://spansh.co.uk/api/systems/search"
    SPANSH_STATIONS_URL = "https://spansh.co.uk/api/stations/search"

    # Request timeout
    TIMEOUT = 30

    # Maximum results to return
    MAX_RESULTS = 500

    # Power states Spansh doesn't index at all — filtered from the local EDDN cache instead
    LOCAL_ONLY_PP_STATES = ('Expansion', 'Contested')

    # Set from main.py after EDDN listener starts — enables local powerplay cache lookups
    EDDN_CACHE_PATH = None

    # Frontier's own journal/EDDN ControllingPower field abbreviates this one Power's name
    # (unlike every other Power, which is written out in full) — and Spansh's own dataset
    # uses that same abbreviated form too (confirmed via direct API query), not the full name
    # our dropdown options use. EDDN-sourced values are normalized to the full name on read
    # via this map; the reverse map below converts back to Spansh's form before sending a
    # controlling_power filter, since sending the full name silently returns zero matches.
    _POWER_NAME_ALIASES = {
        'A. Lavigny-Duval': 'Arissa Lavigny-Duval',
    }
    _POWER_NAME_ALIASES_REVERSE = {v: k for k, v in _POWER_NAME_ALIASES.items()}

    @classmethod
    def _normalize_power_name(cls, power_name: Optional[str]) -> Optional[str]:
        if not power_name:
            return power_name
        return cls._POWER_NAME_ALIASES.get(power_name, power_name)

    @classmethod
    def _is_newer(cls, candidate: str, current: str) -> bool:
        """True if candidate's ISO timestamp is later than current's. Unparseable/missing values lose."""
        if not candidate:
            return False
        if not current:
            return True
        try:
            candidate_time = datetime.datetime.fromisoformat(candidate.replace('Z', '+00:00'))
            current_time = datetime.datetime.fromisoformat(current.replace('Z', '+00:00'))
            if candidate_time.tzinfo is None:
                candidate_time = candidate_time.replace(tzinfo=datetime.timezone.utc)
            if current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=datetime.timezone.utc)
            return candidate_time > current_time
        except Exception:
            return False

    @classmethod
    def _spansh_pp_should_replace_cache(cls, spansh_entry: Dict, cached_entry: Optional[Dict]) -> bool:
        """Whether Spansh's PowerPlay entry should overwrite what's cached from EDDN.

        Two independent reasons to prefer Spansh, not just 'is it newer':
        - No cache entry at all -> always take Spansh's.
        - Cache has a real timestamp advantage (newer 'updated_at') -> take Spansh's.
        - Cache entry has no controlling_power at all (blank, not the confirmed '~none~'
          sentinel) despite a known power_state - EDDN's own PowerplayState events often omit
          ControllingPower for Unoccupied systems, since Frontier doesn't always attach a
          contesting-power hint. That's not "stale", it's incomplete, and Spansh may know the
          power name EDDN never provided - so patch it in regardless of which updated_at wins.
        """
        if not cached_entry:
            return True
        if cls._is_newer(spansh_entry.get('updated_at'), cached_entry.get('updated_at')):
            return True
        cached_power = cached_entry.get('controlling_power')
        spansh_power = spansh_entry.get('controlling_power')
        if not cached_power and cached_power != '~none~' and spansh_power:
            return True
        return False

    @classmethod
    def _batch_get_powerplay(cls, system_names: List[str]) -> Dict[str, Dict]:
        """
        Query local EDDN powerplay cache for a list of systems in one SQL call.
        Returns {system_name: {controlling_power, power_state}} for hits only.
        Falls back to empty dict if cache unavailable.
        """
        if not cls.EDDN_CACHE_PATH or not system_names:
            return {}
        try:
            placeholders = ','.join('?' * len(system_names))
            with sqlite3.connect(cls.EDDN_CACHE_PATH) as conn:
                rows = conn.execute(
                    f'SELECT system_name, controlling_power, power_state, updated_at FROM system_powerplay'
                    f' WHERE system_name IN ({placeholders}) COLLATE NOCASE',
                    system_names
                ).fetchall()
            return {
                row[0]: {'controlling_power': cls._normalize_power_name(row[1]), 'power_state': row[2], 'updated_at': row[3]}
                for row in rows if row[1] or row[2]  # keep rows with a known power OR state -
                # a blank controlling_power is expected/correct for Unoccupied, not "no data"
            }
        except Exception as e:
            log.debug(f"[SYSTEM_FINDER] EDDN powerplay batch lookup error: {e}")
            return {}

    # Timeout for best-effort enrichment calls that the user can interrupt via Stop —
    # kept short so a slow Spansh response doesn't hold up the UI past what Stop implies.
    ENRICHMENT_TIMEOUT = 10

    @classmethod
    def _query_spansh_powerplay_systems(cls, reference_system: str, max_distance: float,
                                         power: str, pp_state: str, is_cancelled=None) -> Tuple[Dict[str, Dict], bool]:
        """
        Query Spansh's systems-search for authoritative Fortified/Stronghold power/state data,
        scoped to the same reference_system + max_distance as the ring search.
        Returns ({system_name: {controlling_power, power_state}}, answered). On any failure or
        cancellation that is ({}, False) — this is a supplementary enrichment call, never
        required for the search to succeed.

        is_cancelled: optional zero-arg callable checked right before the request is sent —
        lets the caller (e.g. the user clicking Stop) skip the call entirely if it's already
        stale. Once the request is in flight it still runs to completion (or ENRICHMENT_TIMEOUT),
        since a blocking HTTP call can't be aborted mid-flight from another thread.
        """
        if is_cancelled and is_cancelled():
            log.debug("[SYSTEM_FINDER] Spansh PowerPlay enrichment skipped (search already cancelled)")
            return {}, False
        spansh_filters = cls._build_spansh_filters({'power': power, 'pp_state': pp_state})
        if not spansh_filters:
            log.debug(f"[SYSTEM_FINDER] Spansh PowerPlay enrichment skipped (no filters built for power={power!r}, pp_state={pp_state!r})")
            return {}, False

        payload = {
            'reference_system': reference_system,
            'size': cls.MAX_RESULTS,
            'sort': [{'distance': {'direction': 'asc'}}],
            'filters': spansh_filters
        }

        import time
        log.debug(f"[SYSTEM_FINDER] Spansh PowerPlay enrichment: querying {reference_system!r} (max {max_distance} LY) with filters={spansh_filters}")

        try:
            _t0 = time.time()
            response = tracked_request('spansh', requests.post, cls.SPANSH_URL, json=payload, timeout=cls.ENRICHMENT_TIMEOUT)
            log.debug(f"[SYSTEM_FINDER] Spansh PowerPlay enrichment: request took {time.time() - _t0:.1f}s")
            response.raise_for_status()
            data = response.json()
            results = data.get('results', [])
            log.debug(f"[SYSTEM_FINDER] Spansh PowerPlay enrichment: got {len(results)} raw results from Spansh")

            pp_systems = {}
            for system in results:
                if system.get('distance', 0) > max_distance:
                    continue
                system_name = system.get('name', '')
                if not system_name:
                    continue
                # Unoccupied systems have no 'controlling_power' (there is no controller) but
                # Spansh still reports the nearby/contesting power in the 'power' list - fall
                # back to that so Unoccupied rows show a power name instead of just the state.
                power = system.get('controlling_power') or (system.get('power') or [None])[0]
                pp_systems[system_name] = {
                    'controlling_power': cls._normalize_power_name(power),
                    'power_state': system.get('power_state', ''),
                    'updated_at': system.get('updated_at', ''),
                    'distance': system.get('distance', 0),
                }
            log.debug(f"[SYSTEM_FINDER] Spansh PowerPlay enrichment: {len(pp_systems)} within {max_distance} LY after distance filter")
            return pp_systems, True
        except Exception as e:
            log.debug(f"[SYSTEM_FINDER] Spansh PowerPlay enrichment failed: {e}")
            return {}, False

    @classmethod
    def _fetch_spansh_powerplay_systems(cls, reference_system: str, max_distance: float,
                                         power: str, pp_state: str, is_cancelled=None) -> Dict[str, Dict]:
        """Like _query_spansh_powerplay_systems, but returns only the systems."""
        return cls._query_spansh_powerplay_systems(
            reference_system, max_distance, power, pp_state, is_cancelled=is_cancelled)[0]

    # PowerPlay states Spansh's systems-search can filter on directly (Expansion/Contested
    # aren't in its index at all - see LOCAL_ONLY_PP_STATES).
    SPANSH_BACKED_PP_STATES = ('Exploited', 'Fortified', 'Stronghold', 'Unoccupied')

    # Merged backfill answers by (reference system, radius), so repeat and Auto searches skip Spansh
    PP_BACKFILL_CACHE_SECS = 300
    _pp_backfill_cache: Dict[tuple, tuple] = {}

    @classmethod
    def _fetch_spansh_powerplay_backfill(cls, reference_system: str, max_distance: float,
                                          is_cancelled=None) -> Dict[str, Dict]:
        """
        Query Spansh for all 4 Spansh-backed PP states (one request each, in parallel) scoped to
        reference_system/max_distance, merging results into a single {system_name: {...}} map.
        Used to backfill the PowerPlay column with Spansh's own data when no Power/PP State
        filter is active, so results aren't limited to whatever the sparse EDDN cache has.
        Empty dict on failure/cancellation for any given state - never blocks the search.
        Complete answers are reused for PP_BACKFILL_CACHE_SECS; failed or cancelled ones are not.
        """
        import time
        from concurrent.futures import ThreadPoolExecutor
        key = (reference_system.lower(), max_distance)
        now = time.monotonic()
        cached = cls._pp_backfill_cache.get(key)
        if cached and now - cached[0] < cls.PP_BACKFILL_CACHE_SECS:
            return dict(cached[1])
        if is_cancelled and is_cancelled():
            return {}

        states = cls.SPANSH_BACKED_PP_STATES
        with ThreadPoolExecutor(max_workers=len(states)) as pool:
            answers = list(pool.map(
                lambda state: cls._query_spansh_powerplay_systems(
                    reference_system, max_distance, 'Any', state, is_cancelled=is_cancelled),
                states))
        merged: Dict[str, Dict] = {}
        for state_systems, _answered in answers:
            merged.update(state_systems)
        if all(answered for _systems, answered in answers):
            for old_key, (stamp, _systems) in list(cls._pp_backfill_cache.items()):
                if now - stamp >= cls.PP_BACKFILL_CACHE_SECS:
                    cls._pp_backfill_cache.pop(old_key, None)
            cls._pp_backfill_cache[key] = (now, merged)
        return dict(merged)

    @classmethod
    def _store_powerplay_batch(cls, pp_systems: Dict[str, Dict]) -> None:
        """Persist Spansh-sourced Fortified/Stronghold controlling_power/power_state/updated_at
        into the EDDN cache's system_powerplay table, same INSERT OR REPLACE pattern as the
        Inara fetch (fetch_and_store_powerplay_from_inara). Caller has already decided which
        entries are worth writing (newer than cache, or filling a blank) — this just persists
        them so future searches/other tabs see it without re-fetching from Spansh every time.
        """
        if not cls.EDDN_CACHE_PATH or not pp_systems:
            return
        try:
            with sqlite3.connect(cls.EDDN_CACHE_PATH) as conn:
                for system_name, entry in pp_systems.items():
                    # Preserve any 'powers' list already captured from EDDN — Spansh's
                    # systems-search doesn't return the contesting powers list.
                    existing = conn.execute(
                        'SELECT powers FROM system_powerplay WHERE system_name = ?', (system_name,)
                    ).fetchone()
                    powers_json = existing[0] if existing else None
                    conn.execute(
                        'INSERT OR REPLACE INTO system_powerplay '
                        '(system_name, controlling_power, power_state, powers, updated_at) '
                        'VALUES (?, ?, ?, ?, ?)',
                        (system_name, entry.get('controlling_power', ''), entry.get('power_state', ''),
                         powers_json, entry.get('updated_at', ''))
                    )
                conn.commit()
        except Exception as e:
            log.debug(f"[POWERPLAY] Failed to persist Spansh PowerPlay batch: {e}")

    @classmethod
    def _fetch_spansh_powerplay_for_named_systems(cls, system_names: List[str], is_cancelled=None) -> Dict[str, Dict]:
        """
        Look up PowerPlay data straight from Spansh for a specific, already-known list of
        systems (no power/state filter) — one /api/systems/search call per system, since
        Spansh has no "search by name list" capability. Used to enrich Spansh-sourced ring
        search results when no Power/PP State filter is active, so the PowerPlay column
        isn't limited to whatever the EDDN cache happens to have for those systems.
        Returns {system_name: {controlling_power, power_state, updated_at}} for hits only.
        Capped at 50 systems (one request each) to avoid a request storm on large result sets —
        this is a display enrichment, not a required part of the search.

        is_cancelled: optional zero-arg callable checked before each request — lets the
        caller (e.g. the user clicking Stop) abort this loop early instead of waiting for
        up to 50 sequential requests to finish before the cancellation takes effect.
        """
        import time
        pp_data = {}
        last_call = 0.0
        truncated = system_names[:50]
        log.debug(f"[SYSTEM_FINDER] Spansh per-system PowerPlay lookup: {len(truncated)} systems to query (of {len(system_names)} total)")
        for i, system_name in enumerate(truncated):
            if is_cancelled and is_cancelled():
                log.debug(f"[SYSTEM_FINDER] Spansh per-system PowerPlay lookup cancelled at {i}/{len(truncated)}")
                break

            elapsed = time.time() - last_call
            if elapsed < 0.5:
                time.sleep(0.5 - elapsed)
            last_call = time.time()
            try:
                payload = {
                    'reference_system': system_name,
                    'size': 1,
                    'sort': [{'distance': {'direction': 'asc'}}],
                }
                log.debug(f"[SYSTEM_FINDER] Spansh call {i+1}/{len(truncated)}: POST {cls.SPANSH_URL} {payload}")
                response = tracked_request('spansh', requests.post, cls.SPANSH_URL, json=payload, timeout=cls.TIMEOUT)
                response.raise_for_status()
                results = response.json().get('results', [])
                if not results:
                    log.debug(f"[SYSTEM_FINDER]   -> no results for {system_name!r}")
                    continue
                system = results[0]
                if system.get('name', '') != system_name:
                    log.debug(f"[SYSTEM_FINDER]   -> name mismatch: asked {system_name!r}, got {system.get('name', '')!r}, skipping")
                    continue
                # Unoccupied systems have no 'controlling_power' (there is no controller) but
                # Spansh still reports the nearby/contesting power in the 'power' list - fall
                # back to that so Unoccupied rows show a power name instead of just the state.
                power = system.get('controlling_power') or (system.get('power') or [None])[0]
                controlling_power = cls._normalize_power_name(power)
                power_state = system.get('power_state', '')
                if not controlling_power and power_state not in cls.SPANSH_BACKED_PP_STATES:
                    log.debug(f"[SYSTEM_FINDER]   -> {system_name!r}: no usable PowerPlay data")
                    continue
                # Still no power at all (e.g. genuinely no PowerPlay activity nearby) — store
                # the sentinel like every other PP write path (Inara fetch, EDDN cache).
                if not controlling_power:
                    controlling_power = '~none~'
                log.debug(f"[SYSTEM_FINDER]   -> {system_name!r}: {controlling_power} / {power_state}")
                pp_data[system_name] = {
                    'controlling_power': controlling_power,
                    'power_state': power_state,
                    'updated_at': system.get('updated_at', ''),
                }
            except Exception as e:
                log.debug(f"[SYSTEM_FINDER]   -> {system_name!r}: request failed: {e}")
                continue
        log.debug(f"[SYSTEM_FINDER] Spansh per-system PowerPlay lookup: {len(pp_data)}/{len(truncated)} systems returned PowerPlay data")
        return pp_data

    @classmethod
    def _get_powerplay_from_cache(cls, system_name: str) -> Optional[Dict]:
        """Single-system EDDN powerplay cache lookup. Returns None if not cached."""
        if not cls.EDDN_CACHE_PATH:
            return None
        try:
            with sqlite3.connect(cls.EDDN_CACHE_PATH) as conn:
                row = conn.execute(
                    'SELECT controlling_power, power_state, updated_at FROM system_powerplay'
                    ' WHERE system_name = ? COLLATE NOCASE',
                    (system_name,)
                ).fetchone()
            if row and (row[0] or row[1]):
                return {'controlling_power': cls._normalize_power_name(row[0]), 'power_state': row[1], 'updated_at': row[2]}
        except Exception as e:
            log.debug(f"[SYSTEM_FINDER] EDDN powerplay lookup error: {e}")
        return None

    # Actual Inara HTML: <span class="bigger"><span class="positive">Stronghold</span></span>
    # The nested span inside "bigger" requires (?:<[^>]+>)? to skip the inner tag.
    _INARA_PP_PATTERN = re.compile(
        r'<span class="uppercase minor small">Powerplay</span>'
        r'.*?<a href="/elite/power/\d+/">([^<]+)</a>\s*<small>\(Controlling\)</small>'
        r'.*?<span class="bigger">(?:<[^>]+>)?([^<]+)</span>',
        re.DOTALL
    )

    # No controlling power: <span class="bigger">Expansion</span> or
    # <span class="bigger"><span class="minor">Unoccupied</span></span>
    _INARA_PP_NO_CONTROLLER_PATTERN = re.compile(
        r'<span class="uppercase minor small">Powerplay</span>\s*<br>\s*'
        r'<span class="bigger">(?:<[^>]+>)?([^<]+)<'
    )

    _INARA_CHALLENGE_PATTERN = re.compile(r"'([a-f0-9]{32})'")

    _INARA_ITEMPAIR_PATTERN = re.compile(
        r'<div class="itempairlabel"[^>]*>([^<]+)</div><div class="itempairvalue "\s*>(.*?)</div>', re.DOTALL)
    _INARA_TIME_PATTERN = re.compile(r'(\d{1,2}) ([A-Za-z]{3}) (\d{4}), (\d{1,2}):(\d{2})\s*(am|pm)', re.I)
    _MONTHS = {m: i for i, m in enumerate(
        ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'), 1)}

    @staticmethod
    def _inara_title(value: Optional[str]) -> Optional[str]:
        if not value or value.strip().lower() == 'none':
            return None
        return ' '.join(w[:1].upper() + w[1:] for w in value.split())

    @classmethod
    def _parse_inara_time(cls, value: Optional[str]) -> Optional[str]:
        """'18 Nov 2026, 9:04pm' (UTC on Inara) -> '2026-11-18T21:04:00Z'."""
        m = cls._INARA_TIME_PATTERN.search(value or '')
        month = cls._MONTHS.get(m.group(2).lower()) if m else None
        if not month:
            return None
        hour = int(m.group(4)) % 12 + (12 if m.group(6).lower() == 'pm' else 0)
        try:
            dt = datetime.datetime(int(m.group(3)), month, int(m.group(1)), hour, int(m.group(5)),
                                   tzinfo=datetime.timezone.utc)
        except ValueError:
            return None
        return system_info_cache.normalize_timestamp(dt)

    @classmethod
    def _parse_inara_system_page(cls, page: str, system_name: str):
        """Return (info_updated_at, system_info) from an Inara star system page.

        The header 'State' field is not the controlling faction's state, so active states are
        read from that faction's row in the minor factions table. system_info is None when the
        page carries no update time, since undated data cannot be compared with other sources.
        """
        import html as html_lib
        pairs = {label.strip(): value for label, value in cls._INARA_ITEMPAIR_PATTERN.findall(page)}

        def text(label):
            raw = pairs.get(label)
            value = html_lib.unescape(re.sub(r'<[^>]+>', '', raw)).strip() if raw else ''
            return value or None

        info_ts = cls._parse_inara_time(text('Info updated'))
        stamps = [s for s in (info_ts, cls._parse_inara_time(text('Factions updated'))) if s]
        if not stamps:
            return info_ts, None

        economies = [cls._inara_title(e) for e in (text('Economy') or '').split(' / ')]
        population = None
        pop_text = (text('Population') or '').replace(',', '').lower()
        pop_match = re.match(r'[\d.]+', pop_text)
        if pop_match:
            multiplier = 1_000_000_000 if 'billion' in pop_text else 1_000_000 if 'million' in pop_text else 1
            population = int(round(float(pop_match.group(0)) * multiplier))

        faction = text('Controlling faction')
        active_states = [] if not faction else None
        faction_id = re.search(r'href="/elite/minorfaction/(\d+)/"', pairs.get('Controlling faction') or '')
        if faction_id:
            row = re.search(r'<tr><td[^>]*><a href="/elite/minorfaction/%s/">.*?</tr>' % faction_id.group(1),
                            page, re.DOTALL)
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row.group(0), re.DOTALL) if row else []
            if len(cells) >= 5:
                active_states = [cls._inara_title(s) for s in
                                 re.findall(r'<span class="statetag[^"]*">([^<]+)</span>', cells[4])]

        return info_ts, {
            'system_name': system_name,
            'security': cls._inara_title(text('Security level')),
            'allegiance': cls._inara_title(text('Allegiance')),
            'government': cls._inara_title(text('Government')),
            'economy': economies[0] if economies else None,
            'second_economy': economies[1] if len(economies) > 1 else None,
            'population': population,
            'controlling_faction': faction,
            'active_states': active_states,
            'updated_at': min(stamps),
        }

    _INARA_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    @classmethod
    def fetch_and_store_powerplay_from_inara(cls, system_name: str) -> Optional[Dict]:
        """Fetch powerplay data for system_name from Inara and store to cache.
        Returns {'controlling_power': ..., 'power_state': ...} on success, None on failure."""
        if not cls.EDDN_CACHE_PATH:
            return None
        try:
            import urllib.parse, random
            url = f"https://inara.cz/elite/starsystem/?search={urllib.parse.quote(system_name)}"
            session = requests.Session()
            session.headers.update(cls._INARA_HEADERS)
            resp = session.get(url, timeout=10)
            html = resp.text
            # Inara bot challenge: 503 page with a base64-encoded /validatechallenge.php endpoint
            if resp.status_code == 503 or 'challenge-container' in html:
                cm = cls._INARA_CHALLENGE_PATTERN.search(html)
                if cm:
                    token = cm.group(1)
                    ts = int(datetime.datetime.utcnow().timestamp() * 1000)
                    cf = random.randint(0, 9999)
                    session.post(
                        'https://inara.cz/validatechallenge.php',
                        data=f'challenge={urllib.parse.quote(token)}&ts={ts}&cf={cf}',
                        headers={'Content-Type': 'application/x-www-form-urlencoded'},
                        timeout=10
                    )
                    resp = session.get(url, timeout=10)
                    resp.raise_for_status()
                    html = resp.text
            info_ts, info = cls._parse_inara_system_page(html, system_name)
            stored_info = None
            if info:
                try:
                    stored_info = system_info_cache.store(cls.EDDN_CACHE_PATH, info)
                except Exception as e:
                    log.debug(f"[SYSTEM_INFO] Inara store error for {system_name!r}: {e}")
            m = cls._INARA_PP_PATTERN.search(html)
            timestamp = info_ts or datetime.datetime.utcnow().isoformat()
            if m:
                controlling_power = m.group(1).strip()
                power_state = m.group(2).strip()
            else:
                m2 = cls._INARA_PP_NO_CONTROLLER_PATTERN.search(html)
                if m2:
                    controlling_power = '~none~'
                    power_state = m2.group(1).strip()
                elif len(html) > 15000:
                    # Valid system page but Powerplay section didn't match either pattern
                    controlling_power = '~none~'
                    power_state = ''
                else:
                    return None
            with sqlite3.connect(cls.EDDN_CACHE_PATH) as conn:
                # Preserve any 'powers' list already captured from EDDN — this fetch
                # only knows controlling_power/power_state, not the contesting powers list.
                existing = conn.execute(
                    'SELECT powers, controlling_power, power_state, updated_at FROM system_powerplay '
                    'WHERE system_name = ?', (system_name,)
                ).fetchone()
                if existing and info_ts and not cls._is_newer(info_ts, existing[3]):
                    # A newer report (EDDN or the player's own jump) is already stored
                    return {'controlling_power': cls._normalize_power_name(existing[1]),
                            'power_state': existing[2], 'updated_at': existing[3], 'system_info': stored_info}
                powers_json = existing[0] if existing else None
                conn.execute(
                    'INSERT OR REPLACE INTO system_powerplay '
                    '(system_name, controlling_power, power_state, powers, updated_at) '
                    'VALUES (?, ?, ?, ?, ?)',
                    (system_name, controlling_power, power_state, powers_json, timestamp)
                )
                conn.commit()
            return {'controlling_power': controlling_power, 'power_state': power_state, 'updated_at': timestamp,
                    'system_info': stored_info}
        except Exception as e:
            log.debug(f"[POWERPLAY] Inara fetch error for {system_name!r}: {e}")
            return None

    @classmethod
    def search_systems(cls, reference_system: str, filters: Dict[str, str] = None,
                       max_results: int = None, progress_callback=None, is_cancelled=None) -> List[Dict]:
        """
        Search for systems using Spansh API with server-side filtering.
        
        Args:
            reference_system: Name of the reference system
            filters: Dict of filter criteria:
                - security: 'Any' or specific value (High, Medium, Low, Anarchy)
                - allegiance: 'Any' or specific value (Federation, Empire, Alliance, Independent)
                - government: 'Any' or specific value
                - state: 'Any' or specific value (War, Boom, Bust, etc.)
                - economy: 'Any' or specific value
                - population: 'Any' or population range key
            max_results: Maximum number of results (default 100)
            progress_callback: Optional callback(current, total, message) for progress
            
        Returns:
            List of systems with full status info, sorted by distance
        """
        if is_cancelled and is_cancelled():
            return []
        if progress_callback:
            progress_callback(0, 100, t('system_finder.searching'))
        
        max_results = max_results or cls.MAX_RESULTS
        filters = filters or {}

        # Expansion/Contested aren't in Spansh's index — cast a wider net so there's a
        # reasonable pool of nearby systems to filter locally against the EDDN cache.
        pp_state = filters.get('pp_state', 'Any')
        local_only_pp = pp_state in cls.LOCAL_ONLY_PP_STATES
        # Spansh filters on the faction's leftover journal state, which can outlive the state
        # itself, so fetch a wider pool and keep only systems where it is still active.
        bgs_state = filters.get('state', 'Any')
        if bgs_state in ('Any', 'None', '-', ''):
            bgs_state = None

        # Build Spansh filter object
        spansh_filters = cls._build_spansh_filters(filters)

        # Build request payload
        payload = {
            'reference_system': reference_system,
            'size': cls.MAX_RESULTS if (local_only_pp or bgs_state) else max_results,
            'sort': [{'distance': {'direction': 'asc'}}]
        }
        
        if spansh_filters:
            payload['filters'] = spansh_filters
        
        log.info(f"[SYSTEM_FINDER] Searching near {reference_system} with filters: {filters}")
        
        try:
            if progress_callback:
                progress_callback(20, 100, t('system_finder.searching'))
            
            response = tracked_request('spansh', requests.post, cls.SPANSH_URL, json=payload, timeout=cls.TIMEOUT)
            response.raise_for_status()
            data = response.json()
            
            total_count = data.get('count', 0)
            results = data.get('results', [])
            
            log.info(f"[SYSTEM_FINDER] Spansh returned {len(results)} of {total_count} matching systems")
            
            if progress_callback:
                progress_callback(80, 100, t('system_finder.processing').format(count=len(results)))
            
            if not results:
                return []

            # Batch-fetch powerplay data from local EDDN cache for all returned systems
            system_names = [s.get('name', '') for s in results if s.get('name')]
            pp_cache = cls._batch_get_powerplay(system_names)

            # For the 4 Spansh-backed PP states, also query Spansh directly and merge in
            # whichever source has the newer 'updated_at' per system - same enrichment
            # Ring Finder's _apply_powerplay_filter does, since the EDDN cache alone is
            # often sparse/stale for systems the player hasn't personally visited.
            if pp_state in cls.SPANSH_BACKED_PP_STATES:
                power_filter = filters.get('power', 'Any')
                spansh_pp = cls._fetch_spansh_powerplay_systems(
                    reference_system, float('inf'), power_filter, pp_state, is_cancelled=is_cancelled)
                to_persist = {}
                for sys_name, entry in spansh_pp.items():
                    cached = pp_cache.get(sys_name)
                    if cls._spansh_pp_should_replace_cache(entry, cached):
                        pp_cache[sys_name] = entry
                        to_persist[sys_name] = entry
                if to_persist:
                    cls._store_powerplay_batch(to_persist)
            elif pp_state == 'Any':
                # No PP State filter active — still backfill Spansh's own Exploited/Fortified/
                # Stronghold/Unoccupied data (the 4 states Spansh reliably indexes) for rows
                # where the EDDN cache has nothing newer, mirroring Ring Finder's behavior.
                spansh_pp = cls._fetch_spansh_powerplay_backfill(
                    reference_system, float('inf'), is_cancelled=is_cancelled)
                to_persist = {}
                for sys_name, entry in spansh_pp.items():
                    if sys_name not in system_names:
                        continue
                    cached = pp_cache.get(sys_name)
                    if cls._spansh_pp_should_replace_cache(entry, cached):
                        pp_cache[sys_name] = entry
                        to_persist[sys_name] = entry
                if to_persist:
                    cls._store_powerplay_batch(to_persist)

            info_cache = system_info_cache.batch_get(cls.EDDN_CACHE_PATH, system_names)

            # Convert Spansh format to our format
            converted = []
            for system in results:
                converted.append(cls._convert_spansh_system(system, pp_cache, info_cache))

            # Expansion/Contested: Spansh can't filter on these, so filter locally against
            # whatever the EDDN cache has for these nearby systems, then trim to max_results.
            if local_only_pp:
                converted = [c for c in converted if c.get('power_state') == pp_state]
            if bgs_state:
                converted = [c for c in converted
                             if c.get('active_states') is None or bgs_state in c['active_states']]
            if local_only_pp or bgs_state:
                converted = converted[:max_results]

            if progress_callback:
                progress_callback(100, 100, t('system_finder.results_count').format(count=len(converted)))

            return converted
            
        except requests.exceptions.RequestException as e:
            log.error(f"[SYSTEM_FINDER] Spansh API error: {e}")
            raise
        except Exception as e:
            log.error(f"[SYSTEM_FINDER] Unexpected error: {e}")
            raise
    
    @classmethod
    def _build_spansh_filters(cls, filters: Dict[str, str]) -> Dict:
        """Convert our filter format to Spansh API format"""
        spansh_filters = {}
        
        # Security filter
        security = filters.get('security', 'Any')
        if security and security != 'Any':
            # Map our values to Spansh values
            security_map = {
                'High': 'High',
                'Medium': 'Medium', 
                'Low': 'Low',
                'Anarchy': 'Anarchy',
                'None': 'Anarchy'  # Unpopulated = Anarchy
            }
            if security in security_map:
                spansh_filters['security'] = {'value': security_map[security]}
        
        # Allegiance filter
        allegiance = filters.get('allegiance', 'Any')
        if allegiance and allegiance != 'Any':
            spansh_filters['allegiance'] = {'value': allegiance}
        
        # Government filter
        government = filters.get('government', 'Any')
        if government and government != 'Any':
            spansh_filters['government'] = {'value': government}
        
        # State filter - uses controlling_minor_faction_state
        state = filters.get('state', 'Any')
        if state and state != 'Any' and state != 'None' and state != '-':
            # Spansh expects array for state
            spansh_filters['controlling_minor_faction_state'] = {'value': [state]}
        
        # Economy filter - uses primary_economy
        economy = filters.get('economy', 'Any')
        if economy and economy != 'Any':
            spansh_filters['primary_economy'] = {'value': economy}
        
        # Population filter
        population = filters.get('population', 'Any')
        if population and population != 'Any':
            pop_filter = cls._build_population_filter(population)
            if pop_filter:
                spansh_filters['population'] = pop_filter

        # Powerplay — controlling power. Spansh's 'power' field lists ALL powers present/contesting
        # in the system, not just the controller, so filtering on it barely restricts results.
        # 'controlling_power' is the actual controller and is what we want to filter by.
        power = filters.get('power', 'Any')
        if power and power != 'Any':
            spansh_power = cls._POWER_NAME_ALIASES_REVERSE.get(power, power)
            spansh_filters['controlling_power'] = {'value': [spansh_power]}

        # Powerplay — system state. Spansh only indexes Unoccupied/Exploited/Fortified/Stronghold;
        # Expansion/Contested aren't in Spansh's dataset at all, so those are filtered from the
        # local EDDN cache after fetching instead (see search_systems).
        pp_state = filters.get('pp_state', 'Any')
        if pp_state and pp_state != 'Any' and pp_state not in cls.LOCAL_ONLY_PP_STATES:
            spansh_filters['power_state'] = {'value': [pp_state]}

        return spansh_filters
    
    @classmethod
    def _build_population_filter(cls, population: str) -> Optional[Dict]:
        """Convert population filter string to Spansh format"""
        # Inara-style population thresholds
        if population == 'None':
            return {'value': 0, 'comparison': '<='}
        elif population == 'Above 1':
            return {'value': 1, 'comparison': '>='}
        elif population == 'Above 10,000':
            return {'value': 10000, 'comparison': '>='}
        elif population == 'Above 100,000':
            return {'value': 100000, 'comparison': '>='}
        elif population == 'Above 1,000,000':
            return {'value': 1000000, 'comparison': '>='}
        elif population == 'Above 1,000,000,000':
            return {'value': 1000000000, 'comparison': '>='}
        elif population == 'Below 10,000':
            return {'value': 10000, 'comparison': '<'}
        elif population == 'Below 100,000':
            return {'value': 100000, 'comparison': '<'}
        elif population == 'Below 1,000,000':
            return {'value': 1000000, 'comparison': '<'}
        elif population == 'Below 1,000,000,000':
            return {'value': 1000000000, 'comparison': '<'}
        return None
    
    @staticmethod
    def _controlling_faction_states(system: Dict):
        """Return (display_state, active_states) for the controlling faction.

        Spansh's controlling_minor_faction_state comes from the journal's FactionState, which
        the game keeps reporting after a state ends; the faction's active_states list is current.
        active_states is None when Spansh has no presence data for the controlling faction.
        """
        leftover = system.get('controlling_minor_faction_state')
        controlling = system.get('controlling_minor_faction')
        presence = next((p for p in system.get('minor_faction_presences') or []
                         if controlling and p.get('name') == controlling), None)
        if presence is None:
            state = leftover if leftover and leftover != 'None' else 'Normal'
            return state, None
        active = [s for s in presence.get('active_states') or [] if s and s != 'None']
        if leftover in active:
            active.remove(leftover)
            active.insert(0, leftover)
        return (', '.join(active) if active else 'Normal'), active

    @classmethod
    def _convert_spansh_system(cls, system: Dict, pp_cache: Dict = None, info_cache: Dict = None) -> Dict:
        """Convert Spansh system format to our display format"""
        # Get economy info
        primary_economy = system.get('primary_economy') or '-'
        secondary_economy = system.get('secondary_economy')
        
        state, active_states = cls._controlling_faction_states(system)
        
        # Get controlling faction name
        faction = system.get('controlling_minor_faction') or '-'
        
        # For unpopulated systems, show 'Independent' allegiance (matches Inara)
        allegiance = system.get('allegiance')
        if not allegiance or allegiance == 'None':
            allegiance = 'Independent'  # Unpopulated systems are in Independent space
        
        population = system.get('population')
        
        system_name = system.get('name', '')

        # Powerplay — EDDN cache preferred (has controlling power + state).
        # If not cached, fall back to Spansh's own controlling_power/power_state.
        cached_pp = (pp_cache or {}).get(system_name)
        if cached_pp:
            pp_power = cached_pp['controlling_power']
            pp_state = cached_pp['power_state'] or None
            pp_updated_at = cached_pp.get('updated_at')
        else:
            pp_power = cls._normalize_power_name(system.get('controlling_power') or (system.get('power') or [None])[0])
            pp_state = system.get('power_state') or None
            pp_updated_at = system.get('updated_at') if (pp_power or pp_state) else None

        # EDDN cache only ever infers a generic 'Unoccupied' — it never emits 'Expansion'
        # or a specific controller for that case. If Spansh's own data disagrees (a real
        # controller/state exists), prefer Spansh's answer over the stale/inferred cache entry.
        if pp_power == '~none~' and (not pp_state or pp_state == 'Unoccupied'):
            spansh_state = system.get('power_state') or None
            if spansh_state and spansh_state != 'Unoccupied':
                pp_power = cls._normalize_power_name(system.get('controlling_power')) or pp_power
                pp_state = spansh_state
                pp_updated_at = None

        converted = {
            'systemName': system_name,
            'distance': system.get('distance'),
            'systemAddress': system.get('id64'),
            'coords': {
                'x': system.get('x', 0),
                'y': system.get('y', 0),
                'z': system.get('z', 0),
            },
            'security': system.get('security') or 'Anarchy',
            'allegiance': allegiance,
            'government': system.get('government') or '-',
            'state': state,
            'active_states': active_states,
            'economy': {'primary': primary_economy, 'secondary': secondary_economy},
            'population': population,
            'faction': faction,
            'power': pp_power,
            'power_state': pp_state,
            'power_updated_at': pp_updated_at,
            'info_updated_at': system.get('updated_at'),
        }
        return cls.apply_system_info(converted, (info_cache or {}).get(system_name)) or converted

    @classmethod
    def apply_system_info(cls, system: Dict, info: Optional[Dict]) -> Optional[Dict]:
        """Return a copy of a converted system with cached EDDN/journal/Inara info applied, or None
        when there is no cached info or it is not newer than what the system already shows."""
        if not info or not cls._is_newer(info.get('updated_at'), system.get('info_updated_at')):
            return None
        system = dict(system)
        if info.get('security'):
            system['security'] = info['security']
        system['allegiance'] = info.get('allegiance') or 'Independent'
        system['government'] = info.get('government') or '-'
        system['economy'] = {'primary': info.get('economy') or '-', 'secondary': info.get('second_economy')}
        if info.get('population') is not None:
            system['population'] = info['population']
        system['faction'] = info.get('controlling_faction') or '-'
        if info.get('active_states') is not None:
            system['active_states'] = list(info['active_states'])
            system['state'] = ', '.join(info['active_states']) or 'Normal'
        system['info_updated_at'] = info['updated_at']
        return system
    
    @classmethod
    def search_material_traders(cls, reference_system: str, trader_type: str,
                                max_results: int = None, progress_callback=None, is_cancelled=None) -> List[Dict]:
        """
        Search for the nearest stations with a specific material trader using Spansh API.

        Args:
            reference_system: Name of the reference system
            trader_type: 'Encoded', 'Manufactured', or 'Raw'
            max_results: Maximum number of results (default 100)
            progress_callback: Optional callback(current, total, message) for progress

        Returns:
            List of stations sorted by distance, each with system/station info

        NOTE: If results come back empty, verify the Spansh filter field name for
        material_trader against https://spansh.co.uk/api/stations/search schema,
        as it may be 'has_encoded_materials_trader' / 'has_manufactured_materials_trader' /
        'has_raw_materials_trader' boolean flags instead of a single typed field.
        """
        if is_cancelled and is_cancelled():
            return []
        if progress_callback:
            progress_callback(0, 100, t('system_finder.searching_traders'))

        max_results = max_results or cls.MAX_RESULTS

        # Map our trader type labels to Spansh API values
        trader_type_map = {
            'Encoded':       'Encoded',
            'Manufactured':  'Manufactured',
            'Raw':           'Raw',
        }
        spansh_trader_type = trader_type_map.get(trader_type, trader_type)

        payload = {
            'reference_system': reference_system,
            'size': max_results,
            'sort': [{'distance': {'direction': 'asc'}}],
            'filters': {
                'material_trader': {'value': spansh_trader_type}
            }
        }

        log.info(f"[SYSTEM_FINDER] Searching {trader_type} material traders near {reference_system}")

        try:
            if progress_callback:
                progress_callback(20, 100, t('system_finder.searching_traders'))

            response = tracked_request('spansh', requests.post, cls.SPANSH_STATIONS_URL, json=payload, timeout=cls.TIMEOUT)
            response.raise_for_status()
            data = response.json()

            total_count = data.get('count', 0)
            results = data.get('results', [])

            log.info(f"[SYSTEM_FINDER] Spansh returned {len(results)} of {total_count} material trader stations")

            if progress_callback:
                progress_callback(80, 100, t('system_finder.processing').format(count=len(results)))

            converted = [cls._convert_spansh_station(s, trader_type) for s in results]

            if progress_callback:
                progress_callback(100, 100, t('system_finder.trader_results_count').format(count=len(converted)))

            return converted

        except requests.exceptions.RequestException as e:
            log.error(f"[SYSTEM_FINDER] Spansh stations API error: {e}")
            raise
        except Exception as e:
            log.error(f"[SYSTEM_FINDER] Unexpected error in material trader search: {e}")
            raise

    @classmethod
    def _convert_spansh_station(cls, station: Dict, trader_type: str = '') -> Dict:
        """Convert Spansh station format to our display format for material traders"""
        # Derive max landing pad from pad counts
        if station.get('large_pads', 0) or station.get('has_large_pad'):
            pad_size = 'L'
        elif station.get('medium_pads', 0):
            pad_size = 'M'
        elif station.get('small_pads', 0):
            pad_size = 'S'
        else:
            pad_size = '-'

        return {
            'systemName':        station.get('system_name', ''),
            'distance':          station.get('distance'),
            'stationName':       station.get('name', ''),
            'stationType':       station.get('type') or '-',
            'landingPad':        pad_size,
            'distanceToArrival': station.get('distance_to_arrival'),
            'isPlanetary':       station.get('is_planetary', False),
            'traderType':        trader_type,
        }

    @classmethod
    def get_system_status(cls, system_name: str) -> Optional[Dict]:
        """
        Get detailed status for a single system using Spansh API.
        
        Args:
            system_name: Name of the system
            
        Returns:
            Dict with system status (security, allegiance, government, state, economy, population)
        """
        try:
            # Use Spansh search to find the system (it will be first result at 0 distance)
            payload = {
                'reference_system': system_name,
                'size': 1,
                'sort': [{'distance': {'direction': 'asc'}}]
            }
            
            response = tracked_request('spansh', requests.post, cls.SPANSH_URL, json=payload, timeout=cls.TIMEOUT)
            response.raise_for_status()
            data = response.json()
            
            results = data.get('results', [])
            if not results:
                log.warning(f"[SYSTEM_FINDER] No results for system: {system_name}")
                return None
            
            # First result should be the system itself (0 distance)
            system = results[0]
            
            # Verify it's the right system (name match)
            if system.get('name', '').lower() != system_name.lower():
                log.warning(f"[SYSTEM_FINDER] System name mismatch: {system.get('name')} != {system_name}")
                return None
            
            cached_pp = cls._get_powerplay_from_cache(system_name)
            pp_cache = {system['name']: cached_pp} if cached_pp else {}
            info_cache = system_info_cache.batch_get(cls.EDDN_CACHE_PATH, [system['name']])
            return cls._convert_spansh_system(system, pp_cache, info_cache)

        except requests.exceptions.RequestException as e:
            log.error(f"[SYSTEM_FINDER] Spansh API error for {system_name}: {e}")
            return None
        except Exception as e:
            log.error(f"[SYSTEM_FINDER] Error getting system status: {e}")
            return None
    

# Predefined filter options for UI dropdowns
SECURITY_OPTIONS = ['Any', 'High', 'Medium', 'Low', 'Anarchy']

ALLEGIANCE_OPTIONS = ['Any', 'Federation', 'Empire', 'Alliance', 'Independent', 'Pilots Federation']

GOVERNMENT_OPTIONS = [
    'Any', 'Anarchy', 'Communism', 'Confederacy', 'Cooperative', 
    'Corporate', 'Democracy', 'Dictatorship', 'Feudal', 
    'Patronage', 'Prison Colony', 'Theocracy'
]

STATE_OPTIONS = [
    'Any', 'Boom', 'Bust', 'Civil Liberty', 'Civil Unrest',
    'Civil War', 'Drought', 'Election', 'Expansion', 'Famine', 
    'Infrastructure Failure', 'Investment', 'Lockdown', 'Natural Disaster',
    'Outbreak', 'Pirate Attack', 'Public Holiday', 'Retreat', 
    'Terrorist Attack', 'War'
]

ECONOMY_OPTIONS = [
    'Any', 'Agriculture', 'Colony', 'Extraction', 'High Tech',
    'Industrial', 'Military', 'Prison', 'Refinery', 'Service',
    'Terraforming', 'Tourism'
]

# Inara-style population options
POPULATION_OPTIONS = [
    'Any', 'None', 'Above 1', 'Above 10,000', 'Above 100,000',
    'Above 1,000,000', 'Above 1,000,000,000',
    'Below 10,000', 'Below 100,000', 'Below 1,000,000', 'Below 1,000,000,000'
]

# Material trader types
MATERIAL_TRADER_OPTIONS = ['Encoded', 'Manufactured', 'Raw']

# Powerplay powers — used for "My Power" pledge dropdown
ELITE_POWERS = [
    "Select your pledge...", "Aisling Duval", "Archon Delaine",
    "Arissa Lavigny-Duval", "Denton Patreus", "Edmund Mahon",
    "Felicia Winters", "Jerome Archer", "Li Yong-Rui", "Nakato Kaine",
    "Pranav Antal", "Yuri Grom", "Zemina Torval"
]

# Power filter options for system search (includes Any)
POWER_FILTER_OPTIONS = ['Any', *ELITE_POWERS[1:]]

# Powerplay state filter options. Unoccupied/Exploited/Fortified/Stronghold are searched via
# Spansh; Expansion/Contested aren't in Spansh's index, so those search the local EDDN cache
# instead (see LOCAL_ONLY_PP_STATES / search_systems) — results limited to what's already cached.
PP_STATE_OPTIONS = [
    'Any', 'Unoccupied', 'Exploited', 'Fortified', 'Stronghold', 'Expansion', 'Contested'
]

# -*- coding: utf-8 -*-
"""
Ring Finder search pipeline: local database, Spansh and EDSM lookups.
Mixed into RingFinder (ring_finder.py); methods are unchanged from there.
"""
import logging
import math
import re
import threading
import time
from typing import Dict, List, Optional

import requests
from service_status import tracked_request

try:
    from localization import t
except Exception:
    def t(key, **kwargs):
        return key

# Same logger name as ring_finder.py so log lines keep their source
log = logging.getLogger('ring_finder')

# Spansh names Void Opal hotspots in the singular; the app and saved data use "Void Opals"
SPANSH_SIGNAL_NAMES = {'Void Opals': 'Void Opal'}
APP_SIGNAL_NAMES = {spansh: app for app, spansh in SPANSH_SIGNAL_NAMES.items()}
# Every hotspot mineral Spansh indexes, in Spansh's spelling
SPANSH_HOTSPOT_SIGNALS = [
    'Alexandrite', 'Benitoite', 'Bromellite', 'Grandidierite', 'Low Temperature Diamonds',
    'Monazite', 'Musgravite', 'Painite', 'Platinum', 'Rhodplumsite', 'Serendibite',
    'Tritium', 'Void Opal',
]


def translate_reserve_level(reserve_level) -> str:
    """Translate reserve level to localized display text
    
    Args:
        reserve_level: English reserve level from database (Pristine, Major, etc.)
        
    Returns:
        Localized reserve level text, or empty string for invalid values
    """
    if not reserve_level:
        return ''
    
    # Convert to string if needed
    reserve_level = str(reserve_level)
    
    # Map to translation keys - only valid reserve levels
    reserve_key_map = {
        'Pristine': 'reserve_pristine',
        'Major': 'reserve_major',
        'Common': 'reserve_common',
        'Low': 'reserve_low',
        'Depleted': 'reserve_depleted'
    }
    
    key = reserve_key_map.get(reserve_level)
    if key:
        return t(f'ring_finder.{key}')  # Use ring_finder prefix
    
    # If not a valid reserve level (e.g., old density data), return empty
    return ''

def translate_ring_type(ring_type: str) -> str:
    """Translate ring type to localized display text
    
    Args:
        ring_type: English ring type from database (Metallic, Rocky, Icy, Metal Rich)
        
    Returns:
        Localized ring type text
    """
    if not ring_type or ring_type == "No data":
        return ring_type
    
    # Map to translation keys
    ring_key_map = {
        'Metallic': 'metallic',
        'Rocky': 'rocky',
        'Icy': 'icy',
        'Metal Rich': 'metal_rich'
    }
    
    key = ring_key_map.get(ring_type)
    if key:
        return t(f'ring_finder.{key}')
    
    # Fallback to original value
    return ring_type


class RingFinderSearchMixin:
    """Search methods for RingFinder. Relies on RingFinder state and helpers via self."""

    def search_hotspots(self, auto_refresh=False, highlight_body=None, highlight_system=None, highlight_bodies=None, force_database=False):
        """Search for mining hotspots using reference system as center point

        Args:
            auto_refresh: DEPRECATED - use highlight_body instead
            highlight_body: Specific body/ring name to highlight (e.g., '1 A Ring')
            highlight_system: Specific system name for the body (e.g., 'Synuefe XR-H d11-45')
                           Only this exact system+ring will be highlighted green. None = no highlighting.
            highlight_bodies: List of (system, body) tuples to highlight (for multiple rapid scans)
            force_database: If True, only search local database (ignore user's data source setting)
        """
        import time as _time
        print(f"[SEARCH] search_hotspots() called at {_time.time():.1f} (force_database={force_database}, auto_refresh={auto_refresh})")

        # Save current reference system (complete name at search time)
        self._save_filter_settings()

        # Temporarily update UI radio button to show "Local" when force_database is active
        self._saved_data_source = None
        if force_database:
            self._saved_data_source = self.data_source_var.get()
            self.data_source_var.set("database")
        
        # If this is an auto-refresh (has highlight info), clear cache first to get fresh data
        if highlight_body and highlight_system:
            if hasattr(self, 'local_db') and hasattr(self.local_db, 'clear_cache'):
                self.local_db.clear_cache()
        if highlight_bodies:
            if hasattr(self, 'local_db') and hasattr(self.local_db, 'clear_cache'):
                self.local_db.clear_cache()
        
        # Store highlight info for use in _update_results (accumulate multiple highlights)
        if not hasattr(self, '_pending_highlights'):
            self._pending_highlights = set()
        
        # Add single highlight
        if highlight_body and highlight_system:
            self._pending_highlights.add((highlight_system.lower(), highlight_body))
        
        # Add multiple highlights from list
        if highlight_bodies:
            for system, body in highlight_bodies:
                if system and body:
                    self._pending_highlights.add((system.lower(), body))
        
        self._is_auto_refresh = auto_refresh  # Keep for backwards compatibility but prefer highlight_body
        
        reference_system = self.system_var.get().strip()
        
        # Update Sol distance for reference system
        self._update_sol_distance(reference_system)
        
        # Map localized UI selections back to English identifiers for queries
        material_filter_local = self.material_var.get()
        material_filter = self._ring_type_rev_map.get(material_filter_local, material_filter_local)
        specific_material_local = self.specific_material_var.get()
        specific_material = self._to_english(specific_material_local)
        
        # Convert dropdown display names to database names for SQL query
        if specific_material == "Low Temp Diamonds":
            specific_material = "Low Temperature Diamonds"
        second_material = self._active_second_material()
        if second_material == "Low Temp Diamonds":
            second_material = "Low Temperature Diamonds"
        same_ring = self.second_scope_var.get() == "ring"

        # Get confirmed_only with error handling
        try:
            confirmed_only = self.confirmed_only_var.get()
        except AttributeError:
            log.warning("Warning: confirmed_only_var not found, defaulting to False")
            confirmed_only = False
            
        max_distance = float(self.distance_var.get() or "100")
        max_results = int(self.max_results_var.get())
        
        # Auto-enable confirmed hotspots when filtering by specific material
        if not self._is_all_minerals(specific_material):
            confirmed_only = True

        if not reference_system:
            self.status_var.set(t('ring_finder.enter_reference_system'))
            return

        # Check if search criteria changed from last search and clear relevant cache
        current_search_key = f"{reference_system}_{material_filter}_{specific_material}_{max_distance}"
        if hasattr(self, '_last_search_key') and self._last_search_key != current_search_key:
            if hasattr(self, 'local_db'):
                # Clear cache entries for the previous search context
                old_system = self._last_search_key.split('_')[0] if hasattr(self, '_last_search_key') else None
                if old_system and old_system == reference_system:
                    # Same system, different criteria - clear material-specific cache
                    self.local_db.clear_cache(f"material_")
                    print(f" DEBUG: Cleared cache due to search criteria change")
        self._last_search_key = current_search_key

        # Set reference system coordinates for distance calculations (case insensitive)
        # NOTE: Coordinate lookup moved to background thread to prevent UI freeze
        self.current_system_coords = None

        # Try exact match from cached systems data (fast lookup)
        self.current_system_coords = self.systems_data.get(reference_system.lower())
        if not self.current_system_coords:
            # Try case-insensitive exact match
            for sys_name, sys_coords in self.systems_data.items():
                if reference_system.lower() == sys_name.lower():
                    self.current_system_coords = sys_coords
                    break

        # Don't do heavy lookups (DB/API) here - let background thread handle it
        # This prevents UI freeze when searching large distances

        # Get min hotspots filter (only valid for specific materials)
        min_hotspots = 1  # Default
        if not self._is_all_minerals(specific_material):
            try:
                min_hotspots = int(self.min_hotspots_var.get())
                if min_hotspots < 1:
                    min_hotspots = 1
            except (ValueError, AttributeError):
                min_hotspots = 1
        
        if second_material:
            impossible = self._impossible_mineral_search(
                material_filter, material_filter_local, specific_material, specific_material_local,
                second_material, self.second_material_var.get(), same_ring)
            if impossible:
                # Nothing can match: clear the old rows and say why instead of searching
                self._search_generation += 1
                self.results_tree.delete(*self.results_tree.get_children())
                self.status_var.set(impossible)
                if self._saved_data_source:
                    self.data_source_var.set(self._saved_data_source)
                    self._saved_data_source = None
                return

        # Keep search button clickable (it now doubles as a Stop button)
        self._search_in_progress = True
        self.search_btn.configure(text=t('ring_finder.stop'))
        self.status_var.set(t('ring_finder.searching'))
        self.new_entries_var.set("")
        
        # Capture Tkinter vars in main thread (Tkinter is not thread-safe)
        overlaps_only = self.overlaps_only_var.get()
        res_only = self.res_only_var.get()
        data_source = self.data_source_var.get()
        ring_type_only = hasattr(self, 'ring_type_only_var') and self.ring_type_only_var.get()
        pp_power_filter = self.pp_power_var.get() if hasattr(self, 'pp_power_var') else 'Any'
        pp_state_filter = self.pp_state_var.get() if hasattr(self, 'pp_state_var') else 'Any'
        # The PowerPlay column is hidden for Spansh/Both, so only Local searches fetch it
        use_spansh_pp = data_source == 'database' and self.spansh_pp_var.get()

        if pp_state_filter in ('Exploited', 'Fortified', 'Stronghold', 'Unoccupied', 'Expansion', 'Contested'):
            # Widen to 500 LY for any specific PowerPlay state. For the 4 Spansh-backed states
            # this also widens the Spansh systems-search call; for Expansion/Contested (EDDN
            # cache only, no Spansh support) it only widens the local DB query, which is cheap
            # regardless of radius - it just means scanning more of what's already been visited.
            max_distance = max(max_distance, 500.0)

        # Favourites Only: favourites live in the local DB; show all regardless of distance/result limits
        self._favourites_search = self.favourites_only_var.get()
        if self.favourites_only_var.get():
            max_distance = 200000.0
            max_results = None
            data_source = "database"

        # Spansh may stop paging once it has enough rings, unless a filter applied after the
        # fetch could still discard some of them and leave the list short
        reserve_filter = self.reserve_var.get()
        spansh_stop_at_limit = not (
            min_hotspots > 1 or self.unvisited_only_var.get()
            or (reserve_filter and reserve_filter != t('ring_finder.all_reserves'))
            or pp_power_filter != 'Any' or pp_state_filter != 'Any'
            or second_material)

        # Reuse the last Spansh rows (set after saving them to the database) for this search only
        cached_spansh = self._cached_spansh_results if self._use_cached_spansh and not second_material else None
        self._use_cached_spansh = False

        # Increment search generation to cancel any in-flight searches
        self._search_generation += 1
        current_generation = self._search_generation

        # Run search in background - pass reference system coords and max results to worker
        threading.Thread(target=self._search_worker,
                        args=(reference_system, material_filter, specific_material, confirmed_only, max_distance, self.current_system_coords, max_results, min_hotspots, overlaps_only, res_only, data_source, ring_type_only, current_generation, pp_power_filter, pp_state_filter, use_spansh_pp, spansh_stop_at_limit, force_database, cached_spansh),
                        kwargs={'second_material': second_material, 'same_ring': same_ring},
                        daemon=True).start()

    def _search_worker(self, reference_system: str, material_filter: str, specific_material: str, confirmed_only: bool, max_distance: float, reference_coords, max_results, min_hotspots: int = 1, overlaps_only: bool = False, res_only: bool = False, data_source: str = "both", ring_type_only: bool = False, search_generation: int = 0, pp_power: str = 'Any', pp_state: str = 'Any', use_spansh_pp: bool = True, spansh_stop_at_limit: bool = False, force_database: bool = False, cached_spansh=None, second_material=None, same_ring: bool = False):
        """Background worker for hotspot search.

        Writes no search state on self: coordinates, PowerPlay data and Spansh rows go to
        _complete_search, which stores them only if this search is still the current one.
        """
        try:
            # Wait for database to be ready (with timeout)
            import time
            print(f"[SEARCH] _search_worker() thread started at {time.time():.1f}")
            wait_start = time.time()
            while not self.db_ready and (time.time() - wait_start) < 5.0:
                time.sleep(0.1)
            print(f"[SEARCH] db_ready wait finished at {time.time():.1f} (waited {time.time() - wait_start:.1f}s)")

            if not self.db_ready:
                print("⚠ Database not ready, search may return incomplete results")
            
            # Check if this search was superseded by a newer one
            if search_generation != self._search_generation:
                print(f"[SEARCH] Search gen {search_generation} cancelled (current: {self._search_generation})")
                return
            
            # Check if window still exists before accessing tkinter vars
            if not self.parent.winfo_exists():
                return
            
            # Perform coordinate lookup in background thread to prevent UI freeze
            if not reference_coords:
                # Try galaxy database first
                galaxy_coords = self._get_system_coords_from_galaxy_db(reference_system)
                if galaxy_coords:
                    reference_coords = galaxy_coords
                    print(f" DEBUG: Using galaxy database coordinates for '{reference_system}'")
                else:
                    # Try visited_systems table in user database
                    try:
                        visited_coords = self.user_db._get_coordinates_from_visited_systems(reference_system)
                        if visited_coords:
                            # Convert tuple (x, y, z) to dict {'x': ..., 'y': ..., 'z': ...}
                            reference_coords = {'x': visited_coords[0], 'y': visited_coords[1], 'z': visited_coords[2]}
                    except Exception:
                        pass
                    
                    if not reference_coords:
                        # Use EDSM as final fallback
                        edsm_coords = self._get_system_coords_from_edsm(
                            reference_system, is_cancelled=lambda: search_generation != self._search_generation)
                        if edsm_coords:
                            reference_coords = edsm_coords
                
                if not reference_coords:
                    # Update UI with error message
                    self.parent.after(0, self._run_search_callback, search_generation,
                                      self.status_var.set, t('ring_finder.coords_not_found_warning').format(system=reference_system))
                    return
            
            if search_generation != self._search_generation:
                return
            print(f"[SEARCH-DEBUG] ref='{reference_system}' coords={reference_coords} systems_data={self.systems_data.get(reference_system.lower())}")
            print(f"[SEARCH] Coordinate resolution done at {time.time():.1f}, entering search dispatch")

            pp_enrichment = {}
            fetched = {}
            # Overlaps Only mode: Show only overlap entries (only works with database)
            if overlaps_only:
                if data_source == "spansh":
                    # Can't filter by overlaps on Spansh - no overlap data
                    self.parent.after(0, lambda: self.status_var.set(t('ring_finder.overlaps_requires_db')))
                    hotspots = []
                else:
                    hotspots = self._get_all_overlaps_for_search(reference_system, reference_coords, specific_material)
                    print(f" DEBUG: Overlaps Only mode - found {len(hotspots)} overlap locations")
            # RES Only mode: Show only RES site entries (only works with database)
            elif res_only:
                if data_source == "spansh":
                    # Can't filter by RES on Spansh - no RES data
                    self.parent.after(0, lambda: self.status_var.set(t('ring_finder.res_requires_db')))
                    hotspots = []
                else:
                    hotspots = self._get_all_res_for_search(reference_system, reference_coords, specific_material)
                    print(f" DEBUG: RES Only mode - found {len(hotspots)} RES locations")
            elif second_material:
                is_cancelled = lambda: search_generation != self._search_generation
                # No Spansh row reuse here: one mineral's rows must never stand in for the other's
                per_mineral = []
                for mineral in (specific_material, second_material):
                    if is_cancelled():
                        break
                    rows = self._get_hotspots(reference_system, material_filter, mineral, confirmed_only, max_distance, max_results,
                                              data_source=data_source, is_cancelled=is_cancelled,
                                              spansh_stop_at_limit=False, force_database=force_database,
                                              reference_coords=reference_coords)
                    if min_hotspots > 1:
                        rows = [h for h in rows if h.get('count', 1) >= min_hotspots]
                    per_mineral.append(rows)
                hotspots = (self._combine_mineral_results(per_mineral[0], per_mineral[1], same_ring)
                            if len(per_mineral) == 2 else [])
            else:
                hotspots = self._get_hotspots(reference_system, material_filter, specific_material, confirmed_only, max_distance, max_results, data_source=data_source, ring_type_only_active=ring_type_only,
                                               is_cancelled=lambda: search_generation != self._search_generation,
                                               spansh_stop_at_limit=spansh_stop_at_limit, force_database=force_database,
                                               reference_coords=reference_coords, cached_spansh=cached_spansh,
                                               spansh_fetched=fetched)

            # Apply PowerPlay filter using EDDN cache (local database only — Power/State
            # combos are greyed out and reset to Any for Spansh/Both data sources)
            pp_backfill = None
            if pp_power != 'Any' or pp_state != 'Any':
                if search_generation != self._search_generation:
                    print(f"[SEARCH] Search gen {search_generation} cancelled before PowerPlay filter (current: {self._search_generation})")
                    return
                hotspots, pp_enrichment = self._apply_powerplay_filter(
                    hotspots, pp_power, pp_state, reference_system, max_distance,
                    is_cancelled=lambda: search_generation != self._search_generation,
                    use_spansh=use_spansh_pp)
            else:
                # No Power/PP State filter active — the PowerPlay column is still backfilled
                # with Spansh's own data, after the rows are shown (_start_pp_backfill).
                if use_spansh_pp:
                    pp_backfill = (reference_system, max_distance)

            # Apply min hotspots filter if needed (skip for overlaps/RES only mode)
            if min_hotspots > 1 and not self._is_all_minerals(specific_material) and not overlaps_only and not res_only and not second_material:
                original_count = len(hotspots)
                hotspots = [h for h in hotspots if h.get('count', 1) >= min_hotspots]
                filtered_count = len(hotspots)
                if filtered_count < original_count:
                    print(f" DEBUG: Min hotspots filter ({min_hotspots}+): {original_count} -> {filtered_count} results")
            
            # Check if this search was superseded before updating UI
            if search_generation != self._search_generation:
                if getattr(self, '_stopped_generation', None) == search_generation:
                    # User clicked Stop (not superseded by a newer search) — show whatever
                    # was collected so far instead of discarding it.
                    print(f"[SEARCH] Search gen {search_generation} stopped by user - showing {len(hotspots)} partial result(s)")
                    self.parent.after(0, self._complete_search, search_generation, hotspots, max_results, pp_backfill,
                                      reference_coords, pp_enrichment, fetched.get('spansh'))
                else:
                    print(f"[SEARCH] Search gen {search_generation} cancelled before display (current: {self._search_generation})")
                return
            
            # Update UI in main thread
            self.parent.after(0, self._complete_search, search_generation, hotspots, max_results, pp_backfill,
                              reference_coords, pp_enrichment, fetched.get('spansh'))
            
        except Exception as e:
            error_msg = f"Search failed: {str(e)}"
            try:
                if self.parent.winfo_exists():
                    self.parent.after(0, self._run_search_callback, search_generation, self._show_error, error_msg)
            except:
                pass  # Window already destroyed
        finally:
            # Reset search button back to "Search" — but only if no newer
            # search has started in the meantime (that search's own finally will handle it).
            try:
                if self.parent.winfo_exists() and search_generation == self._search_generation:
                    self.parent.after(0, self._run_search_callback, search_generation, self._reset_search_button)
            except:
                pass  # Window already destroyed
    
    def _run_search_callback(self, search_generation, callback, *args):
        if search_generation == self._search_generation:
            callback(*args)

    def _complete_search(self, search_generation, hotspots, max_results, pp_backfill=None,
                         reference_coords=None, pp_enrichment=None, spansh_results=None):
        stopped = (getattr(self, '_stopped_generation', None) == search_generation
                   and self._search_generation == search_generation + 1)
        if search_generation != self._search_generation and not stopped:
            return
        self._search_result_limit = max_results
        self._pp_backfill_request = pp_backfill
        self._spansh_pp_enrichment = pp_enrichment or {}
        if reference_coords:
            self.current_system_coords = reference_coords
        if spansh_results is not None:
            self._cached_spansh_results = spansh_results
        self._update_results(hotspots)

    def _hotspot_missing_metadata(self, hotspot: Dict):
        """Return (ring type missing, LS distance missing) for a result row."""
        return (hotspot.get('ring_type') in (None, '', 'No data'),
                hotspot.get('ls_distance') in (None, '', 'No data'))

    def _start_edsm_metadata_fill(self, generation):
        """Fill missing LS distance and ring type of the shown rows from EDSM.

        Runs after the rows are displayed; the cells are updated in place when EDSM answers.
        """
        edsm = getattr(self, 'edsm', None)
        rows = dict(getattr(self, '_result_row_hotspots', {}))
        if edsm is None or not rows:
            return
        if not hasattr(self, '_edsm_no_data_systems'):
            self._edsm_no_data_systems = set()

        systems, seen = [], set()
        for hotspot in rows.values():
            if not hotspot or not any(self._hotspot_missing_metadata(hotspot)):
                continue
            system = hotspot.get('systemName', hotspot.get('system', ''))
            key = system.lower()
            if system and key not in seen and key not in self._edsm_no_data_systems:
                seen.add(key)
                systems.append(system)
        if len(rows) >= 100:
            systems = systems[:30]
        if not systems:
            return

        def is_cancelled():
            return generation != self._results_generation or generation[0] != self._search_generation

        threading.Thread(target=self._edsm_metadata_worker,
                         args=(generation, rows, systems, is_cancelled), daemon=True).start()

    def _edsm_metadata_worker(self, generation, rows: Dict, systems: List[str], is_cancelled):
        """Background part of _start_edsm_metadata_fill."""
        try:
            stats = self.edsm.fill_missing_metadata_for_systems_direct(systems, is_cancelled=is_cancelled)
            # EDSM's answer won't change this session, so don't ask again on the next search
            self._edsm_no_data_systems.update(s.lower() for s in stats.get('no_data_systems', []))
            if not stats.get('materials_updated') or is_cancelled():
                return
            updates = self._read_filled_ring_metadata(rows)
            if updates:
                self.parent.after(0, self._apply_edsm_metadata, generation, updates)
        except Exception as e:
            log.error(f"[EDSM] Fallback failed (non-critical): {e}")

    def _read_filled_ring_metadata(self, rows: Dict) -> Dict:
        """Map tree item -> (ring_type, ls_distance) from the database for rows still missing either."""
        import sqlite3
        updates = {}
        conn = sqlite3.connect(self.user_db.db_path)
        try:
            cursor = conn.cursor()
            for item_id, hotspot in rows.items():
                if not hotspot or not any(self._hotspot_missing_metadata(hotspot)):
                    continue
                system = hotspot.get('systemName', hotspot.get('system', ''))
                body = hotspot.get('bodyName', hotspot.get('ring', ''))
                if system and body.startswith(system):
                    body = body[len(system):].strip()
                cursor.execute(
                    'SELECT MAX(ring_type), MAX(ls_distance) FROM hotspot_data '
                    'WHERE system_name = ? AND body_name = ?', (system, body))
                found = cursor.fetchone()
                if found and (found[0] or found[1] is not None):
                    updates[item_id] = found
        finally:
            conn.close()
        return updates

    def _apply_edsm_metadata(self, generation, updates: Dict):
        """Fill the LS and Ring Type cells of the shown rows in place."""
        if (not self.parent.winfo_exists() or generation != self._results_generation
                or generation[0] != self._search_generation):
            return
        for item_id, (ring_type, ls_distance) in updates.items():
            hotspot = self._result_row_hotspots.get(item_id)
            if hotspot is None or not self.results_tree.exists(item_id):
                continue
            type_missing, ls_missing = self._hotspot_missing_metadata(hotspot)
            if type_missing and ring_type:
                hotspot['ring_type'] = translate_ring_type(ring_type)
                self.results_tree.set(item_id, 'Ring Type', hotspot['ring_type'])
            if ls_missing and ls_distance is not None:
                try:
                    ls_display = f"{int(float(ls_distance)):,}"
                except (TypeError, ValueError):
                    continue
                hotspot['ls_distance'] = ls_distance
                hotspot['ls'] = ls_display
                self.results_tree.set(item_id, 'LS', ls_display)

    def _start_pp_backfill(self, generation):
        """Fill the PowerPlay column of the shown rows with Spansh data after they are displayed.

        Covers Spansh's Exploited/Fortified/Stronghold/Unoccupied states, for rows where the
        EDDN cache has nothing newer. Only runs when the search asked for it (no Power/PP State
        filter, and Spansh PowerPlay data enabled).
        """
        request = getattr(self, '_pp_backfill_request', None)
        rows = dict(getattr(self, '_result_row_hotspots', {}))
        if not request or not rows:
            return
        systems = {h.get('system', h.get('systemName', '')) for h in rows.values() if h}
        systems.discard('')
        if not systems:
            return

        def is_cancelled():
            return generation != self._results_generation or generation[0] != self._search_generation

        threading.Thread(target=self._pp_backfill_worker,
                         args=(generation, request, systems, is_cancelled), daemon=True).start()

    def _pp_backfill_worker(self, generation, request, systems, is_cancelled):
        """Background part of _start_pp_backfill."""
        try:
            from system_finder_api import SystemFinderAPI
            reference_system, max_distance = request
            spansh_pp = SystemFinderAPI._fetch_spansh_powerplay_backfill(
                reference_system, max_distance, is_cancelled=is_cancelled)
            found = [name for name in systems if name in spansh_pp]
            if not found:
                return
            pp_cache = SystemFinderAPI._batch_get_powerplay(found)
            updates = {name: spansh_pp[name] for name in found
                       if SystemFinderAPI._spansh_pp_should_replace_cache(spansh_pp[name], pp_cache.get(name))}
            if updates:
                SystemFinderAPI._store_powerplay_batch(updates)
                self.parent.after(0, self._apply_pp_backfill, generation, updates)
        except Exception as e:
            log.error(f"[POWERPLAY] Spansh backfill failed (non-critical): {e}")

    def _apply_pp_backfill(self, generation, updates: Dict):
        """Set the PowerPlay cells of the shown rows in place."""
        if (not self.parent.winfo_exists() or generation != self._results_generation
                or generation[0] != self._search_generation):
            return
        for item_id, hotspot in self._result_row_hotspots.items():
            entry = updates.get(hotspot.get('system', hotspot.get('systemName', ''))) if hotspot else None
            if entry and self.results_tree.exists(item_id):
                self.results_tree.set(item_id, 'PowerPlay', self._powerplay_display(entry, hotspot))

    def _limit_results_by_unique_rings(self, results: List[Dict], max_rings: int) -> List[Dict]:
        """Limit results by counting unique rings (system+body pairs) instead of individual rows.
        
        This ensures max_results counts unique mining locations rather than individual hotspot entries.
        Database returns one row per material per ring; Spansh returns one row per ring with grouped materials.
        
        Args:
            results: List of hotspot result dicts (must have 'systemName' and 'bodyName' keys)
            max_rings: Maximum number of unique rings to include
            
        Returns:
            Sliced list containing rows for up to max_rings unique rings
        """
        if not max_rings or not results:
            return results
        
        seen_rings = set()
        limited_results = []
        
        for result in results:
            system = result.get('systemName', result.get('system', ''))
            body = result.get('bodyName', result.get('ring', ''))
            body = self.user_db._normalize_body_name(body, system)
            ring_key = (system.lower(), body)

            if ring_key not in seen_rings:
                if len(seen_rings) >= max_rings:
                    continue
                seen_rings.add(ring_key)
            limited_results.append(result)
        
        if len(limited_results) < len(results):
            print(f"[MAX_RESULTS] Limited from {len(results)} rows to {len(limited_results)} rows ({len(seen_rings)} unique rings)")
        
        return limited_results

    def _impossible_mineral_search(self, ring_type: str, ring_type_display: str, first: str, first_display: str,
                                   second: str, second_display: str, same_ring: bool) -> Optional[str]:
        """Message explaining why a two-mineral search can't match anything, or None.

        ring_type/first/second are English names; minerals missing from the table are never blocked.
        """
        types = self.MINING_METHOD_BY_RING
        if ring_type != 'All':
            for mineral, display in ((first, first_display), (second, second_display)):
                if mineral in types and ring_type not in types[mineral]:
                    return t('ring_finder.mineral_not_in_ring_type').format(mineral=display, ring_type=ring_type_display)
        if same_ring and first in types and second in types and not set(types[first]) & set(types[second]):
            return t('ring_finder.minerals_never_same_ring').format(first=first_display, second=second_display)
        return None

    def _combine_mineral_results(self, rows_a: List[Dict], rows_b: List[Dict], same_ring: bool) -> List[Dict]:
        """Rows for places holding both minerals: the same ring, or anywhere in the same system.

        rows_a/rows_b are the results of searching for each mineral on its own.
        """
        def keys(row):
            system = row.get('systemName', row.get('system', ''))
            body = self.user_db._normalize_body_name(row.get('bodyName', row.get('ring', '')), system)
            return system.lower(), body

        rings_a = {keys(r) for r in rows_a}
        rings_b = {keys(r) for r in rows_b}
        if same_ring:
            combined = [r for r in rows_a if keys(r) in rings_b]
        else:
            both_systems = {s for s, _ in rings_a} & {s for s, _ in rings_b}
            combined = [r for r in rows_a if keys(r)[0] in both_systems]
            # A ring holding both minerals is already listed from rows_a
            combined += [r for r in rows_b if keys(r)[0] in both_systems and keys(r) not in rings_a]

        def number(value, default):
            try:
                return float(str(value).replace(',', ''))
            except (TypeError, ValueError):
                return default

        # Rows of one system can carry slightly different distances; the nearest keeps them together
        system_distance = {}
        for r in combined:
            s = keys(r)[0]
            system_distance[s] = min(system_distance.get(s, 999999.0), number(r.get('distance'), 999999.0))

        def ring_order(body):
            """Natural order within a system, like the system map: 2 B Ring before 10 A Ring."""
            return tuple((0, int(part), '') if part.isdigit() else (1, 0, part)
                         for part in re.findall(r'\d+|[^\d\s]+', body.lower()))

        def sort_key(r):
            key = keys(r)
            return (system_distance[key[0]], key[0], ring_order(key[1]), str(r.get('source', '')).lower())

        combined.sort(key=sort_key)
        # _update_results keeps this order and shades the rows per system instead of per row
        for i, r in enumerate(combined):
            r['pair_order'] = i
        return combined

    def _resolve_spansh_system_name(self, system_name: str, is_cancelled=None) -> Optional[str]:
        """Resolve system name to correct capitalization using Spansh API (case-insensitive)

        Names known from the journal, or answered by Spansh earlier this session, need no request.

        Args:
            system_name: System name to resolve (e.g., "sol" or "Sol")
            is_cancelled: optional zero-arg callable; no request is sent once it returns True

        Returns:
            Correctly capitalized system name, or None if resolution fails
        """
        import requests

        candidate = system_name.strip()
        if not candidate:
            return None
        key = candidate.lower()

        panel = getattr(self, 'prospector_panel', None)
        journal_names = (getattr(self, 'last_monitored_system', None),
                         getattr(panel, 'last_system', None),
                         getattr(getattr(panel, 'main_app', None), 'current_system', None))
        for name in journal_names:
            if isinstance(name, str) and name.strip().lower() == key:
                return name.strip()

        if not hasattr(self, '_spansh_name_cache'):
            self._spansh_name_cache = {}
        if key in self._spansh_name_cache:
            return self._spansh_name_cache[key]
        if is_cancelled and is_cancelled():
            return None

        try:
            url = 'https://spansh.co.uk/api/systems/field_values/system_names'
            params = {'q': candidate}
            headers = {'User-Agent': 'EliteMining/4.79', 'Accept': 'application/json'}

            response = tracked_request('spansh', requests.get, url, params=params, headers=headers, timeout=10)
            if response.status_code != 200:
                return None

            values = [value.strip() for value in response.json().get('values', [])
                      if isinstance(value, str) and value.strip()]
            # Exact match only (case-insensitive): a suggestion would centre the search on another system
            resolved = next((value for value in values if value.lower() == key), None)
            self._spansh_name_cache[key] = resolved
            return resolved

        except Exception as e:
            log.error(f"[SPANSH] System name resolution failed: {e}")
            return None
    
    def _search_spansh_with_filters(self, reference_system: str, material_filter: str, specific_material: str, max_distance: float, max_results: int, reference_coords, ring_type_only: bool = False, is_cancelled=None, stop_at_limit: bool = False) -> List[Dict]:
        """Search Spansh API with proper filters for hotspot fallback (EDMC approach)

        Args:
            reference_system: Name of reference system
            material_filter: Ring type filter (All, Icy, Rocky, Metallic, Metal Rich)
            specific_material: Specific mineral name or "All Minerals"
            max_distance: Maximum distance in light years
            max_results: Maximum number of results
            reference_coords: Reference system coordinates dict
            ring_type_only: If True, search for ring types only (ignore hotspot data)
            is_cancelled: optional zero-arg callable checked between pagination pages —
                lets Stop end a Ring Search (which can page up to 30 requests) after the
                current page instead of waiting for the whole sweep to finish.
            stop_at_limit: If True, stop paging once max_results rings are collected. Results are
                sorted by distance, so these are the closest ones.

        Returns:
            List of hotspot-format dicts compatible with _update_results
        """
        import requests
        import time
        
        # Update status to show Spansh search is starting
        self.parent.after(0, lambda: self.status_var.set(t('ring_finder.spansh_querying'))
                          if self.parent.winfo_exists() and not (is_cancelled and is_cancelled()) else None)
        
        # Rows from pages already fetched are kept if a later page fails
        hotspots = []
        try:
            # Throttle API calls (1.5 second minimum between requests)
            if not hasattr(self, '_last_spansh_call'):
                self._last_spansh_call = 0
            
            elapsed = time.time() - self._last_spansh_call
            if elapsed < 1.5:
                sleep_time = 1.5 - elapsed
                print(f"[SPANSH] Throttling: waiting {sleep_time:.1f}s...")
                time.sleep(sleep_time)
            
            # Resolve reference system name to correct capitalization (case-insensitive)
            resolved_system = self._resolve_spansh_system_name(reference_system.strip(), is_cancelled)
            if resolved_system:
                reference_system = resolved_system
            
            # Convert localized ring type back to English for API
            ring_type_english = self._ring_type_rev_map.get(material_filter, material_filter)
            
            # Build filter payload
            filters = {
                'distance': {'min': 0.0, 'max': float(max_distance)}
            }
            
            # Ring Type Only mode: search for ring types without requiring hotspots
            if ring_type_only:
                # Don't add ring_signals filter - we want ALL rings of the type
                pass
            else:
                # Normal mode - only bodies with hotspot rings. "All Minerals" lists every hotspot
                # mineral, since Spansh needs a name; without it most returned bodies have no
                # hotspots and the pages run out before reaching the search radius.
                if not self._is_all_minerals(specific_material):
                    signal_names = [SPANSH_SIGNAL_NAMES.get(specific_material, specific_material)]
                else:
                    signal_names = SPANSH_HOTSPOT_SIGNALS
                filters['ring_signals'] = [{
                    'comparison': '<=>',
                    'count': [1, 9999],
                    'name': signal_names
                }]
            
            # Add ring type filter (both modes) - only if specific type selected
            if ring_type_english != 'All':
                filters['rings'] = [{'type': [ring_type_english]}]
            
            # For "All Minerals" or "All Ring Types" or "Ring Type Only" searches, use pagination to get more results covering larger distances
            # Spansh returns bodies sorted by distance, but with no filters there are many bodies
            # so 500 results might only cover 10-15 LY per page in dense regions. Fetch multiple pages to reach max_distance.
            use_pagination = self._is_all_minerals(specific_material) or ring_type_english == 'All' or ring_type_only
            page_size = 500 if use_pagination else 200
            
            # Ring Type Only mode: allow many pages to reach 300 LY (for finding distant rings)
            # Normal hotspot searches: balanced page count for reasonable performance
            if ring_type_only:
                max_pages = 30  # Up to 15,000 results - reach 300 LY even in dense regions
            elif use_pagination:
                max_pages = 10  # Up to 5,000 results - balance between distance coverage and speed
            else:
                max_pages = 1   # Single page for specific material searches
            
            payload_template = {
                'filters': filters,
                'reference_system': reference_system.strip(),  # Don't use .title() - it breaks system names like "HIP 21750" -> "Hip 21750"
                'sort': [{'distance': {'direction': 'asc'}}],
                'size': page_size,
                'page': 0
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
            
            # Fetch pages until we reach max_distance or run out of pages
            for page_num in range(max_pages):
                if is_cancelled and is_cancelled():
                    print(f"[SPANSH PAGINATION] Cancelled before page {page_num}, stopping")
                    break

                # Update status message for pagination (especially for "All Minerals" searches)
                if use_pagination and page_num > 0:
                    progress_msg = t('ring_finder.spansh_fetching_page').format(page=page_num + 1, total=max_pages)
                    self.parent.after(0, lambda msg=progress_msg: self.status_var.set(msg)
                                      if self.parent.winfo_exists() and not (is_cancelled and is_cancelled()) else None)
                
                # Update last call time and throttle
                elapsed = time.time() - self._last_spansh_call
                if elapsed < 1.5 and page_num > 0:
                    sleep_time = 1.5 - elapsed
                    time.sleep(sleep_time)
                
                payload = payload_template.copy()
                payload['page'] = page_num
                
                self._last_spansh_call = time.time()
                
                response = tracked_request('spansh', requests.post,
                    'https://spansh.co.uk/api/bodies/search',
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                
                total_count = data.get('count', 0)
                results = data.get('results', [])
                
                print(f"[SPANSH PAGINATION] Page {page_num}: Got {len(results)} bodies, total available: {total_count}")
                
                if not results:
                    print(f"[SPANSH PAGINATION] No results on page {page_num}, stopping")
                    break
                
                # Check if we've reached bodies beyond max_distance
                last_body_distance = results[-1].get('distance', 0) if results else 0
                
                print(f"[SPANSH PAGINATION] Page {page_num}: Distance range {results[0].get('distance', 0):.1f} - {last_body_distance:.1f} LY")
                
                hotspots.extend(self._spansh_bodies_to_hotspots(
                    results, ring_type_english, ring_type_only, specific_material, reference_coords))

                # Stop if we've gone beyond max_distance
                if last_body_distance >= max_distance:
                    print(f"[SPANSH PAGINATION] Reached max distance ({max_distance} LY) at page {page_num}, stopping")
                    break
                if stop_at_limit and max_results and len(hotspots) >= max_results:
                    print(f"[SPANSH PAGINATION] Have {len(hotspots)} rings (limit {max_results}) at page {page_num}, stopping")
                    break
                if len(results) < page_size:
                    break
            
            
            print(f"[SPANSH] Converted {len(hotspots)} rings to hotspot format")
            
            # Update status: Spansh search succeeded
            self.parent.after(0, lambda: self._update_spansh_status("online"))
            
            return hotspots
            
        except requests.exceptions.Timeout:
            print("[SPANSH] Request timed out")
            self.parent.after(0, lambda: self.status_var.set(t('ring_finder.spansh_timeout'))
                              if not (is_cancelled and is_cancelled()) else None)
            # Update status: Spansh is offline/timing out
            self.parent.after(0, lambda: self._update_spansh_status("offline"))
            return hotspots
        except requests.exceptions.RequestException as e:
            log.error(f"[SPANSH] API error: {e}")
            self.parent.after(0, lambda: self.status_var.set(t('ring_finder.spansh_error'))
                              if not (is_cancelled and is_cancelled()) else None)
            # Update status: Spansh has errors
            self.parent.after(0, lambda: self._update_spansh_status("offline"))
            return hotspots
        except Exception as e:
            log.error(f"[SPANSH] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return hotspots
    
    def _spansh_bodies_to_hotspots(self, results, ring_type_english, ring_type_only, specific_material, reference_coords):
        """Convert one page of Spansh body results to hotspot rows, one per matching ring."""
        hotspots = []
        for body in results:
            system_name = body.get('system_name', '')
            body_name = body.get('name', '')
            distance_ly = body.get('distance', 0)
            distance_ls = body.get('distance_to_arrival', 0)
            reserve_level = body.get('reserve_level', '')  # Extract reserve level from Spansh
            # Extract actual system coordinates provided by Spansh API
            sys_x = body.get('system_x')
            sys_y = body.get('system_y')
            sys_z = body.get('system_z')
            body_coords = {'x': sys_x, 'y': sys_y, 'z': sys_z} if sys_x is not None else reference_coords

            rings = body.get('rings', [])
            for ring in rings:
                ring_type = ring.get('type', 'Unknown')
                ring_name = ring.get('name', '')
                signals = ring.get('signals', [])
                
                # Filter by ring type (client-side) - skip rings that don't match the selected type
                if ring_type_english != 'All' and ring_type != ring_type_english:
                    continue
                
                # Track whether hotspot data came from local DB
                found_in_local_db = False
                
                # In "Ring Type Only" mode, check local database FIRST, then fallback to Spansh signals
                if ring_type_only:
                    # Try to get hotspots from local database first
                    materials_found = []
                    found_in_local_db = False
                    try:
                        # Strip system prefix from ring name for database lookup
                        db_ring_name = ring_name
                        if ring_name.lower().startswith(system_name.lower()):
                            db_ring_name = ring_name[len(system_name):].strip()
                        
                        db_hotspots = self.user_db.get_body_hotspots(system_name, db_ring_name)
                        if db_hotspots:
                            # Found in local database - use that data
                            for h in db_hotspots:
                                material = h.get('material_name', '')
                                count = h.get('hotspot_count', 1)
                                if material:
                                    from material_utils import abbreviate_material
                                    abbrev = abbreviate_material(material)
                                    materials_found.append(f"{abbrev} ({count})")
                            # Sort materials by count (descending), then alphabetically
                            # This ensures consistent ordering: highest count first, then alphabetical
                            materials_found.sort(key=lambda x: (-int(x.split('(')[1].rstrip(')')), x.split(' (')[0]))
                            found_in_local_db = True
                    except Exception as e:
                        log.error(f"[RING SEARCH] DB lookup error for {system_name} {ring_name}: {e}")
                    
                    # Fallback to Spansh signals if no local data
                    if not materials_found and signals:
                        for sig in signals:
                            sig_name = sig.get('name', '')
                            sig_name = APP_SIGNAL_NAMES.get(sig_name, sig_name)
                            sig_count = max(sig.get('count', 0), 1)  # At least 1 if signal exists
                            # Filter out invalid signal names (e.g., "signals")
                            if sig_name and self._is_valid_mining_material(sig_name):
                                materials_found.append(f"{sig_name} ({sig_count})")
                        # Sort materials by count (descending), then alphabetically
                        materials_found.sort(key=lambda x: (-int(x.split('(')[1].rstrip(')')), x.split(' (')[0]))
                    
                    # If still nothing, show "-"
                    if not materials_found:
                        materials_found = ["-"]
                else:
                    # Filter by material if searching for specific mineral
                    materials_found = []
                    selected_count = None
                    for sig in signals:
                        sig_name = sig.get('name', '')
                        sig_name = APP_SIGNAL_NAMES.get(sig_name, sig_name)
                        sig_count = max(sig.get('count', 0), 1)  # At least 1 if signal exists
                        
                        # Filter out invalid signal names (e.g., "signals")
                        if not sig_name or not self._is_valid_mining_material(sig_name):
                            continue
                        
                        materials_found.append(f"{sig_name} ({sig_count})")
                        if not self._is_all_minerals(specific_material) and sig_name == specific_material:
                            selected_count = sig_count

                    # Sort materials by count (descending), then alphabetically
                    if materials_found and materials_found != ["-"]:
                        materials_found.sort(key=lambda x: (-int(x.split('(')[1].rstrip(')')), x.split(' (')[0]))

                    # Skip rings without matching materials (normal mode only)
                    if not materials_found:
                        continue
                    if not self._is_all_minerals(specific_material) and selected_count is None:
                        continue
                
                # Format LS distance for display (same as user DB format)
                ls_display = "No data"
                if distance_ls and distance_ls > 0:
                    try:
                        ls_display = f"{int(float(distance_ls)):,}"
                    except (ValueError, TypeError):
                        ls_display = "No data"
                
                # In Ring Search mode, source is ALWAYS Spansh (ring discovery source)
                # Local DB only provides hotspot details, not the ring discovery
                entry_source = 'Spansh'
                
                # Format for display (match user database format)
                hotspot_entry = {
                    'systemName': system_name,
                    'bodyName': ring_name,  # Use ring name for bodyName
                    'type': ', '.join(materials_found),
                    'count': (selected_count if not ring_type_only and selected_count is not None
                              else sum(int(m.split('(')[1].rstrip(')')) for m in materials_found if '(' in m)),
                    'distance': f"{distance_ly:.1f}" if distance_ly > 0 else "0.0",  # String format
                    'coords': body_coords,
                    'data_source': entry_source,
                    'ring_type': translate_ring_type(ring_type),
                    'ls': ls_display,  # Formatted LS distance
                    'ls_distance': distance_ls,  # Raw LS value
                    'reserve': translate_reserve_level(reserve_level) if reserve_level else '-',  # Translate reserve level
                    'inner_radius': None,
                    'outer_radius': None,
                    'source': entry_source,
                    'ring': ring_name,  # Add ring field
                    'system': system_name,  # Add system field
                    'body': body_name  # Add body field
                }
                hotspots.append(hotspot_entry)
        return hotspots

    def _apply_powerplay_filter(self, hotspots: List[Dict], pp_power: str, pp_state: str,
                                 reference_system: str, max_distance: float, is_cancelled=None,
                                 use_spansh: bool = True) -> List[Dict]:
        """Filter hotspot results by PowerPlay controlling power and/or state.

        Uses the EDDN cache by default. For Exploited/Fortified/Stronghold/Unoccupied - the
        4 states Spansh's systems-search actually supports (Expansion/Contested aren't in its
        index at all) - also queries Spansh and merges it in, keeping whichever source has
        the newer 'updated_at' per system — the EDDN cache alone is often sparse/stale
        for systems the player hasn't personally visited.

        is_cancelled: optional zero-arg callable, passed through to the Spansh enrichment
        call so a Stop click before that request is sent skips it instead of waiting on it.

        Returns (filtered rows, Spansh entries newer than the EDDN cache). The entries are
        for _update_results' PowerPlay column, so a matched row shows real data instead of
        "No data" when the EDDN cache is empty for it.
        """
        from system_finder_api import SystemFinderAPI
        system_names = list({h.get('system', h.get('systemName', '')) for h in hotspots})
        system_names = [s for s in system_names if s]
        pp_cache = SystemFinderAPI._batch_get_powerplay(system_names)
        enrichment = {}

        if use_spansh and pp_state in ('Exploited', 'Fortified', 'Stronghold', 'Unoccupied'):
            # max_distance is already widened to 500 LY by _search_worker for these states
            spansh_pp = SystemFinderAPI._fetch_spansh_powerplay_systems(
                reference_system, max_distance, pp_power, pp_state, is_cancelled=is_cancelled)
            to_persist = {}
            for sys_name, entry in spansh_pp.items():
                cached = pp_cache.get(sys_name)
                if SystemFinderAPI._spansh_pp_should_replace_cache(entry, cached):
                    pp_cache[sys_name] = entry
                    enrichment[sys_name] = entry
                    to_persist[sys_name] = entry
            if to_persist:
                SystemFinderAPI._store_powerplay_batch(to_persist)

        filtered = []
        for h in hotspots:
            sys_name = h.get('system', h.get('systemName', ''))
            entry = pp_cache.get(sys_name, {})
            power = entry.get('controlling_power', '')
            state = entry.get('power_state', '')
            if pp_power != 'Any' and power != pp_power:
                continue
            if pp_state != 'Any' and state != pp_state:
                continue
            filtered.append(h)
        return filtered, enrichment

    def _get_hotspots(self, reference_system: str, material_filter: str, specific_material: str, confirmed_only: bool, max_distance: float, max_results: int = None, data_source: str = None, ring_type_only_active: bool = False, is_cancelled=None, spansh_stop_at_limit: bool = False, force_database: bool = False, reference_coords=None, cached_spansh=None, spansh_fetched=None) -> List[Dict]:
        """Get hotspot data based on user's data source selection.

        cached_spansh: Spansh rows to reuse instead of asking Spansh again.
        spansh_fetched: optional dict; receives the fresh Spansh rows under 'spansh'.
        """

        # Get user's data source preference (or force database for auto-search)
        if force_database:
            data_source = "database"
            print(f"[SEARCH] Auto-search: forcing database only")
        elif ring_type_only_active:
            # Force Spansh-only when Ring Search mode is enabled
            data_source = "spansh"
            print(f"[SEARCH] Ring Search mode: forcing Spansh only")
        elif data_source is None:
            # Fallback to reading Tkinter var (for legacy callers)
            data_source = self.data_source_var.get()
        print(f"[SEARCH] Data source selected: {data_source}")
        
        user_results = []
        spansh_results = []
        
        # When using "both", fetch more from database (user's confirmed scans) than from Spansh
        # This ensures database results have priority while still getting Spansh supplementary coverage
        # Increased multipliers to account for ring-based counting (DB returns multiple rows per ring)
        if data_source == "both" and max_results:
            db_limit = max_results * 6  # Fetch 6x from database (priority) - DB has multiple rows per ring
            spansh_limit = max_results * 2  # Fetch 2x from Spansh (supplementary)
        else:
            db_limit = max_results
            spansh_limit = max_results
        
        # Cap Spansh queries at 150 to prevent API overload and slow searches
        if data_source in ["spansh", "both"]:
            if spansh_limit is None or spansh_limit > 150:
                print(f"[SEARCH] Capping Spansh limit from {spansh_limit} to 150 (API protection)")
                spansh_limit = 150
        
        # Query user database if selected
        if data_source in ["database", "both"]:
            user_results = self._search_user_database_first(reference_system, material_filter, specific_material, max_distance, db_limit, is_cancelled=is_cancelled, reference_coords=reference_coords)
            print(f"[SEARCH] User database returned {len(user_results)} results")
        
        # Query Spansh if selected
        if data_source in ["spansh", "both"]:
            # Reuse the Spansh rows passed in (e.g., after save to database)
            if cached_spansh:
                spansh_results = cached_spansh
                print(f"[SEARCH] Using cached Spansh results: {len(spansh_results)} entries")
            else:
                try:
                    print(f"[SEARCH] Calling Spansh API...")
                    # Pass "Ring Type Only" mode state to Spansh search (already determined at top of function)
                    spansh_results = self._search_spansh_with_filters(
                        reference_system,
                        material_filter,
                        specific_material,
                        max_distance,
                        spansh_limit,  # Use spansh_limit (2x for Both mode, or max_results for spansh-only)
                        reference_coords if reference_coords else self.current_system_coords,
                        ring_type_only=ring_type_only_active,
                        is_cancelled=is_cancelled,
                        stop_at_limit=spansh_stop_at_limit
                    )
                    print(f"[SEARCH] Spansh returned {len(spansh_results)} results")
                    if spansh_fetched is not None:
                        spansh_fetched['spansh'] = spansh_results
                except Exception as e:
                    log.error(f"[SEARCH] Spansh query failed: {e}")
                    import traceback
                    traceback.print_exc()
        
        # Return based on selection
        if data_source == "database":
            return user_results
        elif data_source == "spansh":
            return spansh_results
        else:  # both
            # Merge results from both sources
            # Don't deduplicate - show both Database and Spansh versions for comparison
            # Users can visually distinguish sources by row color (orange=local, cyan=Spansh)
            combined_results = user_results + spansh_results
            
            print(f"[SEARCH] Combined: {len(user_results)} from DB + {len(spansh_results)} from Spansh = {len(combined_results)} total")
            
            # Helper function to normalize body name (strip system prefix)
            def normalize_body(body, system):
                body_lower = body.lower()
                system_lower = system.lower()
                if body_lower.startswith(system_lower):
                    return body_lower[len(system_lower):].strip()
                return body_lower
            
            # Sort combined results - group duplicates (same system+body) together
            # This ensures Database and Spansh results for same ring appear consecutively
            combined_results.sort(key=lambda x: (
                float(x.get('distance', 999999)),  # Primary: distance (closest first)
                x.get('systemName', '').lower(),   # Secondary: system name
                normalize_body(x.get('bodyName', ''), x.get('systemName', '')),  # Tertiary: normalized body name
                x.get('source', '').lower()        # Quaternary: source (database/spansh)
            ))
            
            return combined_results
    
    def _search_user_database_first(self, reference_system: str, material_filter: str, specific_material: str, max_distance: float, max_results: int = None, is_cancelled=None, reference_coords=None) -> List[Dict]:
        """Search user database first for confirmed hotspots, return results in _update_results compatible format"""
        try:
            # Get user database hotspots
            user_hotspots = self._get_user_database_hotspots(reference_system, material_filter, specific_material, max_distance, is_cancelled=is_cancelled, reference_coords=reference_coords)
            
            if not user_hotspots:
                return []
            
            # Convert user database format to _update_results compatible format
            compatible_results = []
            for hotspot in user_hotspots:
                system_name = hotspot.get('systemName', '')
                body_name = hotspot.get('bodyName', '')
                material_name = hotspot.get('type', '')  # User database uses 'type' field for material name
                hotspot_count = hotspot.get('count', 1)
                
                # Get distance (already calculated in user_hotspots)
                distance = hotspot.get('distance', 0)
                ls_distance = hotspot.get('ls_distance', "No data")  # Use actual LS distance from database
                # Don't show old density data - Reserve level is only available from Spansh
                
                # Format LS distance properly for display with comma separators
                if ls_distance != "No data" and ls_distance is not None:
                    try:
                        ls_distance = f"{int(float(ls_distance)):,}"
                    except (ValueError, TypeError):
                        ls_distance = "No data"
                
                # Clean up the ring name using the existing method
                raw_ring_name = body_name
                clean_ring_name = self._clean_ring_name(raw_ring_name, body_name, system_name, source="user_database")
                
                # Create compatible result entry
                compatible_result = {
                    'system': system_name,
                    'systemName': system_name,
                    'body': body_name,
                    'bodyName': body_name,
                    'ring': clean_ring_name,  # Use cleaned ring name
                    'ring_type': hotspot.get('ring_type', 'No data') if hotspot.get('ring_type') not in [None, 'Unknown'] else 'No data',  # Clean ring_type from database
                    'type': material_name,  # Add the material name here
                    'ls': ls_distance,
                    'ls_distance': hotspot.get('ls_distance'),  # Add raw ls_distance for EDSM compatibility
                    'distance': f"{distance:.1f}" if distance > 0 else "0.0",
                    'mass': "No data",  # User database doesn't store ring mass
                    'radius': "No data",  # User database doesn't store ring radius
                    'reserve': hotspot.get('reserve', ''),  # Reserve level from database (Pristine, Major, etc.)
                    'inner_radius': hotspot.get('inner_radius'),  # Include inner radius from database
                    'outer_radius': hotspot.get('outer_radius'),  # Include outer radius from database
                    'has_hotspots': True,
                    'hotspot_data': hotspot,
                    'count': hotspot_count,
                    'data_source': 'Local (Confirmed)',
                    'source': 'Local',
                    'coords': hotspot.get('coords')
                }
                compatible_results.append(compatible_result)
            
            # Sort by distance
            try:
                compatible_results.sort(key=lambda x: float(x.get('distance', 999)))
            except:
                pass
            
            # Don't apply max_results here - it will be applied AFTER min_hotspots filter in _search_worker
            
            return compatible_results
            
        except Exception as e:
            log.error(f"[SEARCH] Database search error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _is_valid_mining_material(self, material_name: str) -> bool:
        """Check if a material name is a valid mining hotspot material"""
        if not material_name:
            return False
        
        material_lower = material_name.lower().strip()
        
        # Valid mining materials (based on Elite Dangerous hotspot data)
        valid_materials = {
            'alexandrite', 'benitoite', 'bromellite', 'grandidierite',
            'low temperature diamonds', 'lowtemperaturediamond', 'ltd',
            'monazite', 'musgravite', 'opal', 'opals', 'void opals',
            'painite', 'platinum', 'rhodplumsite', 'serendibite', 'tritium',
            # Legacy materials
            'palladium', 'osmium', 'gold'
        }
        
        return material_lower in valid_materials
    
    def _material_matches(self, target_material: str, hotspot_material: str) -> bool:
        """Check if hotspot material matches target material, handling abbreviations and display names"""
        if not target_material or not hotspot_material:
            return False
            
        target_lower = target_material.lower().strip()
        hotspot_lower = hotspot_material.lower().strip()
        
        # Direct match (most common case with our clean database)
        if target_lower == hotspot_lower:
            return True
            
        # Handle display name to database name mapping
        display_to_db_mapping = {
            'low temperature diamonds': 'lowtemperaturediamond',
            'low temp diamonds': 'lowtemperaturediamond',  # Dropdown shows this
            'void opals': 'opal'
        }
        
        # Convert display name to database name if needed
        if target_lower in display_to_db_mapping:
            target_lower = display_to_db_mapping[target_lower]
        if hotspot_lower in display_to_db_mapping:
            hotspot_lower = display_to_db_mapping[hotspot_lower]
        
        # Direct match after mapping
        if target_lower == hotspot_lower:
            return True
            
        # Material name mappings for backward compatibility and alternative names
        material_mappings = {
            # Standard materials from our database
            'alexandrite': ['alexandrite', 'alex'],
            'benitoite': ['benitoite', 'beni'],
            'bromellite': ['bromellite', 'brom', 'bromel'],
            'grandidierite': ['grandidierite', 'grand', 'grandi'],
            'lowtemperaturediamond': ['lowtemperaturediamond', 'ltd', 'ltds', 'low temperature diamonds', 'low temp diamonds', 'diamonds'],
            'monazite': ['monazite', 'mona'],
            'musgravite': ['musgravite', 'musg', 'musgravi'],
            'opal': ['opal', 'opals', 'void opals', 'void opal', 'vo'],
            'painite': ['painite', 'pain'],
            'platinum': ['platinum', 'pt', 'plat'],
            'rhodplumsite': ['rhodplumsite', 'rhod', 'rhodplum'],
            'serendibite': ['serendibite', 'seren', 'serendi'],
            'tritium': ['tritium', 't', 'tri'],
            # Legacy materials that might still be searched for
            'palladium': ['palladium', 'pd', 'pall'],
            'osmium': ['osmium', 'os'],
            'gold': ['gold', 'au']
        }
        
        # Check material mappings
        for standard_name, variants in material_mappings.items():
            # If target matches any variant of a material
            if target_lower in variants:
                # Check if hotspot material matches any variant of the same material
                if hotspot_lower in variants:
                    return True
                
        return False
    
    def _determine_ring_type_from_material(self, material_name: str) -> str:
        """DEPRECATED: Always return 'No data' to identify wrong code paths"""
        log.warning(f"⚠️ WARNING: Fallback ring type function called for '{material_name}' - this should not happen!")
        return "Unknown"  # Force obvious identification
            
        material_lower = material_name.lower()
        
        # Ring type mapping based on our database materials
        metallic_materials = ['platinum', 'pt', 'palladium', 'pd', 'gold', 'au']
        icy_materials = ['lowtemperaturediamond', 'ltd', 'low temperature diamonds', 'diamonds', 'bromellite', 'tritium']
        rocky_materials = ['alexandrite', 'benitoite', 'grandidierite', 'monazite', 'musgravite', 'opal', 'opals', 'void opals', 'painite', 'rhodplumsite', 'serendibite']
        
        # Check material type
        if any(m in material_lower for m in metallic_materials):
            return "Metallic"
        elif any(m in material_lower for m in icy_materials):
            return "Icy"  
        elif any(m in material_lower for m in rocky_materials):
            return "Rocky"
        else:
            return "Rocky"  # Default for unknown materials from our database
        
    def _clean_ring_name(self, full_ring_name: str, body_name: str, system_name: str, source: str = None) -> str:
        """Preserve spreadsheet-imported and user database ring names; clean only for journal/API data."""
        try:
            # If source is spreadsheet import or user database, return the original name
            # These sources already have properly formatted ring names
            if source in ("spreadsheet", "user_database"):
                return full_ring_name
            # Otherwise, apply cleaning for journal/API data
            # ...existing cleaning logic...
            import re
            if system_name and full_ring_name.startswith(system_name):
                cleaned = full_ring_name[len(system_name):].strip()
            else:
                cleaned = full_ring_name
            pattern1 = r'(\d+\s+[A-Za-z]\s+Ring)'
            match1 = re.search(pattern1, cleaned)
            if match1:
                result = match1.group(1)
                parts = result.split()
                if len(parts) == 3:
                    return f"{parts[0]} {parts[1].upper()} {parts[2].title()}"
                return result
            pattern2 = r'([A-Za-z]+\s+\d+\s+Ring\s+[A-Za-z])'
            match2 = re.search(pattern2, cleaned)
            if match2:
                parts = match2.group(1).split()
                if len(parts) >= 4:
                    return f"{parts[1]} {parts[3].upper()} Ring"
            pattern3 = r'^[A-Za-z]\s+Ring$'
            if re.match(pattern3, cleaned.strip()):
                parts = cleaned.strip().split()
                return f"{parts[0].upper()} Ring"
            if "Ring" in cleaned:
                result = cleaned.strip()
                result = re.sub(r'\bring\b', 'Ring', result, flags=re.IGNORECASE)
                result = re.sub(r'\b([a-z])\s+Ring\b', lambda m: f"{m.group(1).upper()} Ring", result)
                return result
            else:
                body_num = "1"
                if body_name:
                    body_match = re.search(r'(\d+)', body_name)
                    if body_match:
                        body_num = body_match.group(1)
                return f"{body_num} A Ring"
        except Exception as e:
            log.error(f"Error cleaning ring name: {e}")
            return full_ring_name

    def _get_user_database_hotspots(self, reference_system: str, material_filter: str, specific_material: str, max_distance: float, is_cancelled=None, reference_coords=None) -> List[Dict]:
        """Search user database for hotspots - pure user database approach without EDSM"""
        try:
            import sqlite3
            user_hotspots = []
            
            # Cache for coordinates fetched from galaxy DB (prevent duplicate lookups in same search)
            coord_cache = {}
            # Track coordinates to save back to database
            coords_to_update = []
            
            # Get reference coordinates from multiple sources FIRST. Only reuse the shared
            # self.current_system_coords cache if it was actually set for this reference_system -
            # otherwise a caller searching a different system (e.g. Find Best Mining System's
            # target_system) would silently inherit stale coords from the main tab's last search.
            if not reference_coords:
                reference_coords = self.current_system_coords if getattr(self, '_last_search_key', '').split('_')[0] == reference_system else None
            if not reference_coords and reference_system:
                reference_coords = self.systems_data.get(reference_system.lower())
            if not reference_coords and reference_system:
                # Try user database first - check visited_systems table (most reliable for current location)
                with sqlite3.connect(self.user_db.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT x_coord, y_coord, z_coord 
                        FROM visited_systems 
                        WHERE system_name = ? AND x_coord IS NOT NULL
                        LIMIT 1
                    ''', (reference_system,))
                    ref_result = cursor.fetchone()
                    if ref_result:
                        reference_coords = {'x': ref_result[0], 'y': ref_result[1], 'z': ref_result[2]}
                        print(f" DEBUG: Found reference system {reference_system} in visited_systems table")
                    
                    # Fallback to hotspot_data table if not in visited_systems
                    if not ref_result:
                        cursor.execute('''
                            SELECT DISTINCT x_coord, y_coord, z_coord 
                            FROM hotspot_data 
                            WHERE system_name = ? AND x_coord IS NOT NULL
                            LIMIT 1
                        ''', (reference_system,))
                        ref_result = cursor.fetchone()
                        if ref_result:
                            reference_coords = {'x': ref_result[0], 'y': ref_result[1], 'z': ref_result[2]}
                            print(f" DEBUG: Found reference system {reference_system} in hotspot_data table")
                
                # Fallback to galaxy_systems.db for reference coordinates
                if not reference_coords:
                    reference_coords = self._get_system_coords_from_galaxy_db(reference_system)
                    if reference_coords:
                        print(f" DEBUG: Found reference system {reference_system} in galaxy database")
                    else:
                        # Final fallback: Try EDSM API (for systems not in galaxy DB, e.g., after carrier jump while offline)
                        print(f" DEBUG: Reference system {reference_system} not in galaxy database, trying EDSM API...")
                        reference_coords = self._get_system_coords_from_edsm(reference_system, is_cancelled=is_cancelled)
                        if reference_coords:
                            print(f" DEBUG: Found reference system {reference_system} coordinates from EDSM API")
                        else:
                            print(f" DEBUG: Reference system {reference_system} not found in any database or EDSM, will show all results without distance filtering")
            
            with sqlite3.connect(self.user_db.db_path) as conn:
                cursor = conn.cursor()
                
                # Get systems within range for optimization if we have reference coordinates
                systems_in_range = None
                favourites_search = getattr(self, '_favourites_search', False)
                if reference_coords and max_distance < 1000 and not favourites_search:
                    # coord_cache receives coordinates looked up for rows that have none, so the
                    # per-row loop below uses (and saves) them without further lookups.
                    systems_in_range = self._local_systems_in_range(
                        cursor, reference_system, reference_coords, max_distance, coord_cache)

                # Favourites Only: search exactly the systems that hold favourite rings (no radius pre-filter)
                if favourites_search:
                    cursor.execute('SELECT DISTINCT system_name FROM hotspot_data WHERE favourite = 1')
                    systems_in_range = [row[0] for row in cursor.fetchall()]
                    if not systems_in_range:
                        return []

                # Build optimized query based on whether we have a system filter
                if systems_in_range:
                    # SQLite has a limit of 999 variables per query, so batch if needed
                    BATCH_SIZE = 999
                    all_results = []
                    
                    for i in range(0, len(systems_in_range), BATCH_SIZE):
                        batch = systems_in_range[i:i + BATCH_SIZE]
                        placeholders = ','.join(['?'] * len(batch))
                        
                        # Different query for ALL_MINERALS vs specific material
                        if self._is_all_minerals(specific_material):
                            # Show ALL rings of this type (one row per ring, combining hotspot info)
                            query = f'''
                                SELECT system_name, body_name, 
                                       GROUP_CONCAT(CASE WHEN hotspot_count > 0 THEN material_name || ' (' || hotspot_count || ')' ELSE NULL END, ', ') as material_name,
                                       1 as hotspot_count,
                                       MAX(x_coord) as x_coord, MAX(y_coord) as y_coord, MAX(z_coord) as z_coord, MAX(coord_source) as coord_source, 
                                       MAX(ls_distance) as ls_distance, MAX(reserve_level) as reserve_level, MAX(ring_type) as ring_type, 
                                       MAX(inner_radius) as inner_radius, MAX(outer_radius) as outer_radius
                                FROM hotspot_data
                                WHERE system_name IN ({placeholders})
                                GROUP BY system_name, body_name
                                ORDER BY system_name, body_name
                            '''
                            cursor.execute(query, batch)
                        else:
                            # Show only rings WITH this specific material - filter by material in SQL for efficiency
                            query = f'''
                                SELECT DISTINCT system_name, body_name, material_name, hotspot_count,
                                       x_coord, y_coord, z_coord, coord_source, ls_distance, reserve_level, ring_type, inner_radius, outer_radius
                                FROM hotspot_data
                                WHERE system_name IN ({placeholders}) AND material_name = ?
                                ORDER BY 
                                    hotspot_count DESC, system_name, body_name
                            '''
                            cursor.execute(query, batch + [specific_material])
                        all_results.extend(cursor.fetchall())
                    
                    # Use results from batched queries
                    results = all_results
                else:
                    # If no systems in range found, try direct system name search first
                    search_pattern = f"%{reference_system}%"
                    
                    # Different query for ALL_MINERALS vs specific material
                    if self._is_all_minerals(specific_material):
                        # Show ALL rings of this type (one row per ring)
                        direct_search_query = '''
                            SELECT system_name, body_name, 
                                   GROUP_CONCAT(material_name || ' (' || hotspot_count || ')', ', ') as material_name,
                                   1 as hotspot_count,
                                   MAX(x_coord) as x_coord, MAX(y_coord) as y_coord, MAX(z_coord) as z_coord, MAX(coord_source) as coord_source, 
                                   MAX(ls_distance) as ls_distance, MAX(reserve_level) as reserve_level, MAX(ring_type) as ring_type, 
                                   MAX(inner_radius) as inner_radius, MAX(outer_radius) as outer_radius
                            FROM hotspot_data
                            WHERE system_name LIKE ? OR system_name = ?
                            GROUP BY system_name, body_name
                            ORDER BY system_name, body_name
                            LIMIT 1000
                        '''
                        cursor.execute(direct_search_query, (search_pattern, reference_system))
                    else:
                        # Show only rings WITH this specific material - filter by material in SQL
                        direct_search_query = '''
                            SELECT DISTINCT system_name, body_name, material_name, hotspot_count,
                                   x_coord, y_coord, z_coord, coord_source, ls_distance, reserve_level, ring_type, inner_radius, outer_radius
                            FROM hotspot_data
                            WHERE (system_name LIKE ? OR system_name = ?) AND material_name = ?
                            ORDER BY 
                                hotspot_count DESC, system_name, body_name
                            LIMIT 1000
                        '''
                        cursor.execute(direct_search_query, (search_pattern, reference_system, specific_material))
                    direct_results = cursor.fetchall()
                    
                    if direct_results:
                        results = direct_results
                    else:
                        return []
                
                material_matches = 0
                systems_with_coords = 0
                systems_without_coords = 0

                # One galaxy lookup for systems whose rows still have no coordinates
                missing_coords = sorted({r[0] for r in results if None in (r[4], r[5], r[6])} - set(coord_cache))
                if missing_coords:
                    batch_coords = self._get_galaxy_coords_batch(missing_coords)
                    for name in missing_coords:
                        if name.lower() in batch_coords:
                            coord_cache[name] = batch_coords[name.lower()]

                # Specific mineral: every mineral on each ring, for the Hotspots column
                ring_minerals = {}
                if not self._is_all_minerals(specific_material) and results:
                    result_systems = sorted({r[0] for r in results})
                    for i in range(0, len(result_systems), 999):
                        batch = result_systems[i:i + 999]
                        cursor.execute(
                            'SELECT system_name, body_name, material_name, hotspot_count FROM hotspot_data '
                            f'WHERE hotspot_count > 0 AND system_name IN ({",".join("?" * len(batch))})',
                            batch)
                        for sys_name, body, mat, cnt in cursor.fetchall():
                            ring_minerals.setdefault((sys_name, body), []).append((mat, cnt))

                for system_name, body_name, material_name, hotspot_count, x_coord, y_coord, z_coord, coord_source, ls_distance, reserve_level, ring_type_db, inner_radius, outer_radius in results:
                    if is_cancelled and is_cancelled():
                        break
                    try:
                        # Filter by specific material using our smart material matching
                        if not self._is_all_minerals(specific_material) and not self._material_matches(specific_material, material_name):
                            continue

                        # Skip hotspots explicitly edited to 0 count - not a real hotspot
                        if not self._is_all_minerals(specific_material) and hotspot_count == 0:
                            continue

                        # All Minerals: skip rings where every material was zeroed out (GROUP_CONCAT yields NULL)
                        if self._is_all_minerals(specific_material) and not material_name:
                            continue

                        # Use ring type from database - no fallback needed
                        ring_type = ring_type_db if ring_type_db else "No data"
                        
                        # Normalize ring type spelling (handle typo in database)
                        if ring_type == "Metalic":
                            ring_type = "Metallic"
                        
                        # Filter by ring type (skip if ring_type is "No data" and filter is set)
                        if material_filter != "All":
                            if ring_type == "No data" or ring_type != material_filter:
                                continue
                        
                        material_matches += 1
                        
                        # Calculate distance if we have coordinates for both systems
                        distance = 999.9  # Default for unknown distance
                        coords_available = False
                        system_coords = None
                        
                        if (x_coord is not None and y_coord is not None and z_coord is not None):
                            # Use coordinates from user database
                            system_coords = {'x': x_coord, 'y': y_coord, 'z': z_coord}
                            coords_available = True
                            systems_with_coords += 1
                        else:
                            # Fallback to galaxy_systems.db for coordinates (with caching)
                            if system_name not in coord_cache:
                                galaxy_coords = self._get_system_coords_from_galaxy_db(system_name)
                                
                                # If not in galaxy DB, try EDSM as final fallback
                                if not galaxy_coords:
                                    edsm_coords = self._get_system_coords_from_edsm(system_name, is_cancelled=is_cancelled)
                                    if edsm_coords:
                                        galaxy_coords = edsm_coords
                                        print(f" DEBUG: Used EDSM coords for {system_name}")
                                
                                coord_cache[system_name] = galaxy_coords
                            else:
                                galaxy_coords = coord_cache[system_name]
                            
                            if galaxy_coords:
                                system_coords = galaxy_coords
                                coords_available = True
                                x_coord, y_coord, z_coord = galaxy_coords['x'], galaxy_coords['y'], galaxy_coords['z']
                                systems_with_coords += 1
                                # Track coordinates to save back to database
                                coords_to_update.append((x_coord, y_coord, z_coord, system_name))
                            else:
                                systems_without_coords += 1
                        
                        # Calculate distance if we have both reference and system coordinates
                        if reference_coords and coords_available:
                            calculated_distance = self._calculate_distance(reference_coords, system_coords)
                            # Ensure distance is never None
                            distance = calculated_distance if calculated_distance is not None else 999.9
                        elif not coords_available:
                            systems_without_coords += 1
                        
                        # Apply distance filtering if reference coordinates are available
                        if reference_coords and coords_available:
                            # Safety check: ensure distance is not None before comparison
                            if distance is None:
                                log.warning(f" DEBUG: WARNING - distance is None for {system_name}, setting to 999.9")
                                distance = 999.9
                            # Apply distance filter for systems with coordinates
                            if distance > max_distance:
                                continue  # Skip systems beyond distance limit
                        elif reference_coords:
                            # If we have reference coords but this system doesn't have coords,
                            # only include it if we need more results or user wants unfiltered search
                            if max_distance < 1000:  # If user set a specific distance limit, skip systems without coords
                                continue
                        
                        # Include this system in results
                        source_label = f"EDTools.cc ({coord_source})" if coord_source else "EDTools.cc Community Data"
                        
                        # Sort and abbreviate material names ONLY for "All Minerals" view
                        if self._is_all_minerals(specific_material):
                            # First sort the hotspots string, then abbreviate
                            sorted_material_name = self._sort_hotspots_display(material_name)
                            display_material_name = self._abbreviate_material_for_display(sorted_material_name)
                        else:
                            ring_mats = sorted(
                                ring_minerals.get((system_name, body_name), []),
                                key=lambda m: (not self._material_matches(specific_material, m[0]), -m[1], m[0]))
                            display_material_name = self._abbreviate_material_for_display(
                                ', '.join(f"{n} ({c})" for n, c in ring_mats)) if ring_mats else material_name

                        # Ensure distance is never None (safety check)
                        if distance is None or distance is False:
                            distance = 999.9
                        
                        # Format distance safely
                        try:
                            formatted_distance = round(distance, 1)
                        except (TypeError, ValueError):
                            formatted_distance = 999.9
                        
                        hotspot_entry = {
                            'systemName': system_name,
                            'bodyName': body_name,
                            'type': display_material_name,
                            'count': hotspot_count if hotspot_count is not None else 1,
                            'distance': formatted_distance,
                            'coords': {'x': x_coord, 'y': y_coord, 'z': z_coord} if x_coord is not None else None,
                            'data_source': source_label,
                            'ring_mass': 0,
                            'ring_type': translate_ring_type(ring_type),  # Translate ring type
                            'ls_distance': ls_distance,  # Include LS distance from database
                            'reserve': translate_reserve_level(reserve_level) if reserve_level else '',  # Translate reserve level
                            'inner_radius': inner_radius,  # Include inner radius from database
                            'outer_radius': outer_radius,  # Include outer radius from database
                            'debug_id': 'SECTION_2'  # Track which section created this entry
                        }
                        
                        user_hotspots.append(hotspot_entry)
                        
                    except Exception:
                        continue
                
                # CRITICAL FIX: Ensure ALL distances are valid numbers before sorting
                try:
                    for h in user_hotspots:
                        if h.get('distance') is None:
                            h['distance'] = 999.9
                except Exception:
                    pass
                
                # Closest first, then nearest arrival point, so the Max Results cut keeps the nearest rings
                user_hotspots.sort(key=lambda x: (x.get('distance') or 999.9, x.get('ls_distance') or 999999))
                
                # Batch-update database with fetched coordinates (save for future searches)
                if coords_to_update:
                    try:
                        print(f" DEBUG: Saving {len(coords_to_update)} coordinate lookups to database...")
                        cursor.executemany('''
                            UPDATE hotspot_data 
                            SET x_coord = ?, y_coord = ?, z_coord = ?, coord_source = 'galaxy_systems.db'
                            WHERE system_name = ? AND x_coord IS NULL
                        ''', coords_to_update)
                        conn.commit()
                    except Exception:
                        log.exception("Saving looked-up hotspot coordinates failed")
                
                return user_hotspots
                
        except Exception:
            return []
    
    def _calculate_distance(self, coord1: Dict, coord2: Dict) -> float:
        """Calculate distance between two 3D coordinates in light years"""
        if not coord1 or not coord2:
            return 0.0
        
        dx = coord1['x'] - coord2['x']
        dy = coord1['y'] - coord2['y'] 
        dz = coord1['z'] - coord2['z']
        
        return math.sqrt(dx*dx + dy*dy + dz*dz)
    
    def _get_system_coords_from_galaxy_db(self, system_name: str) -> Optional[Dict]:
        """Get system coordinates from galaxy_systems.db with retry logic"""
        try:
            import sqlite3
            from pathlib import Path
            import time
            
            # Use bundled galaxy database
            script_dir = Path(self.app_dir) if self.app_dir else Path(__file__).parent
            galaxy_db_path = script_dir / "data" / "galaxy_systems.db"
            
            if not galaxy_db_path.exists():
                print(f" DEBUG: Galaxy database not found at {galaxy_db_path}")
                return None
            
            # Retry logic for database access (may be locked after restart)
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    with sqlite3.connect(str(galaxy_db_path), timeout=5.0) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT x, y, z FROM systems WHERE name = ? COLLATE NOCASE LIMIT 1", (system_name,))
                        result = cursor.fetchone()
                        
                        if result:
                            return {'x': result[0], 'y': result[1], 'z': result[2]}
                        return None  # System not found
                        
                except sqlite3.OperationalError as e:
                    if attempt < max_retries - 1:
                        print(f" DEBUG: Galaxy DB locked, retrying... (attempt {attempt + 1})")
                        time.sleep(0.3)
                    else:
                        log.error(f" DEBUG: Galaxy DB access failed after retries: {e}")
                        return None
                    
        except Exception as e:
            log.error(f" DEBUG: Error accessing galaxy database: {e}")
            
        return None
    
    def _local_systems_in_range(self, cursor, reference_system: str, reference_coords: Dict, max_distance: float, coord_out: Dict[str, Dict]) -> List[str]:
        """Systems with hotspot rows within max_distance of reference_coords, closest first.

        Only systems in hotspot_data can match, so the galaxy database is only asked for
        systems whose rows have no coordinates. coord_out receives the coordinates used for
        those rows, so the caller can calculate their distance and save them.
        """
        distances = {}
        known_coords = {}
        cursor.execute('''
            SELECT DISTINCT system_name, x_coord, y_coord, z_coord FROM hotspot_data
            WHERE x_coord IS NOT NULL AND y_coord IS NOT NULL AND z_coord IS NOT NULL
        ''')
        for name, x, y, z in cursor.fetchall():
            coords = {'x': x, 'y': y, 'z': z}
            known_coords.setdefault(name.lower(), coords)
            distance = self._calculate_distance(reference_coords, coords)
            if distance <= max_distance:
                distances[name] = min(distance, distances.get(name, distance))

        cursor.execute('''
            SELECT DISTINCT system_name FROM hotspot_data
            WHERE x_coord IS NULL OR y_coord IS NULL OR z_coord IS NULL
        ''')
        missing = [row[0] for row in cursor.fetchall()]
        if missing:
            galaxy_coords = self._get_galaxy_coords_batch(missing)
            visited_coords = {}
            if any(name.lower() not in galaxy_coords for name in missing):
                try:
                    cursor.execute('''
                        SELECT system_name, x_coord, y_coord, z_coord FROM visited_systems
                        WHERE x_coord IS NOT NULL AND y_coord IS NOT NULL AND z_coord IS NOT NULL
                    ''')
                    for name, x, y, z in cursor.fetchall():
                        visited_coords.setdefault(name.lower(), {'x': x, 'y': y, 'z': z})
                except Exception:
                    log.exception("Reading visited system coordinates failed")
            reference_key = (reference_system or '').lower()
            for name in missing:
                key = name.lower()
                coords = galaxy_coords.get(key) or visited_coords.get(key) or known_coords.get(key)
                if not coords and key == reference_key:
                    coords = {'x': reference_coords['x'], 'y': reference_coords['y'], 'z': reference_coords['z']}
                if not coords:
                    continue
                distance = self._calculate_distance(reference_coords, coords)
                if distance <= max_distance:
                    coord_out[name] = coords
                    distances[name] = min(distance, distances.get(name, distance))

        return sorted(distances, key=distances.get)

    def _get_galaxy_coords_batch(self, system_names: List[str]) -> Dict[str, Dict]:
        """Coordinates from galaxy_systems.db for many systems at once, keyed by lowercase name."""
        found = {}
        try:
            import sqlite3
            from pathlib import Path

            script_dir = Path(self.app_dir) if self.app_dir else Path(__file__).parent
            galaxy_db_path = script_dir / "data" / "galaxy_systems.db"
            if not galaxy_db_path.exists():
                return found
            with sqlite3.connect(str(galaxy_db_path), timeout=5.0) as conn:
                cursor = conn.cursor()
                for i in range(0, len(system_names), 999):
                    batch = system_names[i:i + 999]
                    cursor.execute(
                        'SELECT name, x, y, z FROM systems '
                        f'WHERE name COLLATE NOCASE IN ({",".join("?" * len(batch))})', batch)
                    for name, x, y, z in cursor.fetchall():
                        found.setdefault(name.lower(), {'x': x, 'y': y, 'z': z})
        except Exception:
            log.exception("Galaxy coordinate lookup failed")
        return found

    def _get_system_coords_from_edsm(self, system_name: str, is_cancelled=None) -> Optional[Dict]:
        """Get system coordinates from EDSM API as fallback (no request once is_cancelled returns True)"""
        if is_cancelled and is_cancelled():
            return None
        try:
            # Use ChatGPT's recommended endpoint - api-v1/systems (plural)
            url = "https://www.edsm.net/api-v1/systems"
            params = {
                "systemName": system_name,
                "showCoordinates": 1
            }

            response = tracked_request('edsm', requests.get, url, params=params, timeout=10,
                                       headers={"User-Agent": "EliteMining/5.1.3"})
            
            if response.status_code == 200:
                data = response.json()
                # EDSM returns a list, take the first match
                if data and len(data) > 0:
                    sys_info = data[0]
                    if 'coords' in sys_info:
                        coords = {
                            'name': sys_info.get('name', system_name),
                            'x': sys_info['coords']['x'],
                            'y': sys_info['coords']['y'],
                            'z': sys_info['coords']['z']
                        }
                        # Cache it in our local systems data for future use
                        self.systems_data[system_name.lower()] = coords
                        print(f" DEBUG: Successfully got coordinates from EDSM for '{system_name}': {coords}")
                        return coords
                    else:
                        print(f" DEBUG: No coordinates in EDSM response for '{system_name}'")
                else:
                    print(f" DEBUG: System '{system_name}' not found in EDSM - may be incomplete name or not discovered yet")
                    
        except Exception as e:
            log.error(f" DEBUG: Failed to get coordinates from EDSM: {e}")
            
        return None

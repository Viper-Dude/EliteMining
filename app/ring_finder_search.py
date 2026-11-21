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
        import traceback
        import time as _time
        print(f"[SEARCH] search_hotspots() called at {_time.time():.1f} (force_database={force_database}, auto_refresh={auto_refresh}) from:")
        print(''.join(traceback.format_stack(limit=4)[:-1]))

        # Store force_database flag for use in search
        self._force_database = force_database

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
        
        # Keep search button clickable (it now doubles as a Stop button)
        self._search_in_progress = True
        self.search_btn.configure(text=t('ring_finder.stop'))
        self.status_var.set(t('ring_finder.searching'))
        
        # Check if Any Ring mode is enabled
        any_ring_mode = self.any_ring_var.get()
        
        # Capture Tkinter vars in main thread (Tkinter is not thread-safe)
        overlaps_only = self.overlaps_only_var.get()
        res_only = self.res_only_var.get()
        data_source = self.data_source_var.get()
        ring_type_only = hasattr(self, 'ring_type_only_var') and self.ring_type_only_var.get()
        pp_power_filter = self.pp_power_var.get() if hasattr(self, 'pp_power_var') else 'Any'
        pp_state_filter = self.pp_state_var.get() if hasattr(self, 'pp_state_var') else 'Any'
        use_spansh_pp = data_source != 'database' or self.spansh_pp_var.get()

        # For Any Ring mode, use a large fixed distance (dropdown is disabled)
        # Some regions of space have limited ring data, so use large radius
        if any_ring_mode:
            max_distance = 1000.0  # Fixed 1000 LY for Any Ring mode (covers sparse regions)
        elif pp_state_filter in ('Exploited', 'Fortified', 'Stronghold', 'Unoccupied', 'Expansion', 'Contested'):
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

        # Increment search generation to cancel any in-flight searches
        self._search_generation += 1
        current_generation = self._search_generation

        # Run search in background - pass reference system coords and max results to worker
        threading.Thread(target=self._search_worker,
                        args=(reference_system, material_filter, specific_material, confirmed_only, max_distance, self.current_system_coords, max_results, min_hotspots, any_ring_mode, overlaps_only, res_only, data_source, ring_type_only, current_generation, pp_power_filter, pp_state_filter, use_spansh_pp),
                        daemon=True).start()

    def _search_worker(self, reference_system: str, material_filter: str, specific_material: str, confirmed_only: bool, max_distance: float, reference_coords, max_results, min_hotspots: int = 1, any_ring_mode: bool = False, overlaps_only: bool = False, res_only: bool = False, data_source: str = "both", ring_type_only: bool = False, search_generation: int = 0, pp_power: str = 'Any', pp_state: str = 'Any', use_spansh_pp: bool = True):
        """Background worker for hotspot search"""
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
                        edsm_coords = self._get_system_coords_from_edsm(reference_system)
                        if edsm_coords:
                            reference_coords = edsm_coords
                
                if not reference_coords:
                    # Update UI with error message
                    self.parent.after(0, self._run_search_callback, search_generation,
                                      self.status_var.set, t('ring_finder.coords_not_found_warning').format(system=reference_system))
                    return
            
            # Set the reference system coords for this worker thread
            if search_generation != self._search_generation:
                return
            self.current_system_coords = reference_coords
            print(f"[SEARCH-DEBUG] ref='{reference_system}' coords={reference_coords} systems_data={self.systems_data.get(reference_system.lower())}")
            print(f"[SEARCH] Coordinate resolution done at {time.time():.1f}, entering search dispatch")

            # Any Ring mode: Search Spansh for rings of specific type (ignoring hotspot data)
            if any_ring_mode:
                # Use max_results if set, otherwise default to 150 for more results
                spansh_max = max_results if max_results else 150
                spansh_rings = self._search_spansh_rings(
                    reference_system, material_filter, max_distance, spansh_max, reference_coords,
                    is_cancelled=lambda: search_generation != self._search_generation)
                print(f" DEBUG: Any Ring mode - found {len(spansh_rings)} rings from Spansh")
                # Convert Spansh rings to hotspot format using local database lookup
                hotspots = self._convert_spansh_to_hotspots(spansh_rings, reference_coords)
                print(f" DEBUG: Any Ring mode - converted to {len(hotspots)} hotspot entries")
            # Overlaps Only mode: Show only overlap entries (only works with database)
            elif overlaps_only:
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
            else:
                hotspots = self._get_hotspots(reference_system, material_filter, specific_material, confirmed_only, max_distance, max_results, data_source=data_source, ring_type_only_active=ring_type_only,
                                               is_cancelled=lambda: search_generation != self._search_generation)
            
            # Apply PowerPlay filter using EDDN cache (local database only — Power/State
            # combos are greyed out and reset to Any for Spansh/Both data sources)
            if pp_power != 'Any' or pp_state != 'Any':
                if search_generation != self._search_generation:
                    print(f"[SEARCH] Search gen {search_generation} cancelled before PowerPlay filter (current: {self._search_generation})")
                    return
                hotspots = self._apply_powerplay_filter(
                    hotspots, pp_power, pp_state, reference_system, max_distance,
                    is_cancelled=lambda: search_generation != self._search_generation,
                    use_spansh=use_spansh_pp)
            else:
                # No Power/PP State filter active — still backfill the PowerPlay column with
                # Spansh's own Exploited/Fortified/Stronghold/Unoccupied data (the 4 states
                # Spansh reliably indexes) for rows where the EDDN cache has nothing newer,
                # so results aren't limited to whatever the sparse EDDN cache happens to have.
                self._spansh_pp_enrichment = {}
                if use_spansh_pp and search_generation == self._search_generation:
                    from system_finder_api import SystemFinderAPI
                    system_names = list({h.get('system', h.get('systemName', '')) for h in hotspots})
                    system_names = [s for s in system_names if s]
                    if system_names:
                        pp_cache = SystemFinderAPI._batch_get_powerplay(system_names)
                        spansh_pp = SystemFinderAPI._fetch_spansh_powerplay_backfill(
                            reference_system, max_distance,
                            is_cancelled=lambda: search_generation != self._search_generation)
                        to_persist = {}
                        for sys_name, entry in spansh_pp.items():
                            if sys_name not in system_names:
                                continue
                            cached = pp_cache.get(sys_name)
                            if SystemFinderAPI._spansh_pp_should_replace_cache(entry, cached):
                                self._spansh_pp_enrichment[sys_name] = entry
                                to_persist[sys_name] = entry
                        if to_persist:
                            SystemFinderAPI._store_powerplay_batch(to_persist)

            # Apply min hotspots filter if needed (skip for overlaps/RES only mode)
            if min_hotspots > 1 and not self._is_all_minerals(specific_material) and not overlaps_only and not res_only:
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
                    self.parent.after(0, self._complete_search, search_generation, hotspots, max_results)
                else:
                    print(f"[SEARCH] Search gen {search_generation} cancelled before display (current: {self._search_generation})")
                return
            
            # EDSM FALLBACK: Smart throttling to prevent hanging
            # Small searches: Query all systems
            # Large searches: Query only first 30 systems for top results
            import time
            print(f"[SEARCH] Before EDSM fallback: {len(hotspots)} hotspots at {time.time():.1f}")
            if hotspots and len(hotspots) < 100:
                self._fill_missing_metadata_edsm(hotspots)
            elif hotspots and len(hotspots) >= 100:
                self._fill_missing_metadata_edsm(hotspots, max_systems=30)
            print(f"[SEARCH] After EDSM fallback at {time.time():.1f}, scheduling _update_results")
            
            # Update UI in main thread
            self.parent.after(0, self._complete_search, search_generation, hotspots, max_results)
            
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

    def _complete_search(self, search_generation, hotspots, max_results):
        stopped = (getattr(self, '_stopped_generation', None) == search_generation
                   and self._search_generation == search_generation + 1)
        if search_generation != self._search_generation and not stopped:
            return
        self._search_result_limit = max_results
        self._update_results(hotspots)

    def _fill_missing_metadata_edsm(self, hotspots: List[Dict], max_systems: int = None):
        """
        Automatically fill missing ring metadata using EDSM fallback.
        
        This runs silently in background thread before displaying results.
        Only queries EDSM for systems that have incomplete rings in THIS result set.
        
        Args:
            hotspots: List of hotspot dicts to check and potentially update
            max_systems: Optional limit on number of systems to query (for large searches)
        """
        try:
            # Build set of systems with incomplete rings in THIS result set only
            systems_needing_data = set()
            for hotspot in hotspots:
                system_name = hotspot.get('systemName')
                ring_type = hotspot.get('ring_type')
                ls_distance = hotspot.get('ls_distance')
                
                # Normalize "No data" strings to None for comparison
                if ring_type == "No data":
                    ring_type = None
                if ls_distance == "No data" or ls_distance is None:
                    ls_distance = None
                
                if ring_type is None or ls_distance is None:
                    if system_name:
                        systems_needing_data.add(system_name)
            
            if not systems_needing_data:
                # All metadata complete in this result set
                print(f"[EDSM DEBUG] No systems need EDSM lookup - all metadata complete")
                return
            
            # Apply max_systems limit if specified (for large searches)
            systems_to_query = list(systems_needing_data)
            if max_systems and len(systems_to_query) > max_systems:
                systems_to_query = systems_to_query[:max_systems]
            
            print(f"[EDSM DEBUG] Systems to query: {systems_to_query}")
            
            # Use modified EDSM query that doesn't rely on get_incomplete_rings() filtering
            stats = self.edsm.fill_missing_metadata_for_systems_direct(systems_to_query)
            
            print(f"[EDSM DEBUG] EDSM query completed, stats: {stats}")
            
            if stats.get('materials_updated', 0) > 0:
                print(f"[EDSM] ✓ Filled {stats['rings_updated']} rings ({stats['materials_updated']} materials)")
                
                # Refresh hotspot data from database to get updated metadata
                print(f"[EDSM DEBUG] Refreshing hotspot metadata from database")
                self._refresh_hotspot_metadata_from_db(hotspots)
            else:
                print(f"[EDSM] ℹ No updates applied (rings may not exist in EDSM)")
                
        except Exception as e:
            # EDSM fallback failure is non-critical - just log and continue
            log.error(f"[EDSM] ⚠ Fallback failed (non-critical): {e}")
            log.error(f"[EDSM DEBUG] Exception details: {type(e).__name__}: {str(e)}")
    
    def _refresh_hotspot_metadata_from_db(self, hotspots: List[Dict]):
        """
        Refresh metadata for hotspots from database after EDSM update.
        
        Modifies hotspot dicts in-place to include updated metadata.
        """
        try:
            print(f"[EDSM DEBUG] _refresh_hotspot_metadata_from_db called for {len(hotspots)} hotspots")
            
            import sqlite3
            conn = sqlite3.connect(self.user_db.db_path)
            cursor = conn.cursor()
            
            updated_count = 0
            
            for hotspot in hotspots:
                system_name = hotspot.get('systemName')
                body_name = hotspot.get('bodyName')
                material_name = hotspot.get('type')
                
                if not all([system_name, body_name, material_name]):
                    continue
                
                # Query updated metadata for this specific hotspot
                cursor.execute("""
                    SELECT ring_type, ls_distance, inner_radius, outer_radius, ring_mass, reserve_level
                    FROM hotspot_data
                    WHERE system_name = ? AND body_name = ? AND material_name = ?
                    LIMIT 1
                """, (system_name, body_name, material_name))
                
                row = cursor.fetchone()
                if row:
                    # Store original values for comparison
                    old_ring_type = hotspot.get('ring_type')
                    old_ls_distance = hotspot.get('ls_distance')
                    
                    # Update hotspot dict with fresh metadata
                    hotspot['ring_type'] = row[0] if row[0] else hotspot.get('ring_type')
                    hotspot['ls_distance'] = row[1] if row[1] else hotspot.get('ls_distance')
                    
                    # Format LS distance for display (whole numbers with comma separators)
                    if row[1] is not None:
                        try:
                            hotspot['ls'] = f"{int(float(row[1])):,}"
                        except (ValueError, TypeError):
                            hotspot['ls'] = row[1]
                    else:
                        hotspot['ls'] = hotspot.get('ls')
                    
                    hotspot['inner_radius'] = row[2] if row[2] else hotspot.get('inner_radius')
                    hotspot['outer_radius'] = row[3] if row[3] else hotspot.get('outer_radius')
                    hotspot['ring_mass'] = row[4] if row[4] else hotspot.get('ring_mass')
                    hotspot['reserve'] = row[5] if row[5] else hotspot.get('reserve')
                    
                    # Check if anything actually changed
                    if (old_ring_type != hotspot.get('ring_type')) or (old_ls_distance != hotspot.get('ls_distance')):
                        updated_count += 1
                        print(f"[EDSM DEBUG] Updated {system_name} {body_name}: LS {old_ls_distance} -> {hotspot.get('ls_distance')}, Type {old_ring_type} -> {hotspot.get('ring_type')}")
            
            conn.close()
            
            print(f"[EDSM DEBUG] Metadata refresh completed: {updated_count} hotspots updated")
            
        except Exception as e:
            log.error(f"[EDSM] ⚠ Error refreshing metadata: {e}")
            log.error(f"[EDSM DEBUG] Refresh exception: {type(e).__name__}: {str(e)}")
    
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
    
    def _resolve_spansh_system_name(self, system_name: str) -> Optional[str]:
        """Resolve system name to correct capitalization using Spansh API (case-insensitive)
        
        Args:
            system_name: System name to resolve (e.g., "sol" or "Sol")
            
        Returns:
            Correctly capitalized system name, or None if resolution fails
        """
        import requests
        
        candidate = system_name.strip()
        if not candidate:
            return None
        
        try:
            url = 'https://spansh.co.uk/api/systems/field_values/system_names'
            params = {'q': candidate}
            headers = {'User-Agent': 'EliteMining/4.79', 'Accept': 'application/json'}
            
            response = requests.get(url, params=params, headers=headers, timeout=30)
            if response.status_code != 200:
                return None
            
            data = response.json()
            values = data.get('values', [])
            
            if not values:
                return None
            
            # Find exact match (case-insensitive)
            candidate_lower = candidate.lower()
            for value in values:
                if isinstance(value, str) and value.strip().lower() == candidate_lower:
                    return value.strip()
            
            # If no exact match, return first result
            return values[0].strip() if values else None
            
        except Exception as e:
            log.error(f"[SPANSH] System name resolution failed: {e}")
            return None
    
    def _search_spansh_with_filters(self, reference_system: str, material_filter: str, specific_material: str, max_distance: float, max_results: int, reference_coords, ring_type_only: bool = False, is_cancelled=None) -> List[Dict]:
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

        Returns:
            List of hotspot-format dicts compatible with _update_results
        """
        import requests
        import time
        
        # Update status to show Spansh search is starting
        self.parent.after(0, lambda: self.status_var.set("Querying Spansh API...")
                          if self.parent.winfo_exists() and not (is_cancelled and is_cancelled()) else None)
        
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
            resolved_system = self._resolve_spansh_system_name(reference_system.strip())
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
                # Normal mode - add ring_signals filter for specific material searches
                # For "All Minerals", don't add ring_signals filter (Spansh requires a name field)
                # Client-side filtering will handle removing bodies without valid signals
                if not self._is_all_minerals(specific_material):
                    # Specific material selected - filter for that material
                    filters['ring_signals'] = [{
                        'comparison': '<=>', 
                        'count': [1, 9999],
                        'name': [specific_material]  # Single material as list
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
            all_results = []
            for page_num in range(max_pages):
                if is_cancelled and is_cancelled():
                    print(f"[SPANSH PAGINATION] Cancelled before page {page_num}, stopping")
                    break

                # Update status message for pagination (especially for "All Minerals" searches)
                if use_pagination and page_num > 0:
                    progress_msg = f"Fetching Spansh data... page {page_num + 1}/{max_pages}"
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
                all_results.extend(results)
                
                print(f"[SPANSH PAGINATION] Page {page_num}: Distance range {results[0].get('distance', 0):.1f} - {last_body_distance:.1f} LY")
                
                # Stop if we've gone beyond max_distance
                if last_body_distance >= max_distance:
                    print(f"[SPANSH PAGINATION] Reached max distance ({max_distance} LY) at page {page_num}, stopping")
                    break
            
            results = all_results
            
            # Convert to user_db format
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
                                print(f"[RING SEARCH] Found {len(materials_found)} hotspots in local DB for {system_name} {db_ring_name}")
                        except Exception as e:
                            log.error(f"[RING SEARCH] DB lookup error for {system_name} {ring_name}: {e}")
                        
                        # Fallback to Spansh signals if no local data
                        if not materials_found and signals:
                            for sig in signals:
                                sig_name = sig.get('name', '')
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
            
            print(f"[SPANSH] Converted {len(hotspots)} rings to hotspot format")
            
            # Update status: Spansh search succeeded
            self.parent.after(0, lambda: self._update_spansh_status("online"))
            
            return hotspots
            
        except requests.exceptions.Timeout:
            print("[SPANSH] Request timed out")
            self.parent.after(0, lambda: self.status_var.set("Spansh search timed out")
                              if not (is_cancelled and is_cancelled()) else None)
            # Update status: Spansh is offline/timing out
            self.parent.after(0, lambda: self._update_spansh_status("offline"))
            return []
        except requests.exceptions.RequestException as e:
            log.error(f"[SPANSH] API error: {e}")
            self.parent.after(0, lambda: self.status_var.set("Spansh API error")
                              if not (is_cancelled and is_cancelled()) else None)
            # Update status: Spansh has errors
            self.parent.after(0, lambda: self._update_spansh_status("offline"))
            return []
        except Exception as e:
            log.error(f"[SPANSH] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _search_spansh_rings(self, reference_system: str, ring_type: str, max_distance: float, max_results: int, reference_coords, is_cancelled=None) -> List[Dict]:
        """Search Spansh API for rings of a specific type (Any Ring mode)
        
        Args:
            reference_system: Name of reference system
            ring_type: Ring type filter (Icy, Rocky, Metallic, Metal Rich)
            max_distance: Maximum distance in light years
            max_results: Maximum number of results
            reference_coords: Reference system coordinates dict
            
        Returns:
            List of hotspot-format dicts for display in results table
        """
        import requests
        
        print(f"[SPANSH] Searching for {ring_type} rings within {max_distance}ly of {reference_system}")
        
        if not reference_coords:
            print("[SPANSH] No reference coordinates available")
            return []
        
        try:
            # Build Spansh API request
            # IMPORTANT: Do NOT use any filters - they all break the API
            # - 'rings' filter limits to ~25 bodies
            # - 'ring_type' filter doesn't actually filter
            # - 'distance' filter also limits to ~25 bodies
            # Instead: Get ALL bodies sorted by distance, filter client-side
            request_size = 5000  # Request max for best coverage
            payload = {
                'reference_system': reference_system,
                'size': request_size,
                'sort': [{'distance': {'direction': 'asc'}}],
                'filters': {}  # NO FILTERS - all done client-side
            }
            
            # Add full browser-like headers to avoid rate limiting
            # The sec-* headers are required for Spansh API to return full results
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Content-Type': 'application/json',
                'Origin': 'https://spansh.co.uk',
                'Referer': 'https://spansh.co.uk/bodies',
                'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin'
            }
            
            print(f"[SPANSH] Searching for {ring_type} rings within {max_distance}ly of {reference_system}")
            
            response = tracked_request('spansh', requests.post,
                'https://spansh.co.uk/api/bodies/search',
                json=payload,
                headers=headers,
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            
            bodies = data.get('results', [])
            total_count = data.get('count', 0)
            print(f"[SPANSH] API returned {len(bodies)} bodies (total available: {total_count})")
            
            # Convert to hotspot format, filtering by ring type CLIENT-SIDE
            # Many bodies won't have rings or won't have the ring type we want
            results = []
            seen_rings = set()  # Avoid duplicate rings
            skipped_type = 0
            skipped_dup = 0
            skipped_no_rings = 0
            
            for body in bodies:
                system_name = body.get('system_name', '')
                body_name = body.get('name', '')
                distance = body.get('distance', 0)
                ls_distance = body.get('distance_to_arrival', 0)
                rings = body.get('rings', [])
                # Extract actual system coordinates provided by Spansh API
                sys_x = body.get('system_x')
                sys_y = body.get('system_y')
                sys_z = body.get('system_z')
                body_coords = {'x': sys_x, 'y': sys_y, 'z': sys_z} if sys_x is not None else None

                # Skip bodies beyond max distance (client-side filter)
                if distance > max_distance:
                    continue
                
                # Skip bodies without rings
                if not rings:
                    skipped_no_rings += 1
                    continue
                
                for ring in rings:
                    ring_type_actual = ring.get('type', '')
                    ring_name = ring.get('name', '')
                    
                    # Filter by ring type (skip if not matching, or if "All" is selected)
                    if ring_type != 'All' and ring_type_actual != ring_type:
                        skipped_type += 1
                        continue
                    
                    # Create unique key to avoid duplicates
                    ring_key = f"{system_name}|{ring_name}"
                    if ring_key in seen_rings:
                        skipped_dup += 1
                        continue
                    seen_rings.add(ring_key)
                    
                    # Get hotspot signals if available
                    signals = ring.get('signals', [])
                    hotspot_info = ""
                    hotspot_count = 0
                    if signals:
                        # Format as "Material (count), Material (count)" like normal search
                        signal_parts = []
                        for s in signals:
                            name = s.get('name', '')
                            count = s.get('count', 1)
                            hotspot_count += count
                            if name:
                                signal_parts.append(f"{name} ({count})")
                        # Show first 3 materials
                        hotspot_info = ", ".join(signal_parts[:3])
                        if len(signal_parts) > 3:
                            hotspot_info += f" +{len(signal_parts)-3}"
                    
                    # Format LS distance for display
                    ls_display = "No data"
                    if ls_distance and ls_distance > 0:
                        try:
                            ls_display = f"{int(float(ls_distance)):,}"
                        except (ValueError, TypeError):
                            ls_display = "No data"
                    
                    # Extract reserve level from body data
                    reserve_level = body.get('reserve_level', '')
                    
                    # Format as hotspot result
                    result = {
                        'system': system_name,
                        'systemName': system_name,
                        'body': body_name,
                        'bodyName': ring_name,
                        'ring': ring_name,
                        'ring_type': translate_ring_type(ring_type_actual),
                        'distance': f"{distance:.1f}" if distance > 0 else "0.0",
                        'ls': ls_display,
                        'ls_distance': round(ls_distance, 2) if ls_distance else None,
                        'material': hotspot_info if hotspot_info else t('ring_finder.no_hotspot_data'),
                        'count': hotspot_count if hotspot_count else 0,
                        'overlap': '',
                        'res_site': '',
                        'reserve': translate_reserve_level(reserve_level) if reserve_level else '-',
                        'source': 'spansh',
                        'data_source': 'spansh',
                        'coords': body_coords,
                    }
                    results.append(result)
                    
                    # Don't break early - collect all results, limit at the end
            
            # Sort by distance (use float conversion since distance is stored as string)
            results.sort(key=lambda x: float(x.get('distance', '9999')))
            
            bodies_with_rings = len(bodies) - skipped_no_rings
            print(f"[SPANSH] {len(bodies)} bodies checked, {bodies_with_rings} have rings, {skipped_no_rings} without rings")
            print(f"[SPANSH] Found {len(results)} {ring_type} rings (skipped {skipped_type} wrong type, {skipped_dup} duplicates)")
            print(f"[SPANSH] Found {len(results)} results")
            
            # Update status: Spansh search succeeded
            self.parent.after(0, lambda: self._update_spansh_status("online"))
            
            return results
            
        except requests.exceptions.Timeout:
            print("[SPANSH] Request timed out")
            self.parent.after(0, lambda: self.status_var.set(t('ring_finder.spansh_timeout'))
                              if not (is_cancelled and is_cancelled()) else None)
            # Update status: Spansh is offline/timing out
            self.parent.after(0, lambda: self._update_spansh_status("offline"))
            return []
        except requests.exceptions.RequestException as e:
            log.error(f"[SPANSH] API error: {e}")
            self.parent.after(0, lambda: self.status_var.set(t('ring_finder.spansh_error'))
                              if not (is_cancelled and is_cancelled()) else None)
            # Update status: Spansh has errors
            self.parent.after(0, lambda: self._update_spansh_status("offline"))
            return []
        except Exception as e:
            log.error(f"[SPANSH] Unexpected error: {e}")
            return []

    def _convert_spansh_to_hotspots(self, spansh_rings: List[Dict], reference_coords) -> List[Dict]:
        """Convert Spansh ring results to the standard hotspot format used by user database searches
        
        This makes Spansh results go through the same display logic as normal searches,
        so Hotspots, Overlaps, RES, etc. columns are populated from the local database.
        
        Args:
            spansh_rings: List of ring results from Spansh API
            reference_coords: Reference system coordinates for distance calculation
            
        Returns:
            List of hotspot-format dicts compatible with _update_results
        """
        from material_utils import abbreviate_material
        
        results = []
        
        for ring in spansh_rings:
            system_name = ring.get('system', '')
            body_name = ring.get('body', '')
            ring_name = ring.get('ring', '')
            ring_type = ring.get('ring_type', 'No data')
            distance = ring.get('distance', 0)
            ls_distance = ring.get('ls_distance')
            
            if not system_name or not ring_name:
                continue
            
            # Format LS distance for display
            ls_display = "No data"
            if ls_distance is not None and ls_distance != "No data":
                try:
                    ls_display = f"{int(float(ls_distance)):,}"
                except (ValueError, TypeError):
                    ls_display = "No data"
            
            # Look up hotspots from local database for this ring
            hotspot_display = "-"
            hotspot_count = 0
            try:
                # Strip the system name prefix from ring_name to match database format
                # Spansh returns: "Antliae Sector IR-W c1-4 A 5 A Ring"
                # Database stores: "A 5 A Ring"
                db_ring_name = ring_name
                if ring_name.lower().startswith(system_name.lower()):
                    db_ring_name = ring_name[len(system_name):].strip()
                
                db_hotspots = self.user_db.get_body_hotspots(system_name, db_ring_name)
                if db_hotspots:
                    formatted_parts = []
                    for h in db_hotspots:
                        material = h.get('material_name', '')
                        count = h.get('hotspot_count', 1)
                        hotspot_count += count
                        if material:
                            abbrev = abbreviate_material(material)
                            formatted_parts.append(f"{abbrev} ({count})")
                    
                    if formatted_parts:
                        hotspot_display = ", ".join(formatted_parts[:4])
                        if len(formatted_parts) > 4:
                            hotspot_display += f" +{len(formatted_parts)-4}"
                        print(f"[SPANSH DB LOOKUP] Formatted: {hotspot_display}")
            except Exception as e:
                log.error(f"[SPANSH] Error looking up hotspots for {system_name} {ring_name}: {e}")
            
            # Create result in standard format (same as _search_user_database_first)
            result = {
                'system': system_name,
                'systemName': system_name,
                'body': body_name,
                'bodyName': ring_name,  # Use ring_name as bodyName for display
                'ring': ring_name,
                'ring_type': translate_ring_type(ring_type),
                'type': hotspot_display,  # This populates Hotspots column
                'ls': ls_display,
                'ls_distance': ls_distance,
                'distance': f"{distance:.1f}" if distance > 0 else "0.0",
                'reserve': "No data",
                'has_hotspots': hotspot_count > 0,
                'count': hotspot_count,
                'data_source': 'Spansh',
                'source': 'Spansh',
            }
            results.append(result)

        return results

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
        """
        from system_finder_api import SystemFinderAPI
        system_names = list({h.get('system', h.get('systemName', '')) for h in hotspots})
        system_names = [s for s in system_names if s]
        pp_cache = SystemFinderAPI._batch_get_powerplay(system_names)

        # Stashed for _update_results to reuse when building the PowerPlay column, so a
        # matched row shows real data instead of "No data" when the EDDN cache is empty
        # for it. Reset every search so stale results never leak in.
        self._spansh_pp_enrichment = {}

        if use_spansh and pp_state in ('Exploited', 'Fortified', 'Stronghold', 'Unoccupied'):
            # max_distance is already widened to 500 LY by _search_worker for these states
            spansh_pp = SystemFinderAPI._fetch_spansh_powerplay_systems(
                reference_system, max_distance, pp_power, pp_state, is_cancelled=is_cancelled)
            to_persist = {}
            for sys_name, entry in spansh_pp.items():
                cached = pp_cache.get(sys_name)
                if SystemFinderAPI._spansh_pp_should_replace_cache(entry, cached):
                    pp_cache[sys_name] = entry
                    self._spansh_pp_enrichment[sys_name] = entry
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
        return filtered

    def _get_hotspots(self, reference_system: str, material_filter: str, specific_material: str, confirmed_only: bool, max_distance: float, max_results: int = None, data_source: str = None, ring_type_only_active: bool = False, is_cancelled=None) -> List[Dict]:
        """Get hotspot data based on user's data source selection"""
        
        # Get user's data source preference (or force database for auto-search)
        if getattr(self, '_force_database', False):
            data_source = "database"
            self._force_database = False  # Reset flag after use
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
            user_results = self._search_user_database_first(reference_system, material_filter, specific_material, max_distance, db_limit, is_cancelled=is_cancelled)
            print(f"[SEARCH] User database returned {len(user_results)} results")
        
        # Query Spansh if selected
        if data_source in ["spansh", "both"]:
            # Check if we should use cached Spansh results (e.g., after save to database)
            if getattr(self, '_use_cached_spansh', False) and getattr(self, '_cached_spansh_results', None):
                spansh_results = self._cached_spansh_results
                print(f"[SEARCH] Using cached Spansh results: {len(spansh_results)} entries")
                self._use_cached_spansh = False  # Reset flag after use
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
                        self.current_system_coords,
                        ring_type_only=ring_type_only_active,
                        is_cancelled=is_cancelled
                    )
                    print(f"[SEARCH] Spansh returned {len(spansh_results)} results")
                    # Cache the Spansh results for potential reuse
                    self._cached_spansh_results = spansh_results
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
    
    def _search_user_database_first(self, reference_system: str, material_filter: str, specific_material: str, max_distance: float, max_results: int = None, is_cancelled=None) -> List[Dict]:
        """Search user database first for confirmed hotspots, return results in _update_results compatible format"""
        try:
            # Get user database hotspots
            user_hotspots = self._get_user_database_hotspots(reference_system, material_filter, specific_material, max_distance, is_cancelled=is_cancelled)
            
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
                
                # Debug: Check conversion for Delkar 7A entries
                if system_name == "Delkar" and "7 A" in body_name:
                    hotspot_ring_type = hotspot.get('ring_type', 'Missing')
                    hotspot_material = hotspot.get('type', 'Missing')
                    print(f"CONVERSION: {system_name} {body_name} -> material: {hotspot_material} | ring_type: {hotspot_ring_type}")
                
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

    def _get_user_database_hotspots(self, reference_system: str, material_filter: str, specific_material: str, max_distance: float, is_cancelled=None) -> List[Dict]:
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
                        reference_coords = self._get_system_coords_from_edsm(reference_system)
                        if reference_coords:
                            print(f" DEBUG: Found reference system {reference_system} coordinates from EDSM API")
                        else:
                            print(f" DEBUG: Reference system {reference_system} not found in any database or EDSM, will show all results without distance filtering")
            
            with sqlite3.connect(self.user_db.db_path) as conn:
                cursor = conn.cursor()
                
                # Get systems within range for optimization if we have reference coordinates
                systems_in_range = None
                if reference_coords and max_distance < 1000:  # Only pre-filter for specific distance searches
                    # coord_cache is populated as a side effect here with {system: {x,y,z}} for
                    # every system found, so the per-row loop below can reuse them instead of
                    # re-querying galaxy_systems.db one connection at a time for each miss.
                    systems_in_range = self._find_systems_in_range(reference_coords, max_distance, coord_out=coord_cache)
                    
                    if systems_in_range is None:
                        systems_in_range = [reference_system]
                        print(f" DEBUG: No systems found in range, starting with reference system '{reference_system}'")
                    
                    if systems_in_range:
                        # PRIORITY FIX: Get all systems that have hotspots in the database
                        cursor.execute('''
                            SELECT DISTINCT system_name FROM hotspot_data
                        ''')
                        systems_with_hotspots = set(row[0] for row in cursor.fetchall())
                        
                        # Separate systems into priority (has hotspots) and non-priority
                        priority_systems = [s for s in systems_in_range if s in systems_with_hotspots]
                        non_priority_systems = [s for s in systems_in_range if s not in systems_with_hotspots]
                        
                        # Cap non-priority systems to prevent search hanging, but keep ALL priority systems
                        LIMIT = 5000
                        if len(priority_systems) + len(non_priority_systems) > LIMIT:
                            slots_remaining = max(0, LIMIT - len(priority_systems))
                            non_priority_systems = non_priority_systems[:slots_remaining]
                        
                        # Combine: priority systems first, then non-priority
                        systems_in_range = priority_systems + non_priority_systems
                        
                        # Always include reference system itself (distance = 0 LY)
                        if reference_system not in systems_in_range:
                            systems_in_range.append(reference_system)
                
                # Favourites Only: search exactly the systems that hold favourite rings (no radius pre-filter)
                if getattr(self, '_favourites_search', False):
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
                        # Update status to show no results found
                        try:
                            self.status_label.config(text=f"No systems found within search criteria for '{reference_system}'. Try adjusting your search terms.")
                        except:
                            pass
                        return []
                
                material_matches = 0
                systems_with_coords = 0
                systems_without_coords = 0
                processed_count = 0
                max_process_limit = 10000  # Hard limit to prevent infinite processing
                
                for system_name, body_name, material_name, hotspot_count, x_coord, y_coord, z_coord, coord_source, ls_distance, reserve_level, ring_type_db, inner_radius, outer_radius in results:
                    if is_cancelled and is_cancelled():
                        break
                    try:
                        # Safety: Stop processing if we've hit the limit
                        processed_count += 1
                        if processed_count > max_process_limit:
                            print(f" DEBUG: Hit processing limit ({max_process_limit}) - stopping to prevent hang")
                            break
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
                                    edsm_coords = self._get_system_coords_from_edsm(system_name)
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
                            cursor.execute(
                                'SELECT material_name, hotspot_count FROM hotspot_data '
                                'WHERE system_name = ? AND body_name = ? AND hotspot_count > 0',
                                (system_name, body_name))
                            ring_mats = sorted(
                                cursor.fetchall(),
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
                
                # Sort by distance first, then LS distance for practical mining workflow
                if not self._is_all_minerals(material_filter):
                    # For specific materials, prioritize by hotspot count, then distance, then LS
                    user_hotspots.sort(key=lambda x: (-x.get('count', 0), x.get('distance') or 999.9, x.get('ls_distance') or 999999))
                else:
                    # For All Minerals, sort by distance, then LS distance (closest arrival points first)
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
    
    def _find_systems_in_range(self, reference_coords: Dict, max_distance: float, coord_out: Dict[str, Dict] = None) -> List[str]:
        """Find all systems within range using galaxy_systems.db spatial index

        coord_out: optional dict the caller passes in; populated here with
        {system_name: {x, y, z}} for every system this function already looked up, so callers
        that need coordinates for these systems (e.g. distance calculations) can reuse them
        instead of re-querying galaxy_systems.db one system at a time.
        """
        try:
            import sqlite3
            from pathlib import Path
            
            # Use bundled galaxy database
            script_dir = Path(self.app_dir) if self.app_dir else Path(__file__).parent
            galaxy_db_path = script_dir / "data" / "galaxy_systems.db"
            
            if not galaxy_db_path.exists():
                return []
                
            systems_in_range = []
            
            with sqlite3.connect(str(galaxy_db_path)) as conn:
                cursor = conn.cursor()
                
                # Use spatial index for efficient range queries
                # Create bounding box for spatial search
                x_min = reference_coords['x'] - max_distance
                x_max = reference_coords['x'] + max_distance
                y_min = reference_coords['y'] - max_distance
                y_max = reference_coords['y'] + max_distance
                z_min = reference_coords['z'] - max_distance
                z_max = reference_coords['z'] + max_distance
                
                # Add LIMIT to prevent query timeout on large searches
                cursor.execute("""
                    SELECT name, x, y, z FROM systems 
                    WHERE x BETWEEN ? AND ? 
                    AND y BETWEEN ? AND ? 
                    AND z BETWEEN ? AND ?
                    LIMIT 50000
                """, (x_min, x_max, y_min, y_max, z_min, z_max))
                
                results = cursor.fetchall()
                
                # Calculate actual distance and filter - store as (name, distance) tuples
                systems_with_distances = []
                for name, x, y, z in results:
                    system_coords = {'x': x, 'y': y, 'z': z}
                    distance = self._calculate_distance(reference_coords, system_coords)

                    if distance <= max_distance:
                        systems_with_distances.append((name, distance))
                        if coord_out is not None:
                            coord_out[name] = system_coords
                
                # Sort by distance (closest first) before converting to name-only list
                systems_with_distances.sort(key=lambda x: x[1])
                systems_in_range = [name for name, dist in systems_with_distances]
                
                # Also check user database for visited systems within range
                try:
                    with sqlite3.connect(self.user_db.db_path) as user_conn:
                        user_cursor = user_conn.cursor()
                        
                        # Get all visited systems with coordinates
                        user_cursor.execute("""
                            SELECT system_name, x_coord, y_coord, z_coord 
                            FROM visited_systems
                            WHERE x_coord IS NOT NULL
                        """)
                        
                        user_systems_in_range = 0
                        for system_name, x, y, z in user_cursor.fetchall():
                            system_coords = {'x': x, 'y': y, 'z': z}
                            distance = self._calculate_distance(reference_coords, system_coords)

                            if distance <= max_distance and system_name not in systems_in_range:
                                systems_in_range.append(system_name)
                                user_systems_in_range += 1
                                if coord_out is not None:
                                    coord_out[system_name] = system_coords
                        
                        # ALSO check hotspot_data table for systems with hotspots
                        # This ensures newly scanned hotspots are found immediately
                        # Use bounding box filter for efficiency (like galaxy database query)
                        x_min = reference_coords['x'] - max_distance
                        x_max = reference_coords['x'] + max_distance
                        y_min = reference_coords['y'] - max_distance
                        y_max = reference_coords['y'] + max_distance
                        z_min = reference_coords['z'] - max_distance
                        z_max = reference_coords['z'] + max_distance
                        
                        user_cursor.execute("""
                            SELECT DISTINCT system_name, x_coord, y_coord, z_coord 
                            FROM hotspot_data
                            WHERE x_coord IS NOT NULL
                            AND x_coord BETWEEN ? AND ?
                            AND y_coord BETWEEN ? AND ?
                            AND z_coord BETWEEN ? AND ?
                        """, (x_min, x_max, y_min, y_max, z_min, z_max))
                        
                        hotspot_systems_added = 0
                        for system_name, x, y, z in user_cursor.fetchall():
                            if system_name in systems_in_range:
                                continue
                            system_coords = {'x': x, 'y': y, 'z': z}
                            distance = self._calculate_distance(reference_coords, system_coords)

                            if distance <= max_distance:
                                systems_in_range.append(system_name)
                                hotspot_systems_added += 1
                                if coord_out is not None:
                                    coord_out[system_name] = system_coords
                        
                except Exception:
                    pass
                
                return systems_in_range
                        
        except Exception:
            pass
            
        return []
        
    def _get_system_coords_from_edsm(self, system_name: str) -> Optional[Dict]:
        """Get system coordinates from EDSM API as fallback"""
        try:
            # Use ChatGPT's recommended endpoint - api-v1/systems (plural)
            url = "https://www.edsm.net/api-v1/systems"
            params = {
                "systemName": system_name,
                "showCoordinates": 1
            }

            response = requests.get(url, params=params, timeout=15, headers={"User-Agent": "EliteMining/5.1.3"})
            
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

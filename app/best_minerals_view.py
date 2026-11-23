# -*- coding: utf-8 -*-
"""
Best Minerals to Mine: live sell prices for a system's hotspot minerals, and Auto Prices.
Mixed into RingFinder (ring_finder.py).
"""
import logging
import threading
import tkinter as tk
from tkinter import ttk
from typing import Dict, List

from core.constants import MENU_COLORS
from column_visibility_helper import displayed_column
from ui.striped_treeview import StripedTreeview
from ui.theme import modern_color
from ui.themed_checkbox import ThemedCheckbutton

try:
    from localization import t
except Exception:
    def t(key, **kwargs):
        return key

# Same logger name as ring_finder.py so log lines keep their source
log = logging.getLogger('ring_finder')


class BestMineralsMixin:
    def _rank_minerals_inputs(self, scope: str):
        """Work out what to price for the selected row: (system_name, fetch_materials,
        extra_candidates, mineral_ring_types), or None (status set) if nothing to rank.

        scope 'ring' = only the clicked ring's hotspot minerals; 'system' = every hotspot
        mineral known anywhere in that row's system (same scope as Auto Prices)."""
        selection = self.results_tree.selection()
        if not selection:
            self.status_var.set(t('ring_finder.no_selection'))
            return None

        values = self.results_tree.item(selection[0], 'values')
        if not values or len(values) < 9:
            return None

        system_name = values[2]

        if scope == 'ring':
            ring_type = self._ring_type_rev_map.get(values[6], values[6])
            materials = self._parse_materials_from_hotspots(values[8])
            if not materials:
                self.status_var.set(t('ring_finder.no_hotspot_minerals'))
                return None

            full_materials = list(dict.fromkeys(self._expand_abbreviated_materials(m) for m in materials))

            # Non-hotspot minerals (e.g. Osmium) mineable in this one ring's type - same
            # "Also check" picker as the system-wide ranking, just scoped to the single
            # ring type already sitting in this row instead of a whole-system DB query.
            extra_candidates = [mat for mat in self.NON_HOTSPOT_RING_MINERALS.get(ring_type, [])
                                if mat not in full_materials]

            # Every mineral here (hotspot or "also check") comes from this one row's ring
            # type - so mining method lookup only ever needs to consider that single type.
            mineral_ring_types = {mat: {ring_type} for mat in full_materials + extra_candidates}
        else:
            try:
                hotspot_rows = self.user_db.get_system_hotspots(system_name)
            except Exception:
                hotspot_rows = []
            full_materials = list(dict.fromkeys(
                self._expand_abbreviated_materials(row['material_name'])
                for row in hotspot_rows if row.get('material_name')
            ))
            if not full_materials:
                self.status_var.set(t('ring_finder.no_hotspot_minerals'))
                return None

            # Ring type(s) each hotspot mineral was actually found in, in this system - a
            # mineral like Platinum can be a laser-mine in one ring type and core-only in
            # another, so mining method needs to be checked per ring type, not per mineral.
            mineral_ring_types: Dict[str, set] = {}
            for row in hotspot_rows:
                mat = row.get('material_name')
                rt = row.get('ring_type')
                if mat and rt:
                    mineral_ring_types.setdefault(self._expand_abbreviated_materials(mat), set()).add(rt)

            # Non-hotspot minerals (e.g. Osmium) mineable somewhere in this system, based on
            # its known ring types - offered via the popup's "Also check" picker since
            # hotspot-based ranking can never surface them on its own.
            ring_types_present = {row['ring_type'] for row in hotspot_rows if row.get('ring_type')}
            extra_candidates = sorted(dict.fromkeys(
                mat for ring_type in ring_types_present
                for mat in self.NON_HOTSPOT_RING_MINERALS.get(ring_type, [])
                if mat not in full_materials
            ))
            for mat in extra_candidates:
                mineral_ring_types[mat] = {rt for rt in ring_types_present
                                            if mat in self.NON_HOTSPOT_RING_MINERALS.get(rt, [])}

        # Minerals the user previously ticked in "Also check" (e.g. always wants Osmium
        # tracked) - fetch them upfront alongside the hotspot minerals, so they're
        # already in the ranked table without having to reopen the picker every time.
        try:
            from config import load_also_check_minerals
            always_check = set(load_also_check_minerals())
        except Exception:
            always_check = set()
        preselected_extras = [mat for mat in extra_candidates if mat in always_check]
        return system_name, full_materials + preselected_extras, extra_candidates, mineral_ring_types

    def _cached_rank_results(self, system_name: str, fetch_materials: List[str]):
        """Prefetched prices (from the "prefetch on jump" toggle) if they already cover
        every mineral with an actual priced hit, else None. A prefetch miss (no price
        found, e.g. the jump fetch ran before Ardent/Spansh had indexed the station)
        doesn't count as covered - the caller should do a fresh live fetch instead of
        showing that stale empty result forever."""
        prefetched = getattr(self, '_prefetched_prices', {}).get(system_name)
        if prefetched is None:
            return None
        priced_materials = {mat for mat, best, _ in prefetched if best}
        if not set(fetch_materials).issubset(priced_materials):
            return None
        cached = [(mat, best, priced_rows) for mat, best, priced_rows in prefetched if mat in fetch_materials]
        cached.sort(key=lambda r: r[1].get('sellPrice', 0) if r[1] else -1, reverse=True)
        return cached

    def _rank_minerals_for_system(self, scope: str = 'ring'):
        """Open the Best Minerals to Mine dialog for the selected row."""
        inputs = self._rank_minerals_inputs(scope)
        if inputs is None:
            return
        system_name, fetch_materials, extra_candidates, mineral_ring_types = inputs

        cached_results = self._cached_rank_results(system_name, fetch_materials)
        if cached_results is not None:
            self.status_var.set(t('ring_finder.ranking_complete').format(system=system_name))
            self._show_mineral_ranking_dialog(system_name, cached_results, extra_candidates=extra_candidates, mineral_ring_types=mineral_ring_types, scope=scope)
            return

        self.status_var.set(t('ring_finder.ranking_minerals').format(system=system_name))
        self._show_ranking_wait_dialog(system_name, scope)
        threading.Thread(target=self._rank_minerals_worker, args=(system_name, fetch_materials, extra_candidates, mineral_ring_types, scope), daemon=True).start()

    def _show_ranking_wait_dialog(self, system_name: str, scope: str = 'system'):
        """Show a small "please wait" dialog while the mineral ranking worker fetches live prices."""
        from config import scaled_font, load_theme

        current_theme = load_theme()
        if current_theme == "elite_orange":
            bg, fg = "#1e1e1e", "#ff8c00"
        else:
            bg, fg = MENU_COLORS["bg"], MENU_COLORS["fg"]

        dialog = tk.Toplevel(self.parent)
        dialog.withdraw()

        try:
            from app_utils import get_app_icon_path
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
        except Exception:
            pass

        dialog.title(t('ring_finder.rank_minerals_title'))
        dialog.resizable(False, False)
        dialog.configure(bg=bg)

        frame = tk.Frame(dialog, bg=bg, padx=30, pady=25)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=t('ring_finder.ranking_wait').format(system=system_name),
                 bg=bg, fg=fg, font=scaled_font(9)).pack()

        dialog.update_idletasks()
        from ui.dialogs import center_window
        center_window(dialog, self.parent.winfo_toplevel())
        dialog.deiconify()
        dialog.attributes('-topmost', True)
        dialog.lift()
        dialog.focus_force()
        try:
            dialog.grab_set()
        except Exception:
            pass

        self._ranking_wait_dialog = dialog

    def _fetch_mineral_prices(self, system_name: str, materials: List[str]):
        """Fetch best sell price per mineral concurrently; returns [(mat, best, priced_rows)]
        sorted by best price. Blocking - call from a worker thread."""
        from marketplace_api import MarketplaceAPI
        from concurrent.futures import ThreadPoolExecutor

        results = []
        with ThreadPoolExecutor(max_workers=min(len(materials), 4)) as pool:
            # search_buyers (Ardent's /imports) - stations that buy this commodity FROM
            # the player, i.e. where a miner can actually sell it. search_sellers is the
            # opposite direction (stations selling TO players, for buying commodities).
            # 7-day window instead of the 2-day default - Rank Minerals/Find Best Mining
            # System cover quieter systems than the Commodity Market tab, which keeps its
            # own tighter filter.
            futures = {pool.submit(MarketplaceAPI.search_buyers, mat, system_name, None, 7, False): mat for mat in materials}
            for future in futures:
                mat = futures[future]
                try:
                    rows = future.result()
                except Exception:
                    rows = []
                priced_rows = [r for r in rows if r.get('sellPrice', 0) > 0]
                best = max(priced_rows, key=lambda r: r.get('sellPrice', 0)) if priced_rows else None
                # Keep every priced row too, so the "in-system only" toggle can re-rank
                # against local-system stations without a second live fetch.
                results.append((mat, best, priced_rows))

        results.sort(key=lambda r: r[1].get('sellPrice', 0) if r[1] else -1, reverse=True)
        return results

    def _rank_minerals_worker(self, system_name: str, materials: List[str], extra_candidates: List[str] = None, mineral_ring_types: Dict[str, set] = None, scope: str = 'system'):
        """Background worker: fetch best sell price per mineral, concurrently.

        extra_candidates: non-hotspot minerals mineable somewhere in this system (see
        NON_HOTSPOT_RING_MINERALS) - offered via the popup's "Also check" picker, not
        fetched here. Only fetched on-demand if the user actually ticks one."""
        results = self._fetch_mineral_prices(system_name, materials)
        self.parent.after(0, lambda: self._show_mineral_ranking_dialog(system_name, results, extra_candidates=extra_candidates, mineral_ring_types=mineral_ring_types, scope=scope))

    def _show_mineral_ranking_dialog(self, system_name: str, results: list, modal: bool = True, extra_candidates: List[str] = None, mineral_ring_types: Dict[str, set] = None, scope: str = 'system'):
        """Show a small dialog ranking hotspot minerals by best live sell price.

        modal=False is used by the "Auto Mineral Prices" post-jump popup - it shouldn't
        steal focus or stay pinned on top while the user is flying/scanning."""
        from config import scaled_font, load_theme, scaled_px

        wait_dialog = getattr(self, '_ranking_wait_dialog', None)
        if wait_dialog is not None:
            try:
                if wait_dialog.winfo_exists():
                    wait_dialog.grab_release()
                    wait_dialog.destroy()
            except Exception:
                pass
            self._ranking_wait_dialog = None

        if not modal:
            # Each jump prefetch calls this again - close the previous auto-popup first,
            # or it stays open underneath/beside the new one and looks like the popup
            # never refreshed for the new system.
            self._close_auto_ranking_dialog()

        self.status_var.set(t('ring_finder.ranking_complete').format(system=system_name))

        dialog = tk.Toplevel(self.parent)
        dialog.withdraw()

        current_theme = load_theme()
        if current_theme == "elite_orange":
            bg, fg = "#1e1e1e", "#ff8c00"
        else:
            bg, fg = MENU_COLORS["bg"], MENU_COLORS["fg"]

        try:
            from app_utils import get_app_icon_path
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
        except Exception:
            pass

        dialog.title(t('ring_finder.rank_minerals_title'))
        dialog.resizable(True, True)
        dialog.configure(bg=bg)

        frame = tk.Frame(dialog, bg=bg, padx=15, pady=15)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=t('ring_finder.rank_minerals_for').format(system=system_name),
                 bg=bg, fg=fg, font=scaled_font(9, "bold")).pack(anchor="w")

        ring_name = ''
        if modal:
            sel = self.results_tree.selection()
            ring_vals = self.results_tree.item(sel[0], 'values') if sel else ()
            ring_name = ring_vals[3] if len(ring_vals) > 3 else ''

        def scope_text(current_scope):
            if current_scope == 'ring' and ring_name:
                return t('ring_finder.rank_scope_for_ring').format(ring=ring_name, system=system_name)
            return t('ring_finder.rank_scope_for_system').format(system=system_name)

        scope_row = tk.Frame(frame, bg=bg)
        scope_row.pack(fill="x", pady=(2, 10))
        scope_label = tk.Label(scope_row, text=scope_text(scope), bg=bg, fg=fg, font=scaled_font(9))
        scope_label.pack(side="left")

        # PowerPlay mode: restrict results to stations in system_name itself - for
        # undermining/reinforcing, the target system is the only place the player can
        # actually sell, so a galaxy-best price elsewhere isn't actionable. Re-ranks the
        # already-fetched priced_rows client-side, no extra live calls.
        from config import load_pp_mode, save_pp_mode
        pp_mode_var = tk.BooleanVar(value=load_pp_mode())

        def rows_for_mode(mat, best, priced_rows):
            if pp_mode_var.get():
                in_system = [r for r in priced_rows if r.get('systemName', '') == system_name]
                best_in_system = max(in_system, key=lambda r: r.get('sellPrice', 0)) if in_system else None
                return best_in_system
            return best

        # Ring type per mineral, from the same hotspot rows Rank Minerals parses from -
        # so a top-priced mineral that's actually core-only in this ring doesn't get mined
        # blind with a laser (e.g. Platinum is laser-mineable in Metallic but core-only
        # in Metal Rich - a single static "is this mineral core" flag can't tell the two
        # apart). Falls back to that static flag when the ring type isn't known.
        from report_generator import ReportGenerator
        core_materials = {mat for mat, info in ReportGenerator.MATERIAL_TPH_THRESHOLDS.items()
                          if info.get('is_core', False)}
        ring_types_by_mat = mineral_ring_types if mineral_ring_types is not None else {}

        def mining_method_for(mat):
            rts = ring_types_by_mat.get(mat, set())
            by_rt = {rt: self.MINING_METHOD_BY_RING.get(mat, {}).get(rt) for rt in rts}
            by_rt = {rt: method for rt, method in by_rt.items() if method}
            if not by_rt:
                is_core = mat in core_materials
                return t('ring_finder.mining_method_core') if is_core else t('ring_finder.mining_method_laser')

            parts = []
            for rt, method in sorted(by_rt.items()):
                rt_display = self._ring_type_map.get(rt, rt)
                if method == 'both':
                    parts.append(f"{t('ring_finder.mining_method_core')}/{rt_display}")
                    parts.append(f"{t('ring_finder.mining_method_laser')}/{rt_display}")
                else:
                    method_display = t('ring_finder.mining_method_core') if method == 'core' else t('ring_finder.mining_method_laser')
                    parts.append(f"{method_display}/{rt_display}")
            return ", ".join(parts)

        # Bulk-fetch PowerPlay data from the local EDDN cache for all result systems in one
        # query - same pattern as the Commodity Market tab (main.py _search_marketplace).
        from system_finder_api import SystemFinderAPI
        pp_names = list({best.get('systemName', '') for _, best, _ in results if best and best.get('systemName')} | {system_name})
        pp_data = SystemFinderAPI._batch_get_powerplay(pp_names) if pp_names else {}

        def powerplay_str_for(sys_name):
            pp_entry = pp_data.get(sys_name, {})
            pp_power = pp_entry.get('controlling_power', '')
            pp_state = pp_entry.get('power_state', '')
            if pp_power == '~none~':
                return pp_state or t('common.no_data')
            elif pp_power and pp_state:
                return f"{pp_power} / {pp_state}"
            elif pp_power:
                return pp_power
            elif pp_state:
                return pp_state
            return t('common.no_data')

        if current_theme == "elite_orange":
            tree_bg, tree_fg, header_bg = "#1e1e1e", "#ff8c00", "#1a1a1a"
            selection_bg, selection_fg = "#ff6600", "#000000"
        elif current_theme in ("modern", "modern_slate", "modern_orange"):
            tree_bg, tree_fg, header_bg = modern_color("#1D2228"), modern_color("#E6EAF0"), modern_color("#14171B")
            selection_bg, selection_fg = modern_color("#4A3520"), "#FFFFFF"
        else:
            tree_bg, tree_fg, header_bg = "#1e1e1e", "#e6e6e6", "#2a2a2a"
            selection_bg, selection_fg = "#0078d7", "#ffffff"

        style = ttk.Style()
        style.configure("RankMinerals.Treeview",
                       borderwidth=1, relief="solid", bordercolor="#333333",
                       background=tree_bg, foreground=tree_fg, fieldbackground=tree_bg,
                       font=scaled_font(9))
        style.configure("RankMinerals.Treeview.Heading",
                       borderwidth=1, relief="groove", background=header_bg, foreground=tree_fg,
                       padding=[5, 5], anchor="w", font=scaled_font(9, "bold"))
        style.map("RankMinerals.Treeview",
                 background=[('selected', selection_bg)],
                 foreground=[('selected', selection_fg)])

        options_row = tk.Frame(frame, bg=bg)
        options_row.pack(fill="x", pady=(0, 8))

        pp_check = ThemedCheckbutton(options_row, text=t('ring_finder.pp_mode_checkbox'),
                                  variable=pp_mode_var, bg=bg, fg=fg,
                                  activebackground=bg, activeforeground=fg,
                                  selectcolor=bg, font=scaled_font(9))
        pp_check.pack(side="left")

        # "Also check" picker: non-hotspot minerals mineable somewhere in this system
        # (e.g. Osmium in a Metal Rich ring) that hotspot-based ranking can't surface on
        # its own, since there's no hotspot row to parse for them. Only offered when the
        # caller computed candidates (system-wide "Rank Minerals in Entire System" - the
        # ring-scoped view and the ring type of any one row isn't known system-wide).
        extra_checked_vars = {}

        def save_also_check_selection():
            try:
                from config import save_also_check_minerals
                checked = [mat for mat, var in extra_checked_vars.items() if var.get()]
                save_also_check_minerals(checked)
            except Exception:
                pass

        def on_extra_mineral_toggle(mat):
            save_also_check_selection()
            if extra_checked_vars[mat].get():
                if not any(r[0] == mat for r in results):
                    self.status_var.set(t('ring_finder.ranking_minerals').format(system=system_name))
                    threading.Thread(target=fetch_extra_mineral, args=(mat,), daemon=True).start()
            else:
                results[:] = [r for r in results if r[0] != mat]
                populate_rows()

        def fetch_extra_mineral(mat):
            from marketplace_api import MarketplaceAPI
            try:
                rows = MarketplaceAPI.search_buyers(mat, system_name, None, 7, False)
            except Exception:
                rows = []
            priced_rows = [r for r in rows if r.get('sellPrice', 0) > 0]
            best = max(priced_rows, key=lambda r: r.get('sellPrice', 0)) if priced_rows else None
            self.parent.after(0, lambda: add_extra_mineral_result(mat, best, priced_rows))

        def add_extra_mineral_result(mat, best, priced_rows):
            if extra_checked_vars.get(mat) and not extra_checked_vars[mat].get():
                return  # unchecked again before the fetch finished
            results.append((mat, best, priced_rows))
            results.sort(key=lambda r: r[1].get('sellPrice', 0) if r[1] else -1, reverse=True)
            self.status_var.set(t('ring_finder.ranking_complete').format(system=system_name))
            populate_rows()

        if extra_candidates is None:
            extra_candidates = []

        def sync_extra_vars():
            # Reflect minerals already fetched upfront (previously saved "Also check"
            # picks) as ticked, instead of showing unchecked despite already being in
            # the ranked table below.
            already_fetched = {r[0] for r in results}
            extra_checked_vars.clear()
            for mat in extra_candidates:
                extra_checked_vars[mat] = tk.BooleanVar(value=mat in already_fetched)

        sync_extra_vars()

        # modal dialogs can switch scope, which changes the candidates, so always offer the button
        if extra_candidates or modal:
            def show_extra_mineral_picker():
                # A tk.Menu with add_checkbutton closes on every click, forcing the user
                # to reopen it after each pick - a persistent Toplevel stays open so they
                # can tick several minerals in one go.
                existing = getattr(dialog, '_extra_mineral_picker', None)
                if existing is not None:
                    try:
                        if existing.winfo_exists():
                            existing.lift()
                            existing.focus_force()
                            return
                    except Exception:
                        pass

                picker = tk.Toplevel(dialog)
                picker.withdraw()

                try:
                    from app_utils import get_app_icon_path
                    icon_path = get_app_icon_path()
                    if icon_path and icon_path.endswith('.ico'):
                        picker.iconbitmap(icon_path)
                except Exception:
                    pass

                picker.title(t('ring_finder.also_check_menu_title'))
                picker.resizable(False, False)
                picker.configure(bg=bg)

                picker_frame = tk.Frame(picker, bg=bg, padx=15, pady=12)
                picker_frame.pack(fill="both", expand=True)

                # Cap the checkbox list height and scroll instead of growing unbounded -
                # with 10+ ring-type minerals now offered, an uncapped list could spill
                # past the ranking dialog's own bottom edge into the window behind it.
                MAX_VISIBLE_ROWS = 8
                ROW_HEIGHT_PX = scaled_px(26)
                list_canvas = tk.Canvas(picker_frame, bg=bg, highlightthickness=0,
                                        width=scaled_px(220), height=min(len(extra_candidates), MAX_VISIBLE_ROWS) * ROW_HEIGHT_PX)
                list_canvas.pack(side="top", fill="both", expand=True)
                list_scrollbar = ttk.Scrollbar(picker_frame, orient="vertical", command=list_canvas.yview)
                if len(extra_candidates) > MAX_VISIBLE_ROWS:
                    list_scrollbar.place(in_=list_canvas, relx=1.0, rely=0, relheight=1.0, anchor="ne")
                    list_canvas.configure(yscrollcommand=list_scrollbar.set)

                checklist_frame = tk.Frame(list_canvas, bg=bg)
                list_canvas.create_window((0, 0), window=checklist_frame, anchor="nw")

                for mat in extra_candidates:
                    ThemedCheckbutton(checklist_frame, text=self._format_material_for_display(mat),
                                   variable=extra_checked_vars[mat],
                                   command=lambda m=mat: on_extra_mineral_toggle(m),
                                   bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                                   selectcolor=bg, font=scaled_font(9), anchor="w"
                                   ).pack(fill="x", anchor="w")

                checklist_frame.update_idletasks()
                list_canvas.configure(scrollregion=list_canvas.bbox("all"))

                def on_mousewheel(event):
                    if len(extra_candidates) > MAX_VISIBLE_ROWS:
                        list_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
                list_canvas.bind("<Enter>", lambda e: list_canvas.bind_all("<MouseWheel>", on_mousewheel))
                list_canvas.bind("<Leave>", lambda e: list_canvas.unbind_all("<MouseWheel>"))

                def follow_dialog_position(event=None):
                    try:
                        if picker.winfo_exists():
                            x = extra_check_btn.winfo_rootx()
                            y = extra_check_btn.winfo_rooty() + extra_check_btn.winfo_height() + 2
                            picker.geometry(f"+{x}+{y}")
                    except Exception:
                        pass

                def close_picker():
                    dialog._extra_mineral_picker = None
                    dialog._row_menu_open = False
                    dialog.unbind("<Configure>", follow_binding)
                    dialog.unbind("<Button-1>", click_away_binding)
                    try:
                        list_canvas.unbind_all("<MouseWheel>")
                    except Exception:
                        pass
                    picker.destroy()

                ttk.Button(picker_frame, text=t('common.close'), command=close_picker).pack(anchor="e", pady=(10, 0))
                picker.protocol("WM_DELETE_WINDOW", close_picker)

                def on_dialog_click_away(event):
                    # The picker is -topmost, so a click on the main ranking table (behind
                    # it) actually still lands on the picker at that screen location - the
                    # tree's own on_click() dismiss logic never fires. Watch clicks on the
                    # dialog itself and close the picker if the click was outside it.
                    try:
                        if not picker.winfo_exists():
                            return
                        px, py = picker.winfo_rootx(), picker.winfo_rooty()
                        pw, ph = picker.winfo_width(), picker.winfo_height()
                        if not (px <= event.x_root <= px + pw and py <= event.y_root <= py + ph):
                            close_picker()
                    except Exception:
                        pass
                click_away_binding = dialog.bind('<Button-1>', on_dialog_click_away, add='+')

                picker.update_idletasks()
                follow_dialog_position()
                picker.deiconify()
                picker.attributes('-topmost', True)
                picker.lift()
                picker.focus_force()
                # Reuses dialog's own keep_on_top() guard flag - without this, the
                # ranking dialog's 100ms re-lift loop buries this picker right back
                # underneath it every tick.
                dialog._row_menu_open = True

                # Stay anchored under the "+ Also Check" button as the parent dialog
                # is moved/resized, rather than floating independently once dropped.
                follow_binding = dialog.bind("<Configure>", follow_dialog_position, add="+")

                dialog._extra_mineral_picker = picker

            extra_check_btn = tk.Button(options_row, text=t('ring_finder.also_check_button'),
                                        command=show_extra_mineral_picker,
                                        bg="#2a2a2a", fg=fg, activebackground="#3a3a3a", activeforeground=fg,
                                        relief="ridge", bd=1, font=scaled_font(9), cursor="hand2")
            extra_check_btn.pack(side="left", padx=(15, 0))

        # Scope switch + Refresh only for the menu-opened dialog (modal): Auto Prices opens
        # this same dialog non-modal with no ring selected, so it never gets these. Both
        # reload the table in place instead of reopening the dialog.
        if modal:
            scope_state = {'scope': scope, 'busy': False}

            def btn_style():
                return dict(bg="#2a2a2a", fg=fg, activebackground="#3a3a3a", activeforeground=fg,
                            relief="ridge", bd=1, font=scaled_font(9), cursor="hand2")

            def switch_label():
                other = 'system' if scope_state['scope'] == 'ring' else 'ring'
                return t(f'ring_finder.rank_scope_switch_to_{other}')

            def apply_reload(new_scope, new_results, new_extras, new_ring_types, new_pp):
                if not dialog.winfo_exists():
                    return
                close_extra_mineral_picker_if_open()
                scope_state['scope'] = new_scope
                scope_label.config(text=scope_text(new_scope))
                results[:] = new_results
                extra_candidates[:] = new_extras
                ring_types_by_mat.clear()
                ring_types_by_mat.update(new_ring_types)
                pp_data.clear()
                pp_data.update(new_pp)
                sync_extra_vars()
                populate_rows()
                finish_reload()

            def finish_reload():
                scope_state['busy'] = False
                busy_label.config(text="")
                scope_btn.config(state="normal", text=switch_label())
                refresh_btn.config(state="normal")
                self.status_var.set(t('ring_finder.ranking_complete').format(system=system_name))

            def reload_worker(new_scope, force, fetch_materials, new_extras, new_ring_types):
                new_results = None if force else self._cached_rank_results(system_name, fetch_materials)
                if new_results is None:
                    new_results = self._fetch_mineral_prices(system_name, fetch_materials)
                names = list({best.get('systemName', '') for _, best, _ in new_results if best and best.get('systemName')} | {system_name})
                new_pp = SystemFinderAPI._batch_get_powerplay(names) if names else {}
                self.parent.after(0, lambda: apply_reload(new_scope, new_results, new_extras, new_ring_types, new_pp))

            def reload(new_scope, force):
                if scope_state['busy']:
                    return
                inputs = self._rank_minerals_inputs(new_scope)
                if inputs is None:
                    return
                _sys, fetch_materials, new_extras, new_ring_types = inputs
                scope_state['busy'] = True
                busy_label.config(text=t('ring_finder.rank_updating'))
                scope_btn.config(state="disabled")
                refresh_btn.config(state="disabled")
                self.status_var.set(t('ring_finder.ranking_minerals').format(system=system_name))
                threading.Thread(target=reload_worker, args=(new_scope, force, fetch_materials, new_extras, new_ring_types), daemon=True).start()

            scope_btn = self._rf_button(scope_row, text=switch_label(), **btn_style(),
                                  command=lambda: reload('system' if scope_state['scope'] == 'ring' else 'ring', False))
            scope_btn.pack(side="right")
            refresh_btn = self._rf_button(scope_row, text=t('ring_finder.rank_refresh'), **btn_style(),
                                    command=lambda: reload(scope_state['scope'], True))
            refresh_btn.pack(side="right", padx=(0, 8))
            busy_label = tk.Label(scope_row, text="", bg=bg, fg=fg, font=scaled_font(9))
            busy_label.pack(side="right", padx=(0, 8))

        tree_frame = tk.Frame(frame, bg=bg)
        tree_frame.pack(fill="both", expand=True)

        columns_header = ttk.Frame(tree_frame)
        columns_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self._cv_add_columns_button(columns_header, 'rank_minerals')

        columns = ("Mineral", "RingType", "Price", "Station", "Type", "Pad", "Dist", "LS", "Demand", "PowerPlay", "Updated")
        tree = StripedTreeview(tree_frame, columns=columns, show="headings", height=min(len(results), 8),
                            selectmode="browse", style="RankMinerals.Treeview")
        column_labels = {
            "Mineral": t('ring_finder.col_mineral'),
            "RingType": t('ring_finder.col_mining_method'),
            "Price": t('ring_finder.col_price'),
            "Station": t('ring_finder.col_station'),
            "Type": t('ring_finder.col_station_type'),
            "Pad": t('ring_finder.col_pad'),
            "Dist": t('ring_finder.col_dist'),
            "LS": t('ring_finder.col_ls'),
            "Demand": t('ring_finder.col_demand'),
            "PowerPlay": t('ring_finder.col_powerplay'),
            "Updated": t('ring_finder.col_updated'),
        }
        sort_reverse = {col: False for col in columns}

        def sort_by_column(col):
            data = [(tree.set(child, col), child) for child in tree.get_children('')]
            reverse = sort_reverse[col]

            if col in ("Dist", "LS", "Demand"):
                def sort_key(item):
                    val = item[0].replace(',', '')
                    try:
                        return float(val)
                    except ValueError:
                        return float('-inf') if reverse else float('inf')
                data.sort(key=sort_key, reverse=reverse)
            elif col == "Price":
                def sort_key(item):
                    val = item[0].replace(',', '').replace(' CR', '')
                    try:
                        return float(val)
                    except ValueError:
                        return float('-inf') if reverse else float('inf')
                data.sort(key=sort_key, reverse=reverse)
            else:
                data.sort(key=lambda item: item[0].lower(), reverse=reverse)

            for index, (_val, child) in enumerate(data):
                tree.move(child, '', index)

            sort_reverse[col] = not reverse
            arrow = " ▼" if reverse else " ▲"
            for c in columns:
                tree.heading(c, text=column_labels[c] + (arrow if c == col else ""),
                            command=lambda c=c: sort_by_column(c))

        for col in columns:
            tree.heading(col, text=column_labels[col], anchor="w", command=lambda c=col: sort_by_column(c))
        tree.column("Mineral", width=130, minwidth=40, anchor="w", stretch=False)
        tree.column("RingType", width=90, minwidth=40, anchor="w", stretch=False)
        tree.column("Price", width=110, minwidth=40, anchor="w", stretch=False)
        tree.column("Station", width=280, minwidth=40, anchor="w", stretch=False)
        tree.column("Type", width=110, minwidth=40, anchor="w", stretch=False)
        tree.column("Pad", width=50, minwidth=40, anchor="w", stretch=False)
        tree.column("Dist", width=80, minwidth=40, anchor="w", stretch=False)
        tree.column("LS", width=70, minwidth=40, anchor="w", stretch=False)
        tree.column("Demand", width=90, minwidth=40, anchor="w", stretch=False)
        tree.column("PowerPlay", width=200, minwidth=40, anchor="w", stretch=False)
        tree.column("Updated", width=90, minwidth=40, anchor="w", stretch=False)

        try:
            from config import load_rank_minerals_column_widths
            saved_widths = load_rank_minerals_column_widths()
            for col_name, width in saved_widths.items():
                try:
                    if width > 0:
                        current_minwidth = tree.column(col_name, "minwidth")
                        tree.column(col_name, width=max(width, current_minwidth))
                except Exception:
                    pass
        except Exception:
            pass

        def save_rank_minerals_widths(event=None):
            try:
                from config import save_rank_minerals_column_widths
                widths = {col: tree.column(col, "width") for col in columns}
                save_rank_minerals_column_widths(widths)
            except Exception:
                pass
        tree.bind("<ButtonRelease-1>", save_rank_minerals_widths, add='+')

        def fit_dialog_width_to_columns():
            shown = tree['displaycolumns']
            shown = columns if shown in ('#all', ('#all',)) else shown
            table_width = sum(tree.column(c, 'width') for c in shown) + v_scrollbar.winfo_reqwidth() + 6
            dialog.update_idletasks()
            dialog.geometry(f"{max(table_width + 30, 500)}x{dialog.winfo_height()}")

        self.setup_column_visibility(
            tree=tree, columns=columns,
            default_widths={"Mineral": 130, "RingType": 90, "Price": 110, "Station": 280, "Type": 110,
                            "Pad": 50, "Dist": 80, "LS": 70, "Demand": 90, "PowerPlay": 200, "Updated": 90},
            config_key='rank_minerals', use_displaycolumns=True, on_change=fit_dialog_width_to_columns, allow_reorder=True)

        mineral_by_row = {}
        system_by_row = {}
        source_by_row = {}
        from app_utils import format_market_source
        from ui.cell_tooltip import attach_cell_tooltip
        cell_tip_open = attach_cell_tooltip(tree, "Updated", lambda item: source_by_row.get(item, ''))

        def populate_rows():
            tree.delete(*tree.get_children())
            mineral_by_row.clear()
            system_by_row.clear()
            source_by_row.clear()
            for mat, best, priced_rows in results:
                row_best = rows_for_mode(mat, best, priced_rows)
                if row_best and row_best.get('sellPrice', 0) > 0:
                    price = f"{row_best.get('sellPrice', 0):,} CR"
                    station_system = row_best.get('systemName', '')
                    station = f"{row_best.get('stationName', '')} ({station_system})"
                    station_type = self._format_station_type(row_best.get('stationType'))
                    pad = self._format_pad_size(row_best.get('maxLandingPadSize'))
                    demand_val = row_best.get('demand')
                    demand = f"{demand_val:,}" if isinstance(demand_val, (int, float)) else "-"
                    dist = f"{row_best.get('distance', 0):.1f}" if row_best.get('distance') is not None else "-"
                    station_ls = row_best.get('distanceToArrival')
                    ls = f"{int(station_ls):,}" if station_ls is not None else "-"

                    powerplay = powerplay_str_for(station_system)
                    updated = self._format_data_age(row_best.get('updatedAt', ''))
                elif pp_mode_var.get():
                    price = t('ring_finder.no_data_in_system')
                    station = "-"
                    station_system = system_name
                    station_type = "-"
                    pad = "-"
                    demand = "-"
                    dist = "-"
                    ls = "-"
                    powerplay = powerplay_str_for(system_name)
                    updated = "-"
                else:
                    price = t('ring_finder.no_data')
                    station = "-"
                    station_system = ""
                    station_type = "-"
                    pad = "-"
                    demand = "-"
                    dist = "-"
                    ls = "-"
                    powerplay = "-"
                    updated = "-"
                mat_display = self._format_material_for_display(mat)
                ring_type_display = mining_method_for(mat)
                row_id = tree.insert("", "end", values=(mat_display, ring_type_display, price, station, station_type, pad, dist, ls, demand, powerplay, updated))
                mineral_by_row[row_id] = mat
                system_by_row[row_id] = station_system
                if row_best and row_best.get('sellPrice', 0) > 0:
                    source_by_row[row_id] = format_market_source(row_best)

        def on_pp_check_toggle():
            save_pp_mode(pp_mode_var.get())
            populate_rows()

        populate_rows()
        pp_check.configure(command=on_pp_check_toggle)

        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        tree.grid(row=1, column=0, sticky="nsew")
        v_scrollbar.grid(row=1, column=1, sticky="ns")
        h_scrollbar.grid(row=2, column=0, sticky="ew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(1, weight=1)

        def copy_system_for_row(row_id):
            system = system_by_row.get(row_id)
            if system:
                self.parent.clipboard_clear()
                self.parent.clipboard_append(system)
                self.parent.update_idletasks()
                self.status_var.set(f"Copied '{system}' to clipboard")

        def open_in_browser(url_template, system):
            import urllib.parse
            import webbrowser
            webbrowser.open(url_template.format(urllib.parse.quote(system)))

        def open_inara_and_fetch_pp(row_id, system):
            """Open Inara and fetch/store its PowerPlay data - same as the main
            Hotspots Finder table's PowerPlay-cell click (_open_inara/_fetch_pp_from_inara)."""
            open_in_browser("https://inara.cz/elite/starsystem/?search={}", system)

            def worker():
                from system_finder_api import SystemFinderAPI
                result = SystemFinderAPI.fetch_and_store_powerplay_from_inara(system)
                self.parent.after(0, lambda: apply_pp_result(row_id, system, result))
            threading.Thread(target=worker, daemon=True).start()

        def apply_pp_result(row_id, system, result):
            if not result or not tree.exists(row_id):
                return
            pp_power = result.get('controlling_power', '')
            pp_state = result.get('power_state', '')
            if pp_power == '~none~':
                pp_str = pp_state or t('common.no_data')
            elif pp_power and pp_state:
                pp_str = f"{pp_power} / {pp_state}"
            elif pp_power:
                pp_str = pp_power
            elif pp_state:
                pp_str = pp_state
            else:
                pp_str = t('common.no_data')
            vals = list(tree.item(row_id, 'values'))
            if len(vals) > 9:
                vals[9] = pp_str
                tree.item(row_id, values=vals)

        def close_extra_mineral_picker_if_open():
            """Dismiss the "Also check" picker on any click in the main ranking table -
            it's meant to be a quick add-a-mineral popup, not something left floating
            over the table it's covering."""
            picker = getattr(dialog, '_extra_mineral_picker', None)
            if picker is not None:
                try:
                    if picker.winfo_exists():
                        picker.event_generate('<<CloseRequest>>')
                except Exception:
                    pass

        def on_click(event):
            close_extra_mineral_picker_if_open()
            row_id = tree.identify_row(event.y)
            col = displayed_column(tree, tree.identify_column(event.x))
            if not row_id:
                return
            if col == "Station":
                tree.selection_set(row_id)
                copy_system_for_row(row_id)
            elif col == "PowerPlay":  # open Inara and refresh PP data, same as main table
                tree.selection_set(row_id)
                system = system_by_row.get(row_id, '')
                if system:
                    open_inara_and_fetch_pp(row_id, system)

        row_menu = tk.Menu(dialog, tearoff=0,
                           bg=MENU_COLORS["bg"] if current_theme != "elite_orange" else "#1e1e1e",
                           fg=MENU_COLORS["fg"] if current_theme != "elite_orange" else "#ff8c00",
                           activebackground=MENU_COLORS["activebackground"] if current_theme != "elite_orange" else "#ff6600",
                           activeforeground=MENU_COLORS["activeforeground"] if current_theme != "elite_orange" else "#000000",
                           font=scaled_font(9))
        row_menu.add_command(label=t('context_menu.copy_system'),
                             command=lambda: copy_system_for_row(tree.selection()[0]) if tree.selection() else None)
        row_menu.add_command(label=t('context_menu.open_inara'),
                             command=lambda: open_in_browser("https://inara.cz/elite/starsystem/?search={}", system_by_row.get(tree.selection()[0], '')) if tree.selection() else None)
        row_menu.add_command(label=t('context_menu.open_edsm'),
                             command=lambda: open_in_browser("https://www.edsm.net/en/system/id/0/name/{}", system_by_row.get(tree.selection()[0], '')) if tree.selection() else None)
        row_menu.add_command(label=t('context_menu.open_spansh'),
                             command=lambda: open_in_browser("https://spansh.co.uk/search/{}", system_by_row.get(tree.selection()[0], '')) if tree.selection() else None)

        def on_right_click(event):
            row_id = tree.identify_row(event.y)
            if row_id and system_by_row.get(row_id):
                tree.selection_set(row_id)
                dialog._row_menu_open = True
                try:
                    row_menu.tk_popup(event.x_root, event.y_root)
                finally:
                    dialog._row_menu_open = False

        tree.bind("<Button-1>", on_click)
        if not hasattr(self, '_context_handlers'):
            self._context_handlers = {}
        self._context_handlers['rank_minerals'] = on_right_click

        btn_frame = tk.Frame(frame, bg=bg)
        btn_frame.pack(fill="x", pady=(10, 0))

        def open_selected():
            selection = tree.selection()
            if not selection:
                return
            mat = mineral_by_row.get(selection[0])
            if mat:
                self._find_sell_station_impl(mineral_override=mat)

        def save_rank_minerals_geometry(event=None):
            try:
                from config import save_rank_minerals_window_geometry
                save_rank_minerals_window_geometry({'width': dialog.winfo_width(), 'height': dialog.winfo_height()})
            except Exception:
                pass

        def close_dialog():
            save_rank_minerals_geometry()
            dialog.destroy()

        ttk.Button(btn_frame, text=t('ring_finder.find_sell_station_btn'), command=open_selected).pack(side="left")
        ttk.Button(btn_frame, text=t('common.close'), command=close_dialog).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)

        dialog.update_idletasks()
        # Don't tie the floor to the table's full natural width (every column fixed-width,
        # no stretch) - that made the window unshrinkable. The horizontal scrollbar above
        # keeps the table usable below that width, so only guard against the button row.
        dialog.minsize(500, dialog.winfo_reqheight())

        from ui.dialogs import center_window
        center_window(dialog, self.parent.winfo_toplevel())

        # center_window resets the size to the content's natural size, so apply the saved
        # size afterwards and keep the window centered on the same spot.
        try:
            from config import load_rank_minerals_window_geometry
            saved_geom = load_rank_minerals_window_geometry()
            if saved_geom.get('width') and saved_geom.get('height'):
                dialog.update_idletasks()
                new_w = max(saved_geom['width'], 500)
                new_h = max(saved_geom['height'], dialog.winfo_reqheight())
                main = self.parent.winfo_toplevel()
                x = main.winfo_x() + (main.winfo_width() - new_w) // 2
                y = main.winfo_y() + (main.winfo_height() - new_h) // 2
                dialog.geometry(f"{new_w}x{new_h}+{x}+{y}")
        except Exception:
            pass
        dialog.deiconify()

        dialog._row_menu_open = False

        if not modal:
            # Non-modal auto-popup: needs its own topmost flag since the main app can
            # run with "always on top" itself - a plain lift() can't rise above another
            # topmost window. No grab/focus_force/keep-on-top loop though, so it never
            # fights for focus or blocks input after this one-time placement.
            dialog.attributes('-topmost', True)
            dialog.lift()
            # Tracked so disabling "Auto Mineral Prices" can close it immediately.
            self._auto_ranking_dialog = dialog
            return

        dialog.attributes('-topmost', True)
        dialog.lift()
        dialog.focus_force()
        try:
            dialog.grab_set()
        except Exception:
            pass

        def keep_on_top():
            try:
                if dialog.winfo_exists():
                    if not getattr(dialog, '_row_menu_open', False) and not cell_tip_open():
                        dialog.lift()
                    dialog.after(100, keep_on_top)
            except Exception:
                pass
        dialog.after(100, keep_on_top)

    def _on_auto_prices_ready(self, system_name: str, results: list, extra_candidates, mineral_ring_types):
        # A fetch started at StartJump can finish mid-jump; hold it until FSDJump arrives there
        if self.last_monitored_system == system_name:
            self._present_auto_prices(system_name, results, extra_candidates, mineral_ring_types)
        else:
            self._pending_auto_prices = (system_name, results, extra_candidates, mineral_ring_types)

    def _present_auto_prices(self, system_name: str, results: list, extra_candidates, mineral_ring_types):
        """Show prefetched prices on the text overlay if chosen and available, else in the popup"""
        text_overlay = None
        if self.prices_overlay_var.get():
            main_app = getattr(getattr(self, 'prospector_panel', None), 'main_app', None)
            text_overlay = getattr(main_app, 'text_overlay', None)
        if text_overlay is not None and text_overlay.overlay_enabled:
            self._close_auto_ranking_dialog()
            self.status_var.set(t('ring_finder.ranking_complete').format(system=system_name))
            # Only while still in supercruise after the jump - if the user already dropped, skip
            if getattr(self, '_in_sc_since_jump', False):
                duration_var = getattr(main_app, 'auto_prices_overlay_duration', None)
                duration_ms = int(duration_var.get() if duration_var is not None else 20) * 1000
                self._prices_overlay_active = True
                text_overlay.show_message(self._build_prices_overlay_text(system_name, results), duration_ms=duration_ms, ignore_sc_hide=True, wrap_width=1300)
                self.parent.after(duration_ms, lambda: setattr(self, '_prices_overlay_active', False))
            return
        self._show_mineral_ranking_dialog(system_name, results, modal=False, extra_candidates=extra_candidates, mineral_ring_types=mineral_ring_types)

    def _close_auto_ranking_dialog(self):
        """Close the non-modal Auto Prices popup if one is currently open."""
        auto_dialog = getattr(self, '_auto_ranking_dialog', None)
        if auto_dialog is not None:
            try:
                if auto_dialog.winfo_exists():
                    auto_dialog.destroy()
            except Exception:
                pass
            self._auto_ranking_dialog = None

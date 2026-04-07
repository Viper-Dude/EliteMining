"""
Fleet Carrier Tab - EliteMining
Displays live fleet carrier status populated from journal events via JournalParser.
All display strings use the localization system via t().
"""

import tkinter as tk
from tkinter import ttk
import logging
from datetime import datetime, timezone

log = logging.getLogger("EliteMining.FleetCarrierTab")

try:
    from localization import t
except ImportError:
    def t(key, **kwargs):
        val = key.split(".")[-1]
        return val.format(**kwargs) if kwargs else val


# Crew role -> localization key suffix
_CREW_ROLES = [
    ("Captain",           "crew_captain"),
    ("Commodities",       "crew_commodities"),
    ("Refuel",            "crew_refuel"),
    ("Repair",            "crew_repair"),
    ("Rearm",             "crew_rearm"),
    ("VoucherRedemption", "crew_voucher"),
    ("Exploration",       "crew_exploration"),
    ("VistaGenomics",     "crew_vista"),
    ("Outfitting",        "crew_outfitting"),
    ("Shipyard",          "crew_shipyard"),
    ("BlackMarket",       "crew_blackmarket"),
    ("CarrierFuel",       "crew_carrierfuel"),
    ("PioneerSupplies",   "crew_pioneer"),
    ("Bartender",         "crew_bartender"),
]


def _fmt_credits(value) -> str:
    if value is None:
        return "-"
    try:
        return f"{int(value):,} cr"
    except Exception:
        return str(value)


def _fmt_ts(ts_str: str) -> str:
    if not ts_str:
        return "-"
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d  %H:%M")
    except Exception:
        return ts_str


def _countdown(departure_str: str) -> str:
    if not departure_str:
        return ""
    try:
        dt = datetime.fromisoformat(departure_str.replace("Z", "+00:00"))
        diff = dt - datetime.now(timezone.utc)
        total_secs = int(diff.total_seconds())
        if total_secs <= 0:
            return t("fleet_carrier.jumping")
        mins, secs = divmod(total_secs, 60)
        hrs, mins  = divmod(mins, 60)
        if hrs:
            return t("fleet_carrier.countdown_hrs", h=hrs, m=mins)
        return t("fleet_carrier.countdown_mins", m=mins, s=secs)
    except Exception:
        return ""


class FleetCarrierTab(tk.Frame):
    """Fleet Carrier information tab widget."""

    _COUNTDOWN_INTERVAL = 5000

    def __init__(self, parent, **kwargs):
        try:
            from config import load_theme
            theme = load_theme()
        except Exception:
            theme = "elite_orange"

        if theme == "elite_orange":
            self.bg        = "#0a0a0a"
            self.fg        = "#ff8c00"
            self.fg_bright = "#ffa500"
            self.fg_dim    = "#666666"
            self.fg_inactive = "#888888"
            self.sect_bg   = "#141414"
            self.hdr_bg    = "#1e1e1e"
            self.bar_fill  = "#ff8c00"
            self.bar_empty = "#2a2a2a"
            self.ok_color  = "#00cc44"
            self.warn_color = "#ffaa00"
            self.err_color  = "#ff3333"
        else:
            self.bg        = "#1e1e1e"
            self.fg        = "#e6e6e6"
            self.fg_bright = "#ffffff"
            self.fg_dim    = "#888888"
            self.fg_inactive = "#999999"
            self.sect_bg   = "#252525"
            self.hdr_bg    = "#333333"
            self.bar_fill  = "#4CAF50"
            self.bar_empty = "#3a3a3a"
            self.ok_color  = "#4CAF50"
            self.warn_color = "#FFC107"
            self.err_color  = "#FF5252"

        super().__init__(parent, bg=self.bg, **kwargs)
        self._tracker = None
        self._countdown_job = None
        self._sv = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tracker(self, tracker):
        self._tracker = tracker
        tracker.set_on_updated(self._on_carrier_updated)
        cd = tracker.carrier_data
        if cd:
            self._refresh(cd)

    def _on_carrier_updated(self, carrier_data):
        try:
            self.after(0, lambda: self._refresh(carrier_data))
        except Exception as e:
            log.warning(f"FC tab update scheduling error: {e}")

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _sv_label(self, parent, key, default="-", font=None, fg=None, **kw):
        var = tk.StringVar(value=default)
        self._sv[key] = var
        return tk.Label(parent, textvariable=var,
                        bg=parent.cget("bg"), fg=fg or self.fg,
                        font=font or ("Helvetica", 10), **kw)

    def _section_header(self, parent, title_key, large=False):
        hdr = tk.Frame(parent, bg=self.hdr_bg)
        hdr.pack(fill="x", pady=(10, 2))
        font = ("Helvetica", 13, "bold") if large else ("Helvetica", 10, "bold")
        tk.Label(hdr, text=f"  {t(title_key)}", bg=self.hdr_bg, fg=self.fg_bright,
                 font=font, anchor="w").pack(fill="x", ipady=4)

    def _row(self, parent, label_key, sv_key, default="-", value_fg=None):
        row = tk.Frame(parent, bg=self.sect_bg)
        row.pack(fill="x", padx=8, pady=1)
        tk.Label(row, text=t(label_key), bg=self.sect_bg, fg=self.fg_dim,
                 font=("Helvetica", 9), width=22, anchor="w").pack(side="left")
        lbl = self._sv_label(row, sv_key, default, fg=value_fg or self.fg,
                             font=("Helvetica", 9), anchor="w")
        lbl.pack(side="left", fill="x", expand=True)

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = tk.Frame(self, bg=self.bg)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=self.bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._scroll_frame = tk.Frame(canvas, bg=self.bg)
        self._scroll_win = canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")

        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(self._scroll_win, width=e.width))
        self._scroll_frame.bind("<Configure>",
                                lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        sf = self._scroll_frame

        # Help banner
        help_frame = tk.Frame(sf, bg=self.hdr_bg)
        help_frame.pack(fill="x", padx=4, pady=(8, 4))
        tk.Label(
            help_frame,
            text=t("fleet_carrier.help_banner"),
            bg=self.hdr_bg, fg=self.fg_dim,
            font=("Helvetica", 8), justify="left", anchor="w", wraplength=600
        ).pack(fill="x", padx=10, ipady=4)

        self._build_status_section(sf)
        self._build_jump_section(sf)
        self._build_finance_section(sf)
        self._build_services_section(sf)
        self._build_cargo_section(sf)
        self._build_history_section(sf)

        self._no_data_lbl = tk.Label(
            sf, text=t("fleet_carrier.no_data"),
            bg=self.bg, fg=self.fg_dim, font=("Helvetica", 11), justify="center"
        )
        self._no_data_lbl.pack(pady=40)

        self._hint_lbl = tk.Label(
            sf, text=t("fleet_carrier.stats_hint"),
            bg=self.bg, fg=self.fg_dim, font=("Helvetica", 9), justify="center"
        )
        # shown only when location is known but stats not yet received

    def _build_status_section(self, parent):
        self._section_header(parent, "fleet_carrier.section_status", large=True)
        sect = tk.Frame(parent, bg=self.sect_bg)
        sect.pack(fill="x", padx=4, pady=2)

        self._row(sect, "fleet_carrier.label_name",      "status_name")
        self._row(sect, "fleet_carrier.label_location",  "status_system")
        self._row(sect, "fleet_carrier.label_docking",   "status_docking")
        self._row(sect, "fleet_carrier.label_jump_range","status_jump_range")

        fuel_row = tk.Frame(sect, bg=self.sect_bg)
        fuel_row.pack(fill="x", padx=8, pady=1)
        tk.Label(fuel_row, text=t("fleet_carrier.label_fuel"), bg=self.sect_bg, fg=self.fg_dim,
                 font=("Helvetica", 9), width=22, anchor="w").pack(side="left")
        self._fuel_text_lbl = tk.Label(fuel_row, text="-", bg=self.sect_bg,
                                       fg=self.fg, font=("Helvetica", 9), anchor="w")
        self._fuel_text_lbl.pack(side="left")

    def _build_jump_section(self, parent):
        self._section_header(parent, "fleet_carrier.section_jump")
        sect = tk.Frame(parent, bg=self.sect_bg)
        sect.pack(fill="x", padx=4, pady=2)
        self._row(sect, "fleet_carrier.label_destination", "jump_dest")
        self._row(sect, "fleet_carrier.label_body",        "jump_body")
        self._row(sect, "fleet_carrier.label_departure",   "jump_departure")
        self._row(sect, "fleet_carrier.label_countdown",   "jump_countdown")

    def _build_finance_section(self, parent):
        self._section_header(parent, "fleet_carrier.section_finance")
        sect = tk.Frame(parent, bg=self.sect_bg)
        sect.pack(fill="x", padx=4, pady=2)
        self._row(sect, "fleet_carrier.label_balance",   "fin_balance")
        self._row(sect, "fleet_carrier.label_available", "fin_available")
        self._row(sect, "fleet_carrier.label_reserve",   "fin_reserve")

        res_row = tk.Frame(sect, bg=self.sect_bg)
        res_row.pack(fill="x", padx=8, pady=1)
        tk.Label(res_row, text=t("fleet_carrier.label_reserve_pct"), bg=self.sect_bg,
                 fg=self.fg_dim, font=("Helvetica", 9), width=22, anchor="w").pack(side="left")
        self._reserve_pct_lbl = tk.Label(res_row, text="-", bg=self.sect_bg,
                                          fg=self.fg, font=("Helvetica", 9), anchor="w")
        self._reserve_pct_lbl.pack(side="left")

        tax_row = tk.Frame(sect, bg=self.sect_bg)
        tax_row.pack(fill="x", padx=8, pady=1)
        tk.Label(tax_row, text=t("fleet_carrier.label_tax_rates"), bg=self.sect_bg,
                 fg=self.fg_dim, font=("Helvetica", 9), width=22, anchor="w").pack(side="left")
        self._tax_lbl = tk.Label(tax_row, text="-", bg=self.sect_bg,
                                  fg=self.fg, font=("Helvetica", 9), anchor="w")
        self._tax_lbl.pack(side="left")

    def _build_services_section(self, parent):
        self._section_header(parent, "fleet_carrier.section_services")
        sect = tk.Frame(parent, bg=self.sect_bg)
        sect.pack(fill="x", padx=4, pady=2)

        # Help text explaining active/inactive colors
        tk.Label(sect, text=t("fleet_carrier.services_help"),
                 bg=self.sect_bg, fg=self.fg_dim,
                 font=("Helvetica", 8), anchor="w").pack(fill="x", padx=8, pady=(4, 0))

        self._service_labels = {}
        grid = tk.Frame(sect, bg=self.sect_bg)
        grid.pack(anchor="w", padx=8, pady=4)
        grid.columnconfigure(0, minsize=200)
        grid.columnconfigure(1, minsize=200)

        for i, (role, loc_key) in enumerate(_CREW_ROLES):
            col = i % 2
            row_idx = i // 2
            cell = tk.Frame(grid, bg=self.sect_bg)
            cell.grid(row=row_idx, column=col, sticky="w", padx=(0, 4), pady=2)
            dot = tk.Label(cell, text="\u25cf", fg=self.fg_dim, bg=self.sect_bg,
                           font=("Helvetica", 8))
            dot.pack(side="left")
            name_lbl = tk.Label(cell, text=t(f"fleet_carrier.{loc_key}"),
                                fg=self.fg_dim, bg=self.sect_bg, font=("Helvetica", 9))
            name_lbl.pack(side="left", padx=(5, 0))
            self._service_labels[role] = (dot, name_lbl, col)

    def _build_cargo_section(self, parent):
        self._section_header(parent, "fleet_carrier.section_cargo")
        sect = tk.Frame(parent, bg=self.sect_bg)
        sect.pack(fill="x", padx=4, pady=2)
        self._row(sect, "fleet_carrier.label_total_capacity", "cargo_total")
        self._row(sect, "fleet_carrier.label_cargo_used",     "cargo_used")
        self._row(sect, "fleet_carrier.label_free_space",     "cargo_free")
        self._row(sect, "fleet_carrier.label_crew_modules",   "cargo_crew")
        self._row(sect, "fleet_carrier.label_used_total",     "cargo_used_total")

    def _build_history_section(self, parent):
        self._section_header(parent, "fleet_carrier.section_history")
        self._history_frame = tk.Frame(parent, bg=self.sect_bg)
        self._history_frame.pack(fill="x", padx=4, pady=2)
        self._history_rows = []

    # ------------------------------------------------------------------
    # Data refresh
    # ------------------------------------------------------------------

    def _refresh(self, cd: dict):
        if not cd:
            return
        has_data = bool(cd.get("name") or cd.get("system"))
        if has_data:
            self._no_data_lbl.pack_forget()
        else:
            return

        # Show hint if location known but full stats not yet received
        has_stats = cd.get("name") is not None
        if has_stats:
            self._hint_lbl.pack_forget()
        else:
            self._hint_lbl.pack(pady=(0, 8))

        # Status
        name = cd.get("name") or "-"
        cs   = cd.get("callsign") or ""
        self._sv["status_name"].set(f"{name}  ({cs})" if cs else name)
        self._sv["status_system"].set(cd.get("system") or "-")

        docking = (cd.get("docking_access") or "-").capitalize()
        if cd.get("allow_notorious"):
            docking += f"  {t('fleet_carrier.notorious_allowed')}"
        self._sv["status_docking"].set(docking)

        jr_curr = cd.get("jump_range_curr")
        jr_max  = cd.get("jump_range_max")
        if jr_curr is not None:
            if jr_max:
                self._sv["status_jump_range"].set(
                    t("fleet_carrier.jump_range_fmt", curr=jr_curr, max=jr_max))
            else:
                self._sv["status_jump_range"].set(
                    t("fleet_carrier.jump_range_simple", curr=jr_curr))
        else:
            self._sv["status_jump_range"].set("-")

        fuel = cd.get("fuel_level")
        cap  = cd.get("fuel_capacity") or 1000
        self._fuel_text_lbl.config(
            text=t("fleet_carrier.fuel_fmt", fuel=fuel or 0, capacity=cap)
            if fuel is not None else "-")

        # Jump schedule — clear stale jump data if departure is in the past
        dep = cd.get('jump_departure_time')
        if dep:
            try:
                dt = datetime.fromisoformat(dep.replace('Z', '+00:00'))
                if (datetime.now(timezone.utc) - dt).total_seconds() > 300:
                    cd['jump_destination'] = None
                    cd['jump_body'] = None
                    cd['jump_departure_time'] = None
                    dep = None
            except Exception:
                pass
        dest = cd.get('jump_destination')
        self._sv["jump_dest"].set(dest or t("fleet_carrier.none_scheduled"))
        self._sv["jump_body"].set(cd.get("jump_body") or "-")
        dep = cd.get("jump_departure_time")
        self._sv["jump_departure"].set(_fmt_ts(dep) if dep else "-")
        self._sv["jump_countdown"].set(_countdown(dep) if dep else "-")
        if dep:
            self._schedule_countdown()

        # Finance
        self._sv["fin_balance"].set(_fmt_credits(cd.get("balance")))
        self._sv["fin_available"].set(_fmt_credits(cd.get("available_balance")))
        self._sv["fin_reserve"].set(_fmt_credits(cd.get("reserve_balance")))

        pct = cd.get("reserve_percent")
        if pct is not None:
            self._reserve_pct_lbl.config(text=f"{pct}%", fg=self.fg)
        else:
            self._reserve_pct_lbl.config(text="-", fg=self.fg_dim)

        rearm  = cd.get("tax_rearm")
        refuel = cd.get("tax_refuel")
        repair = cd.get("tax_repair")
        if rearm is not None:
            self._tax_lbl.config(
                text=t("fleet_carrier.tax_fmt", rearm=rearm, refuel=refuel, repair=repair))

        # Services — orange/white if active, grey if inactive
        crew_map = {c.get("CrewRole"): c for c in (cd.get("crew") or [])}
        for role, (dot, name_lbl, col) in self._service_labels.items():
            info      = crew_map.get(role, {})
            activated = info.get("Activated", False)
            enabled   = info.get("Enabled", False)
            active    = activated and enabled
            dot.config(fg=self.fg if active else self.fg_inactive)
            name_lbl.config(fg=self.fg if active else self.fg_inactive)

        # Cargo
        total   = cd.get("space_total")
        cargo   = cd.get("space_cargo") or 0
        crew_sp = cd.get("space_crew")  or 0
        free    = cd.get("space_free")
        used    = cargo + crew_sp
        self._sv["cargo_total"].set(t("fleet_carrier.units_fmt", n=total) if total else "-")
        self._sv["cargo_used"].set(t("fleet_carrier.units_fmt", n=cargo) if cargo else "-")
        self._sv["cargo_free"].set(t("fleet_carrier.units_fmt", n=free)  if free is not None else "-")
        self._sv["cargo_crew"].set(t("fleet_carrier.units_fmt", n=crew_sp) if crew_sp else "-")
        self._sv["cargo_used_total"].set(
            f"{used:,} / {total:,}" if total else "-")

        # Jump history
        for w in self._history_rows:
            w.destroy()
        self._history_rows.clear()
        history = cd.get("jump_history") or []
        if not history:
            lbl = tk.Label(self._history_frame,
                           text=f"  {t('fleet_carrier.no_jumps')}",
                           bg=self.sect_bg, fg=self.fg_dim, font=("Helvetica", 9), anchor="w")
            lbl.pack(fill="x", padx=8, pady=2)
            self._history_rows.append(lbl)
        else:
            for entry in history[:10]:
                row = tk.Frame(self._history_frame, bg=self.sect_bg)
                row.pack(fill="x", padx=8, pady=1)
                tk.Label(row, text=_fmt_ts(entry.get("timestamp", "")),
                         bg=self.sect_bg, fg=self.fg_dim, font=("Helvetica", 9),
                         width=20, anchor="w").pack(side="left")
                tk.Label(row, text=entry.get("system", "-"),
                         bg=self.sect_bg, fg=self.fg, font=("Helvetica", 9),
                         anchor="w").pack(side="left")
                self._history_rows.append(row)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _schedule_countdown(self):
        if self._countdown_job:
            try:
                self.after_cancel(self._countdown_job)
            except Exception:
                pass
        self._countdown_job = self.after(self._COUNTDOWN_INTERVAL, self._tick_countdown)

    def _tick_countdown(self):
        cd  = self._tracker.carrier_data if self._tracker else None
        dep = cd.get("jump_departure_time") if cd else None
        if dep:
            self._sv["jump_countdown"].set(_countdown(dep))
            self._schedule_countdown()
        else:
            self._sv["jump_countdown"].set("-")

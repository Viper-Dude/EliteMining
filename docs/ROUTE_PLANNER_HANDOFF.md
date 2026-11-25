# Route Planner — Handover

Start each new chat with: "Read docs/ROUTE_PLANNER_HANDOFF.md and continue with the next step in the progress table."

Planned 25 Nov 2026 (Claude, with the user), at commit `28543b3`. Built by Codex step by step. Line numbers refer to that commit.

## Goal

A simple, mining-focused route planner. Spansh does the plotting; EliteMining fills in everything it can from the journal, so the player only picks a destination.

**No over-engineering (the user's explicit requirement).** The user finds EDDiscovery's route finder over-engineered. Build only what each step lists, with as few new classes, settings and options as possible. No extra columns, options, caching layers, retries beyond the polling loop, or abstractions "for later". If something seems missing, name it and ask the user first.

## Settled Decisions

- **One new top-level tab, "Route"**, placed after Market: Mining | Hotspots | Market | **Route** | Systems | Fleet Carrier | Distance | VoiceAttack | Bookmarks | Settings.
- **Tab renames** (EN / DE): Hotspots Finder → Hotspots / Hotspots; Commodity Market → Market / Markt; Star Systems → Systems / Systeme; Distance Calculator → Distance / Entfernung; VoiceAttack Controls → VoiceAttack / VoiceAttack. New: Route / Route.
- **Other views choose where to go; the Route tab shows the one active route.** Views get "Plot route" in their right-click menu. A new plot replaces the active route after a yes/no confirmation. Only one route at a time.
- **Plotter: Spansh Galaxy Plotter only** (`generic/route`). No Neutron, Riches, Trade or Exobiology plotters, no local router.
- **Fleet Carrier route** (`fleetcarrier/route`) is a later phase 2, not part of this handover.
- **Left out on purpose:** coordinates and deviation columns, a routing-method choice, saving or exporting routes, multiple routes, EDSM lookup buttons.
- **EDSM** is used only as the existing coordinate fallback. Never call it on the UI thread.

## Spansh Galaxy Plotter API (confirmed 25 Nov 2026 from the website's own request)

Spansh's API is undocumented and run by one person. Keep traffic low: one plot at a time, no automatic re-plots. Use a generic User-Agent (`EliteMining/<version>`), never player details. The user may contact the Spansh author before release.

**Request:** `POST https://spansh.co.uk/api/generic/route`, `Content-Type: application/x-www-form-urlencoded`. The reply (HTTP 202) is a small JSON with the job id.

**Polling:** `GET https://spansh.co.uk/api/results/<job>`. HTTP 202 while running, 200 when done. EDDiscovery waits 2 s, doubling to at most 8 s. Add an overall timeout (about 2 minutes) and cancellation through `SearchControl`'s Stop button.

**Fields the website sends**, with the user's Type-11 Prospector ("lakonminer") as the example:

| Field | Example | EliteMining source |
|---|---|---|
| `source` | `10477373803` (Sol) | The website sends the system ID (id64). Current system ID = `SystemAddress` from the journal. Plain names such as `Sol` and `Paesia` worked in the live probe. |
| `destination` | `3657466647274` (Paesia) | Same as above |
| `is_supercharged` | 0 | 1 if a `JetConeBoost` event came after the last `FSDJump` |
| `use_supercharge` | 0 | Checkbox, default **on** |
| `use_injections` | 0 | Always 0 |
| `use_injections_when_required` | 0 | Checkbox, default off |
| `exclude_secondary` | 0 | Hidden, always **1** |
| `refuel_every_scoopable` | 1 | Hidden, always 1 |
| `reserve_size` | 0 | Hidden, always 0 |
| `fuel_power` | 2.45 | FSD lookup table (FSD size) |
| `fuel_multiplier` | 0.013 | FSD lookup table (FSD grade and type) |
| `optimal_mass` | 1997.514343 | Loadout FSD engineering modifier `FSDOptimalMass` if present, else the table's standard value |
| `max_fuel_per_jump` | 5.2 | Loadout FSD modifier `MaxFuelPerJump` if present, else the table value |
| `base_mass` | 601.325058 | Loadout `UnladenMass` (600.725058) + `FuelCapacity.Reserve` (0.6) |
| `tank_size` | 32 | Loadout `FuelCapacity.Main` |
| `internal_tank_size` | 0.6 | Loadout `FuelCapacity.Reserve` |
| `range_boost` | (empty) | Guardian FSD booster range from the loadout (table by booster size), empty if none |
| `ship_build` | SLEF JSON | `[{"header":{"appName":"EliteMining","appVersion":"<ver>"},"data":<Loadout event>}]` |
| `cargo` | 144 | Current cargo tons from the Cargo Monitor. |
| `algorithm` | `beam` | Hidden, always Beam. |
| `supercharge_multiplier` | 4 | The frontend sends 4 by default and can override it for specific FSDs. |
| `injection_multiplier` | 2 | The frontend sends 2 by default and can override it for specific FSDs. |
| `max_time` | omitted in probe | The frontend sends its plot time setting. The live probe succeeded with the field omitted. |

The website calculates the FSD values itself and sends them, so EliteMining must do the same. The FSD table needs one entry per FSD item (normal, pre-engineered and SCO drives): power constant, linear constant, standard optimal mass and standard max fuel per jump. Copy the values from an open-source source such as the Coriolis data repository (check its licence) and name the source in a comment.

The live probe used a synthetic ship after automatic approval review blocked sending journal-derived build data. With explicit FSD fields, the named Sol-to-Paesia plot queued and completed in six jumps. Omitting those fields as a group while retaining the synthetic SLEF returned HTTP 400, “ship details are invalid”. Individual field requirements and whether a full journal SLEF can substitute for the explicit fields were not tested. Send the explicit FSD fields. [Spansh frontend](https://spansh.co.uk/assets/elite-dangerous-gui-f1d8f22e101c2fd0c520103f601d1877.js)

**Results.** HTTP 202 returned `status: queued` during polling. HTTP 200 returned `status: ok` and the ordered stops under `result.jumps`, including the source at index 0. Each stop has `name`, `id64` (string), `distance` (incoming jump), `distance_to_destination`, `fuel_in_tank`, `fuel_used`, `must_refuel`, `has_neutron`, `is_scoopable`, `must_inject`, and `x`, `y`, `z`. Jumps left is derived as `len(jumps) - 1 - index`.

## Jump Range Without Spansh

The journal's `Loadout` event has `MaxJumpRange` (no cargo, just enough fuel for one jump). The current range is not written anywhere. FSD formula:

```
range = optimal_mass / mass * (max_fuel_per_jump / fuel_multiplier) ** (1 / fuel_power) + range_boost
mass  = base_mass + current fuel + cargo
```

Check values for the user's ship (no Guardian booster). Results must match within 0.05 ly:

| Case | Expected |
|---|---|
| Fuel 5.2 t, cargo 0 | 38.03 ly (journal `MaxJumpRange`) |
| Full tank 32 t, cargo 0 | 36.42 ly (EDDiscovery) |
| Full tank, cargo 144 t | 29.67 ly (EDDiscovery) |
| Full tank, cargo 344 t | about 23.6 ly |

Use this only for "jump range now" and rough "~N jumps" estimates. An estimate from straight-line distance is often one jump too low (the user's EDDiscovery test: 169.76 ly at 29.67 ly gave 7 jumps, not 6), so show it as "~N". Real routes always come from Spansh.

## Existing Code To Reuse

| Need | Where |
|---|---|
| Latest `Loadout` event | `CargoMonitor` already handles it for cargo capacity: `app/cargo_monitor.py:650`, `:1009` (startup scan), `:1448`. Keep the whole event, e.g. `self.latest_loadout`. |
| Journal events (FSDJump, JetConeBoost) | `CargoMonitor.add_journal_listener()` at `app/cargo_monitor.py:1301`. Don't add a second journal reader. |
| Current cargo, capacity, fuel | `CargoMonitor` (cargo, `max_cargo`, Status.json reading) |
| Spansh requests | Header and session pattern in `app/system_finder_api.py` |
| System name autocomplete | `app/system_autocomplete.py` |
| Current system, Home, Fleet Carrier shortcuts | `app/distance_calculator_tab.py` |
| Search with Stop | `ui/search_control.py` (`SearchControl`) |
| Table | `ui/striped_treeview.py`, `ColumnVisibilityMixin`, column widths through `config.py` |
| Background work with stale-result guard | Request-id pattern in `app/best_minerals_view.py` and `app/best_mining_view.py` |
| Clipboard copy | `_copy_to_clipboard` in `app/fleet_carrier_tab.py:184` |
| VoiceAttack variables | `app/va_variables.py`, `_atomic_write_text()` |
| In-game route jumps left (existing) | `app/main.py:5349` (NavRoute/FSDTarget polling), `app/journal_parser.py:1413`. That is the game's route, not ours. Keep them separate. |
| Settings | `_load_cfg()` / `update_config_value()` in `config.py` |

## Steps

Run the steps in order, one per chat where possible, one commit each (`git add -A`). Before each step, name the recommended model and effort and wait for the user to confirm. After each step, update the progress table.

### Step 0 — Confirm the open API details (light model, medium effort)

Write a dev-only script outside `app/` (for example `scripts/dev_spansh_route_probe.py`) that sends one `generic/route` request using the example values above and a real Loadout from the user's journal. Confirm:

1. Plain system names work for `source` and `destination`. If not, find how to get an id64 for a name (Spansh `api/search/systems` or similar).
2. The field names for cargo and algorithm, and the value for Beam. The user can also scroll to the bottom of the browser's Payload list to see them.
3. Whether the FSD fields are required, by also trying without them. Send them anyway if the website does.
4. The result JSON field names (system, id64, distance, remaining, jumps, fuel, refuel, neutron, scoopable).

Write the answers into this document (replace the "Step 0 confirms" notes) before step 2.

### Step 1 — Tab renames and Route tab placeholder (light model, medium effort)

- Change the `tabs.*` labels in `strings_en.json` and `strings_de.json` as listed above.
- Check that nothing finds a tab by its label text or remembers the open tab by position. Inserting Route after Market moves the later tabs by one.
- Check help pages and docs for the old names.
- Adding the empty Route tab can wait until step 3 if that's simpler. The rename should ship in its own commit either way.
- Patch note: one sentence about shorter tab names.

### Step 2 — `app/route_planner.py` core, no UI (strongest model, high effort)

- Keep the latest Loadout in `CargoMonitor`. Rebuild the ship data when a new Loadout arrives (ship swap, outfitting).
- FSD table plus Guardian booster table, `fsd_spec(loadout)`, and `jump_range(loadout, fuel, cargo)`.
- `build_slef(loadout)` and `build_route_form(...)`, which builds the form fields from the table above.
- Spansh client: `start_plot(form)` returns the job id; `poll(job, is_cancelled)` waits with backoff until done; then parse the stops.
- Active route state: stops, current index, source view and time. Save it through `config.py` so it survives a restart.
- Moving along: on each `FSDJump`, match `SystemAddress` (or `StarSystem`) to the next stop. A system that isn't in the route counts as off route; keep the index.
- `is_supercharged`: true after `JetConeBoost`, false after the next `FSDJump`.
- No Tk calls from the worker. All network work runs in a daemon thread.
- New check script `scripts/check_route_planner.py`: the jump range check values, the SLEF wrapper, the form fields from a Loadout fixture, polling with a fake HTTP layer (202, 202, 200), cancel and timeout, moving along and off route.

### Step 3 — Route tab UI, new module `app/route_tab.py` (strong model, high effort)

Read docs/UI_RULES.md and docs/MAIN_SPLIT_HANDOFF.md first. `main.py` only adds the notebook line.

- From and To boxes with autocomplete. From defaults to the current system.
- Two checkboxes: Use Supercharge (on), Use FSD Injections When Required (off).
- One line: "Jump range now: X ly (full hold: Y ly)".
- Plot with Stop (`SearchControl`).
- Table: current marker (▷), #, System, Jump (ly), Star (scoopable / neutron), Refuel, Jumps left. Totals underneath: jumps and ly travelled. Follow the table rules in AGENTS.md.
- "Copy next system" button and Clear. Transient messages via `_show_notice()`. Replacing a route asks with `centered_yesno_dialog`.
- Short help text with Spansh's two tips: target the next system rather than plotting to it in the galaxy map; if out of sync, plot to the next refuel stop first.
- Every new string goes in EN and DE. Theme colours from the active theme.

### Step 4 — "Plot route" from Sell My Hold (strong model, medium effort)

- `app/cargo_sell_planner.py` (Sell My Hold, inside the Market tab via `app/commodity_market_tab.py:46`). Add "Plot route" for the selected plan.
- One-stop plan: one plot. Two-stop plan: plot leg 1 with the current cargo, then leg 2 with the cargo left after the first sale, and join both legs into one route.
- Switch to the Route tab after plotting.

### Step 5 — "Plot route" in the other views (medium model, medium effort)

Right-click "Plot route" in: Where to Mine (`app/best_mining_view.py`), Best Prices (`app/best_minerals_view.py`), Merit Miner (`app/merit_miner_view.py`), Acquisition (`app/acquisition_view.py`), Ring Finder results, and Market search results. Cargo is always the current cargo. Optional: "~N jumps" on the selected row only, using the jump range calculation (no Spansh call).

### Step 6 — Cockpit support (strongest model, high effort)

Read docs/VOICEATTACK_RULES.md first.

- Optional setting: copy the next system to the clipboard after each jump.
- VoiceAttack variables for the next system and jumps left on our route. Use new file names; don't reuse the existing jumps-left variables, which follow the game's route.
- Optional text overlay line "Next: <system> (N jumps)". "Enable Text Overlay" is the master switch.
- A voice command needs a `.vap` change: insert the elements in `COMMAND_ELEMENT_ORDER` and remind the user to re-import. Ask the user before adding one.

## Progress

| Step | Status | Commit | Notes |
|---|---|---|---|
| 0 Confirm API details | API verified with synthetic input | This commit | Names, cargo and Beam fields, polling, and stop schema verified. Omitting explicit FSD fields returned HTTP 400. Real journal request blocked by approval review. |
| 1 Tab renames | Done | This commit | EN and DE labels and help references updated. Positional tab selection is in use, so the Route placeholder and index updates are deferred to step 3. UI verification pending. |
| 2 Route core | Done | This commit | Route and journal checks passed. One live Spansh plot using the actual Type-11 Loadout with `appName: EliteMining` returned seven jumps from Sol to Paesia. |
| 3 Route tab UI | Not started | | |
| 4 Sell My Hold | Not started | | |
| 5 Other views | Not started | | |
| 6 Cockpit support | Not started | | |

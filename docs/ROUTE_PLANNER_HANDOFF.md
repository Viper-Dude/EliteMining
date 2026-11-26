# Route Planner — Handover

Start each new chat with: "Read docs/ROUTE_PLANNER_HANDOFF.md and continue with the next step in the progress table."

Planned 25 Nov 2026 (Claude, with the user), at commit `28543b3`. Built by Codex step by step. Line numbers refer to that commit.

## Goal

A simple, mining-focused route planner. Spansh does the plotting; EliteMining fills in everything it can from the journal, so the player only picks a destination.

**No over-engineering (the user's explicit requirement).** The user finds EDDiscovery's route finder over-engineered. Build only what each step lists, with as few new classes, settings and options as possible. No extra columns, options, caching layers, retries beyond the polling loop, or abstractions "for later". If something seems missing, name it and ask the user first.

## Settled Decisions

- **One new top-level tab, "Route"**, placed after Market: Mining | Hotspots | Market | **Route** | Star Systems | Fleet Carrier | Distance Calculator | VoiceAttack | Bookmarks | Settings.
- **Tab renames** (EN / DE): Hotspots Finder → Hotspots / Hotspots; Commodity Market → Market / Markt; VoiceAttack Controls → VoiceAttack / VoiceAttack. New: Route / Route. Star Systems / Sternensysteme and Distance Calculator / Entfernungsrechner keep their full names.
- **Other views choose where to go; the Route tab shows the one active route.** Views get "Plot route" in their right-click menu. Plotting replaces the active route only after the new plot succeeds.
- **Plotter: Spansh Galaxy Plotter only** (`generic/route`). No Neutron, Riches, Trade or Exobiology plotters, no local router.
- **Fleet Carrier route** (`fleetcarrier/route`) is a later phase 2, not part of this handover.
- **Left out on purpose:** coordinates and deviation columns, a routing-method choice, multiple routes, a text overlay line, EDSM lookup buttons.
- **Export and import** of the active route as Spansh JSON, Spansh CSV or a plain system list (.txt), added after the original plan; sample files are in `scripts/fixtures/`.
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
| `use_injections` | 0 | 1 when a grade is selected and **Every jump** is checked, otherwise 0 |
| `use_injections_when_required` | 0 | 1 when a grade is selected and **Every jump** is unchecked, otherwise 0 |
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
| `injection_multiplier` | 2 | Basic sends 1.25, Standard 1.5 and Premium 2. The frontend defaults to 2 and supports per-FSD injection overrides. None are defined in its current drive data. |
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

Run the steps in order, one per chat where possible. Commit once when the route planner is finished (`git add -A`). See Codex Only in AGENTS.md for model recommendations. Before each step, name the recommended effort and wait for the user to confirm. After each step, update the progress table.

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
- Moving along: on each `FSDJump`, match `SystemAddress` (or `StarSystem`) to the first matching later stop, even if the player skips stops. A system that isn't in the route counts as off route; keep the index.
- `is_supercharged`: true after `JetConeBoost`, false after the next `FSDJump`.
- No Tk calls from the worker. All network work runs in a daemon thread.
- New check script `scripts/check_route_planner.py`: the jump range check values, the SLEF wrapper, the form fields from a Loadout fixture, polling with a fake HTTP layer (202, 202, 200), cancel and timeout, moving along and off route.

### Step 3 — Route tab UI, new module `app/route_tab.py` (Sol 6.2, high effort)

Read docs/UI_RULES.md and docs/MAIN_SPLIT_HANDOFF.md first. `main.py` only adds the notebook line.

- Inserting Route at position 3 breaks `main_app.notebook.select(3)` in `app/ring_finder.py:3874` (meant for Systems). Change that call to select the Systems tab frame instead of an index. Calls to positions 0–2 (`commodity_market_tab.py:1007`, `main.py:11447`, `mining_missions_tab.py:674/685`, `ring_finder.py:4085/4133`) are unaffected.

- From and To boxes with autocomplete. From defaults to the current system.
- Two checkboxes: Use Supercharge (on), Use FSD Injections When Required (off).
- One line in the game's own galaxy-map format: "Jump range: X (Y) ly". X = current range with current fuel (Status.json) and current cargo (`jump_range()`); Y = the Loadout's `MaxJumpRange`. Example from the game: "Jump range: 50.64 (52.91) ly".
- Plot with Stop (`SearchControl`).
- Table: # (with the ▷ current marker inside it), System, Jump (ly), Star (scoopable / neutron), Refuel, Jumps left. Totals underneath: jumps and ly travelled. Follow the table rules in AGENTS.md.
- "Copy next system" button and Clear. Transient messages via `_show_notice()`. Importing a route asks for confirmation when it would replace the active route.
- Short help text with Spansh's two tips: target the next system rather than plotting to it in the galaxy map; if out of sync, plot to the next refuel stop first.
- Every new string goes in EN and DE. Theme colours from the active theme.

**User test feedback (25 Nov 2026, first live plot worked: Wregoe JT-Q c18-27 → Sol, 8 jumps).** Changes to make:

1. **"Use Current System" button** beside the From box. Reuse the Distance tab's pattern and string (`distance_calculator.use_current`, `_distance_use_current_system` in `app/distance_calculator_tab.py:179`).
2. **System boxes too wide.** Use the Distance tab's layout (`app/distance_calculator_tab.py:95-122`): From and To on two rows, the entry column with a fixed minimum width (`px(250)`), not stretching, and the buttons beside the entry.
3. **Remove the separate marker column.** The user couldn't tell what the empty first column was. Show the ▷ marker inside the # column (for example "▷ 3") instead.
4. **Column chooser missing.** Use `ColumnVisibilityMixin` like the other tables: `setup_column_visibility(...)` plus the Columns button via `_cv_add_columns_button` (see `app/cargo_sell_planner.py:245/265`). That replaces the tab's own width-saving code. Make the System column's default width fit long names such as "Col 285 Sector MQ-M b38-5".
5. **FSD injection grade, like the game's "FSD Boost" setting.** Replace the "Use FSD Injections When Required" checkbox with one dropdown: Off / Basic (+25%) / Standard (+50%) / Premium (+100%). Off sends both injection flags as 0 and disables **Every jump**. Basic, Standard and Premium send `injection_multiplier` 1.25 / 1.5 / 2 respectively. **Every jump** selects which injection flag is sent as 1 (see the fields table). The Spansh website always sends 2 and has no grade choice, so first confirm with one test plot that Spansh accepts 1.25 and 1.5 (fewer or equal jumps than Off, more than or equal to Premium) and check in the website's JavaScript whether some FSDs override the multiplier. If Spansh ignores other values, keep the checkbox and tell the user.
6. **Tooltips** (requested by the user) on: Use Current System (reuse `tooltips.use_current`), Use Supercharge, the FSD injection dropdown, the jump range line (X = with current fuel and cargo, Y = maximum), Plot, Copy next system, Clear, and the table headers (`add_header_tooltips` from `ui/tooltip.py`, as in `app/cargo_sell_planner.py`). EN and DE strings.
7. **Cargo box** (like EDDiscovery's Route Finder and the game's Cargo Mass slider), so the player can plan a trip for a full hold while still empty. Place the Cargo box and the jump range line together on one row, so it's visible that changing cargo changes the range (EDDiscovery shows "Max jump" and "Cargo" side by side): `Jump range: 29.67 (38.03) ly   Cargo: [144] t`. The range stays read-only text and updates immediately when the Cargo value changes. The Cargo box is filled with the current cargo and following it until the player types a value; limited to 0 – cargo capacity. The jump range line and the Route tab's own Plot use this value. "Plot route" from other views (Sell My Hold, Where to Mine and so on) keeps using the real current cargo. **No editable Max jump box:** the Galaxy Plotter works from the ship build, not a range number, so a typed range would be ignored.
8. **From the Spansh results page** (compared 25 Nov 2026):
   - **Inject column** from `must_inject` ("Yes" when the player must use an FSD injection before that jump). Needed now that the injection dropdown exists; without it the player can't know when to synthesise. Header tooltip, EN and DE.
   - **Estimated time** in the totals line ("8 jumps · 361.69 ly · about 16 min"). The Spansh Galaxy Plotter calculates one minute per jump plus two minutes per refuel stop, excluding the starting system.
   - **Right-click on a route row: "Copy system name"**, like the copy icon on every Spansh row. Reuse an existing copy string.
   - **Left out on purpose:** Done checkboxes (the route moves forward by itself from the journal), Remaining (ly), Fuel Left and Fuel Used (refuel stops are already marked), and row colours.

The live Type-11 test from Wregoe JT-Q c18-27 to Sol returned the same 12 jumps without injections at all four grades. Forcing injections on that route for the diagnostic returned 10 jumps with Basic and 8 with Standard, confirming Spansh applies both multipliers. With a grade selected, **Every jump** plans injections for every jump without a neutron boost. The checkbox starts unchecked, so injections are used only when a jump cannot otherwise be made.

### Step 4 — "Plot route" from Sell My Hold (Sol 6.2, medium effort)

- `app/cargo_sell_planner.py` (Sell My Hold, inside the Market tab via `app/commodity_market_tab.py:46`). Add "Plot route" for the selected plan.
- One-stop plan: one plot. Two-stop plan: plot leg 1 with the current cargo, then leg 2 with the cargo left after the first sale, and join both legs into one route.
- Add a Plot route button beside the search controls and the same action in the sale plan’s right-click menu. Switch to the Route tab immediately so it shows progress and Stop.

### Step 5 — "Plot route" in the other views (Sol 6.2, medium effort)

Right-click "Plot route" in: Where to Mine (`app/best_mining_view.py`), Best Prices (`app/best_minerals_view.py`), Merit Miner (`app/merit_miner_view.py`), Acquisition (`app/acquisition_view.py`), Ring Finder results, and Market search results. Cargo is always the current cargo. Optional: "~N jumps" on the selected row only, using the jump range calculation (no Spansh call).

### Step 6 — Cockpit support (Sol 6.2, high effort)

Read docs/VOICEATTACK_RULES.md first.

- Optional setting: copy the next system to the clipboard after each jump.
- VoiceAttack variables for the next system and jumps left on our route. Use new file names; don't reuse the existing jumps-left variables, which follow the game's route.
- No text overlay line: the user decided on 25 Nov 2026 that the route stays off the text overlay.
- A voice command needs a `.vap` change: insert the elements in `COMMAND_ELEMENT_ORDER` and remind the user to re-import. Ask the user before adding one.

### Plot next waypoint in VoiceAttack

The shipped v5.7.2 profile adds **Plot next waypoint** under **EliteMining App Commands**. Say it from the ship HUD or assign a hotkey in VoiceAttack. The command reads `Variables/routeNextSystem.txt` on each trigger and says “No route” if it is empty or missing. It works with **Copy after jump** turned off.

The Route tab’s **Plot next system in game** button sends the same command to the running VoiceAttack profile and passes the path of the current app’s waypoint file. VoiceAttack and the EliteAPI plugin must be installed, with the plugin enabled and the updated EliteMining profile loaded. The button brings Elite Dangerous to the foreground and checks that the game has focus before sending the command. The button is disabled once the route has no next stop.

The user verified that the button worked from a second monitor after the focus fix.

The command uses the player's EliteAPI bindings for Galaxy Map, Camera Zoom In and Out, UI Panel Up, UI Panel Right and UI Panel Select. It opens the map, waits 2.5 seconds, zooms in, then presses Up → Select to focus search. VoiceAttack Quick Input enters the waypoint and presses Enter. After a 1-second pause the command presses Right → Select to choose the result, zooms out, waits 2 seconds and holds Select for 1 second to plot. After the hold, it waits 2 seconds for Elite to plot, then closes the Galaxy Map if EliteAPI still reports that it is open.

The first live test opened the map and moved the camera without entering the waypoint. EliteAPI reported that W was shared by UI Panel Up and Galaxy Cam Translate Forward, and D by UI Panel Right and Galaxy Cam Translate Right. The user confirmed that plotting worked after assigning separate bindings. [FAQ troubleshooting](../FAQ.md#troubleshooting) · [Galaxy Map navigation and binding collisions](https://github.com/RatherRude/Elite-Dangerous-AI-Integration/blob/main/src/lib/actions/Plotter.py#L574-L618)

To adjust timing, edit **Plot next waypoint** in VoiceAttack and change the pauses or the hold duration of the final UI Select action. The shipped command uses ship HUD and Galaxy Map focus checks from EliteVA and makes a single attempt.

## Progress

| Step | Status | Commit | Notes |
|---|---|---|---|
| 0 Confirm API details | Done | `445c982` | The live synthetic Sol-to-Paesia probe verified system names, the cargo and Beam fields, polling, and the stop fields. Omitting all explicit FSD fields returned HTTP 400. Individual field requirements and a real Loadout without those fields remain unverified. Step 2 verified a real Loadout with the fields. |
| 1 Tab renames | Done | `7fcd54b` | Both translation files parsed successfully, and help references were updated. The user later tested plotting in the running app with the Route tab present. A full visual pass of the renamed tabs in both languages was not recorded. |
| 2 Route core | Done | `9d5be6e` | Syntax, route and journal checks passed. A live Spansh plot using the user's Type-11 Loadout returned seven jumps from Sol to Paesia. Automated checks covered saved progress, skipped stops and off-route jumps. In-game coverage of those edge cases was not recorded. |
| 3 Route tab UI and user feedback | Done | Release pending | The user's first live plot from Wregoe JT-Q c18-27 to Sol returned eight jumps. All feedback items were implemented, including the Stop column with the current-stop marker, editable planning cargo, Inject column, estimated time and row copy. Live Spansh diagnostics confirmed the Basic and Standard injection multipliers. Route checks and off-screen Tk checks across all five themes passed during implementation. A full visual pass after the feedback changes was not recorded. |
| 4 Sell My Hold | Done | Release pending | Route, Sell My Hold, Stop and Market checks passed. Off-screen checks used mocked plots for the Route tab handoff and the two-leg sale route, including the reduced cargo on the second leg. Live one-stop and two-stop sale plots were not documented. |
| 5 Other views | Done | Release pending | Route, journal, cargo and result-view checks passed, including off-screen checks for all eight result menus. The user's test at the game's main menu exposed the missing Loadout and fuel readings. Automated checks verified the older-journal and full-tank fallbacks. Live plots from each result view and an in-game retest of those fallbacks were not documented. |
| 6 Cockpit support and voice tab commands | Done | Release pending | Route checks simulated jumps and verified the next-system clipboard calls, the settings gates and the VoiceAttack variable updates. VoiceAttack checks passed for named-tab selection, and the shipped profile contains "Show route". In-game results for clipboard copying, and spoken-command results in VoiceAttack, were not documented. |

## Remaining (25 Nov 2026)

1. **User's release test** of the built v5.7.2: clipboard after plotting and after a jump, `Variables\routeNextSystem.txt` and `routeJumpsLeft.txt` updating, and "Show route" and "Show systems" by voice (after re-importing the profile). Record the results in the progress table and fix anything that fails.
2. **In-game waypoint command test.** Re-import the profile and try **Plot next waypoint** by voice, by a hotkey and from the Route tab button with clipboard copying off. Check that the plotted route matches the next stop, that the Galaxy Map closes after plotting, that clearing or completing the route results in “No route”, and that jumping alone leaves the Galaxy Map closed.
   - 25 Nov 2026: the Route tab button plotted the correct next stop with the installer build. In the dev run, VoiceAttack received an empty `~passedText1` and fell back to the installed `VariablesouteNextSystem.txt`, so it plotted a stale system. This only affects dev testing. The unconfirmed suspect is the extra quotes around the path in `VAProcessManager.send_command`.
3. **Commit and push** everything together with the v5.7.2 release (`git add -A`), once the test passes.
4. **Later, beyond v5.7.2.** See [Fleet Carrier Route (phase 2)](#fleet-carrier-route-phase-2). The optional ship “Next system” voice command can read `routeNextSystem.txt` aloud. The user adds voice commands in VoiceAttack himself.

## Fleet Carrier Route (phase 2)

**Planning, 26 Nov 2026.** Add **Ship** and **Fleet Carrier** inside the existing **Route** tab. Spansh plots the route, and EliteMining follows it. Allow one plot at a time across both sub-tabs, use `EliteMining/<version>` as the User-Agent, and plot only on request. Scope is settled below.

### Step 0 findings — Spansh Fleet Carrier Plotter API

**Request.** `POST https://spansh.co.uk/api/fleetcarrier/route` with `application/x-www-form-urlencoded`. The website repeats the same key for each array value, such as `destinations=A&destinations=B`. It sends each selected system's id64. Poll `GET https://spansh.co.uk/api/results/<job>` with the ship client's existing backoff, timeout and Stop handling. [Spansh frontend](https://spansh.co.uk/assets/elite-dangerous-gui-f1d8f22e101c2fd0c520103f601d1877.js)

| POST field | Determine Tritium Requirements on (website default) | Off |
|---|---|---|
| `source` | Source system id64 | Same |
| `destinations` | Ordered destination id64s, with the key repeated for each system | Same |
| `capacity` | 25,000 t for Player Carrier, 60,000 t for Squadron Carrier | Same |
| `mass` | 25,000 t for Player Carrier, 15,000 t for Squadron Carrier | Same |
| `capacity_used` | Used Capacity in whole tonnes. The UI sends 0 for a blank or invalid value. | Same |
| `calculate_starting_fuel` | `1`, let Spansh calculate the starting Tritium requirements | `0`, use the entered Tritium stocks |
| `refuel_destinations` | Optional marked destination id64s, sent as repeated keys | Omitted |
| `fuel_loaded` | Omitted | Entered starting tank fuel in whole tonnes. The UI sends 0 for a blank or invalid value. |
| `tritium_stored` | Omitted | Entered starting Tritium in the carrier market in whole tonnes. The UI sends 0 for a blank or invalid value. |

The carrier picker sets the `capacity` and `mass` pair. `carrier_type`, `used_capacity`, `source_system`, `destination_systems`, `tritium_fuel` and `tritium_market` are results-page URL parameters. The frontend converts them to the POST fields above. Legacy market and module capacity inputs can be combined into `capacity_used`. Reorder, Reverse Route and destination import change the list in the browser before submission. [Spansh frontend](https://spansh.co.uk/assets/elite-dangerous-gui-f1d8f22e101c2fd0c520103f601d1877.js)

**Confirmed live.** One `scripts/dev_spansh_route_probe.py --carrier` run sent Sol (`10477373803`) to Paesia (`3657466647274`) with synthetic Used Capacity of 4,000 t and the checkbox on. POST returned HTTP 202 and `queued`. The first poll returned HTTP 200 and `ok`. The route included the source and one 169.76 ly jump that used 30 t. At Sol, Spansh marked a 30 t restock and showed 30 t in the planned tank even though the request supplied no tank or market stock. At Paesia, both tank and market showed 0 t. Keep the source row so the player can see how much to load before departing.

**Live name checks before Step 3 (26 Nov 2026).** The dev probe sent one `GET https://spansh.co.uk/api/search/systems?q=Paesia`. HTTP 200 returned a JSON object with `count`, `query` and a `results` array. The ten matches included the exact record `{"name":"Paesia","id64":3657466647274,"x":107.59375,"y":-15.0625,"z":130.4375}`. This confirmed the lookup shape tested in Step 2, including an integer id64.

One synthetic `POST /api/fleetcarrier/route` with `source=Sol` and `destinations=Paesia` also returned HTTP 202 and `queued`. The first poll returned HTTP 200 and `ok`, with the same 169.76 ly jump, 30 t fuel cost and expected string id64s in the stops. The probe used the same 4,000 t example capacity and automatic Tritium calculation. Both requests used public systems and synthetic values.

**Tank fuel check before Step 4 (26 Nov 2026).** One live synthetic dev probe plotted Sol to Paesia with 4,000 t used capacity, `calculate_starting_fuel=0`, `fuel_loaded=500` and `tritium_stored=0`. The POST returned HTTP 202 (`queued`) and the first poll returned HTTP 200 (`ok`). Spansh showed 500 t at Sol and 470 t at Paesia after the 169.76 ly jump used 30 t. Both stops had zero restock and zero Tritium in the market.

**Decision.** Send an id64 when already available and otherwise submit the selected system name directly. This saves up to two requests per plot and the route result still provides ids for matching. The live check covers the Sol-to-Paesia pair. Compare the entered endpoints case-insensitively and reject identical values before submitting.

**Result fields.** The website uses `result.jumps` in order. Every field in the table except the derived count and totals appeared in the live response.

| Website column | Field or calculation |
|---|---|
| System | `name`, with `id64` as a string. `x`, `y`, `z` are also available. `is_desired_destination` highlights plotted endpoints, including the source. |
| Distance / Remaining | `distance` for the incoming jump and `distance_to_destination` for the remaining distance |
| Jumps Left | `len(jumps) - 1 - index` |
| Fuel Left / Tritium in market | `fuel_in_tank` / `tritium_in_market`, planned carrier balances |
| Fuel Used | `fuel_used`, in tonnes |
| Icy ring | `has_icy_ring`, with `is_system_pristine` used for the Pristine label |
| Restock? / Restock Amount | `must_restock` / `restock_amount`, in tonnes |
| Totals / Estimated time | Sum distance, fuel used and restock amounts. The frontend uses 20 minutes per jump plus 7 hours for each marked restock after the source. EliteMining shows estimated jump time at 20 minutes per jump. |

**Still unverified live.** Individual server-required fields, multiple destinations, marked refuel stops and the incomplete-route response were outside the probes. The frontend renders an `incomplete` result separately. Preserve the prior route on a plot failure or an incomplete replacement. The probes showed zero market Tritium throughout, so behavior with a nonzero stored supply is based on the frontend. [Spansh plotter](https://spansh.co.uk/fleet-carrier) · [Spansh frontend](https://spansh.co.uk/assets/elite-dangerous-gui-f1d8f22e101c2fd0c520103f601d1877.js)

### EliteMining data and reuse

| Need | Existing source and planned use |
|---|---|
| From system and carrier identity | `fleet_carrier_tracker.get_fleet_carrier_tracker().carrier_data` exposes `system`, `carrier_id` and `callsign` from `JournalParser`. Prefill From with the carrier's known system. Keep it editable. The player supplies a system when it is unknown. Send the system name from the tracker or `SystemAutocomplete`, or preserve an id64 already available to the caller. |
| Destination and plot mode | The player chooses one destination. Send the name or known id64 as the single `destinations` value, and the Player Carrier capacity and mass. Select the starting fuel mode from the journal tank fuel. |
| Used Capacity | `JournalParser.process_carrier_stats()` reads `SpaceUsage.TotalCapacity`, `Cargo` and `FreeSpace` as `space_total`, `space_cargo` and `space_free`. Prefill `space_total - space_free` when both are known. This includes occupied space beyond commodity cargo. The snapshot updates when the player opens carrier management, so the saved value can lag. Follow new snapshots until the player edits the field, as with `RouteTab._route_cargo()` and `_validate_cargo()`. Keep a manual override through refreshes and tab switches. Ask the player for a value when the snapshot is missing, and accept an explicit 0. |
| Current tank fuel | Show `carrier_data['fuel_level']` next to the totals as a read-only value in tonnes. This game value comes from `CarrierStats` and is updated by an owned `CarrierDepositFuel`. It may lag after a jump. For a known value, including 0, send `calculate_starting_fuel=0`, `fuel_loaded=<fuel_level>` and `tritium_stored=0`. For an unknown value, send `calculate_starting_fuel=1`. |
| Other journal fields | The parser's `fuel_capacity` is the 1,000 t player-carrier tank default, while `jump_range_curr` and `jump_range_max` describe the carrier's range. Phase 2 uses Spansh's player-carrier capacity and mass for plotting. `space_cargo` is aggregate cargo, and the tracker has no stored Tritium breakdown. |
| Request, worker and cancellation | In `app/route_planner.py`, extend `SpanshRouteClient.start_plot()` and `poll()` to select the carrier endpoint and retain carrier result fields and the incomplete flag where needed. Reuse `RoutePlanner.plot()`'s daemon worker, Future, lock and cancellation. Keep its ship-specific `destination` shortcut and second-leg handling on the Ship path. Share the existing in-flight guard across both sub-tabs, including while a stopped worker finishes. |
| Saved routes and matching | Reuse the shape and config path of `RoutePlanner._save_route()`, `set_route()` and `clear_route()`. Save the carrier route in its own slot, `active_carrier_route`, alongside the existing ship `active_route` key and schema. Reuse `_matches_stop()` and the forward match in `_advance_route()` for scheduled jumps. A fresh confirmed carrier location can match any route stop and override the single cursor. |
| Table and plot feedback | Reuse `app/route_tab.py` patterns in `_build_table()`, `_show_route()`, `_spin_plot_overlay()`, `_wait_for_plot()` and `_plot_idle()`, including `StripedTreeview`, `ColumnVisibilityMixin`, `SearchControl`, inline notices and the in-table plotting overlay. Use a carrier column settings key. Keep EN and DE strings, theme colours and translated header minimums. |
| Mining details and row menu | Reuse the background read and stale-result guard from `_load_route_details()` / `_apply_route_details()`. Read local Tritium counts via `UserDatabase.bulk_get_hotspot_counts_for_systems()` and leave unknown counts blank. Put them beside Spansh's Icy ring column with its Pristine label. Use `calculate_distance(stop, SOL_COORDS)` for Distance to Sol. Reuse `_show_row_menu()` for Copy system name. |
| Clipboard and ship VoiceAttack | Reuse `_next_system()`, `_copy_next()`, `_copy_system()` and Copy system name for manual carrier clipboard copy. Enable the copy button while there is a next stop. The player pastes the name into carrier management. The Ship sub-tab owns **Plot next waypoint**, **Plot next system in game**, `routeNextSystem.txt` and `routeJumpsLeft.txt`. |

### Route sub-tabs

- Keep `RouteTab(app)` and the outer `app.route_tab` entry point. In `app/route_tab.py`, make it a small parent for a `ttk.Notebook`. Change the current frame into the Ship child in the same file and pass it the inner notebook as parent. Keep its form, table and callbacks together. Put the carrier child in its own module. Share only small pieces that both actually need.
- Follow `CommodityMarketTabMixin._build_marketplace_tab()` in `app/commodity_market_tab.py`. Its `_clear_market_sub_focus()` focuses the inner notebook and clears the entry selection on `<<NotebookTabChanged>>`, immediately and again after 50 ms. Apply that to both pages' entries, including numeric inputs. Leave the Ship page's FocusOut handling in place and target the current page in the delayed callback.
- Keep the top-level `route` key and `switch_to_tab('route')`. **Show route** opens Route on its last selected sub-tab, with Ship selected on first open. The outer `plot_to_system()` and `plot_sale_route()` entry points explicitly select Ship before delegating to its existing code, including the Sell My Hold two-leg flow.

### Carrier route progress

1. Use the shared journal reader and the tracker that already serves `FleetCarrierTab.set_tracker()` / `_on_carrier_updated()`. Today `FleetCarrierTracker.set_on_updated()` owns one callback. Add a second subscriber without replacing the Fleet Carrier tab callback, and use the notification after catch-up as well as live events. Marshal snapshots to Tk with `after` and keep tracking while the carrier sub-tab is hidden. Reuse `JournalParser.process_carrier_event()` and `_is_own_carrier()`. Check the carrier ID where the event provides it. Ignore squadron carriers and rides on another player's carrier.
2. Keep one current-stop cursor. Reuse the tracker's persisted pending request fields, `jump_destination` and `jump_departure_time`. For an owned `CarrierJumpRequest` whose destination matches a later stop, move the cursor at departure plus five minutes if the request is still current. `CarrierJumpCancelled` clears the pending request and stops its timer. A replacement request supersedes the old one. Use the UTC timing pattern from `FleetCarrierTab._refresh_jump()` and check saved requests after startup catch-up.
3. An owned `CarrierJump` or fresh owned `CarrierLocation` takes precedence over the timer and sets the same cursor to the confirmed route stop, including an earlier stop if applicable. If the confirmed system is outside the route, keep the cursor and show off-route status as on Ship. A confirmation that resolves the pending request ends its timer. Use the location event's timestamp for freshness because `carrier_data['last_updated']` also changes for finance and stats. Keep duplicate arrival reports idempotent, and compare id64s where the event supplies one.
4. Read the pending request from the tracker and leave its fields under Fleet Carrier ownership. When the route applies a request or a confirmed location resolves it, save its destination and departure time as the applied request in `active_carrier_route` alongside the cursor. Skip a matching request, including after restart. Route code treats all tracker data as read-only. The Fleet Carrier tab continues to use the tracker's pending fields for its countdown.

### Fleet Carrier sub-tab

- Player Carrier only, matching EliteMining's existing ownership filter. From defaults to the carrier's system. Offer one destination, editable Used Capacity, Plot with Stop, Copy next system and Clear. Use the journal tank fuel when it is known.
- Show the current-stop marker, System, Jump Distance, Jumps Left, Fuel Used, Fuel Left, Restock and Restock Amount. Put local Tritium Hotspots next to Spansh's Icy ring column and include its Pristine label. Show Distance to Sol. Below the table, show totals, estimated jump time in hours and minutes, and read-only current tank fuel from the journal.

### Implementation steps

1. **API verification (Sol 6.2, medium effort, done).** Read the frontend, extend the dev probe and run one synthetic plot. Use the verified response for local checks.
2. **Carrier plotting and storage (Sol 6.2, high effort, done).** `RoutePlanner.plot_carrier()` plots one Player Carrier destination with starting-fuel calculation always on. It sends names or known id64s directly and rejects identical endpoints case-insensitively. The caller applies a successful result with `set_carrier_route()`, which saves it in `active_carrier_route`. Mocked HTTP covers the form and result, timeout, cancellation, failed or incomplete replacement, independent saved routes and the shared one-plot limit. The app's carrier path has yet to be exercised live.
3. **Sub-tabs and controls (Sol 6.2, high effort, done).** The Route notebook hosts Ship and `FleetCarrierRouteTab`. Both panes share the table and plot feedback in `app/route_table.py`. The carrier uses the separate `carrier_route` column settings key and marks the plotted source as its current stop. It shows the agreed columns, read-only journal fuel and manual clipboard actions. Syntax checks and all 37 route-planner checks passed. Withdrawn Tk checks in EN and DE across all five themes covered the ship plotting entry points, named Route tab selection, entry highlighting, carrier inputs, Stop, independent route actions and table settings. The user's in-app visual and voice checks are pending.
4. **Carrier progress (Sol 6.2, high effort, implemented 26 Nov 2026).** The shared journal and pending request timer update one carrier cursor. The cursor and applied request are saved together in `active_carrier_route`. Route progress reads the Fleet Carrier data without editing it. Carrier totals show hours and minutes in English and German, and plotting uses the journal tank fuel when known. `py_compile`, all 49 route planner checks, and all 12 route status checks passed with isolated config. Coverage includes departure plus five minutes, cancellation and replacement, confirmed arrival before the timer, earlier and off-route corrections, duplicate and foreign events, startup catch-up, hidden tabs, clipboard, independent ship progress and VoiceAttack output, and both fuel branches. One in-game jump aboard and one while away are pending user verification.

### Decisions (open questions answered 26 Nov 2026)

1. Ship and carrier routes can be active at the same time and are saved separately.
2. One destination for now. Multiple destinations, marked refuel stops, Reverse Route and destination-list import are deferred.
3. When the game's tank fuel is known, send it to Spansh with **Determine Tritium Requirements** off and zero stored Tritium. When tank fuel is unknown, let Spansh determine the starting requirement. Show the game's tank fuel beside the totals as a read-only value.
4. Carrier plotting is available from **Route → Fleet Carrier**. An entry in the separate Fleet Carrier tab is deferred.
5. Carrier route import and export are deferred.
6. Carrier cockpit support is manual clipboard copy only. Carrier VoiceAttack variables are deferred.
7. Keep Spansh's Icy ring column with its Pristine label. Add local Tritium Hotspots beside it and include Distance to Sol. Reserve and Last Mined are deferred. The Pristine label covers the reserve detail for this view.

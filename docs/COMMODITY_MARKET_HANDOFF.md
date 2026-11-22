# Commodity Market Review — Handover

Start each new chat with: "Read docs/COMMODITY_MARKET_HANDOFF.md and continue with the next step in the progress table."

Review date: 22 Nov 2026, at commit `cd40897`. Line numbers refer to that commit and move after step 1.

## Recommended Order

The user's requirement: today's search works and must not break. Each step must show that it only changes what it is meant to change.

1. **Step 0:** the before/after comparison script (below).
2. **Step 2:** the data age window. Save the "before" results first.
3. **Steps 3 and 4.**
4. **Step E1:** EDDN coordinates.
5. **Step 6:** hardcoded text.
6. Optional later: 7, 8, E2 and E3. Postponed: 1, 5 and 9.

Run the steps one after another, never in parallel. Steps 2, 3, 4 and E1 all change `marketplace_api.py`, and other chats may edit the same checkout. A subagent is only worth it for step 0, which is a new file of its own.

**Before each step:** name the step's recommended model and effort (given in each step section) and say whether Plan mode helps. Then wait until the user confirms they have switched, or tells you to go ahead. Never start a step on the wrong model or effort without asking.

After each step: the matching checks, the comparison run, the user's dev test, then one commit (`git add -A`, as AGENTS.md says). Update the progress table at the bottom.

**At the end of each chat:** give the user one ready-to-paste prompt for the next chat, naming the next step and its recommended model and effort. Use this form:

```
Read docs/COMMODITY_MARKET_HANDOFF.md and continue with the next step in the progress table.
```

Recommended for the next chat: <model>, <effort>.

**When to start a new chat:** say so in one line when the current step is finished and committed, when the next step needs a different model or effort, or when the chat has grown long, for example after several large files or many test runs. Tell the user to type `/clear` (or `/new` in Codex) and paste the prompt above. Don't suggest it during a step or for follow-ups on the same step.

**Rule conflict to confirm with the user before step 2:** AGENTS.md says a tab in `main.py` must be moved into its own module (step 1) before it is changed. Step 2 needs one line changed in `_search_marketplace` (`api_days = 30`). The recommendation is to allow that one-line exception and postpone the move, but ask the user first.

## Step 0 — Before/After Comparison Script

- New `scripts/compare_market_search.py`. It runs a fixed set of searches through the same calls the tabs use (`search_buyers`/`search_sellers`, the galaxy-wide variants, `filter_results`, `sort_results`/`prepare_galaxy_results`):
  - Mining: Painite and Platinum, Sell and Buy.
  - Trade: one commodity, for example Gold.
  - Near System from Sol (bubble), Colonia (remote) and a system missing from the galaxy database (`HIP 67282`), plus Galaxy-Wide.
  - Max Age 8 hours and "Any".
- `--save before` stores the results as JSON (in the scratchpad or a git-ignored folder, never in the repo). `--compare before` lists, per search, the stations added, the stations lost and the change in row count and time.
- Live prices change between runs. Run "before" and "after" close together, and treat a lost station as a failure only if it is still in the latest raw source data.
- Work on a copy of `app/data/marketplace_cache.db`. The searches write back into the cache.
- **Model:** Sonnet, medium. A subagent is fine here.

## Scope

The Commodity Market tab and its four sub-tabs: Mining Commodities, Multiple Prices, Sell My Hold and Trade Commodities. The review covered the GUI and the speed of the search.

## Rules for Every Step

- One step per chat and one commit per step. Read [FEATURE_RULES.md](FEATURE_RULES.md) "Commodity Market" before you change any search behaviour.
- `MarketplaceAPI` (`app/marketplace_api.py`) is shared with Ring Finder, Auto Prices and Find Best Mining System (`ring_finder.py` calls `search_buyers` with 7 days). Backend changes also affect those features. Changing what Ring Finder or Auto Prices request is a separate decision, so ask first.
- Baseline (22 Nov 2026): `check_marketplace` (28), `check_search_stop` (26), `check_cargo_sell_planner` (13) and `check_marketplace_indexes` (11) all pass. Run the ones that match each step, plus `py_compile` on every changed file.
- New UI text goes in both `strings_en.json` and `strings_de.json`.

## Code Map (at `cd40897`)

| What | Where |
|---|---|
| Sub-tab container | `main.py` `_build_marketplace_tab` (11280) |
| Mining Commodities UI | `_build_mining_commodities_tab` (11315), `_create_marketplace_results_table` (13084) |
| Trade Commodities UI | `_build_trade_commodities_tab` (11620), `_create_trade_results_table` (14143) |
| Context menus and preferences | 13309–14033 (`_create_marketplace_context_menu` … `_save_trade_preferences`) |
| Searches | `_search_trade_market` (14035), `_search_marketplace` (14435) |
| Result display, Powerplay fill-in, sorting | 14122–14912 |
| Multiple Prices | `app/multi_mineral_tab.py` |
| Sell My Hold | `app/cargo_sell_planner.py` |
| Backend | `app/marketplace_api.py`: `search_buyers`/`search_sellers` (1047/1144), galaxy-wide variants (1243/1304), `_fetch_spansh_nearby` (695), `_fetch_spansh_carriers` (301), `_fetch_eddn_cache` (448), `add_distances_to_results` (1364) |
| Stop and cancel | `app/ui/search_control.py` |
| Powerplay fill-in | `system_finder_api.py` `_fetch_spansh_powerplay_for_named_systems` (274) |

Star Systems (`_build_system_finder_tab`, 11915–13083) sits between these blocks but is a different tab. Leave it out of scope.

## How a Near System Search Works Now

1. Four sources run in parallel: Ardent nearby, Spansh nearby, Spansh carriers and the local EDDN cache.
2. **Then**, one after another, the Ardent "commodities in the reference system" request runs.
3. The results are merged by `marketId` (newest wins), written back into the EDDN cache, filtered locally (station type, pad, age), sorted and shown.
4. After the rows are shown, a background thread asks Spansh for Powerplay data for up to 50 result systems, one request each, at least 0.5 s apart.

Measured on 22 Nov 2026 (Painite near Sol, 500 LY):

| Source | Time | Rows |
|---|---|---|
| Ardent nearby, 30 days | 1.59 s | 1000 (capped) |
| Ardent nearby, 1 day | 0.46 s | 1000 (capped) |
| Ardent reference-system list | 0.64 s | 8437 |
| Spansh nearby (300 most recent stations anywhere) | 2.92 s | 153 within 500 LY |
| Spansh carriers (200 most recent carriers) | 0.72 s | 6 |
| EDDN cache, 30 days / 1 day | 0.26 s / 0.07 s | 4447 / 537 |
| Ardent galaxy-wide, 30 days / 2 days | 0.96 s / 0.42 s | 100 / 100 (capped) |

**Key finding:** Ardent returns at most 1000 nearby rows. Mining Commodities, Multiple Prices and Sell My Hold always ask for 30 days and then filter by age locally. In the bubble, 30 days of data fills the 1000-row cap, so fresh prices get cut off. For Sol with an 8-hour age limit, the 30-day request kept 183 (Painite) and 196 (Platinum) fresh stations. The 1-day request returned 723 and 710, and it is 3x faster. Outside the bubble (Colonia) nothing was lost. Trade Commodities already requests the matching window through `_convert_age_to_days`.

---

## Step 1 — Move Commodity Market Code out of main.py (move only)

**Why:** [MAIN_SPLIT_HANDOFF.md](MAIN_SPLIT_HANDOFF.md) requires a tab in `main.py` to be moved to its own module, in a separate commit, before it is changed.

- Follow MAIN_SPLIT_HANDOFF's rules exactly. Use a mixin `CommodityMarketTabMixin` in `app/commodity_market_tab.py`, add it to `App`'s bases and keep the method bodies unchanged.
- Move the Commodity Market methods listed in the code map: 11280–11902, and 13084–14912 except the Star Systems methods. `_check_market_api_status` (7010) stays where it is.
- Do a scope-aware `symtable` scan for names the moved code takes from `main.py` (`t`, `log`, `ToolTip`, `ThemedRadiobutton`, `ThemedCheckbutton`, `create_action_button`, `StripedTreeview`, `SearchControl`, `MarketplaceAPI`, `displayed_column`, `modern_color`, `get_material`, `get_station_types`, `get_sort_options`, `get_age_options`, `_load_cfg`, `threading`, and so on).
- Point `scripts/check_marketplace.py` (`load_methods('app/main.py', 'App', …)` around line 345) and `scripts/check_search_stop.py` (lines 227 and 238, plus the file list at 490) to the new module.
- Remove the misleading banner "UNUSED MARKETPLACE SEARCH METHODS (Kept for reference)" in step 6, not here.
- **Checks:** `py_compile`, the undefined-name scan, `check_marketplace`, `check_search_stop`, `check_cargo_sell_planner`.
- **Dev test:** the app starts; each of the four sub-tabs opens; one Near System and one Galaxy-Wide search on Mining and Trade; right-click menu; column sort.
- **Model:** Opus, high effort. Plan mode isn't needed; the procedure is fixed.

## Step 2 — Request Only the Needed Age Window (largest speed and quality gain)

- Mining Commodities (`_search_marketplace`, `api_days = 30`), Multiple Prices (`multi_mineral_tab.py` line 316) and Sell My Hold (`cargo_sell_planner.py` line 329) pass the API window derived from the chosen Max Age instead of 30. Reuse `_convert_age_to_days` (Any → 30, up to 1 day → 1, 2 days → 2), and move it to `MarketplaceAPI` as a static helper so all three can call it.
- Keep the local hour-level filter (`filter_results` / `filter_results_by_age`). It still trims to the exact hours.
- Ring Finder and Auto Prices (7 days) are out of scope unless the user agrees.
- **Checks:** `check_marketplace`, `check_cargo_sell_planner`, `check_search_stop`.
- **Dev test:** Mining Commodities near a bubble system with Max Age 8 hours. Expect more rows than before, and a faster search. Max Age "Any" still works. Repeat for Multiple Prices and Sell My Hold.
- **Model:** Sonnet, medium.

## Step 3 — Run the Reference-System Lookup in Parallel

- In `search_buyers` and `search_sellers`, submit the "commodities in the reference system" Ardent request to the same pool as the four nearby sources instead of after them. This saves about 0.5–1 s per search, and per mineral in Multiple Prices and Sell My Hold.
- `search_sellers` doesn't use `_short_cached` for this request but `search_buyers` does. Cache it the same way (key `("ardent_local_exports", system, days)`).
- Keep the cancel check: if cancelled, return the merged nearby rows as now.
- **Checks:** `check_marketplace`, `check_search_stop`.
- **Dev test:** Near System Sell and Buy searches; results still include stations in the reference system at 0 LY.
- **Model:** Sonnet, medium.

## Step 4 — Share Spansh Carrier Pages Between Minerals

- `_fetch_spansh_carriers` downloads the 200 most recently updated carriers, which doesn't depend on the commodity, and then matches the commodity locally. Multiple Prices with 5 minerals sends the same 2 requests 5 times, and so do Sell My Hold, Auto Prices and Ring Finder.
- Wrap the raw page fetch in `_short_cached(("spansh_carriers",), …)` as `_fetch_spansh_nearby` does. Keep distance, age and commodity matching per call.
- **Checks:** `check_marketplace`, `check_search_stop`.
- **Dev test:** Multiple Prices with 5 minerals and Exclude Carriers off; carriers still appear and the search is faster.
- **Model:** Sonnet, low.

## Step 5 — Make the Powerplay Fill-in Stoppable and Avoid Repeat Lookups

- After every Mining or Trade search, `_backfill_commodity_pp_worker` makes up to 50 sequential Spansh requests (25 s or more). It can't be stopped, it starts again on every new search for the same systems, and it competes with the next search's Spansh requests.
- Pass an `is_cancelled` to `_fetch_spansh_powerplay_for_named_systems` that turns true when a new search starts on the same table or the user presses Stop. Use a per-table generation counter, and skip the UI update for an old generation.
- Skip systems that Spansh already answered in the last few minutes (in-memory TTL map in `system_finder_api.py`). The "newest data wins" comparison (`_spansh_pp_should_replace_cache`) stays as it is, and so does the `~none~` sentinel handling.
- Ring Finder and Star Systems use the same helper; check that they still pass no `is_cancelled` or their own.
- **Checks:** `check_marketplace`, `check_search_stop`, `check_ring_finder_search`.
- **Dev test:** run three searches quickly one after another; the log shows the older fill-ins stopping, and the Powerplay column still fills in for the last search.
- **Model:** Opus, high (threading plus DB writes through `_store_powerplay_batch`).

## Step 6 — Fix Hardcoded English and Dead Status Text

- `_display_marketplace_results` and `_display_trade_results` show "Avg: … CR", "Best Sell" and "Best Buy" in English. Add `t()` keys in both languages.
- `_populate_marketplace_results` writes "Found N stations to sell to. Best price …" in English, which `_display_marketplace_search_results` overwrites straight away. Remove it.
- "❌ Error displaying results" and "❌ Sort error" are hardcoded. Use `t()` keys.
- Mining Commodities in Buy mode shows the price without " CR", but Sell mode and Trade show it. Make them the same.
- Remove the wrong "UNUSED MARKETPLACE SEARCH METHODS" banner. Ask before deleting the unused `_open_edtools_market` (its button is commented out).
- **Checks:** `check_marketplace`, `check_search_stop`, and a JSON check that both string files load.
- **Dev test:** search in English and German; both summary labels are translated.
- **Model:** Sonnet, low.

## Step 7 — Make Trade Commodities Behave Like Mining Commodities

- Switching Sell/Buy on Trade changes the sort list but not the selected value, so "Best price (highest)" stays shown in Buy mode while results sort lowest first. Mirror `_update_marketplace_order_options` (13643), which remaps price and demand/supply.
- Selecting Station = Fleet Carrier on Trade unticks Exclude Carriers but doesn't disable the checkbox, unlike Mining and Multiple Prices.
- Trade's "Current System" button does nothing silently when no system is known. Mining shows `ring_finder.could_not_detect_system` via `_show_notice`; do the same.
- **Checks:** `check_marketplace`.
- **Dev test:** on Trade, switch Buy↔Sell with each sort option; select Fleet Carrier; press Current System before any journal location is known.
- **Model:** Sonnet, low.

## Step 8 — Column Sort Fixes and Faster Table Refresh

- Mining Commodities column sort: a distance of "-" (unknown) fails to parse and becomes 0, so unknown distances sort first in ascending order. Trade's `parse_value` sends unknown values to the end. Make Mining use one shared parse helper.
- `_sort_marketplace_column` re-tags row stripes manually; `StripedTreeview` already re-stripes on move, so that loop can go.
- Clear tables with `tree.delete(*tree.get_children())` instead of a per-row loop, and move the `from app_utils import …` out of the per-row loop in both populate methods (it runs once per row now).
- **Checks:** `check_marketplace`, `check_search_stop`.
- **Dev test:** Galaxy-Wide with Max Results "All", then sort every column both ways; unknown distances stay at the bottom.
- **Model:** Sonnet, low.

## Step 9 — Spansh Nearby Relevance (investigate first)

- `_fetch_spansh_nearby` downloads the 300 most recently updated stations **anywhere** for the commodity (no reference system) and keeps those within 500 LY. It is the slowest source (about 3 s). Outside the bubble it returns almost nothing, and in the bubble it overlaps heavily with Ardent and the EDDN cache.
- The shared raw cache (`("spansh_nearby", …)`, 5 min) was deliberate: Auto Prices reuses it after each jump. A reference-system request would lose that reuse.
- First measure what Spansh adds that the other sources don't (unique `marketId`s after the merge), for bubble and non-bubble systems. A quick test of `reference_system` + distance sort (1 page) returned only 33 stations within 500 LY of Sol; find out why before relying on it.
- Options to compare: keep as is; use a reference-system query only for Near System searches in Commodity Market; skip Spansh nearby when Ardent didn't hit its cap.
- **Model:** Opus, high, with Plan mode. **In-game test needed** if Auto Prices is affected (jump between systems with Auto Prices on).

## EDDN Listener Review (22 Nov 2026)

`app/eddn_listener.py` subscribes to the EDDN feed on its own thread and writes prices, station details, Powerplay and system status into `marketplace_cache.db` (WAL mode). An hourly thread deletes data older than 14 days.

Checked and fine:
- The log shows one clean connect per app start, with no errors and no "database is locked" messages.
- The search query uses its index (`idx_commodity_name_lower_updated`).
- The startup cleanup takes 0.04 s.
- No future timestamps are stored.
- All sources store timestamps in the same format.

How coordinates work today:
- Spansh and Ardent rows bring their own coordinates.
- EDDN price messages carry none. The listener reads the `system_coords` table when it saves a price, but **nothing ever writes that table** (0 rows).
- Near System reads the cache through `_fetch_eddn_cache`, which only looks in the bundled galaxy database (89,731 systems) and drops rows it can't place.
- Galaxy-Wide (`add_distances_to_results`) also uses other cache rows, `system_coords` and EDSM.
- The reference system's own coordinates come from the galaxy database, then EDSM. Spansh is never asked for coordinates directly.

Measured on a copy of the dev cache:
- 153,398 price rows. 44,888 of them (1,376 systems) have no coordinates and their system isn't in the galaxy database.
- 8,694 of those rows are less than 1 day old, and 1,197 are Painite, Platinum, Low Temperature Diamonds or Void Opals. Near System searches never show them today.
- Another cache row already holds coordinates for 441 of the 1,376 systems.
- Live feed sample (60 s): 1,296 messages. 51 were price messages (34 with tracked commodities, none from the Legacy galaxy). All 146 jump, location and docking messages carried `StarPos` coordinates.

### Step E1 — Store EDDN Coordinates and Use Them in Near System (recommended)

- In `_process_journal_message`, save `StarSystem` + `StarPos` from FSDJump, Location, CarrierJump and Docked into `system_coords` (`INSERT OR REPLACE`, one row per system). Coordinates belong to the system, never to a carrier (FEATURE_RULES).
- In `_fetch_eddn_cache`, after the galaxy database, also look up `system_coords` and coordinates from other rows of the same system. Reuse the lookup already in `add_distances_to_results` rather than writing a second one.
- Expected effect: more fresh stations in Near System results, mostly outside the bubble and in newly colonised systems. Nothing that shows today should disappear.
- Make the before/after comparison script first (see the risk notes) and check that only stations are added.
- **Checks:** `check_marketplace`, `check_marketplace_indexes`, `check_search_stop`, plus a new check: a journal message with StarPos fills `system_coords`, and a later price row in that system gets a distance.
- **Dev test:** run the app for 10 minutes, then search near a system outside the galaxy database (for example `HIP 67282`); the log shows `system_coords` growing.
- **Model:** Opus, high (writes on the listener thread).

### Step E2 — Reconnect After a Silent Connection (optional)

- The feed sends about 20 messages per second, but the loop never reconnects after receive timeouts. A connection that dies without an error (sleep/resume, network change) would leave the cache going stale with no sign in the log. This hasn't been seen in the logs, but timeouts are only logged at debug level.
- After about 3 minutes with no message, close the socket and reconnect, logging it once at INFO.
- **Checks:** `py_compile`, a unit test with a fake socket that always times out.
- **Model:** Sonnet, medium.

### Step E3 — Ignore Legacy Galaxy Data Everywhere (optional, low value)

- System status already skips Legacy (`_process_system_info_from_event`), but prices, station details and Powerplay don't. None appeared in the sample, so the risk is small. The fix is a 3-line guard using the same check.
- **Model:** Sonnet, low.

## Considered and Left Out

- Merging the near-duplicate Mining and Trade builders and search methods (about 600 lines each): a worthwhile follow-up after step 1, but it is a refactor, so ask first.
- Hardcoded dark colours in the builders (`#1e1e1e`, `#ffffff`): the Modern themes recolour them. Only change them if a theme bug is reported.
- SQLite variable limit in `add_distances_to_results`: the bundled SQLite is 3.50 (limit 32766), so there's no real risk.
- Sell My Hold's 1-second cargo poll: it only reads in-memory data, so it's cheap.
- One database connection per EDDN message: about 3 per second, which is acceptable.
- EDDN size cap: the file never shrinks without VACUUM, so above 350 MB it would trim 20% of Powerplay data every hour. Today it's 72 MB with little free space, so this isn't reachable soon. Revisit if the file grows past about 250 MB.

## Risk Notes

- Nothing can be guaranteed safe. Step 0 is the safeguard, together with one commit per step so any step can be reverted on its own.
- Highest risk: 9 (changes which sources feed the results and affects Auto Prices), then 5 (background threads shared with Ring Finder and Star Systems) and 1 (a missed import crashes the tab).
- Step 2 changes results on purpose (more fresh stations). E1 should only add stations; anything lost is a bug.

## Progress

| Step | Status | Commit |
|---|---|---|
| 0 Comparison script | Done (`--quick` smoke run on Painite: identical rows between two runs apart from live changes) | see git log |
| 1 Move to module | Postponed | — |
| 2 Age window | Done, dev tested (checks pass; comparison: Sol 8 h Painite sell 314 -> 819 rows, Platinum 355 -> 778, buy and Colonia unchanged) | see git log |
| 3 Parallel reference-system lookup | Not started | — |
| 4 Carrier page sharing | Not started | — |
| 5 Powerplay fill-in | Not started | — |
| 6 Hardcoded text | Not started | — |
| 7 Trade parity | Not started | — |
| 8 Sort and refresh | Not started | — |
| 9 Spansh nearby | Not started | — |
| E1 EDDN coordinates | Not started | — |
| E2 EDDN reconnect | Not started | — |
| E3 Legacy guard | Not started | — |

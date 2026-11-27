# Voice Commands Reference Card — Handover

Start the chat with: "Read docs/VA_REFERENCE_CARD_HANDOFF.md and build the Voice Commands sub-tab."

Written 27 Nov 2026 at commit `fe86f87` (v5.7.5 profile). Recommended: medium effort. Plan mode is not needed; the design below is settled with the user.

## Goal

A new sub-tab in the VoiceAttack tab that lists the spoken commands of the EliteMining profile. The phrases are read from the profile, so when phrases change in a new profile the card follows without a hand-kept list. The main design risk is visual clutter: many commands have 3–10 phrases, so the rules below keep one row per command.

## Source of the phrases

- Read the newest shipped profile with `App._newest_shipped_va_profile()` (`app/main.py`, search by name). It globs `EliteMining v*-Profile.vap` in `self.va_root`. Parse it with `VAProfileParser().parse()` (`app/va_profile_parser.py`), which handles compressed and XML profiles.
- Do not read VoiceAttack.dat. `va_profile_reader.py` can only copy it while VoiceAttack is closed, so during play it would show a stale backup. Player-edited phrases are out of scope.
- Parse in a daemon thread the first time the sub-tab is shown, and update the UI via `parent.after(0, ...)`. Keep the result keyed by (path, mtime) and re-parse on a later visit only when either changed (for example after a profile update).
- No profile found or parse error: show a short inline message in the tab (via `_show_notice` or a label), no dialog.
- Each command: `CommandString` is the phrases separated by `;`, and `Category` is the group. Reuse `command_phrases()` / `is_internal_command()` from `app/va_keybind_extractor.py` where they fit, but keep the original casing for display (`command_phrases()` lower-cases).

## Which commands are shown

Never show called commands. Two independent rules, both always applied:

- Skip every command whose name starts with `((`, whatever its category (for example `((*PanelMove*))` sits in `Commands - Panels`).
- Skip every command in a `Called Commands*` category, even if a future profile names one without `((`.

Map the profile's remaining raw categories to seven translated groups. The v5.7.5 counts of user-facing commands are in brackets.

| Group (display) | Raw categories |
|---|---|
| Mining (default) | Custom Keybinds for Mining control (set you own keybinds here) (18) |
| Mining settings | Commands - Set Toggles (16), Commands - Set Timers (13), Commands - Set Power Settings (1), Commands  - Set Counters (1) |
| Check settings | Commands - Check Status (41) |
| Firegroups | Commands - Set Firegroups (7), the four `Commands - Set Fire Button For ...` (3 each), Commands - Macros FG (8), Commands - Weapons (5) |
| Ship and SRV | Ship commands (23), Commands  - Flight Throttle (9), Commands  - Mode Switches (3), Commands - Panels (2), Commands - Misc (10), Commands Target (6), SRV commands (2), Trackir (2) |
| EliteMining app | EliteMining App Commands (39), EliteMining - Information (1) |
| VoiceAttack | VoiceAttack - Control (9) |

Hidden: `Dev's commands`, every `Called Commands*` category, `EliteApi`, and commands with no category.

- Several raw names contain a double space (`Commands  - Flight Throttle`). Match after collapsing whitespace, and match the four Fire Button categories by prefix.
- Keep the mapping in one dict. A raw category that is neither mapped nor hidden is left out and logged once at INFO, and the check script (below) fails on it, so a new category in a future profile is caught during development rather than silently missing.

## Layout

```
[Group: Mining v]   [Search: ____________]
 Say this                                     Other ways
 Start prospector sequence                    +5
 Stop prospector sequence                     +1
 Enable or disable cargo scoop retraction     +6
 Set firegroup for mining lasers to alpha … hotel
──────────────────────────────────────────────────────────
 Also works: start prospector · launch prospector · prospector ·
             Initiate prospector sequence · prospector sequence
```

- One row per command. "Say this" is the main phrase. "Other ways" shows `+N`, the number of further phrases, and stays empty when there are none.
- Selecting a row fills a details area under the table with every other phrase of that command, separated by ` · ` and word-wrapped. Use a read-only themed `Text` widget so the text can be copied. It is empty until a row is selected. No tooltips.
- The Group dropdown shows one group at a time and opens on Mining.
- Search is case-insensitive and matches every phrase of a command, not just the main one. While the search box has text, it searches all groups, shows a third "Group" column via `displaycolumns`, and puts the matched phrase in "Say this" so the row visibly explains why it matched. Clearing the search returns to the selected group.
- Follow the table rules in docs/UI_RULES.md: left-aligned, `stretch=False` on data columns, minimum width = translated header width, widths saved through `config.py`, theme colours from `load_theme()` / `get_theme_colors()`. Reuse the existing striped Treeview (`app/ui/striped_treeview.py`) if it fits.

## Tidy-up rules (display only)

Apply these to every phrase before display or search. Never write anything back to the profile.

1. Strip spaces and capitalise the first letter (several phrases end with a stray space).
2. Enable/Disable merge: when a command has a phrase "Enable X" and a phrase "Disable X" with the same X (case-insensitive), the main phrase becomes "Enable or disable X". The same applies to "Turn on X" / "Turn off X". The merged pair counts as one phrase in `+N`. Use a translated pattern for "Enable or disable {x}" only for the joining words if needed; the X part stays English.
3. Brackets in the main phrase, kept as valid speech:
   - Number range `[1..50]` → `1–50`; a single number `[0]` → `0`.
   - Word choice `[timer;duration]` → the first option (`timer`).
   - Optional word, i.e. a list with an empty option such as `[firing;]` → the first non-empty option.
   - Four or more non-empty options (`[alpha;bravo;...;hotel]`, `[one; two;three; four;]`) → `first … last` (`alpha … hotel`).
4. Brackets in the details area show the choices: `[timer;duration]` → `timer or duration`, three options → `delay, timer or duration`, optional words in parentheses (`(firing)`), ranges and long lists as in rule 3.
5. Trim spaces inside options (`[Show; Unhide; Maximize]`).

All bracket forms in the v5.7.5 profile: number ranges `[0..3]` to `[8..30]`, single `[0]` and `[1]`, two- to four-word choices, optional words `[firing;]`, `[mining;]`, `[retracting;]`, `[target;targeting;]`, the eight-letter firegroup list and `[one; two;three; four;]`.

When a row still reads oddly after these rules, the fix belongs in the profile phrase, not in a special case in code. List such rows for the user instead of adding exceptions.

## Code placement

- Pure logic (no Tk): new module `app/va_phrase_reference.py` holding the category map, the tidy-up functions, the search, and `load_reference(profile_path) -> list of entries` (group, main phrase, other phrases, all phrases for search).
- UI: new module `app/va_reference_tab.py`, built from `_build_voiceattack_controls_tab()` in `app/voiceattack_controls_tab.py` as a fourth sub-tab after Voice Feedback. Do not add the UI to `main.py`.
- Strings: new keys under `voiceattack` (tab name, column headers, group names, "Also works:", search label, empty and error messages) in both `strings_en.json` and `strings_de.json`. Suggested tab name: "Voice Commands" / "Sprachbefehle". Phrases themselves stay English, because VoiceAttack listens for the English phrases.

## Checks

New `scripts/check_va_reference.py` (unittest, no Tk needed for the logic part):

- Every category in the shipped `Voiceattack Profile/*.vap` is either mapped or hidden.
- No `((` command, no `Called Commands*` command and no other hidden-category command appears, including `((*PanelMove*))` in `Commands - Panels`.
- Each tidy-up rule, with real phrases from the profile (Enable/Disable merge, range, optional word, long list, stray space).
- Search finds a command by an alternative phrase that is not the main one.
- Every new string key exists in both language files.

Then `py_compile` the new and changed files. The user tests the tab in the app.

## Open questions for the user

- Should the tab show a one-line note that the phrases are spoken in English? Useful for German players, but AGENTS.md says no help text unless asked, so ask first.
- Patch note, once done: one sentence in "New Features & Improvements", for example "A new Voice Commands tab in VoiceAttack lists the spoken commands, with search."

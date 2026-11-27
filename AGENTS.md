# EliteMining — Shared Project Instructions (Claude Code and Codex)

> Keep this file under ~3k tokens. Put detailed info in docs/.

- Shared by Codex (direct) and Claude Code (via [CLAUDE.md](CLAUDE.md)). Claude-only notes go in CLAUDE.md, Codex-only notes go in "Codex Only", and none of these rules get copied into memory.
- Current user instructions override saved rules, and memory is only context. Report conflicts before making affected changes.

## Chat Rules

- Be concise: no preamble, no trailing summaries. Use general judgment: proceed with straightforward work, ask one targeted question only when scope or risk depends on it, and don't re-explain settled decisions.
- Fix only what was asked: no unsolicited refactoring, extra error handling, abstractions, tooltips, docs or help text. Name a worthwhile follow-up briefly and ask first.
- Flag rule conflicts first (master switches, shared settings, other tabs' behavior) in 1–2 sentences with a recommendation. When asked for an opinion, give one recommendation; say plainly when there is no real fix.
- Comments only when the WHY is non-obvious; no task/PR references. No emojis unless asked.
- Reuse first: search the likely modules (including other tabs, e.g. distance/coordinate lookups in `ring_finder.py`) for an existing function and extend it minimally. Text-only edits need no search.
- Patch notes (`docs/PATCHNOTES_v*.md`): one plain-English sentence per change from the player's view, with the player benefit first and only the detail needed to explain it. Cover only what is new or fixed, combine related changes, and avoid dev terms (EDDN, API, cache, database, function names). Use the "New Features & Improvements" and "Bug Fixes" sections from `docs/PATCHNOTES_TEMPLATE.md`.
- At the start of each new task (not follow-ups), recommend a model and effort in one line: lighter for small work, strongest with high effort for threading, DB writes, VoiceAttack contracts or multi-component work. Say whether Plan mode helps. Then wait for the user to confirm before editing any code; reading and searching are fine.
- When the chat ends, save lasting decisions and open issues to memory or docs, without duplicates and only in authorized files.

## Validation

- Scale checks to risk, not patch size: `py_compile` for small changes, the matching check scripts for fixes, and failure-path checks for DB, threading or shared config changes.
- Checks must never write the real app/config.json; isolate config in a temp file.
- Checks are `unittest` scripts: `app\.venv\Scripts\python.exe scripts\check_<area>.py`. Many create a Tk root, so run only the areas you changed. Syntax check: `app\.venv\Scripts\python.exe -m py_compile <file>`.
- The user restarts `app/main.py` and tests the UI. Don't duplicate that or assume it passed. When a problem is reported, assume a fresh restart and find the code cause. Give a numbered test list only for non-obvious behavior.
- Report what was and wasn't verified; never claim visual verification from code inspection.

## Editing

- `app/main.py` (~22k lines) and `app/ring_finder.py` (~12k lines) are too large to read whole: search by name and read ranges.
- Most `app/` files and the `.vap` profiles are CRLF; a few (e.g. `announcer.py`) are LF. For multi-line patch scripts: write the script outside the repo, normalize to `\n`, assert one match each, restore CRLF, then `py_compile`.

## Code Conventions

- Background work runs in a daemon thread, with UI updates via `parent.after(0, ...)`.
- Every new UI string goes in both `strings_en.json` and `strings_de.json`, accessed via `t('section.key')`. Never hardcode user-visible text.
- Config loads and saves go through the rate-limited `_load_cfg()` in `config.py`. Never bypass it.
- `PP_FETCH_MAX_BATCH` and `PP_FETCH_DELAY_SECS` exist in both `ring_finder.py` and `main.py`, so keep them in sync.
- Cargo Monitor display changes go in `EliteMiningApp._update_integrated_cargo_display()` in `app/main.py`.

## UI Rules (details: [docs/UI_RULES.md](docs/UI_RULES.md))

- Dialogs: call `withdraw()` right after `tk.Toplevel()`, never use `transient()`, and center with `center_window()`. Prefer `centered_info_dialog` / `centered_yesno_dialog`. Dialogs with child popups must not run the `keep_on_top` lift loop over them.
- New widgets take colours from the active theme (`load_theme()` / `get_theme_colors()`), never defaults. Gate Modern-only changes on all three of `modern`, `modern_slate` and `modern_orange`.
- Focus for new filters and text fields: clear automatic text selection when opening or re-entering a tab and clear lingering highlights on focus loss or after choosing a dropdown value. For nested tabs, handle `<<NotebookTabChanged>>` on their notebook and clear the selection again after 50 ms if Tk restores it. Preserve keyboard navigation and deliberate text selection while editing.
- There is no status bar; `_set_status()` only logs. Show transient feedback beside the controls with `_show_notice(label, msg)`.
- UI wording: plain player language with no jargon (rank, query, scope) and no slash labels like "Mine/Sell".
- "Enable Text Overlay" is the master switch for every overlay, including Auto Prices. Never resize a live TextOverlay with `geometry()`; rebuild it via `show_message()`/`reinstate()`.
- Tables: left-align by default, use `stretch=False` on data columns, set the minimum width to the translated header width, and hide columns via `displaycolumns` (not `width=0`). Resolve columns with `displayed_column()`, reuse `ColumnVisibilityMixin`, and persist widths through `config.py`.

## Build & Packaging

- The user builds. Never run PyInstaller, `app/create_release.py`, or the installer compiler. See [docs/BUILD_RELEASE.md](docs/BUILD_RELEASE.md).
- Keep the image exclusions in `EliteMiningInstaller.iss` and `app/create_release.py` in sync.
- Never write to `sys._MEIPASS`. Load icons via `get_app_icon_path()`.
- Keep `Voiceattack Profile/VA_PROFILE_UPDATE_NOTICE.txt` and `docs/INSTALLER_RELEASE_NOTES.txt` compact, with blank lines only between sections.

## Logs

- Installed: `%LOCALAPPDATA%\EliteMining\logs\elitemining_<timestamp>.log`. Dev: `~\EliteMining.log` plus `.log.1`. INFO and above only; overlay lines are tagged `[OVERLAY]`.

## VoiceAttack (details: [docs/VOICEATTACK_RULES.md](docs/VOICEATTACK_RULES.md))

- When editing `.vap` profiles: preserve the UTF-8 BOM and CRLF, validate the XML, and verify condition pairings. Afterwards, remind the user to re-import the profile.
- Code that adds `.vap` elements must insert them in `COMMAND_ELEMENT_ORDER` (`app/va_keybind_applier.py`), and checks must test that order; VoiceAttack silently ignores out-of-order elements.
- Renaming a player command requires a `COMMAND_RENAMES` entry (`app/va_command_renames.py`), or players lose that command's shortcut.
- Write all `Variables/*.txt` values with `_atomic_write_text()`; values are NATO phonetic and case-sensitive.

## Git

- Commit messages are concise and focus on the why. Attribution trailers follow the tool's guidance.
- For commit and push, use `git add -A`. The `.vap` profile and `docs/INSTALLER_RELEASE_NOTES.txt` are included (the user no longer commits the installer notes separately). Before a release, at most mention once if the shipped profile still has shortcuts.
- The remote is `https://github.com/Viper-Dude/EliteMining.git`. Confirm it still matches, and never change it automatically.

## More docs

- Read [docs/FEATURE_RULES.md](docs/FEATURE_RULES.md) before changing Mining Sessions, Reports, Statistics graphs or Commodity Market searches.
- Read [docs/UI_RULES.md](docs/UI_RULES.md) before creating or changing a dialog, popup, themed widget, overlay window or table.
- Read [docs/ARCHITECTURE_NOTES.md](docs/ARCHITECTURE_NOTES.md) before changing data fetching, background workers, powerplay lookups or marketplace_cache.db.
- Read [docs/VOICEATTACK_RULES.md](docs/VOICEATTACK_RULES.md) before changing VoiceAttack variables, Voice Feedback sounds or the shipped profile.
- Read [docs/VOICEATTACK_UPDATE_HANDOFF.md](docs/VOICEATTACK_UPDATE_HANDOFF.md) before changing the VoiceAttack profile update flow.
- Read [docs/BUILD_RELEASE.md](docs/BUILD_RELEASE.md) before changing build scripts, the splash screen, the installer or release packaging.
- Read [docs/MAIN_SPLIT_HANDOFF.md](docs/MAIN_SPLIT_HANDOFF.md) before changing a tab or dialog in `main.py`, `prospector_panel.py` or `ring_finder.py`; move it into its own module first (move only, then change it; no separate commit, the user commits once per finished task).
- Read [docs/AGENTS-full-backup.md](docs/AGENTS-full-backup.md) only to recover a rule from the old untrimmed file.

## Codex Only

Claude Code ignores this section.

- The user runs Codex on Sol 6.2 by default; recommend only the effort level, and suggest Astra only when the user asks.
- At session start, read `C:\Users\olmba\.claude\projects\d--My-Apps-Work-Folder-Elitemining-Working-folder-Releases-EliteMining-Dev\memory\MEMORY.md` and the relevant linked files. It is context; don't modify it unless asked, and if the path breaks, report it.
- At a task boundary (an unrelated task or a new release), suggest a new session (`/new`) in one line, since usage limits are shared.
- For a requested push, verify the remote URL, the upstream and the remote-tracking reflog, and cite that evidence plus the request in any approval justification. This never authorizes an unrequested push.

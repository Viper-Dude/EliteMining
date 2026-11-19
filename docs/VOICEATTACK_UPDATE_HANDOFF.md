# VoiceAttack updates and player bindings

**Status (19 November 2026): implemented and merged into `main` (up to commit `9b30814`).** Phases 0 to 4 are done. The update flow and the Settings tab **Preserve / Re-apply Keybinds** button now read the player's shortcuts straight from VoiceAttack's data file and merge them into the new profile, so the player no longer exports a profile; the old export steps remain as the fallback. Open items: VoiceAttack 1 was never tested, and the rename list is empty. Everything below is the investigation and plan this work was built from.

The original question was whether a player could install an EliteMining update and keep using their shortcuts without exporting a profile, running **Apply Keybinds**, or importing a replacement. The investigation covered source code and documentation.

## What players need to keep

The maintainer recommends **17 key or button assignments**. Players can bind any player-facing command, including commands outside those 17. Commands named `((…))` are internal commands called by the profile. The bindings discussed here are the keyboard, joystick, and mouse inputs that trigger VoiceAttack commands. Elite Dangerous has its own in-game control bindings.

Success means that each player-assigned shortcut still triggers its intended action after an update, including press, release, double-tap, long-press, and shared-button behavior where configured. If a command is renamed or removed, the updater should identify the affected assignment so the player knows what needs attention.

## How EliteMining works today

- The installer copies a versioned `.vap` into the EliteMining folder. VoiceAttack maintains its own installed copy of the profile. When a profile changes, the current flow asks the player to export their active profile as XML, merges its bindings into the new file, and instructs the player to import that file. A saved export only contains assignments made up to the time it was created. [Installer](../EliteMiningInstaller.iss) · [Startup update and Settings flows](../app/main.py)
- **Apply Keybinds** matches commands by their full `CommandString`. Changing even one spoken alias can break a match. The success dialog counts commands with bindings extracted from the old profile. That count does not establish how many matched or whether VoiceAttack imported the result. [Extractor](../app/va_keybind_extractor.py) · [Applier](../app/va_keybind_applier.py) · [Merge and result dialog](../app/main.py)
- In the v5.6.5 profile inspected, 37 of 306 commands had exactly one action that wrote to `eliteMiningCommand.txt`. For example, “Show sidebar” sends `SIDEBAR:SHOW` and the Python app shows the sidebar. Updating the Python handler alone already preserves that command's bindings. Other commands hold meaningful logic inside VoiceAttack. Continuous Boost uses separate start and stop commands and supports a shared joystick button. [Profile inspected](../Voiceattack%20Profile/EliteMining%20v5.6.5-Profile.vap) · [Boost behavior](VOICEATTACK_PROFILE_HANDOFF.md)

## How often releases change the profile

Checked on 19 November 2026 by comparing the final profile of each release from v5.3.9 to v5.6.6 in git history. Display-only action captions were ignored. "Player commands" excludes internal `((…))` commands. A command whose spoken text changed counts as renamed.

| Release | Player commands renamed or removed | Player commands with changed actions | New player commands |
|---|---|---|---|
| 5.4.3 | 0 | 0 | 0 (identical to 5.3.9) |
| 5.4.7 | 8 | 17 | 5 |
| 5.5.0 | 6 | 21 | 0 |
| 5.5.1 | 8 | 14 | 0 |
| 5.5.2 | 0 | 6 | 0 |
| 5.5.3 | 0 | 5 | 0 |
| 5.5.5 | 1 | 5 | 0 |
| 5.5.6 | 0 | 12 | 0 |
| 5.5.8 | 51 | 35 | 0 |
| 5.5.9 | 0 | 24 | 0 |
| 5.6.0 | 0 | 17 | 0 |
| 5.6.1 | 22 | 30 | 0 |
| 5.6.2 | 0 | 5 | 0 |
| 5.6.4 | 1 | 7 | 0 |
| 5.6.5 | 0 | 14 | 9 |
| 5.6.6 | 0 | 12 | 1 |

- Every release after v5.4.3 changed actions inside existing commands, so each one required a profile replacement. Fifteen profile releases shipped between 20 October and 19 November.
- Most changes are logic inside VoiceAttack: the mining, prospector, cargo scoop, power, firegroup, boost, and jump sequences. They press game keys with timing and conditions, so moving them into the Python app is not straightforward.
- Renames are what lose bindings, because **Apply Keybinds** matches the full `CommandString`. They happened in 7 of 15 releases, mostly as added aliases or typo fixes ("toogle", "monito", "Continouse", "launcer", "discovey"). v5.5.8 renamed 51 and v5.6.1 renamed 22.
- The profile `Id` and nearly every command `Id` are regenerated in every release. `InternalID` is empty at both profile and command level. A `.vax` overwrite import recognises the profile by its `InternalID`, so that would need to be set and kept fixed. A binding tool that matched commands by ID instead of spoken text would also need stable command IDs.
- A rule against renaming existing commands would have prevented the binding losses in those 7 releases. It would not remove the need to replace the profile while sequence logic keeps changing. Only shipping profile changes less often, or moving the sequences out of the profile (for example into a plugin), would do that.
- The individual action differences have not been reviewed one by one. Some may be minor, such as reordered actions.

## What the other products demonstrate

**VAICOM Community v3.1.9.3** has a routine updater that replaces its plugin DLL and restarts VoiceAttack. During initialization the plugin writes its current voice phrases to the `vaicom.keywords` variable and reloads the profile. The commands holding the player's buttons stay in place during this update. This explains how VAICOM can add spoken phrases automatically. It leaves open how to migrate an EliteMining release that changes the actual VoiceAttack commands. **HCS** likewise documents that many Hub updates replace a plugin. Its public FAQ does not describe how it migrates individual VoiceAttack shortcuts. [VAICOM updater script](https://github.com/Penecruz/VAICOM-Community/blob/v3.1.9.3/VAICOM/Resources/Files/Updater_Plugin.txt) · [VAICOM keyword refresh](https://github.com/Penecruz/VAICOM-Community/blob/v3.1.9.3/VAICOM/Client/Initialize/Initialize.cs#L369) · [HCS Hub FAQ](https://www.hcsvoicepacks.com/pages/hcs-hub-faq)

**VAICOM profile structure**, checked on 19 November 2026 against the repository at commit `af6fac5`. VAICOM does not read `VoiceAttack.dat`, use `.vax` packages or `InternalID`, or migrate bindings. Its updates avoid the problem through the design of the profile:

- The main profile has about 40 commands in a 10 KB file, compared with about 300 in EliteMining. Each command passes a fixed label, such as `ptt.hotkey.TX1.press`, to the plugin, which holds all the logic.
- The commands players bind, the push-to-talk press and release commands, stay the same between releases, so there is nothing to migrate.
- All AI communication phrases come from a single command whose phrase is `{TXT:vaicom.keywords}`. The plugin fills that variable on startup and reloads the profile, so new phrases ship with a plugin update.
- Installation is still manual. The plugin writes the `.vap` to its Apps folder only when it is missing, and the player imports it once. Resetting to default overwrites that file.

This suits VAICOM because its commands mostly pass phrases to DCS. EliteMining's commands run timed key-press sequences inside VoiceAttack, and those sequences are where most profile changes happen. VAICOM confirms the direction of a small, stable profile with the logic elsewhere, but offers no shortcut for carrying bindings across a profile replacement. [Profile writer](https://github.com/Penecruz/VAICOM-Community/blob/af6fac5/VAICOM/FileManager/Root_Profile.cs) · [Main profile](https://github.com/Penecruz/VAICOM-Community/blob/af6fac5/VAICOM/Resources/Files/VAICOM%20PRO%20for%20DCS%20World.vap)

**VoiceAttack package import** is another route for first installs or releases that genuinely need to replace a profile. VoiceAttack documents replacing a profile from a `.vax` package in its Import folder when the old and new profiles share an `InternalID` and overwrite is enabled (`OP=1`). The documented preservation flags cover profile options and saved variables. There is no documented guarantee there for individual command shortcuts. The bundled EliteMining v5.6.5 profile has an empty `InternalID` and `OP=0`. A profile author's installation guide also describes an import confirmation after restart. Prompt behavior for an EliteMining package has yet to be tested. [VoiceAttack manual, p. 288](https://www.voiceattack.com/VoiceAttackHelpV2.pdf#page=288) · [Package installation example](https://docs.alternerd.tv/VoiceAttack-profiles/installing/#import-profiles-package)

## Plugin option

Discussed on 19 November 2026. EliteMining had its own VoiceAttack plugin (`EliteMiningPlugin`, C#, built for .NET Framework 4.8 and .NET 8). It was removed in v5.0.0 because file messaging through `eliteMiningCommand.txt` covered every use. The project is still in the repo, and the installer entry is commented out. [Plugin project](../EliteMiningPlugin/README.md) · [Installer](../EliteMiningInstaller.iss)

- A plugin does not preserve bindings by itself. Shortcuts are stored on the profile's commands. A plugin cannot create commands or assign shortcuts, so first installs and releases that add commands still need a profile import.
- It would help only if the profile became a fixed set of thin wrapper commands, with the sequence logic moved into the DLL. Behaviour changes would then ship as a new DLL without touching the profile. Converting to that design would itself be one large profile change and binding migration.
- The commands that already write to `eliteMiningCommand.txt` get the same benefit without a plugin.
- VAICOM and HCS use plugins for things file messaging cannot do: real-time two-way communication, immediate return values, phrase lists built on the fly, and pack management. Binding preservation is not why they use plugins.
- The practical downsides are VoiceAttack restarts to load a new DLL, enabling plugin support, two .NET targets, antivirus warnings on an unsigned DLL, a plugin fault affecting VoiceAttack, and a second codebase. The maintainer considers these minor.

**Decision:** no plugin for now, and not for the binding problem. Reconsider if file messaging becomes slow or unreliable, if VoiceAttack needs immediate answers from the app, if large auto-updating phrase lists are wanted, or if the sequence logic should move out of the profile. The release comparison above shows that logic is where most profile changes happen.

## Where to resume

A small test is worth doing. A full redesign remains an open decision. Its value depends on how often releases require profile changes and how much trouble players experience carrying their bindings forward.

1. Recent profile changes are summarised above. Recheck the current shipped profile and pick a change to an existing app action and a change that genuinely needs a new voice phrase or bindable command.
2. Use a disposable profile. Give it a keyboard shortcut, a joystick shortcut outside the recommended 17, and a shared-button or release-triggered action. Record what each does. Test an app-only update first, then prototype adding a spoken phrase through a variable and reloading the profile. Check whether that phrase also needs to be individually bindable.
3. Assess first installation and migration from an existing customized profile separately. Record every prompt, restart, export, and import actually observed. If replacement is needed, check the assignments in VoiceAttack after the update and exercise them. Report what happens to renamed commands, cleared bindings, and settings on the shared button.

## Implementation plan: read bindings directly from VoiceAttack

Drafted on 19 November 2026. The goal is to remove the manual export step. The app reads the player's current EliteMining profile from VoiceAttack's own data file, copies its bindings onto the new `.vap`, and the player only imports the result. VoiceAttack stores all profiles in `%APPDATA%\VoiceAttack2\VoiceAttack.dat` (`%APPDATA%\VoiceAttack\` for VoiceAttack 1), with timestamped copies in its `Backup` subfolder. On the maintainer's machine both the live file and the backups are LiteDB databases. VoiceAttack does not document this file for other programs to read.

### Phase 0: feasibility test (no app changes)

1. Copy the newest file from `%APPDATA%\VoiceAttack2\Backup` to the scratchpad. Never open the live `VoiceAttack.dat`.
2. Write a throwaway .NET console tool with the LiteDB library to open that copy read-only. The .NET 8 SDK is installed.
3. Check that the EliteMining profile can be found by name, that its commands and `CommandString` values can be read, and that the binding fields can be read: keyboard, joystick 1 and 2, mouse, release, double-tap, long-press, and shared-button options.
4. Export the same profile from VoiceAttack as XML and compare the bindings command by command.

**Go/no-go:** continue if the database stores readable fields. If each profile is stored as one encoded blob, VoiceAttack's internal format would have to be decoded. Stop there and only do Phase 2, which improves the current export flow.

### Phase 0 result (19 November 2026)

**Go, pending the maintainer's decision on the blob rule.** Strictly, each profile is one encoded blob. But the encoding is simple and decoded completely, and every command field matched the XML export.

- **Format.** `VoiceAttack.dat` is a LiteDB v5 file with one collection, `VAMain`. Each record is one profile: `_id` (GUID), `Data` (binary) and `Version` (1). `Data` is raw deflate. Inflated, it is a ZeroFormatter-style object: total size, last field index, a table of field offsets, then the values. Strings are a length followed by UTF-8 text; null is -1. A nullable bool is a presence byte followed by a value byte. A nullable GUID is a flag byte followed by 16 bytes.
- **Profile record.** Field 0 is the profile Id and field 1 the name. Field 2 is the command list: a count followed by command objects, each recording its own size. Find the EliteMining profile by name. The maintainer's file holds 11 EliteMining profiles (v5.1.7 to v5.6.6), so the reader must choose the right one rather than the first match.
- **Command fields (85 per command).** 0 `BaseId`, 1 `CommandString`, 2 action sequence (nested), 4 `Enabled`, 8 `UseShortcut`, 9 `keyValue`, 10 `keyShift`, 11 `keyAlt`, 12 `keyCtrl`, 13 `keyWin`, 14 `keyPassthru`, 16 `onlyKeyUp`, 24 `UseJoystick`, 25 `joystickNumber`, 26 `joystickButton`, 27 `joystickNumber2`, 28 `joystickButton2`, 29 `joystickUp`, 30 `KeepRepeating`, 37 `UseMouse`, 38–46 `Mouse1`–`Mouse9`, 47 `MouseUpOnly`, 48 `MousePassThru`, 49 `joystickExclusive`, 54–56 `RepeatIfKeysDown`/`RepeatIfMouseDown`/`RepeatIfJoystickDown`, 60 `UseVariableHotkey`, 68–73 hotkey, mouse and joystick double-tap and long-tap levels, 79 `UseVariableMouseShortcut` and 81 `UseVariableJoystickShortcut`. The XML elements `DoubleTapInvoked`, `LongTapInvoked` and `ShortTapDelayedInvoked` are always false in the export. The tap level fields hold the actual setting.
- **Comparison.** The v5.6.6 profile was checked against an XML export of it (`Voiceattack Profile/Test_profile/EliteMining v1.0.0-Profile.vap`) across all 308 commands. All 41 binding-related fields matched. Fields that vary in the export were matched by value: `Enabled`, keyboard key and Shift/Ctrl, `keyPassthru`, `onlyKeyUp`, both joysticks, `MousePassThru`, `RepeatIfJoystickDown`, and joystick double-tap and long-tap levels.
- **Mapped by position only.** These were off for every command in the export: mouse buttons, Alt/Win, joystick and mouse release, keyboard and mouse tap levels, variable shortcuts and `joystickExclusive`. Confirm them with a disposable profile that uses each option, an export, and a fresh backup. VoiceAttack 1 was not tested.
- **Internal commands.** Commands named `((…))` are called by other commands and are never bound to a key or button. Skip them when reading and merging. Of the 308 commands, 66 are internal and none has a shortcut enabled. Two still hold leftover joystick values with the joystick shortcut switched off: `((Start continuous prospector sequence))` and `((startup reset all silence executed))`. Of the 242 player commands, 68 have a shortcut enabled.
- **No stable command ID.** `BaseId` differed for every command, unchanged ones included, between the stored v5.4.7, v5.5.9 and v5.6.1 profiles and v5.6.6. Matching must stay on `CommandString` plus the rename list.
- **Backups.** File names use a 12-hour clock (`20261119014435` is 13:44), so sorting by name does not find the newest. Use the file's modification time.
- **Existing extractor (Phase 2).** In a VoiceAttack 2 export, keyboard shortcuts are `keyValue`/`keyShift`/`keyAlt`/`keyCtrl`/`keyWin`. Mouse buttons are `Mouse1`–`Mouse9`. Release is `onlyKeyUp`/`joystickUp`/`MouseUpOnly`. `VAKeybindExtractor` reads `CommandKeyValue`, `MouseValue`, `KeysReleased`, `JoystickValue` and similar names that this export does not contain, so it currently carries over only joystick bindings. `is_command_enabled()` compares against `"True"`, but the export writes `true`.

### Phase 1: reader helper

- Build a small `va_profile_reader.exe` targeting .NET Framework 4.8, which every Windows 10 and 11 machine has.
- Input: the path to `VoiceAttack.dat` and a profile name. Output: the profile's commands and bindings as XML in the same shape as an exported `.vap`, so the existing extractor reads it unchanged.
- Always work on a temporary copy and never write to VoiceAttack's file. Check both the VoiceAttack 2 and VoiceAttack 1 folders.

### Phase 1 result (19 November 2026)

**Done on branch `va-binding-reader`.** The reader works on the maintainer's data, and every field mapped by position only in Phase 0 is now confirmed.

- **Helper.** `tools/va_profile_reader/` (C#, .NET Framework 4.8, LiteDB 5.0.21). `list <copy> <out.xml>` lists every profile with its player-command and bound counts. `export <copy> <profile id> <out.xml>` writes the profile's player commands with `BaseId`, `CommandString` and the 41 binding fields, using the VoiceAttack 2 export element names; internal `((…))` commands are skipped. It refuses any path inside `%APPDATA%\VoiceAttack2\` or `%APPDATA%\VoiceAttack\` (exit 4). It exits 3 on any unexpected layout: a record `Version` other than 1, a field whose width differs from its fixed table, fewer than 82 command fields, or out-of-range offsets. Field widths were identical across all 6,978 stored commands in 18 profiles.
- **Python wrapper.** `app/va_profile_reader.py` finds the newest backup by modification time in both VoiceAttack folders, copies it to a temp folder, chooses the profile and exports it. It is not yet called from `main.py`. `VAProfileParser.version_from_name()` is shared with the update check.
- **Profile choice.** Candidates are profiles whose name starts with "EliteMining". A single candidate wins. Otherwise the order is: the one matching `installed_version` in `va_profile_state.json`, then the highest version among those with bindings, then the one with more bindings. A tie, or no candidate, gives no pick. The dev state file holds a stale `4.8.9`. Phase 3 must keep it current, or a stale value could select an old profile.
- **Checks.** `tools/check_va_profile_reader.py selftest` covers the choice rules and the 12-hour-clock backup names. `real --export` against the v5.6.6 export found 242 player commands, 68 with a shortcut, and 0 mismatches over 41 fields.
- **Position-only fields confirmed.** A generated 20-command test profile set Alt/Win, Mouse3–Mouse9, mouse and joystick release, the keyboard and mouse tap levels, `joystickExclusive` and the three variable-shortcut switches. Read back from the backup written at import, it gave 0 mismatches. Mouse1 and Mouse2 were not set; they sit directly before Mouse3 in the field order.
- **Backups do not lag.** The backup written at import already contained the imported profile and had the same modification time as the live file.
- **Variable shortcut names are not mapped.** The export omits the field holding the variable name when it is empty. The test profile switched variable shortcuts on without a name, and VoiceAttack crashed (`NullReferenceException` in `GetTextVariables`) on import and whenever the profile was selected. The maintainer restored the pre-import backup. Phase 2 must never carry a variable shortcut over without its name; skip those fields until the name is mapped. None of the 242 player commands uses one.
- **Packaging (Phase 3).** The exe needs `LiteDB.dll` and `System.Buffers.dll` beside it. The build output is git-ignored, and `_reader_exe_path()` only knows the dev path. The unused `tools/VAProfileHelper.csproj` would also compile the new `Program.cs` if anyone built it.
- VoiceAttack 1 remains untested.

### Phase 2: improve the merge (useful either way)

- Reuse `VAKeybindExtractor` and `VAKeybindApplier`, which already cover the binding fields. [Extractor](../app/va_keybind_extractor.py) · [Applier](../app/va_keybind_applier.py)
- Add a maintained rename list (old `CommandString` to new) so renamed commands keep their bindings. This covers the losses in 7 of 15 recent releases.
- Fall back to matching commands that share at least one spoken phrase when the list has no entry.
- Change the result dialog in `_merge_profiles_with_keybinds()` ([main.py](../app/main.py)) to report how many bindings were applied and list those that were not, instead of the extracted count.

### Phase 2 result (19 November 2026)

**Done on branch `va-binding-reader`.** Not yet tested in VoiceAttack; the maintainer chose to test it together with Phase 3 in Phase 4.

- **Extractor.** `CommandKeybinds` now holds the VoiceAttack 2 export fields: `keyValue`/`keyShift`/`keyAlt`/`keyCtrl`/`keyWin`, `keyPassthru`, `onlyKeyUp`, both joysticks, `joystickUp`, `joystickExclusive`, `Mouse1`–`Mouse9`, `MouseUpOnly`, `MousePassThru` (nullable), the three repeat flags, `KeepRepeating`, `Enabled` and the six tap levels. The old invented names and the always-false `DoubleTapInvoked`/`LongTapInvoked`/`ShortTapDelayedInvoked` are gone. A command counts as bound only when `UseShortcut`, `UseJoystick` or `UseMouse` is true, so leftover joystick values are ignored. Internal `((…))` commands are skipped. `is_command_enabled()` compares case-insensitively.
- **Variable shortcuts.** When `UseVariableHotkey`, `UseVariableMouseShortcut` or `UseVariableJoystickShortcut` is on, that shortcut group is dropped and the command is listed in `extractor.skipped` with reason `variable`. The applier never writes the variable flags.
- **Applier.** Writes only the groups enabled in the old command; other groups keep the new profile's defaults. Internal commands in the new profile are never touched. Matching order: exact `CommandString`, then the rename list (only if the new name exists and is not already taken by an exact match), then a spoken phrase (split on `;`, case-insensitive) shared with exactly one unclaimed new command. A phrase that fits several new commands, or a new command picked by several old ones, is reported as `ambiguous`; no match is `no_match`. `apply()` still returns the tree; the outcome is in `applier.last_result` (`applied`, `matched_by`, `not_applied`).
- **Rename list.** `app/va_command_renames.py` (`COMMAND_RENAMES`), empty for now. Past renames were not reconstructed; add entries when a release renames a command.
- **Result dialog.** `_merge_profiles_with_keybinds()` shows the applied count and lists up to 15 bindings that were not applied with a reason (English and German strings added). The "no keybinds" dialog shows only when nothing was bound and nothing was skipped.
- **Checks.** `tools/check_va_keybind_merge.py`: the v1.0.0 test export gives 68 bound player commands and no internal ones; applying them to a copy with bindings cleared and re-reading gives identical bindings; synthetic cases cover rename, phrase match, ambiguous match, no match, variable skip and a disabled command. 18 of 18 pass.
- `strings_de.json` already had duplicate keys in its `voiceattack` section; the new keys were added once after the last copy, which is the one that takes effect.

### Phase 3: update flow

1. After an update, the app detects the changed profile as it does today.
2. It asks the player to close VoiceAttack so it reads a consistent copy.
3. The helper reads the current EliteMining profile, and the merge applies its bindings to the new `.vap`.
4. The player imports the merged profile and selects it.
5. If any step fails, the app falls back to the current export flow.

Run this in the app, not the installer. The app already has the update flow, the merge code, and localized dialogs that the installer would otherwise have to duplicate in Inno Setup.

### Phase 3 result (19 November 2026)

**Done on branch `va-binding-reader`.** Not yet tested in VoiceAttack; that is Phase 4.

- **Flow.** After Yes on the update dialog, the state file is saved as before, then `_va_profile_auto_merge()` in `main.py` runs. If VoiceAttack is running, the player is asked to close it (Yes checks again, No goes to the export flow). The reader runs on a background thread with the previous `installed_version` as the hint. The player confirms the profile found ("'EliteMining v5.6.5' with 68 shortcuts") before the existing `_merge_profiles_with_keybinds()` merges the reader's XML into the new `.vap`; the existing success dialog explains the import. A failed read, No at the confirmation, or a merge error shows one notice and falls back to the unchanged export flow, now `_va_profile_export_merge()`. The temp folder is always deleted. The Settings tab **Apply Keybinds** still uses the export flow.
- **Data file.** `newest_data_file()` picks the newest by modification time of the backups and, once VoiceAttack is confirmed closed, the live `VoiceAttack.dat`. This relaxes the Phase 0 rule: the live file is copied while VoiceAttack is closed, and the helper only opens the copy. A live file with a `VoiceAttack-log.dat` beside it is skipped because it may hold unwritten changes. If the running check itself fails, only backups are read. `VAProcessManager.is_running()` is now a staticmethod. Phase 1 only saw a backup written at import; whether VoiceAttack writes one when a binding changes is still unknown, which is why the live file is included.
- **Packaging.** In the installed app the helper is looked for in `Configurator\va_profile_reader\`. The installer copies the build output there, excluding the `.pdb`, and so does the ZIP. `create_release.py` runs `dotnet build tools/va_profile_reader -c Release` after PyInstaller and aborts if it fails. `tools/VAProfileHelper.csproj` now excludes `va_profile_reader\**`. The import of `psutil` comes in through `va_process_manager`; if the frozen build lacks it, the running check fails and only backups are read.
- **Changes after the first installed test.**
  - The state file is now saved only when the flow ends: after a successful merge, after the export flow whatever its outcome, or on No at the first dialog. An interrupted update is then offered again on the next start.
  - Each step is logged under `[VA_PROFILE]`: every answer, the read result with the reason the profile was chosen, and the start and end of the export flow.
  - The profile confirmation now appears only when `VAProfileReadResult.guessed` is true: several EliteMining profiles and no match for the previous version. Its Yes button reads "Yes (recommended)" through a new optional `yes_text` on `centered_askyesno()`.
  - The success dialog is shorter and names the source profile (`merge_source`). The Settings tab flow uses the same text, without a source.
  - The update check runs only in the installed app (`main.py` skips it unless frozen), so this flow cannot be tested with `python app/main.py`.
- **Installed test (19 November 2026).** A ShareX screenshot during the first run seemed to close the "Close VoiceAttack" prompt; no later step left a trace, and the cause was not found. The second run, with ShareX screenshots of every dialog, with VoiceAttack closed and the v5.6.6 profile renamed "EliteMining v5.6.5" in VoiceAttack: read it by version match from the newest backup, applied 68 of 68 shortcuts, and saved the state at the end. Importing the merged profile and exercising the shortcuts are left to Phase 4.
- **Element order bug (found at import).** VoiceAttack imported the merged profile without any of the 68 shortcuts. `clear_keybinds.py` strips unbound fields from the shipped profile, for example every joystick field, and the applier appended the missing elements at the end of each command. VoiceAttack silently ignores command elements that are out of its export order. `VAKeybindApplier._set()` now inserts missing elements at their place in `COMMAND_ELEMENT_ORDER` (98 elements, taken from the v1.0.0 export, where all 308 commands follow it). `check_va_profile_reader.py real --merge` now fails if any merged command is out of order; the earlier checks read the file back with Python, which ignores order. A profile merged with the fix imported with all shortcuts in place, including the shared Boost button. The installed app still had the old applier at the time.
- **Installed test after the order fix (19 November 2026).** Build with commit `c1ad65c`, VoiceAttack closed, state file at 5.6.5, v5.6.6 profile renamed "EliteMining v5.6.5" in VoiceAttack. The update flow ran without the profile question, the merged profile imported with every shortcut in place, and the dialogs looked right. Phase 4 still has the edge cases below.
- **Settings button.** **Preserve / Re-apply Keybinds** now runs the same flow against the newest `EliteMining v*-Profile.vap` in the EliteMining folder (`_manual_va_keybind_preserve()`), with no installed-version hint, so it picks the highest version that has shortcuts and asks only when it has to guess. Without a shipped profile in the folder it uses the old two-file picker (`_manual_va_keybind_preserve_files()`). A manual run does not change the saved installed version. Compile-checked only; the button was not clicked through.
- **Dialogs need an answer.** In a later installed test the first update dialog closed as "No" without the player clicking No: the window's close button and Escape both counted as No, and the version was then saved as handled. This is the likely cause of the earlier vanished "Close VoiceAttack" prompt too. `centered_askyesno()` has an opt-in `require_answer` mode, used for the update dialog, the close prompt and the profile confirmation: the close button and Escape do nothing, and a minimized dialog is restored. Compile-checked only.
- **Profile tie message.** When two candidate profiles cannot be told apart (same version and same number of shortcuts, for example two profiles both named "EliteMining v5.6.6"), the reader sets `va_profile_reader.last_failure` to a reason starting with `TIE_PREFIX`, and the app shows `profiles_tie_message` instead of the generic read failure before the export steps. Seen in an installed test; the second run worked once one copy was gone.
- **Rename test.** Renaming "Toggle night vision" to "NightVison" in the new profile without a `COMMAND_RENAMES` entry gave 67 of 68, and the success dialog listed the command as not carried over, as intended.
- **Installer prompt.** When the VoiceAttack profile task is selected, `PrepareToInstall` in `EliteMiningInstaller.iss` checks through WMI whether `VoiceAttack.exe` is running. If it is, the installer asks the player to close it (OK checks again, Cancel continues the install). The in-app prompt stays as the backstop for ZIP installs and for players who reopen VoiceAttack before starting EliteMining. Not compiled or tested yet.
- **Strings.** New English and German strings for the close prompt, the confirmation and the fallback notice. `profile_update_message` no longer says an export is needed. German has the update message in both duplicate copies; the new keys sit in the last copy, which is the one that takes effect.
- **Checks.** `tools/check_va_profile_reader.py selftest` adds the data-file choice (live ignored while VoiceAttack may run, newer live used when closed, newer backup beats older live, pending log skipped, `VoiceAttack_crashed.dat` ignored) and the installed and dev helper paths. `real --installed 5.6.6 --export <v1.0.0 export> --merge "Voiceattack Profile/EliteMining v5.6.6-Profile.vap"` read 242 player commands with 68 shortcuts, 0 mismatches over 41 fields against the export, and merged 68 of 68 into a copy of the shipped profile with 0 field mismatches. `tools/check_va_keybind_merge.py` still passes. The release builder, installer and ZIP were not built.

### Phase 4: testing

- Use a disposable profile with a keyboard shortcut, a joystick shortcut outside the recommended 17, a release-triggered command, a double-tap command, and a shared Boost button.
- Cover VoiceAttack 1 and 2, a renamed command, a removed command, a profile the player renamed, two EliteMining profiles, and a missing or unreadable data file.
- After importing, check the assignments in VoiceAttack and exercise them.

### Phase 4 result (19 November 2026)

**Automated checks done; manual edge cases pending.**

- **Automated.** `tools/check_va_keybind_merge.py` now also applies the 68 bindings to the real shipped v5.6.6 profile and fails if any command is out of VoiceAttack's element order or holds an element missing from the order list, and covers an old profile with no shortcuts. It already covered rename-list, shared-phrase, ambiguous, removed and variable-shortcut cases. `check_va_profile_reader.py selftest` now covers failed reads: missing data file, a folder instead of a file, random bytes, an empty file and a missing helper all return `None` and leave no temp folder behind, which sends the update flow to the export steps.
- **Patch notes.** Two lines added to `docs/PATCHNOTES_v5.6.6.md`.
- **Installed tests.** The full update on the maintainer's machine imported with every shortcut, including the shared Boost button.
- **Not tested.** VoiceAttack 1, a command renamed by a real release, a player-renamed profile that no longer starts with "EliteMining" (falls back to the export steps), a manual check that a double-tap or release-triggered shortcut still fires after import (their fields round-trip in the checks, and the release fields were confirmed from a backup in Phase 1), and the missing or locked data file in the installed app.
- **Release rule.** Renaming an existing command still needs a `COMMAND_RENAMES` entry in `app/va_command_renames.py`; the list is empty.

### Later, as a separate decision

- Test a `.vax` overwrite import with a fixed `InternalID`, which could remove the import step.
- Add a release rule: renaming an existing command requires updating the rename list.

**Main risk:** a VoiceAttack update could change the data file and break the helper. The export flow stays as the fallback for that reason.

### Recommended model and settings

| Work | Model | Effort | Notes |
|---|---|---|---|
| Phase 0 feasibility test | Opus 5.5 | High | Investigating an undocumented format. Work only on copies in the scratchpad. |
| Phase 1 helper and Phase 3 update flow | Opus 5.5 | High | Start in plan mode and approve the plan before code changes. New C# component plus changes to the update flow. |
| Phase 2 merge improvements | Sonnet 5.5 | Medium | Contained changes to existing Python modules. Use Opus 5.5 if matching rules get complicated. |
| Phase 4 tests and patch notes | Sonnet 5.5 | Medium | Focused tests; the maintainer does the manual VoiceAttack checks. |

Start a new chat for each phase. Keep the default permission mode so file writes outside the scratchpad and any VoiceAttack file access ask first.

**Model prompts (required):** the assistant cannot change its own model or effort. At the start of each phase, and whenever work moves to a row in the table above with a different model or effort, the assistant must stop, tell the maintainer which model and effort to switch to (with `/model` and the effort setting), and wait for confirmation before continuing. If the current model or effort does not match the table, say so before starting.

**Prompt for a future chat**

> Read `docs/VOICEATTACK_UPDATE_HANDOFF.md` and compare the findings with the current checkout. Follow its model prompts: tell me which model and effort Phase 0 needs and wait for me to confirm the switch. Then start Phase 0 of the implementation plan: test, on a copy of a VoiceAttack backup only, whether the EliteMining profile's commands and bindings can be read from `VoiceAttack.dat`. Report the go/no-go result before changing any app code.

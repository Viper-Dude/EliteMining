# VoiceAttack updates and player bindings

**Parked on 18 November 2026.** The question is whether a player could install an EliteMining update and keep using their shortcuts without exporting a profile, running **Apply Keybinds**, or importing a replacement. The investigation covered source code and documentation. A live update test and a decision about implementation are still pending.

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

### Phase 1: reader helper

- Build a small `va_profile_reader.exe` targeting .NET Framework 4.8, which every Windows 10 and 11 machine has.
- Input: the path to `VoiceAttack.dat` and a profile name. Output: the profile's commands and bindings as XML in the same shape as an exported `.vap`, so the existing extractor reads it unchanged.
- Always work on a temporary copy and never write to VoiceAttack's file. Check both the VoiceAttack 2 and VoiceAttack 1 folders.

### Phase 2: improve the merge (useful either way)

- Reuse `VAKeybindExtractor` and `VAKeybindApplier`, which already cover the binding fields. [Extractor](../app/va_keybind_extractor.py) · [Applier](../app/va_keybind_applier.py)
- Add a maintained rename list (old `CommandString` to new) so renamed commands keep their bindings. This covers the losses in 7 of 15 recent releases.
- Fall back to matching commands that share at least one spoken phrase when the list has no entry.
- Change the result dialog in `_merge_profiles_with_keybinds()` ([main.py](../app/main.py)) to report how many bindings were applied and list those that were not, instead of the extracted count.

### Phase 3: update flow

1. After an update, the app detects the changed profile as it does today.
2. It asks the player to close VoiceAttack so it reads a consistent copy.
3. The helper reads the current EliteMining profile, and the merge applies its bindings to the new `.vap`.
4. The player imports the merged profile and selects it.
5. If any step fails, the app falls back to the current export flow.

Run this in the app, not the installer. The app already has the update flow, the merge code, and localized dialogs that the installer would otherwise have to duplicate in Inno Setup.

### Phase 4: testing

- Use a disposable profile with a keyboard shortcut, a joystick shortcut outside the recommended 17, a release-triggered command, a double-tap command, and a shared Boost button.
- Cover VoiceAttack 1 and 2, a renamed command, a removed command, a profile the player renamed, two EliteMining profiles, and a missing or unreadable data file.
- After importing, check the assignments in VoiceAttack and exercise them.

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

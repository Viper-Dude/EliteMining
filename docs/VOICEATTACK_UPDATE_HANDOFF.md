# VoiceAttack updates and player bindings

**Parked on 18 November 2026.** The question is whether a player could install an EliteMining update and keep using their shortcuts without exporting a profile, running **Apply Keybinds**, or importing a replacement. The investigation covered source code and documentation. A live update test and a decision about implementation are still pending.

## What players need to keep

The maintainer recommends **17 key or button assignments**. Players can bind any player-facing command, including commands outside those 17. Commands named `((…))` are internal commands called by the profile. The bindings discussed here are the keyboard, joystick, and mouse inputs that trigger VoiceAttack commands. Elite Dangerous has its own in-game control bindings.

Success means that each player-assigned shortcut still triggers its intended action after an update, including press, release, double-tap, long-press, and shared-button behavior where configured. If a command is renamed or removed, the updater should identify the affected assignment so the player knows what needs attention.

## How EliteMining works today

- The installer copies a versioned `.vap` into the EliteMining folder. VoiceAttack maintains its own installed copy of the profile. When a profile changes, the current flow asks the player to export their active profile as XML, merges its bindings into the new file, and instructs the player to import that file. A saved export only contains assignments made up to the time it was created. [Installer](../EliteMiningInstaller.iss) · [Startup update and Settings flows](../app/main.py)
- **Apply Keybinds** matches commands by their full `CommandString`. Changing even one spoken alias can break a match. The success dialog counts commands with bindings extracted from the old profile. That count does not establish how many matched or whether VoiceAttack imported the result. [Extractor](../app/va_keybind_extractor.py) · [Applier](../app/va_keybind_applier.py) · [Merge and result dialog](../app/main.py)
- In the v5.6.5 profile inspected, 37 of 306 commands had exactly one action that wrote to `eliteMiningCommand.txt`. For example, “Show sidebar” sends `SIDEBAR:SHOW` and the Python app shows the sidebar. Updating the Python handler alone already preserves that command's bindings. Other commands hold meaningful logic inside VoiceAttack. Continuous Boost uses separate start and stop commands and supports a shared joystick button. [Profile inspected](../Voiceattack%20Profile/EliteMining%20v5.6.5-Profile.vap) · [Boost behavior](VOICEATTACK_PROFILE_HANDOFF.md)

## What the other products demonstrate

**VAICOM Community v3.1.9.3** has a routine updater that replaces its plugin DLL and restarts VoiceAttack. During initialization the plugin writes its current voice phrases to the `vaicom.keywords` variable and reloads the profile. The commands holding the player's buttons stay in place during this update. This explains how VAICOM can add spoken phrases automatically. It leaves open how to migrate an EliteMining release that changes the actual VoiceAttack commands. **HCS** likewise documents that many Hub updates replace a plugin. Its public FAQ does not describe how it migrates individual VoiceAttack shortcuts. [VAICOM updater script](https://github.com/Penecruz/VAICOM-Community/blob/v3.1.9.3/VAICOM/Resources/Files/Updater_Plugin.txt) · [VAICOM keyword refresh](https://github.com/Penecruz/VAICOM-Community/blob/v3.1.9.3/VAICOM/Client/Initialize/Initialize.cs#L369) · [HCS Hub FAQ](https://www.hcsvoicepacks.com/pages/hcs-hub-faq)

**VoiceAttack package import** is another route for first installs or releases that genuinely need to replace a profile. VoiceAttack documents replacing a profile from a `.vax` package in its Import folder when the old and new profiles share an `InternalID` and overwrite is enabled (`OP=1`). The documented preservation flags cover profile options and saved variables. There is no documented guarantee there for individual command shortcuts. The bundled EliteMining v5.6.5 profile has an empty `InternalID` and `OP=0`. A profile author's installation guide also describes an import confirmation after restart. Prompt behavior for an EliteMining package has yet to be tested. [VoiceAttack manual, p. 288](https://www.voiceattack.com/VoiceAttackHelpV2.pdf#page=288) · [Package installation example](https://docs.alternerd.tv/VoiceAttack-profiles/installing/#import-profiles-package)

## Where to resume

A small test is worth doing. A full redesign remains an open decision. Its value depends on how often releases require profile changes and how much trouble players experience carrying their bindings forward.

1. Recheck the current shipped profile and recent profile changes. Pick a change to an existing app action and a change that genuinely needs a new voice phrase or bindable command.
2. Use a disposable profile. Give it a keyboard shortcut, a joystick shortcut outside the recommended 17, and a shared-button or release-triggered action. Record what each does. Test an app-only update first, then prototype adding a spoken phrase through a variable and reloading the profile. Check whether that phrase also needs to be individually bindable.
3. Assess first installation and migration from an existing customized profile separately. Record every prompt, restart, export, and import actually observed. If replacement is needed, check the assignments in VoiceAttack after the update and exercise them. Report what happens to renamed commands, cleared bindings, and settings on the shared button.

**Prompt for a future chat**

> Read `docs/VOICEATTACK_UPDATE_HANDOFF.md` and compare the findings with the current checkout. I want to revisit whether we can simplify VoiceAttack installation and updates while preserving every player-assigned binding. Start with the smallest test that will tell us what a player would actually have to do.

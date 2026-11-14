# VoiceAttack profile handoff — 2026-11-14

## Current work

- Work-in-progress profile: `Voiceattack Profile/EliteMining v5.6.1-Profile.vap`.
- The user has used this profile successfully in-game for a long time. Preserve its working structure; make targeted changes only.
- The user plans several days of gameplay testing before releasing this update. These latest changes have been checked structurally, but gameplay testing is pending. Do not release or build unless asked.

## Changes made

### Prepare for mining

Current spoken aliases: `Prepare for mining;mining standby;reset scoop;reset power;reset firegroup`.

- The firegroup-only path now sets `resetScoop` to True and plays `retract_scoop_set_power_and_firegroup` before setting the firegroup.
- The scoop and power paths share `soundPowersetting` so the starting announcement does not play twice when both need changing. The flag is initialized for each invocation and cleared after the scoop announcement.
- `resetScoopWasResettingMining` records whether `resetLasermining` was True at initiation.
- An active Reset Mining sequence is stopped in that initial check, before preparation changes, including when scoop and power are already correct.
- `mining_sequence_reset_complete` plays after preparation only when that initial snapshot was True.

### Continuous boost

- Start and Stop no longer have their main actions gated by whether another feedback sound is playing. Only the feedback pause remains conditional.
- Start clears `continuousBoost` after its loop, inside its start-condition block. A skipped Start must not clear another running sequence's active flag.
- Stop kills the Start command and clears `continuousBoost` before any sound wait or termination announcement.
- Support both shared-button Start/Stop setups and separate buttons. The user's shared binding is displayed as joystick button 12; the exported value is 11. Bindings were not changed.

### Wording

- Corrected spelling and obvious grammar in command names/spoken aliases and event-log text, including missing spoken-alias separators.
- Corrected the weapons, seismic charge launcher, and mining laser firegroup query log labels from “Timer for target” to the corresponding firegroup description. Variable tokens and saved values were unchanged.
- Internal Execute/Kill references were verified to resolve by command ID after the spelling pass. A later user export regenerated IDs; use IDs from the current profile, never hardcoded IDs from earlier conversation history or temporary edit scripts.

## Validation and next steps

- Edits were checked by parsing XML, checking changed condition/loop pairings, and comparing unaffected commands. UTF-8 BOM and CRLF were preserved.
- Re-import the updated profile into VoiceAttack for gameplay testing; exporting/importing can change IDs and metadata, so always inspect the latest file before patching.
- Test shared and separate boost buttons, repeated Start, stopping during an announcement, and preparation with each scoop/power/firegroup combination while Reset Mining is active and inactive.
- The four review findings discussed with the user have been addressed. No further confirmed review items remain; this was not a guarantee that every possible runtime path is fault-free.
- Claude instruction and memory originals were not modified. Read the project's `CLAUDE.md` and saved project memory as usual, then this handoff note.

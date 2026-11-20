# EliteMining — VoiceAttack Rules

Details moved out of [AGENTS.md](../AGENTS.md). The critical profile-editing rules stay there; the update flow itself is in [VOICEATTACK_UPDATE_HANDOFF.md](VOICEATTACK_UPDATE_HANDOFF.md).

- **Profile update testing**: the profile update flow runs only in the installed app, not in `python app/main.py`; test it with a built installer and `va_profile_state.json` set to an older version.
- **Variables**: values in `Variables/*.txt` use NATO phonetic (A→Alpha, C→Charlie) and are case-sensitive. `NATO_REVERSE` maps back ("ALPHA" → "A"). `VA_VARS` in `main.py` maps tools to variable files. Use `_atomic_write_text()` for all variable writes because VoiceAttack polls continuously.
- **Voice Feedback sounds**: the app writes `soundPath_<event>.txt` (wav path, `none`, or `tts`); the `((Play Feedback Sound))` command in the `.vap` reads it, and for `tts` writes the event name to `soundTrigger.txt` for the app to speak. Changing this contract means editing and re-exporting the profile. Events come from `Sound_Packs/<pack>/<pack>_<Female|Male>/*.wav`; `Sound_Packs/Voice_files.xlsx` is a dev-only sheet excluded from builds.
- **Distribution**: must include `LICENSE.txt` with MIT attribution for the EliteVA plugin.

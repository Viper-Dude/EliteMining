# EliteMining — FAQ

## Installation

<details>
<summary><b>How do I install the app?</b></summary>

Run EliteMiningSetup.exe and follow the installer.
</details>

<details>
<summary><b>Can I use EliteMining without VoiceAttack?</b></summary>

Yes. All features work in standalone mode except automated mining sequence control.
</details>

<details>
<summary><b>How do I import the VoiceAttack profile?</b></summary>

Open VoiceAttack → Profile → Import Profile. Select EliteMining-Profile.vap from the install folder.

**Note:** Starting with v4.75, the profile is in XML format. You'll need to reconfigure your keybinds one time after importing.
</details>

<details>
<summary><b>How do I preserve my VoiceAttack keybinds during updates?</b></summary>

**Automatic Method (v4.76+):**
EliteMining will automatically detect when a new VoiceAttack profile is available and prompt you to preserve your keybinds. Simply follow the on-screen instructions:
1. Export your current profile as XML when prompted
2. Select the exported file
3. Your keybinds will be automatically merged into the new profile

**Manual Method:**
If you prefer to do it manually:
1. Open VoiceAttack
2. Right-click your EliteMining profile → Export Profile
3. Save as type: **"VoiceAttack Profile Expanded as XML (*.vap)"**
4. Save with a descriptive name (e.g., `EliteMining-Backup.vap`)
5. Install the update
6. Run EliteMining - it will detect the new profile and guide you through the merge process
</details>

<details>
<summary><b>Does EliteVA need any special setup?</b></summary>

Set Controls in Elite Dangerous to a saved Custom preset. This creates `Custom.binds` required by EliteVA.
</details>

## Features

<details>
<summary><b>How do I find mining hotspots?</b></summary>

Open the app → Hotspot Finder tab. Filter by minerals or ring type. Results show distance and overlap counts.
</details>

<details>
<summary><b>How do I create HTML reports?</b></summary>

Right-click any mining session in the Reports tab. Select Generate Detailed Report. Add screenshots if needed.
</details>

<details>
<summary><b>How do I use bookmarks?</b></summary>

Mining Session tab → Bookmarks. Save current location or search saved spots. Includes system and ring details.
</details>

<details>
<summary><b>What are ship presets?</b></summary>

Saved firegroup and timer configurations for different ships. Create and switch between setups quickly.
</details>

<details>
<summary><b>Where are reports stored?</b></summary>

Reports are saved to the `Reports/Mining Session/` folder inside the app installation folder.
</details>

<details>
<summary><b>How do I back up settings and reports?</b></summary>

Open the app → Backup & Restore. You can also copy the install folder to a safe location.
</details>

## Troubleshooting

<details>
<summary><b>The app will not start. What should I try?</b></summary>

Run the app as Administrator. Add an antivirus exclusion for the install folder. Reboot and try again.
</details>

<details>
<summary><b>Automatic firegroup switching does not work.</b></summary>

Make sure all firegroups A–H are populated in Elite Dangerous. Empty firegroups prevent automated switching even if you don't use them.
</details>

<details>
<summary><b>Hotspot finder shows no data.</b></summary>

Log out and back into Elite Dangerous once. Make sure the game journal files are accessible to the app.
</details>

<details>
<summary><b>Mining announcements not working?</b></summary>

Check Settings → Interface → Text-to-Speech. Test voice and volume. Enable announcement filters.
</details>

<details>
<summary><b>Session data missing after update?</b></summary>

Relog into Elite Dangerous once. The app refreshes location data on first login.
</details>

<details>
<summary><b>How do I change TTS voice or volume?</b></summary>

Open the app → Settings → Interface → Text-to-Speech. Choose a voice and set the volume.
</details>

## Support

<details>
<summary><b>How do I report bugs or get help?</b></summary>

Join the Discord server or open a GitHub issue. Include steps to reproduce and any relevant log files from the install folder.
</details>

<details>
<summary><b>Any other tips?</b></summary>

Keep the app updated. Create backups before major changes or updates.
</details>
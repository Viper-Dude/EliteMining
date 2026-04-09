### <img src="https://github.com/Viper-Dude/EliteMining/blob/main/app/Images/logo_multi.ico" width="32" height="32"> EliteMining
**Release Date:** 2026-04-09

## New Features & Improvements

### Settings/General Settings Tab

- Added option to update and preserve custom keybinds the VoiceAttack profile — available via Settings
- Added **Cargo Status text Overlay** — live cargo monitoring displayed on screen while mining
- Added **"Only when game is focused"** option — overlays automatically hide when you alt-tab out of Elite Dangerous and reappear when you return. Enabled by default.
- Overlays now follow the game window across monitors — works correctly on multi-monitor setups and DPI scaling up to 150%

### Voiceattack Profile - Updated to v5.0.0

### Important Notes 
- This update is adding new and edits of existing command, some keybind could be missed when updating, remember to always check all your key and joystick bindings after every profile update.

### New VoiceAttack Commands - Turns the text overlay on or off by voice or keybind/joystik

- **Enable/Disable Text Overlay** — Main switch for text overlay 
- **Enable/Disable Standard Text Overlay** — Standard text overlay mode
- **Enable/Disable Enhanced Text Overlay** — Enhanced prospector overlay mode
- **Enable/Disable Cargo Text Overlay** — Cargo status overlay 

### VoiceAttack Controls Tab

- Added **Thrust up duration** spinbox (0.5–3.0s, default 1.2s) — controls how long the upward thrust is applied during the prospector sequence. Value saved as part of the ship preset.

### Removed

- **EliteMining Plugin** has been removed — it is no longer needed. All VoiceAttack commands now use direct file communication instead.  
  If you have the plugin from a previous install, you can safely disable it in VoiceAttack → Options → Plugin Manager and delete `EliteMiningPlugin.dll` from your installation folder.

[![Discord](https://img.shields.io/badge/Discord%20Community-Join%20Server-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/5dsF3UshRR)
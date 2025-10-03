# Reminders for Next Version

## Installer Configuration Changes

### config.json Handling
**v4.1.4 (Previous):**
```ini
Source: "app\config.json"; DestDir: "{app}\Apps\EliteMining"
```
- No flags = overwrites only if installer file is newer (default Inno Setup behavior)
- This was used to ensure Tritium material update reached users

**✅ v4.1.5 (Current):**
```ini
Source: "app\config.json"; DestDir: "{app}\Apps\EliteMining"; Flags: onlyifdoesntexist
```
- **PRESERVES USER SETTINGS** - Never overwrites on upgrades
- Only installs on fresh installations
- ⚠️ **IMPORTANT:** Remove `onlyifdoesntexist` flag if critical config updates are needed in future versions

### VoiceAttack Profile Handling (EliteMining-Profile.vap)
**v4.1.4 (Previous):**
```ini
Source: "EliteMining-Profile.vap"; DestDir: "{app}\Apps\EliteMining"; Flags: uninsneveruninstall skipifsourcedoesntexist
```
- Overwrites only if installer file is newer (default Inno Setup behavior)
- Never deleted on uninstall (`uninsneveruninstall`)

**✅ v4.1.5 (Current):**
```ini
Source: "EliteMining-Profile.vap"; DestDir: "{app}\Apps\EliteMining"; Flags: uninsneveruninstall skipifsourcedoesntexist onlyifdoesntexist
```
- **PRESERVES USER MODIFICATIONS** - Never overwrites on upgrades
- Only installs on fresh installations
- Never deleted on uninstall
- ⚠️ **IMPORTANT:** Remove `onlyifdoesntexist` flag if critical profile updates are needed in future versions

---

## Other Reminders
- Add new reminders here as needed for the next release
- 

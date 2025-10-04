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

### User Database Handling (user_data.db)
**✅ v4.1.6 (Current):**
```ini
Source: "app\data\UserDb for install\user_data.db"; DestDir: "{app}\Apps\EliteMining\app\data"; Flags: onlyifdoesntexist
```
- **PRESERVES USER DATA** - Never overwrites on upgrades
- Only installs on fresh installations
- Contains cleaned default database (phantom rings removed)
- ⚠️ **IMPORTANT:** Remove `onlyifdoesntexist` flag ONLY if critical database schema changes require forced update
- ⚠️ **WARNING:** Forcing database overwrite will DELETE ALL USER MINING DATA! Only do this as last resort with clear user warning.

**Database Changes in v4.1.6:**
- Removed phantom Paesia 2 C Ring (Alexandrite, Icy) - ring was removed by Frontier
- Implemented smart update logic to prevent incomplete journal data from overwriting complete data
- Fixed issue where newer scans with missing data would overwrite older complete data

---

## Other Reminders
- Add new reminders here as needed for the next release
- 

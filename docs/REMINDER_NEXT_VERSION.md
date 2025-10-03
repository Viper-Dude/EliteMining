# Reminders for Next Version

## Installer Configuration Changes

### config.json Handling
**Current (v4.1.4):**
```ini
Source: "app\config.json"; DestDir: "{app}\Apps\EliteMining"
```
- No flags = overwrites only if installer file is newer (default Inno Setup behavior)
- This ensures Tritium material update reaches users while respecting file timestamps

**For next version:** If you want to fully preserve user configs regardless of file age:
```ini
Source: "app\config.json"; DestDir: "{app}\Apps\EliteMining"; Flags: onlyifdoesntexist
```

### VoiceAttack Profile Handling (EliteMining-Profile.vap)
**Current (v4.1.4):**
```ini
Source: "EliteMining-Profile.vap"; DestDir: "{app}\Apps\EliteMining"; Flags: uninsneveruninstall skipifsourcedoesntexist
```
- Overwrites only if installer file is newer (default Inno Setup behavior)
- Never deleted on uninstall (`uninsneveruninstall`)

**For next version:** If you want to fully preserve user profile modifications on upgrades:
```ini
Source: "EliteMining-Profile.vap"; DestDir: "{app}\Apps\EliteMining"; Flags: uninsneveruninstall skipifsourcedoesntexist onlyifdoesntexist
```
This will install the profile only on fresh installations and never overwrite it on upgrades.

---

## Other Reminders
- Add new reminders here as needed for the next release
- 

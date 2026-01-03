# VoiceAttack Profile Auto-Updater Design

## Overview
Automatic VoiceAttack profile updater that preserves user keybinds during updates. Integrated into the EliteMining application for seamless one-click profile updates.

---

## User Experience

### Scenario: Update Available

**1. App detects new profile version**
```
[EliteMining Notification]
┌─────────────────────────────────────────┐
│  🎮 VoiceAttack Profile Update          │
│                                         │
│  New version available: 4.8.0           │
│  Current version: 4.7.5                 │
│                                         │
│  Your keybinds will be preserved!       │
│                                         │
│  [Update Now]  [Later]  [Release Notes] │
└─────────────────────────────────────────┘
```

**2. User clicks "Update Now"**
```
[Progress Dialog]
┌─────────────────────────────────────────┐
│  Updating VoiceAttack Profile...        │
│                                         │
│  ✓ Backing up current profile          │
│  ✓ Extracting keybinds (247 found)     │
│  ✓ Closing VoiceAttack                 │
│  → Installing new profile...           │
│    Restoring keybinds...               │
│    Restarting VoiceAttack...           │
│                                         │
│  [Cancel]                               │
└─────────────────────────────────────────┘
```

**3. Update completes**
```
[Success Dialog]
┌─────────────────────────────────────────┐
│  ✓ Profile Updated Successfully!        │
│                                         │
│  VoiceAttack profile: 4.8.0             │
│  Keybinds preserved: 247                │
│  Backup saved to:                       │
│  C:\Users\...\EliteMining-4.7.5.vap    │
│                                         │
│  [OK]                                   │
└─────────────────────────────────────────┘
```

---

## Architecture

### Components

```
EliteMining App (Python)
├── va_profile_updater.py       # Main updater module
├── va_profile_parser.py        # .VAP XML parser
├── va_keybind_extractor.py     # Extracts keybinds from profile
├── va_keybind_applier.py       # Applies keybinds to new profile
└── va_process_manager.py       # Start/stop VoiceAttack

VoiceAttack
├── VoiceAttack.dat             # Database file
├── Profiles/
│   └── EliteMining.vap         # User's profile (not used directly)
└── VoiceAttack.exe
```

### Data Flow

```
1. Check for Updates
   ├─> Compare local version vs server version
   └─> Download new .VAP if available

2. User Confirms Update
   ├─> Show progress dialog
   └─> Start update process

3. Backup Current Profile
   ├─> Export current profile from VA database
   └─> Save to: AppData\EliteMining\Backups\EliteMining-{version}-{timestamp}.vap

4. Extract Keybinds
   ├─> Parse current profile XML
   ├─> Extract for each command:
   │   ├─> Keyboard shortcuts
   │   ├─> Joystick button bindings
   │   ├─> Mouse button bindings
   │   └─> Command enabled state
   └─> Save to keybinds.json

5. Close VoiceAttack
   ├─> Check if VA is running
   ├─> Close gracefully (save state)
   └─> Wait for process to exit

6. Import New Profile
   ├─> Read new .VAP file
   ├─> Parse XML
   └─> Write to VoiceAttack.dat database

7. Restore Keybinds
   ├─> Match commands by name
   ├─> Apply saved keybinds to new profile
   └─> Save modified profile to database

8. Restart VoiceAttack
   ├─> Launch VoiceAttack.exe
   └─> Verify profile loaded correctly

9. Show Success/Failure
   └─> Close progress dialog
```

---

## Implementation

### Module 1: va_profile_updater.py

**Main orchestrator**

```python
class VAProfileUpdater:
    """Manages VoiceAttack profile updates with keybind preservation"""
    
    def __init__(self, app_data_path: str):
        self.app_data_path = app_data_path
        self.backup_dir = Path(app_data_path) / "Backups"
        self.parser = VAProfileParser()
        self.keybind_extractor = VAKeybindExtractor()
        self.keybind_applier = VAKeybindApplier()
        self.process_manager = VAProcessManager()
        
    def check_for_update(self) -> Optional[UpdateInfo]:
        """Check if new profile version available"""
        current_version = self.get_current_profile_version()
        latest_version = self.get_latest_profile_version()
        
        if latest_version > current_version:
            return UpdateInfo(
                current=current_version,
                latest=latest_version,
                download_url=self.get_download_url(latest_version),
                release_notes=self.get_release_notes(latest_version)
            )
        return None
    
    def update_profile(self, new_vap_path: str, progress_callback=None) -> UpdateResult:
        """
        Update VoiceAttack profile while preserving keybinds
        
        Args:
            new_vap_path: Path to new .VAP file
            progress_callback: Function(step: str, progress: int)
        
        Returns:
            UpdateResult with success status and details
        """
        try:
            # Step 1: Backup
            progress_callback("Backing up current profile...", 10)
            backup_path = self.backup_current_profile()
            
            # Step 2: Extract keybinds
            progress_callback("Extracting keybinds...", 20)
            keybinds = self.extract_keybinds()
            
            # Step 3: Close VoiceAttack
            progress_callback("Closing VoiceAttack...", 30)
            if not self.process_manager.close_voiceattack():
                raise UpdateError("Failed to close VoiceAttack")
            
            # Step 4: Import new profile
            progress_callback("Installing new profile...", 50)
            self.import_profile(new_vap_path)
            
            # Step 5: Restore keybinds
            progress_callback("Restoring keybinds...", 70)
            restored_count = self.restore_keybinds(keybinds)
            
            # Step 6: Restart VoiceAttack
            progress_callback("Restarting VoiceAttack...", 90)
            if not self.process_manager.start_voiceattack():
                raise UpdateError("Failed to restart VoiceAttack")
            
            progress_callback("Complete!", 100)
            
            return UpdateResult(
                success=True,
                backup_path=backup_path,
                keybinds_restored=restored_count,
                message="Profile updated successfully!"
            )
            
        except Exception as e:
            # Rollback: restore backup
            self.rollback(backup_path)
            return UpdateResult(
                success=False,
                error=str(e),
                message=f"Update failed: {e}"
            )
    
    def backup_current_profile(self) -> str:
        """Export current profile as backup"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        version = self.get_current_profile_version()
        backup_path = self.backup_dir / f"EliteMining-{version}-{timestamp}.vap"
        
        # Export from VoiceAttack database
        self.export_profile_from_database("EliteMining", backup_path)
        
        return str(backup_path)
    
    def extract_keybinds(self) -> Dict[str, CommandKeybinds]:
        """Extract all keybinds from current profile"""
        current_profile = self.get_current_profile_xml()
        return self.keybind_extractor.extract(current_profile)
    
    def restore_keybinds(self, keybinds: Dict[str, CommandKeybinds]) -> int:
        """Apply keybinds to new profile"""
        new_profile = self.get_current_profile_xml()
        modified_profile = self.keybind_applier.apply(new_profile, keybinds)
        self.save_profile_to_database(modified_profile)
        return len(keybinds)
```

### Module 2: va_profile_parser.py

**XML parsing for .VAP files**

```python
class VAProfileParser:
    """Parse VoiceAttack .VAP profile files"""
    
    def parse(self, vap_path: str) -> ET.ElementTree:
        """Parse .VAP file XML"""
        tree = ET.parse(vap_path)
        return tree
    
    def get_profile_version(self, tree: ET.ElementTree) -> str:
        """Extract profile version from XML"""
        profile = tree.getroot()
        # Look for custom version element or parse from name
        version_elem = profile.find(".//Version")
        if version_elem is not None:
            return version_elem.text
        
        # Parse from profile name: "EliteMining Dev 4.7.5-Profile"
        name = profile.find("Name").text
        match = re.search(r'(\d+\.\d+\.\d+)', name)
        if match:
            return match.group(1)
        
        return "unknown"
    
    def get_all_commands(self, tree: ET.ElementTree) -> List[ET.Element]:
        """Get all Command elements"""
        return tree.findall(".//Command")
```

### Module 3: va_keybind_extractor.py

**Extract keybinds from profile**

```python
@dataclass
class CommandKeybinds:
    """Keybinds for a single command"""
    command_name: str
    keyboard_shortcut: Optional[str] = None
    joystick_shortcut: Optional[str] = None
    mouse_shortcut: Optional[str] = None
    enabled: bool = True
    
class VAKeybindExtractor:
    """Extract keybinds from VoiceAttack profile XML"""
    
    def extract(self, profile_xml: ET.ElementTree) -> Dict[str, CommandKeybinds]:
        """
        Extract all keybinds from profile
        
        Returns:
            Dict mapping command name to keybinds
        """
        keybinds = {}
        
        for command in profile_xml.findall(".//Command"):
            cmd_name = self.get_command_name(command)
            
            keybinds[cmd_name] = CommandKeybinds(
                command_name=cmd_name,
                keyboard_shortcut=self.extract_keyboard_shortcut(command),
                joystick_shortcut=self.extract_joystick_shortcut(command),
                mouse_shortcut=self.extract_mouse_shortcut(command),
                enabled=self.is_command_enabled(command)
            )
        
        return keybinds
    
    def get_command_name(self, command: ET.Element) -> str:
        """Get command's full name"""
        name_elem = command.find("CommandString")
        if name_elem is not None:
            return name_elem.text
        return ""
    
    def extract_keyboard_shortcut(self, command: ET.Element) -> Optional[str]:
        """Extract keyboard shortcut if present"""
        # Check if keyboard shortcut is enabled
        enabled = command.find("UseShortcut")
        if enabled is None or enabled.text != "True":
            return None
        
        # Get the shortcut string
        shortcut = command.find("CommandKeyValue")
        if shortcut is not None:
            return shortcut.text
        
        return None
    
    def extract_joystick_shortcut(self, command: ET.Element) -> Optional[str]:
        """Extract joystick button shortcut if present"""
        enabled = command.find("UseJoystick")
        if enabled is None or enabled.text != "True":
            return None
        
        shortcut = command.find("JoystickValue")
        if shortcut is not None:
            return shortcut.text
        
        return None
    
    def extract_mouse_shortcut(self, command: ET.Element) -> Optional[str]:
        """Extract mouse button shortcut if present"""
        enabled = command.find("UseMouse")
        if enabled is None or enabled.text != "True":
            return None
        
        shortcut = command.find("MouseValue")
        if shortcut is not None:
            return shortcut.text
        
        return None
    
    def is_command_enabled(self, command: ET.Element) -> bool:
        """Check if command is enabled"""
        enabled = command.find("Enabled")
        if enabled is not None:
            return enabled.text == "True"
        return True  # Default to enabled
```

### Module 4: va_keybind_applier.py

**Apply keybinds to new profile**

```python
class VAKeybindApplier:
    """Apply keybinds to VoiceAttack profile XML"""
    
    def apply(self, profile_xml: ET.ElementTree, 
              keybinds: Dict[str, CommandKeybinds]) -> ET.ElementTree:
        """
        Apply keybinds to profile
        
        Args:
            profile_xml: New profile XML tree
            keybinds: Keybinds to apply
        
        Returns:
            Modified profile XML tree
        """
        matched = 0
        unmatched = []
        
        for command in profile_xml.findall(".//Command"):
            cmd_name = self.get_command_name(command)
            
            if cmd_name in keybinds:
                self.apply_keybinds_to_command(command, keybinds[cmd_name])
                matched += 1
            else:
                unmatched.append(cmd_name)
        
        logging.info(f"Applied keybinds: {matched} matched, {len(unmatched)} unmatched")
        if unmatched:
            logging.warning(f"Unmatched commands: {unmatched}")
        
        return profile_xml
    
    def apply_keybinds_to_command(self, command: ET.Element, 
                                   keybinds: CommandKeybinds):
        """Apply keybinds to a single command"""
        
        # Apply keyboard shortcut
        if keybinds.keyboard_shortcut:
            self.set_keyboard_shortcut(command, keybinds.keyboard_shortcut)
        
        # Apply joystick shortcut
        if keybinds.joystick_shortcut:
            self.set_joystick_shortcut(command, keybinds.joystick_shortcut)
        
        # Apply mouse shortcut
        if keybinds.mouse_shortcut:
            self.set_mouse_shortcut(command, keybinds.mouse_shortcut)
        
        # Apply enabled state
        self.set_enabled(command, keybinds.enabled)
    
    def set_keyboard_shortcut(self, command: ET.Element, shortcut: str):
        """Set keyboard shortcut on command"""
        # Enable keyboard shortcut
        use_shortcut = command.find("UseShortcut")
        if use_shortcut is None:
            use_shortcut = ET.SubElement(command, "UseShortcut")
        use_shortcut.text = "True"
        
        # Set shortcut value
        shortcut_elem = command.find("CommandKeyValue")
        if shortcut_elem is None:
            shortcut_elem = ET.SubElement(command, "CommandKeyValue")
        shortcut_elem.text = shortcut
    
    def set_joystick_shortcut(self, command: ET.Element, shortcut: str):
        """Set joystick shortcut on command"""
        use_joystick = command.find("UseJoystick")
        if use_joystick is None:
            use_joystick = ET.SubElement(command, "UseJoystick")
        use_joystick.text = "True"
        
        shortcut_elem = command.find("JoystickValue")
        if shortcut_elem is None:
            shortcut_elem = ET.SubElement(command, "JoystickValue")
        shortcut_elem.text = shortcut
    
    def set_mouse_shortcut(self, command: ET.Element, shortcut: str):
        """Set mouse shortcut on command"""
        use_mouse = command.find("UseMouse")
        if use_mouse is None:
            use_mouse = ET.SubElement(command, "UseMouse")
        use_mouse.text = "True"
        
        shortcut_elem = command.find("MouseValue")
        if shortcut_elem is None:
            shortcut_elem = ET.SubElement(command, "MouseValue")
        shortcut_elem.text = shortcut
    
    def set_enabled(self, command: ET.Element, enabled: bool):
        """Set command enabled state"""
        enabled_elem = command.find("Enabled")
        if enabled_elem is None:
            enabled_elem = ET.SubElement(command, "Enabled")
        enabled_elem.text = "True" if enabled else "False"
    
    def get_command_name(self, command: ET.Element) -> str:
        """Get command name"""
        name_elem = command.find("CommandString")
        if name_elem is not None:
            return name_elem.text
        return ""
```

### Module 5: va_process_manager.py

**Manage VoiceAttack process**

```python
class VAProcessManager:
    """Manage VoiceAttack process (start/stop)"""
    
    def __init__(self):
        self.va_exe = self.find_voiceattack_exe()
    
    def find_voiceattack_exe(self) -> Optional[Path]:
        """Find VoiceAttack installation"""
        # Check common locations
        common_paths = [
            Path(r"C:\Program Files\VoiceAttack\VoiceAttack.exe"),
            Path(r"C:\Program Files (x86)\VoiceAttack\VoiceAttack.exe"),
            Path(r"D:\SteamLibrary\steamapps\common\VoiceAttack 2\VoiceAttack.exe"),
        ]
        
        for path in common_paths:
            if path.exists():
                return path
        
        # Check registry
        va_path = self.get_va_path_from_registry()
        if va_path and va_path.exists():
            return va_path
        
        return None
    
    def is_running(self) -> bool:
        """Check if VoiceAttack is running"""
        for proc in psutil.process_iter(['name']):
            if proc.info['name'].lower() == 'voiceattack.exe':
                return True
        return False
    
    def close_voiceattack(self, timeout: int = 10) -> bool:
        """
        Gracefully close VoiceAttack
        
        Args:
            timeout: Seconds to wait for close
        
        Returns:
            True if closed successfully
        """
        if not self.is_running():
            return True
        
        # Find process
        for proc in psutil.process_iter(['name', 'pid']):
            if proc.info['name'].lower() == 'voiceattack.exe':
                logging.info(f"Closing VoiceAttack (PID: {proc.info['pid']})")
                
                try:
                    # Try graceful close first (sends WM_CLOSE)
                    proc.terminate()
                    proc.wait(timeout=timeout)
                    return True
                    
                except psutil.TimeoutExpired:
                    logging.warning("Graceful close timed out, forcing...")
                    proc.kill()
                    proc.wait(timeout=5)
                    return True
                    
                except Exception as e:
                    logging.error(f"Failed to close VoiceAttack: {e}")
                    return False
        
        return False
    
    def start_voiceattack(self) -> bool:
        """
        Start VoiceAttack
        
        Returns:
            True if started successfully
        """
        if self.is_running():
            logging.warning("VoiceAttack already running")
            return True
        
        if not self.va_exe:
            logging.error("VoiceAttack executable not found")
            return False
        
        try:
            # Start VoiceAttack
            subprocess.Popen([str(self.va_exe)])
            
            # Wait for it to start
            for _ in range(10):  # 10 second timeout
                time.sleep(1)
                if self.is_running():
                    logging.info("VoiceAttack started successfully")
                    return True
            
            logging.error("VoiceAttack failed to start")
            return False
            
        except Exception as e:
            logging.error(f"Failed to start VoiceAttack: {e}")
            return False
```

---

## Integration with EliteMining App

### In main.py

```python
from app.va_profile_updater import VAProfileUpdater, UpdateInfo

class EliteMiningApp:
    def __init__(self):
        # ... existing init ...
        self.va_updater = VAProfileUpdater(self.app_data_path)
        
    def check_for_updates(self):
        """Check for app and profile updates"""
        # Check VA profile update
        profile_update = self.va_updater.check_for_update()
        if profile_update:
            self.show_profile_update_dialog(profile_update)
    
    def show_profile_update_dialog(self, update_info: UpdateInfo):
        """Show update available dialog"""
        from tkinter import messagebox
        
        message = f"""New VoiceAttack Profile Available!

Current Version: {update_info.current}
New Version: {update_info.latest}

Your keybinds will be automatically preserved.

Update now?"""
        
        result = messagebox.askyesno(
            "Profile Update Available",
            message,
            icon='info'
        )
        
        if result:
            self.update_va_profile(update_info)
    
    def update_va_profile(self, update_info: UpdateInfo):
        """Execute profile update with progress"""
        # Download new profile
        new_vap_path = self.download_profile(update_info.download_url)
        
        # Show progress dialog
        progress_dialog = self.show_progress_dialog("Updating VoiceAttack Profile...")
        
        def progress_callback(step: str, progress: int):
            progress_dialog.update(step, progress)
        
        # Execute update
        result = self.va_updater.update_profile(new_vap_path, progress_callback)
        
        progress_dialog.close()
        
        # Show result
        if result.success:
            messagebox.showinfo(
                "Update Successful",
                f"Profile updated successfully!\n\n"
                f"Keybinds preserved: {result.keybinds_restored}\n"
                f"Backup saved to:\n{result.backup_path}"
            )
        else:
            messagebox.showerror(
                "Update Failed",
                f"Failed to update profile:\n{result.message}\n\n"
                f"Your original profile has been restored."
            )
```

---

## Database Access

VoiceAttack stores profiles in `VoiceAttack.dat` (binary format). Two approaches:

### Approach 1: Export/Import via VoiceAttack (Recommended)

Use VoiceAttack's command-line interface:

```python
def export_profile_from_database(self, profile_name: str, output_path: str):
    """Export profile using VA command line"""
    subprocess.run([
        str(self.va_exe),
        "-export",
        profile_name,
        "-exportfile",
        output_path
    ])

def import_profile_to_database(self, vap_path: str):
    """Import profile using VA command line"""
    subprocess.run([
        str(self.va_exe),
        "-import",
        vap_path
    ])
```

### Approach 2: Direct Database Manipulation

If VA doesn't support command-line export/import, manipulate database directly:

```python
import sqlite3  # If VoiceAttack.dat is SQLite

def get_current_profile_xml(self) -> ET.ElementTree:
    """Read profile XML from VoiceAttack database"""
    db_path = self.get_va_database_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT ProfileXML FROM Profiles WHERE Name = ?",
        ("EliteMining",)
    )
    
    xml_data = cursor.fetchone()[0]
    conn.close()
    
    return ET.fromstring(xml_data)
```

**Note:** Need to reverse-engineer VoiceAttack.dat format first.

---

## Testing Plan

### Unit Tests

```python
# test_va_keybind_extractor.py
def test_extract_keyboard_shortcut():
    """Test keyboard shortcut extraction"""
    xml = """
    <Command>
        <CommandString>Test Command</CommandString>
        <UseShortcut>True</UseShortcut>
        <CommandKeyValue>[CTRL][SHIFT]T</CommandKeyValue>
    </Command>
    """
    command = ET.fromstring(xml)
    extractor = VAKeybindExtractor()
    
    shortcut = extractor.extract_keyboard_shortcut(command)
    assert shortcut == "[CTRL][SHIFT]T"

# test_va_keybind_applier.py
def test_apply_keyboard_shortcut():
    """Test applying keyboard shortcut"""
    xml = "<Command><CommandString>Test</CommandString></Command>"
    command = ET.fromstring(xml)
    applier = VAKeybindApplier()
    
    applier.set_keyboard_shortcut(command, "[CTRL]T")
    
    assert command.find("UseShortcut").text == "True"
    assert command.find("CommandKeyValue").text == "[CTRL]T"
```

### Integration Tests

```python
def test_full_update_cycle():
    """Test complete update process"""
    updater = VAProfileUpdater(test_app_data)
    
    # Create test profile with keybinds
    old_profile = create_test_profile_v1()
    
    # Perform update
    result = updater.update_profile(new_profile_path)
    
    assert result.success
    assert result.keybinds_restored > 0
    
    # Verify keybinds preserved
    new_profile = updater.get_current_profile_xml()
    verify_keybinds_match(old_profile, new_profile)
```

### Manual Testing

1. **Basic Update**
   - Set some keybinds on commands
   - Run updater
   - Verify keybinds preserved

2. **New Commands**
   - New profile has commands old doesn't
   - Verify they import without keybinds

3. **Removed Commands**
   - Old profile has commands new doesn't
   - Verify they don't cause errors

4. **VoiceAttack Running**
   - Start with VA running
   - Verify updater closes it gracefully
   - Verify it restarts after update

5. **Update Failure**
   - Simulate failure (corrupt VAP file)
   - Verify rollback restores original

---

## Rollout Plan

### Phase 1: Development (Week 1-2)
- Implement core modules
- Unit tests
- Integration tests

### Phase 2: Alpha Testing (Week 3)
- Test with 2-3 volunteers
- Fix critical bugs
- Refine UX

### Phase 3: Beta Release (Week 4)
- Release to subset of users
- Gather feedback
- Monitor for issues

### Phase 4: General Release (Week 5+)
- Roll out to all users
- Monitor update success rate
- Provide support

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| VoiceAttack not found | Install path not detected | Prompt user to locate VA |
| Failed to close VA | Process stuck | Force kill with user confirmation |
| Backup failed | Disk full / permissions | Check space, request admin |
| Import failed | Corrupt .VAP file | Restore backup, retry download |
| Keybind mismatch | Command renamed | Log warning, skip that command |

### Rollback Strategy

If update fails at any point:
1. Stop update process
2. Restore backup profile
3. Restart VoiceAttack
4. Show error to user with details
5. Log full error for debugging

---

## Benefits

✅ **Zero manual work** - One click updates
✅ **Keybinds preserved** - Never lose custom bindings
✅ **Automatic backup** - Safety net for failures
✅ **Graceful handling** - Closes/restarts VA properly
✅ **Error recovery** - Automatic rollback on failure
✅ **User-friendly** - Clear progress and status
✅ **Future-proof** - Easy to add new features

---

## Future Enhancements

1. **Diff View**
   - Show what changed between versions
   - Let users review changes before updating

2. **Selective Update**
   - Choose which commands to update
   - Keep some old commands if preferred

3. **Cloud Sync**
   - Backup keybinds to cloud
   - Sync across multiple PCs

4. **Update Schedule**
   - Auto-update on app start
   - Or schedule for specific times

5. **Version History**
   - Keep multiple profile versions
   - Rollback to previous version

---

This is your complete auto-updater solution! No more manual profile imports, no more lost keybinds. 🎉

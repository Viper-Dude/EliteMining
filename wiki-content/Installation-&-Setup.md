# ⚙️ Installation & Setup

Complete installation guide for EliteMining with both standalone and VoiceAttack integration options.

## System Requirements

### Essential Requirements
- Windows 10 or later (64-bit)
- Elite Dangerous PC version
- 2GB available disk space
- Internet connection for hotspot database updates

### VoiceAttack Integration Requirements
- VoiceAttack (paid version required)
- Microphone for voice commands
- Custom keybind preset in Elite Dangerous

## Installation Methods

### Method 1: Installer (Recommended)

**Download:**
- Get `EliteMiningSetup.exe` from GitHub Releases
- Verify file integrity if provided

**Installation:**
- Run installer as Administrator
- Select installation directory
- Choose VoiceAttack integration option
- Complete installation and launch

**Included Components:**
- EliteMining Configurator
- EliteVA plugin for VoiceAttack integration
- VoiceAttack profile (EliteMining-Profile.vap)
- Documentation and examples

### Method 2: Portable Installation

**Download:**
- Download latest `.zip` release package
- Extract to preferred directory location
- No installation required

**Setup:**
- Run `Configurator.exe` directly
- Configure paths and settings manually
- Import VoiceAttack profile if needed

## First-Time Configuration

### Automatic Detection
EliteMining automatically detects:
- Elite Dangerous journal folder location
- VoiceAttack installation directory
- Existing mining data for import

### Manual Configuration
If auto-detection fails:

**Journal Folder Setup:**
- Navigate to Settings tab
- Click "Change" next to Journal Directory
- Browse to: `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`
- Verify folder contains Journal.*.log files

**VoiceAttack Integration:**
- Locate VoiceAttack installation folder
- Import EliteMining-Profile.vap
- Configure microphone and speech recognition
- Test basic commands

## Elite Dangerous Configuration

### Required Keybind Setup

**Enable Custom Keybinds:**
- Open Elite Dangerous Options
- Navigate to Controls section
- Set Controls preset to "Custom"
- Save configuration to create Custom.binds file

**Essential Keybinds:**
EliteVA requires specific keybinds for automation:
- Mining lasers fire group
- Collector limpet controller
- Prospector limpet controller
- Cargo scoop toggle
- Ship lights control

### Firegroup Configuration
Configure ship firegroups using EliteMining interface:
- Assign mining lasers to primary firegroup
- Set prospector limpets to secondary
- Configure collector limpets appropriately
- Test each firegroup assignment

## VoiceAttack Profile Setup

### Profile Import
- Open VoiceAttack application
- Select "Import Profile" from Profile menu
- Choose EliteMining-Profile.vap file
- Set as active profile for Elite Dangerous

### Speech Recognition Training
- Complete Windows Speech Recognition setup
- Train voice recognition in quiet environment
- Test basic commands before gaming session
- Backup speech profile after training

### Command Testing
Verify these essential commands work:
- "Start mining sequence"
- "Deploy prospector limpets"
- "Stop mining sequence"
- "Open configurator"

## Initial Data Import

### Journal History Import
Import existing mining data:
- Open Mining Session tab
- Click "Import Journal" button
- Select date range for import
- Monitor import progress

**Import Options:**
- Full history scan (comprehensive but slow)
- Recent sessions only (faster startup)
- Specific date range (targeted import)

### Hotspot Database Update
- Database updates automatically on startup
- Manual refresh available in Hotspot Finder
- Verify 32,000+ hotspots loaded correctly

## Configuration Verification

### Test Core Functions

**Announcement System:**
- Start Elite Dangerous
- Begin mining operation
- Verify material announcements appear
- Adjust thresholds if needed

**Hotspot Finder:**
- Enter current system name
- Execute search with default parameters
- Verify results appear with distance data
- Test material filtering options

**Report Generation:**
- Complete short mining session
- Generate HTML report
- Verify charts and statistics display
- Check screenshot integration

### VoiceAttack Validation
- Launch Elite Dangerous with VoiceAttack active
- Test basic navigation commands
- Verify mining sequence automation
- Check prospector deployment timing

## Backup Configuration

### Create Initial Backup
After successful setup:
- Use Backup & Restore feature
- Create timestamped backup
- Store backup file safely
- Document configuration notes

### Backup Contents
Full backup includes:
- All configuration settings
- Custom firegroup assignments
- Mining bookmarks and annotations
- Report templates and preferences

## Optimization Settings

### Performance Tuning
For optimal performance:
- Adjust announcement frequency
- Limit journal scan depth
- Configure memory usage limits
- Set appropriate update intervals

### UI Customization
- Configure text overlay position and style
- Set announcement volume levels
- Customize color schemes and themes
- Arrange interface layout preferences

## Post-Installation Tasks

### Documentation Review
- Read Quick Start Guide for basic usage
- Review Hotspot Finder documentation
- Study VoiceAttack command reference
- Bookmark troubleshooting resources

### Community Integration
- Join GitHub Discussions for community support
- Follow development updates and releases
- Contribute feedback and feature requests
- Share mining discoveries with community

### Regular Maintenance
- Check for software updates monthly
- Update hotspot database regularly
- Clean old reports and logs periodically
- Verify backup integrity

## Uninstallation

### Complete Removal
If uninstalling EliteMining:
- Export any important data or bookmarks
- Run included uninstaller if available
- Remove VoiceAttack profile manually
- Clean up remaining configuration files

### Preserving Data
To reinstall while keeping data:
- Create full backup before uninstalling
- Note custom configuration changes
- Export bookmark collections
- Save custom report templates
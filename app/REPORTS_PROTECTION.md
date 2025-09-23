# EliteMining Reports Protection Guide

## Overview

The EliteMining application includes automatic protection for your valuable mining session data during installation and updates. Your Reports folder contains irreplaceable mining history, session statistics, and analytics that you've collected over months of gameplay.

## Protection Features

### Automatic Protection Scripts
- **Python Script**: `reports_protector.py` - Advanced protection with JSON metadata
- **Batch Script**: `protect_reports.bat` - Windows command-line protection
- **PowerShell Script**: `protect_reports.ps1` - Modern Windows PowerShell protection

### Protection Actions
1. **Backup**: Creates a timestamped backup of your Reports folder
2. **Restore**: Restores Reports folder from backup after installation
3. **Merge**: Intelligently merges old and new Reports data

## How It Works

### During Installation
1. **Pre-Installation**: Scripts automatically backup your existing Reports folder
2. **Installation**: New application files are installed
3. **Post-Installation**: Your Reports data is restored/merged back

### Backup Locations
- **Default**: `%TEMP%\EliteMining_Reports_Backup_YYYYMMDD_HHMMSS\`
- **Custom**: You can specify your own backup location
- **Metadata**: Backup information is saved for automatic restoration

## Manual Usage

### Using PowerShell (Recommended)
```powershell
# Create backup
.\protect_reports.ps1 -Action backup

# Restore from automatic backup
.\protect_reports.ps1 -Action restore

# Restore from specific location
.\protect_reports.ps1 -Action restore -BackupLocation "C:\MyBackup"

# Merge old and new data
.\protect_reports.ps1 -Action merge
```

### Using Command Line
```batch
# Create backup
protect_reports.bat "C:\EliteMining" backup

# Restore from backup
protect_reports.bat "C:\EliteMining" restore

# Merge data
protect_reports.bat "C:\EliteMining" merge
```

### Using Python
```bash
# Create backup
python reports_protector.py backup

# Restore from backup
python reports_protector.py restore

# Merge data
python reports_protector.py merge "C:\MyBackup"
```

## Data Protection Strategies

### 1. Full Restore (Default)
- Completely replaces new Reports folder with your backup
- Use when you want to keep only your existing data
- Best for preserving session continuity

### 2. Intelligent Merge
- Combines old and new Reports data
- Keeps newer files based on modification time
- Best for preserving both old sessions and new defaults

### 3. Manual Backup
- Create additional backups before major updates
- Store backups in multiple locations
- Export important session data to external storage

## Backup Contents

### What's Protected
- **Mining Session Reports**: All your session history files
- **Session Data**: Analytics and statistics databases
- **Custom Configurations**: Any personalized report settings
- **Historical Data**: Months of accumulated mining data

### Backup Structure
```
Backup_Location/
├── Reports/
│   ├── Mining Session/
│   │   ├── Session_2025-08-23_08-29-16_*.txt
│   │   ├── Session_2025-08-31_13-48-22_*.txt
│   │   └── ...
│   └── Session Data/
│       ├── analytics.db
│       ├── session_index.csv
│       └── ...
└── backup_metadata.json
```

## Troubleshooting

### Common Issues

#### "No backup location found"
**Solution**: 
- Check if `reports_backup_info.json` exists in installation directory
- Manually specify backup location with `-BackupLocation` parameter

#### "Backup not found"
**Solution**:
- Verify backup directory path is correct
- Check if backup was moved or deleted
- Look in `%TEMP%` folder for automatic backups

#### "Permission denied"
**Solution**:
- Run scripts as Administrator
- Check if Reports folder is being used by another application
- Ensure sufficient disk space for backup

### Recovery Options

#### If Automatic Restore Fails
1. **Manual Copy**:
   ```
   xcopy "BackupLocation\Reports" "EliteMining\app\Reports" /E /I /H /Y
   ```

2. **Selective Restore**:
   - Copy only specific session files you need
   - Preserve new default configurations

3. **Emergency Recovery**:
   - Check Windows System Restore points
   - Look for backup files in `%TEMP%` folder
   - Contact support with backup metadata file

## Best Practices

### Before Updates
1. **Create Manual Backup**: Always create an additional backup before major updates
2. **Verify Backup**: Check that backup contains all your session files
3. **Note Backup Location**: Record backup path for manual recovery if needed

### Regular Maintenance
1. **Weekly Backups**: Create regular backups of Reports folder
2. **External Storage**: Copy important sessions to external drives
3. **Cloud Backup**: Upload critical session data to cloud storage

### After Installation
1. **Verify Data**: Check that all your session files are present
2. **Test Functionality**: Ensure Reports tab loads correctly
3. **Backup New State**: Create fresh backup after successful installation

## Integration with Installer

### Automatic Protection
The installer automatically:
1. Detects existing Reports folder
2. Creates timestamped backup
3. Proceeds with installation
4. Restores/merges data post-installation

### Manual Override
Users can:
- Skip automatic protection (not recommended)
- Specify custom backup locations
- Choose restore vs merge strategy

## Support

### If You Need Help
1. **Check Logs**: Look for error messages in terminal/command prompt
2. **Verify Paths**: Ensure installation directory is correct
3. **Check Permissions**: Run as Administrator if needed
4. **Contact Support**: Include backup metadata file with support requests

### Backup Verification
To verify backup integrity:
```powershell
# Check file count
(Get-ChildItem -Path "BackupLocation\Reports" -Recurse -File).Count

# Check latest session files
Get-ChildItem -Path "BackupLocation\Reports\Mining Session" -File | Sort-Object LastWriteTime -Descending | Select-Object -First 10
```

## Technical Details

### Backup Metadata Format
```json
{
  "backup_time": "2025-01-XX...",
  "backup_location": "C:\\Temp\\...",
  "original_location": "C:\\EliteMining\\app\\Reports",
  "files_count": 1234
}
```

### File Merge Logic
- **Newer Modified Time**: Backup file replaces existing file
- **Missing File**: Backup file is copied
- **Directory Structure**: Preserved exactly as original
- **Permissions**: Inherited from installation directory

---

**Remember**: Your mining session data is valuable and irreplaceable. These protection scripts ensure your historical data survives application updates and reinstallations.

"""
Reports Folder Protection Script
Backup and restore Reports folder during EliteMining installation
"""

import shutil
import os
from pathlib import Path
import json
from datetime import datetime
import tempfile


class ReportsProtector:
    """Protects Reports folder during installation/uninstallation"""
    
    def __init__(self, install_dir=None):
        """Initialize with installation directory"""
        self.install_dir = Path(install_dir) if install_dir else Path.cwd()
        self.reports_dir = self.install_dir / "app" / "Reports"
        self.backup_info_file = self.install_dir / "reports_backup_info.json"
        
    def create_backup(self, backup_location=None):
        """Create backup of Reports folder before installation"""
        if not self.reports_dir.exists():
            print("No Reports folder found to backup")
            return None
            
        # Use temp directory if no location specified
        if backup_location is None:
            backup_location = Path(tempfile.gettempdir()) / f"EliteMining_Reports_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        else:
            backup_location = Path(backup_location)
            
        try:
            # Create backup directory
            backup_location.mkdir(parents=True, exist_ok=True)
            
            # Copy entire Reports folder
            backup_reports = backup_location / "Reports"
            shutil.copytree(self.reports_dir, backup_reports, dirs_exist_ok=True)
            
            # Save backup info
            backup_info = {
                "backup_time": datetime.now().isoformat(),
                "backup_location": str(backup_location),
                "original_location": str(self.reports_dir),
                "files_count": sum(1 for _ in backup_reports.rglob('*') if _.is_file())
            }
            
            with open(self.backup_info_file, 'w') as f:
                json.dump(backup_info, f, indent=2)
                
            print(f"✅ Reports backup created at: {backup_location}")
            print(f"   Files backed up: {backup_info['files_count']}")
            return str(backup_location)
            
        except Exception as e:
            print(f"❌ Error creating backup: {e}")
            return None
    
    def restore_backup(self, backup_location=None):
        """Restore Reports folder from backup after installation"""
        # Load backup info if available
        backup_info = None
        if self.backup_info_file.exists():
            try:
                with open(self.backup_info_file, 'r') as f:
                    backup_info = json.load(f)
                    if backup_location is None:
                        backup_location = backup_info.get('backup_location')
            except Exception as e:
                print(f"Warning: Could not read backup info: {e}")
        
        if backup_location is None:
            print("❌ No backup location specified and no backup info found")
            return False
            
        backup_location = Path(backup_location)
        backup_reports = backup_location / "Reports"
        
        if not backup_reports.exists():
            print(f"❌ Backup not found at: {backup_reports}")
            return False
            
        try:
            # Create app directory if it doesn't exist
            self.reports_dir.parent.mkdir(parents=True, exist_ok=True)
            
            # Remove existing Reports if present
            if self.reports_dir.exists():
                shutil.rmtree(self.reports_dir)
            
            # Restore from backup
            shutil.copytree(backup_reports, self.reports_dir, dirs_exist_ok=True)
            
            files_restored = sum(1 for _ in self.reports_dir.rglob('*') if _.is_file())
            print(f"✅ Reports folder restored successfully")
            print(f"   Files restored: {files_restored}")
            
            # Clean up backup info file
            if self.backup_info_file.exists():
                self.backup_info_file.unlink()
                
            return True
            
        except Exception as e:
            print(f"❌ Error restoring backup: {e}")
            return False
    
    def merge_with_existing(self, backup_location=None):
        """Merge backup with existing Reports folder (preserve both old and new)"""
        # Load backup info if available
        if backup_location is None and self.backup_info_file.exists():
            try:
                with open(self.backup_info_file, 'r') as f:
                    backup_info = json.load(f)
                    backup_location = backup_info.get('backup_location')
            except Exception:
                pass
        
        if backup_location is None:
            print("❌ No backup location specified")
            return False
            
        backup_location = Path(backup_location)
        backup_reports = backup_location / "Reports"
        
        if not backup_reports.exists():
            print(f"❌ Backup not found at: {backup_reports}")
            return False
            
        try:
            # Ensure Reports directory exists
            self.reports_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy files from backup, keeping existing ones
            files_merged = 0
            for backup_file in backup_reports.rglob('*'):
                if backup_file.is_file():
                    relative_path = backup_file.relative_to(backup_reports)
                    target_file = self.reports_dir / relative_path
                    
                    # Create parent directories if needed
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Only copy if file doesn't exist or is older
                    if not target_file.exists():
                        shutil.copy2(backup_file, target_file)
                        files_merged += 1
                    else:
                        # Keep newer file based on modification time
                        if backup_file.stat().st_mtime > target_file.stat().st_mtime:
                            shutil.copy2(backup_file, target_file)
                            files_merged += 1
            
            print(f"✅ Reports folders merged successfully")
            print(f"   Files merged: {files_merged}")
            
            # Clean up backup info file
            if self.backup_info_file.exists():
                self.backup_info_file.unlink()
                
            return True
            
        except Exception as e:
            print(f"❌ Error merging backup: {e}")
            return False


def main():
    """Command line interface for Reports protection"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python reports_protector.py backup [backup_location]")
        print("  python reports_protector.py restore [backup_location]")
        print("  python reports_protector.py merge [backup_location]")
        return
    
    command = sys.argv[1].lower()
    backup_location = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Try to detect installation directory
    install_dir = Path.cwd()
    if (install_dir / "app" / "main.py").exists():
        # We're in the installation root
        pass
    elif (install_dir / "main.py").exists():
        # We're in the app folder
        install_dir = install_dir.parent
    else:
        print("Warning: EliteMining installation not detected in current directory")
    
    protector = ReportsProtector(install_dir)
    
    if command == "backup":
        backup_path = protector.create_backup(backup_location)
        if backup_path:
            print(f"\nBackup created successfully!")
            print(f"To restore later, run: python reports_protector.py restore \"{backup_path}\"")
    
    elif command == "restore":
        if protector.restore_backup(backup_location):
            print("\nReports folder restored successfully!")
        else:
            print("\nFailed to restore Reports folder")
    
    elif command == "merge":
        if protector.merge_with_existing(backup_location):
            print("\nReports folders merged successfully!")
        else:
            print("\nFailed to merge Reports folders")
    
    else:
        print(f"Unknown command: {command}")
        print("Use: backup, restore, or merge")


if __name__ == "__main__":
    main()

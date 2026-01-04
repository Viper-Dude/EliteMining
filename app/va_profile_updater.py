"""
VoiceAttack Profile Updater
Main orchestrator for automatic profile updates with keybind preservation
"""

import logging
import shutil
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Callable, Dict
import xml.etree.ElementTree as ET

from app.va_profile_parser import VAProfileParser
from app.va_keybind_extractor import VAKeybindExtractor, CommandKeybinds
from app.va_keybind_applier import VAKeybindApplier
from app.va_process_manager import VAProcessManager
from app.va_profile_importer import VAProfileImporter
from app.va_export_helper import VAExportHelper

logger = logging.getLogger(__name__)


@dataclass
class UpdateInfo:
    """Information about available update"""
    current_version: str
    latest_version: str
    download_url: str
    release_notes: str


@dataclass
class UpdateResult:
    """Result of profile update"""
    success: bool
    backup_path: Optional[str] = None
    keybinds_restored: int = 0
    message: str = ""
    error: Optional[str] = None


class UpdateError(Exception):
    """Profile update error"""
    pass


class VAProfileUpdater:
    """Manages VoiceAttack profile updates with keybind preservation"""
    
    def __init__(self, app_data_path: str, testing_profile: str = None):
        """
        Initialize updater
        
        Args:
            app_data_path: Path to app data directory
            testing_profile: Path to testing profile (e.g., "EliteMining v4.7.5 testing-Profile.vap")
        """
        self.app_data_path = Path(app_data_path)
        self.backup_dir = self.app_data_path / "Backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Testing profile override
        self.testing_profile = Path(testing_profile) if testing_profile else None
        
        self.parser = VAProfileParser()
        self.keybind_extractor = VAKeybindExtractor()
        self.keybind_applier = VAKeybindApplier()
        self.process_manager = VAProcessManager()
        self.importer = VAProfileImporter(str(self.process_manager.va_exe)) if self.process_manager.va_exe else None
        self.export_helper = VAExportHelper(str(self.app_data_path))
        
        logger.info(f"VA Profile Updater initialized. Backup dir: {self.backup_dir}")
        if self.testing_profile:
            logger.info(f"Testing mode: Using profile {self.testing_profile}")
    
    def get_current_profile_name(self) -> Optional[str]:
        """
        Get the name of the current EliteMining profile
        
        Returns:
            Profile name or None
        """
        current_profile = self.get_current_profile_path()
        if not current_profile:
            return None
        
        try:
            tree = self.parser.parse(str(current_profile))
            root = tree.getroot()
            name_elem = root.find('Name')
            if name_elem is not None:
                return name_elem.text
        except Exception as e:
            logger.error(f"Failed to get profile name: {e}")
        
        return None
    
    def get_current_profile_path(self) -> Optional[Path]:
        """
        Find current EliteMining profile .VAP file
        
        Returns:
            Path to current profile or None
        """
        # Use testing profile if specified
        if self.testing_profile and self.testing_profile.exists():
            logger.info(f"Using testing profile: {self.testing_profile}")
            return self.testing_profile
        
        va_data_path = self.process_manager.get_va_data_path()
        if not va_data_path:
            logger.error("Could not determine VoiceAttack data path")
            return None
        
        # Look in Apps/EliteMining subdirectory first (standard location)
        elitemining_dir = va_data_path / "Apps" / "EliteMining"
        if elitemining_dir.exists():
            profile_patterns = [
                "EliteMining*.vap",
                "elitemining*.vap",
            ]
            
            for pattern in profile_patterns:
                for vap_file in elitemining_dir.glob(pattern):
                    logger.info(f"Found profile in Apps/EliteMining: {vap_file}")
                    return vap_file
        
        # Fallback: look in VA root directory
        profile_patterns = [
            "EliteMining*.vap",
            "elitemining*.vap",
        ]
        
        for pattern in profile_patterns:
            for vap_file in va_data_path.glob(pattern):
                logger.info(f"Found profile in VA root: {vap_file}")
                return vap_file
        
        logger.warning("EliteMining profile not found")
        return None
    
    def is_export_configured(self) -> bool:
        """
        Check if XML export is configured for keybind preservation
        
        Returns:
            True if export is configured and valid
        """
        return self.export_helper.is_export_configured()
    
    def get_export_instructions(self) -> str:
        """
        Get instructions for one-time XML export setup
        
        Returns:
            Instruction text for user
        """
        return self.export_helper.get_export_instructions()
    
    def save_export_path(self, export_path: str):
        """
        Save path to XML export for future updates
        
        Args:
            export_path: Path to exported XML profile
        """
        self.export_helper.save_export_path(export_path)
        logger.info("XML export configured for automatic keybind preservation")
    
    def get_current_profile_version(self) -> str:
        """
        Get version of currently installed profile
        
        Returns:
            Version string or "unknown"
        """
        profile_path = self.get_current_profile_path()
        if not profile_path:
            return "unknown"
        
        try:
            tree = self.parser.parse(str(profile_path))
            version = self.parser.get_profile_version(tree)
            return version
        except Exception as e:
            logger.error(f"Failed to get current version: {e}")
            return "unknown"
    
    def check_for_update(self, latest_version: str, download_url: str, 
                        release_notes: str = "") -> Optional[UpdateInfo]:
        """
        Check if update is available
        
        Args:
            latest_version: Latest version available
            download_url: URL to download new profile
            release_notes: Release notes for new version
        
        Returns:
            UpdateInfo if update available, None otherwise
        """
        current_version = self.get_current_profile_version()
        
        if latest_version > current_version:
            logger.info(f"Update available: {current_version} -> {latest_version}")
            return UpdateInfo(
                current_version=current_version,
                latest_version=latest_version,
                download_url=download_url,
                release_notes=release_notes
            )
        
        logger.info(f"Profile is up to date: {current_version}")
        return None
    
    def update_profile(self, new_vap_path: str, 
                      progress_callback: Optional[Callable[[str, int], None]] = None) -> UpdateResult:
        """
        Update VoiceAttack profile while preserving keybinds
        
        Args:
            new_vap_path: Path to new .VAP file
            progress_callback: Optional callback(step: str, progress: int)
        
        Returns:
            UpdateResult with success status and details
        """
        def report_progress(step: str, progress: int):
            logger.info(f"Update progress: {step} ({progress}%)")
            if progress_callback:
                progress_callback(step, progress)
        
        backup_path = None
        
        try:
            # Step 1: Get source for keybinds (saved XML or current profile)
            report_progress("Locating keybind source...", 5)
            
            # Check for saved XML export first
            saved_export = self.export_helper.get_saved_export_path()
            if saved_export:
                logger.info(f"Using saved XML export: {saved_export}")
                keybind_source = saved_export
            else:
                # Fallback: backup current profile
                logger.warning("No saved XML export - using current profile")
                report_progress("Backing up current profile...", 10)
                backup_path = self.backup_current_profile()
                if not backup_path:
                    raise UpdateError("Failed to create backup and no XML export configured")
                keybind_source = backup_path
            
            # Step 2: Extract keybinds
            report_progress("Extracting keybinds...", 20)
            keybinds = self.extract_keybinds(keybind_source)
            keybind_count = len(keybinds)
            logger.info(f"Extracted {keybind_count} keybinds")
            
            # Step 3: Close VoiceAttack
            report_progress("Closing VoiceAttack...", 30)
            if not self.process_manager.close_voiceattack():
                raise UpdateError("Failed to close VoiceAttack")
            
            # Step 4: Install new profile
            report_progress("Installing new profile...", 50)
            self.install_profile(new_vap_path)
            
            # Step 5: Restore keybinds
            report_progress("Restoring keybinds...", 70)
            restored_count = self.restore_keybinds(keybinds)
            logger.info(f"Restored {restored_count} keybinds")
            
            # Step 6: Delete old profile from VoiceAttack to avoid conflicts
            report_progress("Preparing for import...", 75)
            if self.importer and self.process_manager.is_running():
                # Get current profile name
                old_profile_name = self.get_current_profile_name()
                if old_profile_name:
                    logger.info(f"Deleting old profile from VoiceAttack: {old_profile_name}")
                    self.importer.delete_profile_from_voiceattack(old_profile_name)
            
            # Step 7: Show import instructions to user
            report_progress("Update complete! Showing instructions...", 80)
            if self.importer:
                logger.info("Showing import instructions to user...")
                self.importer.show_import_instructions(str(new_vap_path))
            
            # Step 8: Restart VoiceAttack if needed
            report_progress("Finalizing...", 90)
            if not self.process_manager.start_voiceattack():
                raise UpdateError("Failed to restart VoiceAttack")
            
            report_progress("Complete!", 100)
            
            return UpdateResult(
                success=True,
                backup_path=backup_path,
                keybinds_restored=restored_count,
                message=f"Profile updated successfully!\n\n"
                        f"✅ Keybinds restored: {restored_count}\n"
                        f"✅ Backup created: {backup_path.name}\n\n"
                        f"📋 File path copied to clipboard!\n"
                        f"Import the profile in VoiceAttack to complete the update."
            )
            
        except Exception as e:
            logger.error(f"Update failed: {e}", exc_info=True)
            
            # Attempt rollback
            if backup_path:
                try:
                    logger.info("Attempting rollback...")
                    self.rollback(backup_path)
                    logger.info("Rollback successful")
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {rollback_error}")
            
            return UpdateResult(
                success=False,
                error=str(e),
                message=f"Update failed: {e}"
            )
    
    def backup_current_profile(self) -> Optional[str]:
        """
        Backup current profile
        
        Returns:
            Path to backup file
        """
        current_profile = self.get_current_profile_path()
        if not current_profile:
            logger.error("Cannot backup: profile not found")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        version = self.get_current_profile_version()
        backup_filename = f"EliteMining-{version}-{timestamp}.vap"
        backup_path = self.backup_dir / backup_filename
        
        try:
            shutil.copy2(current_profile, backup_path)
            logger.info(f"Backup created: {backup_path}")
            return str(backup_path)
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return None
    
    def extract_keybinds(self, profile_path: str) -> Dict[str, CommandKeybinds]:
        """
        Extract keybinds from profile
        
        Args:
            profile_path: Path to .VAP file
            
        Returns:
            Dict of command keybinds
            
        Raises:
            UpdateError: If profile format is not supported
        """
        try:
            tree = self.parser.parse(profile_path)
            keybinds = self.keybind_extractor.extract(tree)
            return keybinds
        except Exception as e:
            error_msg = str(e)
            if "Cannot decompress" in error_msg or "binary format" in error_msg.lower():
                raise UpdateError(
                    "Cannot read profile format!\n\n"
                    "Your VoiceAttack profile appears to be in binary/compressed format.\n\n"
                    "To preserve your keybinds, you need to export as XML:\n"
                    "1. Open VoiceAttack\n"
                    "2. Right-click your EliteMining profile\n"
                    "3. Select 'Export Profile'\n"
                    "4. UNCHECK 'Export as compressed binary'\n"
                    "5. Save the file and try again\n\n"
                    "Without XML format, keybind preservation cannot work."
                )
            else:
                # Re-raise other parsing errors
                raise UpdateError(f"Failed to extract keybinds: {error_msg}")
    
    def install_profile(self, new_vap_path: str):
        """
        Install new profile (replace old one)
        
        Args:
            new_vap_path: Path to new .VAP file
        """
        current_profile = self.get_current_profile_path()
        if not current_profile:
            raise UpdateError("Current profile not found")
        
        try:
            # Copy new profile to VoiceAttack directory
            shutil.copy2(new_vap_path, current_profile)
            logger.info(f"Installed new profile: {current_profile}")
        except Exception as e:
            raise UpdateError(f"Failed to install profile: {e}")
    
    def restore_keybinds(self, keybinds: Dict[str, CommandKeybinds]) -> int:
        """
        Apply keybinds to current profile
        
        Args:
            keybinds: Keybinds to apply
            
        Returns:
            Number of keybinds restored
        """
        current_profile = self.get_current_profile_path()
        if not current_profile:
            raise UpdateError("Profile not found for keybind restoration")
        
        # Load profile
        tree = self.parser.parse(str(current_profile))
        
        # Apply keybinds
        modified_tree = self.keybind_applier.apply(tree, keybinds)
        
        # Save modified profile
        self.parser.save(modified_tree, str(current_profile))
        
        return len(keybinds)
    
    def rollback(self, backup_path: str):
        """
        Restore from backup
        
        Args:
            backup_path: Path to backup file
        """
        current_profile = self.get_current_profile_path()
        if not current_profile:
            raise UpdateError("Cannot rollback: current profile location unknown")
        
        try:
            # Close VA if running
            self.process_manager.close_voiceattack()
            
            # Restore backup
            shutil.copy2(backup_path, current_profile)
            logger.info(f"Restored from backup: {backup_path}")
            
            # Restart VA
            self.process_manager.start_voiceattack()
            
        except Exception as e:
            raise UpdateError(f"Rollback failed: {e}")

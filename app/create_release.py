#!/usr/bin/env python3
"""
EliteMining Release Builder
Automates the process of building and creating installer for EliteMining
"""

import os
import sys
import subprocess
import time
import zipfile
import shutil
from pathlib import Path

# Add the app directory to the path to import version
sys.path.insert(0, str(Path(__file__).parent))
try:
    from version import get_version
except ImportError:
    def get_version():
        return "unknown"

class ReleaseBuilder:
    def __init__(self):
        self.script_dir = Path(__file__).parent.absolute()
        self.project_root = self.script_dir.parent  # Go up one level from app folder
        self.build_bat = self.project_root / "build_eliteMining_with_icon.bat"
        self.installer_iss = self.project_root / "EliteMiningInstaller.iss"
        
    def print_step(self, step_num, description):
        """Print a formatted step message"""
        print(f"\n{'='*60}")
        print(f"STEP {step_num}: {description}")
        print('='*60)
        
    def run_command(self, command, cwd=None, shell=True):
        """Run a command and return success status"""
        try:
            print(f"Running: {command}")
            if cwd:
                print(f"Working directory: {cwd}")
            
            # For batch files with pause, we need to send Enter to continue
            if command.endswith('.bat'):
                result = subprocess.run(
                    command,
                    cwd=cwd,
                    shell=shell,
                    input='\n',  # Send Enter key to bypass pause
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
            else:
                result = subprocess.run(
                    command,
                    cwd=cwd,
                    shell=shell,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
            
            if result.stdout:
                print("STDOUT:", result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr)
                
            if result.returncode == 0:
                print("✅ Command completed successfully")
                return True
            else:
                print(f"❌ Command failed with return code: {result.returncode}")
                return False
                
        except subprocess.TimeoutExpired:
            print("❌ Command timed out after 5 minutes")
            return False
        except Exception as e:
            print(f"❌ Error running command: {e}")
            return False
    
    def check_prerequisites(self):
        """Check if required files exist"""
        self.print_step(1, "Checking Prerequisites")
        
        missing_files = []
        
        if not self.build_bat.exists():
            print(f"⚠️  Build script not found: {self.build_bat}")
            print("Will use PyInstaller directly from spec file")
            
        if not self.installer_iss.exists():
            print(f"⚠️  Installer script not found: {self.installer_iss}")
            print("Will skip installer creation")
            
        print("✅ Prerequisites check complete")
        return True
    
    def run_build_script(self):
        """Execute the build batch file or PyInstaller directly"""
        self.print_step(2, "Building Executable")
        
        if self.build_bat.exists():
            print(f"Executing: {self.build_bat}")
            return self.run_command(str(self.build_bat), cwd=str(self.project_root))
        else:
            print("Running PyInstaller directly from spec file")
            spec_file = self.script_dir / "Configurator.spec"
            if spec_file.exists():
                return self.run_command(f"pyinstaller --clean {spec_file}", cwd=str(self.project_root))
            else:
                print("❌ No spec file found")
                return False
    
    def create_zip_package(self):
        """Create a ZIP package with the executable and necessary files"""
        self.print_step(4, "Creating ZIP Package")
        
        try:
            # Get version for filename
            version = get_version()
            
            # Create output directory if it doesn't exist
            output_dir = self.project_root / "Output"
            output_dir.mkdir(exist_ok=True)
            
            zip_filename = f"EliteMining {version}.zip"
            zip_path = output_dir / zip_filename
            
            print(f"Creating ZIP package: {zip_path}")
            print(f"Version: {version}")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add the main executable in EliteMining/Configurator/ folder
                exe_path = self.project_root / "dist" / "Configurator.exe"
                if exe_path.exists():
                    zipf.write(exe_path, "EliteMining/Configurator/Configurator.exe")
                    print(f"✅ Added: EliteMining/Configurator/Configurator.exe")
                else:
                    print(f"❌ Missing: {exe_path}")
                    return False
                
                # Add configuration files in EliteMining root
                config_files = [
                    ("app/config.json", "config.json"),
                    ("EliteMining-Profile.vap", "EliteMining-Profile.vap"),
                    ("LICENSE.txt", "LICENSE.txt")
                ]
                
                for source_file, dest_file in config_files:
                    config_path = self.project_root / source_file
                    if config_path.exists():
                        zipf.write(config_path, f"EliteMining/{dest_file}")
                        print(f"✅ Added: EliteMining/{dest_file}")
                
                # Add EliteVA directory at VoiceAttack Apps level
                eliteva_dir = self.project_root / "app" / "EliteVA"
                if eliteva_dir.exists():
                    for root, dirs, files in os.walk(eliteva_dir):
                        for file in files:
                            file_path = Path(root) / file
                            arc_path = f"EliteVA/{file_path.relative_to(eliteva_dir)}"
                            zipf.write(file_path, arc_path)
                    print(f"✅ Added: EliteVA/ (directory)")
                
                # Add app folder contents (Images, Settings, Reports, etc.) under EliteMining/app/
                app_dir = self.project_root / "app"
                for item in ["Images", "Ship Presets", "Reports"]:
                    item_path = app_dir / item
                    if item_path.exists():
                        if item_path.is_dir():
                            # Add directory and all its contents
                            for file_path in item_path.rglob('*'):
                                if file_path.is_file():
                                    # Skip test data files from Reports directory
                                    if item == "Reports" and file_path.name == "sessions_index.csv":
                                        print(f"⏩ Skipped: {file_path.name} (test data)")
                                        continue
                                    arc_name = f"EliteMining/app/{item}/{file_path.relative_to(item_path)}"
                                    zipf.write(file_path, arc_name)
                            print(f"✅ Added: EliteMining/app/{item}/ (directory)")
                
                # Skip adding protection scripts to ZIP - installer handles these separately
                
                # Add Variables folder if it exists under EliteMining/
                variables_dir = self.project_root / "Variables"
                if variables_dir.exists():
                    for file_path in variables_dir.rglob('*'):
                        if file_path.is_file():
                            arc_name = f"EliteMining/Variables/{file_path.relative_to(variables_dir)}"
                            zipf.write(file_path, arc_name)
                    print(f"✅ Added: EliteMining/Variables/ (directory)")
                
                # Add Doc folder if it exists under EliteMining/
                doc_dir = self.project_root / "Doc"
                if doc_dir.exists():
                    for file_path in doc_dir.rglob('*'):
                        if file_path.is_file():
                            arc_name = f"EliteMining/Doc/{file_path.relative_to(doc_dir)}"
                            zipf.write(file_path, arc_name)
                    print(f"✅ Added: EliteMining/Doc/ (directory)")
                
                # Add galaxy systems database if it exists
                galaxy_db_path = self.project_root / "app" / "data" / "galaxy_systems.db"
                if galaxy_db_path.exists():
                    arc_name = "EliteMining/app/data/galaxy_systems.db"
                    zipf.write(galaxy_db_path, arc_name)
                    size_mb = galaxy_db_path.stat().st_size / 1024 / 1024
                    print(f"✅ Added: EliteMining/app/data/galaxy_systems.db ({size_mb:.1f} MB)")
                else:
                    print("⚠️  Galaxy systems database not found - ZIP users may need to download separately")
            
            print(f"✅ ZIP package created successfully: {zip_path}")
            return True
            
        except Exception as e:
            print(f"❌ Error creating ZIP package: {e}")
            return False
    
    def run_installer_script(self):
        """Execute the Inno Setup installer script"""
        self.print_step(5, "Creating Installer")
        
        if not self.installer_iss.exists():
            print("⚠️  Installer script not found - skipping installer creation")
            print("ZIP package is available for manual installation")
            return True
        
        # Verify the executable exists and show its timestamp
        exe_path = self.project_root / "dist" / "Configurator.exe"
        if exe_path.exists():
            import datetime
            mod_time = datetime.datetime.fromtimestamp(exe_path.stat().st_mtime)
            print(f"✅ Using executable: {exe_path}")
            print(f"   Last modified: {mod_time}")
            print(f"   File size: {exe_path.stat().st_size:,} bytes")
        else:
            print(f"❌ Executable not found at: {exe_path}")
            return False
        
        # Force clean any existing installer output
        output_dir = self.project_root / "Output"
        existing_installer = output_dir / "EliteMiningSetup.exe"
        if existing_installer.exists():
            print(f"🗑️  Removing existing installer: {existing_installer}")
            existing_installer.unlink()
        
        # Try to find Inno Setup compiler
        possible_inno_paths = [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
            r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
            r"C:\Program Files\Inno Setup 5\ISCC.exe",
        ]
        
        inno_compiler = None
        for path in possible_inno_paths:
            if os.path.exists(path):
                inno_compiler = path
                break
        
        if not inno_compiler:
            print("❌ Inno Setup compiler not found in standard locations.")
            print("Trying to run ISS file directly (assuming Inno Setup is in PATH)...")
            return self.run_command(f'"{self.installer_iss}"', cwd=str(self.project_root))
        else:
            print(f"Found Inno Setup compiler: {inno_compiler}")
            print(f"Working directory: {self.project_root}")
            
            # Force a clean compile with verbose output
            command = f'"{inno_compiler}" /Q- "{self.installer_iss}"'  # /Q- for verbose output
            result = self.run_command(command, cwd=str(self.project_root))
            
            # Verify the new installer was created and show its info
            if result and existing_installer.exists():
                import datetime
                new_mod_time = datetime.datetime.fromtimestamp(existing_installer.stat().st_mtime)
                print(f"✅ New installer created: {existing_installer}")
                print(f"   Created: {new_mod_time}")
                print(f"   Size: {existing_installer.stat().st_size:,} bytes")
            
            return result
    
    def build_release(self):
        """Main method to build the complete release"""
        print("🚀 EliteMining Release Builder")
        print(f"Project root: {self.project_root}")
        
        # Step 1: Check prerequisites
        has_build_script = self.check_prerequisites()
        
        # Step 2: Run build script or fallback to direct PyInstaller
        if has_build_script:
            if not self.run_build_script():
                print("❌ Build script failed. Aborting release process.")
                return False
        else:
            # Fallback to direct PyInstaller execution
            if not self.run_pyinstaller_direct():
                print("❌ PyInstaller execution failed. Aborting release process.")
                return False
        
        # Wait a moment for file operations to complete
        print("\nWaiting 3 seconds for build to finalize...")
        time.sleep(3)
        
        # Step 3: Create ZIP package
        if not self.create_zip_package():
            print("❌ ZIP package creation failed.")
            return False
        
        # Step 4: Run installer script
        if not self.run_installer_script():
            print("❌ Installer creation failed.")
            return False
        
        # Success!
        self.print_step(6, "Release Complete!")
        print("✅ EliteMining release has been successfully created!")
        
        # Get version for display
        version = get_version()
        print(f"📦 ZIP Package: Output/EliteMining_{version}.zip")
        if self.installer_iss.exists():
            print(f"💿 Installer: Output/EliteMiningSetup.exe")
        else:
            print("⚠️  No installer created (missing installer script)")
        print(f"Check the Output directory for your release files.")
        
        return True

def main():
    """Main entry point"""
    try:
        builder = ReleaseBuilder()
        success = builder.build_release()
        
        if success:
            print("\n🎉 Release process completed successfully!")
            sys.exit(0)
        else:
            print("\n💥 Release process failed!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Release process interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

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
            
            result = subprocess.run(
                command,
                cwd=cwd,
                shell=shell,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
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
        """Execute PyInstaller build (cleans build/dist dirs first)"""
        self.print_step(2, "Building Executable")
        
        # Clean previous build artifacts (same as batch file)
        for d in [self.project_root / "build", self.project_root / "dist"]:
            if d.exists():
                import shutil
                print(f"Cleaning: {d}")
                shutil.rmtree(d, ignore_errors=True)
        
        spec_file = self.project_root / "Configurator.spec"
        if not spec_file.exists():
            spec_file = self.script_dir / "Configurator.spec"
        
        if spec_file.exists():
            print(f"Running PyInstaller with spec: {spec_file}")
            return self.run_command(f"python -m PyInstaller --clean \"{spec_file}\"", cwd=str(self.project_root))
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
                exe_path = self.project_root / "dist" / "EliteMining.exe"
                if exe_path.exists():
                    zipf.write(exe_path, "EliteMining/Configurator/EliteMining.exe")
                    print(f"✅ Added: EliteMining/Configurator/EliteMining.exe")
                else:
                    print(f"❌ Missing: {exe_path}")
                    return False
                
                # Add configuration files in EliteMining root
                config_files = [
                    ("app/config.json.template", "config.json"),  # Use template for clean config
                    ("LICENSE.txt", "LICENSE.txt")
                ]
                
                # Find versioned profile file (EliteMining v*-Profile.vap), exclude Dev profiles
                # v4.7.8+: Look in Voiceattack Profile folder
                profile_dir = self.project_root / "Voiceattack Profile"
                if profile_dir.exists():
                    profile_files = list(profile_dir.glob("EliteMining v*-Profile.vap"))
                else:
                    # Fallback to root if folder doesn't exist
                    profile_files = list(self.project_root.glob("EliteMining v*-Profile.vap"))
                # Filter out Dev profiles
                profile_files = [f for f in profile_files if 'Dev' not in f.name]
                if profile_files:
                    profile_file = profile_files[0]  # Use first match
                    zipf.write(profile_file, f"EliteMining/{profile_file.name}")
                    print(f"✅ Added: EliteMining/{profile_file.name}")
                else:
                    print("⚠️  No production profile file found (EliteMining v*-Profile.vap, excluding Dev)")
                
                for source_file, dest_file in config_files:
                    config_path = self.project_root / source_file
                    if config_path.exists():
                        zipf.write(config_path, f"EliteMining/{dest_file}")
                        print(f"✅ Added: EliteMining/{dest_file}")
                
                # Add EliteAPI directory at VoiceAttack Apps level
                eliteapi_dir = self.project_root / "app" / "EliteAPI"
                if eliteapi_dir.exists():
                    for root, dirs, files in os.walk(eliteapi_dir):
                        for file in files:
                            file_path = Path(root) / file
                            arc_path = f"EliteAPI/{file_path.relative_to(eliteapi_dir)}"
                            zipf.write(file_path, arc_path)
                    print(f"✅ Added: EliteAPI/ (directory)")
                
                # Add app folder contents (Images, Settings, Reports, etc.) under EliteMining/app/
                app_dir = self.project_root / "app"
                for item in ["Images", "Ship Presets", "Reports"]:
                    item_path = app_dir / item
                    if item_path.exists():
                        if item_path.is_dir():
                            has_files = False
                            # Add directory and all its contents
                            for file_path in item_path.rglob('*'):
                                if file_path.is_file():
                                    # Skip test data and version flag files from Reports directory
                                    if item == "Reports" and file_path.name in ["sessions_index.csv", ".v430_wipe_done"]:
                                        print(f"⏩ Skipped: {file_path.name} (development/test file)")
                                        continue
                                    arc_name = f"EliteMining/app/{item}/{file_path.relative_to(item_path)}"
                                    zipf.write(file_path, arc_name)
                                    has_files = True
                            
                            # For Reports folder, ensure empty structure exists even if no files
                            if item == "Reports" and not has_files:
                                # Create empty Reports/Mining Session directory structure
                                zipf.writestr(f"EliteMining/app/Reports/Mining Session/", "")
                                zipf.writestr(f"EliteMining/app/Reports/Mining Session/Cards/", "")
                                zipf.writestr(f"EliteMining/app/Reports/Mining Session/Detailed Reports/", "")
                                print(f"✅ Added: EliteMining/app/Reports/ (empty structure)")
                            else:
                                print(f"✅ Added: EliteMining/app/{item}/ (directory)")
                
                # Add localization folder (required for UI translations)
                localization_dir = app_dir / "localization"
                if localization_dir.exists():
                    for file_path in localization_dir.glob('*.json'):
                        arc_name = f"EliteMining/app/localization/{file_path.name}"
                        zipf.write(file_path, arc_name)
                    print(f"✅ Added: EliteMining/app/localization/ (JSON files)")
                
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
                
                # Add user database (pre-populated with hotspots) if it exists
                user_db_path = self.project_root / "app" / "data" / "UserDb for install" / "user_data.db"
                if user_db_path.exists():
                    arc_name = "EliteMining/app/data/user_data.db"
                    zipf.write(user_db_path, arc_name)
                    size_kb = user_db_path.stat().st_size / 1024
                    print(f"✅ Added: EliteMining/app/data/user_data.db ({size_kb:.1f} KB) - Pre-populated with hotspots")
                else:
                    print("⚠️  User database not found - ZIP users will start with empty database")
                
                # Add database metadata if it exists
                metadata_path = self.project_root / "app" / "data" / "database_metadata.json"
                if metadata_path.exists():
                    arc_name = "EliteMining/app/data/database_metadata.json"
                    zipf.write(metadata_path, arc_name)
                    print(f"✅ Added: EliteMining/app/data/database_metadata.json")
                
                # Add overlap and RES site CSV files for migration
                overlaps_csv = self.project_root / "app" / "data" / "overlaps.csv"
                if overlaps_csv.exists():
                    arc_name = "EliteMining/app/data/overlaps.csv"
                    zipf.write(overlaps_csv, arc_name)
                    print(f"✅ Added: EliteMining/app/data/overlaps.csv")
                
                res_csv = self.project_root / "app" / "data" / "res_sites.csv"
                if res_csv.exists():
                    arc_name = "EliteMining/app/data/res_sites.csv"
                    zipf.write(res_csv, arc_name)
                    print(f"✅ Added: EliteMining/app/data/res_sites.csv")
            
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
        exe_path = self.project_root / "dist" / "EliteMining.exe"
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
            try:
                # Try to delete, retry a few times if locked
                for attempt in range(3):
                    try:
                        existing_installer.unlink()
                        print("✅ Existing installer removed")
                        break
                    except PermissionError:
                        if attempt < 2:
                            print(f"⏳ File locked, waiting... (attempt {attempt + 1}/3)")
                            time.sleep(2)
                        else:
                            print("⚠️  Could not delete existing installer (file may be in use)")
                            print("   Continuing anyway - Inno Setup will overwrite it")
            except Exception as e:
                print(f"⚠️  Could not delete existing installer: {e}")
                print("   Continuing anyway - Inno Setup will overwrite it")
        
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
    
    def resize_splash_image(self):
        """Resize EliteMining_splash.png to max 800x460 before building"""
        self.print_step(0, "Resizing Splash Image")
        splash_path = self.script_dir / "Images" / "EliteMining_splash.png"
        if not splash_path.exists():
            print(f"⚠️  Splash image not found: {splash_path} — skipping")
            return
        try:
            from PIL import Image
            img = Image.open(splash_path)
            orig_size = img.size
            img.thumbnail((800, 460), Image.LANCZOS)
            if img.size != orig_size:
                img.save(splash_path)
                print(f"✅ Resized splash: {orig_size} → {img.size}")
            else:
                print(f"✅ Splash already fits ({orig_size}) — no resize needed")
        except Exception as e:
            print(f"⚠️  Could not resize splash image: {e}")

    def build_release(self):
        """Main method to build the complete release"""
        print("🚀 EliteMining Release Builder")
        print(f"Project root: {self.project_root}")
        
        # Step 0: Resize splash image
        self.resize_splash_image()

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

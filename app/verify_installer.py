#!/usr/bin/env python3
"""
Verify that the installer contains the correct executable
"""

import os
import tempfile
import subprocess
import shutil
from pathlib import Path
import datetime

def get_file_info(file_path):
    """Get file information"""
    if not os.path.exists(file_path):
        return None
    
    stat = os.stat(file_path)
    size = stat.st_size
    mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
    
    return {
        'size': size,
        'modified': mtime,
        'path': file_path
    }

def main():
    project_root = Path(__file__).parent.parent
    
    # Check the source executable
    source_exe = project_root / "dist" / "Configurator.exe"
    source_info = get_file_info(source_exe)
    
    print("=== Source Executable Info ===")
    if source_info:
        print(f"Path: {source_info['path']}")
        print(f"Size: {source_info['size']:,} bytes")
        print(f"Modified: {source_info['modified']}")
    else:
        print("Source executable not found!")
        return
    
    # Check the installer
    installer_exe = project_root / "Output" / "EliteMiningSetup.exe"
    installer_info = get_file_info(installer_exe)
    
    print("\n=== Installer Info ===")
    if installer_info:
        print(f"Path: {installer_info['path']}")
        print(f"Size: {installer_info['size']:,} bytes")
        print(f"Modified: {installer_info['modified']}")
    else:
        print("Installer not found!")
        return
    
    # Extract the installer to a temp directory
    print("\n=== Extracting Installer ===")
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"Extracting to: {temp_dir}")
            
            # Use innoextract if available, otherwise try manual extraction
            try:
                result = subprocess.run([
                    "innoextract", 
                    str(installer_exe), 
                    "-d", temp_dir
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    print("✅ Extracted with innoextract")
                    # Look for the executable in the extracted files
                    extracted_exe = None
                    for root, dirs, files in os.walk(temp_dir):
                        for file in files:
                            if file.lower() == "configurator.exe":
                                extracted_exe = os.path.join(root, file)
                                break
                        if extracted_exe:
                            break
                    
                    if extracted_exe:
                        extracted_info = get_file_info(extracted_exe)
                        print("\n=== Extracted Executable Info ===")
                        print(f"Path: {extracted_info['path']}")
                        print(f"Size: {extracted_info['size']:,} bytes")
                        print(f"Modified: {extracted_info['modified']}")
                        
                        # Compare
                        print("\n=== Comparison ===")
                        if extracted_info['size'] == source_info['size']:
                            print("✅ File sizes match")
                        else:
                            print(f"❌ File sizes differ: {source_info['size']} vs {extracted_info['size']}")
                        
                        time_diff = abs((extracted_info['modified'] - source_info['modified']).total_seconds())
                        if time_diff < 60:  # Allow 1 minute difference for file operations
                            print("✅ Modification times are close")
                        else:
                            print(f"❌ Modification times differ by {time_diff} seconds")
                    else:
                        print("❌ Could not find Configurator.exe in extracted files")
                else:
                    print(f"❌ innoextract failed: {result.stderr}")
                    
            except FileNotFoundError:
                print("⚠️  innoextract not available - install it for better verification")
                print("    You can download it from: https://constexpr.org/innoextract/")
                
    except Exception as e:
        print(f"❌ Error during extraction: {e}")

if __name__ == "__main__":
    main()

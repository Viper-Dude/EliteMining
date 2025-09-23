#!/usr/bin/env python3
"""
Check for any version or build inconsistencies
"""

import os
import sys
import subprocess
from pathlib import Path

def run_command(cmd, cwd=None):
    """Run command and return output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), 1

def check_executable_info(exe_path):
    """Get information about an executable"""
    if not os.path.exists(exe_path):
        return None
    
    print(f"\n=== Checking {exe_path} ===")
    
    # Get file stats
    stat = os.stat(exe_path)
    print(f"Size: {stat.st_size:,} bytes")
    print(f"Modified: {stat.st_mtime}")
    
    # Try to get version info using PowerShell
    ps_cmd = f'(Get-ItemProperty "{exe_path}").VersionInfo | Select-Object FileVersion, ProductVersion, FileDescription'
    stdout, stderr, code = run_command(f'powershell -Command "{ps_cmd}"')
    if code == 0 and stdout:
        print("Version Info:")
        print(stdout)
    
    return True

def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    print("=== EliteMining Executable Analysis ===")
    
    # Check the main executable
    main_exe = project_root / "dist" / "Configurator.exe"
    check_executable_info(main_exe)
    
    # Check for any other copies
    print("\n=== Searching for other Configurator.exe files ===")
    for root, dirs, files in os.walk(project_root):
        for file in files:
            if file.lower() == "configurator.exe":
                full_path = os.path.join(root, file)
                if full_path != str(main_exe):
                    print(f"Found additional copy: {full_path}")
                    check_executable_info(full_path)
    
    # Check version.py
    print("\n=== Checking version.py ===")
    version_file = script_dir / "version.py"
    if version_file.exists():
        try:
            sys.path.insert(0, str(script_dir))
            from version import get_version
            print(f"Current version from version.py: {get_version()}")
        except Exception as e:
            print(f"Error importing version: {e}")
    
    # Check for git status that might affect version
    print("\n=== Checking Git Status ===")
    stdout, stderr, code = run_command("git status --porcelain", cwd=project_root)
    if code == 0:
        if stdout:
            print("Modified files:")
            print(stdout)
        else:
            print("Working directory is clean")
        
        # Check current commit
        stdout, stderr, code = run_command("git rev-parse --short HEAD", cwd=project_root)
        if code == 0:
            print(f"Current commit: {stdout}")
    else:
        print("Not a git repository or git not available")

if __name__ == "__main__":
    main()

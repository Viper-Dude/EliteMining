"""
Version Update Script for EliteMining
Updates version number in: version.py, main.py, EliteMiningInstaller.iss
"""

import re
from pathlib import Path
from datetime import datetime

# === CHANGE VERSION AND DATE HERE ===
NEW_VERSION = "4.73"
NEW_BUILD_DATE = "2025-12-27"  # Format: YYYY-MM-DD (leave empty for today's date)
# ====================================

def main():
    base_path = Path(__file__).parent.parent
    
    # File paths
    version_file = base_path / "app" / "version.py"
    main_file = base_path / "app" / "main.py"
    installer_file = base_path / "EliteMiningInstaller.iss"
    
    # Use provided date or today's date
    build_date = NEW_BUILD_DATE if NEW_BUILD_DATE else datetime.now().strftime("%Y-%m-%d")
    
    print(f"Updating to version: {NEW_VERSION}")
    print(f"Build date: {build_date}")
    print("-" * 40)
    
    # Update version.py
    content = version_file.read_text(encoding="utf-8")
    content = re.sub(r'__version__ = "[^"]+"', f'__version__ = "{NEW_VERSION}"', content)
    content = re.sub(r'__build_date__ = "[^"]+"', f'__build_date__ = "{build_date}"', content)
    version_file.write_text(content, encoding="utf-8")
    print(f"✓ Updated {version_file.name}")
    
    # Update main.py
    content = main_file.read_text(encoding="utf-8")
    content = re.sub(r'APP_VERSION = "v[^"]+"', f'APP_VERSION = "v{NEW_VERSION}"', content)
    main_file.write_text(content, encoding="utf-8")
    print(f"✓ Updated {main_file.name}")
    
    # Update EliteMiningInstaller.iss
    content = installer_file.read_text(encoding="utf-8")
    content = re.sub(r'AppVersion=v[^\r\n]+', f'AppVersion=v{NEW_VERSION}', content)
    installer_file.write_text(content, encoding="utf-8")
    print(f"✓ Updated {installer_file.name}")
    
    # Create patchnotes file from template
    template_file = base_path / "docs" / "PATCHNOTES_TEMPLATE.md"
    patchnotes_file = base_path / "docs" / f"PATCHNOTES_v{NEW_VERSION}.md"
    
    if template_file.exists() and not patchnotes_file.exists():
        template = template_file.read_text(encoding="utf-8")
        template = template.replace("[DATE]", build_date)
        patchnotes_file.write_text(template, encoding="utf-8")
        print(f"✓ Created {patchnotes_file.name}")
    elif patchnotes_file.exists():
        print(f"⚠ Patchnotes already exists: {patchnotes_file.name}")
    
    print("-" * 40)
    print("Done! All version numbers updated.")

if __name__ == "__main__":
    main()

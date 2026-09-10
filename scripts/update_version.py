"""
Version Update Script for EliteMining
Updates version number in: version.py, main.py, EliteMiningInstaller.iss
"""

import re
from pathlib import Path
from datetime import datetime

# === CHANGE VERSION AND DATE HERE ===
NEW_VERSION = "5.3.8"
NEW_BUILD_DATE = "2026-September-10"  # Format: YYYY-MM-DD (leave empty for today's date)
VA_PROFILE_VERSION = "5.3.8"  # Set to "" if this release does not include a VA profile update
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
    if VA_PROFILE_VERSION:
        bundled_version = VA_PROFILE_VERSION
    else:
        # No profile update declared this release - derive the real bundled version from
        # the actual .vap filename instead of leaving whatever a prior/mistaken run wrote,
        # so BundledProfileVersion/checkbox text can't drift out of sync with what's shipped.
        vap_dir = base_path / "Voiceattack Profile"
        vap_files = list(vap_dir.glob("EliteMining v*-Profile.vap"))
        if len(vap_files) == 1:
            m = re.search(r'EliteMining v([\d.]+)-Profile\.vap', vap_files[0].name)
            bundled_version = m.group(1) if m else None
        else:
            bundled_version = None
            print(f"⚠ Could not determine bundled VA profile version ({len(vap_files)} .vap files found) - leaving BundledProfileVersion as-is")

    if bundled_version:
        content = re.sub(r"BundledProfileVersion := '[^']+'", f"BundledProfileVersion := '{bundled_version}'", content)
        content = re.sub(r'Install/Update VoiceAttack profile \(v[^)]+\)', f'Install/Update VoiceAttack profile (v{bundled_version})', content)

    if VA_PROFILE_VERSION:
        # New profile this release - show the update notice page
        content = re.sub(r'^;?InfoBeforeFile=', 'InfoBeforeFile=', content, flags=re.MULTILINE)
    else:
        # No profile update this release - suppress the update notice page
        content = re.sub(r'^;?InfoBeforeFile=', ';InfoBeforeFile=', content, flags=re.MULTILINE)
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

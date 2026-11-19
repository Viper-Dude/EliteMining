"""
VoiceAttack profile reader
Reads the player's EliteMining profile bindings from a temporary copy of
VoiceAttack's data file, using va_profile_reader.exe. The live VoiceAttack.dat
is only copied, and only while VoiceAttack is closed; otherwise the newest
backup is used. The helper only ever opens the copy.
"""

import glob
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from va_profile_parser import VAProfileParser

logger = logging.getLogger(__name__)

READER_TIMEOUT_SECS = 30
GUESSED_REASON = "highest version with bindings"


@dataclass
class VAProfileInfo:
    id: str
    name: str
    commands: int
    bound: int


@dataclass
class VAProfileReadResult:
    xml_path: str
    profile_id: str
    profile_name: str
    backup_path: str
    backup_mtime: float
    reason: str
    candidates: List[VAProfileInfo] = field(default_factory=list)

    @property
    def guessed(self) -> bool:
        """True when several EliteMining profiles exist and none matched the previously installed version."""
        return self.reason == GUESSED_REASON


def voiceattack_data_dirs() -> List[str]:
    """VoiceAttack 2 and VoiceAttack 1 data folders that exist."""
    appdata = os.environ.get('APPDATA')
    if not appdata:
        return []
    dirs = [os.path.join(appdata, 'VoiceAttack2'), os.path.join(appdata, 'VoiceAttack')]
    return [d for d in dirs if os.path.isdir(d)]


def newest_backup(data_dirs: Optional[List[str]] = None) -> Optional[str]:
    """Newest backup by modification time; the file names use a 12-hour clock, so name order is wrong."""
    if data_dirs is None:
        data_dirs = voiceattack_data_dirs()
    backups = []
    for d in data_dirs:
        backups.extend(p for p in glob.glob(os.path.join(d, 'Backup', '*VoiceAttack.dat')) if os.path.isfile(p))
    if not backups:
        return None
    return max(backups, key=os.path.getmtime)


def newest_data_file(data_dirs: Optional[List[str]] = None, include_live: bool = False) -> Optional[str]:
    """
    Newest of the backups and, with include_live (VoiceAttack closed), the live VoiceAttack.dat.
    A live file with a LiteDB log beside it may hold unwritten changes, so it is skipped.
    """
    if data_dirs is None:
        data_dirs = voiceattack_data_dirs()
    files = []
    backup = newest_backup(data_dirs)
    if backup:
        files.append(backup)
    if include_live:
        for d in data_dirs:
            live = os.path.join(d, 'VoiceAttack.dat')
            if os.path.isfile(live) and not os.path.exists(os.path.join(d, 'VoiceAttack-log.dat')):
                files.append(live)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def _version_key(version: Optional[str]) -> Optional[Tuple[int, ...]]:
    if not version:
        return None
    try:
        return tuple(int(part) for part in version.split('.'))
    except ValueError:
        return None


def choose_profile(profiles: List[VAProfileInfo],
                   installed_version: Optional[str] = None) -> Tuple[Optional[VAProfileInfo], str]:
    """Pick the player's current EliteMining profile, or return None when the choice is not clear."""
    candidates = [p for p in profiles if p.name.strip().lower().startswith('elitemining')]
    if not candidates:
        return None, "no EliteMining profile found"
    if len(candidates) == 1:
        return candidates[0], "only EliteMining profile"

    def key(p):
        return _version_key(VAProfileParser.version_from_name(p.name))

    installed = _version_key(installed_version)
    if installed:
        matches = [p for p in candidates if key(p) == installed]
        if len(matches) == 1:
            return matches[0], f"matches installed version {installed_version}"

    pool = [p for p in candidates if p.bound > 0] or candidates
    pool.sort(key=lambda p: (key(p) is not None, key(p) or (), p.bound), reverse=True)
    best = pool[0]
    if len(pool) > 1 and key(pool[1]) == key(best) and pool[1].bound == best.bound:
        return None, f"cannot choose between '{best.name}' and '{pool[1].name}'"
    return best, GUESSED_REASON


def _reader_exe_path() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent / "va_profile_reader" / "va_profile_reader.exe"
    return Path(__file__).resolve().parent.parent / "tools" / "va_profile_reader" / "bin" / "Release" / "net48" / "va_profile_reader.exe"


def _run_reader(args: List[str]) -> bool:
    exe = _reader_exe_path()
    if not exe.exists():
        logger.warning(f"[VA_READER] Helper not found: {exe}")
        return False
    try:
        proc = subprocess.run([str(exe)] + args, capture_output=True, text=True,
                              timeout=READER_TIMEOUT_SECS,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning(f"[VA_READER] Helper failed to run: {e}")
        return False
    if proc.returncode != 0:
        logger.warning(f"[VA_READER] Helper exit {proc.returncode}: {proc.stderr.strip()}")
        return False
    return True


def list_profiles(dat_copy: str, out_xml: str) -> Optional[List[VAProfileInfo]]:
    if not _run_reader(['list', dat_copy, out_xml]):
        return None
    return [VAProfileInfo(id=e.get('Id', ''), name=e.get('Name', ''),
                          commands=int(e.get('Commands', '0')), bound=int(e.get('Bound', '0')))
            for e in ET.parse(out_xml).getroot().findall('Profile')]


def read_profile_bindings(installed_version: Optional[str] = None,
                          backup_path: Optional[str] = None,
                          include_live: bool = False) -> Optional[VAProfileReadResult]:
    """
    Export the chosen EliteMining profile's commands and bindings to an XML file
    in a new temp folder (the caller deletes it). Returns None on any failure.
    Pass include_live only when VoiceAttack is not running.
    """
    backup = backup_path or newest_data_file(include_live=include_live)
    if not backup:
        logger.info("[VA_READER] No VoiceAttack data file found")
        return None

    work_dir = tempfile.mkdtemp(prefix='em_va_reader_')
    dat_copy = os.path.join(work_dir, 'VoiceAttack.dat')
    result = None
    try:
        backup_mtime = os.path.getmtime(backup)
        shutil.copy2(backup, dat_copy)

        profiles = list_profiles(dat_copy, os.path.join(work_dir, 'profiles.xml'))
        if profiles is None:
            return None
        chosen, reason = choose_profile(profiles, installed_version)
        if chosen is None:
            logger.info(f"[VA_READER] {reason}")
            return None

        xml_path = os.path.join(work_dir, 'bindings.xml')
        if not _run_reader(['export', dat_copy, chosen.id, xml_path]):
            return None
        logger.info(f"[VA_READER] Read '{chosen.name}' ({reason}) from {os.path.basename(backup)}")
        result = VAProfileReadResult(xml_path=xml_path, profile_id=chosen.id, profile_name=chosen.name,
                                   backup_path=backup, backup_mtime=backup_mtime, reason=reason,
                                   candidates=profiles)
        return result
    except (OSError, ET.ParseError, ValueError) as e:
        logger.warning(f"[VA_READER] Failed: {e}")
        return None
    finally:
        if result is None:
            shutil.rmtree(work_dir, ignore_errors=True)
        else:
            try:
                os.remove(dat_copy)
            except OSError:
                pass

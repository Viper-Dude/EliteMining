"""
Checks for the VoiceAttack profile reader (app/va_profile_reader.py + tools/va_profile_reader).

  python tools/check_va_profile_reader.py selftest
      Profile choice and newest-backup rules, on synthetic data.
  python tools/check_va_profile_reader.py real [--profile NAME] [--export EXPORT.vap] [--installed X.Y.Z]
      Reads a temp copy of VoiceAttack's newest backup and, with --export, compares every
      command's binding fields with a VoiceAttack XML export of the same profile.
"""

import argparse
import os
import shutil
import sys
import tempfile
import time
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app'))

import va_profile_reader as reader  # noqa: E402
from va_keybind_extractor import VAKeybindExtractor  # noqa: E402
from va_profile_parser import VAProfileParser  # noqa: E402

BINDING_FIELDS = [
    'Enabled', 'UseShortcut', 'keyValue', 'keyShift', 'keyAlt', 'keyCtrl', 'keyWin', 'keyPassthru',
    'onlyKeyUp', 'UseJoystick', 'joystickNumber', 'joystickButton', 'joystickNumber2', 'joystickButton2',
    'joystickUp', 'KeepRepeating', 'UseMouse', 'Mouse1', 'Mouse2', 'Mouse3', 'Mouse4', 'Mouse5', 'Mouse6',
    'Mouse7', 'Mouse8', 'Mouse9', 'MouseUpOnly', 'MousePassThru', 'joystickExclusive', 'RepeatIfKeysDown',
    'RepeatIfMouseDown', 'RepeatIfJoystickDown', 'UseVariableHotkey', 'HotkeyDoubleTapLevel',
    'MouseDoubleTapLevel', 'JoystickDoubleTapLevel', 'HotkeyLongTapLevel', 'MouseLongTapLevel',
    'JoystickLongTapLevel', 'UseVariableMouseShortcut', 'UseVariableJoystickShortcut',
]


def is_internal(name):
    s = (name or '').strip()
    return s.startswith('((') and s.endswith('))')


def has_shortcut(cmd):
    return any((cmd.findtext(f) or '') == 'true' for f in ('UseShortcut', 'UseJoystick', 'UseMouse'))


def selftest():
    P = reader.VAProfileInfo
    choose = reader.choose_profile
    profiles = [P('a', 'EliteMining v5.6.1', 297, 60), P('b', 'EliteMining v5.6.6', 308, 68),
                P('c', 'EDCoPilot', 3000, 10), P('d', 'EliteMining v5.5.8_old', 301, 50)]
    assert choose(profiles)[0].id == 'b', 'highest version'
    assert choose(profiles, '5.6.1')[0].id == 'a', 'installed version match'
    assert choose(profiles, '9.9.9')[0].id == 'b', 'installed version not present'
    assert choose(profiles + [P('e', 'EliteMining v5.7.0', 309, 0)])[0].id == 'b', 'skip unbound newest'
    assert choose([P('e', 'EliteMining v5.7.0', 309, 0), P('f', 'EliteMining v5.6.0', 300, 0)])[0].id == 'e', \
        'all unbound: highest version'
    assert choose([P('g', 'EliteMining v5.5.8_old', 301, 5), P('h', 'EliteMining v5.5.8_old 2', 301, 5)])[0] is None, \
        'tie gives no pick'
    assert choose([P('g', 'EliteMining v5.5.8_old', 301, 5), P('h', 'EliteMining v5.5.8_old 2', 301, 7)])[0].id == 'h', \
        'tie broken by bindings'
    assert choose([P('c', 'EDCoPilot', 3000, 10), P('i', 'My Mining', 300, 60)])[0] is None, 'no candidates'
    assert choose([P('j', ' elitemining custom', 300, 3)])[0].id == 'j', 'single candidate, any case'
    assert choose([P('k', 'EliteMining Custom', 300, 9), P('l', 'EliteMining v5.6.6', 308, 1)])[0].id == 'l', \
        'unversioned ranks lowest'

    def guessed(reason):
        return reader.VAProfileReadResult('', '', '', '', 0, reason).guessed
    assert guessed(choose(profiles)[1]), 'highest-version pick is a guess'
    assert not guessed(choose(profiles, '5.6.1')[1]), 'installed version match is not a guess'
    assert not guessed(choose([P('j', 'EliteMining v5.6.6', 300, 3)])[1]), 'single candidate is not a guess'

    work = tempfile.mkdtemp(prefix='em_va_selftest_')
    try:
        backup = os.path.join(work, 'VoiceAttack2', 'Backup')
        os.makedirs(backup)
        now = time.time()
        # 12-hour clock names: "...014435" is 13:44, "...102319" is 10:23; name order says 10:23 is newer.
        for name, age in (('20261119014435.VoiceAttack.dat', 0), ('20261119102319.VoiceAttack.dat', 3600),
                          ('20261118111012.VoiceAttack.dat', 7200)):
            path = os.path.join(backup, name)
            open(path, 'wb').close()
            os.utime(path, (now - age, now - age))
        open(os.path.join(work, 'VoiceAttack2', 'VoiceAttack.dat.backup'), 'wb').close()
        assert os.path.basename(reader.newest_backup([os.path.join(work, 'VoiceAttack2')])) == \
            '20261119014435.VoiceAttack.dat', 'newest by mtime'
        assert reader.newest_backup([os.path.join(work, 'missing')]) is None, 'no backups'

        va2 = os.path.join(work, 'VoiceAttack2')
        live = os.path.join(va2, 'VoiceAttack.dat')
        open(live, 'wb').close()
        os.utime(live, (now + 60, now + 60))
        open(os.path.join(va2, 'VoiceAttack_crashed.dat'), 'wb').close()
        assert os.path.basename(reader.newest_data_file([va2])) == '20261119014435.VoiceAttack.dat', \
            'live file ignored while VoiceAttack may be running'
        assert reader.newest_data_file([va2], include_live=True) == live, 'newer live file used when closed'
        os.utime(live, (now - 60, now - 60))
        assert os.path.basename(reader.newest_data_file([va2], include_live=True)) == \
            '20261119014435.VoiceAttack.dat', 'newer backup beats older live file'
        os.utime(live, (now + 60, now + 60))
        open(os.path.join(va2, 'VoiceAttack-log.dat'), 'wb').close()
        assert os.path.basename(reader.newest_data_file([va2], include_live=True)) == \
            '20261119014435.VoiceAttack.dat', 'live file with pending log skipped'
        assert reader.newest_data_file([os.path.join(work, 'missing')], include_live=True) is None, 'no data files'
    finally:
        shutil.rmtree(work, ignore_errors=True)

    frozen_exe = os.path.join('C:\\', 'VA', 'Apps', 'EliteMining', 'Configurator', 'EliteMining.exe')
    saved = (getattr(sys, 'frozen', None), sys.executable)
    try:
        sys.frozen, sys.executable = True, frozen_exe
        assert str(reader._reader_exe_path()) == os.path.join(
            os.path.dirname(frozen_exe), 'va_profile_reader', 'va_profile_reader.exe'), 'installed helper path'
    finally:
        if saved[0] is None:
            del sys.frozen
        else:
            sys.frozen = saved[0]
        sys.executable = saved[1]
    assert reader._reader_exe_path().parts[-5:] == ('va_profile_reader', 'bin', 'Release', 'net48',
                                                    'va_profile_reader.exe'), 'dev helper path'
    print('selftest: all checks passed')


def compare(reader_xml, export_path):
    ours = {}
    dup = Counter()
    for cmd in VAProfileParser().parse(reader_xml).getroot().findall('Commands/Command'):
        name = cmd.findtext('CommandString')
        dup[name] += 1
        ours[name] = cmd
    theirs = {}
    internal_skipped = 0
    for cmd in VAProfileParser().parse(export_path).getroot().findall('Commands/Command'):
        name = cmd.findtext('CommandString')
        if is_internal(name):
            internal_skipped += 1
            continue
        theirs[name] = cmd

    mismatches = []
    for name in sorted(set(ours) & set(theirs)):
        for f in BINDING_FIELDS:
            a = ours[name].findtext(f) or ''
            b = theirs[name].findtext(f) or ''
            if a != b:
                mismatches.append((name, f, a, b))

    print(f"reader commands: {len(ours)}  export player commands: {len(theirs)}  "
          f"export internal commands skipped: {internal_skipped}")
    print(f"reader commands with a shortcut: {sum(has_shortcut(c) for c in ours.values())}")
    print(f"internal commands in reader output: {sum(is_internal(n) for n in ours)}")
    for name in sorted(set(theirs) - set(ours)):
        print(f"  only in export: {name}")
    for name in sorted(set(ours) - set(theirs)):
        print(f"  only in reader: {name}")
    for name, n in dup.items():
        if n > 1:
            print(f"  duplicate in reader: {name} x{n}")
    print(f"field mismatches: {len(mismatches)} ({len(BINDING_FIELDS)} fields per command)")
    for name, f, a, b in mismatches[:50]:
        print(f"  {name!r} {f}: reader={a!r} export={b!r}")
    return not mismatches and set(ours) == set(theirs)


def merge_check(reader_tree, extracted, new_vap):
    """Apply the reader's bindings to a copy of new_vap (as the update flow does) and compare them read back."""
    from va_keybind_applier import VAKeybindApplier

    def norm(value):
        return '' if value in (None, '', 'false', '0') else value

    parser = VAProfileParser()
    applier = VAKeybindApplier()
    work = tempfile.mkdtemp(prefix='em_va_merge_')
    try:
        merged_path = os.path.join(work, 'merged.vap')
        parser.save(applier.apply(parser.parse(new_vap), extracted), merged_path, compress=False)
        result = applier.last_result
        merged = {c.findtext('CommandString'): c
                  for c in parser.parse(merged_path).getroot().findall('Commands/Command')}
        source = {c.findtext('CommandString'): c for c in reader_tree.getroot().findall('Commands/Command')}
        mismatches = []
        for name in result.applied:
            if result.matched_by.get(name) != 'exact':
                continue
            old = source.get(name)
            new = merged.get(name)
            if old is None or new is None:
                continue
            for f in BINDING_FIELDS:
                if f.startswith('UseVariable'):
                    continue
                # The shipped profile omits elements left at their default
                if norm(old.findtext(f)) != norm(new.findtext(f)):
                    mismatches.append((name, f, old.findtext(f), new.findtext(f)))
        print(f"merge into {os.path.basename(new_vap)}: {len(result.applied)} applied, "
              f"{len(result.not_applied)} not applied, field mismatches on exact names: {len(mismatches)}")
        for name, reason in result.not_applied:
            print(f"  not applied: {name!r} ({reason})")
        for name, f, a, b in mismatches[:20]:
            print(f"  {name!r} {f}: reader={a!r} merged={b!r}")

        # VoiceAttack ignores elements that are out of its export order
        from va_keybind_applier import COMMAND_ELEMENT_ORDER
        rank = {n: i for i, n in enumerate(COMMAND_ELEMENT_ORDER)}
        out_of_order = []
        for name, cmd in merged.items():
            ranks = [rank[e.tag] for e in cmd if e.tag in rank]
            if ranks != sorted(ranks):
                out_of_order.append(name)
        print(f"commands with elements out of VoiceAttack order: {len(out_of_order)}")
        for name in out_of_order[:10]:
            print(f"  {name!r}")
        return not mismatches and not out_of_order
    finally:
        shutil.rmtree(work, ignore_errors=True)


def real(args):
    backup = reader.newest_backup()
    print(f"newest backup: {backup}")
    if not backup:
        return False

    if args.profile:
        work = tempfile.mkdtemp(prefix='em_va_check_')
        try:
            dat = os.path.join(work, 'VoiceAttack.dat')
            shutil.copy2(backup, dat)
            profiles = reader.list_profiles(dat, os.path.join(work, 'profiles.xml'))
            match = [p for p in profiles or [] if p.name == args.profile]
            if len(match) != 1:
                print(f"profile '{args.profile}' found {len(match)} times")
                return False
            xml_path = os.path.join(work, 'bindings.xml')
            if not reader._run_reader(['export', dat, match[0].id, xml_path]):
                return False
            os.remove(dat)
            result = reader.VAProfileReadResult(xml_path, match[0].id, match[0].name, backup,
                                                os.path.getmtime(backup), 'chosen by --profile', profiles)
        except Exception:
            shutil.rmtree(work, ignore_errors=True)
            raise
    else:
        result = reader.read_profile_bindings(installed_version=args.installed, backup_path=backup)
    if result is None:
        print("read failed (see log)")
        return False

    try:
        print(f"profile: {result.profile_name} ({result.reason})")
        for p in result.candidates:
            print(f"  {p.name!r}: {p.commands} player commands, {p.bound} bound")
        tree = VAProfileParser().parse(result.xml_path)
        extracted = VAKeybindExtractor().extract(tree)
        print(f"extractor smoke test: {len(extracted)} commands with bindings found")
        ok = True
        if args.export:
            ok = compare(result.xml_path, args.export)
        if args.merge:
            ok = merge_check(tree, extracted, args.merge) and ok
        return ok
    finally:
        shutil.rmtree(os.path.dirname(result.xml_path), ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='mode', required=True)
    sub.add_parser('selftest')
    r = sub.add_parser('real')
    r.add_argument('--profile')
    r.add_argument('--export')
    r.add_argument('--installed')
    r.add_argument('--merge', help='new .vap to apply the read bindings to (a temp copy)')
    args = ap.parse_args()
    if args.mode == 'selftest':
        selftest()
        return 0
    return 0 if real(args) else 1


if __name__ == '__main__':
    sys.exit(main())

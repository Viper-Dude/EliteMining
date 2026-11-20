# EliteMining — Build & Release

The user handles all installer and release-package builds. Agents do not run PyInstaller, the release builder, or the installer compiler. This file documents the user's workflow.

```powershell
# CRITICAL: Clean PyInstaller cache before every build
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
python app/create_release.py
```

- Version constants in `app/version.py`: `__version__`, `__config_version__`, `__build_date__`
- `Configurator.spec` → PyInstaller → exe at `VoiceAttack\Apps\EliteMining\Configurator\`
- `EliteMiningInstaller.iss` → Inno Setup installer with VoiceAttack path auto-detection
- Output ZIP in `Output/` directory
- `app/create_release.py` builds the VoiceAttack binding reader (`dotnet build tools/va_profile_reader -c Release`, needs the .NET SDK) and aborts if that fails. The installer and ZIP ship its output, without the `.pdb`, to `Configurator\va_profile_reader\`.

## Splash Version Labels

- Set `NEW_VERSION` in `scripts/update_version.py` and run that script before `app/create_release.py`.
- Set `VA_PROFILE_VERSION` when releasing a new VoiceAttack profile; otherwise leave it empty so the splash uses the version from the bundled `.vap` filename.
- When `VA_PROFILE_VERSION` is set, `app/create_release.py` automatically runs `clear_keybinds.py` on that profile before building and aborts if cleanup fails.
- The version script generates `app/Images/EliteMining_splash.png` from `app/Images/EliteMining_splash_base.png`, adding both version labels each time. It requires Pillow and the installed `Orbitron-VariableFont_wght.ttf` font (Medium weight).
- When changing the splash artwork in Affinity, export the complete artwork with only the version labels hidden and refresh `EliteMining_splash_base.png` with that clean export. Keep the base at full resolution; never replace it with the generated splash containing version labels.
- The release builder resizes the generated splash to fit 1200 × 675 and the main logo to fit 1600 × 900; it leaves the splash base unchanged.
- Every installer clears only the installed `{app}\app\Images` folder before copying the current runtime images. ZIP extraction does not remove old files.
- Build-only and unused artwork stays in the project but is excluded from both packages, including the clean splash base and README main logo. Keep `EliteMining_txt_logo_transp_resize.png` in both packages: non-Modern status bars, About screens, and generated mining cards still use it.

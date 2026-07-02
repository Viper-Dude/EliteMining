# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

# Collect matplotlib's data files (fonts, mpl-data), binaries, and submodules
mpl_datas, mpl_binaries, mpl_hiddenimports = collect_all('matplotlib')
# Collect numpy fully — required by matplotlib at runtime
np_datas, np_binaries, np_hiddenimports = collect_all('numpy')

a = Analysis(
    ['app\\main.py'],
    pathex=['app'],
    binaries=mpl_binaries + np_binaries,
    datas=mpl_datas + np_datas,
    hiddenimports=[
        'requests', 'requests.adapters', 'requests.auth', 'requests.cookies',
        'requests.models', 'requests.sessions', 'requests.structures', 'urllib3',
        'zlib',
        # Logging
        'logging_setup',
        # Event-driven file monitoring (optional)
        'file_watcher', 'watchdog', 'watchdog.observers', 'watchdog.events',
        # Matplotlib for charts and graphs (data files + submodules collected via collect_all above)
        'matplotlib', 'matplotlib.pyplot', 'matplotlib.dates', 'matplotlib.backends.backend_tkagg',
        # Additional dependencies
        'ctypes', 'ctypes.wintypes',
        # UI module components
        'ui', 'ui.theme', 'ui.tooltip', 'ui.dialogs'
    ] + mpl_hiddenimports + np_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # NOTE: numpy submodules cannot be safely excluded — matplotlib + numpy's
        # internal _distributor_init machinery requires them. Use collect_all('numpy').
        # Exclude unused stdlib packages
        'unittest', 'pydoc', 'doctest', 'difflib',
        'ftplib', 'imaplib', 'poplib', 'smtplib', 'telnetlib', 'nntplib',
        # Exclude test/dev tooling never needed at runtime
        'pytest', '_pytest', 'setuptools', 'pkg_resources', 'pip',
        'lib2to3', 'xmlrpc', 'multiprocessing',
        # Exclude unused matplotlib backends
        'matplotlib.backends.backend_pdf', 'matplotlib.backends.backend_ps',
        'matplotlib.backends.backend_svg', 'matplotlib.backends.backend_wx',
        'matplotlib.backends.backend_gtk3', 'matplotlib.backends.backend_qt5',
        'matplotlib.tests',
        # Exclude unused PIL modules
        'PIL.ImageQt', 'PIL.ImageWin',
        # Exclude tkinter test modules
        'tkinter.test',
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='EliteMining',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    icon='app/Images/logo_multi.ico',
    codesign_identity=None,
    entitlements_file=None,
)

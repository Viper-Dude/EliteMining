# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app\\main.py'],
    pathex=['app'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'requests', 'requests.adapters', 'requests.auth', 'requests.cookies', 
        'requests.models', 'requests.sessions', 'requests.structures', 'urllib3', 
        'hotspot_finder', 'zlib',
        # Logging and journal scanning modules
        'logging_setup', 'incremental_journal_scanner', 'journal_scan_state',
        # Event-driven file monitoring (optional)
        'file_watcher', 'watchdog', 'watchdog.observers', 'watchdog.events',
        # Matplotlib for charts and graphs
        'matplotlib', 'matplotlib.pyplot', 'matplotlib.dates', 'matplotlib.backends.backend_tkagg',
        # Additional dependencies
        'ctypes', 'ctypes.wintypes',
        # UI module components
        'ui', 'ui.theme', 'ui.tooltip', 'ui.dialogs'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unused numpy submodules to reduce exe size
        'numpy.testing', 'numpy._pytesttester',
        'numpy.linalg', 'numpy.fft', 'numpy.polynomial',
        'numpy.random', 'numpy.ma', 'numpy.matlib',
        'numpy.distutils', 'numpy.f2py',
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

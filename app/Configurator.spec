# -*- mode: python ; coding: utf-8 -*-

# PyInstaller imports for VS Code linting
from PyInstaller.building.build_main import Analysis
from PyInstaller.building.api import PYZ, EXE
import sys
import os

# Get Tcl/Tk library paths
tcl_path = os.path.join(sys.base_prefix, 'tcl')
tcl_library = os.path.join(tcl_path, 'tcl8.6')
tk_library = os.path.join(tcl_path, 'tk8.6')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/Images', 'Images'), 
        ('app/Settings', 'Settings'), 
        ('app/Reports', 'Reports'),
        ('app/localization', 'localization'),
        (tcl_library, 'tcl8.6'),
        (tk_library, 'tk8.6'),
    ],
    hiddenimports=[
        'matplotlib',
        'matplotlib.pyplot',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_agg',
        'matplotlib.figure',
        'matplotlib.dates',
        'matplotlib.ticker',
        'matplotlib.patches',
        'matplotlib.colors',
        'matplotlib.font_manager',
        'matplotlib.style',
        'numpy',
        'numpy.core',
        'numpy.lib.format',
        'mining_charts',
        'mining_statistics',
        'prospector_panel',
        'announcer',
        'config',
        'version',
        'update_checker',
        'material_utils',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'requests',
        'packaging',
        'packaging.version'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Configurator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app/Images/logo.ico'],
)

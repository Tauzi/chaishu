# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['_tkinter']
hiddenimports += collect_submodules('tkinter')


a = Analysis(
    ['chaishu_gui.py'],
    pathex=[],
    binaries=[('C:\\Users\\12231.TAU\\AppData\\Local\\Programs\\Python\\Python311\\DLLs\\_tkinter.pyd', '.'), ('C:\\Users\\12231.TAU\\AppData\\Local\\Programs\\Python\\Python311\\DLLs\\tcl86t.dll', '.'), ('C:\\Users\\12231.TAU\\AppData\\Local\\Programs\\Python\\Python311\\DLLs\\tk86t.dll', '.')],
    datas=[('C:\\Users\\12231.TAU\\AppData\\Local\\Programs\\Python\\Python311\\Lib\\tkinter', 'tkinter'), ('C:\\Users\\12231.TAU\\AppData\\Local\\Programs\\Python\\Python311\\tcl\\tcl8.6', '_tcl_data'), ('C:\\Users\\12231.TAU\\AppData\\Local\\Programs\\Python\\Python311\\tcl\\tk8.6', '_tk_data')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_runtime_hook.py'],
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
    name='ChaishuDesktop',
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
)

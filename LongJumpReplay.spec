# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('PIL') + ['hid']

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('config.json', '.'), ('assets/long_jump_replay.ico', 'assets')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LongJumpReplay',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/long_jump_replay.ico',
    version='windows_version_info.txt',
)
coll = COLLECT(a.binaries, a.datas, strip=False, upx=True, upx_exclude=[], name='LongJumpReplay')

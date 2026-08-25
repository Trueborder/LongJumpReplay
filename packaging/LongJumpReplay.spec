# -*- mode: python ; coding: utf-8 -*-

project_root = os.path.dirname(SPECPATH)
version_file = os.path.join(SPECPATH, 'windows_version_info.txt')

a = Analysis(
    [os.path.join(project_root, 'app.py')],
    pathex=[project_root],
    binaries=[],
    datas=[
        (os.path.join(project_root, 'config.json'), '.'),
        (os.path.join(project_root, 'assets/long_jump_replay.ico'), 'assets'),
        (os.path.join(project_root, 'assets/long_jump_splash.png'), 'assets'),
    ],
    hiddenimports=['hid'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

splash = Splash(
    os.path.join(project_root, 'assets/long_jump_splash.png'),
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    minify_script=True,
    always_on_top=True,
    center='active',
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    [],
    name='LongJumpReplay',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    exclude_binaries=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=version_file if os.path.exists(version_file) else None,
    icon=[os.path.join(project_root, 'assets/long_jump_replay.ico')],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    splash.binaries,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='LongJumpReplay',
)

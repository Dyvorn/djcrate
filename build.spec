# -*- mode: python ; coding: utf-8 -*-
# DJ Crate build.spec — PyInstaller configuration for v0.3.2
# Generates a one-folder Windows executable bundled via COLLECT.
# Inno Setup then wraps the dist/ folder into a single installer exe.

import os

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'djcrate',
        'djcrate.app',
        'djcrate.config',
        'djcrate.database',
        'djcrate.logger',
        'djcrate.utils',
        'djcrate.obs_overlay',
        'djcrate.serato',
        'djcrate.updater',
        'djcrate.ui',
        'djcrate.workers',
        'qtawesome',
        'mutagen',
        'mutagen.id3',
        'mutagen.flac',
        'mutagen.wave',
        'mutagen.mp4',
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtMultimedia',
        'sqlalchemy',
        'numpy',
        'scipy',
        'librosa',
        'requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DJ Crate',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No terminal window on launch
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DJ Crate',
)

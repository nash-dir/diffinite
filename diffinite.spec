# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for diffinite standalone binary.

Produces a one-directory (onedir) bundle that includes all Python
dependencies. Onedir mode avoids antivirus false-positive detections
that frequently occur with single-file executables.

Used by CI (release.yml) to create platform-specific bundles
for the VSCode Extension and GitHub Release assets.

Usage:
    pyinstaller diffinite.spec
    # Output: dist/diffinite/  (directory containing diffinite executable + libs)
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['src/diffinite/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # diffinite submodules
        'diffinite.cli',
        'diffinite.pipeline',
        'diffinite.collector',
        'diffinite.parser',
        'diffinite.differ',
        'diffinite.fingerprint',
        'diffinite.deep_compare',
        'diffinite.evidence',
        'diffinite.models',
        'diffinite.pdf_gen',
        # languages registry
        'diffinite.languages',
        'diffinite.languages._registry',
        'diffinite.languages._spec',
        'diffinite.languages.c_family',
        'diffinite.languages.csharp',
        'diffinite.languages.data',
        'diffinite.languages.go_rust_swift',
        'diffinite.languages.java',
        'diffinite.languages.javascript',
        'diffinite.languages.markup',
        'diffinite.languages.python',
        'diffinite.languages.scripting',
        # dependencies
        'rapidfuzz',
        'charset_normalizer',
        'pygments',
        'xhtml2pdf',
        'pypdf',
        'reportlab',
        'reportlab.graphics.barcode',
        'reportlab.graphics.barcode.code128',
        'reportlab.graphics.barcode.code39',
        'reportlab.graphics.barcode.code93',
        'reportlab.graphics.barcode.common',
        'reportlab.graphics.barcode.eanbc',
        'reportlab.graphics.barcode.ecc200datamatrix',
        'reportlab.graphics.barcode.fourstate',
        'reportlab.graphics.barcode.lto',
        'reportlab.graphics.barcode.qr',
        'reportlab.graphics.barcode.qrencoder',
        'reportlab.graphics.barcode.usps',
        'reportlab.graphics.barcode.usps4s',
        'reportlab.graphics.barcode.widgets',
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

# Onedir mode: EXE only contains scripts (no binaries/datas)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='diffinite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# COLLECT gathers exe + binaries + data into dist/diffinite/ folder
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='diffinite',
)

# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for diffinite standalone binary.

Produces a single-file executable that includes all Python
dependencies. Used by CI (build-binaries.yml) to create
platform-specific binaries for the VSCode Extension bundle.

Usage:
    pyinstaller diffinite.spec
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
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

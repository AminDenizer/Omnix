# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

datas = [
    ('ui', 'ui'),
    ('data/starter_backup.obk', 'data'),
    ('vendors/lion.xpl', 'vendors'),
    ('vendors/javan.xpl', 'vendors'),
    ('core/plugins/trust_store', 'core/plugins/trust_store'),
    ('core/plugins/manifest.schema.json', 'core/plugins'),
]

hiddenimports = [
    'PyQt6.sip',
    'openpyxl',
    'reportlab',
    'reportlab.graphics.barcode',
    'reportlab.lib.pagesizes',
    'selenium',
    'sqlite3',
    'bidi',
    'arabic_reshaper',
    'jsonschema',
] + collect_submodules('core') + collect_submodules('ui') + collect_submodules('vendors')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'torch',
        'cv2',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Omnix',
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
    icon=['ui/icons/app_logo.ico'],
)

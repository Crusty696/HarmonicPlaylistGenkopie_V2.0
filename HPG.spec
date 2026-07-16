# -*- mode: python ; coding: utf-8 -*-
# WICHTIG (Python 3.12.0): CPython-3.12.0-Bug laesst scipy.stats im Frozen-Build
# crashen (NameError 'obj', pyinstaller#8186). Workaround ist im Build-venv
# gepatcht: venv312\...\scipy\stats\_distn_infrastructure.py, letzte Zeile des
# _doc_-Cleanups -> globals().pop('obj', None). Bei frischem venv312 Patch
# erneut anwenden oder Python >= 3.12.1 verwenden.
import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

block_cipher = None

binaries = collect_dynamic_libs('soundfile')

# Hiddenimports gezielt sammeln, um dynamische Importfehler zur Laufzeit (z. B. scipy oder librosa) auszuschließen
hidden_imports = [
    'scipy',
    'scipy.signal',
    'scipy.signal._spectral',
    'scipy.special',
    'scipy.special.cython_special',
    'librosa',
    'librosa.effects',
    'librosa.feature',
    'librosa.beat',
    'soundfile',
    'mutagen',
    'pyrekordbox',
    'numpy',
    'PyQt6',
    'pedalboard',
]

# Automatische Submodule für Stabilität sammeln
hidden_imports += collect_submodules('scipy')
hidden_imports += collect_submodules('librosa')
hidden_imports += collect_submodules('soundfile')
hidden_imports += collect_submodules('pedalboard')

# Daten- und DLL-Dateien für Librosa und Rekordbox sammeln
datas = collect_data_files('librosa')
datas += collect_data_files('pyrekordbox')

# Icon Pfad festlegen
icon_file = 'icon.ico'
if not os.path.exists(icon_file):
    icon_file = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
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
    name='HarmonicPlaylistGenerator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Setze auf False, damit beim Öffnen der GUI kein störendes DOS-Fenster erscheint
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

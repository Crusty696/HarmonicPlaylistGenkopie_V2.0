# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec File for Harmonic Playlist Generator v3.0
Builds standalone Windows executable with all dependencies
"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Add data files if needed (e.g., images, configs)
        # ('path/to/data', 'destination_folder'),
    ],
    hiddenimports=[
        # Core dependencies
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',

        # Audio analysis
        'librosa',
        'librosa.core',
        'librosa.feature',
        'librosa.beat',
        'numpy',
        'scipy',
        'scipy.signal',
        'soundfile',

        # Metadata
        'mutagen',
        'mutagen.mp3',
        'mutagen.flac',
        'mutagen.wave',
        'mutagen.aiff',

        # Optional: Rekordbox integration
        'pyrekordbox',
        'pyrekordbox.db6',
        'sqlalchemy',
        'bidict',

        # Caching
        'sqlite3',
        'shelve',

        # Multiprocessing
        'multiprocessing',
        'concurrent.futures',

        # System
        'platform',
        'pathlib',
        'typing',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce size
        'matplotlib',
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
        'tkinter',
        'test',
        'unittest',
        'pytest',
    ],
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
    upx=True,  # Compress executable (optional, may cause issues)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',  # App icon (create this file)
    version_file='version_info.txt',  # Version info (create this file)
)

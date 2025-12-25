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
        # Include hpg_core package as data (backup for imports)
        ('hpg_core', 'hpg_core'),
    ],
    hiddenimports=[
        # HPG Core modules (CRITICAL - must be explicit!)
        'hpg_core',
        'hpg_core.models',
        'hpg_core.config',
        'hpg_core.analysis',
        'hpg_core.playlist',
        'hpg_core.caching',
        'hpg_core.parallel_analyzer',
        'hpg_core.rekordbox_importer',
        'hpg_core.exporters',
        'hpg_core.exporters.base_exporter',
        'hpg_core.exporters.m3u8_exporter',
        'hpg_core.exporters.rekordbox_xml_exporter',

        # Core dependencies
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',

        # Audio analysis
        'librosa',
        'librosa.core',
        'librosa.core.audio',
        'librosa.core.spectrum',
        'librosa.core.pitch',
        'librosa.core.constantq',
        'librosa.feature',
        'librosa.feature.spectral',
        'librosa.feature.rhythm',
        'librosa.beat',
        'librosa.onset',
        'librosa.util',
        'numpy',
        'numpy.core',
        'numpy.fft',
        'numpy.testing',
        'scipy',
        'scipy.signal',
        'scipy.spatial',
        'scipy.sparse',
        'scipy.fft',
        'soundfile',
        'audioread',

        # Metadata
        'mutagen',
        'mutagen.mp3',
        'mutagen.flac',
        'mutagen.wave',
        'mutagen.aiff',
        'mutagen.id3',
        'mutagen.mp4',

        # Optional: Rekordbox integration
        'pyrekordbox',
        'pyrekordbox.db6',
        'sqlalchemy',
        'sqlalchemy.orm',
        'sqlalchemy.engine',
        'bidict',

        # Caching
        'sqlite3',
        'shelve',
        'dbm',
        'dbm.dumb',

        # Multiprocessing (CRITICAL for parallel analysis)
        'multiprocessing',
        'multiprocessing.pool',
        'multiprocessing.queues',
        'multiprocessing.managers',
        'concurrent.futures',
        'concurrent.futures.process',

        # System
        'platform',
        'pathlib',
        'typing',
        'dataclasses',
        'enum',
        'hashlib',
        'contextlib',

        # Standard library (needed by numpy.testing)
        'unittest',
        'unittest.mock',
        'doctest',
        'pprint',
        'tempfile',
        'warnings',
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
        'scipy.optimize',
        'scipy.stats',
        'scipy.integrate',
        'scipy.interpolate',
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
    console=False,  # No console window (GUI app) - freeze_support() now handles multiprocessing
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',  # App icon (create this file)
    version_file='version_info.txt',  # Version info (create this file)
)

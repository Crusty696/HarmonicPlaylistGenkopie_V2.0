# -*- mode: python ; coding: utf-8 -*-
# Hinweis: Build braucht Python >= 3.12.1 (3.12.0 crasht scipy.stats im
# Frozen-Build, pyinstaller#8186). Basis-Python ist seit 2026-07-16 3.12.10.
import sys
import os
import importlib.util
from pathlib import Path


def _hpg_build_path(system_root, executable, base_prefix, qt_bin):
    """Deterministische DLL-Suchpfade; niemals geerbte PATH-Eintraege uebernehmen."""
    def validated(value, *, file=False):
        raw = str(value)
        if not raw or any(character in raw for character in (os.pathsep, '"', '\0', '\r', '\n')):
            raise ValueError('Build-PATH enthaelt einen ungueltigen Pfad')
        path = Path(raw)
        if not path.is_absolute():
            raise ValueError('Build-PATH braucht absolute Pfade')
        try:
            path = path.resolve(strict=True)
        except (OSError, ValueError) as exc:
            raise ValueError('Build-PATH-Pfad existiert nicht') from exc
        if not (path.is_file() if file else path.is_dir()):
            raise ValueError('Build-PATH-Pfad hat den falschen Typ')
        return path

    windows = validated(system_root)
    interpreter = validated(executable, file=True)
    base = validated(base_prefix)
    qt = validated(qt_bin)
    directories = [validated(windows / 'System32'), windows,
                   validated(interpreter.parent), base, validated(base / 'DLLs'), qt]
    seen = set()
    result = []
    for directory in directories:
        key = os.path.normcase(str(directory))
        if key not in seen:
            seen.add(key)
            result.append(str(directory))
    return os.pathsep.join(result)


# Nur die Build-Prozessumgebung aendern, vor Hooks und jeder Collector-Ausfuehrung.
# Qt-Pfad aus dem installierten Paket ableiten, ohne eine Qt-DLL zu laden.
_hpg_qt_spec = importlib.util.find_spec('PyQt6')
_hpg_qt_locations = list(getattr(_hpg_qt_spec, 'submodule_search_locations', None) or ())
if len(_hpg_qt_locations) != 1:
    raise ValueError('Build braucht genau einen installierten PyQt6-Paketpfad')
os.environ['PATH'] = _hpg_build_path(
    os.environ.get('SystemRoot', ''), sys.executable, sys.base_prefix,
    Path(_hpg_qt_locations[0]) / 'Qt6' / 'bin',
)

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
# Mitgelieferte JSON-Daten (transition_tolerances.json, candidate_preferences.json):
# tolerances.py / candidate_preferences.py lesen Path(__file__).parent / 'data'
_hpg_data_dir = os.path.join(SPECPATH, 'hpg_core', 'data')   # SPECPATH: Spec-Verzeichnis, nicht cwd
datas += [(os.path.join(_hpg_data_dir, f), os.path.join('hpg_core', 'data'))
          for f in sorted(os.listdir(_hpg_data_dir)) if f.endswith('.json')]


def _hpg_source_datas(spec_root):
    """Exakte Quell-Allowlist fuer denselben Algorithmus-Fingerprint im Frozen-Build."""
    root = Path(spec_root).resolve(strict=True)
    files = [root / 'tools' / 'rate_transitions.py', *root.glob('hpg_core/**/*.py')]
    result = []
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root)
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
            raise ValueError('Fingerprint-Quelle verlaesst SPECPATH')
        result.append((str(path), relative.parent.as_posix()))
    return result


datas += _hpg_source_datas(SPECPATH)

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
    version='version_info.txt',
)

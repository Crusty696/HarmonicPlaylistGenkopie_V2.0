"""Gemeinsamer Installationspfad fuer die gepinnte Rekordbox-Laufzeit."""
import os
from pathlib import Path


DEFAULT_REKORDBOX_ROOT = Path(r'C:\Program Files\rekordbox\rekordbox 7.2.19')
_configured_root = os.environ.get('HPG_REKORDBOX_ROOT', '').strip()
REKORDBOX_ROOT = Path(_configured_root) if _configured_root else DEFAULT_REKORDBOX_ROOT
REKORDBOX_EXE = REKORDBOX_ROOT / 'rekordbox.exe'

"""
HPG Core - Harmonic Playlist Generator Core Module.

This package provides audio analysis, playlist generation,
and export functionality for DJ mixing.
"""

# Bewusst keine Re-Exporte: `from hpg_core import Track` o.ae. nutzte niemand,
# und der Import von `.analysis` zog librosa bei JEDEM Paket-Import (auch fuer
# Tools, die nur den Cache lesen). Module werden direkt importiert
# (`from hpg_core.models import Track`).
from .app_metadata import APP_VERSION

# Einzige Versionsquelle ist app_metadata.APP_VERSION.
__version__ = APP_VERSION

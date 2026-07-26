"""Ressourcenlimits fuer sichere Playlist-Verarbeitung.

Der alte Modulname ``playlist_security`` bleibt als Kompatibilitaetsschicht
erhalten; neue Anwendungspfade verwenden diesen fachlich passenden Namen.
"""

from .playlist_security import (
    sanitize_playlist,
    validate_playlist_security,
    validate_track_security,
)

__all__ = [
    "sanitize_playlist",
    "validate_playlist_security",
    "validate_track_security",
]

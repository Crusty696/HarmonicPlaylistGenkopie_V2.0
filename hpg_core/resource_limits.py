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
    "filter_library_tracks",
    "sanitize_playlist",
    "validate_playlist_security",
    "validate_track_security",
]


def filter_library_tracks(tracks):
    """Validate individual library files before selecting a playlist."""
    return [track for track in tracks if track is not None and validate_track_security(track)]

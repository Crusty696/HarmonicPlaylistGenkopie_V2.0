"""
M3U8 Playlist Exporter - Universal DJ Software Compatible

Exports playlists in M3U8 format, compatible with:
- Rekordbox 5.x, 6.x, 7.x
- Serato DJ Pro
- Traktor Pro 3
- iTunes/Music.app
- VLC Media Player
- Most other DJ software and media players
"""

import logging
import os
from typing import List
from ..models import Track
from .base_exporter import BaseExporter

logger = logging.getLogger(__name__)


class M3U8Exporter(BaseExporter):
    """
    M3U8 Playlist Exporter

    Features:
    - UTF-8 encoding for international characters
    - Extended M3U format with metadata (#EXTINF)
    - Compatible with all major DJ software
    - No dependencies required
    """

    def __init__(self, encoding: str = "utf-8"):
        """
        Initialize M3U8 Exporter

        Args:
            encoding: File encoding (default: utf-8)
        """
        self.encoding = encoding

    def export(
        self,
        playlist: List[Track],
        output_path: str,
        playlist_name: str = "HPG Playlist",
    ) -> None:
        """
        Export playlist to M3U8 format

        Args:
            playlist: List of Track objects
            output_path: Path to save .m3u8 file
            playlist_name: Name of the playlist

        Raises:
            ValueError: If playlist is empty or invalid
            IOError: If file cannot be written
        """
        # Validate playlist
        self._validate_playlist(playlist)

        try:
            with open(output_path, "w", encoding=self.encoding) as f:
                # Write header
                f.write("#EXTM3U\n")
                f.write(f"#EXTENC:{self.encoding.upper()}\n")
                f.write(f"#PLAYLIST:{playlist_name}\n\n")

                # Write tracks
                for track in playlist:
                    # Extended info: duration, artist - title
                    duration = int(track.duration) if track.duration else 0

                    # M10: Sanitize metadata to prevent newline injection
                    artist = (track.artist or "Unknown Artist").replace("\n", " ").replace("\r", "")
                    title = (track.title or os.path.basename(track.filePath)).replace("\n", " ").replace("\r", "")

                    # EXTINF format: #EXTINF:duration,artist - title
                    f.write(f"#EXTINF:{duration},{artist} - {title}\n")

                    # M5: Pfade mit Forward-Slashes fuer Cross-Platform-Kompatibilitaet
                    # M10: Sanitize path to prevent path traversal/newline injection
                    normalized_path = track.filePath.replace("\n", "").replace("\r", "").replace("\\", "/")
                    f.write(f"{normalized_path}\n\n")

            logger.info(f"M3U8 exportiert: {output_path} ({len(playlist)} Tracks)")

        except IOError as e:
            raise IOError(f"Failed to write M3U8 file: {e}")

    def get_format_info(self) -> dict:
        """
        Get information about the M3U8 format

        Returns:
            Dictionary with format information
        """
        return {
            "format": "M3U8",
            "extension": ".m3u8",
            "encoding": self.encoding,
            "compatible_with": [
                "Rekordbox 5.x, 6.x, 7.x",
                "Serato DJ Pro",
                "Traktor Pro 3",
                "iTunes/Music.app",
                "VLC Media Player",
                "Most DJ Software",
            ],
            "features": [
                "Track paths",
                "Artist & Title metadata",
                "Duration information",
                "UTF-8 support",
            ],
            "limitations": [
                "No BPM data",
                "No Key data",
                "No Cue Points",
                "No Beat Grid",
            ],
        }

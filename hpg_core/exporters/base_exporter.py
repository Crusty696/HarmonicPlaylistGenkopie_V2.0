"""
Base Exporter - Abstract Base Class for all playlist exporters
"""

from abc import ABC, abstractmethod
from typing import List
from ..models import Track


class BaseExporter(ABC):
    """
    Abstract base class for playlist exporters

    All exporters must implement the export() method
    """

    @abstractmethod
    def export(self, playlist: List[Track], output_path: str, playlist_name: str = "HPG Playlist") -> None:
        """
        Export playlist to target format

        Args:
            playlist: List of Track objects to export
            output_path: Full path where to save the exported file
            playlist_name: Name of the playlist

        Raises:
            IOError: If file cannot be written
            ValueError: If playlist is empty or invalid
        """
        pass

    def _validate_playlist(self, playlist: List[Track]) -> None:
        """
        Validate playlist before export

        Args:
            playlist: List of Track objects

        Raises:
            ValueError: If playlist is empty or contains invalid tracks
        """
        if not playlist:
            raise ValueError("Playlist is empty. Cannot export empty playlist.")

        if not all(isinstance(track, Track) for track in playlist):
            raise ValueError("Playlist contains invalid track objects.")

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename to remove invalid characters

        Args:
            filename: Raw filename

        Returns:
            Sanitized filename safe for file systems
        """
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename

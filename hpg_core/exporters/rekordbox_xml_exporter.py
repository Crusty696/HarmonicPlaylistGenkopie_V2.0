"""
Rekordbox XML Exporter - Professional DJ Integration

Exports playlists in Rekordbox XML format with full metadata:
- BPM, Key, Genre
- Hot Cues A/B + Memory Cues fuer Mix In/Out
- Memory Cues fuer erkannte Sektionen (Drop/Breakdown)
- Beat Grid (TEMPO-Element, Anker bei 0.0s)
- Playlist Hierarchy

Compatible with Rekordbox 5.x, 6.x, 7.x
"""

import logging
import os
from typing import List, Optional
from ..models import Track
from .base_exporter import BaseExporter

logger = logging.getLogger(__name__)

try:
    from pyrekordbox.rbxml import RekordboxXml

    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    logging.getLogger(__name__).warning("pyrekordbox nicht installiert. Install: pip install pyrekordbox")


class RekordboxXMLExporter(BaseExporter):
    """
    Rekordbox XML Exporter - Professional DJ Integration

    Features:
    - Metadata (BPM, Key, Genre)
    - Hot Cues A/B + Memory Cues (Mix In/Out), Sektions-Cues (Drop/Breakdown)
    - Beat Grid (TEMPO-Element)
    - Playlist hierarchy
    - Rekordbox 5.x, 6.x, 7.x compatible
    """

    # Camelot Wheel → Rekordbox Key Mapping
    CAMELOT_TO_REKORDBOX = {
        # Major Keys (B)
        "1B": "B",
        "2B": "Gb",
        "3B": "Db",
        "4B": "Ab",
        "5B": "Eb",
        "6B": "Bb",
        "7B": "F",
        "8B": "C",
        "9B": "G",
        "10B": "D",
        "11B": "A",
        "12B": "E",
        # Minor Keys (A)
        "1A": "Abm",
        "2A": "Ebm",
        "3A": "Bbm",
        "4A": "Fm",
        "5A": "Cm",
        "6A": "Gm",
        "7A": "Dm",
        "8A": "Am",
        "9A": "Em",
        "10A": "Bm",
        "11A": "Gbm",
        "12A": "Dbm",
    }

    def __init__(self):
        """
        Initialize Rekordbox XML Exporter

        Raises:
            ImportError: If pyrekordbox is not installed
        """
        if not PYREKORDBOX_AVAILABLE:
            raise ImportError(
                "pyrekordbox is required for Rekordbox XML export. "
                "Install with: pip install pyrekordbox"
            )

    def export(
        self,
        playlist: List[Track],
        output_path: str,
        playlist_name: str = "HPG Playlist",
    ) -> None:
        """
        Export playlist to Rekordbox XML format

        Args:
            playlist: List of Track objects
            output_path: Path to save rekordbox.xml
            playlist_name: Name of the playlist

        Raises:
            ValueError: If playlist is empty or invalid
            IOError: If file cannot be written
            ImportError: If pyrekordbox is not available
        """
        # Validate playlist
        self._validate_playlist(playlist)

        try:
            # Create new Rekordbox XML
            xml = RekordboxXml()

            # Add tracks to collection
            for idx, track in enumerate(playlist, start=1):
                self._add_track_to_collection(xml, track, idx)

            # Create playlist -- get_playlist() wirft auf frischem XML ValueError,
            # Ordner und Playlist muessen explizit angelegt werden
            folder = xml.add_playlist_folder("HPG Playlists")
            pl = folder.add_playlist(playlist_name)
            for idx in range(1, len(playlist) + 1):
                pl.add_track(str(idx))

            # Save XML
            xml.save(output_path)

            logger.info(f"Rekordbox XML exportiert: {output_path} ({len(playlist)} Tracks, Playlist: {playlist_name})")

        except Exception as e:
            raise IOError(f"Failed to export Rekordbox XML: {e}")

    def _add_track_to_collection(
        self, xml: "RekordboxXml", track: Track, track_id: int
    ) -> None:
        """
        Add a single track to the Rekordbox XML collection

        Args:
            xml: RekordboxXml instance
            track: Track object
            track_id: Unique track ID
        """
        # Convert file path to Rekordbox URI
        uri = self._convert_to_rekordbox_uri(track.filePath)

        # Add track to collection
        rb_track = xml.add_track(uri)

        # Basic metadata
        rb_track["TrackID"] = str(track_id)
        rb_track["Name"] = track.title or os.path.basename(track.filePath)
        rb_track["Artist"] = track.artist or "Unknown Artist"
        rb_track["Genre"] = track.genre or ""

        # Duration
        if track.duration:
            rb_track["TotalTime"] = str(int(track.duration))

        # BPM
        if track.bpm:
            rb_track["AverageBpm"] = f"{track.bpm:.2f}"

        # Key (convert from Camelot to Rekordbox notation)
        if track.camelotCode:
            rb_key = self._convert_camelot_to_rekordbox_key(track.camelotCode)
            if rb_key:
                rb_track["Tonality"] = rb_key

        # Add Beat Grid (TEMPO element)
        self._add_beat_grid(rb_track, track)

        # Add Cue Points (Mix In/Out markers + Sektions-Cues)
        self._add_cue_points(xml, rb_track, track)

    def _add_beat_grid(self, rb_track: dict, track: Track) -> None:
        """
        Schreibt ein TEMPO-Element (Beatgrid-Anker) fuer den Track.

        Downbeat-Feature 2026-07-17: Anker ist der erkannte erste Downbeat
        (Track.first_downbeat); 0.0 wenn keiner erkannt wurde.
        """
        if not track.bpm or track.bpm <= 0:
            return
        try:
            if hasattr(rb_track, "add_tempo"):
                inizio = float(getattr(track, "first_downbeat", 0.0) or 0.0)
                rb_track.add_tempo(Inizio=inizio, Bpm=float(track.bpm), Metro="4/4", Battito=1)
        except Exception as e:
            logger.warning(f"Beat Grid konnte nicht zur XML hinzugefuegt werden: {e}")

    def _add_cue_points(
        self, xml: "RekordboxXml", rb_track: dict, track: Track
    ) -> None:
        """
        Add Cue Points to track (POSITION_MARKs).

        Mix In/Out werden doppelt geschrieben: als Hot Cue A/B (Num=0/1, direkt
        anspringbar) UND als Memory Cue (Num=-1, sichtbar in der Waveform).
        Erkannte Drop-/Breakdown-Sektionen werden als Memory Cues exportiert.
        """
        try:
            # pyrekordbox-API: Hot Cue = Num>=0, Memory Cue = Num=-1
            if hasattr(track, "mix_in_point") and track.mix_in_point > 0:
                rb_track.add_mark(Name="MIX IN", Type="cue", Start=track.mix_in_point, Num=0)
                rb_track.add_mark(Name="MIX IN", Type="cue", Start=track.mix_in_point, Num=-1)

            if hasattr(track, "mix_out_point") and track.mix_out_point > 0:
                rb_track.add_mark(Name="MIX OUT", Type="cue", Start=track.mix_out_point, Num=1)
                rb_track.add_mark(Name="MIX OUT", Type="cue", Start=track.mix_out_point, Num=-1)

            # Sektions-Cues: erkannte Drops/Breakdowns als Memory Cues
            for section in (track.sections or []):
                label = str(section.get("label", "")).lower()
                start = section.get("start_time")
                if label in ("drop", "breakdown") and start and start > 0:
                    rb_track.add_mark(
                        Name=label.upper(), Type="cue", Start=float(start), Num=-1
                    )
        except Exception as e:
            logger.warning(f"Cue Points konnten nicht zur XML hinzugefuegt werden: {e}")

    def _convert_to_rekordbox_uri(self, file_path: str) -> str:
        """
        Convert Windows/Unix path to Rekordbox URI format

        Args:
            file_path: Absolute or relative file path

        Returns:
            Rekordbox URI format (file://localhost/C:/Music/track.wav)
        """
        # Normalize to absolute path
        abs_path = os.path.abspath(file_path)

        # Convert to URI format
        if os.name == "nt":  # Windows
            # Replace backslashes with forward slashes
            abs_path = abs_path.replace("\\", "/")
            uri = f"file://localhost/{abs_path}"
        else:  # Unix/Linux/Mac
            uri = f"file://localhost{abs_path}"

        return uri

    def _convert_camelot_to_rekordbox_key(self, camelot_code: str) -> Optional[str]:
        """
        Convert Camelot code to Rekordbox key notation

        Args:
            camelot_code: Camelot code (e.g., "8A", "9B")

        Returns:
            Rekordbox key notation (e.g., "Am", "G") or None if unknown
        """
        # m2: Case-Normalisierung fuer robuste Lookup
        if not camelot_code:
            return None
        return self.CAMELOT_TO_REKORDBOX.get(camelot_code.upper().strip())

    def get_format_info(self) -> dict:
        """
        Get information about the Rekordbox XML format

        Returns:
            Dictionary with format information
        """
        return {
            "format": "Rekordbox XML",
            "extension": ".xml",
            "compatible_with": ["Rekordbox 5.x", "Rekordbox 6.x", "Rekordbox 7.x"],
            "features": [
                "Track paths (URI format)",
                "Artist, Title, Genre metadata",
                "BPM & Beat Grid (TEMPO)",
                "Key (Musical Key)",
                "Hot Cues A/B + Memory Cues (Mix In/Out)",
                "Sektions-Cues (Drop/Breakdown)",
                "Playlist hierarchy",
                "Duration",
            ],
            "metadata_mapping": {
                "bpm": "AverageBpm",
                "key": "Tonality (Camelot → Key)",
                "mix_in_point": "POSITION_MARK (MIX IN)",
                "mix_out_point": "POSITION_MARK (MIX OUT)",
                "file_path": "Location (URI)",
                "artist": "Artist",
                "title": "Name",
                "genre": "Genre",
                "duration": "TotalTime",
            },
            "dependencies": ["pyrekordbox>=0.3.0"],
        }

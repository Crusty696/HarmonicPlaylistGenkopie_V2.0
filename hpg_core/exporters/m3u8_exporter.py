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
import tempfile
from typing import List
from ..models import Track
from .base_exporter import BaseExporter, ExportReport

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

    def __init__(self, encoding: str = "utf-8", relative_paths: bool = False):
        """
        Initialize M3U8 Exporter

        Args:
            encoding: File encoding (default: utf-8)
            relative_paths: Write paths relative to the .m3u8 file directory.
        """
        self.encoding = encoding
        self.relative_paths = relative_paths

    def export(
        self,
        playlist: List[Track],
        output_path: str,
        playlist_name: str = "HPG Playlist",
    ) -> ExportReport:
        """
        Export playlist to M3U8 format

        Args:
            playlist: List of Track objects
            output_path: Path to save .m3u8 file
            playlist_name: Name of the playlist

        Returns:
            ExportReport. M3U8 kennt weder Cues noch Beatgrids -> beide 0.
            status="partial", wenn einzelne Tracks uebersprungen wurden.

        Raises:
            ValueError: If playlist is empty or invalid
            IOError: If file cannot be written
        """
        # Validate playlist
        self._validate_playlist(playlist)

        errors: List[str] = []
        tracks_written = 0

        try:
            # HIGH-Fix: atomar schreiben — erst in eine Temp-Datei im Zielordner,
            # dann os.replace(). Verhindert eine abgeschnittene/korrupte .m3u8 bei
            # Absturz/voller Platte bzw. dass eine parallel lesende DJ-Software
            # eine halb geschriebene Playlist sieht (konsistent zum XML-Exporter).
            out_dir = os.path.dirname(os.path.abspath(output_path)) or "."
            fd, tmp_path = tempfile.mkstemp(suffix=".m3u8", dir=out_dir)
            try:
                with os.fdopen(fd, "w", encoding=self.encoding) as f:
                    # Write header
                    safe_playlist_name = (
                        playlist_name.replace("\r", " ").replace("\n", " ")
                    )
                    f.write("#EXTM3U\n")
                    f.write(f"#EXTENC:{self.encoding.upper()}\n")
                    f.write(f"#PLAYLIST:{safe_playlist_name}\n\n")

                    # Write tracks
                    for track in playlist:
                        # Ohne Dateipfad ist der Eintrag fuer jeden Player wertlos —
                        # ueberspringen und im Report melden (status="partial").
                        if not track.filePath:
                            errors.append(
                                "Track uebersprungen (kein Dateipfad): "
                                + (track.title or track.fileName or "?")
                            )
                            continue

                        # Extended info: duration, artist - title
                        duration = int(track.duration) if track.duration else 0

                        # M10: Sanitize metadata to prevent newline injection
                        artist = (track.artist or "Unknown Artist").replace("\n", " ").replace("\r", "")
                        title = (track.title or os.path.basename(track.filePath)).replace("\n", " ").replace("\r", "")

                        # EXTINF format: #EXTINF:duration,artist - title
                        f.write(f"#EXTINF:{duration},{artist} - {title}\n")

                        # M5: Pfade mit Forward-Slashes fuer Cross-Platform-Kompatibilitaet
                        # M10: Sanitize path to prevent path traversal/newline injection
                        normalized_path = track.filePath.replace("\n", "").replace("\r", "")
                        if self.relative_paths:
                            try:
                                normalized_path = os.path.relpath(
                                    normalized_path, out_dir
                                )
                            except ValueError:
                                # Unterschiedliche Windows-Laufwerke koennen
                                # nicht relativ zueinander ausgedrueckt werden.
                                pass
                        if normalized_path.startswith("\\\\"):
                            # UNC-Netzwerkpfad (\\server\share): nativ belassen — ein
                            # pauschales \\->// macht //server/share draus (weder gueltiger
                            # UNC noch file://-URI, Player finden die Datei nicht).
                            pass
                        else:
                            normalized_path = normalized_path.replace("\\", "/")
                        f.write(f"{normalized_path}\n\n")
                        tracks_written += 1
                if tracks_written == 0:
                    raise IOError(
                        f"Kein Track exportierbar (0/{len(playlist)}): "
                        + "; ".join(errors[:3])
                    )
                os.replace(tmp_path, output_path)
            except BaseException:
                # Temp-Datei bei jedem Fehler aufraeumen, dann weiterreichen
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                raise

            logger.info(f"M3U8 exportiert: {output_path} ({tracks_written} Tracks)")
            return ExportReport(
                status="partial" if errors else "success",
                output_path=output_path,
                tracks_written=tracks_written,
                cues_written=0,
                beatgrids_written=0,
                errors=tuple(errors),
            )

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
            "relative_paths": self.relative_paths,
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

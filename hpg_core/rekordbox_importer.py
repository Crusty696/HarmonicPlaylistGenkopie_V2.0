"""
Rekordbox Database Importer

Imports analyzed track data from Rekordbox 6/7 master.db database.
Provides BPM, Key, Cue Points, and metadata from Rekordbox's professional analysis.

Features:
- Automatic Rekordbox database detection
- BPM import (Rekordbox analyzed)
- Musical Key import with Rekordbox → Camelot conversion
- Cue Point import (Memory Cues, Hot Cues)
- Fast lookup by file path
- Graceful fallback if Rekordbox not available
"""

import os
from typing import Optional, Dict, List
from pathlib import Path
from dataclasses import dataclass

try:
    from pyrekordbox import Rekordbox6Database
    REKORDBOX_AVAILABLE = True
except ImportError:
    REKORDBOX_AVAILABLE = False
    print("[INFO] pyrekordbox not installed. Rekordbox import unavailable.")
    print("[INFO] Install with: pip install pyrekordbox")


@dataclass
class RekordboxTrackData:
    """Container for Rekordbox analyzed track data"""
    bpm: Optional[float] = None
    key: Optional[str] = None  # Rekordbox notation (e.g., "Am", "C")
    camelot_code: Optional[str] = None  # Converted to Camelot (e.g., "8A", "8B")
    duration: Optional[float] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    genre: Optional[str] = None
    album: Optional[str] = None
    rating: Optional[int] = None
    cue_points: Optional[List[Dict]] = None
    color: Optional[str] = None


class RekordboxImporter:
    """
    Imports track analysis data from Rekordbox 6/7 database

    Usage:
        importer = RekordboxImporter()
        if importer.is_available():
            data = importer.get_track_data("/path/to/track.wav")
            print(f"BPM: {data.bpm}, Key: {data.camelot_code}")
    """

    # Rekordbox stores keys in MIXED formats:
    # - Most tracks: Camelot codes (1A-12A, 1B-12B)
    # - Some tracks: Musical notation (Am, Fm, C, etc.)
    # We need to handle both!

    VALID_CAMELOT_CODES = {
        '1A', '2A', '3A', '4A', '5A', '6A', '7A', '8A', '9A', '10A', '11A', '12A',
        '1B', '2B', '3B', '4B', '5B', '6B', '7B', '8B', '9B', '10B', '11B', '12B'
    }

    REKORDBOX_TO_CAMELOT = {
        # Major keys (B)
        'C': '8B', 'Db': '3B', 'D': '10B', 'Eb': '5B', 'E': '12B', 'F': '7B',
        'Gb': '2B', 'G': '9B', 'Ab': '4B', 'A': '11B', 'Bb': '6B', 'B': '1B',
        # Minor keys (A)
        'Cm': '5A', 'Dbm': '12A', 'Dm': '7A', 'Ebm': '2A', 'Em': '9A', 'Fm': '4A',
        'Gbm': '11A', 'Gm': '6A', 'Abm': '1A', 'Am': '8A', 'Bbm': '3A', 'Bm': '10A',
    }

    def __init__(self):
        """Initialize Rekordbox Importer"""
        self.db = None
        self.track_cache: Dict[str, RekordboxTrackData] = {}

        if REKORDBOX_AVAILABLE:
            try:
                self.db = Rekordbox6Database()
                self._build_track_cache()
                print(f"[SUCCESS] Rekordbox database loaded: {len(self.track_cache)} tracks")
            except Exception as e:
                print(f"[WARNING] Failed to load Rekordbox database: {e}")
                self.db = None

    def is_available(self) -> bool:
        """Check if Rekordbox database is available"""
        return self.db is not None and len(self.track_cache) > 0

    def _build_track_cache(self):
        """Build fast lookup cache of all Rekordbox tracks"""
        if not self.db:
            return

        try:
            for content in self.db.get_content():
                # Build full file path
                folder_path = content.FolderPath or ""
                file_name = content.FileNameL or content.FileNameS or ""

                if not file_name:
                    continue

                # Normalize path for matching
                full_path = os.path.join(folder_path, file_name)
                full_path = os.path.normpath(full_path).lower()

                # Extract data
                # Note: Rekordbox stores BPM as integer * 100 (e.g., 13600 = 136.0 BPM)
                data = RekordboxTrackData(
                    bpm=float(content.BPM) / 100.0 if content.BPM else None,
                    key=content.KeyName if hasattr(content, 'KeyName') else None,
                    duration=float(content.Length) if content.Length else None,
                    title=content.Title,
                    artist=content.ArtistName if hasattr(content, 'ArtistName') else None,
                    genre=content.GenreName if hasattr(content, 'GenreName') else None,
                    album=content.AlbumName if hasattr(content, 'AlbumName') else None,
                    rating=content.Rating if content.Rating else None,
                    color=content.ColorName if hasattr(content, 'ColorName') else None,
                )

                # Convert Rekordbox key to Camelot
                if data.key:
                    data.camelot_code = self._convert_key_to_camelot(data.key)

                # Extract cue points
                if hasattr(content, 'Cues') and content.Cues:
                    data.cue_points = self._extract_cue_points(content.Cues)

                # Cache by normalized path
                self.track_cache[full_path] = data

        except Exception as e:
            print(f"[WARNING] Error building Rekordbox track cache: {e}")

    def _convert_key_to_camelot(self, rekordbox_key: str) -> Optional[str]:
        """
        Convert/validate Rekordbox key to Camelot code

        Rekordbox stores keys in MIXED formats:
        - Most: Camelot codes (8A, 11B, 6A, etc.) → return directly
        - Some: Musical notation (Am, C, Fm, etc.) → convert to Camelot

        Args:
            rekordbox_key: Rekordbox key (e.g., "8A", "Am", "C")

        Returns:
            Camelot code (e.g., "8A", "8B") or None if unknown
        """
        # Clean up key string
        key = rekordbox_key.strip()

        # 1. Check if already valid Camelot code (most common case)
        if key in self.VALID_CAMELOT_CODES:
            return key

        # 2. Try to convert from musical notation
        if key in self.REKORDBOX_TO_CAMELOT:
            return self.REKORDBOX_TO_CAMELOT[key]

        # 3. Try with 'sharp' → 'flat' conversion (e.g., "C#" → "Db")
        if '#' in key:
            sharp_to_flat = {
                'C#': 'Db', 'D#': 'Eb', 'F#': 'Gb', 'G#': 'Ab', 'A#': 'Bb',
                'C#m': 'Dbm', 'D#m': 'Ebm', 'F#m': 'Gbm', 'G#m': 'Abm', 'A#m': 'Bbm'
            }
            flat_key = sharp_to_flat.get(key)
            if flat_key and flat_key in self.REKORDBOX_TO_CAMELOT:
                return self.REKORDBOX_TO_CAMELOT[flat_key]

        # Unknown format
        print(f"[WARNING] Unknown Rekordbox key format: {rekordbox_key}")
        return None

    def _extract_cue_points(self, cues) -> List[Dict]:
        """
        Extract cue points from Rekordbox Cues relationship

        Args:
            cues: Rekordbox Cues objects

        Returns:
            List of cue point dictionaries with position and name
        """
        cue_list = []

        try:
            for cue in cues:
                cue_data = {
                    'position': float(cue.InMsec) / 1000.0 if hasattr(cue, 'InMsec') else None,
                    'name': cue.Comment if hasattr(cue, 'Comment') else None,
                    'type': cue.Kind if hasattr(cue, 'Kind') else None,
                    'hot_cue_number': cue.HotCueBankNumber if hasattr(cue, 'HotCueBankNumber') else None,
                    'color': cue.ColorID if hasattr(cue, 'ColorID') else None,
                }
                cue_list.append(cue_data)
        except Exception as e:
            print(f"[WARNING] Error extracting cue points: {e}")

        return cue_list

    def get_track_data(self, file_path: str) -> Optional[RekordboxTrackData]:
        """
        Get Rekordbox analysis data for a specific track

        Args:
            file_path: Absolute path to audio file

        Returns:
            RekordboxTrackData object with analysis data, or None if not found
        """
        if not self.is_available():
            return None

        # Normalize path for lookup
        normalized_path = os.path.normpath(file_path).lower()

        # Try exact match
        if normalized_path in self.track_cache:
            return self.track_cache[normalized_path]

        # Try filename-only match (fallback for moved files)
        filename = os.path.basename(normalized_path)
        for cached_path, data in self.track_cache.items():
            if os.path.basename(cached_path) == filename:
                print(f"[INFO] Found Rekordbox match by filename: {filename}")
                return data

        return None

    def get_available_count(self) -> int:
        """Get number of tracks available in Rekordbox database"""
        return len(self.track_cache)

    def has_track(self, file_path: str) -> bool:
        """Check if track exists in Rekordbox database"""
        return self.get_track_data(file_path) is not None

    def get_statistics(self) -> Dict:
        """Get statistics about Rekordbox database content"""
        if not self.is_available():
            return {
                'available': False,
                'total_tracks': 0,
            }

        stats = {
            'available': True,
            'total_tracks': len(self.track_cache),
            'tracks_with_bpm': sum(1 for d in self.track_cache.values() if d.bpm),
            'tracks_with_key': sum(1 for d in self.track_cache.values() if d.camelot_code),
            'tracks_with_cues': sum(1 for d in self.track_cache.values() if d.cue_points),
            'average_bpm': None,
        }

        # Calculate average BPM
        bpms = [d.bpm for d in self.track_cache.values() if d.bpm]
        if bpms:
            stats['average_bpm'] = sum(bpms) / len(bpms)

        return stats


# Global singleton instance
_rekordbox_importer: Optional[RekordboxImporter] = None


def get_rekordbox_importer() -> RekordboxImporter:
    """Get or create global RekordboxImporter singleton"""
    global _rekordbox_importer
    if _rekordbox_importer is None:
        _rekordbox_importer = RekordboxImporter()
    return _rekordbox_importer

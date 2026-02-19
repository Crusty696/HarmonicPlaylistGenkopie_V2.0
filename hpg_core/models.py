from __future__ import annotations
from dataclasses import dataclass, field

# Mapping from Key and Mode to Camelot Code
CAMELOT_MAP = {
    ('A', 'Minor'): '8A', ('A#', 'Minor'): '3A', ('B', 'Minor'): '10A',
    ('C', 'Minor'): '5A', ('C#', 'Minor'): '12A', ('D', 'Minor'): '7A',
    ('D#', 'Minor'): '2A', ('E', 'Minor'): '9A', ('F', 'Minor'): '4A',
    ('F#', 'Minor'): '11A', ('G', 'Minor'): '6A', ('G#', 'Minor'): '1A',
    ('C', 'Major'): '8B', ('C#', 'Major'): '3B', ('D', 'Major'): '10B',
    ('D#', 'Major'): '5B', ('E', 'Major'): '12B', ('F', 'Major'): '7B',
    ('F#', 'Major'): '2B', ('G', 'Major'): '9B', ('G#', 'Major'): '4B',
    ('A', 'Major'): '11B', ('A#', 'Major'): '6B', ('B', 'Major'): '1B',
}

@dataclass
class Track:
    # Core Info
    filePath: str
    fileName: str

    # ID3 Tag Info
    artist: str = "Unknown"
    title: str = "Unknown"
    genre: str = "Unknown"

    # Analysis Info
    duration: float = 0.0
    bpm: float = 0.0
    keyNote: str = ""
    keyMode: str = ""
    camelotCode: str = ""
    energy: int = 0
    bass_intensity: int = 0

    # Structural Info
    mix_in_point: float = 0.0
    mix_out_point: float = 0.0

    # Mix Points in Bars (für DJ-Anzeige)
    mix_in_bars: int = 0
    mix_out_bars: int = 0

    # DJ Brain - Genre Detection (Phase 1)
    detected_genre: str = "Unknown"
    genre_confidence: float = 0.0
    genre_source: str = ""

    # DJ Brain - Track Structure (Phase 2)
    sections: list = field(default_factory=list)  # Liste von TrackSection-Dicts
    phrase_unit: int = 8

    # Audio Feature Extensions (Phase 3)
    brightness: int = 0  # Spektrale Helligkeit 0-100 (dunkel→hell)
    vocal_instrumental: str = "unknown"  # "vocal", "instrumental", "unknown"
    danceability: int = 0  # Tanzbarkeit 0-100
    mfcc_fingerprint: list = field(default_factory=list)  # MFCC-Vektor für Similarity

def key_to_camelot(track: Track):
    """Assigns a Camelot code to a track based on its key."""
    if track.keyNote and track.keyMode:
        track.camelotCode = CAMELOT_MAP.get((track.keyNote, track.keyMode), "")


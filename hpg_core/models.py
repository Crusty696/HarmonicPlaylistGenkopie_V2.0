from __future__ import annotations
import re
from dataclasses import dataclass, field

from .config import METER, BPM_HALF_DOUBLE_ENABLED

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

# Hinweis: TrackSection lebt in structure_analyzer.py (einzige Definition).
# Das fruehere ungenutzte Duplikat hier wurde entfernt (Audit 2026-07-17);
# in Track.sections liegen serialisierte Section-Dicts.


def seconds_per_bar(bpm: float, meter: int = METER) -> float:
    """Sekunden pro Takt — zentrale Definition statt 15+ Kopien im Code.

    Audit 2026-07-17: mehrere Stellen umgingen METER mit hartkodierter 4.
    """
    if bpm <= 0:
        return 0.0
    return (60.0 / bpm) * meter


_CAMELOT_RE = re.compile(r"(1[0-2]|[1-9])([AB])")


def get_camelot_components(camelot_code: str) -> tuple[int, str]:
    """Parst einen Camelot-Code in (Nummer, Buchstabe); (0, "") bei ungueltig.

    Zentrale Definition — vorher identische Regexe in playlist und dj_brain.
    """
    match = _CAMELOT_RE.fullmatch(camelot_code or "")
    if match:
        return int(match.group(1)), match.group(2)
    return 0, ""


def effective_bpm_diff(bpm1: float, bpm2: float) -> tuple[float, str]:
    """Effektive BPM-Differenz mit Half/Double-Time-Erkennung.

    Zentrale Definition (Audit 2026-07-17) — vorher zwei divergierende Kopien:
    playlist respektierte BPM_HALF_DOUBLE_ENABLED, dj_brain ignorierte das Flag.

    Returns:
        (effektive_differenz, relation) mit relation in "direct"/"half"/"double"
    """
    if bpm1 <= 0 or bpm2 <= 0:
        return abs(bpm1 - bpm2), "direct"

    candidates = [
        (abs(bpm1 - bpm2), "direct"),
        (abs(bpm1 - bpm2 * 2), "half"),   # bpm2 ist Half-Time
        (abs(bpm1 * 2 - bpm2), "half"),   # bpm1 ist Half-Time
        (abs(bpm1 - bpm2 / 2), "double"), # bpm2 ist Double-Time
        (abs(bpm1 / 2 - bpm2), "double"), # bpm1 ist Double-Time
    ]

    if not BPM_HALF_DOUBLE_ENABLED:
        return candidates[0]

    return min(candidates, key=lambda x: x[0])


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

    # Advanced Frequency Bands
    avg_bass: float = 0.0
    avg_mids: float = 0.0
    avg_highs: float = 0.0

    # Structural Info
    mix_in_point: float = 0.0
    mix_out_point: float = 0.0

    # Mix Points in Bars (fuer DJ-Anzeige)
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
    brightness: int = 0  # Spektrale Helligkeit 0-100 (dunkel?hell)
    vocal_instrumental: str = "unknown"  # "vocal", "instrumental", "unknown"
    danceability: int = 0  # Tanzbarkeit 0-100
    spectral_flatness: float = 0.0
    percussive_ratio: float = 0.0
    mfcc_fingerprint: list = field(default_factory=list)  # MFCC-Vektor fuer Similarity
    timbre_fingerprint: list = field(default_factory=list)  # Gemittelter MFCC-Fingerabdruck
    ai_metadata: dict = field(default_factory=dict)  # LLM Analysis Results

def key_to_camelot(track: Track):
    """Assigns a Camelot code to a track based on its key."""
    if track.keyNote and track.keyMode:
        track.camelotCode = CAMELOT_MAP.get((track.keyNote, track.keyMode), "")

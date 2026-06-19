"""Test fixtures and generators for Harmonic Playlist Generator."""

from .audio_generators import (
    generate_click_track,
    generate_tone,
    generate_silence,
    generate_noise,
    generate_bass_tone,
    generate_track_with_structure,
    generate_major_chord,
    generate_minor_chord,
    NOTE_FREQUENCIES,
    DEFAULT_SR,
)
from .track_factories import (
    make_track,
    make_house_track,
    make_techno_track,
    make_dnb_track,
    make_minimal_track,
    make_dj_set,
)
from .camelot_test_data import (
    EXPECTED_CAMELOT_MAP,
    COMPATIBILITY_RULES,
    INCOMPATIBLE_PAIRS,
    BPM_TOLERANCE_CASES,
)

__all__ = [
    # Audio generators
    'generate_click_track',
    'generate_tone',
    'generate_silence',
    'generate_noise',
    'generate_bass_tone',
    'generate_track_with_structure',
    'generate_major_chord',
    'generate_minor_chord',
    'NOTE_FREQUENCIES',
    'DEFAULT_SR',
    # Track factories
    'make_track',
    'make_house_track',
    'make_techno_track',
    'make_dnb_track',
    'make_minimal_track',
    'make_dj_set',
    # Test data
    'EXPECTED_CAMELOT_MAP',
    'COMPATIBILITY_RULES',
    'INCOMPATIBLE_PAIRS',
    'BPM_TOLERANCE_CASES',
]

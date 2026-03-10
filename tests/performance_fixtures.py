"""
Performance-optimized test fixtures using caching.

Reduces test runtime by pre-caching expensive audio analysis operations.
Provides lightweight Track objects with pre-analyzed properties instead of
regenerating audio files and running librosa analysis on each test.

Usage:
  @pytest.mark.performance_optimized
  def test_something(cached_house_track):
      assert cached_house_track.bpm > 0
"""

import pytest
from pathlib import Path
from hpg_core.models import Track


# Cache directory for test data
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)


def _make_cached_track(name: str, **properties) -> Track:
    """Create a Track object with pre-analyzed properties."""
    return Track(
        filePath=f"<cached:{name}>",
        fileName=name,
        artist=properties.get("artist", "Unknown"),
        title=properties.get("title", name),
        genre=properties.get("genre", "Techno"),
        duration=properties.get("duration", 300.0),
        bpm=properties.get("bpm", 128.0),
        keyNote=properties.get("keyNote", "A"),
        keyMode=properties.get("keyMode", "Minor"),
        camelotCode=properties.get("camelotCode", "8A"),
        energy=int(properties.get("energy", 75)),
        bass_intensity=int(properties.get("bass_intensity", 65)),
        detected_genre=properties.get("detected_genre", "Techno"),
        genre_confidence=properties.get("genre_confidence", 0.75),
        sections=properties.get("sections", []),
        phrase_unit=properties.get("phrase_unit", 8),
    )


# ============================================================================
# HOUSE MUSIC FIXTURES (120-128 BPM)
# ============================================================================

@pytest.fixture
def cached_house_track():
    """Pre-cached House music track (128 BPM, A Minor)."""
    return _make_cached_track("house_128.mp3",
        duration=240.0,
        bpm=128.0,
        camelotCode="8A",
        keyNote="A",
        keyMode="Minor",
        energy=72,
        bass_intensity=68,
        genre="House",
        detected_genre="House",
        phrase_unit=8,
    )


@pytest.fixture
def cached_deep_house_track():
    """Pre-cached Deep House track (120 BPM, G Minor)."""
    return _make_cached_track("deep_house_120.mp3",
        duration=300.0,
        bpm=120.0,
        camelotCode="5A",
        keyNote="G",
        keyMode="Minor",
        energy=58,
        bass_intensity=62,
        genre="Deep House",
        phrase_unit=16,
    )


# ============================================================================
# TECHNO MUSIC FIXTURES (120-135 BPM)
# ============================================================================

@pytest.fixture
def cached_techno_track():
    """Pre-cached Techno track (130 BPM, E Minor)."""
    return _make_cached_track("techno_130.mp3",
        duration=360.0,
        bpm=130.0,
        camelotCode="9A",
        keyNote="E",
        keyMode="Minor",
        energy=85,
        bass_intensity=78,
        genre="Techno",
        detected_genre="Techno",
        phrase_unit=8,
    )


@pytest.fixture
def cached_minimal_techno_track():
    """Pre-cached Minimal Techno (125 BPM, E Minor)."""
    return _make_cached_track("minimal_125.mp3",
        duration=400.0,
        bpm=125.0,
        camelotCode="12A",
        keyNote="E",
        keyMode="Minor",
        energy=68,
        bass_intensity=71,
        genre="Minimal",
        phrase_unit=16,
    )


# ============================================================================
# DRUM & BASS FIXTURES (160-180 BPM)
# ============================================================================

@pytest.fixture
def cached_dnb_track():
    """Pre-cached Drum & Bass track (170 BPM, C Minor)."""
    return _make_cached_track("dnb_170.mp3",
        duration=240.0,
        bpm=170.0,
        camelotCode="4A",
        keyNote="C",
        keyMode="Minor",
        energy=92,
        bass_intensity=88,
        genre="Drum & Bass",
        detected_genre="Drum & Bass",
        phrase_unit=4,
    )


# ============================================================================
# MELODIC FIXTURES (DIFFERENT KEYS)
# ============================================================================

@pytest.fixture
def cached_track_c_major():
    """Pre-cached track in C Major (128 BPM)."""
    return _make_cached_track("c_major_128.mp3",
        duration=240.0,
        bpm=128.0,
        camelotCode="3B",
        keyNote="C",
        keyMode="Major",
        energy=75,
        bass_intensity=65,
        genre="Techno",
    )


@pytest.fixture
def cached_track_g_minor():
    """Pre-cached track in G Minor (120 BPM)."""
    return _make_cached_track("g_minor_120.mp3",
        duration=240.0,
        bpm=120.0,
        camelotCode="5A",
        keyNote="G",
        keyMode="Minor",
        energy=70,
        bass_intensity=60,
        genre="House",
    )


# ============================================================================
# ENERGY VARIATION FIXTURES
# ============================================================================

@pytest.fixture
def cached_low_energy_track():
    """Pre-cached ambient/low-energy track (100 BPM)."""
    return _make_cached_track("ambient_100.mp3",
        duration=480.0,
        bpm=100.0,
        camelotCode="12A",
        keyNote="E",
        keyMode="Minor",
        energy=35,
        bass_intensity=25,
        genre="Ambient",
        phrase_unit=32,
    )


@pytest.fixture
def cached_high_energy_track():
    """Pre-cached high-energy track (135 BPM)."""
    return _make_cached_track("hardcore_135.mp3",
        duration=200.0,
        bpm=135.0,
        camelotCode="1A",
        keyNote="B",
        keyMode="Minor",
        energy=95,
        bass_intensity=92,
        genre="Hardcore",
        phrase_unit=4,
    )


# ============================================================================
# BATCH FIXTURES (COLLECTIONS OF TRACKS)
# ============================================================================

@pytest.fixture
def cached_harmonic_set(
    cached_house_track,
    cached_track_c_major,
    cached_track_g_minor,
):
    """Pre-cached set of harmonically compatible tracks."""
    return [cached_house_track, cached_track_c_major, cached_track_g_minor]


@pytest.fixture
def cached_energy_progression(
    cached_low_energy_track,
    cached_deep_house_track,
    cached_house_track,
    cached_techno_track,
    cached_high_energy_track,
):
    """Pre-cached tracks in energy progression (low -> high)."""
    return [
        cached_low_energy_track,
        cached_deep_house_track,
        cached_house_track,
        cached_techno_track,
        cached_high_energy_track,
    ]


@pytest.fixture
def cached_bpm_progression():
    """Pre-cached tracks in BPM progression (100 -> 170 BPM)."""
    return [
        _make_cached_track("t1", bpm=100.0, camelotCode="12A"),
        _make_cached_track("t2", bpm=110.0, camelotCode="11A"),
        _make_cached_track("t3", bpm=120.0, camelotCode="5A"),
        _make_cached_track("t4", bpm=128.0, camelotCode="8A"),
        _make_cached_track("t5", bpm=135.0, camelotCode="1A"),
        _make_cached_track("t6", bpm=150.0, camelotCode="6A"),
        _make_cached_track("t7", bpm=170.0, camelotCode="4A"),
    ]

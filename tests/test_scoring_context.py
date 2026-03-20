import sys
import pytest
from unittest.mock import MagicMock, patch

# Mock out the difficult imports for this entire test module properly
# Note that we HAVE to mock before the import because of hpg_core package __init__ dependencies
mocks = {
    'numpy': MagicMock(),
    'soundfile': MagicMock(),
    'librosa': MagicMock(),
    'scipy': MagicMock(),
    'scipy.signal': MagicMock(),
    'mutagen': MagicMock(),
    'mutagen.mp3': MagicMock(),
    'mutagen.flac': MagicMock(),
    'mutagen.wave': MagicMock(),
    'mutagen.id3': MagicMock(),
    'librosa.display': MagicMock(),
    'scipy.spatial': MagicMock()
}
sys.modules.update(mocks)

from hpg_core.scoring_context import PlaylistContext
from hpg_core.models import Track

def teardown_module(module):
    """Clean up sys.modules modifications."""
    for mod in mocks:
        sys.modules.pop(mod, None)

@pytest.fixture
def empty_context():
    return PlaylistContext([], total_tracks=10)

@pytest.fixture
def sample_tracks():
    return [
        Track(filePath="1.mp3", fileName="1.mp3", energy=50, bpm=120, camelotCode="8A", detected_genre="House"),
        Track(filePath="2.mp3", fileName="2.mp3", energy=65, bpm=126, camelotCode="9A", detected_genre="House"),
        Track(filePath="3.mp3", fileName="3.mp3", energy=80, bpm=132, camelotCode="10A", detected_genre="Techno"),
    ]

@pytest.fixture
def populated_context(sample_tracks):
    return PlaylistContext(sample_tracks, total_tracks=10)

def test_get_playlist_phase():
    # Intro
    ctx = PlaylistContext([Track(filePath="1.mp3", fileName="1.mp3")] * 1, total_tracks=10)
    assert ctx.get_playlist_phase() == "INTRO"

    # Build-Up
    ctx = PlaylistContext([Track(filePath="1.mp3", fileName="1.mp3")] * 3, total_tracks=10)
    assert ctx.get_playlist_phase() == "BUILD_UP"

    # Peak
    ctx = PlaylistContext([Track(filePath="1.mp3", fileName="1.mp3")] * 6, total_tracks=10)
    assert ctx.get_playlist_phase() == "PEAK"

    # Outro
    ctx = PlaylistContext([Track(filePath="1.mp3", fileName="1.mp3")] * 9, total_tracks=10)
    assert ctx.get_playlist_phase() == "OUTRO"

def test_get_playlist_phase_undefined():
    ctx = PlaylistContext([], total_tracks=-1)
    ctx.total_tracks = 0
    assert ctx.get_playlist_phase() == "UNDEFINED"

def test_get_energy_trend(populated_context):
    assert populated_context.get_energy_trend() == "RISING"

    falling_tracks = [
        Track(filePath="1.mp3", fileName="1.mp3", energy=80),
        Track(filePath="2.mp3", fileName="2.mp3", energy=65),
        Track(filePath="3.mp3", fileName="3.mp3", energy=50),
    ]
    ctx = PlaylistContext(falling_tracks, total_tracks=10)
    assert ctx.get_energy_trend() == "FALLING"

    stable_tracks = [
        Track(filePath="1.mp3", fileName="1.mp3", energy=60),
        Track(filePath="2.mp3", fileName="2.mp3", energy=62),
        Track(filePath="3.mp3", fileName="3.mp3", energy=65), # change = 5
    ]
    ctx = PlaylistContext(stable_tracks, total_tracks=10)
    assert ctx.get_energy_trend() == "STABLE"

def test_get_energy_trend_undefined(empty_context):
    assert empty_context.get_energy_trend() == "UNDEFINED"

def test_get_genre_streak(populated_context):
    # Techno is the last one
    assert populated_context.get_genre_streak() == 1

    ctx = PlaylistContext(populated_context.playlist[:2], total_tracks=10)
    assert ctx.get_genre_streak() == 2

def test_get_genre_streak_empty(empty_context):
    assert empty_context.get_genre_streak() == 0

def test_get_camelot_stability(populated_context):
    # 8A to 9A (1) + 9A to 10A (1) = avg 1 (<2 -> TIGHT)
    assert populated_context.get_camelot_stability() == "TIGHT"

def test_get_camelot_stability_medium_loose():
    medium_tracks = [
        Track(filePath="1.mp3", fileName="1.mp3", camelotCode="8A"),
        Track(filePath="2.mp3", fileName="2.mp3", camelotCode="11A"), # dist = 3
    ]
    assert PlaylistContext(medium_tracks, total_tracks=10).get_camelot_stability() == "MEDIUM"

    loose_tracks = [
        Track(filePath="1.mp3", fileName="1.mp3", camelotCode="8A"),
        Track(filePath="2.mp3", fileName="2.mp3", camelotCode="2A"), # dist = 6
    ]
    assert PlaylistContext(loose_tracks, total_tracks=10).get_camelot_stability() == "LOOSE"

def test_get_camelot_stability_undefined(empty_context):
    assert empty_context.get_camelot_stability() == "UNDEFINED"

def test_get_bpm_trend(populated_context):
    assert populated_context.get_bpm_trend() == "ACCELERATING"

    decel_tracks = [
        Track(filePath="1.mp3", fileName="1.mp3", bpm=132),
        Track(filePath="2.mp3", fileName="2.mp3", bpm=126),
        Track(filePath="3.mp3", fileName="3.mp3", bpm=120),
    ]
    assert PlaylistContext(decel_tracks, total_tracks=10).get_bpm_trend() == "DECELERATING"

    stable_tracks = [
        Track(filePath="1.mp3", fileName="1.mp3", bpm=120),
        Track(filePath="2.mp3", fileName="2.mp3", bpm=122),
        Track(filePath="3.mp3", fileName="3.mp3", bpm=124), # diff = 4 <= 5
    ]
    assert PlaylistContext(stable_tracks, total_tracks=10).get_bpm_trend() == "STABLE"

def test_get_bpm_trend_undefined(empty_context):
    assert empty_context.get_bpm_trend() == "UNDEFINED"

def test_get_last_track_feature(populated_context):
    assert populated_context.get_last_track_feature("bpm") == 132
    assert populated_context.get_last_track_feature("energy") == 80
    assert populated_context.get_last_track_feature("nonexistent") is None

def test_get_last_track_feature_empty(empty_context):
    assert empty_context.get_last_track_feature("bpm") is None

def test_camelot_distance():
    assert PlaylistContext._camelot_distance("8A", "9A") == 1
    assert PlaylistContext._camelot_distance("8A", "7A") == 1
    assert PlaylistContext._camelot_distance("8A", "2A") == 6
    assert PlaylistContext._camelot_distance("8A", "8B") == 2
    assert PlaylistContext._camelot_distance("8A", "9B") == 3
    assert PlaylistContext._camelot_distance("12A", "1A") == 1

    # Invalid or unknown formats
    assert PlaylistContext._camelot_distance("", "9A") == 999
    assert PlaylistContext._camelot_distance("8A", None) == 999
    assert PlaylistContext._camelot_distance("XX", "9A") == 999

def test_repr(populated_context):
    r = repr(populated_context)
    assert "PlaylistContext" in r
    assert "position=3/10" in r
    assert "phase=BUILD_UP" in r
    assert "energy_trend=RISING" in r
    assert "genre_streak=1" in r

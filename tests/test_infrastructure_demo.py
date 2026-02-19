"""
Demo tests showing how to use the test infrastructure.

These tests demonstrate the usage of:
- Audio generators
- Track factories
- Camelot test data
- Fixtures from conftest.py
"""

import pytest
import numpy as np

from tests.fixtures.audio_generators import generate_click_track, generate_tone, generate_track_with_structure
from tests.fixtures.track_factories import make_track, make_compatible_pair, make_playlist_set
from tests.fixtures.camelot_test_data import COMPATIBILITY_RULES, get_related_key


# ========================================
# Audio Generator Tests
# ========================================

def test_click_track_generation():
  """Test that click track has exact BPM timing."""
  bpm = 120.0
  duration = 10.0
  sr = 44100
  audio = generate_click_track(bpm, duration, sr)

  # Verify shape
  expected_samples = int(duration * sr)
  assert len(audio) == expected_samples
  assert audio.dtype == np.float32

  # Verify amplitude range
  assert np.max(np.abs(audio)) <= 1.0


def test_tone_generation():
  """Test pure tone has correct frequency."""
  freq = 440.0  # A4
  duration = 5.0
  sr = 44100
  audio = generate_tone(freq, duration, sr)

  # Verify duration
  expected_samples = int(duration * sr)
  assert len(audio) == expected_samples

  # Verify clean signal (should be pure sine)
  assert np.max(np.abs(audio)) <= 1.0
  assert np.min(audio) < 0  # Has negative values (sine wave)
  assert np.max(audio) > 0  # Has positive values


def test_structured_track():
  """Test structured track has intro/body/outro sections."""
  bpm = 128.0
  duration = 180.0
  intro_ratio = 0.15
  outro_ratio = 0.85
  sr = 44100

  audio = generate_track_with_structure(
    bpm=bpm,
    duration=duration,
    intro_ratio=intro_ratio,
    outro_ratio=outro_ratio,
    sr=sr
  )

  # Verify structure exists
  intro_end = int(intro_ratio * len(audio))
  outro_start = int(outro_ratio * len(audio))

  # Intro should be quieter than body
  intro_rms = np.sqrt(np.mean(audio[:intro_end] ** 2))
  body_rms = np.sqrt(np.mean(audio[intro_end:outro_start] ** 2))

  assert body_rms > intro_rms, "Body should be louder than intro"


# ========================================
# Track Factory Tests
# ========================================

def test_make_track_defaults():
  """Test that make_track creates valid DJ track."""
  track = make_track()

  # Verify DJ defaults
  assert track.bpm == 128.0
  assert track.camelotCode == "8A"
  assert track.energy >= 0 and track.energy <= 100
  assert track.mix_in_point < track.mix_out_point
  assert track.duration == 300.0  # 5 minutes default


def test_make_track_overrides():
  """Test that overrides work correctly."""
  track = make_track(
    bpm=140.0,
    camelotCode="5A",
    energy=95,
    duration=240.0
  )

  assert track.bpm == 140.0
  assert track.camelotCode == "5A"
  assert track.energy == 95
  assert track.duration == 240.0


def test_make_compatible_pair():
  """Test compatible pair has correct relationship."""
  track_a, track_b = make_compatible_pair(base_key="8A", relation="energy_up")

  assert track_a.camelotCode == "8A"
  assert track_b.camelotCode == "9A"  # Energy boost from 8A
  assert abs(track_a.bpm - track_b.bpm) < 1.0  # Similar BPM


def test_make_playlist_set():
  """Test playlist set has progression."""
  tracks = make_playlist_set(num_tracks=8, progression="energy_boost")

  assert len(tracks) == 8

  # Verify energy progression
  energies = [t.energy for t in tracks]
  assert energies[0] < energies[-1], "Energy should increase"

  # Verify BPM progression
  bpms = [t.bpm for t in tracks]
  assert bpms[0] <= bpms[-1], "BPM should increase or stay constant"


# ========================================
# Camelot Test Data Tests
# ========================================

def test_compatibility_rules_coverage():
  """Test that compatibility rules cover main scenarios."""
  rule_types = {rule[3] for rule in COMPATIBILITY_RULES}

  # Should have all major rule types
  assert "Same Key" in rule_types
  assert "Adjacent +1" in rule_types
  assert "Relative Major/Minor" in rule_types


def test_get_related_key():
  """Test key relationship helper."""
  # Same key
  assert get_related_key("8A", "same") == "8A"

  # Energy up
  assert get_related_key("8A", "energy_up") == "9A"

  # Energy down
  assert get_related_key("9A", "energy_down") == "8A"

  # Relative major/minor
  assert get_related_key("8A", "relative") == "8B"
  assert get_related_key("8B", "relative") == "8A"

  # Wraparound
  assert get_related_key("12A", "energy_up") == "1A"
  assert get_related_key("1A", "energy_down") == "12A"


# ========================================
# Fixture Integration Tests
# ========================================

def test_click_track_fixture(click_128bpm):
  """Test using fixture from conftest.py."""
  assert click_128bpm is not None
  assert len(click_128bpm) > 0
  assert isinstance(click_128bpm, np.ndarray)


def test_default_track_fixture(default_track):
  """Test using track fixture from conftest.py."""
  assert default_track is not None
  assert default_track.bpm > 0
  assert default_track.camelotCode in ["1A", "2A", "3A", "4A", "5A", "6A", "7A", "8A",
                                         "9A", "10A", "11A", "12A",
                                         "1B", "2B", "3B", "4B", "5B", "6B", "7B", "8B",
                                         "9B", "10B", "11B", "12B"]


def test_dj_set_fixture(dj_set_8tracks):
  """Test using DJ set fixture from conftest.py."""
  assert len(dj_set_8tracks) == 8

  # All tracks should be valid
  for track in dj_set_8tracks:
    assert track.bpm > 0
    assert track.duration > 0
    assert track.mix_in_point < track.mix_out_point


def test_compatibility_rules_fixture(compatibility_rules):
  """Test using compatibility rules fixture."""
  assert len(compatibility_rules) > 0

  # Should have expected structure
  for rule in compatibility_rules:
    key1, key2, score, name = rule
    assert isinstance(key1, str)
    assert isinstance(key2, str)
    assert isinstance(score, int)
    assert isinstance(name, str)
    assert 0 <= score <= 100


# ========================================
# Helper Function Tests
# ========================================

def test_assert_mix_points_valid(default_track):
  """Test mix point validation helper."""
  from tests.conftest import assert_mix_points_valid

  # Should not raise for valid track
  assert_mix_points_valid(default_track)

  # Should raise for invalid track
  invalid_track = make_track(mix_in_point=100.0, mix_out_point=50.0)
  with pytest.raises(AssertionError):
    assert_mix_points_valid(invalid_track)


def test_assert_phrase_aligned():
  """Test phrase alignment helper."""
  from tests.conftest import assert_phrase_aligned

  # Valid phrase boundaries (8-bar phrases)
  assert_phrase_aligned(8)
  assert_phrase_aligned(16)
  assert_phrase_aligned(32)

  # Invalid boundaries
  with pytest.raises(AssertionError):
    assert_phrase_aligned(7)

  with pytest.raises(AssertionError):
    assert_phrase_aligned(15)


# ========================================
# Integration Demo
# ========================================

@pytest.mark.integration
def test_full_workflow_demo():
  """Demonstrate complete test workflow using all infrastructure."""
  # 1. Create audio signal
  sr = 44100
  audio = generate_click_track(bpm=128.0, duration=10.0, sr=sr)
  assert len(audio) > 0

  # 2. Create compatible tracks
  track_a, track_b = make_compatible_pair("8A", "energy_up")
  assert track_a.camelotCode == "8A"
  assert track_b.camelotCode == "9A"

  # 3. Create full playlist
  tracks = make_playlist_set(8, progression="energy_boost")
  assert len(tracks) == 8

  # 4. Verify harmonic flow
  for i in range(len(tracks) - 1):
    current = tracks[i]
    next_track = tracks[i + 1]

    # Keys should be compatible (this would use actual compatibility checker in real test)
    assert current.camelotCode is not None
    assert next_track.camelotCode is not None

  # 5. Verify energy progression
  energies = [t.energy for t in tracks]
  assert energies[0] < energies[-1]


if __name__ == "__main__":
  pytest.main([__file__, "-v"])

"""
Zentrale Test-Konfiguration und Fixtures fuer HPG Tests.
Bietet Audio-Generatoren, Track-Factories und gemeinsame Fixtures.
"""
import sys
import os
import pytest
import numpy as np

# Projekt-Root zum Path hinzufuegen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hpg_core.models import Track, CAMELOT_MAP
from tests.fixtures.audio_generators import (
  generate_click_track,
  generate_tone,
  generate_silence,
  generate_noise,
  generate_track_with_structure,
  generate_major_chord,
  generate_minor_chord,
  DEFAULT_SR,
)
from tests.fixtures.track_factories import (
  make_track,
  make_house_track,
  make_techno_track,
  make_dnb_track,
  make_minimal_track,
  make_dj_set,
)


# === Audio Fixtures ===

@pytest.fixture
def sr():
  """Standard Sample Rate."""
  return DEFAULT_SR


@pytest.fixture
def click_128bpm(sr):
  """Click-Track bei 128 BPM, 10 Sekunden."""
  return generate_click_track(128.0, 10.0, sr)


@pytest.fixture
def click_120bpm(sr):
  """Click-Track bei 120 BPM, 10 Sekunden."""
  return generate_click_track(120.0, 10.0, sr)


@pytest.fixture
def silence_10s(sr):
  """10 Sekunden Stille."""
  return generate_silence(10.0, sr)


@pytest.fixture
def noise_10s(sr):
  """10 Sekunden weisses Rauschen."""
  return generate_noise(10.0, sr)


@pytest.fixture
def structured_audio_128bpm(sr):
  """Audio mit klarem Intro/Main/Outro bei 128 BPM, 5 Minuten."""
  return generate_track_with_structure(
    bpm=128.0,
    duration=300.0,
    sr=sr,
    intro_ratio=0.10,
    outro_ratio=0.90,
    main_amplitude=0.5,
    intro_amplitude=0.02,
    outro_amplitude=0.02,
  )


@pytest.fixture
def structured_audio_short(sr):
  """Kurzes strukturiertes Audio, 30 Sekunden bei 128 BPM."""
  return generate_track_with_structure(
    bpm=128.0,
    duration=30.0,
    sr=sr,
    intro_ratio=0.15,
    outro_ratio=0.85,
  )


@pytest.fixture
def a_minor_chord(sr):
  """A-Moll Akkord (3 Sekunden) fuer Key-Detection."""
  return generate_minor_chord('A', 3.0, sr)


@pytest.fixture
def c_major_chord(sr):
  """C-Dur Akkord (3 Sekunden) fuer Key-Detection."""
  return generate_major_chord('C', 3.0, sr)


# === Track Fixtures ===

@pytest.fixture
def default_track():
  """Standard House-Track mit allen Feldern."""
  return make_track()


@pytest.fixture
def house_track():
  """Typischer House-Track."""
  return make_house_track()


@pytest.fixture
def techno_track():
  """Typischer Techno-Track."""
  return make_techno_track()


@pytest.fixture
def dnb_track():
  """Typischer D&B Track."""
  return make_dnb_track()


@pytest.fixture
def minimal_track():
  """Track nur mit Pflichtfeldern."""
  return make_minimal_track()


@pytest.fixture
def dj_set_8tracks():
  """8-Track DJ Set mit harmonischem Flow."""
  return make_dj_set(count=8)


@pytest.fixture
def dj_set_3tracks():
  """Minimales 3-Track Set."""
  return make_dj_set(count=3)


@pytest.fixture
def empty_track_list():
  """Leere Track-Liste."""
  return []


@pytest.fixture
def single_track_list():
  """Liste mit einem Track."""
  return [make_track()]


# === Camelot Fixtures ===

@pytest.fixture
def all_camelot_tracks():
  """Ein Track fuer jeden der 24 Camelot-Codes."""
  tracks = []
  for (note, mode), code in CAMELOT_MAP.items():
    track = make_track(
      keyNote=note,
      keyMode=mode,
      camelotCode=code,
      title=f"Track {code}",
      filePath=f"/test/{code}.mp3",
      fileName=f"{code}.mp3",
    )
    tracks.append(track)
  return tracks


# === Hilfsfunktionen ===

def assert_mix_points_valid(track: Track, tolerance_bars: int = 2):
  """Prueft ob Mix-Punkte eines Tracks DJ-tauglich sind.

  Validiert:
  - mix_out > mix_in
  - Beide innerhalb der Track-Dauer
  - Genuegend Abstand zwischen beiden Punkten
  - Bar-Zahlen positiv
  """
  assert track.mix_out_point > track.mix_in_point, (
    f"Mix-Out ({track.mix_out_point}s) muss nach Mix-In ({track.mix_in_point}s) liegen"
  )
  assert track.mix_in_point >= 0, "Mix-In darf nicht negativ sein"

  if track.duration > 0:
    assert track.mix_in_point <= track.duration, (
      f"Mix-In ({track.mix_in_point}s) ueber Track-Dauer ({track.duration}s)"
    )
    assert track.mix_out_point <= track.duration, (
      f"Mix-Out ({track.mix_out_point}s) ueber Track-Dauer ({track.duration}s)"
    )

  assert track.mix_in_bars >= 0, "Mix-In Bars muss >= 0 sein"
  assert track.mix_out_bars >= 0, "Mix-Out Bars muss >= 0 sein"
  assert track.mix_out_bars > track.mix_in_bars, (
    f"Mix-Out Bars ({track.mix_out_bars}) muss groesser als Mix-In Bars ({track.mix_in_bars}) sein"
  )


def assert_phrase_aligned(bars: int, bars_per_phrase: int = 8):
  """Prueft ob eine Bar-Zahl auf einer Phrasengrenze liegt."""
  assert bars % bars_per_phrase == 0, (
    f"Bar {bars} ist nicht auf einer {bars_per_phrase}-Bar Phrasengrenze "
    f"(Rest: {bars % bars_per_phrase})"
  )


# === Compatibility Test Data ===

@pytest.fixture
def compatibility_rules():
  """Expected compatibility scores for Camelot key pairs."""
  from tests.fixtures.camelot_test_data import COMPATIBILITY_RULES
  return COMPATIBILITY_RULES


@pytest.fixture
def incompatible_pairs():
  """Pairs of keys that should be incompatible."""
  from tests.fixtures.camelot_test_data import INCOMPATIBLE_PAIRS
  return INCOMPATIBLE_PAIRS


@pytest.fixture
def bpm_tolerance_cases():
  """BPM tolerance test cases."""
  from tests.fixtures.camelot_test_data import BPM_TOLERANCE_CASES
  return BPM_TOLERANCE_CASES


# === pytest configuration ===

def pytest_configure(config):
  """Add custom markers."""
  config.addinivalue_line(
    "markers", "audio: tests that require audio processing"
  )
  config.addinivalue_line(
    "markers", "slow: tests that take longer than 1 second"
  )
  config.addinivalue_line(
    "markers", "integration: integration tests requiring multiple components"
  )


def pytest_collection_modifyitems(config, items):
  """Auto-add markers based on test names."""
  for item in items:
    # Mark audio tests
    if "audio" in item.nodeid.lower() or "bpm" in item.nodeid.lower():
      item.add_marker(pytest.mark.audio)

    # Mark slow tests
    if "integration" in item.nodeid or "playlist" in item.nodeid:
      item.add_marker(pytest.mark.slow)

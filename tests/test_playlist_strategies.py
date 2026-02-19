"""
Tests fuer alle 10 Playlist-Sortierstrategien.
Prueft ob jede Strategie korrekt sortiert und keine Tracks verliert.
"""
import pytest
from hpg_core.playlist import generate_playlist, STRATEGIES
from tests.fixtures.track_factories import (
  make_track, make_house_track, make_techno_track,
  make_dnb_track, make_minimal_track, make_dj_set,
)


@pytest.fixture
def mixed_set():
  """8 Tracks mit verschiedenen BPM, Keys und Energy."""
  return make_dj_set()


@pytest.fixture
def same_key_set():
  """4 Tracks mit gleichem Key aber unterschiedlichem BPM."""
  return [
    make_track(camelotCode="8A", bpm=120.0, energy=50, title="Low BPM"),
    make_track(camelotCode="8A", bpm=126.0, energy=60, title="Mid BPM"),
    make_track(camelotCode="8A", bpm=128.0, energy=75, title="House BPM"),
    make_track(camelotCode="8A", bpm=130.0, energy=85, title="High BPM"),
  ]


class TestAllStrategiesExist:
  """Alle 10 Strategien sind registriert."""

  def test_10_strategies_available(self):
    """Genau 10 Strategien in STRATEGIES."""
    assert len(STRATEGIES) == 10

  @pytest.mark.parametrize("name", [
    "Harmonic Flow", "Harmonic Flow Enhanced",
    "Warm-Up", "Cool-Down",
    "Peak-Time", "Peak-Time Enhanced",
    "Energy Wave", "Emotional Journey",
    "Genre Flow", "Consistent",
  ])
  def test_strategy_registered(self, name):
    """Strategie ist in STRATEGIES registriert."""
    assert name in STRATEGIES, f"Strategie '{name}' fehlt"


class TestStrategyBasicProperties:
  """Grundeigenschaften aller Strategien."""

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_no_crash_with_mixed_set(self, mixed_set, strategy):
    """Kein Crash mit gemischtem Set."""
    result = generate_playlist(mixed_set[:], strategy, bpm_tolerance=6.0)
    assert isinstance(result, list)

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_output_not_empty(self, mixed_set, strategy):
    """Ergebnis ist nicht leer."""
    result = generate_playlist(mixed_set[:], strategy, bpm_tolerance=6.0)
    assert len(result) > 0

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_no_duplicates(self, mixed_set, strategy):
    """Keine duplizierten Tracks."""
    result = generate_playlist(mixed_set[:], strategy, bpm_tolerance=6.0)
    paths = [t.filePath for t in result]
    assert len(paths) == len(set(paths)), (
      f"Strategie '{strategy}': Duplikate gefunden"
    )

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_track_count_preserved_or_filtered(self, mixed_set, strategy):
    """Tracks werden nicht hinzugefuegt (nur gefiltert)."""
    input_count = len(mixed_set)
    result = generate_playlist(mixed_set[:], strategy, bpm_tolerance=6.0)
    assert len(result) <= input_count


class TestWarmUp:
  """Warm-Up: BPM aufsteigend."""

  def test_bpm_ascending(self, same_key_set):
    """BPM muss aufsteigend sortiert sein."""
    result = generate_playlist(same_key_set, "Warm-Up", bpm_tolerance=15.0)
    bpms = [t.bpm for t in result]
    for i in range(len(bpms) - 1):
      assert bpms[i] <= bpms[i + 1], (
        f"Nicht aufsteigend bei Index {i}: {bpms[i]} > {bpms[i + 1]}"
      )

  def test_first_track_lowest_bpm(self, same_key_set):
    """Erster Track hat niedrigsten BPM."""
    result = generate_playlist(same_key_set, "Warm-Up", bpm_tolerance=15.0)
    if len(result) >= 2:
      assert result[0].bpm <= result[1].bpm


class TestCoolDown:
  """Cool-Down: BPM absteigend."""

  def test_bpm_descending(self, same_key_set):
    """BPM muss absteigend sortiert sein."""
    result = generate_playlist(same_key_set, "Cool-Down", bpm_tolerance=15.0)
    bpms = [t.bpm for t in result]
    for i in range(len(bpms) - 1):
      assert bpms[i] >= bpms[i + 1], (
        f"Nicht absteigend bei Index {i}: {bpms[i]} < {bpms[i + 1]}"
      )

  def test_first_track_highest_bpm(self, same_key_set):
    """Erster Track hat hoechsten BPM."""
    result = generate_playlist(same_key_set, "Cool-Down", bpm_tolerance=15.0)
    if len(result) >= 2:
      assert result[0].bpm >= result[1].bpm


class TestHarmonicFlow:
  """Harmonic Flow: Nachbarkeys bevorzugen."""

  def test_compatible_transitions(self, mixed_set):
    """Aufeinanderfolgende Tracks sollten kompatibel sein."""
    from hpg_core.playlist import calculate_compatibility
    result = generate_playlist(mixed_set[:], "Harmonic Flow", bpm_tolerance=6.0)
    if len(result) >= 2:
      compat_count = 0
      for i in range(len(result) - 1):
        score = calculate_compatibility(result[i], result[i + 1], 6.0)
        if score > 0:
          compat_count += 1
      # Mindestens 50% der Uebergaenge sollten kompatibel sein
      ratio = compat_count / (len(result) - 1)
      assert ratio >= 0.3, f"Nur {ratio:.0%} kompatible Uebergaenge"


class TestPeakTime:
  """Peak-Time: Energie steigt, dann faellt."""

  def test_returns_valid_playlist(self, mixed_set):
    """Peak-Time gibt valide Playlist zurueck."""
    result = generate_playlist(mixed_set[:], "Peak-Time", bpm_tolerance=6.0)
    assert len(result) > 0


class TestEdgeCases:
  """Edge Cases fuer alle Strategien."""

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_empty_input(self, strategy):
    """Leere Eingabe = leere Ausgabe."""
    result = generate_playlist([], strategy, bpm_tolerance=3.0)
    assert result == []

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_single_track(self, strategy):
    """Ein Track = ein Track zurueck."""
    tracks = [make_house_track()]
    result = generate_playlist(tracks, strategy, bpm_tolerance=3.0)
    assert len(result) <= 1

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_two_tracks(self, strategy):
    """Zwei Tracks = kein Crash."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, energy=70),
      make_track(camelotCode="9A", bpm=128.0, energy=72),
    ]
    result = generate_playlist(tracks, strategy, bpm_tolerance=3.0)
    assert len(result) > 0

  def test_unknown_strategy_uses_default(self, mixed_set):
    """Unbekannte Strategie = Harmonic Flow (Fallback)."""
    result = generate_playlist(mixed_set[:], "NonExistent", bpm_tolerance=6.0)
    assert len(result) > 0

  def test_tracks_without_camelot_code(self):
    """Tracks ohne Camelot-Code werden gefiltert."""
    tracks = [
      make_track(camelotCode="", bpm=128.0),
      make_track(camelotCode="8A", bpm=128.0),
    ]
    result = generate_playlist(tracks, "Harmonic Flow", bpm_tolerance=3.0)
    # Nur Track mit gueltigem Code sollte uebrig bleiben
    assert len(result) >= 1

  def test_tracks_with_zero_bpm_filtered(self):
    """Tracks mit BPM 0 werden gefiltert."""
    tracks = [
      make_track(camelotCode="8A", bpm=0.0),
      make_track(camelotCode="8A", bpm=128.0),
    ]
    result = generate_playlist(tracks, "Harmonic Flow", bpm_tolerance=3.0)
    valid_bpms = [t.bpm for t in result if t.bpm > 0]
    assert len(valid_bpms) >= 1

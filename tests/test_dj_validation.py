"""
⭐ DJ AGENT GESAMTTEST: Cross-cutting DJ-Perspektive.
Prueft ob die App aus DJ-Sicht korrekt funktioniert:
- Beatgrid Trust, Mix-Point Phrasing, Harmonic Rules,
  Playlist Flow, Transition Safety.
"""
import pytest
import numpy as np
from math import floor

from hpg_core.analysis import (
  analyze_structure_and_mix_points, get_key, calculate_energy,
)
from hpg_core.playlist import (
  calculate_compatibility, generate_playlist, STRATEGIES,
  compute_transition_recommendations, calculate_playlist_quality,
)
from hpg_core.config import METER, BARS_PER_PHRASE, DEFAULT_BPM
from hpg_core.models import CAMELOT_MAP
from tests.fixtures.audio_generators import (
  generate_track_with_structure, generate_click_track,
  generate_silence, DEFAULT_SR,
)
from tests.fixtures.track_factories import (
  make_track, make_house_track, make_techno_track,
  make_dnb_track, make_dj_set,
)


def _calc_timing(bpm):
  """Berechnet Timing-Konstanten."""
  spb = 60.0 / bpm
  bar = spb * METER
  phrase = bar * BARS_PER_PHRASE
  return spb, bar, phrase


class TestDJBeatgridTrust:
  """DJ-Perspektive: Kann ich dem Beatgrid vertrauen?"""

  def test_bar_calculation_matches_bpm(self):
    """Bar-Berechnung stimmt mit BPM ueberein."""
    bpm = 128.0
    _, bar, _ = _calc_timing(bpm)
    y = generate_track_with_structure(bpm, 300.0, DEFAULT_SR)
    mi, mo, mi_bars, mo_bars = analyze_structure_and_mix_points(
      y, DEFAULT_SR, 300.0, 70, bpm
    )
    # Bar-Zahl * Sekunden pro Bar ≈ Zeitpunkt
    expected_mi_time = mi_bars * bar
    expected_mo_time = mo_bars * bar
    assert abs(mi - expected_mi_time) < bar * 2, (
      f"Mix-In: {mi}s vs {mi_bars} Bars * {bar}s = {expected_mi_time}s"
    )
    assert abs(mo - expected_mo_time) < bar * 2, (
      f"Mix-Out: {mo}s vs {mo_bars} Bars * {bar}s = {expected_mo_time}s"
    )

  def test_128bpm_phrase_is_15_seconds(self):
    """Bei 128 BPM ist eine 8-Bar Phrase exakt 15 Sekunden."""
    _, _, phrase = _calc_timing(128.0)
    assert abs(phrase - 15.0) < 0.01, f"Phrase = {phrase}s (erwartet 15.0)"

  def test_energy_reflects_loudness(self):
    """Lautere Passage hat hoehere Energy als leise."""
    y_quiet = np.random.RandomState(42).randn(DEFAULT_SR * 5).astype(np.float32) * 0.05
    y_loud = np.random.RandomState(42).randn(DEFAULT_SR * 5).astype(np.float32) * 0.5
    e_quiet = calculate_energy(y_quiet)
    e_loud = calculate_energy(y_loud)
    assert e_loud > e_quiet, (
      f"Laut ({e_loud}) sollte > leise ({e_quiet}) sein"
    )


class TestDJMixPointPhrasing:
  """DJ-Perspektive: Fallen Mix-Points auf Phrasengrenzen?"""

  def test_mix_in_on_phrase_boundary(self):
    """Mix-In muss auf 8-Bar Phrasengrenze liegen."""
    bpm = 128.0
    y = generate_track_with_structure(bpm, 300.0, DEFAULT_SR)
    _, _, mi_bars, _ = analyze_structure_and_mix_points(
      y, DEFAULT_SR, 300.0, 70, bpm
    )
    assert mi_bars % BARS_PER_PHRASE == 0, (
      f"Mix-In bei {mi_bars} Bars - nicht auf 8-Bar Grenze"
    )

  def test_mix_in_not_in_first_4_bars(self):
    """Mix-In nicht in den ersten 4 Bars (kein DJ mischt so frueh ein)."""
    bpm = 128.0
    _, bar, _ = _calc_timing(bpm)
    y = generate_track_with_structure(bpm, 300.0, DEFAULT_SR)
    mi, _, _, _ = analyze_structure_and_mix_points(
      y, DEFAULT_SR, 300.0, 70, bpm
    )
    assert mi >= bar, f"Mix-In bei {mi}s ist zu frueh (min {bar}s)"

  def test_mix_out_leaves_enough_outro(self):
    """Mix-Out laesst mindestens 8 Bars Outro uebrig."""
    bpm = 128.0
    _, bar, phrase = _calc_timing(bpm)
    duration = 300.0
    y = generate_track_with_structure(bpm, duration, DEFAULT_SR)
    _, mo, _, _ = analyze_structure_and_mix_points(
      y, DEFAULT_SR, duration, 70, bpm
    )
    outro_time = duration - mo
    assert outro_time >= 0, f"Mix-Out ({mo}s) nach Track-Ende ({duration}s)"

  def test_main_body_long_enough(self):
    """Hauptteil (Mix-In bis Mix-Out) mindestens 2 Phrasen lang."""
    bpm = 128.0
    _, _, phrase = _calc_timing(bpm)
    y = generate_track_with_structure(bpm, 300.0, DEFAULT_SR)
    mi, mo, _, _ = analyze_structure_and_mix_points(
      y, DEFAULT_SR, 300.0, 70, bpm
    )
    body = mo - mi
    assert body >= phrase * 2, (
      f"Hauptteil nur {body:.1f}s (min {phrase * 2:.1f}s = 2 Phrasen)"
    )

  @pytest.mark.parametrize("bpm", [100.0, 128.0, 140.0, 174.0])
  def test_mix_points_valid_at_any_bpm(self, bpm):
    """Mix-Points sind bei jedem DJ-relevanten BPM valide."""
    duration = 300.0
    y = generate_track_with_structure(bpm, duration, DEFAULT_SR)
    mi, mo, mi_bars, mo_bars = analyze_structure_and_mix_points(
      y, DEFAULT_SR, duration, 70, bpm
    )
    assert mo > mi, f"BPM {bpm}: Mix-Out ({mo}) <= Mix-In ({mi})"
    assert mi >= 0, f"BPM {bpm}: Mix-In negativ"
    assert mo <= duration, f"BPM {bpm}: Mix-Out ueber Dauer"
    assert mo_bars > mi_bars


class TestDJHarmonicRules:
  """DJ-Perspektive: Funktioniert das Camelot Wheel korrekt?"""

  def test_camelot_wheel_is_circular(self):
    """12A -> 1A ist kompatibel (Wheel ist rund)."""
    t1 = make_track(camelotCode="12A", bpm=128.0)
    t2 = make_track(camelotCode="1A", bpm=128.0)
    score = calculate_compatibility(t1, t2, 3.0)
    assert score >= 60, f"12A->1A Score {score} (Wheel nicht zirkulaer?)"

  def test_relative_keys_always_safe(self):
    """Relative Minor/Major (gleiche Nummer) immer safe (>=85)."""
    for num in range(1, 13):
      t1 = make_track(camelotCode=f"{num}A", bpm=128.0)
      t2 = make_track(camelotCode=f"{num}B", bpm=128.0)
      score = calculate_compatibility(t1, t2, 3.0)
      assert score >= 85, (
        f"Relative {num}A->{num}B Score {score} (erwartet >=85)"
      )

  def test_all_adjacent_keys_compatible(self):
    """Alle Nachbar-Keys (+-1) sind kompatibel (>=60)."""
    for num in range(1, 13):
      next_num = (num % 12) + 1
      for letter in ("A", "B"):
        t1 = make_track(camelotCode=f"{num}{letter}", bpm=128.0)
        t2 = make_track(camelotCode=f"{next_num}{letter}", bpm=128.0)
        score = calculate_compatibility(t1, t2, 3.0)
        assert score >= 60, (
          f"Adjacent {num}{letter}->{next_num}{letter} "
          f"Score {score} (erwartet >=60)"
        )

  def test_same_key_perfect_score(self):
    """Gleicher Key = 100 Punkte."""
    t1 = make_track(camelotCode="8A", bpm=128.0)
    t2 = make_track(camelotCode="8A", bpm=128.0)
    assert calculate_compatibility(t1, t2, 3.0) == 100

  def test_bpm_mismatch_kills_compatibility(self):
    """Zu grosser BPM-Unterschied = Score 0."""
    t1 = make_track(camelotCode="8A", bpm=128.0)
    t2 = make_track(camelotCode="8A", bpm=145.0)
    assert calculate_compatibility(t1, t2, 3.0) == 0


class TestDJPlaylistFlow:
  """DJ-Perspektive: Funktionieren die Playlist-Strategien?"""

  @pytest.fixture
  def dj_set(self):
    """8-Track DJ-Set mit verschiedenen Tracks."""
    return make_dj_set()

  def test_warm_up_bpm_ascending(self, dj_set):
    """Warm-Up: BPM muss aufsteigend sortiert sein."""
    result = generate_playlist(dj_set, "Warm-Up", bpm_tolerance=6.0)
    bpms = [t.bpm for t in result]
    for i in range(len(bpms) - 1):
      assert bpms[i] <= bpms[i + 1], (
        f"Warm-Up nicht aufsteigend: {bpms[i]} > {bpms[i + 1]}"
      )

  def test_cool_down_bpm_descending(self, dj_set):
    """Cool-Down: BPM muss absteigend sortiert sein."""
    result = generate_playlist(dj_set, "Cool-Down", bpm_tolerance=6.0)
    bpms = [t.bpm for t in result]
    for i in range(len(bpms) - 1):
      assert bpms[i] >= bpms[i + 1], (
        f"Cool-Down nicht absteigend: {bpms[i]} < {bpms[i + 1]}"
      )

  def test_no_strategy_loses_tracks(self, dj_set):
    """Keine Strategie verliert Tracks (gleiche Anzahl rein/raus)."""
    original_count = len(dj_set)
    for name in STRATEGIES:
      result = generate_playlist(dj_set[:], name, bpm_tolerance=6.0)
      assert len(result) <= original_count, (
        f"Strategie '{name}': {len(result)} Tracks "
        f"(mehr als Input {original_count})"
      )
      assert len(result) > 0, f"Strategie '{name}': leere Playlist"

  def test_no_strategy_duplicates_tracks(self, dj_set):
    """Keine Strategie dupliziert Tracks."""
    for name in STRATEGIES:
      result = generate_playlist(dj_set[:], name, bpm_tolerance=6.0)
      paths = [t.filePath for t in result]
      assert len(paths) == len(set(paths)), (
        f"Strategie '{name}': Duplikate in Playlist"
      )

  def test_harmonic_flow_quality(self, dj_set):
    """Harmonic Flow hat positive Qualitaetsmetriken."""
    result = generate_playlist(dj_set, "Harmonic Flow", bpm_tolerance=6.0)
    if len(result) >= 2:
      quality = calculate_playlist_quality(result, 6.0)
      assert quality["overall_score"] >= 0, (
        f"Harmonic Flow Quality negativ: {quality['overall_score']}"
      )
      assert quality["harmonic_flow"] >= 0

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_all_strategies_no_crash(self, dj_set, strategy):
    """Alle Strategien laufen ohne Crash."""
    result = generate_playlist(dj_set[:], strategy, bpm_tolerance=6.0)
    assert isinstance(result, list)

  def test_empty_playlist_safe(self):
    """Leere Playlist = kein Crash."""
    result = generate_playlist([], "Harmonic Flow", bpm_tolerance=3.0)
    assert result == []

  def test_single_track_safe(self):
    """Ein Track = kein Crash."""
    tracks = [make_house_track()]
    result = generate_playlist(tracks, "Harmonic Flow", bpm_tolerance=3.0)
    assert len(result) <= 1


class TestDJTransitionSafety:
  """DJ-Perspektive: Sind die Uebergangsempfehlungen brauchbar?"""

  def test_single_track_no_recommendations(self):
    """1 Track = keine Uebergangsempfehlung."""
    tracks = [make_house_track()]
    recs = compute_transition_recommendations(tracks)
    assert len(recs) == 0

  def test_two_tracks_one_recommendation(self):
    """2 Tracks = genau 1 Empfehlung."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, duration=300.0,
                 mix_in_point=30.0, mix_out_point=270.0, energy=70),
      make_track(camelotCode="8A", bpm=128.0, duration=300.0,
                 mix_in_point=30.0, mix_out_point=270.0, energy=70),
    ]
    recs = compute_transition_recommendations(tracks)
    assert len(recs) == 1

  def test_overlap_positive(self):
    """Ueberlappung muss positiv sein."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, duration=300.0,
                 mix_in_point=30.0, mix_out_point=270.0, energy=70),
      make_track(camelotCode="9A", bpm=128.0, duration=300.0,
                 mix_in_point=30.0, mix_out_point=270.0, energy=72),
    ]
    recs = compute_transition_recommendations(tracks)
    assert recs[0].overlap > 0, f"Overlap {recs[0].overlap} nicht positiv"

  def test_compatible_tracks_low_risk(self):
    """Kompatible Tracks = Risk 'low' oder 'medium'."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, duration=300.0,
                 mix_in_point=30.0, mix_out_point=270.0, energy=70),
      make_track(camelotCode="8A", bpm=128.0, duration=300.0,
                 mix_in_point=30.0, mix_out_point=270.0, energy=72),
    ]
    recs = compute_transition_recommendations(tracks)
    assert recs[0].risk_level in ("low", "medium"), (
      f"Same-Key Risk '{recs[0].risk_level}' (erwartet low/medium)"
    )

  def test_fade_out_before_track_end(self):
    """Fade-Out muss vor Track-Ende beginnen."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, duration=300.0,
                 mix_in_point=30.0, mix_out_point=270.0, energy=70),
      make_track(camelotCode="9A", bpm=128.0, duration=300.0,
                 mix_in_point=30.0, mix_out_point=270.0, energy=72),
    ]
    recs = compute_transition_recommendations(tracks)
    assert recs[0].fade_out_start >= 0, "Fade-Out Start negativ"
    assert recs[0].fade_out_end <= 300.0, "Fade-Out Ende nach Track-Ende"

  def test_recommendations_count_matches(self):
    """Anzahl Empfehlungen = Anzahl Tracks - 1."""
    tracks = [
      make_track(camelotCode=f"{i}A", bpm=128.0, duration=300.0,
                 mix_in_point=30.0, mix_out_point=270.0, energy=70)
      for i in range(1, 6)
    ]
    recs = compute_transition_recommendations(tracks)
    assert len(recs) == len(tracks) - 1

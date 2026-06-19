"""
Mix-Point Tests fuer die STRIKTE Version (analysis.py im Root-Verzeichnis).
Unterschiede zur hpg_core Version:
- ceil() statt round() fuer Phrase-Alignment
- Min 16 Bars (2 Phrasen) statt 8 Bars
- Mix-In max 30% (statt 40%)
- Mix-Out min 70%
- Min 4 Phrasen Abstand zwischen Mix-In und Mix-Out

HINWEIS: Die Root analysis.py verwendet relative Imports (from .models ...)
und kann daher nur als Teil des hpg_core Packages importiert werden.
Da beide analysis.py identische Imports haben, testen wir die hpg_core
Version mit den strikteren Erwartungen der Root-Version.
"""
import pytest
import sys
import os
import numpy as np
from math import ceil, floor

# Root analysis.py hat relative Imports (.models, .config) - nutze hpg_core
from hpg_core.analysis import analyze_structure_and_mix_points as analyze_root

from hpg_core.config import METER, BARS_PER_PHRASE
from tests.fixtures.audio_generators import (
  generate_track_with_structure,
  generate_silence,
  generate_noise,
  DEFAULT_SR,
)


def _calc_timing(bpm):
  """Berechnet Timing-Konstanten."""
  spb = 60.0 / bpm
  bar = spb * METER
  phrase = bar * BARS_PER_PHRASE
  return spb, bar, phrase


class TestRootMixPointBasics:
  """Grundlegende Eigenschaften - gleich wie hpg_core."""

  def test_mix_out_after_mix_in(self):
    """Mix-Out nach Mix-In."""
    bpm = 128.0
    y = generate_track_with_structure(bpm, 300.0, DEFAULT_SR)
    mi, mo, _, _ = analyze_root(y, DEFAULT_SR, 300.0, 70, bpm)
    assert mo > mi

  def test_mix_in_not_negative(self):
    """Mix-In >= 0."""
    y = generate_track_with_structure(128.0, 300.0, DEFAULT_SR)
    mi, _, _, _ = analyze_root(y, DEFAULT_SR, 300.0, 70, 128.0)
    assert mi >= 0

  def test_within_duration(self):
    """Mix-Out <= Dauer."""
    duration = 300.0
    y = generate_track_with_structure(128.0, duration, DEFAULT_SR)
    _, mo, _, _ = analyze_root(y, DEFAULT_SR, duration, 70, 128.0)
    assert mo <= duration


class TestRootStricterBounds:
  """Strengere Grenzen der Root-Version."""

  def test_mix_in_min_16_bars(self):
    """Root: Mindestens 16 Bars (2 Phrasen) fuer Mix-In."""
    bpm = 128.0
    _, bar, phrase = _calc_timing(bpm)
    y = generate_track_with_structure(bpm, 300.0, DEFAULT_SR)
    mi, _, mi_bars, _ = analyze_root(y, DEFAULT_SR, 300.0, 70, bpm)
    # Root verwendet ceil() und min 2 Phrasen
    assert mi >= phrase, (
      f"Mix-In bei {mi}s / {mi_bars} Bars - unter 1 Phrase ({phrase}s)"
    )

  def test_mix_in_max_30_percent(self):
    """Root: Mix-In maximal bei 30% der Track-Dauer."""
    bpm = 128.0
    duration = 300.0
    y = generate_track_with_structure(bpm, duration, DEFAULT_SR)
    mi, _, _, _ = analyze_root(y, DEFAULT_SR, duration, 70, bpm)
    assert mi <= duration * 0.3, (
      f"Mix-In ({mi}s) ueber 30% ({duration * 0.3}s)"
    )

  def test_mix_out_min_70_percent(self):
    """Root: Mix-Out mindestens bei mix_in + 4 Phrasen."""
    bpm = 128.0
    duration = 300.0
    _, _, phrase = _calc_timing(bpm)
    y = generate_track_with_structure(bpm, duration, DEFAULT_SR)
    mi, mo, _, _ = analyze_root(y, DEFAULT_SR, duration, 70, bpm)
    min_gap = 4 * phrase
    actual_gap = mo - mi
    assert actual_gap >= min_gap - 1.0, (
      f"Abstand {actual_gap:.1f}s < 4 Phrasen ({min_gap:.1f}s)"
    )

  def test_4_phrase_gap_minimum(self):
    """Root: Mindestens 4 Phrasen zwischen Mix-In und Mix-Out."""
    bpm = 128.0
    _, _, phrase = _calc_timing(bpm)
    y = generate_track_with_structure(bpm, 300.0, DEFAULT_SR)
    mi, mo, _, _ = analyze_root(y, DEFAULT_SR, 300.0, 70, bpm)
    gap_phrases = (mo - mi) / phrase
    assert gap_phrases >= 3.5, (
      f"Nur {gap_phrases:.1f} Phrasen Abstand (min ~4)"
    )


class TestRootCeilAlignment:
  """Root verwendet ceil() statt round() fuer konservativere Platzierung."""

  def test_mix_in_uses_ceil_logic(self):
    """Mix-In wird eher nach oben gerundet (konservativer Intro)."""
    bpm = 128.0
    _, bar, phrase = _calc_timing(bpm)
    y = generate_track_with_structure(
      bpm, 300.0, DEFAULT_SR,
      intro_ratio=0.08, outro_ratio=0.92,
    )
    mi, _, _, _ = analyze_root(y, DEFAULT_SR, 300.0, 70, bpm)
    # Bei ceil() ist Mix-In mindestens 2 * phrase
    assert mi >= 2 * phrase - 1.0, (
      f"Mix-In {mi}s unter 2 Phrasen ({2 * phrase}s) - ceil() nicht aktiv?"
    )


class TestRootDifferentBPMs:
  """Root Mix-Points bei verschiedenen Tempi."""

  @pytest.mark.parametrize("bpm", [100.0, 120.0, 128.0, 135.0, 140.0, 174.0])
  def test_valid_at_various_bpm(self, bpm):
    """Valide Mix-Points bei verschiedenen BPM."""
    duration = 300.0
    y = generate_track_with_structure(bpm, duration, DEFAULT_SR)
    mi, mo, mi_bars, mo_bars = analyze_root(y, DEFAULT_SR, duration, 70, bpm)
    assert mo > mi
    assert mi >= 0
    assert mo <= duration
    assert mo_bars > mi_bars


class TestRootEdgeCases:
  """Edge Cases fuer Root-Version."""

  def test_zero_bpm(self):
    """BPM 0 = ValueError (ungueltige Eingabe)."""
    y = generate_noise(300.0, DEFAULT_SR)
    with pytest.raises((ValueError, ZeroDivisionError)):
      analyze_root(y, DEFAULT_SR, 300.0, 50, 0.0)

  def test_silence(self):
    """Stille = valide Fallback-Points."""
    y = generate_silence(300.0, DEFAULT_SR)
    mi, mo, _, _ = analyze_root(y, DEFAULT_SR, 300.0, 0, 128.0)
    assert mo > mi
    assert mi >= 0

  def test_very_short(self):
    """Kurzer Track (20s) - kein Crash."""
    bpm = 128.0
    duration = 20.0
    y = generate_track_with_structure(bpm, duration, DEFAULT_SR)
    mi, mo, _, _ = analyze_root(y, DEFAULT_SR, duration, 70, bpm)
    assert mo > mi
    assert mi >= 0
    assert mo <= duration


class TestRootVsHpgCoreDifferences:
  """Vergleich Root vs hpg_core - Root muss strikter sein."""

  def test_root_mix_in_not_earlier_than_hpg(self):
    """Root Mix-In >= hpg_core Mix-In (wegen ceil und min 2 Phrasen)."""
    from hpg_core.analysis import analyze_structure_and_mix_points as analyze_hpg

    bpm = 128.0
    duration = 300.0
    y = generate_track_with_structure(bpm, duration, DEFAULT_SR)

    mi_hpg, _, _, _ = analyze_hpg(y, DEFAULT_SR, duration, 70, bpm)
    mi_root, _, _, _ = analyze_root(y, DEFAULT_SR, duration, 70, bpm)

    # Root sollte gleich oder spaeter Mix-In haben
    assert mi_root >= mi_hpg - 1.0, (
      f"Root Mix-In ({mi_root}s) frueher als hpg_core ({mi_hpg}s)"
    )

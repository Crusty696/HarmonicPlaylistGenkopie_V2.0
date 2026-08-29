"""Tests fuer Key-Confidence (Essentia-Muster) und LUFS-Loudness (EBU R128).

Plan + Research: docs/plans/2026-07-17-key-confidence-lufs.md
"""

import numpy as np
import pytest

from hpg_core.analysis import (
  get_key,
  get_key_with_confidence,
  key_confidence_score,
  calculate_lufs,
  MAJOR_PROFILE,
)
from hpg_core.dj_brain import _gain_advice
from hpg_core.config import GAIN_DIFF_SHOW_DB, GAIN_DIFF_WARN_DB


SR = 44100


class TestKeyConfidence:
  def test_eindeutiges_profil_hohe_konfidenz(self):
    """Exaktes C-Dur-Profil als Chroma -> strength hoch, margin > 0."""
    chroma = np.array(MAJOR_PROFILE, dtype=float)
    note, mode, strength, margin, _, _ = get_key_with_confidence(chroma)
    assert (note, mode) == ("C", "Major")
    assert strength > 0.9
    assert margin > 0.0

  def test_rauschen_niedrige_konfidenz(self):
    """Flaches Chroma (kein tonales Profil) -> niedrige Gesamt-Konfidenz."""
    rng = np.random.default_rng(42)
    chroma = np.ones(12) + rng.normal(0, 0.01, 12)
    note, mode, strength, margin, sn, sm = get_key_with_confidence(chroma)
    conf = key_confidence_score(strength, margin, note, mode, sn, sm)
    assert conf < 0.6

  def test_get_key_bleibt_kompatibel(self):
    """get_key liefert weiter (note, mode) — API-Vertrag der Bestandstests."""
    result = get_key(np.array(MAJOR_PROFILE, dtype=float))
    assert result == ("C", "Major")

  def test_score_sicher_bei_starkem_match(self):
    # AUDIT-FIX F02: strength ist jetzt ein z-Score-Kontrast (typ. 2-4 fuer
    # klaren Sieger), nicht mehr der rohe Cosine-Wert. margin auf Cosine-Skala.
    conf = key_confidence_score(2.5, 0.03, "A", "Minor", "E", "Minor")
    assert conf >= 0.6

  def test_score_nachbar_quasi_sicher(self):
    """Zweitkandidat = Quint-Nachbar (8A vs 9A) -> quasi-sicher (>= 0.5)."""
    # A-Moll = 8A, E-Moll = 9A (Quinte). AUDIT-FIX F02: Kontrast-Skala.
    conf = key_confidence_score(1.5, 0.01, "A", "Minor", "E", "Minor")
    assert conf >= 0.5

  def test_score_relative_quasi_sicher(self):
    """Zweitkandidat = relative Dur/Moll (8A vs 8B) -> quasi-sicher."""
    # AUDIT-FIX F02: Kontrast-Skala.
    conf = key_confidence_score(1.5, 0.01, "A", "Minor", "C", "Major")
    assert conf >= 0.5

  def test_score_entfernter_zweitkandidat_unsicher(self):
    """Zweitkandidat harmonisch weit weg + knappe Marge -> unsicher (<= 0.4)."""
    # A-Moll = 8A, A#-Dur = 6B (weit weg)
    conf = key_confidence_score(0.55, 0.01, "A", "Minor", "A#", "Major")
    assert conf <= 0.4


class TestCalculateLufs:
  def test_sinus_referenzwert(self):
    """-18 dBFS 997-Hz-Sinus muss ~-21 LKFS ergeben (BS.1770-Sollwert:
    0 dBFS Sinus == -3.01 LKFS; via pyloudnorm-Compliance verifiziert)."""
    t = np.arange(SR * 6) / SR
    sine = (10 ** (-18 / 20)) * np.sin(2 * np.pi * 997 * t)
    lufs = calculate_lufs(sine.astype(np.float32), SR)
    assert lufs == pytest.approx(-21.0, abs=0.5)

  def test_stille_gibt_sentinel(self):
    assert calculate_lufs(np.zeros(SR * 5, dtype=np.float32), SR) == 0.0

  def test_zu_kurz_gibt_sentinel(self):
    assert calculate_lufs(np.ones(100, dtype=np.float32), SR) == 0.0

  def test_leiserer_track_hat_niedrigere_lufs(self):
    t = np.arange(SR * 6) / SR
    loud = 0.5 * np.sin(2 * np.pi * 200 * t)
    quiet = 0.05 * np.sin(2 * np.pi * 200 * t)
    l1 = calculate_lufs(loud.astype(np.float32), SR)
    l2 = calculate_lufs(quiet.astype(np.float32), SR)
    assert l2 < l1 < 0.0
    assert l1 - l2 == pytest.approx(20.0, abs=0.5)  # 0.5/0.05 = 20 dB


class TestGainAdvice:
  def test_unbekannte_lufs_kein_advice(self):
    assert _gain_advice(0.0, -10.0) == ""
    assert _gain_advice(-10.0, 0.0) == ""

  def test_kleine_differenz_pegel_passt(self):
    advice = _gain_advice(-10.0, -10.0 - GAIN_DIFF_SHOW_DB + 0.5)
    assert "kein Gain noetig" in advice

  def test_hoerbare_differenz_mit_richtung(self):
    advice = _gain_advice(-9.0, -11.0)  # B ist 2 dB leiser
    assert "2.0 dB" in advice and "rauf" in advice

  def test_grosse_differenz_warnhinweis(self):
    advice = _gain_advice(-8.0, -8.0 - GAIN_DIFF_WARN_DB - 1.0)
    assert "deutlich" in advice

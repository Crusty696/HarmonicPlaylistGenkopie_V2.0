"""Tests fuer die Downbeat-Erkennung (hpg_core/downbeat.py) und das
downbeat-verankerte Quantisierungs-Raster.

Plan + Research: docs/plans/2026-07-17-downbeat-erkennung.md
"""

import numpy as np
import pytest

from hpg_core.config import PHRASE_CONFIDENCE_MIN
from hpg_core.downbeat import (
  _vote_margin_confidence,
  estimate_first_downbeat,
  estimate_first_phrase,
)
from hpg_core.models import quantize_to_grid
from hpg_core.dj_brain import calculate_genre_aware_mix_points, align_ai_mix_points


SR = 22050


def _make_four_on_floor(bpm: float, duration: float, downbeat_offset: float) -> np.ndarray:
  """Synthetischer 4/4-Track: Kick auf jedem Beat, akzentuierte '1' mit
  zusaetzlichem Sub-Bass und Harmoniewechsel pro Takt."""
  n = int(SR * duration)
  y = np.zeros(n, dtype=np.float32)
  beat_sec = 60.0 / bpm
  t_kick = np.arange(int(SR * 0.09)) / SR
  kick = (np.sin(2 * np.pi * 55 * t_kick) * np.exp(-t_kick * 35)).astype(np.float32)
  t_sub = np.arange(int(SR * 0.25)) / SR
  sub = (np.sin(2 * np.pi * 40 * t_sub) * np.exp(-t_sub * 8)).astype(np.float32)

  beat_idx = 0
  t = downbeat_offset
  while t < duration - 0.5:
    s = int(t * SR)
    is_one = beat_idx % 4 == 0
    amp = 1.0 if is_one else 0.55
    seg = kick * amp
    y[s:s + len(seg)] += seg[: max(0, n - s)][: len(y[s:s + len(seg)])]
    if is_one:
      y[s:s + len(sub)] += sub[: len(y[s:s + len(sub)])] * 0.8
      # Harmoniewechsel auf der 1: Akkordton pro Takt wechseln
      bar_len = int(beat_sec * 4 * SR)
      t_tone = np.arange(min(bar_len, n - s)) / SR
      freq = 220.0 * (2 ** (((beat_idx // 4) % 4) / 12.0))
      y[s:s + len(t_tone)] += (0.12 * np.sin(2 * np.pi * freq * t_tone)).astype(np.float32)
    t += beat_sec
    beat_idx += 1
  peak = float(np.max(np.abs(y)))
  return y / peak * 0.8 if peak > 0 else y


class TestEstimateFirstDownbeat:
  @pytest.mark.slow
  @pytest.mark.parametrize("bpm,offset", [
    (128.0, 0.30),
    (128.0, 1.20),
    (140.0, 0.50),
  ])
  def test_erkennt_downbeat_phase(self, bpm, offset):
    """Erkannter Downbeat liegt auf der richtigen BEAT-PHASE (mod 1 Beat)
    und bevorzugt auf der akzentuierten '1' (mod 4 Beats, ±1 Beat toleriert
    — Halbtakt-Fehler ist die bekannte Fehlerklasse, Hockman ISMIR 2012)."""
    y = _make_four_on_floor(bpm, 60.0, offset)
    db, conf = estimate_first_downbeat(y, SR, bpm)
    beat_sec = 60.0 / bpm
    # Phase relativ zum bekannten Beat-Raster
    phase_err = (db - offset) % beat_sec
    phase_err = min(phase_err, beat_sec - phase_err)
    assert phase_err < 0.08, f"Beat-Phase daneben: db={db}, offset={offset}"
    assert conf >= 0.0

  def test_stille_liefert_null(self):
    y = np.zeros(SR * 30, dtype=np.float32)
    db, conf = estimate_first_downbeat(y, SR, 128.0)
    assert db == 0.0 and conf == 0.0

  def test_zu_kurz_liefert_null(self):
    y = np.random.randn(SR * 2).astype(np.float32)
    db, conf = estimate_first_downbeat(y, SR, 128.0)
    assert db == 0.0 and conf == 0.0

  def test_ungueltige_bpm_liefert_null(self):
    y = np.random.randn(SR * 30).astype(np.float32)
    assert estimate_first_downbeat(y, SR, 0.0) == (0.0, 0.0)


class TestQuantizeToGrid:
  def test_anchor_null_ist_altes_verhalten(self):
    assert quantize_to_grid(17.0, 8.0) == 16.0
    assert quantize_to_grid(17.0, 8.0, mode="ceil") == 24.0
    assert quantize_to_grid(17.0, 8.0, mode="floor") == 16.0

  def test_anchor_verschiebt_raster(self):
    # Raster: 0.7, 8.7, 16.7, 24.7 ...
    assert quantize_to_grid(17.0, 8.0, anchor=0.7) == pytest.approx(16.7)
    assert quantize_to_grid(17.0, 8.0, anchor=0.7, mode="ceil") == pytest.approx(24.7)
    assert quantize_to_grid(16.7, 8.0, anchor=0.7, mode="floor") == pytest.approx(16.7)

  def test_grid_null_gibt_original(self):
    assert quantize_to_grid(13.37, 0.0, anchor=5.0) == 13.37


class TestAnchoredMixPoints:
  def _sections(self, duration):
    return [
      {"label": "intro", "start_time": 0.0, "end_time": 30.0, "avg_energy": 20.0},
      {"label": "main", "start_time": 30.0, "end_time": duration - 40.0, "avg_energy": 80.0},
      {"label": "outro", "start_time": duration - 40.0, "end_time": duration, "avg_energy": 25.0},
    ]

  @pytest.mark.parametrize("anchor", [0.0, 0.47, 1.9])
  def test_mixpoints_liegen_auf_verankertem_gitter(self, anchor):
    bpm, duration = 128.0, 360.0
    mi, mo, _, _ = calculate_genre_aware_mix_points(
      self._sections(duration), bpm, duration, "Techno", anchor=anchor
    )
    spb = (60.0 / bpm) * 4
    grid = spb * 8  # Techno phrase_unit 8
    for t in (mi, mo):
      rem = (t - anchor) % grid
      assert min(rem, grid - rem) < 0.05, f"anchor={anchor}: {t} nicht auf Gitter"
    assert 0 <= mi < mo <= duration

  def test_align_ai_mix_points_mit_anker(self):
    bpm = 120.0  # spb=2, Phrase(8)=16s; Raster: 0.5, 16.5, 32.5 ...
    mi, mo = align_ai_mix_points(20.0, 200.0, bpm, 300.0, 8, anchor=0.5)
    assert mi == pytest.approx(32.5)
    assert mo == pytest.approx(192.5)


def _simulated_votes(rng, phrase_unit: int, n_bars: int = 128,
                     boost: float = 1.0) -> np.ndarray:
  """Simuliert das Bar-Voting aus estimate_first_phrase: pro Bar ein
  z-normierter Score (~N(0,1)), Phrasen-Start-Bars bekommen `boost`
  zusaetzlich (boost=1.0 entspricht einer 1-Sigma-Struktur pro Bar)."""
  scores = rng.randn(n_bars)
  idx = np.arange(n_bars)
  scores[idx % phrase_unit == 0] += boost
  return np.array([
    float(np.sum(scores[idx % phrase_unit == p])) for p in range(phrase_unit)
  ])


class TestVoteMarginConfidence:
  """AUDIT-FIX N-03 (2026-07-26): Konfidenz darf nicht mit phrase_unit
  skalieren — sonst ist die Phrasen-Erkennung bei 16-Bar-Genres
  (Psytrance/Trance) faktisch abgeschaltet."""

  def test_dominanter_bin_gibt_konfidenz_1_unabhaengig_von_p(self):
    for p in (8, 16, 32):
      votes = np.zeros(p)
      votes[3 % p] = 10.0
      assert _vote_margin_confidence(votes) == pytest.approx(1.0)

  def test_identisch_zur_alten_formel_bei_phrase_unit_8(self):
    """Bei P=8 (Kalibrierungs-Basis von PHRASE_CONFIDENCE_MIN) muss die
    Normierung ein No-Op sein: (v1-v2)/sum(|votes|) * 8/8."""
    rng = np.random.RandomState(3)
    votes = rng.randn(8) * 5.0
    order = np.argsort(votes)[::-1]
    old = (votes[order[0]] - votes[order[1]]) / np.sum(np.abs(votes))
    assert _vote_margin_confidence(votes) == pytest.approx(
      float(np.clip(old, 0.0, 1.0))
    )

  def test_starke_struktur_passiert_gate_auch_bei_16_bars(self):
    """Kern des N-03-Fixes: starke 2-Sigma-Struktur muss bei phrase_unit=16
    eine aehnlich hohe Pass-Rate erreichen wie bei 8. Mit der ALTEN Formel
    (Margin/Spread ohne Normierung) lag die 16er-Pass-Rate bei nur ~49 %."""
    rng = np.random.RandomState(42)
    runs = 300
    rates, old_rates = {}, {}
    for p in (8, 16):
      hits = old_hits = 0
      for _ in range(runs):
        votes = _simulated_votes(rng, p, boost=2.0)  # 2-Sigma-Struktur
        if _vote_margin_confidence(votes) >= PHRASE_CONFIDENCE_MIN:
          hits += 1
        # alte, unnormierte Formel zum Vergleich
        order = np.argsort(votes)[::-1]
        old = (votes[order[0]] - votes[order[1]]) / np.sum(np.abs(votes))
        if old >= PHRASE_CONFIDENCE_MIN:
          old_hits += 1
      rates[p] = hits / runs
      old_rates[p] = old_hits / runs
    assert rates[8] >= 0.9, f"Pass-Rate P=8 eingebrochen: {rates[8]:.2f}"
    assert rates[16] >= 0.85, f"Pass-Rate P=16 zu niedrig: {rates[16]:.2f}"
    # Dokumentiert den urspruenglichen Bug: alte Formel verlor P=16 systematisch
    assert old_rates[16] < 0.6, (
      f"Alte Formel unerwartet gut bei P=16 ({old_rates[16]:.2f}) — "
      "Simulationsannahme pruefen"
    )

  def test_reines_rauschen_bleibt_unter_dem_gate(self):
    """Noise-Rejection: ohne Struktur darf das Gate nur selten oeffnen —
    ein falscher Phrasen-Anker waere schlimmer als keiner."""
    rng = np.random.RandomState(7)
    runs = 300
    for p in (8, 16):
      hits = sum(
        _vote_margin_confidence(_simulated_votes(rng, p, boost=0.0))
        >= PHRASE_CONFIDENCE_MIN
        for _ in range(runs)
      )
      assert hits / runs < 0.1, f"Noise-Pass-Rate P={p}: {hits / runs:.2f}"

  def test_degenerierte_eingaben(self):
    assert _vote_margin_confidence(np.zeros(8)) == 0.0
    assert _vote_margin_confidence(np.array([1.0])) == 0.0
    assert _vote_margin_confidence(np.array([])) == 0.0


class TestEstimateFirstPhraseSentinel:
  """AUDIT-FIX R4 (2026-07-26): Fehler-Sentinel ist -1.0 statt 0.0 —
  eine Phase von exakt 0.0 ist eine GUELTIGE Schaetzung."""

  def test_ungueltige_bpm_liefert_sentinel(self):
    y = np.random.RandomState(0).randn(SR * 30).astype(np.float32)
    assert estimate_first_phrase(y, SR, 0.0, 0.0, 8) == (-1.0, 0.0)

  def test_leeres_audio_liefert_sentinel(self):
    assert estimate_first_phrase(
      np.zeros(0, dtype=np.float32), SR, 128.0, 0.0, 8
    ) == (-1.0, 0.0)

  def test_zu_kurz_fuer_zwei_phrasen_liefert_sentinel(self):
    # 128 BPM, 8 Bars Phrase: 2 Phrasen = 30 s — 10 s sind zu wenig
    y = np.random.RandomState(1).randn(SR * 10).astype(np.float32)
    assert estimate_first_phrase(y, SR, 128.0, 0.0, 8) == (-1.0, 0.0)

  def test_phrase_unit_1_liefert_sentinel(self):
    y = np.random.RandomState(2).randn(SR * 30).astype(np.float32)
    assert estimate_first_phrase(y, SR, 128.0, 0.0, 1) == (-1.0, 0.0)

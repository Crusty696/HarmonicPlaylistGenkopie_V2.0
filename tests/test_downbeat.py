"""Tests fuer die Downbeat-Erkennung (hpg_core/downbeat.py) und das
downbeat-verankerte Quantisierungs-Raster.

Plan + Research: docs/plans/2026-07-17-downbeat-erkennung.md
"""

import numpy as np
import pytest

from hpg_core.config import PHRASE_CONFIDENCE_MIN
from hpg_core.downbeat import (
  DOWNBEAT_RELIABLE_MIN,
  REFERENCE_BEATGRID_CONFIDENCE,
  SELF_ESTIMATE_CONFIDENCE_MAX,
  _bar_phase_confidence,
  _beat_phase_from_fold,
  _grid_is_commensurate,
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


class TestDownbeatAnkerInvarianten:
  """AUDIT-FIX D-01/D-02 (2026-08-14): Messungen an 34 echten Psytrance-AIFFs
  (D:/beatport_tracks_2025-08) und am Produktivcache (52 Tracks).

  Zwei belegte Defekte:
  * D-01 Drift — der Anker wurde linear ueber `median(diff(beat_times))`
    zurueckgerechnet. Dieser Median ist auf allen 34 Tracks EXAKT ein
    ganzzahliges Vielfaches der Hop-Dauer (Abweichung < 1e-12) und damit
    systematisch bias-behaftet; der lineare Term multipliziert den Bias mit
    der Taktnummer. Folge: 28 von 34 Ankern lagen ausserhalb des ersten
    Takts, der schlimmste bei 11,6 Takten (19,95 s), im Produktivcache bei
    31,5 Takten (55,6 s).
  * D-02 Fremdes Raster — bei 11 von 34 Tracks trackte librosa ein
    inkommensurables Tempo (fast immer 3:2), sodass `% 4` Takte einer
    anderen Metrik zaehlte.

  Gegen die 9 Tracks mit Rekordbox-ANLZ-Downbeat als Ground Truth sank der
  mediane Takt-Fehler von 0,287 s auf 0,024 s.
  """

  @pytest.mark.slow
  @pytest.mark.parametrize("bpm,offset", [(128.0, 0.30), (140.0, 0.50)])
  def test_anker_driftet_nicht_mit_der_tracklaenge(self, bpm, offset):
    """D-01: Derselbe Downbeat muss bei 40 s und bei 300 s Material
    denselben Anker liefern. Genau das tat die alte Rueckrechnung nicht —
    ihr Fehler wuchs linear mit der Tracklaenge."""
    kurz = estimate_first_downbeat(_make_four_on_floor(bpm, 40.0, offset), SR, bpm)[0]
    lang = estimate_first_downbeat(_make_four_on_floor(bpm, 300.0, offset), SR, bpm)[0]
    assert kurz == pytest.approx(lang, abs=0.05), (
      f"Anker haengt von der Tracklaenge ab: {kurz} vs {lang}"
    )
    assert abs(lang - offset) < 0.08, f"Anker {lang} statt {offset}"

  @pytest.mark.slow
  @pytest.mark.parametrize("bpm,offset,duration", [
    (128.0, 0.30, 300.0),
    (140.0, 0.50, 300.0),
    (140.0, 1.60, 120.0),
  ])
  def test_anker_liegt_immer_im_ersten_takt(self, bpm, offset, duration):
    """Ein ERSTER Downbeat kann per Definition nicht hinter dem ersten Takt
    liegen. dj_brain nutzt first_downbeat als Untergrenze fuer Mix-In
    (AUDIT-FIX R3) — ein Anker bei 55 s verschiebt dort den Einstiegspunkt."""
    bar_len = (60.0 / bpm) * 4
    db, _ = estimate_first_downbeat(
      _make_four_on_floor(bpm, duration, offset), SR, bpm
    )
    assert 0.0 <= db < bar_len, f"Anker {db} liegt nicht im ersten Takt ({bar_len})"

  def test_kommensurabilitaet_trennt_die_gemessenen_verhaeltnisse(self):
    """D-02: Die Schwelle muss die an echtem Material gemessenen Cluster
    trennen — Verhaeltnisse um 1 (und ganzzahlige Vielfache/Teiler, wenn
    librosa nur jeden n-ten Beat findet) sind gueltig, 3:2 & Co. nicht."""
    for ratio in (0.962, 0.996, 1.019, 1.044, 0.5, 2.0, 3.975, 4.024):
      assert _grid_is_commensurate(ratio, 1.0), f"ratio {ratio} faelschlich verworfen"
    for ratio in (0.756, 1.320, 1.351, 1.485, 1.489, 2.650):
      assert not _grid_is_commensurate(ratio, 1.0), f"ratio {ratio} faelschlich akzeptiert"

  def test_degenerierte_raster_werden_verworfen(self):
    assert not _grid_is_commensurate(0.0, 1.0)
    assert not _grid_is_commensurate(1.0, 0.0)

  @pytest.mark.slow
  def test_fremdes_beat_raster_liefert_keinen_anker(self):
    """D-02 Integration: passt das getrackte Raster nicht zum uebergebenen
    bpm, ist die '1' auf dem Zielgitter nicht definiert. Dann gilt der
    dokumentierte Vertrag (0.0, 0.0) — kein Anker statt falschem Anker."""
    y = _make_four_on_floor(128.0, 60.0, 0.30)
    # 85,33 BPM = 2/3 von 128: das Raster liegt zwischen den Zielbeats
    assert estimate_first_downbeat(y, SR, 85.33) == (0.0, 0.0)
    # dasselbe Material mit passendem Tempo liefert weiterhin einen Anker
    assert estimate_first_downbeat(y, SR, 128.0)[1] > 0.0

  @pytest.mark.slow
  def test_konfidenz_nutzt_die_volle_skala_bleibt_aber_unter_1(self):
    """AUDIT-FIX D-03 (2026-08-14): Die Skala ist repariert.

    Vorher war `confidence` die rohe Voting-Margin (v1-v2)/sum(|v|). Weil
    die vier Votes Summen z-normierter Groessen sind, summieren sie sich
    exakt zu 0 — damit ist die Margin analytisch auf 2/3 gedeckelt. Die
    frueheren Gates `>= 0.9` waren fuer eine Eigenschaetzung deshalb
    UNERREICHBAR und bedeuteten faktisch "nur Rekordbox-ANLZ-Beatgrid".

    Jetzt: Margin durch ihren Deckel geteilt (ehrliche 0..1-Skala), mit dem
    Faltungs-Lock konjungiert und hart unter 1.0 gehalten — 1.0 bleibt
    exklusiv dem Referenz-Beatgrid vorbehalten.
    """
    conf = estimate_first_downbeat(_make_four_on_floor(140.0, 120.0, 0.5), SR, 140.0)[1]
    assert conf > 2.0 / 3.0, (
      f"Skala weiterhin gedeckelt (conf={conf}) — Ruecknormierung wirkt nicht"
    )
    assert conf >= DOWNBEAT_RELIABLE_MIN
    assert conf <= SELF_ESTIMATE_CONFIDENCE_MAX < REFERENCE_BEATGRID_CONFIDENCE

  def test_margin_deckel_wird_auf_1_zurueckgerechnet(self):
    """Der analytisch maximale Vote-Vektor (S, -S/3, -S/3, -S/3) hat die
    rohe Margin 2/3 und muss auf 1.0 abgebildet werden."""
    votes = np.array([3.0, -1.0, -1.0, -1.0])
    raw = (votes[0] - votes[1]) / np.sum(np.abs(votes))
    assert raw == pytest.approx(2.0 / 3.0)
    assert _bar_phase_confidence(votes) == pytest.approx(1.0)

  def test_bar_phase_confidence_degeneriert(self):
    assert _bar_phase_confidence(np.zeros(4)) == 0.0
    assert _bar_phase_confidence(np.array([1.0])) == 0.0
    # Gleichstand zwischen Platz 1 und 2 = keine Entscheidung
    assert _bar_phase_confidence(np.array([1.0, 1.0, -1.0, -1.0])) == 0.0

  @pytest.mark.slow
  def test_faltung_findet_die_beat_phase_ohne_gruppenlaufzeit(self):
    """D-03 Kern: der Sub-Beat-Anteil kommt aus der beat-synchronen Faltung
    der nullphasig gefilterten Huellkurve. Auf einem Klick-Track muss der
    Attack-Punkt praktisch exakt auf dem Kick liegen — der alte Snap auf den
    staerksten Onset-FRAME war an echtem Material im Median 116 ms zu spaet
    und auf das 46-ms-Hop-Raster gequantelt."""
    bpm, offset = 140.0, 0.5
    ibi = 60.0 / bpm
    y = _make_four_on_floor(bpm, 60.0, offset)
    phase, lock = _beat_phase_from_fold(y, SR, ibi)
    assert phase is not None
    assert lock > 0.5, f"Klick-Track ohne beat-synchrone Struktur? lock={lock}"
    err = abs(phase - offset % ibi) % ibi
    err = min(err, ibi - err)
    assert err < ibi / 8.0, f"Beat-Phase {phase} statt {offset % ibi} (Fehler {err:.4f}s)"

  def test_faltung_lehnt_zu_kurzes_material_ab(self):
    assert _beat_phase_from_fold(np.zeros(SR, dtype=np.float32), SR, 0.5) == (None, 0.0)
    assert _beat_phase_from_fold(None, SR, 0.5) == (None, 0.0)
    assert _beat_phase_from_fold(np.zeros(SR * 30, dtype=np.float32), SR, 0.0) == (None, 0.0)

  def test_stille_hat_keinen_lock(self):
    """Ohne Transienten gibt es keine Sub-Beat-Phase — und damit keinen
    Anker. Ein erfundener Anker waere schlimmer als keiner."""
    assert _beat_phase_from_fold(
      np.zeros(SR * 30, dtype=np.float32), SR, 0.5
    ) == (None, 0.0)


class TestKalibrierteSchwelle:
  """AUDIT-FIX D-03 (2026-08-14): Kalibrierung an 35 Tracks mit
  Rekordbox-ANLZ-Beatgrid als Ground Truth (Paare aus Konfidenz und
  tatsaechlichem Phasenfehler). 19 davon liefern ueberhaupt eine
  Eigenschaetzung, 16 werden vom Kommensurabilitaets-Gate (D-02) verworfen.

  Hoerbare Grenze: 1/8 Beat (54 ms bei 138 BPM). Gemessen:
    * Konfidenz >= 0.30 -> 12 Tracks, Sub-Beat-Fehler Median 16 ms,
      Max 43 ms — 0 Verletzungen.
    * Konfidenz <= 0.241 -> enthaelt ALLE drei Ausreisser (83/153/188 ms).
  Die Luecke 0.241..0.391 ist eindeutig; 0.30 liegt geometrisch mittig.
  """

  def test_schwelle_liegt_in_der_gemessenen_luecke(self):
    assert 0.241 < DOWNBEAT_RELIABLE_MIN <= 0.391

  def test_referenz_beatgrid_bleibt_exklusiv(self):
    """1.0 darf ausschliesslich das ANLZ-Beatgrid bedeuten — nur dort ist
    auch die TAKT-Phase belegt. Die Eigenschaetzung muss hart darunter
    bleiben, sonst wird `== 1.0` in Exporter und Renderer bedeutungslos."""
    assert SELF_ESTIMATE_CONFIDENCE_MAX < REFERENCE_BEATGRID_CONFIDENCE

  def test_gates_der_konsumenten_stimmen_mit_der_kalibrierung_ueberein(self):
    """Kein Konsument darf eine eigene Zahlenschwelle mitfuehren."""
    from hpg_core import transition_renderer as tr

    class _T:
      filePath = "x"
      bpm = 138.0
      lufs = 0.0
      first_downbeat = 0.5

    class _Plan:
      mix_out_a = 10.0
      mix_in_b = 20.0
      overlap = 30.0
      transition_type = "smooth_blend"
      target_sr = 44100

    def spec_for(conf_a, conf_b):
      a, b = _T(), _T()
      a.downbeat_confidence = conf_a
      b.downbeat_confidence = conf_b
      return tr.TransitionClipSpec.from_plan(_Plan(), a, b)

    below = spec_for(DOWNBEAT_RELIABLE_MIN - 0.01, 1.0)
    assert not below.downbeat_reliable_a
    at = spec_for(DOWNBEAT_RELIABLE_MIN, DOWNBEAT_RELIABLE_MIN)
    assert at.downbeat_reliable_a and at.downbeat_reliable_b
    # Eigenschaetzung erlaubt Beat-, aber nie Takt-Alignment
    assert not at.bar_phase_reliable_a and not at.bar_phase_reliable_b
    ref = spec_for(1.0, 1.0)
    assert ref.bar_phase_reliable_a and ref.bar_phase_reliable_b

  def test_beatgrid_export_verlangt_das_referenz_beatgrid(self):
    """Ein TEMPO-Element behauptet mit `Battito=1` die Takt-Phase. Die
    liefert die Eigenschaetzung nicht verlaesslich (9 von 19 Schaetzungen
    lagen um ganze Beats daneben), deshalb bleibt der Export bei == 1.0."""
    from hpg_core.exporters import rekordbox_xml_exporter as rx
    import inspect

    src = inspect.getsource(rx.RekordboxXMLExporter._add_beat_grid)
    assert "REFERENCE_BEATGRID_CONFIDENCE" in src
    assert ">= 0.9" not in src

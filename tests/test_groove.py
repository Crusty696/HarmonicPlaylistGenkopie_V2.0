"""Tests fuer die beat-synchrone Mustererkennung."""
import numpy as np
import pytest

from hpg_core.groove import BAR_SLOTS, fold_to_bar


def _envelope_with_peaks(peak_times, duration, sr_frames=100.0):
    """Baut eine Huellkurve mit Spitzen an den gegebenen Sekunden."""
    n = int(duration * sr_frames)
    env = np.zeros(n, dtype=float)
    times = np.arange(n) / sr_frames
    for t in peak_times:
        idx = int(round(t * sr_frames))
        if 0 <= idx < n:
            env[idx] = 1.0
    return env, times


def test_fold_to_bar_viertel_landen_auf_slot_0_4_8_12():
    # 120 BPM -> 0.5 s pro Beat, 2.0 s pro Takt. Zwei Takte, Viertel auf jeder Zaehlzeit.
    peaks = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
    env, times = _envelope_with_peaks(peaks, duration=4.0)

    pattern = fold_to_bar(env, times, bpm=120.0, first_downbeat=0.0)

    assert len(pattern) == BAR_SLOTS
    belegt = [i for i, v in enumerate(pattern) if v > 0.0]
    assert belegt == [0, 4, 8, 12]
    assert pytest.approx(sum(pattern), abs=1e-9) == 1.0


def test_fold_to_bar_offbeat_landet_auf_slot_2_6_10_14():
    # Offbeat-Achtel: 0.25 s nach jeder Zaehlzeit bei 120 BPM.
    peaks = [0.25, 0.75, 1.25, 1.75]
    env, times = _envelope_with_peaks(peaks, duration=2.0)

    pattern = fold_to_bar(env, times, bpm=120.0, first_downbeat=0.0)

    belegt = [i for i, v in enumerate(pattern) if v > 0.0]
    assert belegt == [2, 6, 10, 14]


def test_fold_to_bar_beruecksichtigt_downbeat_versatz():
    # Gleiche Viertel, aber das Raster beginnt erst bei 0.3 s.
    peaks = [0.3, 0.8, 1.3, 1.8]
    env, times = _envelope_with_peaks(peaks, duration=2.5)

    pattern = fold_to_bar(env, times, bpm=120.0, first_downbeat=0.3)

    belegt = [i for i, v in enumerate(pattern) if v > 0.0]
    assert belegt == [0, 4, 8, 12]


def test_fold_to_bar_leere_huellkurve_gibt_leere_liste():
    assert fold_to_bar(np.array([]), np.array([]), bpm=120.0, first_downbeat=0.0) == []


def test_fold_to_bar_ungueltige_bpm_gibt_leere_liste():
    env, times = _envelope_with_peaks([0.0], duration=1.0)
    assert fold_to_bar(env, times, bpm=0.0, first_downbeat=0.0) == []


from hpg_core.groove import bass_punch_from_band, syncopation_from_pattern


def test_syncopation_null_bei_reinen_vierteln():
    pattern = [0.0] * 16
    for slot in (0, 4, 8, 12):
        pattern[slot] = 0.25
    assert syncopation_from_pattern(pattern) == pytest.approx(0.0)


def test_syncopation_eins_bei_reinem_offbeat():
    pattern = [0.0] * 16
    for slot in (2, 6, 10, 14):
        pattern[slot] = 0.25
    assert syncopation_from_pattern(pattern) == pytest.approx(1.0)


def test_syncopation_haelfte_bei_gleichverteilung_auf_on_und_off():
    pattern = [0.0] * 16
    for slot in (0, 4, 8, 12, 2, 6, 10, 14):
        pattern[slot] = 0.125
    assert syncopation_from_pattern(pattern) == pytest.approx(0.5)


def test_syncopation_leeres_muster_gibt_null():
    assert syncopation_from_pattern([]) == 0.0


def test_bass_punch_hoch_bei_spitzen_niedrig_bei_teppich():
    # Nachbildung einer echten Bass-Huellkurve aus dem STFT: die traegt in
    # 98-100 % der Frames Energie (gemessen an 18 Tracks, 2026-08-19). Ein
    # Fixture aus Einzelsample-Spitzen waere unrealistisch duenn und wuerde
    # das 95. Perzentil auf 0.0 druecken.
    n = np.arange(1000)
    grundpegel = 0.1
    # Kick alle 100 Frames, exponentiell abklingend ueber ~20 Frames
    spitzen = grundpegel + np.exp(-(n % 100) / 20.0)
    teppich = np.full(1000, 0.5)

    assert bass_punch_from_band(spitzen) > bass_punch_from_band(teppich)
    assert bass_punch_from_band(teppich) == pytest.approx(1.0, abs=0.05)


def test_bass_punch_leeres_signal_gibt_null():
    assert bass_punch_from_band(np.array([])) == 0.0


from hpg_core.analysis import FeatureCache
from hpg_core.groove import GrooveFeatures, extract_groove


def _click_track(bpm=120.0, sr=22050, bars=8, offbeat=False):
    """Erzeugt ein Klick-Signal auf den Zaehlzeiten (oder dazwischen)."""
    beat = 60.0 / bpm
    dauer = bars * 4 * beat
    y = np.zeros(int(dauer * sr), dtype=np.float32)
    versatz = beat / 2.0 if offbeat else 0.0
    t = versatz
    while t < dauer:
        i = int(t * sr)
        if i + 200 < len(y):
            # kurzer Bass-Impuls bei 50 Hz
            n = np.arange(200)
            y[i:i + 200] += (np.sin(2 * np.pi * 50 * n / sr) * np.exp(-n / 40.0)).astype(np.float32)
        t += beat
    return y, sr


def test_extract_groove_liefert_muster_fuer_klick_track():
    y, sr = _click_track()
    features = extract_groove(y, sr, bpm=120.0, first_downbeat=0.0)

    assert isinstance(features, GrooveFeatures)
    assert len(features.groove_pattern) == BAR_SLOTS
    assert len(features.bass_pattern) == BAR_SLOTS
    assert features.sub_energy > 0.0
    assert features.bass_punch > 0.0


def test_extract_groove_trennt_gerade_von_offbeat():
    y_gerade, sr = _click_track(offbeat=False)
    y_offbeat, _ = _click_track(offbeat=True)

    gerade = extract_groove(y_gerade, sr, bpm=120.0, first_downbeat=0.0)
    off = extract_groove(y_offbeat, sr, bpm=120.0, first_downbeat=0.0)

    assert gerade.syncopation < 0.35
    assert off.syncopation > 0.65


def test_extract_groove_nutzt_uebergebenen_feature_cache():
    y, sr = _click_track()
    cache = FeatureCache(y, sr)
    cache.get_onset_strength()  # vorbelegen

    features = extract_groove(y, sr, bpm=120.0, first_downbeat=0.0, feature_cache=cache)

    assert len(features.groove_pattern) == BAR_SLOTS


def test_extract_groove_ohne_bpm_liefert_leere_muster():
    y, sr = _click_track()
    features = extract_groove(y, sr, bpm=0.0, first_downbeat=0.0)

    assert features.groove_pattern == []
    assert features.bass_pattern == []
    assert features.syncopation == 0.0


from hpg_core.caching import CACHE_VERSION
from hpg_core.models import Track


def test_track_hat_groove_felder_mit_defaults():
    t = Track(filePath="x.mp3", fileName="x.mp3")

    assert t.groove_pattern == []
    assert t.bass_pattern == []
    assert t.syncopation == 0.0
    assert t.sub_energy == 0.0
    assert t.bass_punch == 0.0


def test_cache_version_ist_30():
    assert CACHE_VERSION == 30


def test_groove_wird_nur_bei_belastbarem_downbeat_berechnet():
    """downbeat_confidence 0.0 heisst: kein Raster, also kein Muster."""
    from hpg_core.analysis import compute_groove_fields

    y, sr = _click_track()
    mit = compute_groove_fields(y, sr, bpm=120.0, first_downbeat=0.0,
                                downbeat_confidence=1.0, feature_cache=None)
    ohne = compute_groove_fields(y, sr, bpm=120.0, first_downbeat=0.0,
                                 downbeat_confidence=0.0, feature_cache=None)

    assert len(mit.groove_pattern) == BAR_SLOTS
    assert ohne.groove_pattern == []
    assert ohne.syncopation == 0.0

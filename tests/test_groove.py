"""Tests fuer die beat-synchrone Mustererkennung."""
import librosa
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


def test_fold_to_bar_leicht_zu_frueh_landet_trotzdem_auf_der_zaehlzeit():
    # Der geschaetzte Downbeat traegt einen Sub-Beat-Fehler (Median 16 ms,
    # Max 43 ms laut Kalibrierung in downbeat.py). Spitzen 8 ms VOR der
    # Zaehlzeit muessen weiterhin auf 0/4/8/12 fallen, nicht auf 3/7/11/15.
    peaks = [0.5 - 0.008, 1.0 - 0.008, 1.5 - 0.008, 2.0 - 0.008]
    env, times = _envelope_with_peaks(peaks, duration=2.5, sr_frames=1000.0)

    pattern = fold_to_bar(env, times, bpm=120.0, first_downbeat=0.0)

    belegt = [i for i, v in enumerate(pattern) if v > 0.0]
    assert belegt == [0, 4, 8, 12]


def _impuls_zug(bpm=128.0, dauer=360.0, fps=100.0):
    """Impulsfolge exakt auf den Zaehlzeiten, ueber ein langes Fenster."""
    n = int(dauer * fps)
    env = np.zeros(n, dtype=float)
    times = np.arange(n) / fps
    beat = 60.0 / bpm
    t = 0.0
    while t < dauer:
        i = int(round(t * fps))
        if i < n:
            env[i] = 1.0
        t += beat
    return env, times


def test_fold_to_bar_exaktes_tempo_liefert_konzentriertes_muster():
    env, times = _impuls_zug(bpm=128.0)

    pattern = fold_to_bar(env, times, bpm=128.0, first_downbeat=0.0)

    assert len(pattern) == BAR_SLOTS
    assert max(pattern) * BAR_SLOTS >= 3.0


def test_fold_to_bar_verschobenes_tempo_gibt_leere_liste():
    # Gleiche Impulsfolge, aber mit 0,5 BPM falschem Tempo gefaltet: die
    # Phase laeuft ueber 360 s um mehrere Slots weg, das Muster wird flach.
    env, times = _impuls_zug(bpm=128.0)

    assert fold_to_bar(env, times, bpm=127.5, first_downbeat=0.0) == []


def test_fold_to_bar_gleichverteilte_huellkurve_gibt_leere_liste():
    n = 36000
    env = np.ones(n, dtype=float)
    times = np.arange(n) / 100.0

    assert fold_to_bar(env, times, bpm=120.0, first_downbeat=0.0) == []


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


def test_extract_groove_legt_keine_zweiten_cache_eintraege_an():
    """Der Groove darf Onset und STFT nicht ein zweites Mal berechnen.

    So belegt die Pipeline den Cache vor dem Groove-Aufruf:
    calculate_danceability ruft get_onset_strength() ohne Argument (Schluessel
    None, librosa-Default-Hop 512) und get_stft_magnitude(2048, 512).
    """
    y, sr = _click_track()
    cache = FeatureCache(y, sr)
    cache.get_onset_strength()
    cache.get_stft_magnitude(n_fft=2048, hop_length=512)
    onset_vorher = set(cache._onset.keys())
    stft_vorher = set(cache._stft.keys())

    extract_groove(y, sr, bpm=120.0, first_downbeat=0.0, feature_cache=cache)

    assert set(cache._onset.keys()) == onset_vorher
    assert set(cache._stft.keys()) == stft_vorher


def test_sub_energy_ist_ein_leistungsverhaeltnis():
    """40 Hz mit Amplitude 1.0 gegen 4 kHz mit Amplitude 0.5.

    Leistung verhaelt sich wie das Quadrat der Amplitude: 1 / (1 + 0.25) =
    0.80. Ueber die reine Magnitude waeren es 1 / (1 + 0.5) = 0.67 — das ist
    kein Energieanteil, auch wenn das Feld so heisst.
    """
    sr = 22050
    t = np.arange(sr * 20) / sr
    y = (np.sin(2 * np.pi * 40 * t) + 0.5 * np.sin(2 * np.pi * 4000 * t)).astype(
        np.float32
    )

    features = extract_groove(y, sr, bpm=128.0, first_downbeat=0.0)

    assert features.sub_energy == pytest.approx(0.80, abs=0.03)


def test_fold_to_bar_hat_keine_abweichende_slot_zahl_mehr():
    """Der `slots`-Parameter ist entfallen.

    ON_BEAT_SLOTS/OFF_BEAT_SLOTS beschreiben ein 16-Slot-Raster; bei jeder
    anderen Slot-Zahl lieferte syncopation_from_pattern stillschweigend 0.0.
    """
    env, times = _envelope_with_peaks([0.0, 0.5, 1.0, 1.5], duration=2.0)

    with pytest.raises(TypeError):
        fold_to_bar(env, times, bpm=120.0, first_downbeat=0.0, slots=8)


class _KurzerOnsetCache:
    """FeatureCache-Attrappe: Onset kuerzer als die STFT-Frames."""

    def __init__(self, y, sr, anteil):
        self.y = y
        self.sr = sr
        self._magnitude = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
        voll = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
        self._onset = voll[: int(len(voll) * anteil)]

    def get_onset_strength(self, hop_length=None):
        return self._onset

    def get_stft_magnitude(self, n_fft=2048, hop_length=512):
        return self._magnitude


def test_sub_energy_und_bass_punch_nutzen_dieselbe_kappung_wie_die_muster():
    """Erste Haelfte 40 Hz, zweite Haelfte 4 kHz.

    Wird der Onset auf die erste Haelfte gekappt, gelten alle Kennwerte fuer
    diese Haelfte — sonst mischt sub_energy Frames bei, die im Muster gar
    nicht vorkommen.
    """
    sr = 22050
    t = np.arange(sr * 20) / sr
    y = np.where(
        t < 10.0, np.sin(2 * np.pi * 40 * t), np.sin(2 * np.pi * 4000 * t)
    ).astype(np.float32)

    cache = _KurzerOnsetCache(y, sr, anteil=0.5)
    features = extract_groove(y, sr, bpm=128.0, first_downbeat=0.0,
                              feature_cache=cache)

    # Nur die 40-Hz-Haelfte zaehlt -> fast die gesamte Leistung liegt im Sub.
    assert features.sub_energy > 0.9


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


def test_cache_version_traegt_die_groove_felder_und_steckt_im_dateinamen():
    """Prueft die Wirkung des Bumps, nicht die Zahl.

    Ein `assert CACHE_VERSION == 30` behauptete nur, eine Konstante sei
    gleich sich selbst: es musste bei jedem Bump von Hand nachgezogen werden
    und fing nichts. Entscheidend ist zweierlei — die Version darf nicht
    unter den Stand fallen, ab dem die Groove-Felder existieren (30), und
    sie muss im Dateinamen stehen, damit ein Bump wirklich eine neue
    Datenbank erzeugt statt alte Zeilen weiterzulesen.
    """
    from hpg_core.caching import _resolve_cache_file

    assert CACHE_VERSION >= 30
    # Ohne Override (Produktivfall) muss die Version im Dateinamen stehen.
    # Im Test setzt conftest HPG_CACHE_FILE auf einen Temp-Pfad, deshalb wird
    # hier die Pfadbildung direkt geprueft statt der aufgeloeste CACHE_FILE.
    assert f"hpg_cache_v{CACHE_VERSION}.db" in _resolve_cache_file("")


def test_groove_wird_nur_bei_belastbarem_downbeat_berechnet():
    """Unterhalb von DOWNBEAT_RELIABLE_MIN gibt es kein belastbares Raster."""
    from hpg_core.analysis import compute_groove_fields
    from hpg_core.downbeat import DOWNBEAT_RELIABLE_MIN

    y, sr = _click_track()
    mit = compute_groove_fields(y, sr, bpm=120.0, first_downbeat=0.0,
                                downbeat_confidence=1.0, feature_cache=None)
    ohne = compute_groove_fields(y, sr, bpm=120.0, first_downbeat=0.0,
                                 downbeat_confidence=0.0, feature_cache=None)

    assert len(mit.groove_pattern) == BAR_SLOTS
    assert ohne.groove_pattern == []
    assert ohne.syncopation == 0.0
    assert DOWNBEAT_RELIABLE_MIN == 0.30


def test_groove_leer_bei_konfidenz_unter_dem_kalibrierten_minimum():
    """0.2 liegt in der Zone mit ALLEN Phasen-Ausreissern (83-188 ms).

    Eine falsche TAKT-Phase verwischt das Muster nicht, sie ROTIERT es um 4,
    8 oder 12 Slots — der schlimmste Fall fuer einen Vergleichs-Fingerabdruck.
    """
    from hpg_core.analysis import compute_groove_fields

    y, sr = _click_track()
    schwach = compute_groove_fields(y, sr, bpm=120.0, first_downbeat=0.0,
                                    downbeat_confidence=0.2, feature_cache=None)

    assert schwach.groove_pattern == []
    assert schwach.bass_pattern == []
    assert schwach.syncopation == 0.0


# --- Mechanismus 1a: reine Bass-Kennwerte ohne Musterfaltung (Spec 5.3) ---


def test_bass_kennwerte_stimmen_mit_extract_groove_ueberein():
    """Eine Quelle: extract_groove muss dieselbe Berechnung benutzen."""
    from hpg_core.groove import bass_kennwerte

    y, sr = _click_track()
    sub, punch = bass_kennwerte(y, sr)
    voll = extract_groove(y, sr, bpm=120.0, first_downbeat=0.0)

    assert sub == pytest.approx(voll.sub_energy, abs=1e-9)
    assert punch == pytest.approx(voll.bass_punch, abs=1e-9)


def test_bass_kennwerte_leeres_signal_gibt_nullen():
    from hpg_core.groove import bass_kennwerte

    assert bass_kennwerte(np.array([], dtype=np.float32), 22050) == (0.0, 0.0)


def test_bass_kennwerte_trennt_basslastig_von_hoehenlastig():
    from hpg_core.groove import bass_kennwerte

    sr = 22050
    t = np.arange(sr * 10) / sr
    tief = np.sin(2 * np.pi * 40 * t).astype(np.float32)
    hoch = np.sin(2 * np.pi * 4000 * t).astype(np.float32)

    assert bass_kennwerte(tief, sr)[0] > 0.9
    assert bass_kennwerte(hoch, sr)[0] < 0.05

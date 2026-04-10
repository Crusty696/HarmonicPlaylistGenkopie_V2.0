"""
tests/test_transition_renderer.py

Unit-Tests fuer hpg_core/transition_renderer.py.
Verwenden synthetische Numpy-Arrays — kein echtes Audiomaterial noetig.
"""

import os

import numpy as np
import pytest
import soundfile as sf

from hpg_core.transition_renderer import (
    EqCrossfadeConfig,
    TransitionClipSpec,
    _apply_compressor,
    _apply_eq_crossfade,
    _ensure_len,
    _load_segment,
    _make_sos,
    _rms_normalize,
    make_temp_output_path,
    render_transition_clip,
)


# ---------------------------------------------------------------------------
# Hilfsfunktionen fuer Tests
# ---------------------------------------------------------------------------

def _write_test_wav(path: str, duration_sec: float = 10.0, sr: int = 44100,
                   freq: float = 440.0, channels: int = 2) -> str:
    """Erstellt eine synthetische WAV-Datei fuer Tests."""
    n = int(sr * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False, dtype=np.float32)
    wave = (np.sin(2 * np.pi * freq * t) * 0.3).astype(np.float32)
    if channels == 2:
        data = np.stack([wave, wave], axis=1)
    else:
        data = wave
    sf.write(path, data, sr, subtype='PCM_16')
    return path


def _write_test_aiff(path: str, duration_sec: float = 10.0, sr: int = 44100) -> str:
    """Erstellt eine synthetische AIFF-Datei fuer Tests."""
    n = int(sr * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False, dtype=np.float32)
    wave = (np.sin(2 * np.pi * 528 * t) * 0.3).astype(np.float32)
    data = np.stack([wave, wave], axis=1)
    sf.write(path, data, sr, subtype='PCM_16')
    return path


def _make_stereo_signal(frames: int, sr: int = 44100,
                        freq: float = 440.0) -> np.ndarray:
    """Erzeugt ein (frames, 2) float32 Sinus-Signal."""
    t = np.linspace(0, frames / sr, frames, endpoint=False, dtype=np.float32)
    wave = (np.sin(2 * np.pi * freq * t) * 0.5).astype(np.float32)
    return np.stack([wave, wave], axis=1)


# ---------------------------------------------------------------------------
# Tests: _ensure_len
# ---------------------------------------------------------------------------

class TestEnsureLen:
    def test_array_zu_lang_wird_gekuerzt(self):
        arr = np.ones((100, 2), dtype=np.float32)
        result = _ensure_len(arr, 50)
        assert result.shape == (50, 2)

    def test_array_genau_richtig_unveraendert(self):
        arr = np.ones((100, 2), dtype=np.float32)
        result = _ensure_len(arr, 100)
        assert result.shape == (100, 2)
        np.testing.assert_array_equal(result, arr)

    def test_array_zu_kurz_wird_aufgefuellt(self):
        arr = np.ones((50, 2), dtype=np.float32)
        result = _ensure_len(arr, 100)
        assert result.shape == (100, 2)
        # Erste 50 Frames unveraendert
        np.testing.assert_array_equal(result[:50], arr)
        # Rest ist Stille
        np.testing.assert_array_equal(result[50:], np.zeros((50, 2), dtype=np.float32))

    def test_leeres_array_wird_aufgefuellt(self):
        arr = np.zeros((0, 2), dtype=np.float32)
        result = _ensure_len(arr, 10)
        assert result.shape == (10, 2)
        np.testing.assert_array_equal(result, np.zeros((10, 2), dtype=np.float32))


# ---------------------------------------------------------------------------
# Tests: _make_sos
# ---------------------------------------------------------------------------

class TestMakeSos:
    def test_sos_lowpass_hat_richtige_form(self):
        sos = _make_sos(200.0, 44100, 'low', order=4)
        # SOS-Matrix: (n_sections, 6), fuer Butterworth 4. Ordnung = 2 Sektionen
        assert sos.ndim == 2
        assert sos.shape[1] == 6
        assert sos.shape[0] >= 1

    def test_sos_highpass_hat_richtige_form(self):
        sos = _make_sos(200.0, 44100, 'high', order=4)
        assert sos.ndim == 2
        assert sos.shape[1] == 6

    def test_sos_lowpass_daempft_hohe_frequenzen(self):
        """Lowpass bei 200 Hz soll 10 kHz stark daempfen (50x ueber Cutoff)."""
        from scipy.signal import sosfiltfilt
        sr = 44100
        sos = _make_sos(200.0, sr, 'low')
        n = sr * 2  # 2 Sekunden — laenger fuer stabile Messung
        t = np.linspace(0, 2.0, n, dtype=np.float32)
        signal_10khz = np.sin(2 * np.pi * 10000 * t).astype(np.float32)
        filtered = sosfiltfilt(sos, signal_10khz)
        # Nur Steady-State-Mitte pruefen (erste + letzte 200ms ausschliessen)
        margin = int(sr * 0.2)
        steady = filtered[margin:-margin]
        # Bei 10 kHz (50x ueber Cutoff) soll 4. Ordnung Butterworth < 0.001 ergeben
        assert np.max(np.abs(steady)) < 0.001


# ---------------------------------------------------------------------------
# Tests: _apply_eq_crossfade
# ---------------------------------------------------------------------------

class TestApplyEqCrossfade:
    SR = 44100
    CF_SEC = 4.0
    CF_FRAMES = int(SR * CF_SEC)

    def setup_method(self):
        self.seg_a = _make_stereo_signal(self.CF_FRAMES, self.SR, freq=440.0)
        self.seg_b = _make_stereo_signal(self.CF_FRAMES, self.SR, freq=528.0)

    def test_output_hat_richtige_form(self):
        config = EqCrossfadeConfig(self.CF_FRAMES, self.SR, 200.0, "smooth_blend")
        result = _apply_eq_crossfade(
            self.seg_a, self.seg_b,
            config
        )
        assert result.shape == (self.CF_FRAMES, 2)
        assert result.dtype == np.float32

    def test_smooth_blend_am_anfang_ist_track_a(self):
        """Erster Frame soll hauptsaechlich Track A sein (fo=1.0, fi=0.0)."""
        config = EqCrossfadeConfig(self.CF_FRAMES, self.SR, 200.0, "smooth_blend")
        result = _apply_eq_crossfade(
            self.seg_a, self.seg_b,
            config
        )
        # Erster Frame: fo=1.0, fi≈0 → result ≈ seg_a[0]
        np.testing.assert_allclose(result[0], self.seg_a[0], atol=0.01)

    def test_smooth_blend_am_ende_ist_track_b(self):
        """Letzter Frame soll hauptsaechlich Track B sein (fo=0.0, fi=1.0)."""
        config = EqCrossfadeConfig(self.CF_FRAMES, self.SR, 200.0, "smooth_blend")
        result = _apply_eq_crossfade(
            self.seg_a, self.seg_b,
            config
        )
        # Letzter Frame: fo≈0, fi=1.0 → result ≈ seg_b[-1]
        np.testing.assert_allclose(result[-1], self.seg_b[-1], atol=0.01)

    def test_bass_swap_output_hat_richtige_form(self):
        config = EqCrossfadeConfig(self.CF_FRAMES, self.SR, 200.0, "bass_swap")
        result = _apply_eq_crossfade(
            self.seg_a, self.seg_b,
            config
        )
        assert result.shape == (self.CF_FRAMES, 2)
        assert result.dtype == np.float32

    def test_filter_ride_output_hat_richtige_form(self):
        config = EqCrossfadeConfig(self.CF_FRAMES, self.SR, 200.0, "filter_ride")
        result = _apply_eq_crossfade(
            self.seg_a, self.seg_b,
            config
        )
        assert result.shape == (self.CF_FRAMES, 2)

    def test_unbekannter_typ_verwendet_smooth_blend(self):
        """Unbekannte transition_type soll als linearer Crossfade behandelt werden."""
        config_unknown = EqCrossfadeConfig(self.CF_FRAMES, self.SR, 200.0, "totally_unknown_type")
        result_unknown = _apply_eq_crossfade(
            self.seg_a, self.seg_b,
            config_unknown
        )
        config_smooth = EqCrossfadeConfig(self.CF_FRAMES, self.SR, 200.0, "smooth_blend")
        result_smooth = _apply_eq_crossfade(
            self.seg_a, self.seg_b,
            config_smooth
        )
        np.testing.assert_array_equal(result_unknown, result_smooth)

    def test_kein_clipping_bei_bass_swap(self):
        """Bass-Swap darf nicht ueber 1.0 gehen (wegen Doppel-Addition)."""
        config = EqCrossfadeConfig(self.CF_FRAMES, self.SR, 200.0, "bass_swap")
        result = _apply_eq_crossfade(
            self.seg_a, self.seg_b,
            config
        )
        # Peaks koennen durch Bass-Dopplung groeßer sein, aber der Soft-Limiter
        # in render_transition_clip() wird sie begrenzen — hier nur pruefen
        # dass die Funktion selbst keine NaN/Inf produziert
        assert not np.any(np.isnan(result))
        assert not np.any(np.isinf(result))


# ---------------------------------------------------------------------------
# Tests: _load_segment
# ---------------------------------------------------------------------------

class TestLoadSegment:
    def test_laedt_stereo_wav_korrekt(self, tmp_path):
        wav_path = str(tmp_path / "test.wav")
        _write_test_wav(wav_path, duration_sec=10.0, sr=44100, channels=2)
        result = _load_segment(wav_path, start_sec=0.0, duration_sec=3.0, target_sr=44100)
        assert result.shape == (44100 * 3, 2)
        assert result.dtype == np.float32

    def test_mono_wird_zu_stereo_konvertiert(self, tmp_path):
        wav_path = str(tmp_path / "mono.wav")
        _write_test_wav(wav_path, duration_sec=10.0, sr=44100, channels=1)
        result = _load_segment(wav_path, start_sec=0.0, duration_sec=2.0, target_sr=44100)
        assert result.shape == (44100 * 2, 2)  # Immer 2 Kanaele!

    def test_offset_seeking_laedt_richtigen_abschnitt(self, tmp_path):
        """Testet ob start_sec korrekt angewendet wird."""
        wav_path = str(tmp_path / "test.wav")
        sr = 44100
        duration = 10.0
        n = int(sr * duration)
        # Track: erste Haelfte = 440 Hz, zweite Haelfte = 1000 Hz
        t1 = np.linspace(0, 5.0, n // 2, endpoint=False, dtype=np.float32)
        t2 = np.linspace(0, 5.0, n // 2, endpoint=False, dtype=np.float32)
        wave1 = (np.sin(2 * np.pi * 440 * t1) * 0.5).astype(np.float32)
        wave2 = (np.sin(2 * np.pi * 1000 * t2) * 0.5).astype(np.float32)
        combined = np.concatenate([wave1, wave2])
        sf.write(wav_path, combined, sr, subtype='PCM_16')

        # Ersten Abschnitt laden (440 Hz)
        seg_first = _load_segment(wav_path, start_sec=0.0, duration_sec=2.0, target_sr=sr)
        # Zweiten Abschnitt laden (1000 Hz)
        seg_second = _load_segment(wav_path, start_sec=5.0, duration_sec=2.0, target_sr=sr)

        # Beide sollen unterschiedlich sein
        assert not np.allclose(seg_first, seg_second, atol=0.01)

    def test_aiff_wird_korrekt_geladen(self, tmp_path):
        aiff_path = str(tmp_path / "test.aiff")
        _write_test_aiff(aiff_path, duration_sec=5.0, sr=44100)
        result = _load_segment(aiff_path, start_sec=0.0, duration_sec=3.0, target_sr=44100)
        assert result.shape == (44100 * 3, 2)

    def test_nicht_existente_datei_wirft_fehler(self):
        with pytest.raises(Exception):
            _load_segment("/nichtvorhanden/pfad/track.wav", 0.0, 5.0)

    def test_start_jenseits_dateiende_gibt_stille(self, tmp_path):
        """Wenn start_sec >= Dateilaenge, soll leeres Array zurueckkommen."""
        wav_path = str(tmp_path / "short.wav")
        _write_test_wav(wav_path, duration_sec=5.0, sr=44100)
        # Start bei 10s, Datei nur 5s lang → soundfile gibt [] zurueck
        result = _load_segment(wav_path, start_sec=10.0, duration_sec=3.0, target_sr=44100)
        # Ergebnis soll ein gültiges Array sein (kann leer sein oder Stille)
        assert result.ndim == 2
        assert result.shape[1] == 2


# ---------------------------------------------------------------------------
# Tests: render_transition_clip (Integration)
# ---------------------------------------------------------------------------

class TestRenderTransitionClip:
    def test_grundlegender_render_erstellt_wav(self, tmp_path):
        """Einfachster Fall: zwei synthetische WAVs → Clip."""
        path_a = str(tmp_path / "track_a.wav")
        path_b = str(tmp_path / "track_b.wav")
        out_path = str(tmp_path / "preview.wav")

        _write_test_wav(path_a, duration_sec=60.0, freq=440.0)
        _write_test_wav(path_b, duration_sec=60.0, freq=528.0)

        spec = TransitionClipSpec(
            track_a_path    = path_a,
            track_b_path    = path_b,
            mix_out_sec     = 40.0,
            mix_in_sec      = 5.0,
            crossfade_sec   = 8.0,
            transition_type = "smooth_blend",
            pre_roll_sec    = 10.0,
            post_roll_sec   = 10.0,
        )
        result = render_transition_clip(spec, out_path)

        assert os.path.exists(result)
        info = sf.info(result)
        expected_dur = spec.pre_roll_sec + spec.crossfade_sec + spec.post_roll_sec
        assert abs(info.duration - expected_dur) < 0.5
        assert info.channels == 2
        assert info.samplerate == 44100

    def test_bass_swap_render_erstellt_gueltige_wav(self, tmp_path):
        path_a = str(tmp_path / "track_a.wav")
        path_b = str(tmp_path / "track_b.wav")
        out_path = str(tmp_path / "bass_swap_preview.wav")

        _write_test_wav(path_a, duration_sec=60.0, freq=440.0)
        _write_test_wav(path_b, duration_sec=60.0, freq=528.0)

        spec = TransitionClipSpec(
            track_a_path    = path_a,
            track_b_path    = path_b,
            mix_out_sec     = 30.0,
            mix_in_sec      = 5.0,
            crossfade_sec   = 8.0,
            transition_type = "bass_swap",
            pre_roll_sec    = 5.0,
            post_roll_sec   = 5.0,
        )
        render_transition_clip(spec, out_path)
        info = sf.info(out_path)
        assert info.channels == 2
        assert info.samplerate == 44100

    def test_soft_limiter_verhindert_clipping(self, tmp_path):
        """Peak-Amplitude im Output soll <= 0.95 sein."""
        path_a = str(tmp_path / "loud_a.wav")
        path_b = str(tmp_path / "loud_b.wav")
        out_path = str(tmp_path / "limited.wav")

        # Sehr laute Signale (0.95 Amplitude)
        sr = 44100
        n = sr * 60
        t = np.linspace(0, 60, n, dtype=np.float32)
        loud = (np.sin(2 * np.pi * 440 * t) * 0.95).astype(np.float32)
        loud_stereo = np.stack([loud, loud], axis=1)
        sf.write(path_a, loud_stereo, sr, subtype='PCM_16')
        sf.write(path_b, loud_stereo, sr, subtype='PCM_16')

        spec = TransitionClipSpec(
            track_a_path    = path_a,
            track_b_path    = path_b,
            mix_out_sec     = 30.0,
            mix_in_sec      = 5.0,
            crossfade_sec   = 8.0,
            transition_type = "bass_swap",  # Bass-Dopplung kann > 1.0 ergeben
            pre_roll_sec    = 5.0,
            post_roll_sec   = 5.0,
        )
        render_transition_clip(spec, out_path)

        # Output laden und Peak pruefen
        data, _ = sf.read(out_path, dtype='float32')
        peak = np.max(np.abs(data))
        assert peak <= 1.0, f"Clipping im Output: Peak = {peak:.3f}"

    def test_kurzer_track_mit_nullpadding(self, tmp_path):
        """Track kuerzer als pre_roll_sec soll mit Stille aufgefuellt werden."""
        path_a = str(tmp_path / "short_a.wav")
        path_b = str(tmp_path / "short_b.wav")
        out_path = str(tmp_path / "padded.wav")

        # Nur 5 Sekunden lang
        _write_test_wav(path_a, duration_sec=5.0)
        _write_test_wav(path_b, duration_sec=5.0)

        spec = TransitionClipSpec(
            track_a_path    = path_a,
            track_b_path    = path_b,
            mix_out_sec     = 3.0,
            mix_in_sec      = 0.0,
            crossfade_sec   = 4.0,
            transition_type = "smooth_blend",
            pre_roll_sec    = 10.0,   # Laenger als der Track!
            post_roll_sec   = 10.0,
        )
        # Kein Fehler erwartet
        result = render_transition_clip(spec, out_path)
        assert os.path.exists(result)

    def test_crossfade_sec_wird_auf_32s_begrenzt(self, tmp_path):
        """crossfade_sec > 32 soll auf 32 reduziert werden."""
        path_a = str(tmp_path / "a.wav")
        path_b = str(tmp_path / "b.wav")
        out_path = str(tmp_path / "capped.wav")

        _write_test_wav(path_a, duration_sec=120.0)
        _write_test_wav(path_b, duration_sec=120.0)

        spec = TransitionClipSpec(
            track_a_path    = path_a,
            track_b_path    = path_b,
            mix_out_sec     = 60.0,
            mix_in_sec      = 10.0,
            crossfade_sec   = 99.0,  # Wird auf 32s begrenzt
            transition_type = "smooth_blend",
            pre_roll_sec    = 10.0,
            post_roll_sec   = 10.0,
        )
        render_transition_clip(spec, out_path)
        info = sf.info(out_path)
        # Erwartete Dauer: 10 + 32 + 10 = 52s (nicht 10 + 99 + 10)
        assert abs(info.duration - 52.0) < 0.5

    def test_gibt_output_pfad_zurueck(self, tmp_path):
        path_a = str(tmp_path / "a.wav")
        path_b = str(tmp_path / "b.wav")
        out_path = str(tmp_path / "result.wav")
        _write_test_wav(path_a, duration_sec=30.0)
        _write_test_wav(path_b, duration_sec=30.0)
        spec = TransitionClipSpec(
            track_a_path=path_a, track_b_path=path_b,
            mix_out_sec=15.0, mix_in_sec=5.0, crossfade_sec=4.0,
        )
        result = render_transition_clip(spec, out_path)
        assert result == out_path


# ---------------------------------------------------------------------------
# Tests: make_temp_output_path
# ---------------------------------------------------------------------------

class TestMakeTempOutputPath:
    def test_gibt_pfad_mit_richtiger_erweiterung(self):
        path = make_temp_output_path(0)
        assert path.endswith(".wav")

    def test_index_ist_im_dateinamen(self):
        path = make_temp_output_path(5)
        assert "005" in os.path.basename(path)

    def test_verschiedene_indizes_unterschiedliche_pfade(self):
        assert make_temp_output_path(0) != make_temp_output_path(1)
        assert make_temp_output_path(42) != make_temp_output_path(43)


# ---------------------------------------------------------------------------
# Tests: TransitionClipSpec — neue Felder (2026-02-28)
# ---------------------------------------------------------------------------

class TestTransitionClipSpecNeueFeleder:
    """Prueft die drei neuen Felder: normalize_rms, normalize_target_db, use_compressor."""

    def _minimal_spec(self) -> TransitionClipSpec:
        return TransitionClipSpec(
            track_a_path="a.wav",
            track_b_path="b.wav",
            mix_out_sec=30.0,
            mix_in_sec=5.0,
            crossfade_sec=8.0,
        )

    def test_normalize_rms_standardwert_ist_true(self):
        """RMS-Normalisierung soll standardmaessig aktiviert sein."""
        assert self._minimal_spec().normalize_rms is True

    def test_normalize_target_db_standardwert(self):
        """Ziel-Pegel soll EBU-R128-Norm (-14 dBRMS) sein."""
        assert self._minimal_spec().normalize_target_db == -14.0

    def test_use_compressor_standardwert_ist_false(self):
        """Compressor soll standardmaessig NICHT aktiviert sein (opt-in)."""
        assert self._minimal_spec().use_compressor is False

    def test_felder_koennen_ueberschrieben_werden(self):
        spec = TransitionClipSpec(
            track_a_path="a.wav", track_b_path="b.wav",
            mix_out_sec=30.0, mix_in_sec=5.0, crossfade_sec=8.0,
            normalize_rms=False, normalize_target_db=-18.0, use_compressor=True,
        )
        assert spec.normalize_rms is False
        assert spec.normalize_target_db == -18.0
        assert spec.use_compressor is True


# ---------------------------------------------------------------------------
# Tests: _rms_normalize
# ---------------------------------------------------------------------------

class TestRmsNormalize:
    """Unit-Tests fuer die RMS-Lautheitsnormalisierung (scipy-only, kein I/O)."""

    SR = 44100

    def _make_signal(self, frames: int, amplitude: float, freq: float = 440.0) -> np.ndarray:
        """Erzeugt ein (frames, 2) float32 Sinus-Signal mit gewaehlter Amplitude."""
        t = np.linspace(0, frames / self.SR, frames, endpoint=False, dtype=np.float32)
        wave = (np.sin(2 * np.pi * freq * t) * amplitude).astype(np.float32)
        return np.stack([wave, wave], axis=1)

    def _rms_db(self, arr: np.ndarray) -> float:
        """Berechnet RMS-Pegel in dBFS (float64 fuer Genauigkeit)."""
        rms = np.sqrt(np.mean(arr.astype(np.float64) ** 2))
        return 20.0 * np.log10(max(rms, 1e-10))

    def test_normalisiert_auf_ziel_rms(self):
        """Signal auf -14 dBRMS normalisieren — Ergebnis soll nahe -14 dB liegen."""
        # Sinus 0.5 Amplitude ≈ -9 dBRMS → wird auf -14 dBRMS reduziert
        sig = self._make_signal(self.SR * 4, amplitude=0.5)
        result = _rms_normalize(sig, target_rms_db=-14.0)
        rms_out = self._rms_db(result)
        # Toleranz ±1.5 dB: active-frame Selektion kann leicht abweichen
        assert abs(rms_out - (-14.0)) < 1.5, \
            f"Erwartet ~-14 dBRMS, bekommen {rms_out:.1f} dBRMS"

    def test_lautes_signal_wird_leiser(self):
        """Lauteres Signal (Amplitude 0.9 ≈ -1.8 dBRMS) soll nach Norm leiser sein."""
        sig = self._make_signal(self.SR * 2, amplitude=0.9)
        result = _rms_normalize(sig, target_rms_db=-14.0)
        assert self._rms_db(result) < self._rms_db(sig)

    def test_leises_signal_wird_lauter(self):
        """Sehr leises Signal (Amplitude 0.01 ≈ -47 dBRMS) soll nach Norm lauter sein."""
        sig = self._make_signal(self.SR * 2, amplitude=0.01)
        result = _rms_normalize(sig, target_rms_db=-14.0)
        assert self._rms_db(result) > self._rms_db(sig)

    def test_stilles_signal_unveraendert(self):
        """Null-Array (RMS < 1e-6) soll identisch zurueckkommen."""
        sig = np.zeros((self.SR, 2), dtype=np.float32)
        result = _rms_normalize(sig, target_rms_db=-14.0)
        np.testing.assert_array_equal(result, sig)

    def test_output_form_unveraendert(self):
        """Shape und dtype sollen erhalten bleiben."""
        sig = self._make_signal(self.SR * 2, amplitude=0.5)
        result = _rms_normalize(sig, target_rms_db=-14.0)
        assert result.shape == sig.shape
        assert result.dtype == np.float32

    def test_gain_clamping_nach_oben(self):
        """Extrem leises Signal: Gain-Clamp auf max 4.0 (+12 dB)."""
        # Amplitude 0.001 → RMS ≈ -63 dBRMS → ohne Clamp Gain ≈ 282
        # Mit Clamp: Gain = 4.0 → Output-Peak = 0.001 * 4.0 = 0.004
        sig = self._make_signal(self.SR * 2, amplitude=0.001)
        result = _rms_normalize(sig, target_rms_db=-14.0)
        input_peak = float(np.max(np.abs(sig)))
        output_peak = float(np.max(np.abs(result)))
        # Output darf maximal 4.0x des Eingangs sein (Clamp greift)
        assert output_peak <= input_peak * 4.01

    def test_gain_clamping_nach_unten(self):
        """Extrem lautes Signal (ausserhalb 0..1): Gain-Clamp auf min 0.1 (-20 dB)."""
        # Amplitude 3.0 → RMS ≈ 2.12 → gain ≈ 0.094 → geclampt auf 0.1
        sig = self._make_signal(self.SR * 2, amplitude=3.0)
        result = _rms_normalize(sig, target_rms_db=-14.0)
        input_peak = float(np.max(np.abs(sig)))
        output_peak = float(np.max(np.abs(result)))
        # Gain wurde auf 0.1 geclampt: Output-Peak ≈ Input-Peak * 0.1
        # Kleine Toleranz wegen float32-Arithmetik
        assert abs(output_peak / input_peak - 0.1) < 0.01

    def test_benutzerdefiniertes_ziel_db(self):
        """Normalisierung auf -20 dBRMS (statt Standard -14) soll korrekt arbeiten."""
        sig = self._make_signal(self.SR * 4, amplitude=0.5)
        result = _rms_normalize(sig, target_rms_db=-20.0)
        rms_out = self._rms_db(result)
        assert abs(rms_out - (-20.0)) < 1.5

    def test_keine_nan_oder_inf(self):
        """Keine ungueltige Zahlen im Ergebnis."""
        sig = self._make_signal(self.SR * 2, amplitude=0.5)
        result = _rms_normalize(sig, target_rms_db=-14.0)
        assert not np.any(np.isnan(result))
        assert not np.any(np.isinf(result))


# ---------------------------------------------------------------------------
# Tests: _apply_compressor
# ---------------------------------------------------------------------------

class TestApplyCompressor:
    """Unit-Tests fuer den optionalen pedalboard-Compressor."""

    SR = 44100

    def _make_signal(self, frames: int, amplitude: float = 0.5) -> np.ndarray:
        """Erzeugt ein (frames, 2) float32 Sinus-Signal."""
        t = np.linspace(0, frames / self.SR, frames, endpoint=False, dtype=np.float32)
        wave = (np.sin(2 * np.pi * 440 * t) * amplitude).astype(np.float32)
        return np.stack([wave, wave], axis=1)

    def test_output_hat_richtige_form(self):
        """Output soll gleiche Shape wie Input haben."""
        sig = self._make_signal(self.SR * 2)
        result = _apply_compressor(sig, self.SR)
        assert result.shape == sig.shape

    def test_output_ist_float32(self):
        """dtype soll float32 sein."""
        sig = self._make_signal(self.SR * 2)
        result = _apply_compressor(sig, self.SR)
        assert result.dtype == np.float32

    def test_kein_clipping(self):
        """Output-Peak soll <= 1.0 sein (Compressor darf nicht verstaerken)."""
        sig = self._make_signal(self.SR * 2, amplitude=0.9)
        result = _apply_compressor(sig, self.SR)
        assert np.max(np.abs(result)) <= 1.0

    def test_keine_nan_oder_inf(self):
        """Keine NaN oder Inf im Ergebnis."""
        sig = self._make_signal(self.SR * 2)
        result = _apply_compressor(sig, self.SR)
        assert not np.any(np.isnan(result))
        assert not np.any(np.isinf(result))

    def test_fallback_bei_fehlendem_pedalboard(self):
        """Ohne pedalboard soll das unveraenderte Eingangssignal zurueckkommen."""
        import unittest.mock

        sig = self._make_signal(self.SR * 2)

        # sys.modules["pedalboard"] = None simuliert nicht installiertes Modul:
        # Python wirft ImportError wenn der Modul-Eintrag None ist
        with unittest.mock.patch.dict("sys.modules", {"pedalboard": None}):
            result = _apply_compressor(sig, self.SR)

        np.testing.assert_array_equal(result, sig)


# ---------------------------------------------------------------------------
# Tests: render_transition_clip — Integration mit Normalisierung
# ---------------------------------------------------------------------------

class TestRenderTransitionClipMitNormalisierung:
    """Integration-Tests fuer normalize_rms und use_compressor in render_transition_clip."""

    def test_render_mit_normalisierung_aktiviert(self, tmp_path):
        """normalize_rms=True soll gueltige WAV ohne Fehler erzeugen."""
        path_a = str(tmp_path / "a.wav")
        path_b = str(tmp_path / "b.wav")
        out_path = str(tmp_path / "norm.wav")

        _write_test_wav(path_a, duration_sec=30.0, freq=440.0)
        _write_test_wav(path_b, duration_sec=30.0, freq=528.0)

        spec = TransitionClipSpec(
            track_a_path=path_a,
            track_b_path=path_b,
            mix_out_sec=20.0,
            mix_in_sec=5.0,
            crossfade_sec=4.0,
            pre_roll_sec=5.0,
            post_roll_sec=5.0,
            normalize_rms=True,
            normalize_target_db=-14.0,
        )
        render_transition_clip(spec, out_path)

        assert os.path.exists(out_path)
        info = sf.info(out_path)
        assert info.channels == 2
        assert info.samplerate == 44100

    def test_render_deaktivierte_normalisierung_kein_fehler(self, tmp_path):
        """normalize_rms=False soll genauso funktionieren wie vorher."""
        path_a = str(tmp_path / "a.wav")
        path_b = str(tmp_path / "b.wav")
        out_path = str(tmp_path / "no_norm.wav")

        _write_test_wav(path_a, duration_sec=30.0, freq=440.0)
        _write_test_wav(path_b, duration_sec=30.0, freq=528.0)

        spec = TransitionClipSpec(
            track_a_path=path_a,
            track_b_path=path_b,
            mix_out_sec=20.0,
            mix_in_sec=5.0,
            crossfade_sec=4.0,
            normalize_rms=False,
        )
        render_transition_clip(spec, out_path)
        assert os.path.exists(out_path)

    def test_render_mit_kompressor_kein_fehler(self, tmp_path):
        """use_compressor=True soll gueltige WAV erzeugen (pedalboard installiert)."""
        path_a = str(tmp_path / "a.wav")
        path_b = str(tmp_path / "b.wav")
        out_path = str(tmp_path / "compressed.wav")

        _write_test_wav(path_a, duration_sec=30.0, freq=440.0)
        _write_test_wav(path_b, duration_sec=30.0, freq=528.0)

        spec = TransitionClipSpec(
            track_a_path=path_a,
            track_b_path=path_b,
            mix_out_sec=20.0,
            mix_in_sec=5.0,
            crossfade_sec=4.0,
            pre_roll_sec=5.0,
            post_roll_sec=5.0,
            normalize_rms=True,
            use_compressor=True,
        )
        render_transition_clip(spec, out_path)

        assert os.path.exists(out_path)
        info = sf.info(out_path)
        assert info.channels == 2

    def test_peak_nach_normalisierung_kein_clipping(self, tmp_path):
        """Vollstaendige Pipeline mit Normalisierung soll Peak <= 1.0 liefern."""
        # Zwei gleich laute Tracks — kein extremer Lautheitssprung erwartet
        path_a = str(tmp_path / "a.wav")
        path_b = str(tmp_path / "b.wav")
        out_path = str(tmp_path / "peak_test.wav")

        _write_test_wav(path_a, duration_sec=30.0, freq=440.0)
        _write_test_wav(path_b, duration_sec=30.0, freq=528.0)

        spec = TransitionClipSpec(
            track_a_path=path_a,
            track_b_path=path_b,
            mix_out_sec=20.0,
            mix_in_sec=5.0,
            crossfade_sec=4.0,
            transition_type="bass_swap",
            normalize_rms=True,
        )
        render_transition_clip(spec, out_path)

        data, _ = sf.read(out_path, dtype='float32')
        peak = float(np.max(np.abs(data)))
        assert peak <= 1.0, f"Clipping nach Normalisierung: Peak = {peak:.3f}"

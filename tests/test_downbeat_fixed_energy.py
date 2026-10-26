"""Gleiche Beatenergie darf durch Fensterrand oder Samplezahl keinen Akzent erhalten."""

import numpy as np
import pytest

from hpg_core import downbeat as d


SR = 22050
BPM = 132.0
IBI = 60.0 / BPM
ONE = 0.173


def _signal(accent=False):
    """Eigene bekannte Synthese: Chirp-Kicks und optional echte Viererakzente."""
    audio = np.zeros(round(48.0 * SR))
    beats = np.arange(ONE, 48.0 - 0.3, IBI)
    t = np.arange(round(0.27 * SR)) / SR
    envelope = (1 - np.exp(-t / 0.001)) * np.exp(-t / 0.065)
    for index, onset in enumerate(beats):
        amplitude = 1.5 if accent and index % 4 == 0 else 0.65
        kick = amplitude * envelope * np.sin(2 * np.pi * (94 * t - 120 * t * t))
        start = round(onset * SR)
        audio[start:start + len(kick)] += kick
        if accent and index % 4 == 0:
            chord_t = np.arange(min(round(4 * IBI * SR), len(audio) - start)) / SR
            root = [220.0, 277.18][(index // 4) % 2]
            chord = sum(np.sin(2 * np.pi * root * ratio * chord_t) for ratio in (1, 1.25, 1.5))
            audio[start:start + len(chord_t)] += 0.05 * chord * np.minimum(chord_t / 0.002, 1)
    return audio, beats


def _estimate(monkeypatch, audio, beats):
    frames = np.rint(beats * SR / d.HOP_LENGTH).astype(int)
    monkeypatch.setattr(d.librosa.beat, "beat_track", lambda **kwargs: (BPM, frames))
    diagnostics = {}
    result = d.estimate_first_downbeat(audio, SR, BPM, diagnostics=diagnostics, _allow_metric_retry=False)
    return result, diagnostics


def test_verkuerztes_endfenster_erfindet_keine_takteins(monkeypatch):
    audio, beats = _signal()
    audio = audio[:round((beats[-1] + 0.27) * SR)]
    (_, confidence), _ = _estimate(monkeypatch, audio, beats)
    assert confidence < d.DOWNBEAT_RELIABLE_MIN


@pytest.mark.parametrize("silent_beats", [1, 2, 3])
def test_stille_nach_gleichfoermigen_kicks_erfindet_keine_takteins(monkeypatch, silent_beats):
    audio, beats = _signal()
    length = round((beats[-1] + 0.27) * SR) + round(silent_beats * IBI * SR)
    padded = np.zeros(length)
    count = min(length, len(audio))
    padded[:count] = audio[:count]
    (_, confidence), _ = _estimate(monkeypatch, padded, beats)
    assert confidence < d.DOWNBEAT_RELIABLE_MIN


def test_gleichfoermige_kicks_mit_dc_bleiben_ohne_taktakzent(monkeypatch):
    audio, beats = _signal()
    (_, confidence), _ = _estimate(monkeypatch, audio + 0.1, beats)
    assert confidence < d.DOWNBEAT_RELIABLE_MIN


@pytest.mark.parametrize("change", ["exact", "late", "missing", "extra", "pause"])
def test_echter_viererakzent_bleibt_trotz_trackerluecken_erhalten(monkeypatch, change):
    audio, beats = _signal(accent=True)
    if change == "late":
        beats += 0.120
    elif change == "missing":
        beats = np.delete(beats, [13, 35, 57])
    elif change == "extra":
        beats = np.sort(np.r_[beats, beats[40] + 0.2 * IBI])
    elif change == "pause":
        audio[16 * SR:32 * SR] = 0.0
    (anchor, confidence), _ = _estimate(monkeypatch, audio, beats)
    assert confidence >= d.DOWNBEAT_RELIABLE_MIN
    assert anchor == pytest.approx(ONE, abs=d.EXACT_BEAT_SYNC_TOLERANCE_SECONDS)


@pytest.mark.parametrize("active_seconds,reason", [(0, "noactivity"), (2.5, "fewbeats")])
def test_fehlende_aktivitaet_bleibt_gesperrt(monkeypatch, active_seconds, reason):
    audio, beats = _signal(accent=True)
    audio[int(active_seconds * SR):] = 0.0
    result, diagnostics = _estimate(monkeypatch, audio, beats)
    assert result == (0.0, 0.0)
    assert diagnostics["reason"] == reason


@pytest.mark.parametrize("start", [0.0, 0.01, 0.499, 0.999, 1.0, 37.125, 1024.875])
@pytest.mark.parametrize("width", [0.125, 0.5, 1.0, IBI * SR])
def test_fraktionale_beobachtung_erhaelt_konstantes_signal(start, width):
    # Konvention: y² ist innerhalb jeder Samplezelle konstant.
    audio = np.full(40000, 0.37)
    end = start + width
    energy = d._sample_energy_integral(audio, start, end)
    assert energy / (end - start) == pytest.approx(0.37 ** 2, abs=1e-12, rel=0)


@pytest.mark.parametrize("dc", [0.0, 0.1])
def test_gleiche_pulsenergie_bleibt_bei_wechselnder_samplezahl_gleich(dc):
    # Analytische Integralprobe; nicht als realistischer Audio-DSP-Test verwendet.
    audio = np.full(22000, dc)
    pulse = np.array([0.1, 0.3, 0.6, 0.4, 0.2, -0.1, -0.4, -0.2])
    audio[100:108] += pulse
    audio[10123:10131] += pulse
    start, width = 0.123, IBI * SR
    first = d._sample_energy_integral(audio, start, start + width)
    second = d._sample_energy_integral(audio, start + width, start + 2 * width)
    assert first / width == pytest.approx(second / width, abs=1e-12, rel=0)


@pytest.mark.parametrize("start,end,expected", [(0.0, 3.0, 3.0), (2.75, 3.0, 0.25), (1.2, 1.4, 0.2)])
def test_integral_beachtet_exakte_endgrenze_und_subsamplefenster(start, end, expected):
    assert d._sample_energy_integral(np.ones(3), start, end) == pytest.approx(expected, abs=1e-12, rel=0)


@pytest.mark.parametrize("start,end", [(-0.1, 1.0), (2.0, 3.1), (1.0, 1.0), (2.0, 1.0), (np.nan, 1.0), (0.0, np.inf)])
def test_unvollstaendige_oder_ungueltige_intervalle_bleiben_unbekannt(start, end):
    assert d._sample_energy_integral(np.ones(3), start, end) is None


def test_unvollstaendiger_sechzehnter_beat_erfuellt_mindestzahl_nicht(monkeypatch):
    # Kontrollfluss mit bewusst kontrollierten Merkmalen, kein musikalischer Nachweis.
    times = 0.2 + np.arange(16) * 0.5
    frames = np.rint(times * SR / d.HOP_LENGTH).astype(int)
    monkeypatch.setattr(d.librosa.beat, "beat_track", lambda **kwargs: (120.0, frames))
    monkeypatch.setattr(d, "_beat_phase_from_fold", lambda *_args: (0.2, 0.9))
    monkeypatch.setattr(d.librosa.onset, "onset_strength", lambda **kwargs: np.ones(400))
    monkeypatch.setattr(d.librosa.feature, "chroma_stft", lambda **kwargs: np.ones((12, 400)))
    diagnostics = {}
    result = d.estimate_first_downbeat(np.ones(8 * SR), SR, 120.0, diagnostics=diagnostics, _allow_metric_retry=False)
    assert result == (0.0, 0.0)
    assert diagnostics["beats_used"] == 15
    assert (diagnostics["reason"], diagnostics["stage"]) == ("fewbeats", "trim")

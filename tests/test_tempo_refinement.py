"""Feintempo-Kandidaten bleiben durch echte Signale und negative Faelle begrenzt."""

import importlib

import numpy as np
import pytest


FACTORS = (0.5, 2 / 3, 0.75, 1.0, 4 / 3, 1.5, 2.0)
SR = 22050


def _pulses(bpm, duration=32.0):
    audio = np.zeros(round(duration * SR))
    t = np.arange(round(0.16 * SR)) / SR
    pulse = np.sin(2 * np.pi * 65 * t) * np.exp(-t / 0.03)
    for onset in np.arange(0.3, duration - 0.17, 60.0 / bpm):
        start = round(onset * SR)
        audio[start:start + len(pulse)] += pulse
    return audio


@pytest.fixture
def estimate():
    # Kein Collectionfehler vor erstmaliger Produktimplementierung.
    return importlib.import_module("hpg_core.tempo_refinement").estimate_fine_tempo


@pytest.mark.parametrize("gain", [0.001, 1.0, 4.0, -1.0])
@pytest.mark.parametrize("prior", [136.0, 138.5])
def test_echter_kandidat_ist_gainunabhaengig(estimate, gain, prior):
    result = estimate(_pulses(138.0) * gain, SR, prior, 112.0, factor_candidates=FACTORS)
    assert result is not None
    bpm, phase = result
    assert bpm == pytest.approx(138.0, abs=0.001, rel=0)
    assert np.isfinite(phase)
    assert 0.0 <= phase < 60.0 / bpm


@pytest.mark.parametrize("prior", [69.0, 276.0, 92.0])
def test_falscher_faktor_wird_nicht_als_feinkorrektur_uebernommen(estimate, prior):
    assert estimate(_pulses(138.0), SR, prior, 112.0, factor_candidates=FACTORS) is None


@pytest.mark.parametrize("kind", ["silence", "dc", "nan", "short", "noise"])
def test_ungeeignetes_training_liefert_keinen_kandidaten(estimate, kind):
    audio = _pulses(138.0)
    if kind == "silence":
        audio[:] = 0.0
    elif kind == "dc":
        audio[:] = 0.7
    elif kind == "nan":
        audio[100] = np.nan
    elif kind == "short":
        audio = audio[:SR]
    else:
        audio = np.random.default_rng(9128).normal(size=len(audio))
    assert estimate(audio, SR, 136.0, 112.0, factor_candidates=FACTORS) is None


def test_widerspruechliche_trainingshaelften_verwerfen_kandidaten(estimate):
    audio = np.r_[_pulses(138.0, 16.0), _pulses(140.0, 16.0)]
    assert estimate(audio, SR, 136.0, 112.0, factor_candidates=FACTORS) is None


@pytest.mark.parametrize("kind", ["stereo", "inf", "zero_sr", "nan_sr", "nan_prior", "zero_prior", "inf_horizon", "negative_horizon"])
def test_ungueltige_kernparameter_erzeugen_keinen_kandidaten(estimate, kind):
    audio, sr, prior, horizon = _pulses(138.0), SR, 136.0, 112.0
    if kind == "stereo":
        audio = np.column_stack([audio, audio])
    elif kind == "inf":
        audio[20] = np.inf
    elif kind == "zero_sr":
        sr = 0
    elif kind == "nan_sr":
        sr = np.nan
    elif kind == "nan_prior":
        prior = np.nan
    elif kind == "zero_prior":
        prior = 0.0
    elif kind == "inf_horizon":
        horizon = np.inf
    else:
        horizon = -1.0
    assert estimate(audio, sr, prior, horizon, factor_candidates=FACTORS) is None

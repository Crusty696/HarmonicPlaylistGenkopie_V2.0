"""Neue Attack-Messung: Zeitverschiebungen erhalten, Stille sperren."""
import numpy as np
import pytest
from hpg_core.ai_models.native_audio_phase import measure


@pytest.mark.parametrize('shift', [0., .025, -.025])
def test_measures_attack_without_snapping_to_reference(shift):
    sr, period, expected = 8000, .5, .2
    y = np.zeros(sr*12)
    t = np.arange(int(sr*.08))/sr
    kick = np.sin(2*np.pi*1700*t)*np.exp(-90*t)
    bass = np.sin(2*np.pi*65*t)*np.exp(-30*t)*4
    for beat in np.arange(expected, 11.5, period):
        start = round((beat+shift)*sr)
        y[start:start+len(kick)] += kick
        offbeat = round((beat+.25)*sr)
        y[offbeat:offbeat+len(bass)] += bass
    measured, lock = measure(y, sr, period, expected)
    assert measured is not None and lock > .1
    assert abs(measured-expected-shift) < .006


def test_silence_and_noise_do_not_confirm_native_grid():
    assert measure(np.zeros(96000), 8000, .5, .2)[0] is None
    noise = np.random.default_rng(37).normal(size=96000)
    assert measure(noise, 8000, .5, .2)[0] is None


def test_native_downbeat_voting_uses_attack_measurement(monkeypatch):
    from hpg_core import downbeat
    from hpg_core.ai_models import native_audio_phase
    sr, period = 8000, .5
    audio = np.zeros(sr * 16)
    times = np.arange(.2, 15.8, period)
    pulse = np.sin(2*np.pi*1700*np.arange(640)/sr) * np.exp(-90*np.arange(640)/sr)
    for index, beat in enumerate(times):
        start = round(beat * sr)
        audio[start:start+len(pulse)] += pulse * (1. if index % 4 == 0 else .4)
    calls = []
    def measured(*args, **kwargs):
        calls.append(args[3])
        return measure(*args, **kwargs)
    monkeypatch.setattr(native_audio_phase, 'measure', measured)
    monkeypatch.setattr(downbeat, '_beat_phase_from_fold',
                        lambda *a: pytest.fail('Nativer Pfad darf nicht auf Bass-Fold wechseln'))
    events = [dict(time_s=float(t), position=i % 4 + 1, observed=True)
              for i, t in enumerate(times)]
    downbeat.estimate_first_downbeat(audio, sr, 120., external_beats=events,
        phase_method='native_attack_v1', _allow_metric_retry=False)
    assert calls == [pytest.approx(.2)]


@pytest.mark.parametrize('shift', [0., .025])
def test_native_attack_renderer_preserves_strict_sync(shift):
    from hpg_core.transition_renderer import _synchronize_and_verify_kicks, BeatSyncError
    sr = 8000
    a, b = np.zeros(sr*12), np.zeros(sr*12)
    t = np.arange(640)/sr
    kick = np.sin(2*np.pi*1700*t)*np.exp(-90*t)
    for beat in np.arange(.2, 11.5, .5):
        for signal, offset in ((a, 0.), (b, shift)):
            start = round((beat+offset)*sr)
            signal[start:start+len(kick)] += kick
    a, b = np.column_stack((a,a)), np.column_stack((b,b))
    def render():
        return _synchronize_and_verify_kicks(a,b,sr,120.,len(a),
            reference_phases=(.2,.2), reference_methods=('native_attack_v1',)*2)
    if shift:
        with pytest.raises(BeatSyncError):
            render()
    else:
        np.testing.assert_allclose(render(), b)


@pytest.mark.parametrize('seed', range(38, 46))
def test_weak_attack_requires_repeatability_not_noise(seed):
    noise = np.random.default_rng(seed).normal(size=128000)
    assert measure(noise, 8000, .5, .2)[0] is None


def test_candidate_audio_gate_binds_cache_to_source_and_rejects_offset(tmp_path):
    import soundfile as sf
    from types import SimpleNamespace
    from hpg_core.ai_models.native_audio_phase import supports_window
    from hpg_core.ai_models.native_phrase_worker import _source_identity
    sr = 8000
    audio = np.zeros(sr*10)
    t = np.arange(640)/sr
    kick = np.sin(2*np.pi*1700*t)*np.exp(-90*t)
    for beat in np.arange(.2,9.5,.5):
        start = round(beat*sr)
        audio[start:start+len(kick)] += kick
    path = tmp_path/'candidate.wav'
    sf.write(path,audio,sr)
    track = SimpleNamespace(filePath=str(path), duration=10., bpm=120., first_downbeat=.2,
        native_beat_analysis=dict(source_identity=_source_identity(path)))
    assert supports_window(track,0.,8.)
    track.first_downbeat = .175
    assert not supports_window(track,0.,8.)
    track.first_downbeat = .2
    sf.write(path,np.zeros(sr*9),sr)
    assert not supports_window(track,0.,8.)

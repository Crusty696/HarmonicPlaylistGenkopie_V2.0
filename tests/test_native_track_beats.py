"""Native Gesamtgrid-Übernahme und Sperren; keine Modelle oder Originalmusik."""
from copy import deepcopy

import numpy as np
import pytest

from hpg_core import analysis, caching
from hpg_core.ai_models import native_track_beats as native
from tests.test_cue_pipeline_integration import pipeline
from tests.test_neural_anchor_integration import setup_adoption


def snapshot(duration=48.):
    return dict(status='ok', reason=None, contract=native.CONTRACT,
        executable_sha256=native.SHA256, tensorflow_sha256=native.TF_SHA256,
        model_id='model7', model_hashes=deepcopy(native.MODEL_HASHES['model7']),
        source_identity=[100, 200, 1, 2], sample_rate=44100, frames=int(duration*44100),
        bpm=120., grid=[dict(pos=round((.005+i*.5)*44100), numBar=i%4+1, bpm=12000)
                       for i in range(int(duration*2))],
        first_downbeat=round(.005*44100)/44100, musically_verified=False,
        input_convention='soundfile-normalized-stereo-float32')


@pytest.mark.parametrize('fast', [True, False])
def test_both_producers_use_native_grid_without_window_rerun(pipeline, monkeypatch, fast):
    path, importer, phrases = setup_adoption(pipeline, monkeypatch, fast)
    data = snapshot()
    context = dict(analysis=data, accepted=True, transient=False,
        validation=analysis.BeatgridValidation('verified', 3, 1., 'verified'),
        diagnostics={'decode_failures': []})
    monkeypatch.setattr(analysis, '_prepare_native_beats', lambda *a: context)
    monkeypatch.setattr(analysis, '_collect_beat_windows', lambda *a: pytest.fail('Redundant model windows'))
    monkeypatch.setattr(analysis, '_resolve_track_tempo', lambda *a, **k: pytest.fail('Native tempo overwritten'))
    track = analysis.analyze_track(str(path))
    assert track is not None
    assert track.first_downbeat == data['first_downbeat']
    assert track.bpm == data['bpm']
    assert track.native_beat_analysis == data
    assert track.measurement_diagnostics['anchor']['method'] == 'native_rekordbox'
    assert track.neural_analysis['beat_windows'] == []
    assert track.phrases == []  # Native Herkunft darf kein importiertes PSSI vortäuschen.
    serialized = caching.track_to_dict(track)
    restored = caching.dict_to_track(serialized)
    assert restored.native_beat_analysis == data
    serialized['native_beat_analysis']['first_downbeat'] += .1
    with pytest.raises(caching.CacheValidationError):
        caching.dict_to_track(serialized)


@pytest.mark.parametrize('status,accepted', [('verified', True), ('mismatch', False)])
def test_native_grid_does_not_bypass_audio_gate(monkeypatch, status, accepted):
    monkeypatch.setenv('HPG_NATIVE_BEAT', '1')
    monkeypatch.setattr(native, 'analyze', lambda *a, **k: snapshot())
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k:
        analysis.BeatgridValidation(status, 3, 1. if accepted else 10.6))
    result = analysis._prepare_native_beats('unused.wav', 48., np.ones(32), 44100)
    assert result['accepted'] is accepted
    assert result['analysis']['musically_verified'] is False


def test_native_variable_grid_is_not_silently_straightened(monkeypatch):
    monkeypatch.setenv('HPG_NATIVE_BEAT', '1')
    data = snapshot()
    data['grid'][20]['pos'] += 4410
    monkeypatch.setattr(native, 'analyze', lambda *a, **k: data)
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', lambda *a, **k: pytest.fail('Unsupported geometry'))
    assert not analysis._prepare_native_beats('unused.wav', 48., np.ones(32), 44100)['accepted']


@pytest.mark.parametrize('field,value', [('executable_sha256', '0'*64),
    ('tensorflow_sha256', '0'*64), ('frames', 44100), ('musically_verified', True),
    ('first_downbeat', True), ('bpm', float('nan'))])
def test_rejects_corrupt_native_provenance(field, value):
    data = snapshot()
    data[field] = value
    with pytest.raises(ValueError):
        native.validate_snapshot(data, duration=48.)

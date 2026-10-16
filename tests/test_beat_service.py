"""Beat/Cue-Lane-Vertrag mit synthetischem PCM und Modell-Doubles."""
from contextlib import contextmanager
import time

import numpy as np
import pytest

from hpg_core.ai_models import cue_service as cs
from hpg_core.ai_models import beat_predictor as bp


@pytest.fixture
def fake_models(monkeypatch):
    from hpg_core.ai_models import native_beat_decoder
    def native(values):
        frames = np.flatnonzero(values.sum(axis=1) > .5)
        return {'bpm': 120., 'grid': [{'pos': int(frame)*441, 'numBar': index % 4 + 1}
                          for index, frame in enumerate(frames)]}
    monkeypatch.setattr(native_beat_decoder, 'decode', native)
    calls = []
    def infer(audio, sr, *, model_directory, model_id):
        calls.append((model_id, sr))
        values = np.full((len(audio) * 100 // sr, 2), .001, np.float32)
        for number, frame in enumerate(range(0, len(values), 50)):
            values[frame, 1 if number % 4 == 0 else 0] = .97
        return dict(activations=values, metadata=dict(
            model_hashes=bp.MODEL_HASHES[model_id], duration_s=len(audio)/sr))
    monkeypatch.setattr(bp, 'infer_beat_activations', infer)
    return calls


def test_beat_wire_and_absolute_decoder(fake_models):
    audio = np.zeros(44100 * 4, np.float32)
    payload = cs.encode_beat_audio(audio, 44100, window_start_s=20., track_duration_s=40.)
    header, decoded = cs.decode_beat_audio(payload)
    assert np.array_equal(audio, decoded)
    header['config'] = cs.model_config()
    result = cs._load(cs.handle_models(cs._pack(header, decoded.tobytes())))
    cs._validate_beat_window(result)
    assert [item['model_id'] for item in result['results']] == ['model7', 'model8']
    for item in result['results']:
        assert item['status'] == 'ok'
        assert all(20 <= beat['time_s'] < 24 for beat in item['decoder']['beats'])
        assert item['decoder']['verified'] is False
    assert fake_models == [('model7', 44100), ('model8', 44100)]


def test_bad_wire_and_unknown_dispatcher():
    payload = cs.encode_beat_audio(np.zeros(44100, np.float32), 44100,
                                   window_start_s=0., track_duration_s=2.)
    with pytest.raises(ValueError):
        cs.decode_beat_audio(payload[:-1])
    header, audio = cs.decode_beat_audio(payload)
    header['job'] = 'arbitrary_callable'
    with pytest.raises(ValueError):
        cs.handle_models(cs._pack(header, audio.tobytes()))


def test_owner_reuses_one_lane_for_cue_and_beat(monkeypatch, fake_models):
    lanes = []
    class Lane:
        pid = 123
        def __init__(self, module, handler, *, memory_limit_bytes):
            from hpg_core.config import MODEL_PROCESS_MEMORY_LIMIT_BYTES
            assert memory_limit_bytes == MODEL_PROCESS_MEMORY_LIMIT_BYTES
            assert handler == 'handle_models'
            lanes.append(self)
        def call(self, payload, *, deadline, cancel_event):
            assert deadline > time.monotonic()
            return cs.handle_models(payload)
        def close(self):
            pass
    from hpg_core.ai_models import cue_predictor
    monkeypatch.setattr(cs, 'OwnedModelProcess', Lane)
    monkeypatch.setattr(cue_predictor, 'score_phrase_candidates',
                        lambda audio, sr, candidates, **kwargs: cs._diagnostics(candidates, 'missing_window_context'))
    with cs.CueServiceOwner() as owner:
        client = owner.register_generation()
        audio = np.zeros(44100 * 4, np.float32)
        args = dict(window_start_s=0., track_duration_s=4.)
        client.score(audio, 44100, [dict(start_s=0., kind=1, mood=1)], verified_grid=True, **args)
        result = client.score_beats(audio, 44100, **args)
        assert result['results'][0]['status'] == 'ok'
        owner.cancel_generation(client.generation)
        other = owner.register_generation()
        assert other.score_beats(audio, 44100, **args)['results'][1]['status'] == 'ok'
        assert len(lanes) == 1


def test_lazy_track_context_does_not_create_owner(monkeypatch):
    monkeypatch.setattr(cs, 'CueServiceOwner', lambda: pytest.fail('Cachehit created owner'))
    @cs.track_session
    def cached():
        return 'cache'
    assert cached() == 'cache'


def test_track_sessions_share_client_and_original_deadline(monkeypatch):
    calls = []
    class Owner:
        def register_generation(self):
            calls.append('register')
            return self
        def close(self):
            calls.append('close')
    monkeypatch.setattr(cs, 'CueServiceOwner', Owner)
    @cs.track_session
    def analyze():
        with cs.session() as first, cs.session() as second:
            assert first is second
            assert cs._local.deadline == deadline
    deadline = time.monotonic() + 10
    with cs.request_deadline(deadline):
        analyze()
    assert calls == ['register', 'close']


def test_missing_model_deterministic_but_runtime_failure_transient(monkeypatch):
    def missing(*args, **kwargs):
        try:
            raise FileNotFoundError('test')
        except FileNotFoundError as error:
            raise bp.BeatModelUnavailable('model_files: FileNotFoundError') from error
    monkeypatch.setattr(bp, 'infer_beat_activations', missing)
    payload = cs.encode_beat_audio(np.zeros(44100, np.float32), 44100,
                                   window_start_s=0., track_duration_s=1.)
    header, audio = cs.decode_beat_audio(payload)
    header['config'] = cs.model_config()
    result = cs._load(cs.handle_models(cs._pack(header, audio.tobytes())))
    assert all(item['status'] == 'missing_model' for item in result['results'])
    value = dict(version=2, fingerprint='a'*64, windows=[], beat_windows=[result])
    cs.validate_neural_analysis(value)
    assert not cs.transient_failure(value)
    result['results'][0]['status'] = 'model_error'
    assert cs.transient_failure(value)


def test_fingerprint_includes_beat_files_and_runtime_versions(tmp_path, monkeypatch):
    config = cs.model_config()
    config.update(beat_model7_path=str(tmp_path / 'model7'), beat_model8_path=str(tmp_path / 'model8'))
    first = cs.fingerprint(config)
    target = tmp_path / 'model7' / 'saved_model.pb'
    target.parent.mkdir()
    target.write_bytes(b'identity only')
    second = cs.fingerprint(config)
    monkeypatch.setattr(cs, '_runtime_versions', lambda: {'changed': '1'})
    assert len({first, second, cs.fingerprint(config)}) == 3


def test_model7_error_keeps_model8_result(monkeypatch, fake_models):
    original = bp.infer_beat_activations
    def partial(audio, sr, *, model_directory, model_id):
        if model_id == 'model7':
            raise bp.BeatModelUnavailable('synthetic_runtime_error')
        return original(audio, sr, model_directory=model_directory, model_id=model_id)
    monkeypatch.setattr(bp, 'infer_beat_activations', partial)
    payload = cs.encode_beat_audio(np.zeros(44100 * 4, np.float32), 44100,
                                   window_start_s=0., track_duration_s=4.)
    header, audio = cs.decode_beat_audio(payload)
    header['config'] = cs.model_config()
    result = cs._load(cs.handle_models(cs._pack(header, audio.tobytes())))
    assert [item['status'] for item in result['results']] == ['model_error', 'ok']


def test_expired_submit_deadline_does_not_start_lane():
    with cs.CueServiceOwner() as owner:
        client = owner.register_generation()
        with cs.request_deadline(time.monotonic()-1):
            result = client.score_beats(np.zeros(44100, np.float32), 44100,
                                       window_start_s=0., track_duration_s=1.)
        assert owner.model_pid is None
        assert all(item['status'] == 'service_error' for item in result['results'])


def test_absolute_times_do_not_change_scores_or_duration(fake_models):
    results = []
    for start in (0., 19.):
        payload = cs.encode_beat_audio(np.zeros(44100 * 4, np.float32), 44100,
                                       window_start_s=start, track_duration_s=60.)
        header, audio = cs.decode_beat_audio(payload)
        header['config'] = cs.model_config()
        results.append(cs._load(cs.handle_models(cs._pack(header, audio.tobytes()))))
    left, right = [window['results'][0]['decoder'] for window in results]
    assert left['algorithm_version'] == right['algorithm_version']
    assert left['covered_duration_s'] == right['covered_duration_s']
    assert right['first_downbeat'] == left['first_downbeat'] + 19
    assert right['bpm'] == left['bpm']
    results[1]['results'][0]['decoder']['beats'][0]['time_s'] = 0.
    with pytest.raises(ValueError):
        cs._validate_beat_window(results[1])


@pytest.mark.parametrize('mutation', ['boolean_anchor', 'short_coverage'])
def test_rejects_decoder_contract_mutations(fake_models, mutation):
    payload = cs.encode_beat_audio(np.zeros(44100 * 4, np.float32), 44100,
                                   window_start_s=0., track_duration_s=4.)
    header, audio = cs.decode_beat_audio(payload)
    header['config'] = cs.model_config()
    window = cs._load(cs.handle_models(cs._pack(header, audio.tobytes())))
    decoded = window['results'][0]['decoder']
    assert decoded['first_downbeat'] == 0.
    assert decoded['bpm'] == 120.
    if mutation == 'boolean_anchor':
        decoded['first_downbeat'] = False
    else:
        decoded['covered_duration_s'] = .4
        decoded['beats'] = [dict(time_s=index / 10, position=index + 1, observed=True)
                            for index in range(4)]
    with pytest.raises(ValueError):
        cs._validate_beat_window(window)

import json
import multiprocessing as mp
import os
import socket
import threading
import time

import numpy as np
import pytest

from hpg_core.ai_models import cue_service as cs
from hpg_core.ai_models.process_runtime import OwnedModelProcess


def test_wire_roundtrip():
    audio = np.arange(20, dtype=np.float32)
    data = cs.encode_audio(audio, 22050, [], window_start_s=0., track_duration_s=1., verified_grid=True)
    header, restored = cs.decode_audio(data)
    np.testing.assert_array_equal(audio, restored)
    assert header['sample_rate'] == 22050


def test_wire_rejects_truncated():
    data = cs.encode_audio(np.zeros(20, np.float32), 22050, [], window_start_s=0., track_duration_s=1., verified_grid=True)
    with pytest.raises(ValueError):
        cs.decode_audio(data[:-1])


def test_owner_lazy():
    with cs.CueServiceOwner() as owner:
        client = owner.register_generation()
        assert owner.model_pid is None
        assert client.score(np.ones(10, np.float32), 22050, [], window_start_s=0., track_duration_s=1., verified_grid=True) == []
        assert owner.model_pid is None


def probe_handler(payload):
    header, audio = cs.decode_audio(payload)
    if header['candidates'][0]['kind'] == 10:
        time.sleep(2)
    return cs._json(cs._diagnostics(header['candidates'], f'probe_pid:{os.getpid()}'))


def worker_request(client):
    with cs.request_deadline(time.monotonic()+10):
        return client.score(np.ones(22050, np.float32), 22050,
                            [dict(start_s=.5, kind=1, mood=1)],
                            window_start_s=0., track_duration_s=1., verified_grid=True)


@pytest.fixture
def probe_lane(monkeypatch):
    monkeypatch.setattr(cs, 'OwnedModelProcess', lambda *a, **k: OwnedModelProcess(__name__, 'probe_handler'))


def test_two_workers_recovery_reuse_idle_lane(probe_lane):
    from concurrent.futures import ProcessPoolExecutor
    with cs.CueServiceOwner() as owner:
        client = owner.register_generation()
        with ProcessPoolExecutor(2, mp_context=mp.get_context('spawn')) as pool:
            futures = [pool.submit(worker_request, client) for _ in range(2)]
            answers = [f.result(timeout=15) for f in futures]
        pid = owner.model_pid
        assert pid is not None
        assert all(a[0]['reason'] == f'probe_pid:{pid}' for a in answers)
        owner.cancel_generation(client.generation)
        recovery = owner.register_generation()
        assert worker_request(recovery)[0]['reason'] == f'probe_pid:{pid}'


def auth_socket(client, deadline=None):
    sock = socket.create_connection(client.address, timeout=1)
    sock.settimeout(.05)
    end = deadline or time.monotonic()+2
    cs._send(sock, cs._json(dict(token=client.token, generation=client.generation,
                                request=os.urandom(16).hex(), deadline=end)), end, None)
    assert cs._receive(sock, cs.MAX_HEADER, end, None) == b'READY'
    return sock


def test_interrupted_worker_write_does_not_poison_broker(probe_lane):
    with cs.CueServiceOwner() as owner:
        client = owner.register_generation()
        sock = auth_socket(client)
        sock.sendall(b'\x00\x01\x00\x00partial')
        sock.close()
        assert worker_request(client)[0]['reason'].startswith('probe_pid:')


def test_close_interrupts_partial_write(probe_lane):
    owner = cs.CueServiceOwner()
    client = owner.register_generation()
    sock = auth_socket(client)
    sock.sendall(b'\x00\x01\x00\x00partial')
    start = time.monotonic()
    owner.close()
    sock.close()
    assert time.monotonic()-start < 4
    assert not owner._thread.is_alive()
    with pytest.raises(RuntimeError):
        owner.register_generation()


def test_generation_cancel_and_unverified_do_not_start_model(probe_lane):
    with cs.CueServiceOwner() as owner:
        client = owner.register_generation()
        owner.cancel_generation(client.generation)
        assert worker_request(client)[0]['raw_score'] is None
        assert owner.model_pid is None
        answer = client.score(np.ones(10), 22050, [dict(start_s=0., kind=1, mood=1)],
                              window_start_s=0., track_duration_s=1., verified_grid=False)
        assert answer[0]['reason'] == 'unverified_grid'


def test_bad_bind_falls_back(monkeypatch):
    monkeypatch.setattr(cs.socket, 'socket', lambda: (_ for _ in ()).throw(OSError('probe')))
    with cs.CueServiceOwner() as owner:
        answer = worker_request(owner.register_generation())
        assert answer[0]['reason'].startswith('service_bind_error:')


def test_fingerprint_tracks_appearance_and_contents(tmp_path):
    config = dict(samplecnn_path=str(tmp_path/'sample'), cue_model_path=str(tmp_path/'cue'), prefer_directml=True)
    first = cs.fingerprint(config)
    (tmp_path/'sample').write_bytes(b'model1')
    second = cs.fingerprint(config)
    (tmp_path/'sample').write_bytes(b'model2')
    assert len({first, second, cs.fingerprint(config)}) == 3


@pytest.mark.parametrize('mutation', ['nan', 'extra', 'shape', 'kind'])
def test_strict_header(mutation):
    payload = cs.encode_audio(np.ones(20, np.float32), 22050, [dict(start_s=0., kind=1, mood=1)],
                               window_start_s=0., track_duration_s=1., verified_grid=True)
    header, audio = cs.decode_audio(payload)
    if mutation == 'nan':
        header['sample_rate'] = float('nan')
    elif mutation == 'extra':
        header['extra'] = 1
    elif mutation == 'shape':
        header['samples'] += 1
    else:
        header['candidates'][0]['kind'] = True
    with pytest.raises(ValueError):
        cs.decode_audio(cs._pack(header, audio.tobytes()))


def test_late_response_not_reused(probe_lane):
    with cs.CueServiceOwner() as owner:
        client = owner.register_generation()
        worker_request(client)
        first_pid = owner.model_pid
        with cs.request_deadline(time.monotonic()+.1):
            failed = client.score(np.ones(22050, np.float32), 22050, [dict(start_s=.5, kind=10, mood=1)],
                                  window_start_s=0., track_duration_s=1., verified_grid=True)
        assert failed[0]['raw_score'] is None
        answer = worker_request(client)
        assert owner.model_pid != first_pid
        assert answer[0]['reason'] == f'probe_pid:{owner.model_pid}'


def test_oversize_rejected_before_pcm_copy(monkeypatch):
    class Audio(np.ndarray):
        def tobytes(self, *args, **kwargs):
            pytest.fail('PCM copied before bounds check')
    audio = np.ones(30, np.float32).view(Audio)
    monkeypatch.setattr(cs, 'MAX_WIRE', 100)
    with pytest.raises(ValueError):
        cs.encode_audio(audio, 22050, [], window_start_s=0., track_duration_s=1., verified_grid=True)


def test_success_requires_measured_coverage():
    result = cs._diagnostics([{}], 'probe')[0]
    result.update(status='ok', reason=None, raw_score=-1., model_hashes=cs.MODEL_HASHES)
    with pytest.raises(ValueError):
        cs._validate_results([result])


def test_deterministic_model_unavailability_is_cacheable():
    result = cs._diagnostics([{}], 'model_hash_mismatch')[0]
    result['status'] = 'unsupported_model'
    value = dict(windows=[dict(results=[result])])
    assert not cs.transient_failure(value)
    result.update(status='model_error', reason='model_load_error: FileNotFoundError')
    assert not cs.transient_failure(value)
    result['reason'] = 'model_load_error: ModelUnavailableError'
    assert cs.transient_failure(value)


def test_real_adapter_missing_models_are_cacheable(tmp_path):
    from hpg_core.ai_models.cue_predictor import score_phrase_candidates
    results = score_phrase_candidates(
        np.zeros(44100, np.float32), 22050, [dict(start_s=1., kind=1, mood=1)],
        samplecnn_path=tmp_path/'missing-samplecnn.onnx',
        cue_model_path=tmp_path/'missing-cue.onnx', window_start_s=0.,
        track_duration_s=2., verified_grid=True,
    )
    assert results[0]['status'] == 'model_error'
    assert results[0]['raw_score'] is None
    assert results[0]['reason'] == 'model_load_error: FileNotFoundError'
    assert not cs.transient_failure(dict(windows=[dict(results=results)]))


def test_terminal_broker_prevents_new_owner(monkeypatch):
    monkeypatch.setattr(cs, '_terminal_failure', threading.Event())
    cs._terminal_failure.set()
    with cs.CueServiceOwner() as owner:
        assert worker_request(owner.register_generation())[0]['reason'] == 'service_cleanup_unconfirmed'
        assert owner._thread is None

"""Gesammelte Laufzeitverträge ohne Audio, Modelle oder echten Broker."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from hpg_core.ai_models import deep_feature_runtime as runtime
from hpg_core.ai_models.feature_audio import source_identity


class RecordingClient:
    marker = object()

    def __init__(self):
        self.calls = []
        self.result = {'status': 'ok'}

    def deep_features(self, parameters, *, timeout_s=240.):
        self.calls.append((parameters, timeout_s))
        return self.result


@pytest.fixture
def track(tmp_path):
    path = tmp_path / 'Quelle mit Leerzeichen.bin'
    path.write_bytes(b'Nur Stat-Metadaten, kein Audio')
    return SimpleNamespace(filePath=str(path), duration=657.084943)


def request(track, kind='stems'):
    from pathlib import Path
    path = Path(track.filePath)
    return dict(kind=kind, path=str(path), identity=source_identity(path))


@pytest.mark.parametrize('duration,expected', [
    (1., 240.), (180., 240.), (181., 241.),
    (657.084943, 717.084943), (840., 900.), (7200., 900.),
])
def test_stem_budget_has_floor_duration_reserve_and_cap(duration, expected):
    assert runtime.stem_timeout_seconds(duration) == pytest.approx(expected)


@pytest.mark.parametrize('invalid', [
    True, False, None, '657', 0, -1, float('nan'), float('inf'), -float('inf'), 10**400,
])
def test_stem_budget_rejects_invalid_duration(invalid):
    with pytest.raises(ValueError):
        runtime.stem_timeout_seconds(invalid)


def test_no_context_preserves_original_client_and_direct_deadlines(track):
    client = RecordingClient()
    assert runtime.client_for_context(client) is client
    for timeout in (30., 240.):
        runtime.client_for_context(client).deep_features(request(track), timeout_s=timeout)
    assert [timeout for _, timeout in client.calls] == [30., 240.]


@pytest.mark.parametrize('kind,timeout,expected', [
    ('stems', 240., 717.084943), ('stems', 30., 30.),
    ('stems', 300., 300.), ('embedding', 240., 240.),
    ('embedding', 38., 38.), ('unknown', 240., 240.),
])
def test_only_bound_automatic_stem_default_changes(track, kind, timeout, expected):
    client = RecordingClient()
    parameters = request(track, kind)
    with runtime.automatic_budget(track):
        proxy = runtime.client_for_context(client)
        assert proxy is not client
        assert proxy.marker is client.marker
        assert proxy.deep_features(parameters, timeout_s=timeout) is client.result
    assert len(client.calls) == 1
    assert client.calls[0][0] is parameters
    assert client.calls[0][1] == pytest.approx(expected)


@pytest.mark.parametrize('damage', ['identity', 'bool_identity', 'other_path', 'changed_file', 'relative'])
def test_source_mismatch_never_expands_budget(track, tmp_path, damage):
    from pathlib import Path
    client = RecordingClient()
    parameters = request(track)
    with runtime.automatic_budget(track):
        if damage == 'identity':
            parameters['identity'][0] += 1
        elif damage == 'bool_identity':
            parameters['identity'][0] = True
        elif damage == 'other_path':
            other = tmp_path / 'Andere Quelle.bin'
            other.write_bytes(b'Andere Stat-Quelle')
            parameters.update(path=str(other), identity=source_identity(other))
        elif damage == 'changed_file':
            Path(track.filePath).write_bytes(b'Geaenderte Stat-Quelle')
        else:
            parameters['path'] = Path(track.filePath).name
        runtime.client_for_context(client).deep_features(parameters)
    assert client.calls == [(parameters, 240.)]


@pytest.mark.parametrize('timeout', [True, None, 0., -1., float('nan'), float('inf')])
def test_proxy_rejects_invalid_timeouts_before_delegation(track, timeout):
    client = RecordingClient()
    with runtime.automatic_budget(track), pytest.raises(ValueError):
        runtime.client_for_context(client).deep_features(request(track), timeout_s=timeout)
    assert client.calls == []


def test_nested_context_restores_parent_and_expired_proxy_cannot_extend(track):
    client = RecordingClient()
    parameters = request(track)
    inner = SimpleNamespace(filePath=track.filePath, duration=300.)
    with runtime.automatic_budget(track):
        outer_proxy = runtime.client_for_context(client)
        with runtime.automatic_budget(inner):
            inner_proxy = runtime.client_for_context(client)
            inner_proxy.deep_features(parameters)
            outer_proxy.deep_features(parameters)
        outer_proxy.deep_features(parameters)
        inner_proxy.deep_features(parameters)
    outer_proxy.deep_features(parameters)
    assert [timeout for _, timeout in client.calls] == pytest.approx(
        [360., 240., 717.084943, 240., 240.])
    assert runtime.client_for_context(client) is client


def test_invalid_inner_source_does_not_inherit_outer_permission(track):
    client = RecordingClient()
    with runtime.automatic_budget(track):
        with runtime.automatic_budget(SimpleNamespace(filePath=track.filePath, duration=True)):
            assert runtime.client_for_context(client) is client
        runtime.client_for_context(client).deep_features(request(track))
    assert client.calls[0][1] == pytest.approx(717.084943)


def test_other_thread_cannot_use_retained_proxy_permission(track):
    client = RecordingClient()
    parameters = request(track)
    with runtime.automatic_budget(track):
        proxy = runtime.client_for_context(client)
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(runtime.client_for_context, client).result() is client
            assert pool.submit(proxy.deep_features, parameters).result() is client.result
    assert client.calls == [(parameters, 240.)]


@pytest.mark.parametrize('fail', [False, True])
def test_attach_delegates_once_preserves_payloads_and_cleans_context(track, monkeypatch, fail):
    from hpg_core.ai_models import deep_features
    track.stem_analysis = {'status': 'ok', 'fingerprint': 'existing-stems'}
    track.embedding_analysis = {'status': 'ok', 'fingerprint': 'existing-embedding'}
    stems, embedding = track.stem_analysis, track.embedding_analysis
    client = RecordingClient()
    calls = []

    def attach(value):
        calls.append(value)
        runtime.client_for_context(client).deep_features(request(value))
        if fail:
            raise RuntimeError('Fehler im vorhandenen Attachment')
        return 'delegiertes Ergebnis'

    monkeypatch.setattr(deep_features, 'attach', attach)
    if fail:
        with pytest.raises(RuntimeError, match='Attachment'):
            runtime.attach(track)
    else:
        assert runtime.attach(track) == 'delegiertes Ergebnis'
    assert calls == [track]
    assert len(client.calls) == 1
    assert client.calls[0][1] == pytest.approx(717.084943)
    assert track.stem_analysis is stems
    assert track.embedding_analysis is embedding
    assert runtime.client_for_context(client) is client


@pytest.fixture(params=['pool', 'owned'])
def session_client(request, monkeypatch):
    """Echte Sessionsteuerung mit isoliertem Zustand, ohne Modellprozesse."""
    import threading
    from hpg_core.ai_models import cue_service

    client = RecordingClient()
    events = []

    class Owner:
        def __init__(self):
            events.append('create')

        def register_generation(self):
            events.append('register')
            return client

        def close(self):
            events.append('close')

    monkeypatch.setattr(cue_service, '_local', threading.local())
    monkeypatch.setattr(cue_service, '_pool_client',
                        client if request.param == 'pool' else None)
    monkeypatch.setattr(cue_service, 'CueServiceOwner', Owner)
    return cue_service, client, events, request.param


def test_real_session_returns_only_temporary_context_proxy(track, session_client):
    service, client, events, mode = session_client
    parameters = request(track)
    with service._track_context():
        with service.session() as direct:
            assert direct is client
        with runtime.automatic_budget(track):
            with service.session() as first:
                assert first is not client
                first.deep_features(parameters)
            with service.session() as second:
                assert second is not client
                assert second is not first
            if mode == 'pool':
                assert service._pool_client is client
            else:
                assert service._local.track['client'] is client
        with service.session() as direct:
            assert direct is client
            direct.deep_features(parameters, timeout_s=30.)
        first.deep_features(parameters)
    assert [timeout for _, timeout in client.calls] == pytest.approx(
        [717.084943, 30., 240.])
    assert events == ([] if mode == 'pool' else ['create', 'register', 'close'])
    assert service._local.track is None


def test_actual_attachment_uses_session_budget_without_replacing_producer(
        track, session_client, monkeypatch):
    from hpg_core.ai_models import deep_features, feature_reuse

    service, client, events, mode = session_client
    client.result = dict(status='unavailable', reason='controlled_failure')
    settings = dict(stems_enabled=True, embedding_enabled=True)
    fingerprints = dict(stems='a' * 64, embedding='b' * 64)
    monkeypatch.setattr(deep_features, 'config', lambda: settings)
    monkeypatch.setattr(deep_features, 'config_fingerprint',
                        lambda config=None: fingerprints)
    monkeypatch.setattr(deep_features, 'identities', lambda config: {
        'stems': {'dll': deep_features.DLL_HASH, 'stems': deep_features.MODEL_HASHES},
        'embedding': {
            'embedding_model': deep_features.EMBEDDING_HASH,
            'energy_model': deep_features.ENERGY_HASH,
            **deep_features.UMAP_HASHES,
        },
    })
    monkeypatch.setattr(feature_reuse, 'load', lambda value, identities: None)
    track.bpm = 140.

    # Das echte Attachment bleibt erhalten; nur dessen externe Dienste sind
    # kontrolliert. Die Session selbst wird nicht durch einen Testgenerator ersetzt.
    runtime.attach(track)

    assert [parameters['kind'] for parameters, _ in client.calls] == ['embedding', 'stems']
    assert [timeout for _, timeout in client.calls] == pytest.approx([38., 717.084943])
    assert track.bpm == 140.
    assert track.stem_analysis['reason'] == 'controlled_failure'
    assert track.embedding_analysis['reason'] == 'controlled_failure'
    assert track.stem_analysis['fingerprint'] == fingerprints['stems']
    assert track.embedding_analysis['fingerprint'] == fingerprints['embedding']
    assert runtime.client_for_context(client) is client
    if mode == 'owned':
        assert service._local.track is None
    else:
        assert not hasattr(service._local, 'track')
    assert events == ([] if mode == 'pool' else ['create', 'register', 'close'])


@pytest.mark.parametrize('kind,timeout,elapsed,remaining', [
    ('stems', 717., 100., 617.),
    ('stems', 30., 10., 20.),
    ('stems', 240., 100., 140.),
    ('embedding', 240., 100., 140.),
])
def test_real_client_fallback_receives_only_remaining_feature_budget(
        monkeypatch, kind, timeout, elapsed, remaining):
    from hpg_core.ai_models import cue_service

    clock = [100.]
    calls = []
    failure = dict(status='unavailable', reason='service_error:controlled_failure')
    success = dict(status='ok')
    parameters = dict(kind=kind, config=dict(prefer_directml=True))
    client = cue_service.CueClient(('127.0.0.1', 1), 'token', 'generation', {})

    def path_job(job, request, *, timeout_s):
        calls.append((job, request, timeout_s))
        if len(calls) == 1:
            clock[0] += elapsed
            return failure
        return success

    monkeypatch.setattr(cue_service.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(client, '_path_job', path_job)

    assert client.deep_features(parameters, timeout_s=timeout) is success

    assert len(calls) == 2
    assert calls[0] == ('deep_features', parameters, timeout)
    assert calls[0][1] is parameters
    assert calls[1] == (
        'deep_features', dict(parameters, cpu_fallback=True), remaining,
    )
    assert calls[1][1] is not parameters
    assert 'cpu_fallback' not in parameters


@pytest.mark.parametrize('kind,timeout', [
    ('stems', 717.), ('stems', 30.), ('stems', 240.), ('embedding', 240.),
])
def test_real_client_does_not_restart_with_exhausted_fallback_budget(
        monkeypatch, kind, timeout):
    from hpg_core.ai_models import cue_service

    clock = [100.]
    calls = []
    failure = dict(status='unavailable', reason='RuntimeError:controlled_failure')
    client = cue_service.CueClient(('127.0.0.1', 1), 'token', 'generation', {})

    def path_job(job, parameters, *, timeout_s):
        calls.append(timeout_s)
        clock[0] += timeout - .5
        return failure

    monkeypatch.setattr(cue_service.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(client, '_path_job', path_job)

    assert client.deep_features(
        dict(kind=kind, config=dict(prefer_directml=True)), timeout_s=timeout,
    ) is failure
    assert calls == [timeout]


@pytest.mark.parametrize('kind,budget,track_deadline,execution,receive_deadline', [
    ('stems', 717., 1100., 717., 1017.),
    ('stems', 717., 800., 717., 795.),
    ('stems', 1000., 2000., 900., 1200.),
    ('embedding', 240., 1100., 240., 540.),
])
def test_path_job_keeps_queue_track_deadline_and_cleanup_limits(
        monkeypatch, kind, budget, track_deadline, execution, receive_deadline):
    from hpg_core.ai_models import cue_service as service

    clock = [100.]
    sent = []
    deadlines = []

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, value):
            pass

        def connect(self, address):
            pass

    def receive(sock, maximum, deadline, cancel):
        deadlines.append(deadline)
        if len(deadlines) == 1:
            clock[0] = 300.
            return b'READY'
        auth = service._load(sent[0])
        return service._json(dict(request=auth['request'], results=dict(status='ok')))

    monkeypatch.setattr(service.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(service.socket, 'socket', Socket)
    monkeypatch.setattr(service, '_send', lambda sock, data, deadline, cancel: sent.append(data))
    monkeypatch.setattr(service, '_receive', receive)
    client = service.CueClient(('127.0.0.1', 1), 'token', 'generation', {})

    with service.request_deadline(track_deadline):
        assert client.deep_features(dict(kind=kind), timeout_s=budget) == {'status': 'ok'}

    envelope, _ = service._header(sent[1])
    assert envelope['execution_timeout_s'] == execution
    assert deadlines == [track_deadline - 5., receive_deadline]


@pytest.mark.parametrize('kind,timeout,accepted', [
    ('stems', 717., True), ('stems', 900., True), ('stems', 900.01, False),
    ('embedding', 240., True), ('embedding', 241., False),
    ('stems', float('nan'), False), ('stems', float('inf'), False),
    ('stems', True, False),
])
def test_broker_validates_kind_specific_execution_budget(monkeypatch, kind, timeout, accepted):
    import json
    import socket
    import struct
    import threading
    import time
    import uuid
    from hpg_core.ai_models import cue_service as service

    calls = []

    class Model:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def call(self, payload, *, deadline, cancel_event):
            calls.append((payload, deadline))
            return service._json(dict(status='ok'))

    monkeypatch.setattr(service, 'OwnedModelProcess', Model)
    monkeypatch.setattr(service, '_terminal_failure', threading.Event())
    with service.CueServiceOwner() as owner:
        client = owner.register_generation()
        deadline = time.monotonic() + 3.
        with socket.create_connection(client.address, timeout=1.) as sock:
            sock.settimeout(.05)
            service._send(sock, service._json(dict(
                token=client.token, generation=client.generation,
                request=uuid.uuid4().hex, deadline=deadline,
            )), deadline, None)
            assert service._receive(sock, service.MAX_HEADER, deadline, None) == b'READY'
            # Auch ungültiges JSON-Zahlenmaterial direkt an der Brokergrenze prüfen.
            header = json.dumps(dict(version=3, job='deep_features',
                                     parameters=dict(kind=kind), execution_timeout_s=timeout)).encode()
            service._send(sock, struct.pack('!I', len(header)) + header, deadline, None)
            if accepted:
                response = service._load(service._receive(sock, service.MAX_HEADER, deadline, None))
                assert response['results'] == {'status': 'ok'}
            else:
                with pytest.raises(EOFError):
                    service._receive(sock, service.MAX_HEADER, deadline, None)
    assert len(calls) == int(accepted)


@pytest.mark.parametrize('workers,expected', [(1, 1080.), (4, 1440.)])
def test_track_budget_reserves_stems_but_keeps_global_hang_cap(monkeypatch, workers, expected):
    from hpg_core import config

    monkeypatch.setenv('HPG_STEMS', '1')
    for setting in ('HPG_EMBEDDINGS', 'HPG_NATIVE_BEAT', 'HPG_NATIVE_PHRASE'):
        monkeypatch.setenv(setting, '0')
    assert config.analysis_timeout_seconds(workers) == expected
    assert expected <= config.PARALLEL_HANG_DEADLINE_MAX - 30.

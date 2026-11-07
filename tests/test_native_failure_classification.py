"""Fachliche native Ablehnung von wiederholbaren Laufzeitfehlern unterscheiden."""
from contextlib import nullcontext
import logging
from types import SimpleNamespace

import numpy as np
import pytest

from hpg_core import analysis
from hpg_core.ai_models import native_track_beats
from hpg_core.analysis_pipeline import finalize_track


@pytest.fixture
def native_failure_context(tmp_path, monkeypatch):
    # Nur Quellstatistik: Der Transport liefert kontrollierte Workerantworten;
    # weder Audio-Decoder noch Modelle werden gestartet.
    source = tmp_path / 'source.aiff'
    source.write_bytes(b'Nur Stat-Metadaten')
    monkeypatch.setenv('HPG_NATIVE_BEAT', '1')
    monkeypatch.setattr(native_track_beats, 'configured_mode', lambda: 2)
    monkeypatch.setattr(analysis, '_validate_track_beatgrid',
                        lambda *args, **kwargs: pytest.fail('Abgelehntes Raster darf nicht freigegeben werden'))

    def prepare(reason):
        calls = []

        def transport(job, parameters, *, timeout_s):
            calls.append(job)
            return dict(status='unavailable', reason=reason)

        client = SimpleNamespace(native_beats=transport)
        monkeypatch.setattr(analysis.cue_service, 'session', lambda: nullcontext(client))
        result = analysis._prepare_native_beats(str(source), 469.333356, np.ones(16), 44100)
        assert calls == ['native_beat']
        return result

    return prepare


@pytest.mark.parametrize('worker_reason,transient', [
    ('NativeContractError: Stable model window still contradicts full sequence', False),
    ('service_error:TimeoutError', True),
    ('service_error:EOFError', True),
    ('NativeContractError: Native source identity changed', True),
    ('NativeContractError: unknown contract failure', True),
    ('RuntimeError: Stable model window still contradicts full sequence', True),
])
def test_real_native_adapter_preserves_rejection_and_classifies_retry(
        native_failure_context, worker_reason, transient):
    context = native_failure_context(worker_reason)

    assert context['accepted'] is False
    assert context['transient'] is transient
    expected = dict(status='unavailable', reason='ValueError: ' + worker_reason)
    if expected['reason'] == native_track_beats.REFINER_FAILURE_REASON:
        expected['failure_producer_revision'] = native_track_beats.REFINER_FAILURE_REVISION
    assert context['analysis'] == expected
    assert context['decision'] == dict(status='unavailable', reason='native_unavailable')
    assert 'grid' not in context['analysis']
    assert 'validation' not in context


@pytest.mark.parametrize('policy,worker_reason,expected_writes', [
    ('reuse', 'NativeContractError: Stable model window still contradicts full sequence', 1),
    ('fresh', 'NativeContractError: Stable model window still contradicts full sequence', 0),
    ('reuse', 'service_error:TimeoutError', 0),
])
def test_common_finalizer_keeps_valid_fallback_without_retrying_native_rejection(
        native_failure_context, policy, worker_reason, expected_writes):
    context = native_failure_context(worker_reason)
    track = SimpleNamespace(
        filePath='source.aiff', native_beat_analysis=context['analysis'],
        native_phrase_analysis=dict(status='skipped', reason='unverified_or_blocked_grid'),
        neural_analysis=dict(windows=[], beat_windows=[]),
    )
    writes = []

    def persist(key, value):
        writes.append((key, value))
        return True

    result = finalize_track(
        track, cache_policy=policy, cache_key='isolated-test-key', analysis_degraded=False,
        anchor_transient=context['transient'], attach_features=lambda value: None,
        transient_failure=analysis.cue_service.transient_failure,
        persist=persist, logger=logging.getLogger(__name__),
    )

    assert result is track
    assert len(writes) == expected_writes
    assert track.native_beat_analysis['status'] == 'unavailable'
    assert track.native_phrase_analysis['status'] == 'skipped'
    assert track.analysis_origin == 'fresh'

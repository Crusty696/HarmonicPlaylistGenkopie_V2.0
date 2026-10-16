"""Neue Produktgrenzen: native Herkunft sichtbar, Export und Ablehnung konsistent."""
from types import SimpleNamespace

import pytest

from hpg_core.ai_models.native_beat_alignment import active_anchor
from hpg_core.ai_models.native_track_beats import has_verified_grid
from hpg_core.exporters.rekordbox_xml_exporter import RekordboxXMLExporter
from hpg_core.measurement_panel import _anchor_summary, _deep_summary
from hpg_core import pair_candidates as pc
from tests.test_native_grid_regressions import aligned
from tests.test_measurement_panel import anchor_diagnosis
from tests.test_pair_rejection_diagnostics import tracks
from tests.test_deep_features import embedding


def native_track():
    value = aligned()
    return SimpleNamespace(native_beat_analysis=value, duration=48., bpm=120.,
        first_downbeat=active_anchor(value), beatgrid_status='verified',
        beatgrid_source='audio', downbeat_confidence=1.,
        bar_position_usage_blocked=False, filePath='Z:/readonly/source.wav')


@pytest.mark.parametrize('damage', [None, 'anchor', 'bpm', 'provenance', 'alignment', 'blocked'])
def test_native_export_requires_same_verified_snapshot_as_renderer(damage):
    track = native_track()
    if damage == 'anchor':
        track.first_downbeat += .01
    elif damage == 'bpm':
        track.bpm += 1
    elif damage == 'provenance':
        track.native_beat_analysis['executable_sha256'] = '0'*64
    elif damage == 'alignment':
        track.native_beat_analysis['audio_alignment']['offset_seconds'] += .01
    elif damage == 'blocked':
        track.bar_position_usage_blocked = True
    calls = []
    target = SimpleNamespace(add_tempo=lambda **kw: calls.append(kw))
    exporter = object.__new__(RekordboxXMLExporter)
    count, errors = exporter._add_beat_grid(target, track)
    assert bool(count) == (damage is None)
    if damage is None:
        assert has_verified_grid(track)
        assert calls == [dict(Inizio=track.first_downbeat, Bpm=120., Metro='4/4', Battito=1)]
        assert errors == []
    else:
        assert calls == [] and errors


@pytest.mark.parametrize('corrected', [False, True])
def test_native_anchor_diagnosis_separates_source_and_musical_proof(corrected):
    method = 'native_rekordbox_audio_offset' if corrected else 'native_rekordbox'
    data = anchor_diagnosis(method=method, confidence=1.)
    data['anchor']['neural']['reason'] = 'native_offset_adopted' if corrected else 'native_adopted'
    text = _anchor_summary(data)
    assert 'Native Rekordbox-Analyse' in text
    assert 'Takt 1 ist nicht unabhängig geprüft' in text
    assert 'keine gemessene musikalische Trefferquote' in text
    assert 'technisch freigegeben' in text
    assert ('Rohfolge bleibt erhalten' in text) == corrected


def test_deep_diagnosis_rejects_corrupt_feature_without_exposing_payload():
    track = native_track()
    track.embedding_analysis = embedding(48.)
    text = _deep_summary(track)
    assert '96 Beatpunkte' in text and '48.0 s abgedeckt' in text
    assert 'kein Rangfolgengewicht' in text
    track.embedding_analysis['data']['vector'] = ['PRIVATE_PAYLOAD']
    text = _deep_summary(track)
    assert 'ungültige gespeicherte Diagnose' in text and 'PRIVATE_PAYLOAD' not in text


def test_native_gap_reason_survives_candidate_prefilter(monkeypatch):
    a, b = tracks()
    monkeypatch.setattr(pc, '_native_blend_supported', lambda *args: False)
    reasons = []
    assert pc.rank_pair_candidates(a, b, wahl={}, rejection_reasons=reasons) == []
    assert reasons[0] == 'Keine durchgehend belegte Beatfolge'
    assert 'unregelmäßig oder unvollständig' in reasons[1]


def test_partial_native_rejections_do_not_label_successful_pair(monkeypatch):
    a, b = tracks()
    calls = 0
    def supported(*args):
        nonlocal calls
        calls += 1
        return calls != 1
    monkeypatch.setattr(pc, '_native_blend_supported', supported)
    reasons = []
    assert pc.rank_pair_candidates(a, b, wahl={}, rejection_reasons=reasons)
    assert reasons == []

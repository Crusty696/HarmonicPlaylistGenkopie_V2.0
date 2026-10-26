"""Neue Hörproben bewahren Messmethoden, alte behalten ihre Bedeutung."""
from dataclasses import asdict
import pytest
from hpg_core.transition_renderer import TransitionClipSpec
from hpg_core.hearing_sources import (
    validate_spec_v1, validate_spec_v2, SPEC_V1_FIELDS, SPEC_V2_FIELDS,
    SourceValidationError)
from tests.test_hearing_sources import source_fixture


def test_phase_methods_survive_v2_and_v1_keeps_legacy_default(tmp_path):
    spec = TransitionClipSpec(str(tmp_path/'a.wav'), str(tmp_path/'b.wav'),
                              40., 20., 8., phase_method_a='native_attack_v1')
    data = {key: value for key, value in asdict(spec).items() if key in SPEC_V2_FIELDS}
    assert TransitionClipSpec(**validate_spec_v2(data)).phase_method_a == 'native_attack_v1'
    legacy = {key:value for key,value in data.items() if key in SPEC_V1_FIELDS}
    assert TransitionClipSpec(**validate_spec_v1(legacy)).phase_method_a == 'bass_fold'


def test_unrecognized_phase_method_cannot_enter_hearing_session(tmp_path):
    data = asdict(TransitionClipSpec(str(tmp_path/'a.wav'), str(tmp_path/'b.wav'),40.,20.,8.))
    data = {key: value for key, value in data.items() if key in SPEC_V2_FIELDS}
    data['phase_method_b'] = 'unchecked'
    with pytest.raises(SourceValidationError):
        validate_spec_v2(data)


def test_source_session_and_discovery_read_both_versions(source_fixture):
    import json
    from hpg_core.hearing_sources import SourceRenderSink, write_source_manifest, load_source_session
    from hpg_core.hearing_discovery import _source_metadata
    stage, spec, _, a, b = source_fixture
    spec.phase_method_a = 'native_attack_v1'
    sink = SourceRenderSink(stage, (a.parent,))
    sink.emit(spec, stage/'clips/001.wav')
    path = write_source_manifest(stage, 'einzel', sink)
    assert _source_metadata(stage)['format_version'] == 3
    load_source_session(stage)
    legacy = json.loads(path.read_text(encoding='utf8'))
    legacy['format_version'] = 1
    for entry in legacy['specs'].values():
        entry.pop('phase_method_a')
        entry.pop('phase_method_b')
        entry.pop('bass_swap_fraction')
    path.write_text(json.dumps(legacy), encoding='utf8')
    assert _source_metadata(stage)['format_version'] == 1
    load_source_session(stage)
    assert a.read_bytes() == b'synthetic source A'

"""Expliziter Diagnosevertrag; keine Rekonstruktion fehlender Messursachen."""
from copy import deepcopy
from dataclasses import asdict
import math


DOWNBEAT_FIELDS = frozenset({
    "reason", "stage", "beats_detected", "beats_used", "grid_ibi_seconds",
    "bar_confidence", "fold_lock", "phase_seconds", "loud_max", "error_type",
    "retry_reason",
})
DOWNBEAT_REASONS = frozenset({
    "unknown", "reference_verified", "invalidinput", "inputshort", "fewbeats",
    "incommensurate", "noactivity", "weakfold", "fold_alignment", "voteweak",
    "estimationerror", "ok", "native_verified",
})
STAGES = frozenset({"input", "beat_tracking", "features", "trim", "voting", "fold", "result", "reference"})
GRID_REASONS = frozenset({
    "unknown", "invalidinput", "nowindows", "duplicategrid", "variablegrid",
    "tempomismatch", "missingreference", "fewwindows", "verified", "phasemismatch",
})
WINDOW_REASONS = frozenset({"measured", "weakfold", "invalidinput", "estimationerror", "gridcoverage"})
TEMPO_REASONS = frozenset({
    "reference_error", "reference_verified", "window_count", "window_unavailable",
    "model_set_invalid", "model_unavailable", "model_bpm_invalid",
    "model_disagreement", "candidate_matches_baseline", "audio_refinement_rejected",
    "refined_tempo_invalid", "audio_phase_unlocked", "final_grid_decode_error",
    "final_grid_unverified", "accepted", "resolver_error",
})
LEGACY_WINDOW_FIELDS = frozenset({
    "offset_seconds", "duration_seconds", "phase_seconds", "fold_lock", "phase_error_ms", "reason",
})
WINDOW_FIELDS = LEGACY_WINDOW_FIELDS | {"signed_phase_error_ms"}
LEGACY_GRID_FIELDS = frozenset({
    "status", "windows_checked", "max_phase_error_ms", "reason", "window_diagnostics", "decode_failures",
})
GRID_FIELDS = LEGACY_GRID_FIELDS | {"phase_pattern", "phase_center_ms"}


def _error():
    raise ValueError("measurement_diagnostics verletzt den Diagnosevertrag")


def _number(value, *, minimum=0.0, maximum=None, nullable=True):
    if value is None and nullable:
        return
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        _error()
    if maximum is not None and value > maximum:
        _error()


def _count(value):
    if type(value) is not int or value < 0:
        _error()


EXTERNAL_REASONS = frozenset({
    'external_input', 'external_numbering', 'external_rotation', 'external_alignment',
    'external_vote_ambiguous', 'external_vote_conflict',
})
EXTERNAL_STAGES = frozenset({'external_beats', 'external_alignment'})


def _validate_downbeat(downbeat, *, external=False):
    if (type(downbeat) is not dict or not {"reason", "stage"}.issubset(downbeat)
            or set(downbeat) - DOWNBEAT_FIELDS):
        _error()
    if type(downbeat["reason"]) is not str or downbeat["reason"] not in (DOWNBEAT_REASONS | EXTERNAL_REASONS if external else DOWNBEAT_REASONS):
        _error()
    stage = downbeat["stage"]
    if stage is not None and (type(stage) is not str or stage not in (STAGES | EXTERNAL_STAGES if external else STAGES)):
        _error()
    if "retry_reason" in downbeat:
        retry_reason = downbeat["retry_reason"]
        if type(retry_reason) is not str or retry_reason not in (DOWNBEAT_REASONS | GRID_REASONS):
            _error()
    for name in ("beats_detected", "beats_used"):
        if name in downbeat:
            _count(downbeat[name])
    for name in ("grid_ibi_seconds", "phase_seconds", "loud_max"):
        if name in downbeat:
            _number(downbeat[name])
    for name in ("bar_confidence", "fold_lock"):
        if name in downbeat:
            _number(downbeat[name], maximum=1.0)
    error = downbeat.get("error_type")
    if error is not None and (type(error) is not str or not error.isidentifier() or len(error) > 100):
        _error()


def _validate_anchor(value, *, schema_version=None):
    expected_anchor_fields = {'source', 'method', 'anchor_s', 'confidence', 'reference', 'neural'}
    if schema_version in {5, 6, 7, 8}:
        expected_anchor_fields.add('bar_position_comparison')
    if type(value) is not dict or set(value) != expected_anchor_fields:
        _error()
    if type(value['method']) is not str or type(value['source']) is not str or value['method'] not in {'rekordbox', 'dsp', 'neural_audio', 'model_audio_rotation', 'model_audio_phase_offset', 'native_rekordbox', 'native_rekordbox_audio_offset'} or value['source'] != ('rekordbox' if value['method'] == 'rekordbox' else 'audio'):
        _error()
    _number(value['anchor_s'], nullable=False)
    _number(value['confidence'], maximum=1., nullable=False)
    if value['method'] == 'rekordbox' and value['confidence'] != 1.:
        _error()
    from .downbeat import (
        BEATGRID_MIN_WINDOWS, DOWNBEAT_RELIABLE_MIN,
        EXACT_BEAT_SYNC_TOLERANCE_SECONDS,
    )
    if value['method'] in {'neural_audio', 'model_audio_rotation', 'model_audio_phase_offset'} and not DOWNBEAT_RELIABLE_MIN <= value['confidence'] < 1.:
        _error()
    reference = value['reference']
    if reference is not None:
        expected_reference_fields = {'anchor_s', 'bpm', 'target_bpm', 'measurement'}
        if schema_version in {4, 5, 6, 7, 8}:
            expected_reference_fields.add('path_match')
        if type(reference) is not dict or set(reference) != expected_reference_fields:
            _error()
        if schema_version in {4, 5, 6, 7, 8}:
            path_match = reference['path_match']
            if type(path_match) is not str or path_match not in {
                    'unknown', 'exact_path', 'volume_rebind'}:
                _error()
        _number(reference['anchor_s'], nullable=False)
        for key in ('bpm', 'target_bpm'):
            _number(reference[key], nullable=key == 'bpm')
            if reference[key] is not None and reference[key] <= 0:
                _error()
        if (type(reference['measurement']) is not dict
                or reference['measurement'].get('version') not in {1, 2, 3, 4, 5, 6, 7, 8}):
            _error()
        validate_measurement_diagnostics(reference['measurement'])
    if value['method'] == 'rekordbox' and (reference is None or reference['measurement']['grid']['status'] != 'verified'
            or reference['anchor_s'] != value['anchor_s']):
        _error()
    neural = value['neural']
    if type(neural) is not dict or set(neural) != {'reason', 'transient', 'windows', 'candidate_anchor_s'}:
        _error()
    if type(neural['reason']) is not str or neural['reason'] not in {'reference_preferred', 'baseline_preferred', 'no_candidates', 'insufficient_evidence',
            'bar_conflict', 'insufficient_windows', 'final_grid_error', 'final_grid_rejected', 'adopted', 'bar_rotation_adopted', 'phase_offset_adopted', 'native_adopted', 'native_offset_adopted'}:
        _error()
    if type(neural['transient']) is not bool or type(neural['windows']) is not list or len(neural['windows']) > 6:
        _error()
    _number(neural['candidate_anchor_s'])
    if ((value['method'] == 'neural_audio') != (neural['reason'] == 'adopted')
            or (value['method'] == 'model_audio_rotation') != (neural['reason'] == 'bar_rotation_adopted')
            or (value['method'] == 'model_audio_phase_offset') != (neural['reason'] == 'phase_offset_adopted')
            or (value['method'] == 'native_rekordbox') != (neural['reason'] == 'native_adopted')
            or (value['method'] == 'native_rekordbox_audio_offset') != (neural['reason'] == 'native_offset_adopted')):
        _error()
    if value['method'] in {'native_rekordbox', 'native_rekordbox_audio_offset'} and (
            value['confidence'] != 0.
            or neural['candidate_anchor_s'] != value['anchor_s']
            or neural['windows']):
        _error()
    if neural['reason'] == 'adopted' and neural['candidate_anchor_s'] != value['anchor_s']:
        _error()

    if schema_version in {5, 6, 7, 8}:
        _validate_bar_position_comparison(value['bar_position_comparison'])
    if value['method'] in {'model_audio_rotation', 'model_audio_phase_offset'}:
        if schema_version not in {5, 6, 7, 8}:
            _error()
        comparison = value['bar_position_comparison']
        confirmation = comparison['audio_confirmation']
        reference_grid = (reference['measurement']['grid']
                          if reference is not None else None)
        verified_reference = (
            type(reference_grid) is dict
            and reference_grid.get('status') == 'verified'
        )
        offset_reference = (
            type(reference_grid) is dict
            and reference_grid.get('status') == 'mismatch'
            and reference_grid.get('phase_pattern') == 'consistent_offset'
            and comparison.get('reason') == 'offset_compensated'
            and type(reference_grid.get('phase_center_ms')) in (int, float)
            and math.isfinite(reference_grid['phase_center_ms'])
            and abs(reference_grid['phase_center_ms'])
                > EXACT_BEAT_SYNC_TOLERANCE_SECONDS * 1000.0
        )
        phase_offset_adoption = (
            value['method'] == 'model_audio_phase_offset'
            and offset_reference
            and comparison['status'] == 'aligned'
            and comparison['rotation_beats'] == 0
        )
        rotation_adoption = (
            value['method'] == 'model_audio_rotation'
            and (verified_reference or offset_reference)
            and comparison['status'] == 'candidate_rotation'
            and comparison['rotation_beats'] in {1, 2, 3}
        )
        if (not (phase_offset_adoption or rotation_adoption)
                or confirmation['status'] != 'audio_confirmed'
                or confirmation['expected_anchor_s'] != value['anchor_s']
                or neural['candidate_anchor_s'] != value['anchor_s']
                or value['confidence'] != min(row['confidence'] for row in confirmation['windows'])):
            _error()
    for window in neural['windows']:
        if type(window) is not dict or set(window) != {'model_id','start_s','duration_s','reason','input_status','input_reason','anchor_s','confidence','downbeat'}:
            _error()
        if (window['model_id'] is not None and type(window['model_id']) is not str) or type(window['reason']) is not str or window['model_id'] not in {None, 'model7', 'model8'} or window['reason'] not in {
                'window_unavailable', 'model_unavailable', 'ambiguous', 'tempo_mismatch', 'weak_audio', 'confirmed', 'audio_error'}:
            _error()
        if type(window['input_status']) is not str or window['input_status'] not in {
                'ok','unavailable','missing_model','unsupported_model','model_error','service_error','decode_error'}:
            _error()
        if window['input_reason'] is not None and (type(window['input_reason']) is not str or len(window['input_reason']) > 1000):
            _error()
        _number(window['start_s'], nullable=False)
        _number(window['duration_s'], nullable=False)
        if window['duration_s'] <= 0:
            _error()
        _number(window['anchor_s'])
        _number(window['confidence'], maximum=1.)
        if type(window['downbeat']) is not dict:
            _error()
        if window['downbeat']:
            _validate_downbeat(window['downbeat'], external=True)
        if window['reason'] == 'confirmed' and (window['anchor_s'] is None or window['confidence'] is None
                or not DOWNBEAT_RELIABLE_MIN <= window['confidence'] < 1.):
            _error()
    if neural['reason'] == 'adopted':
        confirmed_all = [window for window in neural['windows']
                         if window['reason'] == 'confirmed']
        winner = min(confirmed_all, key=lambda window: (
            window['anchor_s'], window['model_id'],
        )) if confirmed_all else None
        if (not confirmed_all
                or winner['anchor_s'] != neural['candidate_anchor_s']
                or value['confidence'] != min(window['confidence'] for window in confirmed_all)):
            _error()
        confirmed_by_model = {}
        for model_id in ('model7', 'model8'):
            confirmed = sorted(
                (window for window in neural['windows']
                 if window['model_id'] == model_id and window['reason'] == 'confirmed'),
                key=lambda window: window['start_s'],
            )
            if (len(confirmed) < BEATGRID_MIN_WINDOWS
                    or any(right['start_s'] < left['start_s'] + left['duration_s']
                           for left, right in zip(confirmed, confirmed[1:]))):
                _error()
            confirmed_by_model[model_id] = {
                (window['start_s'], window['duration_s']) for window in confirmed
            }
        if confirmed_by_model['model7'] != confirmed_by_model['model8']:
            _error()


BAR_POSITION_STATUSES = frozenset({'unknown', 'aligned', 'candidate_rotation', 'conflict'})
BAR_POSITION_REASONS = frozenset({
    'reference_not_verified', 'reference_constant_offset', 'invalid_reference', 'window_count', 'window_overlap',
    'insufficient_evidence', 'rotation_disagreement', 'measured', 'offset_compensated',
})
BAR_POSITION_WINDOW_STATUSES = frozenset({
    'unavailable', 'invalid_events', 'conflict', 'insufficient_matches',
    'time_mismatch', 'measured',
})


def _validate_bar_position_comparison(value):
    required = {'status', 'reason', 'rotation_beats', 'windows', 'audio_confirmation'}
    if (type(value) is not dict or set(value) != required
            or type(value['status']) is not str
            or value['status'] not in BAR_POSITION_STATUSES
            or type(value['reason']) is not str or value['reason'] not in BAR_POSITION_REASONS
            or type(value['windows']) is not list or len(value['windows']) > 6):
        _error()
    rotation = value['rotation_beats']
    if rotation is not None and (type(rotation) is not int or not 0 <= rotation <= 3):
        _error()
    rows = value['windows']
    seen = set()
    measured_rotations = set()
    for row in rows:
        fields = {'model_id', 'start_s', 'status', 'matched_beats', 'max_time_error_ms',
                  'rotation_beats', 'decoder_positions', 'rekordbox_positions',
                  'rotation_candidates'}
        if (type(row) is not dict or set(row) != fields
                or row['model_id'] not in {'model7', 'model8'}
                or type(row['status']) is not str or row['status'] not in BAR_POSITION_WINDOW_STATUSES):
            _error()
        _number(row['start_s'], nullable=False)
        key = (row['model_id'], row['start_s'])
        if key in seen:
            _error()
        seen.add(key)
        _count(row['matched_beats'])
        _number(row['max_time_error_ms'], maximum=6.0)
        for name in ('decoder_positions', 'rekordbox_positions', 'rotation_candidates'):
            values = row[name]
            allowed = {0, 1, 2, 3} if name == 'rotation_candidates' else {1, 2, 3, 4}
            if (type(values) is not list or any(type(item) is not int or item not in allowed
                                                  for item in values)
                    or values != sorted(set(values))):
                _error()
        item_rotation = row['rotation_beats']
        if item_rotation is not None and (type(item_rotation) is not int or not 0 <= item_rotation <= 3):
            _error()
        if row['status'] == 'measured':
            if (row['matched_beats'] < 4 or row['decoder_positions'] != [1, 2, 3, 4]
                    or row['rekordbox_positions'] != [1, 2, 3, 4]
                    or item_rotation is None or row['rotation_candidates'] != [item_rotation]
                    or row['max_time_error_ms'] is None):
                _error()
            measured_rotations.add(item_rotation)
        elif item_rotation is not None:
            _error()
        if row['status'] == 'conflict' and len(row['rotation_candidates']) < 2:
            _error()
    if value['status'] in {'aligned', 'candidate_rotation'}:
        model_ids = {row['model_id'] for row in rows}
        starts = {row['start_s'] for row in rows}
        expected_pairs = {
            (model_id, start_s)
            for model_id in ('model7', 'model8')
            for start_s in starts
        }
        if (value['reason'] not in {'measured', 'offset_compensated'} or len(rows) != 6
                or any(row['status'] != 'measured' for row in rows)
                or model_ids != {'model7', 'model8'} or len(starts) != 3
                or seen != expected_pairs
                or len(measured_rotations) != 1 or rotation != next(iter(measured_rotations))
                or (value['status'] == 'aligned') != (rotation == 0)):
            _error()
    elif rotation is not None:
        _error()
    if value['status'] == 'conflict' and value['reason'] != 'rotation_disagreement':
        _error()
    if value['status'] == 'unknown' and value['reason'] in {'measured', 'rotation_disagreement'}:
        _error()
    _validate_bar_audio_confirmation(value['audio_confirmation'])


BAR_AUDIO_STATUSES = frozenset({'unknown', 'rejected', 'error', 'audio_confirmed'})
BAR_AUDIO_REASONS = frozenset({
    'not_attempted', 'no_rotation_candidate', 'invalid_candidate',
    'incomplete_model_evidence', 'window_unavailable', 'model_unavailable',
    'weak_audio', 'audio_phase_conflict', 'audio_error', 'final_grid_error',
    'final_grid_rejected', 'independent_windows_unavailable', 'measured',
})
BAR_AUDIO_WINDOW_STATUSES = frozenset({'unavailable', 'confirmed', 'rejected', 'error'})
BAR_AUDIO_GRID_STATUSES = frozenset({
    'unknown', 'not_checked', 'verified', 'mismatch', 'unverifiable', 'unsupported',
})


def _validate_bar_audio_confirmation(value):
    fields = {'status', 'reason', 'expected_anchor_s', 'final_grid_status', 'windows'}
    if (type(value) is not dict or set(value) != fields
            or type(value['status']) is not str
            or value['status'] not in BAR_AUDIO_STATUSES
            or type(value['reason']) is not str or value['reason'] not in BAR_AUDIO_REASONS
            or type(value['final_grid_status']) is not str
            or value['final_grid_status'] not in BAR_AUDIO_GRID_STATUSES
            or type(value['windows']) is not list or len(value['windows']) > 6):
        _error()
    _number(value['expected_anchor_s'])
    seen = set()
    for row in value['windows']:
        fields = {'model_id', 'start_s', 'status', 'reason', 'anchor_s',
                  'confidence', 'phase_error_ms'}
        if (type(row) is not dict or set(row) != fields
                or row['model_id'] not in {'model7', 'model8'}
                or type(row['status']) is not str
                or row['status'] not in BAR_AUDIO_WINDOW_STATUSES
                or type(row['reason']) is not str or row['reason'] not in BAR_AUDIO_REASONS):
            _error()
        _number(row['start_s'], nullable=False)
        key = (row['model_id'], row['start_s'])
        if key in seen:
            _error()
        seen.add(key)
        _number(row['anchor_s'])
        _number(row['confidence'], maximum=1.0)
        _number(row['phase_error_ms'], maximum=10000.0)
        if row['status'] == 'confirmed' and any(
                row[name] is None for name in ('anchor_s', 'confidence', 'phase_error_ms')):
            _error()
    if value['status'] == 'audio_confirmed':
        from .downbeat import DOWNBEAT_RELIABLE_MIN
        if (value['reason'] != 'measured' or len(value['windows']) != 6
                or any(row['status'] != 'confirmed'
                       or row['confidence'] < DOWNBEAT_RELIABLE_MIN
                       or row['phase_error_ms'] > 6.0 for row in value['windows'])
                or value['expected_anchor_s'] is None
                or value['final_grid_status'] != 'verified'):
            _error()
    elif value['status'] == 'unknown':
        if value['windows'] or value['expected_anchor_s'] is not None:
            _error()
    elif value['status'] == 'error' and value['reason'] != 'final_grid_error':
        _error()


PHRASE_UNIT_DIAGNOSTIC_FIELDS = frozenset({
    'unit', 'source', 'candidate', 'raw_score', 'ranking_margin',
})


def _validate_phrase_unit_diagnostic(value):
    if type(value) is not dict or set(value) != PHRASE_UNIT_DIAGNOSTIC_FIELDS:
        _error()
    if value['unit'] is not None and (
            type(value['unit']) is not int or value['unit'] not in {8, 16, 32}):
        _error()
    if type(value['source']) is not str or value['source'] not in {
            'unknown', 'genre_prior', 'audio_novelty', 'configured'}:
        _error()
    if value['candidate'] is not None and (
            type(value['candidate']) is not int or value['candidate'] not in {8, 16, 32}):
        _error()
    raw_score = value['raw_score']
    if (raw_score is not None
            and (type(raw_score) not in (int, float) or not math.isfinite(raw_score))):
        _error()
    _number(value['ranking_margin'], minimum=0.0)
    if value['candidate'] is None:
        if value['raw_score'] is not None or value['ranking_margin'] is not None:
            _error()
    elif value['raw_score'] is None:
        _error()
    if value['source'] == 'audio_novelty' and (
            value['unit'] != value['candidate']
            or value['raw_score'] is None
            or value['ranking_margin'] is None):
        _error()


def _validate_tempo_diagnostic(value):
    fields = {
        'status', 'reason', 'model_bpm', 'refined_bpm', 'model_spread',
        'model_samples',
    }
    if (type(value) is not dict or set(value) != fields
            or type(value['status']) is not str
            or value['status'] not in {'baseline', 'accepted'}
            or type(value['reason']) is not str or value['reason'] not in TEMPO_REASONS):
        _error()
    for name in ('model_bpm', 'refined_bpm'):
        _number(value[name], minimum=0.0)
        if value[name] is not None and value[name] <= 0:
            _error()
    _number(value['model_spread'], minimum=0.0)
    samples = value['model_samples']
    if type(samples) is not list or len(samples) > 6:
        _error()
    seen = set()
    for sample in samples:
        if (type(sample) is not dict
                or set(sample) != {'model_id', 'start_s', 'bpm'}
                or type(sample['model_id']) is not str
                or sample['model_id'] not in {'model7', 'model8'}):
            _error()
        _number(sample['start_s'], minimum=0.0, nullable=False)
        _number(sample['bpm'], minimum=0.0, nullable=False)
        if sample['bpm'] <= 0:
            _error()
        identity = (sample['model_id'], sample['start_s'])
        if identity in seen:
            _error()
        seen.add(identity)
    if len(samples) == 6:
        sample_tempos = sorted(sample['bpm'] for sample in samples)
        expected_median = (sample_tempos[2] + sample_tempos[3]) / 2.0
        expected_spread = sample_tempos[-1] / sample_tempos[0] - 1.0
        if (value['model_bpm'] is None or value['model_spread'] is None
                or not math.isclose(value['model_bpm'], expected_median,
                                    rel_tol=1e-9, abs_tol=1e-9)
                or not math.isclose(value['model_spread'], expected_spread,
                                    rel_tol=1e-9, abs_tol=1e-12)):
            _error()
    if value['status'] == 'accepted' or value['reason'] == 'model_disagreement':
        from .downbeat import BEATGRID_MAX_INTERVAL_DEVIATION

        if value['model_spread'] is None:
            _error()
        if value['reason'] == 'model_disagreement':
            if len(samples) != 6 or value['model_spread'] <= BEATGRID_MAX_INTERVAL_DEVIATION:
                _error()
        elif value['model_spread'] > BEATGRID_MAX_INTERVAL_DEVIATION:
            _error()
    if value['status'] == 'accepted':
        if (value['reason'] != 'accepted' or value['model_bpm'] is None
                or value['refined_bpm'] is None or value['model_spread'] is None
                or len(samples) != 6
                or {sample['model_id'] for sample in samples} != {'model7', 'model8'}
                or len({sample['start_s'] for sample in samples}) != 3):
            _error()
        if any(
            abs(value['refined_bpm'] / sample['bpm'] - 1.0)
            > BEATGRID_MAX_INTERVAL_DEVIATION
            for sample in samples
        ):
            _error()
    elif value['reason'] == 'accepted':
        _error()


def validate_measurement_diagnostics(value):
    """Gespeicherte Fremdschluessel ablehnen; {} bleibt ausdruecklich unbekannt."""
    if type(value) is not dict:
        _error()
    if not value:
        return
    if type(value.get('version')) is not int or value['version'] not in {1, 2, 3, 4, 5, 6, 7, 8}:
        _error()
    keys = {'version', 'downbeat', 'grid'} | (
        {'anchor'} if value['version'] in {2, 3, 4, 5, 6, 7, 8} and 'anchor' in value else set()
    )
    if value['version'] in {6, 7, 8}:
        keys.add('phrase_unit')
    if value['version'] == 7 or value['version'] == 8 and 'tempo' in value:
        keys.add('tempo')
    if value['version'] == 8:
        keys.add('native_grid')
    if set(value) != keys:
        _error()
    if value['version'] in {2, 3, 4, 5, 6, 7, 8} and 'anchor' in value:
        _validate_anchor(value['anchor'], schema_version=value['version'])
        if type(value['grid']) is not dict:
            _error()
        if value['anchor']['method'] in {'rekordbox', 'neural_audio'} and value['grid'].get('status') != 'verified':
            _error()
    downbeat, grid = value["downbeat"], value["grid"]
    _validate_downbeat(downbeat, external=value['version'] in {2, 3, 4, 5, 6, 7, 8})
    current_schema = value['version'] in {3, 4, 5, 6, 7, 8}
    if value['version'] in {6, 7, 8}:
        _validate_phrase_unit_diagnostic(value['phrase_unit'])
    if 'tempo' in value:
        _validate_tempo_diagnostic(value['tempo'])
    if value['version'] == 8:
        native = value['native_grid']
        if (type(native) is not dict or set(native) != {'status', 'reason'}
                or type(native['status']) is not str
                or native['status'] not in {'accepted', 'rejected', 'unavailable', 'disabled'}
                or type(native['reason']) is not str
                or native['reason'] not in {
                    'verified', 'audio_offset_confirmed', 'grid_unverified',
                    'variable_grid_unsupported', 'offset_out_of_range',
                    'offset_confirmation_windows_missing',
                    'offset_audio_confirmation_failed', 'offset_audio_decode_failed',
                    'native_unavailable', 'unsupported_duration', 'disabled'}
                or (native['status'], native['reason']) not in {
                    ('accepted', 'verified'), ('accepted', 'audio_offset_confirmed'),
                    ('rejected', 'grid_unverified'), ('rejected', 'variable_grid_unsupported'),
                    ('rejected', 'offset_out_of_range'),
                    ('rejected', 'offset_confirmation_windows_missing'),
                    ('rejected', 'offset_audio_confirmation_failed'),
                    ('rejected', 'offset_audio_decode_failed'),
                    ('unavailable', 'native_unavailable'),
                    ('unavailable', 'unsupported_duration'), ('disabled', 'disabled')}
                or (native['status'] == 'accepted'
                    and (type(value['grid']) is not dict
                         or value['grid'].get('status') != 'verified'))):
            _error()
    grid_fields = GRID_FIELDS if current_schema else LEGACY_GRID_FIELDS
    window_fields = WINDOW_FIELDS if current_schema else LEGACY_WINDOW_FIELDS
    if type(grid) is not dict or set(grid) != grid_fields:
        _error()
    if type(grid["status"]) is not str or grid["status"] not in {"unknown", "unverifiable", "unsupported", "mismatch", "verified"}:
        _error()
    if type(grid["reason"]) is not str or grid["reason"] not in GRID_REASONS:
        _error()
    _count(grid["windows_checked"])
    _number(grid["max_phase_error_ms"], minimum=-1.0, nullable=False)
    if grid["max_phase_error_ms"] < 0 and grid["max_phase_error_ms"] != -1.0:
        _error()
    windows = grid["window_diagnostics"]
    failures = grid["decode_failures"]
    if type(windows) is not list or type(failures) is not list or len(windows) + len(failures) > 100:
        _error()
    for window in windows:
        if type(window) is not dict or set(window) != window_fields:
            _error()
        if type(window["reason"]) is not str or window["reason"] not in WINDOW_REASONS:
            _error()
        for name in window_fields - {"reason", "fold_lock", "signed_phase_error_ms"}:
            _number(window[name])
        _number(window["fold_lock"], maximum=1.0)
        if current_schema:
            _number(window['signed_phase_error_ms'], minimum=-600.0, maximum=600.0)
        if window["reason"] == "measured" and any(window[k] is None for k in window_fields - {"reason"}):
            _error()
    if current_schema:
        measured_residuals = sum(
            window['reason'] == 'measured' and window['signed_phase_error_ms'] is not None
            for window in windows
        )
        if type(grid['phase_pattern']) is not str or grid['phase_pattern'] not in {
                'unknown', 'aligned', 'consistent_offset', 'variable_phase'}:
            _error()
        _number(grid['phase_center_ms'], minimum=-600.0, maximum=600.0)
        if (grid['status'] == 'verified'
                and grid['phase_pattern'] not in {'aligned', 'unknown'}):
            _error()
        if (grid['phase_center_ms'] is not None
                and grid['phase_pattern'] not in {'aligned', 'consistent_offset', 'variable_phase'}):
            _error()
        if grid['phase_pattern'] == 'aligned' and grid['phase_center_ms'] is not None:
            from .downbeat import EXACT_BEAT_SYNC_TOLERANCE_SECONDS
            # Auch ein bestätigtes Grid hat einen gemessenen Median. Er darf
            # gespeichert werden, muss aber innerhalb derselben Sync-Grenze liegen.
            if abs(grid['phase_center_ms']) > EXACT_BEAT_SYNC_TOLERANCE_SECONDS * 1000.0:
                _error()
        if grid['phase_pattern'] == 'consistent_offset':
            from .downbeat import EXACT_BEAT_SYNC_TOLERANCE_SECONDS

            if (grid['status'] != 'mismatch'
                    or grid['phase_center_ms'] is None
                    or abs(grid['phase_center_ms'])
                       <= EXACT_BEAT_SYNC_TOLERANCE_SECONDS * 1000.0
                    or measured_residuals < 3):
                _error()
        if grid['status'] == 'mismatch':
            if grid['phase_pattern'] in {'consistent_offset', 'variable_phase'}:
                pass
            elif not (grid['phase_pattern'] == 'unknown'
                      and grid['windows_checked'] == 0
                      and measured_residuals == 0
                      and grid['phase_center_ms'] is None):
                _error()
        if grid['status'] in {'unknown', 'unverifiable', 'unsupported'} and grid['phase_pattern'] != 'unknown':
            _error()
        if measured_residuals >= 3 and grid['phase_center_ms'] is None:
            _error()
    if (value['version'] in {6, 7, 8}
            and value['phrase_unit']['source'] == 'audio_novelty'):
        from .downbeat import DOWNBEAT_RELIABLE_MIN
        anchor = value.get('anchor')
        native_beat_anchor = (
            type(anchor) is dict
            and anchor.get('method') in {'native_rekordbox', 'native_rekordbox_audio_offset'}
            and anchor.get('confidence') == 0.0
        )
        if (grid['status'] != 'verified' or type(anchor) is not dict
                or (anchor['confidence'] < DOWNBEAT_RELIABLE_MIN and not native_beat_anchor)):
            _error()
    for failure in failures:
        if type(failure) is not dict or set(failure) != {"offset_seconds", "reason"} or failure["reason"] != "decode_error":
            _error()
        _number(failure["offset_seconds"], nullable=False)


def measurement_snapshot(
    downbeat, grid, *, decode_failures=(), anchor_decision=None,
    phrase_unit_diagnostic=None, tempo_diagnostic=None, native_grid_diagnostic=None,
):
    """Nur bekannte Producer-Felder projizieren; Legacy-Mocks liefern unbekannt."""
    measured = {key: deepcopy(value) for key, value in downbeat.items() if key in DOWNBEAT_FIELDS}
    measured.setdefault("reason", "unknown")
    measured.setdefault("stage", None)
    grid_data = asdict(grid)
    grid_data["reason"] = grid_data.get("reason") or "unknown"
    grid_data["window_diagnostics"] = list(grid_data.get("window_diagnostics", ()))
    grid_data["decode_failures"] = deepcopy(list(decode_failures))
    result = {"version": 5, "downbeat": measured, "grid": grid_data}
    if anchor_decision is not None:
        result.update(anchor=deepcopy(anchor_decision))
    if phrase_unit_diagnostic is not None:
        result['version'] = 6
        result['phrase_unit'] = deepcopy(phrase_unit_diagnostic)
    if tempo_diagnostic is not None:
        result['version'] = 7
        result['tempo'] = deepcopy(tempo_diagnostic)
    if native_grid_diagnostic is not None:
        result['version'] = 8
        result['native_grid'] = deepcopy(native_grid_diagnostic)
    validate_measurement_diagnostics(result)
    return result

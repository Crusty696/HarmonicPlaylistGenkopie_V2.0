"""Externe Ereignisse liefern Kandidaten; das Audio muss deren Eins bestätigen."""
import copy

import numpy as np
import pytest

from hpg_core import downbeat as d
from tests.test_downbeat import SR, _make_four_on_floor

BPM = 128.
IBI = 60 / BPM
ONE = .3


@pytest.fixture(scope='module')
def known():
    audio = _make_four_on_floor(BPM, 40., ONE)
    times = np.arange(ONE, 39.5, IBI)
    events = [dict(time_s=float(value), position=index % 4 + 1, observed=True)
              for index, value in enumerate(times)]
    return audio, events


def external(monkeypatch, known, events=None, **kwargs):
    monkeypatch.setattr(d.librosa.beat, 'beat_track',
                        lambda **kw: pytest.fail('Externe Beats dürfen keinen Tracker starten'))
    diagnostics = {}
    audio, original = known
    result = d.estimate_first_downbeat(audio, SR, BPM, diagnostics=diagnostics,
        external_beats=original if events is None else events, **kwargs)
    return result, diagnostics


@pytest.mark.parametrize('rotation', range(4))
def test_real_audio_confirms_known_bar_with_rotated_window_start(monkeypatch, known, rotation):
    (anchor, confidence), diagnostics = external(monkeypatch, known, known[1][rotation:])
    assert anchor == pytest.approx(ONE, abs=d.EXACT_BEAT_SYNC_TOLERANCE_SECONDS)
    assert d.DOWNBEAT_RELIABLE_MIN <= confidence <= d.SELF_ESTIMATE_CONFIDENCE_MAX
    assert diagnostics['reason'] == 'ok'


def test_predictions_and_missing_bar_do_not_renumber(monkeypatch, known):
    events = copy.deepcopy(known[1])
    for index in range(20, 24):
        events[index]['observed'] = False
    first, diag = external(monkeypatch, known, events)
    removed = [event for event in events if event['observed']]
    second, _ = external(monkeypatch, known, removed)
    assert first == second
    assert first[0] == pytest.approx(ONE, abs=d.EXACT_BEAT_SYNC_TOLERANCE_SECONDS)
    assert first[1] >= d.DOWNBEAT_RELIABLE_MIN
    assert diag['grid_ibi_seconds'] == pytest.approx(IBI)


def test_predictions_do_not_count_toward_minimum(monkeypatch, known):
    events = copy.deepcopy(known[1])
    for event in events[15:]:
        event['observed'] = False
    result, diagnostics = external(monkeypatch, known, events)
    assert result == (0., 0.)
    assert diagnostics['reason'] == 'fewbeats'


@pytest.mark.parametrize('change', ['empty', 'booltime', 'boolposition', 'boolobserved',
  'nan', 'negative', 'duplicate', 'reversed', 'end', 'extra', 'badrotation'])
def test_invalid_external_events_no_fallback(monkeypatch, known, change):
    events = copy.deepcopy(known[1])
    if change == 'empty': events = []
    elif change == 'booltime': events[0]['time_s'] = True
    elif change == 'boolposition': events[0]['position'] = True
    elif change == 'boolobserved': events[0]['observed'] = 1
    elif change == 'nan': events[0]['time_s'] = float('nan')
    elif change == 'negative': events[0]['time_s'] = -.1
    elif change == 'duplicate': events[1]['time_s'] = events[0]['time_s']
    elif change == 'reversed': events.reverse()
    elif change == 'end': events[-1]['time_s'] = len(known[0]) / SR
    elif change == 'extra': events[0]['confidence'] = 1.
    elif change == 'badrotation': events[7]['position'] = 1
    result, _ = external(monkeypatch, known, events)
    assert result == (0., 0.)


@pytest.mark.parametrize('change', ['half', 'double'])
def test_foreign_metric_has_no_retry(monkeypatch, known, change):
    if change == 'half':
        events = known[1][::2]
    else:
        events = [dict(time_s=float(value), position=index % 4 + 1, observed=True)
                  for index, value in enumerate(np.arange(ONE, 39.5, IBI/2))]
    assert external(monkeypatch, known, events)[0] == (0., 0.)


def test_audio_rejects_model_bar_rotation(monkeypatch, known):
    events = copy.deepcopy(known[1])
    for event in events:
        event['position'] = event['position'] % 4 + 1
    result, diagnostics = external(monkeypatch, known, events)
    assert result == (0., 0.)
    assert diagnostics['reason'] == 'external_vote_conflict'


def test_internal_candidate_mode_keeps_audio_phase_on_model_conflict(monkeypatch, known):
    (anchor, confidence), diagnostics = external(
        monkeypatch, known,
        [dict(time_s=event['time_s'], position=event['position'] % 4 + 1,
              observed=event['observed']) for event in known[1]],
        _allow_external_conflict_candidate=True,
    )
    assert anchor == pytest.approx(ONE, abs=d.EXACT_BEAT_SYNC_TOLERANCE_SECONDS)
    assert confidence >= d.DOWNBEAT_RELIABLE_MIN
    assert diagnostics['reason'] == 'external_vote_conflict'


@pytest.mark.parametrize('alignment', ['none', 'few', 'classes'])
def test_alignment_must_keep_enough_observations(monkeypatch, known, alignment):
    def align(times, numbers, *args):
        if alignment == 'none': return None
        mask = np.arange(len(times)) < 15 if alignment == 'few' else numbers % 4 != 3
        return times[mask], numbers[mask], mask
    monkeypatch.setattr(d, '_align_beat_feature_grid', align)
    assert external(monkeypatch, known)[0] == (0., 0.)


@pytest.mark.parametrize('trim', ['classes', 'few'])
def test_trim_requires_all_four_observed_classes_and_minimum(monkeypatch, known, trim):
    def energy(audio, start, end):
        number = round((start / SR - ONE) / IBI)
        missing = number % 4 == 3 if trim == 'classes' else number >= 15
        return 0. if missing else end - start
    monkeypatch.setattr(d, '_sample_energy_integral', energy)
    result, diagnostics = external(monkeypatch, known)
    assert result == (0., 0.)
    assert diagnostics['stage'] == 'trim'


def test_alignment_edge_trim_keeps_original_numbers(monkeypatch, known):
    original = d._align_beat_feature_grid
    def trimmed(*args):
        times, numbers, keep = original(*args)
        assert numbers[0] == 0
        keep[np.flatnonzero(keep)[0]] = False
        return times[1:], numbers[1:], keep
    monkeypatch.setattr(d, '_align_beat_feature_grid', trimmed)
    (anchor, confidence), diagnostics = external(monkeypatch, known)
    assert anchor == pytest.approx(ONE, abs=d.EXACT_BEAT_SYNC_TOLERANCE_SECONDS)
    assert confidence >= d.DOWNBEAT_RELIABLE_MIN
    assert diagnostics['reason'] == 'ok'


def test_audio_vote_tie_is_not_confirmation(monkeypatch, known):
    monkeypatch.setattr(d, '_znorm', lambda values: np.zeros_like(values))
    result, diagnostics = external(monkeypatch, known)
    assert result == (0., 0.)
    assert diagnostics['reason'] == 'external_vote_ambiguous'


def test_default_none_matches_existing_tracker_path(monkeypatch, known):
    calls = []
    frames = d.librosa.time_to_frames([event['time_s'] for event in known[1]], sr=SR, hop_length=d.HOP_LENGTH)
    def track(**kwargs):
        calls.append(kwargs)
        return BPM, frames
    monkeypatch.setattr(d.librosa.beat, 'beat_track', track)
    first = d.estimate_first_downbeat(known[0], SR, BPM)
    second = d.estimate_first_downbeat(known[0], SR, BPM, external_beats=None)
    assert first == second
    assert len(calls) == 2

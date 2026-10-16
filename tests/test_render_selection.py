"""Reservevertrag ohne Modell- oder Originalaudio-Wiederholungen."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from hpg_core.playlist import generate_playlist_result
from hpg_core.render_selection import render_with_reserve
from hpg_core.transition_renderer import BeatSyncError
from tests.test_pair_candidates import _track_mit_kandidaten, _voll, _grid


@pytest.fixture
def result():
    grid = _grid()
    a = _track_mit_kandidaten('a.mp3', outs=[_voll(round(5*grid,3)), _voll(round(6*grid,3))])
    b = _track_mit_kandidaten('b.mp3', ins=[_voll(round(3*grid,3))])
    return generate_playlist_result([a,b], 'Harmonic Flow', candidate_choice_snapshot={})


def test_reserve_deduplicates_and_returns_matching_plan(result):
    seen = []
    def render(spec, sources):
        key = (spec['mix_out_sec'],spec['mix_in_sec'],spec['crossfade_sec'])
        assert key not in seen
        seen.append(key)
        if len(seen) == 1:
            raise BeatSyncError('kontrollierter erster Fehlschlag')
        return b'RAM-Testantwort'
    selected = render_with_reserve(result, 0, [], lambda: None, render=render)
    assert len(seen) == 2 and len(selected.rejected) == 1
    plan = selected.playlist.recommendations[0].plan
    assert plan.mix_out_a == selected.spec.mix_out_sec
    assert plan.overlap == selected.spec.crossfade_sec
    assert selected.playlist.tracks == result.tracks


@pytest.mark.parametrize('error', [OSError('Quelle fehlt'), InterruptedError('Abbruch')])
def test_non_sync_errors_never_start_reserve(result, error):
    render = Mock(side_effect=error)
    with pytest.raises(type(error)):
        render_with_reserve(result, 0, [], lambda: None, render=render)
    assert render.call_count == 1


def test_cancel_before_render(result):
    render = Mock()
    with pytest.raises(InterruptedError):
        render_with_reserve(result, 0, [], Mock(side_effect=InterruptedError()), render=render)
    render.assert_not_called()


def test_stale_gui_result_is_not_published():
    from main import MainWindow
    window = SimpleNamespace(_close_pending=False, current_generation_result=object(),
                             _publiziere_generation_result=Mock())
    MainWindow._on_render_reserve_ready(window, (object(), None, None, None, ()))
    window._publiziere_generation_result.assert_not_called()


def test_gui_publishes_plan_before_installing_audio():
    from main import MainWindow
    base, updated = object(), object()
    events = []
    panel = SimpleNamespace(_ram_preview_cache={}, _preview_transitions={},
        _show_ram_preview=lambda *args: events.append('audio'),
        _request_preview=lambda *args: events.append('next'))
    window = SimpleNamespace(_close_pending=False, current_generation_result=base,
        mix_tips_panel=panel, _publiziere_generation_result=lambda result: events.append('plan'))
    selected = SimpleNamespace(playlist=updated, boundary_index=0, audio=b'RAM', spec=None)
    MainWindow._on_render_reserve_ready(window, (base, selected, [], 1., (1,)))
    assert events == ['plan', 'audio', 'next']


def test_reserve_success_is_counted_before_status_signal():
    from collections import deque
    from main import MixTipsPanel
    worker = SimpleNamespace(selection=object(), base_result=object(), peaks=[], duration=1.,
        get_temp_dir=lambda: None, get_temp_files=lambda: [], deleteLater=Mock())
    panel = SimpleNamespace(_render_workers=[worker], _render_worker=worker,
        _preview_batch_cancelled=False, _preview_queue=deque(), _preview_cache={},
        _preview_batch_successes=0, _preview_batch_active=True, reserve_ready=Mock())
    observed = []
    panel.preview_state_changed = SimpleNamespace(emit=lambda busy:
        observed.append((busy, panel._preview_batch_successes)))
    MixTipsPanel._on_preview_worker_finished(panel, worker)
    assert observed == [(False, 1)]
    panel.reserve_ready.emit.assert_called_once()

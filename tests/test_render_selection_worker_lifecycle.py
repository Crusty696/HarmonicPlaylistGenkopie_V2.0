"""Nur Lebenszyklus: kontrollierte Kindprozesse, keine Audio-/Modelllaeufe."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from hpg_core import render_selection_worker as module


@pytest.mark.parametrize('case', ['ok', 'crashed', 'stuck', 'cancelled', 'late'])
def test_result_requires_clean_timely_uncancelled_child(monkeypatch, case):
    worker = module.RenderSelectionWorker(None, 0, timeout=10.)
    errors = []
    worker.clip_error.connect(lambda index, message: errors.append(message))
    clock = [0.]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    alive = [case == 'stuck']
    process = Mock()
    process.exitcode = 1 if case == 'crashed' else 0
    process.is_alive.side_effect = lambda: alive[0]
    process.terminate.side_effect = lambda: alive.__setitem__(0, False)
    selected = object()
    def receive():
        if case == 'cancelled':
            worker.request_cancel()
        if case == 'late':
            clock[0] = 11.
        return True, selected, [.2], 2.
    receiver, sender = Mock(), Mock()
    receiver.poll.return_value = True
    receiver.recv.side_effect = receive
    context = SimpleNamespace(Pipe=lambda **kw: (receiver, sender),
                              Process=lambda **kw: process)
    monkeypatch.setattr(module.multiprocessing, 'get_context', lambda *a: context)
    worker.run()
    if case == 'ok':
        assert worker.selection is selected
        assert not errors
    else:
        assert worker.selection is None
        assert bool(errors) == (case != 'cancelled')
    assert not alive[0]
    process.close.assert_called_once()
    receiver.close.assert_called_once()


def test_cancel_before_start_allocates_no_process(monkeypatch):
    factory = Mock()
    monkeypatch.setattr(module.multiprocessing, 'get_context', factory)
    worker = module.RenderSelectionWorker(None, 0)
    worker.request_cancel()
    worker.run()
    factory.assert_not_called()


def test_process_setup_error_reaches_gui(monkeypatch):
    monkeypatch.setattr(module.multiprocessing, 'get_context', Mock(side_effect=OSError('setup failed')))
    worker = module.RenderSelectionWorker(None, 0)
    errors = []
    worker.clip_error.connect(lambda i, text: errors.append(text))
    worker.run()
    assert errors == ['setup failed']
    assert worker.selection is None


@pytest.mark.parametrize('timeout', [True, 0, -1, float('nan'), float('inf')])
def test_invalid_timeout_rejected(timeout):
    with pytest.raises(ValueError, match='Renderzeitlimit'):
        module.RenderSelectionWorker(None, 0, timeout=timeout)

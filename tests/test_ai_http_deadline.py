"""Gesamtfrist und Ressourcenfreigabe des isolierten KI-Requests."""
from types import SimpleNamespace

import pytest
import requests

from hpg_core import ai_engine


@pytest.mark.parametrize('timeout', [0.2, (0.1, 0.1)])
@pytest.mark.parametrize('outcome', ['timeout', 'response', 'cancel', 'eof'])
def test_http_request_has_bounded_lifetime(monkeypatch, timeout, outcome):
    clock = [0.0]
    closed = []
    stopped = []

    class Pipe:
        def poll(self, wait=0):
            clock[0] += 0.05
            # Der alte Code soll reproduzierbar scheitern statt ewig hängen.
            assert clock[0] < 1.0, 'Request überschreitet seine Gesamtfrist'
            return outcome in {'response', 'eof'}

        def recv(self):
            if outcome == 'eof':
                raise EOFError
            return ('response', 200, '{"ok": true}')

        def close(self):
            closed.append(self)

    receive, send = Pipe(), Pipe()
    process = SimpleNamespace(start=lambda: None, is_alive=lambda: True)
    context = SimpleNamespace(Pipe=lambda **kw: (receive, send),
                              Process=lambda **kw: process)
    monkeypatch.setattr(ai_engine.multiprocessing, 'get_context', lambda method: context)
    monkeypatch.setattr(ai_engine, '_stop_spawned_process', stopped.append)
    # Eigenes Zeitobjekt verändert keine globale pytest-/Qt-Uhr.
    monkeypatch.setattr(ai_engine, 'time', SimpleNamespace(monotonic=lambda: clock[0]), raising=False)
    cancel = lambda: outcome == 'cancel' and clock[0] >= 0.1
    expected = {'timeout': requests.exceptions.Timeout,
                'cancel': InterruptedError, 'eof': requests.exceptions.RequestException}
    if outcome == 'response':
        assert ai_engine._cancelable_post('http://local', {}, timeout, cancel).json() == {'ok': True}
    else:
        with pytest.raises(expected[outcome]):
            ai_engine._cancelable_post('http://local', {}, timeout, cancel)
    assert closed == [send, receive]
    assert stopped == [process]
    assert clock[0] <= 0.25

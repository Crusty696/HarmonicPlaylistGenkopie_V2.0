"""Echte Windows-Spawn-Proben ohne Modelle oder Audiodateien."""
import os
import multiprocessing as mp
import threading
import time

import pytest

from hpg_core.ai_models import process_runtime as runtime

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows-Prozessvertrag')


def echo_handler(payload):
    if payload == b'crash':
        os._exit(71)
    if payload == b'hang':
        time.sleep(60)
    if payload == b'oversize':
        return b'x' * 4097
    if payload == b'wrong':
        return 'not bytes'
    if payload == b'pid':
        return str(os.getpid()).encode()
    return payload


def make(**kwargs):
    return runtime.OwnedModelProcess(__name__, 'echo_handler', **kwargs)


def deadline(seconds=10):
    return time.monotonic() + seconds


def test_lazy_reuse_and_close():
    process = make()
    assert process.state == 'NEW'
    assert process.pid is None
    first = process.call(b'pid', deadline=deadline())
    assert first != str(os.getpid()).encode()
    assert process.call(b'pid', deadline=deadline()) == first
    assert process.state == 'READY'
    process.close()
    process.close()
    with pytest.raises(runtime.ModelProcessClosed):
        process.call(b'x', deadline=deadline())


@pytest.mark.parametrize('payload,error', [(b'crash', runtime.ModelProcessCrashed),
                                          (b'hang', runtime.ModelProcessTimeout)])
def test_failure_restart(payload, error):
    with make() as process:
        first = process.call(b'pid', deadline=deadline())
        start = time.monotonic()
        with pytest.raises(error):
            process.call(payload, deadline=deadline(.15 if payload == b'hang' else 5))
        assert time.monotonic() - start < 4
        assert process.call(b'pid', deadline=deadline()) != first


def test_payload_bounds_and_type():
    with make(max_payload_bytes=4096) as process:
        with pytest.raises(runtime.ModelProcessProtocolError):
            process.call(b'x' * 4097, deadline=deadline())
        assert process.pid is None
        with pytest.raises(runtime.ModelProcessProtocolError):
            process.call('text', deadline=deadline())
        with pytest.raises(runtime.ModelProcessProtocolError):
            process.call(b'oversize', deadline=deadline())
        assert process.call(b'ok', deadline=deadline()) == b'ok'


def test_waiting_deadline_does_not_cancel_active():
    with make() as process:
        process.call(b'pid', deadline=deadline())
        entered = threading.Event()
        original = process._exchange
        def slow(*args):
            entered.set()
            time.sleep(.3)
            return original(*args)
        process._exchange = slow
        result = []
        thread = threading.Thread(target=lambda: result.append(process.call(b'ok', deadline=deadline())))
        thread.start()
        assert entered.wait(2)
        with pytest.raises(runtime.ModelProcessTimeout):
            process.call(b'waiter', deadline=deadline(.05))
        thread.join(3)
        assert result == [b'ok']


@pytest.mark.parametrize('action', ['close', 'cancel'])
def test_concurrent_stop(action):
    process = make()
    process.call(b'pid', deadline=deadline())
    event = threading.Event()
    errors = []
    def run():
        try:
            process.call(b'hang', deadline=deadline(), cancel_event=event)
        except Exception as error:
            errors.append(error)
    thread = threading.Thread(target=run)
    thread.start()
    time.sleep(.1)
    if action == 'close':
        process.close()
    else:
        event.set()
    thread.join(4)
    assert not thread.is_alive()
    expected = runtime.ModelProcessClosed if action == 'close' else runtime.ModelProcessCancelled
    assert isinstance(errors[0], expected)
    process.close()


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), None, True])
def test_bad_deadline(bad):
    with make() as process:
        with pytest.raises(ValueError):
            process.call(b'a', deadline=bad)


def test_cancel_before_start():
    event = threading.Event()
    event.set()
    with make() as process:
        with pytest.raises(runtime.ModelProcessCancelled):
            process.call(b'a', deadline=deadline(), cancel_event=event)
        assert process.pid is None


def blocked_reader(connection, *args):
    connection.recv_bytes()
    connection.send_bytes(b'READY')
    time.sleep(60)


def malformed_reply(connection, *args):
    connection.recv_bytes()
    connection.send_bytes(b'READY')
    connection.recv_bytes()
    connection.send_bytes(b'bad')


@pytest.mark.parametrize('target,payload,error', [
    (blocked_reader, b'x' * (16 * 1024 * 1024), runtime.ModelProcessTimeout),
    (malformed_reply, b'x', runtime.ModelProcessProtocolError),
], ids=['blocked_send', 'bad_wire'])
def test_blocked_send_and_bad_wire(monkeypatch, target, payload, error):
    monkeypatch.setattr(runtime, '_bootstrap', target)
    with make() as process:
        start = time.monotonic()
        with pytest.raises(error):
            process.call(payload, deadline=deadline(.7))
        assert time.monotonic()-start < 4
        assert process.pid is None


def test_start_deadline(monkeypatch):
    original = runtime.mp.get_context
    def slow_context(method):
        ctx = original(method)
        class Context:
            Pipe = staticmethod(ctx.Pipe)
            @staticmethod
            def Process(**kwargs):
                process = ctx.Process(**kwargs)
                start = process.start
                def slow_start():
                    time.sleep(.2)
                    start()
                process.start = slow_start
                return process
        return Context()
    monkeypatch.setattr(runtime.mp, 'get_context', slow_context)
    with make() as process:
        with pytest.raises(runtime.ModelProcessTimeout):
            process.call(b'x', deadline=deadline(.05))
        assert process.pid is None


def owner_exit(send, mode):
    process = make()
    if mode == 'handshake':
        def exit_before_assign():
            send.send(process.pid)
            os._exit(0)
        runtime._create_job = exit_before_assign
        process.call(b'pid', deadline=deadline())
    else:
        process.call(b'pid', deadline=deadline())
        send.send(process.pid)
        if mode == 'busy':
            threading.Thread(target=lambda: process.call(b'hang', deadline=deadline()), daemon=True).start()
            time.sleep(.1)
        os._exit(0)


def wait_dead(pid):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        return ctypes.get_last_error() == 87
    try:
        return kernel.WaitForSingleObject(handle, 5000) == 0
    finally:
        kernel.CloseHandle(handle)


@pytest.mark.parametrize('mode', ['handshake', 'ready', 'busy'])
def test_owner_exit_reaps_child(mode):
    ctx = mp.get_context('spawn')
    receive, send = ctx.Pipe(duplex=False)
    owner = ctx.Process(target=owner_exit, args=(send, mode))
    owner.start()
    send.close()
    try:
        assert receive.poll(10)
        pid = receive.recv()
        owner.join(5)
        assert not owner.is_alive()
        assert wait_dead(pid)
    finally:
        if owner.is_alive():
            owner.kill()
            owner.join(3)
        owner.close()
        receive.close()


def test_unconfirmed_io_end_poison_no_restart(monkeypatch):
    release = threading.Event()
    entered = threading.Event()
    process = make(cleanup_timeout=.1)
    def stuck(payload):
        entered.set()
        release.wait(3)
        return payload
    monkeypatch.setattr(process, '_exchange', stuck)
    start = time.monotonic()
    try:
        with pytest.raises(runtime.ModelProcessCleanupError):
            process.call(b'x', deadline=deadline(.1))
        assert entered.is_set()
        assert time.monotonic()-start < 1
        assert process.state == 'BROKEN'
        thread = process._thread
        with pytest.raises(runtime.ModelProcessCleanupError):
            process.call(b'y', deadline=deadline())
        assert process._thread is thread
    finally:
        release.set()
        thread.join(2)
        process.close()


def test_job_failure_fails_closed(monkeypatch):
    def failure(*args):
        raise OSError('job rejected')
    monkeypatch.setattr(runtime, '_assign_job', failure)
    with make() as process:
        with pytest.raises(runtime.ModelProcessUnavailable):
            process.call(b'x', deadline=deadline())
        assert process.pid is None


def test_owner_pid_guard():
    process = make()
    process._owner = -1
    try:
        with pytest.raises(runtime.ModelProcessUnavailable):
            process.call(b'x', deadline=deadline())
        assert process.pid is None
    finally:
        process._owner = os.getpid()
        process.close()

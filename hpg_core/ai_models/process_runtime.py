"""Windows-Lane mit privater Bytes-Pipe und begrenztem Fehler-Cleanup.

Ein Owner gehört genau einem Prozess. Handler werden erst nach Job-Zuweisung
im Kind importiert. ONNX und Demucs benötigen getrennte Owner/Lanes.
Der Sentinel-Wächter startet erst in unserem Bootstrap; CPython-Prepare davor
ist ausdrücklich nicht durch diesen Wächter abgedeckt. Kein Produktdispatch.
"""
import ctypes
from ctypes import wintypes
import importlib
import math
import multiprocessing as mp
from multiprocessing.connection import wait
import os
import threading
import time


class ModelProcessUnavailable(RuntimeError):
    """Prozess oder Windows-Job konnte nicht gestartet werden."""


class ModelProcessTimeout(ModelProcessUnavailable):
    """Absolute Deadline überschritten."""


class ModelProcessCancelled(ModelProcessUnavailable):
    """Auftrag abgebrochen."""


class ModelProcessCrashed(ModelProcessUnavailable):
    """Kind unerwartet beendet."""


class ModelProcessProtocolError(ModelProcessUnavailable):
    """Bytes-Vertrag verletzt."""


class ModelProcessClosed(ModelProcessUnavailable):
    """Owner bereits geschlossen."""


class ModelProcessCleanupError(ModelProcessUnavailable):
    """Ende nicht bestätigt; Owner dauerhaft gesperrt."""


class _BasicLimits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                ('flags', wintypes.DWORD), ('min_working', ctypes.c_size_t),
                ('max_working', ctypes.c_size_t), ('active', wintypes.DWORD),
                ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                ('scheduling', wintypes.DWORD)]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [('basic', _BasicLimits), ('io', ctypes.c_uint64 * 6),
                ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]


def _kernel():
    dll = ctypes.WinDLL('kernel32', use_last_error=True)
    signatures = {
        'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        'SetInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
        'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
        'CancelIoEx': ([wintypes.HANDLE, ctypes.c_void_p], wintypes.BOOL),
    }
    for name, (args, result) in signatures.items():
        function = getattr(dll, name)
        function.argtypes, function.restype = args, result
    return dll


def _create_job(memory_limit_bytes=None):
    kernel = _kernel()
    # NULL security attributes: Handle ist nicht vererbbar; kein benannter Job.
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    info = _ExtendedLimits()
    info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, Win32-Vertrag.
    if memory_limit_bytes is not None:
        # Zugesicherten Speicher des gesamten Jobs begrenzen, nicht Working Set.
        info.basic.flags |= 0x200  # JOB_OBJECT_LIMIT_JOB_MEMORY.
        info.job_memory = memory_limit_bytes
    if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
        error = ctypes.WinError(ctypes.get_last_error())
        kernel.CloseHandle(handle)
        raise error
    return handle


def _assign_job(job, pid):
    kernel = _kernel()
    handle = kernel.OpenProcess(0x100 | 0x1, False, pid)  # SET_QUOTA | TERMINATE
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not kernel.AssignProcessToJobObject(job, handle):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)


def _watch_parent():
    parent = mp.parent_process()
    if parent is not None:
        wait([parent.sentinel])
        os._exit(72)


def _bootstrap(connection, module, name, maximum):
    threading.Thread(target=_watch_parent, daemon=True).start()
    handshake = threading.Event()
    def handshake_watchdog():
        # Fünf Sekunden begrenzen ausschließlich das Warten auf Owner-GO.
        if not handshake.wait(5):
            os._exit(73)
    threading.Thread(target=handshake_watchdog, daemon=True).start()
    try:
        if connection.recv_bytes(2) != b'GO':
            return
        handshake.set()
        handler = getattr(importlib.import_module(module), name)
        connection.send_bytes(b'READY')
        while True:
            payload = connection.recv_bytes(maximum)
            result = handler(payload)
            if not isinstance(result, bytes) or len(result) > maximum:
                connection.send_bytes(b'P')
                return
            connection.send_bytes(b'R' + result)
    except (EOFError, OSError):
        return
    finally:
        connection.close()


class OwnedModelProcess:
    """Lazy Spawn, genau eine aktive Anfrage, keine automatischen Retries.

    call wartet einschließlich Lock/Start/Übertragung bis zur Deadline.
    Fehler-Cleanup darf anschließend höchstens cleanup_timeout dauern.
    Bestätigtes Kind-/Threadende erlaubt nach Timeout/Crash eine neue Generation.
    Unbestätigtes Ende vergiftet den Owner dauerhaft. close unterbricht aktive
    Arbeit, wartet aber nie auf deren Call-Lock.
    """

    def __init__(self, handler_module, handler_name, max_payload_bytes=64 * 1024 * 1024,
                 cleanup_timeout=3.0, memory_limit_bytes=None):
        if os.name != 'nt':
            raise ModelProcessUnavailable('Windows required')
        if not isinstance(handler_module, str) or not handler_module or not isinstance(handler_name, str) or not handler_name:
            raise ValueError('Handler module/name required')
        if type(max_payload_bytes) is not int or not 0 < max_payload_bytes <= 64 * 1024 * 1024:
            raise ValueError('Payload bound must be 1..64 MiB')
        if isinstance(cleanup_timeout, bool) or not isinstance(cleanup_timeout, (float, int)) or not math.isfinite(cleanup_timeout) or not 0 < cleanup_timeout <= 3:
            raise ValueError('Cleanup bound must be >0 and <=3 seconds')
        if memory_limit_bytes is not None and (
                type(memory_limit_bytes) is not int
                or not 0 < memory_limit_bytes <= (1 << (ctypes.sizeof(ctypes.c_size_t) * 8)) - 1):
            raise ValueError('Memory limit must be a positive SIZE_T byte count')
        self._module, self._name = handler_module, handler_name
        self._maximum, self._cleanup_timeout = max_payload_bytes, float(cleanup_timeout)
        self._memory_limit_bytes = memory_limit_bytes
        self._owner = os.getpid()
        self._state = 'NEW'
        self._state_lock = threading.Lock()
        self._call_lock = threading.Lock()
        self._cleanup_lock = threading.Lock()
        self._stop = threading.Event()
        self._process = self._pipe = self._job = self._thread = None
        self._poisoned = False

    @property
    def state(self):
        with self._state_lock:
            return self._state

    @property
    def pid(self):
        with self._state_lock:
            return self._process.pid if self._process else None

    def _check(self, deadline, cancel):
        if os.getpid() != self._owner:
            raise ModelProcessUnavailable('Owner belongs to another process')
        with self._state_lock:
            if self._poisoned:
                raise ModelProcessCleanupError('Unconfirmed cleanup; owner poisoned')
            if self._state == 'CLOSED':
                raise ModelProcessClosed('Owner closed')
        if cancel is not None and cancel.is_set():
            raise ModelProcessCancelled('Request cancelled')
        if time.monotonic() >= deadline:
            raise ModelProcessTimeout('Request deadline exceeded')

    def _exchange(self, payload):
        if self._process is None:
            context = mp.get_context('spawn')
            connection, child_connection = context.Pipe(duplex=True)
            process = context.Process(target=_bootstrap,
                                      args=(child_connection, self._module, self._name, self._maximum),
                                      daemon=True)
            try:
                with self._state_lock:
                    if self._stop.is_set():
                        raise ModelProcessClosed('Start stopped')
                    self._pipe, self._process = connection, process
                process.start()
                # Nach langsamem Spawn keinen verwaisten Prozess weiterlaufen lassen.
                if self._stop.is_set():
                    process.terminate()
                    process.join(self._cleanup_timeout)
                    raise ModelProcessClosed('Start stopped')
                job = (_create_job() if self._memory_limit_bytes is None
                       else _create_job(self._memory_limit_bytes))
                try:
                    # Noch privates Handle: Cleanup kann es während Assign
                    # nicht schließen; die WinAPI hält keinen State-Lock.
                    _assign_job(job, process.pid)
                    with self._state_lock:
                        if self._stop.is_set():
                            raise ModelProcessClosed('Start stopped')
                        self._job = job
                        job = None
                finally:
                    if job:
                        _kernel().CloseHandle(job)
                connection.send_bytes(b'GO')
                if connection.recv_bytes(5) != b'READY':
                    raise ModelProcessProtocolError('Invalid startup handshake')
            finally:
                child_connection.close()
        connection = self._pipe
        connection.send_bytes(payload)
        response = connection.recv_bytes(self._maximum + 1)
        if response[:1] != b'R':
            raise ModelProcessProtocolError('Invalid response or oversized result')
        return response[1:]

    def _cleanup(self):
        end = time.monotonic() + self._cleanup_timeout
        if not self._cleanup_lock.acquire(timeout=self._cleanup_timeout):
            with self._state_lock:
                self._poisoned = True
                if self._state != 'CLOSED':
                    self._state = 'BROKEN'
            raise ModelProcessCleanupError('Concurrent cleanup did not finish')
        try:
            self._stop.set()
            with self._state_lock:
                job, self._job = self._job, None
                process, pipe, thread = self._process, self._pipe, self._thread
            if job:
                _kernel().CloseHandle(job)
            if process is not None and process.pid is not None:
                try:
                    if process.is_alive():
                        process.terminate()
                except (OSError, ValueError):
                    pass
            if pipe is not None:
                try:
                    _kernel().CancelIoEx(pipe.fileno(), None)
                except (OSError, ValueError):
                    pass
                pipe.close()
            if thread is not None:
                thread.join(max(0, end - time.monotonic()))
            # Ein spät zurückkehrender Spawn kann jetzt erst eine PID besitzen.
            if process is not None and process.pid is not None:
                try:
                    if process.is_alive():
                        process.kill()
                    process.join(max(0, end - time.monotonic()))
                except (OSError, ValueError):
                    pass
            alive = thread is not None and thread.is_alive()
            alive |= process is not None and process.pid is not None and process.is_alive()
            with self._state_lock:
                if alive:
                    self._poisoned = True
                    if self._state != 'CLOSED':
                        self._state = 'BROKEN'
                else:
                    if process is not None and process.pid is not None:
                        process.close()
                    self._process = self._pipe = self._thread = None
                    if self._state != 'CLOSED' and not self._poisoned:
                        self._state = 'NEW'
            if alive:
                raise ModelProcessCleanupError('Child or IO thread end unconfirmed')
        finally:
            self._cleanup_lock.release()

    def call(self, payload, *, deadline, cancel_event=None):
        if isinstance(deadline, bool) or not isinstance(deadline, (float, int)) or not math.isfinite(deadline):
            raise ValueError('Finite absolute monotonic deadline required')
        if not isinstance(payload, bytes) or len(payload) > self._maximum:
            raise ModelProcessProtocolError('Bounded bytes payload required')
        if cancel_event is not None and not isinstance(cancel_event, threading.Event):
            raise ValueError('threading.Event required')
        # Wartende Anfragen besitzen die Lane nicht und dürfen sie nicht stoppen.
        while True:
            self._check(deadline, cancel_event)
            if self._call_lock.acquire(timeout=min(.05, max(0, deadline-time.monotonic()))):
                break
        started = False
        try:
            self._check(deadline, cancel_event)
            done = threading.Event()
            outcome = []
            def exchange():
                try:
                    outcome.append((True, self._exchange(payload)))
                except BaseException as error:
                    outcome.append((False, error))
                finally:
                    done.set()
            with self._state_lock:
                if self._state == 'CLOSED':
                    raise ModelProcessClosed('Owner closed')
                self._stop.clear()
                self._state = 'BUSY'
                thread = threading.Thread(target=exchange, daemon=True, name='hpg-model-io')
                self._thread = thread
                thread.start()
                started = True
            while not done.wait(min(.05, max(0, deadline-time.monotonic()))):
                self._check(deadline, cancel_event)
            self._check(deadline, cancel_event)
            thread.join(max(0, deadline-time.monotonic()))
            if thread.is_alive():
                raise ModelProcessTimeout('IO thread did not finish before deadline')
            success, value = outcome[0]
            if not success:
                if isinstance(value, ModelProcessUnavailable):
                    raise value
                if isinstance(value, EOFError) or (isinstance(value, OSError) and getattr(value, 'winerror', None) in (109, 232)):
                    raise ModelProcessCrashed('Child exited during exchange') from value
                if isinstance(value, OSError) and 'bad message length' in str(value):
                    raise ModelProcessProtocolError('Oversized pipe message') from value
                raise ModelProcessUnavailable(f'Process exchange failed: {type(value).__name__}') from value
            with self._state_lock:
                if self._state == 'CLOSED':
                    raise ModelProcessClosed('Owner closed')
                self._state = 'READY'
                self._thread = None
            return value
        except BaseException:
            if started:
                self._cleanup()
            raise
        finally:
            self._call_lock.release()

    def close(self):
        if os.getpid() != self._owner:
            raise ModelProcessUnavailable('Owner belongs to another process')
        with self._state_lock:
            self._state = 'CLOSED'
            self._stop.set()
        self._cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

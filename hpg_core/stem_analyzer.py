"""Demucs3-C-ABI im isolierten Modellprozess; nur lokale RMS-Kurven zurückgeben.

Beleg: Demucs3.dll a94ddfd5..., RVAs 8c40/7150/a760 und b500/b5d0/b680.
SeparatedBass liefert other, vocals, drums, bass, jeweils links/rechts.
Hör-Audio bleibt ausschließlich flüchtig. RMS ist keine Vocal-Wahrscheinlichkeit.
"""
from __future__ import annotations

import ctypes as ct
from contextlib import contextmanager, nullcontext
import hashlib
import logging
import os
from pathlib import Path

import numpy as np

from .ai_models.feature_audio import EnergyBins, windows

DLL_HASH = 'a94ddfd5e45507f0be5cadb9e46b929433cbe2a26191ee0afb762053148bdd4b'
MODEL_HASH = '435c987855f7ea74ff5f20090541748cbbce5a2e8e501d07b10f4e703453215a'
RATE, WIDTH, HOP = 44100, 485100, 483052
NAMES = ('other', 'vocals', 'drums', 'bass')
ORT_DLL_HASH = 'e7a702e13bd3e487705204d518c96f1f116aa25b0ac584741838e20bc1ff6e9f'
_DML_IMPORT_RVA = 0x442F0
_logger = logging.getLogger(__name__)


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@contextmanager
def _route_demucs_directml(library, dll_path, device_id):
    """Lenkt nur den gepinnten Demucs-ORT-Import im eigenen Kindprozess um."""
    import pefile

    if type(device_id) is not int or device_id < 0:
        raise ValueError('Invalid DirectML adapter index')
    if device_id == 0:
        yield []
        return
    ort_path = Path(dll_path).parent / 'onnxruntime.dll'
    if _digest(ort_path) != ORT_DLL_HASH:
        raise ValueError('Unsupported Demucs ONNX Runtime library')
    pe = pefile.PE(str(dll_path), fast_load=True)
    try:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
        imports = [symbol for entry in pe.DIRECTORY_ENTRY_IMPORT
                   if entry.dll.lower() == b'onnxruntime.dll'
                   for symbol in entry.imports if symbol.ordinal == 4]
        if (len(imports) != 1 or imports[0].name is not None
                or imports[0].address - pe.OPTIONAL_HEADER.ImageBase != _DML_IMPORT_RVA):
            raise ValueError('Unexpected Demucs DirectML import')
        slot = library._handle + _DML_IMPORT_RVA
    finally:
        pe.close()

    runtime = ct.WinDLL(str(ort_path), winmode=0x1100)
    kernel = ct.WinDLL('kernel32', use_last_error=True)
    kernel.GetProcAddress.argtypes = [ct.c_void_p, ct.c_void_p]
    kernel.GetProcAddress.restype = ct.c_void_p
    expected = kernel.GetProcAddress(runtime._handle, ct.c_void_p(4))
    original = ct.c_void_p.from_address(slot).value
    if not expected or original != expected:
        raise RuntimeError('Demucs DirectML import does not match pinned runtime')

    callback_type = ct.WINFUNCTYPE(ct.c_void_p, ct.c_void_p, ct.c_int)
    native_append = callback_type(original)
    calls = []

    @callback_type
    def selected_append(options, requested):
        calls.append(requested)
        return native_append(options, device_id)

    kernel.VirtualProtect.argtypes = [ct.c_void_p, ct.c_size_t, ct.c_ulong,
                                      ct.POINTER(ct.c_ulong)]
    kernel.VirtualProtect.restype = ct.c_int

    def write_pointer(value):
        old_protection = ct.c_ulong()
        if not kernel.VirtualProtect(slot, ct.sizeof(ct.c_void_p), 0x04,
                                     ct.byref(old_protection)):
            raise OSError(ct.get_last_error(), 'Demucs import protection failed')
        try:
            ct.c_void_p.from_address(slot).value = value
        finally:
            restored = ct.c_ulong()
            if not kernel.VirtualProtect(slot, ct.sizeof(ct.c_void_p),
                                         old_protection.value, ct.byref(restored)):
                raise OSError(ct.get_last_error(), 'Demucs import protection restore failed')
        if ct.c_void_p.from_address(slot).value != value:
            raise RuntimeError('Demucs import readback failed')

    write_pointer(ct.cast(selected_append, ct.c_void_p).value)
    try:
        yield calls
    finally:
        write_pointer(original)


def analyze(source, *, dll_path, model_dir, prefer_directml=True):
    """Ein Track pro Child; keine DLL im GUI-/Analysehauptprozess laden."""
    import multiprocessing
    if multiprocessing.current_process().name == 'MainProcess':
        raise RuntimeError('Stem inference requires an owned child process')
    dll_path, model_dir = Path(dll_path), Path(model_dir)
    if _digest(dll_path) != DLL_HASH or _digest(model_dir/'hdemucs.onnx') != MODEL_HASH:
        raise ValueError('Unsupported Demucs artifacts')
    if prefer_directml:
        from .ai_models.directml_device import choose_device_id
        device_id = choose_device_id()
        if device_id is None:
            prefer_directml = False
    else:
        device_id = None
    # Win32-C-ABI verwendet eine Bytepfadangabe. Unklare Kodierung nicht raten.
    encoded = str(model_dir).encode('ascii', errors='strict')
    handle = ct.c_void_p()
    completed = False
    with os.add_dll_directory(str(dll_path.parent)):
        library = ct.CDLL(str(dll_path))
        initialize = library.demucs3Initialize
        initialize.argtypes = [ct.c_char_p, ct.c_int32, ct.c_bool, ct.c_bool, ct.c_int32, ct.c_bool]
        initialize.restype = None
        initialized = library.demucs3IsInitialized
        initialized.argtypes, initialized.restype = [], ct.c_bool
        pre = library.demucs3PreOperation
        pre.argtypes, pre.restype = [ct.POINTER(ct.c_void_p), ct.c_int32], ct.c_bool
        post = library.demucs3PostOperation
        post.argtypes, post.restype = [ct.c_void_p], None
        finalize = library.demucs3Finalize
        finalize.argtypes, finalize.restype = [], None
        pointer = ct.POINTER(ct.c_float)
        operation = library.demucs3OperationAtIndexSeparatedBass
        operation.argtypes = [ct.c_void_p, ct.c_int32] + [pointer]*10
        operation.restype = ct.c_bool
        try:
            route = (_route_demucs_directml(library, dll_path, device_id)
                     if prefer_directml else nullcontext([]))
            with route as dml_calls:
                initialize(encoded, 1, not prefer_directml, False, 1, False)
            if prefer_directml and device_id != 0 and dml_calls != [0]:
                raise RuntimeError('Demucs did not request the pinned DirectML adapter import')
            if prefer_directml:
                _logger.info('Demucs DirectML: DXGI-Adapter %s angefordert', device_id)
            if not initialized():
                raise RuntimeError('Demucs initialization failed')
            total = round(len(source)*RATE/source.samplerate)
            if not 0 < total < 2**31 or not pre(ct.byref(handle), total) or not handle.value:
                raise RuntimeError('Demucs preparation failed')
            bins = EnergyBins(total, RATE, NAMES)
            for start, count, block in windows(source, RATE, WIDTH, HOP, left_padding=1024):
                output = np.zeros((8, count), np.float32)
                buffers = [row.ctypes.data_as(pointer) for row in block]
                buffers += [row.ctypes.data_as(pointer) for row in output]
                if not operation(handle, start//HOP, *buffers):
                    raise RuntimeError('Demucs block failed')
                bins.add(start, output.reshape(4, 2, count))
            result = dict(curves=bins.result(), hop_s=1., sample_rate=RATE,
                          samples=total, model_sha256=MODEL_HASH, dll_sha256=DLL_HASH,
                          provider_request='DirectML' if prefer_directml else 'CPU',
                          provider_verified=False, scale='stereo_rms_normalized_pcm',
                          calibrated=False)
            completed = True
            return result
        finally:
            # Nach einem nativen Fehler keinen eventuell inkonsistenten Handle
            # erneut aufrufen. Der Owner beendet den gesamten Einmalprozess.
            if completed:
                post(handle)
                handle.value = None
                finalize()

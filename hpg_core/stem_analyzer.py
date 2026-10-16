"""Demucs3-C-ABI im isolierten Modellprozess; nur lokale RMS-Kurven zurückgeben.

Beleg: Demucs3.dll a94ddfd5..., RVAs 8c40/7150/a760 und b500/b5d0/b680.
SeparatedBass liefert other, vocals, drums, bass, jeweils links/rechts.
Hör-Audio bleibt ausschließlich flüchtig. RMS ist keine Vocal-Wahrscheinlichkeit.
"""
from __future__ import annotations

import ctypes as ct
import hashlib
import os
from pathlib import Path

import numpy as np

from .ai_models.feature_audio import EnergyBins, windows

DLL_HASH = 'a94ddfd5e45507f0be5cadb9e46b929433cbe2a26191ee0afb762053148bdd4b'
MODEL_HASH = '435c987855f7ea74ff5f20090541748cbbce5a2e8e501d07b10f4e703453215a'
RATE, WIDTH, HOP = 44100, 485100, 483052
NAMES = ('other', 'vocals', 'drums', 'bass')


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def analyze(source, *, dll_path, model_dir, prefer_directml=True):
    """Ein Track pro Child; keine DLL im GUI-/Analysehauptprozess laden."""
    import multiprocessing
    if multiprocessing.current_process().name == 'MainProcess':
        raise RuntimeError('Stem inference requires an owned child process')
    dll_path, model_dir = Path(dll_path), Path(model_dir)
    if _digest(dll_path) != DLL_HASH or _digest(model_dir/'hdemucs.onnx') != MODEL_HASH:
        raise ValueError('Unsupported Demucs artifacts')
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
            initialize(encoded, 1, not prefer_directml, False, 1, False)
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

"""Rekordbox-Modellaufruf und Beatdecoder im isolierten Forschungsprozess.

Die native Vorverarbeitung beginnt an den Float-Stereopuffern. Der originale
Dateidecoder und die musikalische Gleichwertigkeit sind noch nicht nachgewiesen.
"""
import ctypes as ct
import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from .native_phrase_worker import NativeImage, NativeContractError, EXE, SHA256, _source_identity
from .native_beat_worker import FloatMatrix
from .native_beat_grid import convert
from .beat_predictor import _hashes

TF_SHA256 = 'b158ff8fdd75723871c5966ec8c1f7c8cda888c9d836365e3b1976966c718424'
_used = False


def _bind_tensorflow(image):
    """Nur die 29 gepinnten TensorFlow-Imports, keine App-Initialisierung."""
    import pefile
    path = EXE.parent / 'tensorflow_cc.dll'
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != TF_SHA256:
            raise NativeContractError('Unsupported native TensorFlow library')
    library = ct.WinDLL(str(path), winmode=0x1100)
    pe = pefile.PE(str(EXE), fast_load=True)
    try:
        pe.parse_data_directories(directories=[1])
        imports = [i for d in pe.DIRECTORY_ENTRY_IMPORT
                   if d.dll.lower() == b'tensorflow_cc.dll' for i in d.imports]
        if len(imports) != 29:
            raise NativeContractError('Unexpected TensorFlow imports')
        for symbol in imports:
            if not symbol.name:
                raise NativeContractError('Unexpected TensorFlow ordinal')
            address = image.kernel.GetProcAddress(library._handle, symbol.name)
            if not address:
                raise NativeContractError('Missing native TensorFlow export')
            slot = image.base + symbol.address - pe.OPTIONAL_HEADER.ImageBase
            image._protect(slot, 8, 0x04)
            ct.c_void_p.from_address(slot).value = address
            image._protect(slot, 8, 0x02)
    finally:
        pe.close()
    return library


def _handle(payload):
    global _used
    if _used:
        raise NativeContractError('Single-use native pipeline required')
    _used = True
    request = json.loads(payload)
    if type(request) is not dict or set(request) != {'path', 'source_identity', 'frames', 'model_id'}:
        raise NativeContractError('Invalid pipeline request')
    path, frames, model_id = Path(request['path']), request['frames'], request['model_id']
    if (not path.is_absolute() or _source_identity(path) != request['source_identity']
            or type(frames) is not int or not 44100 <= frames <= 1200 * 44100
            or model_id not in ('model7', 'model8')):
        raise NativeContractError('Invalid pipeline source or window')
    directory = EXE.parent / 'models' / 'detect_beat' / model_id
    hashes = _hashes(directory, model_id)
    with sf.SoundFile(str(path), mode='r') as source:
        if source.samplerate != 44100 or source.channels != 2 or source.subtype != 'PCM_16' or len(source) < frames:
            raise NativeContractError('Only stereo PCM16/44100 input reconstructed')
        samples = source.read(frames, dtype='float32', always_2d=True)
    left, right = (np.ascontiguousarray(samples[:, channel]) for channel in (0, 1))
    image = NativeImage()
    library = _bind_tensorflow(image)
    if image.function(0x2998258, ct.c_int32)() != 0:
        raise NativeContractError('Native standard-stream initialization failed')
    model_path = ct.c_void_p()
    image.function(0x2a6e420, ct.c_void_p, ct.c_void_p, ct.c_char_p)(
        ct.byref(model_path), str(directory).encode('utf8'))
    target = FloatMatrix()
    # RVA1293f70: beide Varianten konsumieren ihre JUCE-Stringkopie.
    # Für lange Tracks übernimmt RVA12a8ef0 die originale 60s-Fensteraufteilung
    # samt Restfenstern und Verknüpfung. Keine HPG-eigene Grenzkorrektur.
    if frames > 60 * 44100:
        image.function(0x12a8ef0, None, ct.POINTER(FloatMatrix), ct.c_void_p,
            ct.c_void_p, ct.c_void_p, ct.c_int32, ct.c_uint64)(ct.byref(target),
                ct.byref(model_path), left.ctypes.data, right.ctypes.data, 44100, frames)
    else:
        image.function(0x12ab830, None, ct.POINTER(FloatMatrix), ct.c_void_p,
            ct.c_void_p, ct.c_void_p, ct.c_uint64)(ct.byref(target), ct.byref(model_path),
                left.ctypes.data, right.ctypes.data, frames)
    try:
        if (target.columns != 2 or not 4 <= target.rows <= 6000
                or target.size != target.rows * 2 or not target.data):
            raise NativeContractError('Invalid native pipeline matrix')
        values = np.ctypeslib.as_array(ct.cast(target.data, ct.POINTER(ct.c_float)),
                                      shape=(target.size,)).reshape(-1, 2)
        rows = values.tolist()
        if (not np.isfinite(values).all() or np.any(values[:, 0] < 0)
                or np.any(values[:, 0] >= frames / 44100)
                or np.any(np.diff(values[:, 0]) <= 0)
                or not np.isin(values[:, 1], [1, 2, 3, 4]).all()):
            raise NativeContractError('Invalid native pipeline beats')
    finally:
        image.function(0x12add90, None, ct.POINTER(FloatMatrix))(ct.byref(target))
    # Native Fenstergrenzen können nach Sample-Rundung doppelte Positionen
    # enthalten. RVA128ecd0 reicht diese unverändert an die Endkorrektur weiter.
    grid, bpm = convert(image, rows, (frames + 440) // 441,
                        source_samples=frames, refinement_input=True)
    if _source_identity(path) != request['source_identity']:
        raise NativeContractError('Source changed during native pipeline')
    return json.dumps(dict(contract='rb-7.2.19-native-beat-pipeline-research-v1',
        executable_sha256=SHA256, tensorflow_sha256=TF_SHA256, model_id=model_id,
        model_hashes=hashes, verified=False, beats=rows, grid=grid, bpm=bpm,
        input_convention='soundfile-normalized-stereo-float32', frames=frames,
        chunked=frames > 60 * 44100),
        allow_nan=False).encode('utf8')


def handle(payload):
    try:
        return _handle(payload)
    except Exception as error:
        # Python-Vertragsfehler nicht als nativen Prozessabsturz verschleiern.
        return json.dumps(dict(status='unavailable', reason=f'{type(error).__name__}: {error}')).encode()

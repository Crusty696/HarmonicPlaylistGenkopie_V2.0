"""Gepinnter nativer Beatdecoder, ausschließlich im begrenzten Modellprozess.

Aufrufvertrag: RB 7.2.19, RVA 0x1297d60; Callsite 0x12ac107..0x12ac16b.
Floatmatrix und Vektorlayout stammen aus 0x1254ef0 und 0x12425c0.
Die Ausgabe bleibt unverifiziert: ein nativer Decoder allein beweist weder
korrekte Modellvorverarbeitung noch musikalische Qualität der Gesamtpipeline.
"""
from __future__ import annotations

import ctypes as ct
import json
import math
import threading

import numpy as np

from .native_phrase_worker import NativeImage, NativeContractError, SHA256


CONTRACT_VERSION = 'rb-7.2.19-native-beat-samples-v2'
MAX_FRAMES = 6000
_image = None
_lock = threading.Lock()


class FloatMatrix(ct.Structure):
    """Geliehene Eingabe: keine native Freigabe des Python-Puffers."""
    _fields_ = [('reserved', ct.c_uint32), ('rows', ct.c_uint32),
                ('columns', ct.c_uint32), ('size', ct.c_uint32),
                ('reserved2', ct.c_uint32), ('data', ct.c_void_p),
                ('owns_data', ct.c_ubyte)]


class IntVector(ct.Structure):
    _fields_ = [('begin', ct.c_void_p), ('end', ct.c_void_p),
                ('capacity', ct.c_void_p)]


def _decode(activations):
    """Ruft den nativen Decoder mit dem belegten festen Parametersatz auf."""
    global _image
    values = np.asarray(activations)
    if (values.ndim != 2 or values.shape[1] != 2
            or not 1 <= len(values) <= MAX_FRAMES or values.dtype.kind != 'f'
            or not np.isfinite(values).all() or np.any(values < 0)
            or np.any(values > 1) or np.any(values.sum(axis=1) > 1 + 1e-6)):
        raise NativeContractError('Invalid beat activations')
    values = np.ascontiguousarray(values, dtype=np.float32)
    # Derselbe 40-Byte-Matrixtyp dient nativer Eingabe und Ausgabe.
    if (ct.sizeof(FloatMatrix) != 40 or FloatMatrix.data.offset != 24
            or FloatMatrix.owns_data.offset != 32 or ct.sizeof(IntVector) != 24):
        raise NativeContractError('Unsupported native matrix ABI')
    source = FloatMatrix(0, len(values), 2, values.size, 0, values.ctypes.data, 0)
    target = FloatMatrix()
    meter = (ct.c_int32 * 1)(4)
    begin = ct.addressof(meter)
    meters = IntVector(begin, begin + 4, begin + 4)
    if _image is None:
        _image = NativeImage()
    image = _image
    function = image.function(0x1297d60, ct.c_void_p,
        ct.POINTER(FloatMatrix), ct.POINTER(FloatMatrix), ct.POINTER(IntVector),
        ct.c_double, ct.c_double, ct.c_int32, ct.c_int32, ct.c_int32,
        ct.c_float, ct.c_ubyte, ct.c_double)
    # Alle Decoderobjekte entstehen pro Aufruf. Nur das gepinnte Abbild bleibt
    # resident; der native Destruktor gibt die Ergebnismatrix wieder frei.
    returned = function(ct.byref(target), ct.byref(source), ct.byref(meters),
                        70., 180., 60, 100, 16, .05, 1, 100.)
    try:
        if returned != ct.addressof(target):
            raise NativeContractError('Unexpected native result address')
        if target.size == 0 and target.rows == 0:
            rows = []
        else:
            if (target.columns != 2 or not 1 <= target.rows <= len(values)
                    or target.size != target.rows * 2 or not target.data):
                raise NativeContractError('Invalid native beat matrix')
            output = np.ctypeslib.as_array(
                ct.cast(target.data, ct.POINTER(ct.c_float)), shape=(target.size,))
            rows = output.reshape(-1, 2).tolist()
    finally:
        image.function(0x12add90, None, ct.POINTER(FloatMatrix))(ct.byref(target))
    previous = None
    duration = len(values) / 100.
    for stamp, position in rows:
        if (not math.isfinite(stamp) or not 0 <= stamp < duration
                or position not in (1., 2., 3., 4.)
                or previous is not None and stamp <= previous):
            raise NativeContractError('Invalid native beat values')
        previous = stamp
    from .native_beat_grid import convert
    grid, bpm = convert(image, rows, len(values))
    return dict(status='ok', contract=CONTRACT_VERSION, executable_sha256=SHA256,
                verified=False, frame_rate=100., beats=rows, grid=grid, bpm=bpm)


def decode(activations):
    """Serieller Zugriff im bereits begrenzten Modellprozess."""
    with _lock:
        return _decode(activations)


def handle(payload):
    """Kleiner Bytes-Vertrag: Float32-Aktivierungen, kein Originalaudio."""
    if not payload or len(payload) % 8 or len(payload) > MAX_FRAMES * 8:
        raise NativeContractError('Invalid activation payload')
    activations = np.frombuffer(payload, dtype='<f4').reshape(-1, 2)
    return json.dumps(decode(activations), allow_nan=False).encode('utf8')

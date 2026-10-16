"""Native Umrechnung der Decoderpaare in Rekordbox beatList/BPM.

RVA1295b40 und RVA1296a80; Aufrufstelle1295591..12955bd. Nur im
bereits begrenzten nativen Worker verwenden, keine eigenen Audiozugriffe.
"""
import ctypes as ct
import math

from .native_phrase_worker import NativeContractError


class _Vector(ct.Structure):
    _fields_ = [('begin', ct.c_size_t), ('end', ct.c_size_t), ('capacity', ct.c_size_t)]


class _Pair(ct.Structure):
    _fields_ = [('seconds', ct.c_float), ('position', ct.c_int32)]


class _Json(ct.Structure):
    _fields_ = [('kind', ct.c_ubyte), ('value', ct.c_uint64)]


def _read_json(address, depth=0):
    """Gepinntes ordered_json: Array16, Objektpaare48, MSVC-String32.

    Beleg: RVA11f8490,1257c20,121c760. Grenzen vor jeder Traversierung;
    native Zeiger werden ausschließlich im isolierten Kind dereferenziert.
    """
    if not address or depth > 4:
        raise NativeContractError('Invalid native JSON depth/address')
    value = _Json.from_address(address)
    if value.kind in (5, 6):
        return ct.c_int64(value.value).value if value.kind == 5 else value.value
    if value.kind == 7:
        return ct.c_double.from_address(address + 8).value
    if value.kind not in (1, 2) or not value.value:
        raise NativeContractError('Unexpected native JSON type')
    vector = _Vector.from_address(value.value)
    stride = 48 if value.kind == 1 else 16
    size = vector.end - vector.begin
    if (size < 0 or size % stride or size > 6000 * stride
            or vector.capacity < vector.end or size and not vector.begin):
        raise NativeContractError('Invalid native JSON vector')
    result = {} if value.kind == 1 else []
    for item in range(vector.begin, vector.end, stride):
        if value.kind == 2:
            result.append(_read_json(item, depth + 1))
        else:
            length = ct.c_uint64.from_address(item + 16).value
            capacity = ct.c_uint64.from_address(item + 24).value
            if length > 32 or capacity < length:
                raise NativeContractError('Invalid native JSON key')
            data = item if capacity < 16 else ct.c_void_p.from_address(item).value
            if not data:
                raise NativeContractError('Null native JSON key')
            key = ct.string_at(data, length).decode('ascii')
            if key in result:
                raise NativeContractError('Duplicate native JSON key')
            result[key] = _read_json(item + 32, depth + 1)
    return result


def convert(image, rows, frames, *, source_samples=None, refinement_input=False):
    if len(rows) < 2:
        return [], None
    pairs = (_Pair * len(rows))(*(_Pair(stamp, int(position)) for stamp, position in rows))
    begin = ct.addressof(pairs)
    vector = _Vector(begin, begin + ct.sizeof(pairs), begin + ct.sizeof(pairs))
    output = _Json()
    convert_grid = image.function(0x1295b40, ct.c_void_p, ct.POINTER(_Json),
        ct.POINTER(_Vector), ct.c_int64, ct.c_int32, ct.c_int32)
    tempo = image.function(0x1296a80, ct.c_double, ct.POINTER(_Json), ct.c_ubyte)
    # Native Modellzeitbasis44100; der Decoder arbeitet mit100Hz.
    samples = frames * 441 if source_samples is None else source_samples
    if type(samples) is not int or not 1 <= samples <= 1200 * 44100:
        raise NativeContractError('Invalid source sample count')
    convert_grid(ct.byref(output), ct.byref(vector), samples, 44100, 4)
    try:
        grid = _read_json(ct.addressof(output))
        if type(grid) is not list or not 2 <= len(grid) <= 6000:
            raise NativeContractError('Invalid native beatList')
        previous = -1
        for row in grid:
            if (type(row) is not dict or set(row) != {'index', 'bpm', 'pos', 'msec', 'numBar'}
                    or any(type(v) is not int for v in row.values())
                    or row['pos'] < 0 or row['pos'] >= samples
                    or row['pos'] < previous
                    or (not refinement_input and row['pos'] == previous)
                    or row['msec'] < 0
                    or not 1 <= row['numBar'] <= 4):
                raise NativeContractError(f'Invalid native grid row: {row!r}')
            # Der native Verbraucher128ecd0 übergibt pos/numBar/bpm an11db800.
            # msec ist bei nativen Endergänzungen nicht zuverlässig; niemals
            # daraus die zeitliche Reihenfolge oder HPG-Zeitpunkte ableiten.
            previous = row['pos']
        # Native beatList und Tempoaggregation verwenden BPM*100: Faktor100
        # bei RVA1295b40, Floatkonstante RVA580013c. HPG verwendet BPM.
        bpm = float(tempo(ct.byref(output), 1)) / 100.
        if not math.isfinite(bpm) or not 0 < bpm <= 1000:
            raise NativeContractError('Invalid native grid BPM')
        return grid, bpm
    finally:
        # Natives JSON besitzt seinen Speicher; nicht mit Python freigeben.
        release = image.function(0x11f0540, None, ct.c_void_p, ct.c_ubyte)
        release(ct.addressof(output) + 8, output.kind)

"""Originale Grenz-/Nahtkorrekturen aus RVA1294100 im privaten RAM-Abbild.

Der Originalwrapper bleibt unverändert. Vier belegte Schnittstellen werden im
Einmalprozess überbrückt: Reader-Konstruktion, Kanalabfrage, PCM-Lesen und
Modelldispatch. So bleiben Roh-Modellbeats verfügbar, ohne eine zweite Inferenz
auszuführen.
Installationsdateien und fremde Prozesse werden niemals verändert.
"""
import ctypes as ct
import numpy as np

from .native_phrase_worker import EXE, NativeContractError
from .native_beat_worker import FloatMatrix
from .native_beat_grid import _Json, _read_json

VERSION = 'rb-7.2.19-wrapper1294100-v5'


def absolute_model_rows(rows, start_frame):
    """Fenstergrenze und Modellzeit im selben Sample-Bezug umrechnen."""
    return [[(seconds * 44100 + start_frame) / 44100, bar]
            for seconds, bar in rows]


class _PrivateBridges:
    def __init__(self, image):
        self.image, self.saved, self.callbacks = image, [], []

    def install(self, rva, callback):
        address = self.image.base + rva
        original = ct.string_at(address, 12)
        jump = b'\x48\xb8' + ct.cast(callback, ct.c_void_p).value.to_bytes(8, 'little') + b'\xff\xe0'
        self.saved.append((address, original))
        self.callbacks.append(callback)
        self._write(address, jump)

    def _write(self, address, data):
        self.image._protect(address, len(data), 0x40)
        ct.memmove(address, data, len(data))
        self.image._protect(address, len(data), 0x20)
        if not self.image.kernel.FlushInstructionCache(
                self.image.kernel.GetCurrentProcess(), address, len(data)):
            raise NativeContractError('Private bridge instruction flush failed')

    def restore(self):
        errors = []
        for address, original in reversed(self.saved):
            try:
                self._write(address, original)
            except Exception as error:
                errors.append(error)
        if errors:
            raise NativeContractError('Private bridge restoration failed') from errors[0]


def run(image, reader, selection, window_start):
    """Grenzkorrekturen nativ; Callbackfehler sperren das gesamte Ergebnis."""
    from .native_beat_pipeline_worker import validate_model_rows
    errors, raw_rows = [], []
    read_frames = 0
    channels = getattr(reader, 'channels', None)
    frames = getattr(reader, 'frames', None)
    if type(channels) is not int or channels not in (1, 2):
        raise NativeContractError('Invalid wrapper reader channel count')
    if type(frames) is not int or frames < 1:
        raise NativeContractError('Invalid wrapper reader frame count')
    bridge = _PrivateBridges(image)
    # Der Wrapper besitzt nur seine kleine Readerhülle; Decoder/Resampler sind
    # bis zum Ende des isolierten Prozesses im NativeAudioReader referenziert.
    destructor_type = ct.WINFUNCTYPE(ct.c_void_p, ct.c_void_p, ct.c_uint32)
    destructor = destructor_type(lambda address, flags: address)
    table = (ct.c_void_p * 1)(ct.cast(destructor, ct.c_void_p).value)
    constructor_type = ct.WINFUNCTYPE(ct.c_void_p, ct.c_void_p, ct.c_void_p,
        ct.c_int32, ct.c_int32, ct.c_int32, ct.c_int32, ct.c_void_p)

    @constructor_type
    def construct(address, path, rate, a, b, c, factory):
        if rate != 44100:
            errors.append('Unexpected wrapper reader rate')
            return 0
        ct.memset(address, 0, 0x2d8)
        ct.c_void_p.from_address(address).value = ct.addressof(table)
        ct.c_void_p.from_address(address + 0x220).value = ct.addressof(reader.owner)
        ct.c_int32.from_address(address + 0x228).value = 44100
        ct.c_int32.from_address(address + 0x238).value = frames
        return address

    # RVA1294100 branches on the reader's channel getter: two channels are
    # deinterleaved from the two PCM buffers, while mono follows a separate
    # path. A fallback NativeAudioReader has no Rekordbox-owned decoder object,
    # so the original getter would report zero channels despite valid PCM.
    channel_type = ct.WINFUNCTYPE(ct.c_uint16, ct.c_void_p)

    @channel_type
    def channel_count(address):
        return channels

    read_type = ct.WINFUNCTYPE(ct.c_int32, ct.c_void_p, ct.c_int32,
                              ct.c_void_p, ct.c_void_p, ct.c_int32)
    @read_type
    def read(address, start, left, right, count):
        nonlocal read_frames
        try:
            if start < 0 or not 0 < count <= 512:
                raise NativeContractError('Invalid wrapper read request')
            count = min(count, reader.frames-start)
            if count <= 0:
                return 0
            lvalues, rvalues = reader.read(start, count)
            read_frames += count
            ct.memmove(left, lvalues.ctypes.data, count*4)
            ct.memmove(right, rvalues.ctypes.data, count*4)
            return count
        except Exception as error:
            errors.append(str(error))
            return 0

    dispatch_type = ct.WINFUNCTYPE(ct.c_void_p, ct.c_void_p, ct.c_void_p,
        ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_int32, ct.c_uint64, ct.c_ubyte)
    @dispatch_type
    def dispatch(output, model7, model8, left, right, rate, frames, chunked):
        target = FloatMatrix()
        path = ct.c_void_p()
        try:
            if rate != 44100 or bool(chunked) != selection['chunked']:
                raise NativeContractError('Native wrapper selected unexpected model')
            image.function(0x2a6e660, ct.c_void_p, ct.c_void_p, ct.c_void_p)(
                ct.byref(path), model7 if chunked else model8)
            if chunked:
                returned_matrix = image.function(0x12a8ef0, ct.c_void_p,
                    ct.POINTER(FloatMatrix), ct.c_void_p,
                    ct.c_void_p, ct.c_void_p, ct.c_int32, ct.c_uint64)(
                        ct.byref(target), ct.byref(path), left, right, rate, frames)
            else:
                returned_matrix = image.function(0x12ab830, ct.c_void_p,
                    ct.POINTER(FloatMatrix), ct.c_void_p,
                    ct.c_void_p, ct.c_void_p, ct.c_uint64)(
                        ct.byref(target), ct.byref(path), left, right, frames)
            # Der Originalwrapper uebergibt den Rueckgabewert direkt an
            # RVA12b2c00, das ihn als FloatMatrix liest. Der native Adapter
            # muss bestaetigen, dass er dieselbe Out-Matrix zurueckliefert.
            if returned_matrix != ct.addressof(target):
                raise NativeContractError('Native wrapper returned an unexpected matrix')
            if (target.columns != 2 or not 4 <= target.rows <= 6000
                    or target.size != target.rows*2 or not target.data):
                # Nur im Fehlerfall: Stille/Lesefehler vom Modellausfall trennen,
                # ohne Audiodaten zu speichern oder einen Modelllauf zu wiederholen.
                peaks = []
                for channel in (left, right):
                    samples = np.ctypeslib.as_array(
                        ct.cast(channel, ct.POINTER(ct.c_float)), shape=(frames,))
                    peaks.append(float(np.max(np.abs(samples))))
                raise NativeContractError(
                    f'Invalid native wrapper matrix: rows={target.rows}, '
                    f'columns={target.columns}, size={target.size}, '
                    f'data_present={bool(target.data)}, frames={frames}, '
                    f'chunked={bool(chunked)}, input_peaks={peaks}, '
                    f'read_frames={read_frames}')
            values = np.ctypeslib.as_array(ct.cast(target.data, ct.POINTER(ct.c_float)),
                                           shape=(target.size,)).reshape(-1, 2)
            raw_rows.extend(validate_model_rows(values, frames, chunked=bool(chunked)))
            image.function(0x12b2c00, ct.c_void_p, ct.c_void_p,
                           ct.POINTER(FloatMatrix))(output, ct.byref(target))
        except Exception as error:
            errors.append(str(error))
            ct.memset(output, 0, 24)
        finally:
            image.function(0x12add90, None, ct.POINTER(FloatMatrix))(ct.byref(target))
            release_models()
        return output

    # MSVC x64 std::string belegt 32 Byte. Ein c_void_p-Ausgabefeld
    # überschreibt benachbarten nativen Speicher, wenn der Konstruktor dort
    # direkt das Stringobjekt initialisiert.
    models = [ct.create_string_buffer(32), ct.create_string_buffer(32)]
    model_ready = [False, False]
    model_released = [False, False]
    release_native = image.function(0x2a6e690, None, ct.c_void_p)

    def release_models():
        for index, model in enumerate(models):
            if model_ready[index] and not model_released[index]:
                release_native(ct.addressof(model))
                model_released[index] = True

    path = ct.create_string_buffer(32)
    encoded = str(reader.path).encode('utf8')
    image.function(0xefbcc0, ct.c_void_p, ct.c_void_p, ct.c_char_p, ct.c_size_t)(
        path, encoded, len(encoded))
    output = _Json()
    try:
        construct_model = image.function(0x2a6e420, ct.c_void_p,
                                         ct.c_void_p, ct.c_char_p)
        for index, (model_id, target) in enumerate(zip(('model7', 'model8'), models)):
            construct_model(ct.byref(target),
                str(EXE.parent/'models'/'detect_beat'/model_id).encode('utf8'))
            model_ready[index] = True

        bridge.install(0x1104be0, construct)
        bridge.install(0x11042d0, channel_count)
        bridge.install(0x2ccfd60, read)
        bridge.install(0x1293f70, dispatch)
        # RVA1294356 lädt den fünften Parameter als INT32-Sampleindex;
        # RVA129444b reicht ihn in EDX an den Reader weiter. Der Decompiler
        # typisiert ihn fälschlich als float. Float-Bits erzeugen einen Seek
        # hinter das Dateiende und dadurch ausschließlich stille Modellinputs.
        image.function(0x1294100, None, ct.c_void_p, ct.c_void_p, ct.c_void_p,
            ct.c_int32, ct.c_int32, ct.c_ubyte, ct.c_void_p)(ct.byref(models[0]),
                ct.byref(models[1]), path, 44100, int(window_start),
                selection['chunked'], ct.byref(output))
        if errors:
            raise NativeContractError('; '.join(errors))
        result = _read_json(ct.addressof(output))
        if (type(result) is not dict or type(result.get('beatList')) is not list
                or not 4 <= len(result['beatList']) <= 6000
                or type(result.get('bpm')) not in (int, float)
                or not 0 < result['bpm'] <= 100000):
            raise NativeContractError('Invalid boundary wrapper output')
        start = 0 if selection['chunked'] else min(max(0, window_start),
                         max(0, reader.frames-1-60*44100))
        coverage_end = (reader.frames-1 if selection['chunked']
                        else min(reader.frames, start+60*44100))
        coverage = dict(start_s=start/44100, end_s=coverage_end/44100)
        return result['beatList'], result['bpm'], absolute_model_rows(raw_rows, start), coverage
    finally:
        try:
            release_models()
        finally:
            try:
                bridge.restore()
            finally:
                try:
                    image.function(0x11f0540, None, ct.c_void_p, ct.c_ubyte)(
                        ct.addressof(output)+8, output.kind)
                finally:
                    image.function(0xefdf30, None, ct.c_void_p)(path)

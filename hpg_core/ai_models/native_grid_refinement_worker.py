"""Native Endgrid-Rekonstruktion; ausschließlich begrenzter Einmalprozess.

Rekordbox 7.2.19: Wrapper11db2e0/350/540/800/860/890/8c0. Audio geht über
denselben quellengebundenen Reader wie die native Analyse. Das Ergebnis ist
technisch rekonstruiert, aber nicht als musikalisch verifiziert freigegeben.
"""
import ctypes as ct
import json
import tempfile
from pathlib import Path

import numpy as np

from .native_phrase_worker import NativeImage, NativeContractError, SHA256, _source_identity
from .native_audio_reader import (
    NativeAudioReader, _source_channel_count, bind_reader_imports,
)
from .native_beat_selection import MAX_NATIVE_BEAT_WINDOW_SECONDS

_used = False


class Triple(ct.Structure):
    _fields_ = [('pos', ct.c_int32), ('numBar', ct.c_int32), ('bpm', ct.c_int32)]


def _handle(payload):
    global _used
    if _used:
        raise NativeContractError('Single-use final-grid child required')
    _used = True
    request = json.loads(payload)
    if type(request) is not dict or set(request) != {'path', 'source_identity', 'frames', 'grid', 'bpm_hundredths'}:
        raise NativeContractError('Invalid refinement fields')
    path = Path(request['path'])
    frames, grid, bpm = request['frames'], request['grid'], request['bpm_hundredths']
    if (not path.is_absolute() or _source_identity(path) != request['source_identity']
            or type(frames) is not int
            or not 44100 <= frames <= MAX_NATIVE_BEAT_WINDOW_SECONDS * 44100
            or type(bpm) is not int or not 5500 <= bpm <= 21500
            or type(grid) is not list or not 4 <= len(grid) <= 6000):
        raise NativeContractError('Invalid refinement input')
    previous = -1
    for row in grid:
        if (type(row) is not dict or not {'pos', 'numBar', 'bpm'} <= set(row)
                or any(type(row[k]) is not int for k in ('pos', 'numBar', 'bpm'))
                or not 0 <= row['pos'] < frames or row['pos'] < previous
                or not 1 <= row['numBar'] <= 4
                # Native Rohintervalle an Fenstergrenzen können extrem kurze
                # Abstände enthalten. Der int32-Vertrag gilt vor der Korrektur;
                # diese Werte sind keine freigegebenen musikalischen Tempi.
                # Doppelpositionen erzeugen nativ INT_MIN als Tempo-Sentinel.
                # RVA128ecd0 übernimmt das signed-int32-Feld unverändert.
                or not -(2**31) <= row['bpm'] < 2**31):
            raise NativeContractError('Invalid refinement beat')
        previous = row['pos']
    image = NativeImage()
    bind_reader_imports(image)
    channels = _source_channel_count(path)
    try:
        source = NativeAudioReader(image, path, use_rekordbox=channels in (1, 2))
    except NativeContractError:
        source = NativeAudioReader(None, path, use_rekordbox=False)
    if source.frames < frames or source.channels not in (1, 2):
        raise NativeContractError('Native reader does not cover refinement input')
    # RVA262bf53/1853f30 erzeugt Diagnose-CSV unter APPDATA. Ausschließlich
    # diesen Pfad isolieren; weder echte Rekordbox-Daten noch Musik beschreiben.
    diagnostic_dir = tempfile.mkdtemp(prefix='hpg-native-final-grid-')
    folder_type = ct.WINFUNCTYPE(ct.c_int32, ct.c_void_p, ct.c_void_p,
                                ct.c_int32, ct.c_int32)
    @folder_type
    def research_folder(window, output, folder, create):
        if folder != 0x1a or not output or len(diagnostic_dir) >= 260:
            return 0
        buffer = ct.create_unicode_buffer(diagnostic_dir)
        ct.memmove(output, buffer, ct.sizeof(buffer))
        return 1
    # Gepinnter IAT-Eintrag SHGetSpecialFolderPathW; Callback bleibt bis
    # zum Ende aller nativen Aufrufe referenziert. Keine globale API-Änderung.
    slot = image.base + 0x3514890
    image._protect(slot, 8, 0x04)
    ct.c_void_p.from_address(slot).value = ct.cast(research_folder, ct.c_void_p).value
    image._protect(slot, 8, 0x02)
    # Die Endgrid-Stufe schreibt über die native CRT-Standardausgabe.
    # CRT-Basisinitialisierung allein richtet deren Critical Sections nicht ein.
    # RVA2998258 initialisiert ausschließlich die drei Standardstreams.
    if image.function(0x2998258, ct.c_int32)() != 0:
        raise NativeContractError('Native standard-stream initialization failed')
    storage = ct.create_string_buffer(24)
    image.function(0x11db2e0, ct.c_void_p, ct.c_void_p, ct.c_int32)(storage, 2)
    initialize = image.function(0x11db350, ct.c_ubyte, ct.c_void_p, ct.c_ubyte,
        ct.c_int32, ct.c_int32, ct.c_uint32, ct.c_ubyte, ct.c_ubyte, ct.c_ubyte)
    # Beatverarbeitung aktiv, optionale Zusatzanalysen aus; kein App-Start.
    if not initialize(storage, 0, 44100, frames, 32, 0, 0, 0):
        raise NativeContractError('Native grid initialization failed')
    feed = image.function(0x11db540, ct.c_ubyte, ct.c_void_p,
                          ct.c_void_p, ct.c_void_p, ct.c_int32)
    remaining = frames
    position = 0
    while remaining:
        # NativeAudioReader begrenzt jeden Zugriff auf 512 Frames. Die
        # Endgridstufe muss dieselbe begrenzte Feed-Aufteilung verwenden wie
        # NativeGridProcessor; große Einzel-Feeds würden vorher abbrechen.
        count = min(512, remaining)
        left, right = source.read(position, count)
        # Der native Feed erwartet Float32 mit PCM16-Amplitude.
        left = np.ascontiguousarray(left * np.float32(32768), dtype=np.float32)
        right = np.ascontiguousarray(right * np.float32(32768), dtype=np.float32)
        if not feed(storage, left.ctypes.data, right.ctypes.data, count):
            raise NativeContractError('Native grid feed rejected')
        position += count
        remaining -= count
    initial_bpm = image.function(0x11db6c0, ct.c_int32, ct.c_void_p)(storage)
    initial_count = image.function(0x11db6f0, ct.c_int32, ct.c_void_p)(storage)
    if not 0 < initial_bpm <= 100000 or not 0 < initial_count <= 6000:
        raise NativeContractError('Native initial grid unavailable')
    triples = (Triple * len(grid))(*(Triple(r['pos'], r['numBar'], r['bpm']) for r in grid))
    refine = image.function(0x11db800, ct.c_ubyte, ct.c_void_p, ct.c_int32,
        ct.c_int32, ct.c_int32, ct.POINTER(Triple), ct.c_int32, ct.c_int32)
    if not refine(storage, 0, initial_count, initial_bpm, triples, len(grid), bpm):
        raise NativeContractError('Native final grid refinement rejected')
    final_bpm = image.function(0x11db860, ct.c_int32, ct.c_void_p)(storage)
    count = image.function(0x11db890, ct.c_int32, ct.c_void_p)(storage)
    if not 0 < count <= 6000 or not 0 < final_bpm <= 100000:
        raise NativeContractError('Native final grid unavailable')
    output = (Triple * count)()
    image.function(0x11db8c0, None, ct.c_void_p, ct.POINTER(Triple))(storage, output)
    rows = [dict(pos=r.pos, numBar=r.numBar, bpm=r.bpm) for r in output]
    if _source_identity(path) != request['source_identity']:
        raise NativeContractError('Source changed during refinement')
    # Native Speicher bleibt bis zum sofortigen Ende dieses Einmalprozesses.
    # Kein wiederverwendbarer Dienst, solange der Freigabevertrag offen ist.
    return json.dumps(dict(contract='rb-7.2.19-final-grid-research-v2',
        executable_sha256=SHA256, verified=False, frames=frames, sample_rate=44100,
        initial_bpm_hundredths=initial_bpm, initial_count=initial_count,
        bpm_hundredths=final_bpm, grid=rows, diagnostic_dir=diagnostic_dir), allow_nan=False).encode('utf8')


def handle(payload):
    try:
        return _handle(payload)
    except Exception as error:
        return json.dumps(dict(status='unavailable', reason=f'{type(error).__name__}: {error}')).encode()

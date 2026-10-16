"""Isolierter Forschungsadapter für den gepinnten Rekordbox-Phrasengenerator.

Ein isolierter Original-WAV-Lauf liegt vor; vollständige App-Abnahme bleibt offen.
Keine Injection, keine Änderungen an Installation, Datenbank oder Audiodateien.
Nur handle() in einem OwnedModelProcess mit Job-Limit und Deadline verwenden.
Die native Abhängigkeitsrekonstruktion ist noch nicht vollständig; insbesondere
indirekte Kontrollflusskanten bleiben vor einer Produktfreigabe zu klären.
"""
from __future__ import annotations

import ctypes as ct
from ctypes import wintypes as wt
import hashlib
import json
import multiprocessing
from pathlib import Path
import struct
import sys


EXE = Path(r'C:\Program Files\rekordbox\rekordbox 7.2.19\rekordbox.exe')
SHA256 = 'c9ed23e974c51c75e2ec069fbd2679a3dbe606be9e79e9cbbd13d6418ab11c37'
CONTRACT_VERSION = 'rb-7.2.19-native-phrase-static-v1'
_resident_images = []
_used = False


class NativeContractError(RuntimeError):
    pass


def _kernel():
    kernel = ct.WinDLL('kernel32', use_last_error=True)
    signatures = {
        'VirtualAlloc': ([ct.c_void_p, ct.c_size_t, wt.DWORD, wt.DWORD], ct.c_void_p),
        'VirtualProtect': ([ct.c_void_p, ct.c_size_t, wt.DWORD, ct.POINTER(wt.DWORD)], wt.BOOL),
        'GetModuleHandleW': ([wt.LPCWSTR], wt.HMODULE),
        'GetProcAddress': ([wt.HMODULE, ct.c_char_p], ct.c_void_p),
        'GetCurrentProcess': ([], wt.HANDLE),
        'FlushInstructionCache': ([wt.HANDLE, ct.c_void_p, ct.c_size_t], wt.BOOL),
        'RtlAddFunctionTable': ([ct.c_void_p, wt.DWORD, ct.c_uint64], ct.c_ubyte),
    }
    for name, (args, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
    return kernel


class NativeImage:
    """Privates RAM-Abbild; bleibt bis zum Ende des Einmal-Kindprozesses geladen.

    Kein EXE-EntryPoint, kein TLS-Callback und kein App-Konstruktor wird gestartet.
    Windows-Imports werden nur aus dem bereits geladenen KERNEL32 gebunden.
    Andere Imports bleiben absichtlich null, statt fremde DLLs zu initialisieren.
    Das ist eine Forschungsgrenze, kein Nachweis einer vollständigen Laufzeit.
    """

    def __init__(self):
        if sys.platform != 'win32' or ct.sizeof(ct.c_void_p) != 8:
            raise NativeContractError('Windows x64 required')
        if multiprocessing.current_process().name == 'MainProcess':
            raise NativeContractError('Dedicated owned child process required')
        raw = EXE.read_bytes()
        if hashlib.sha256(raw).hexdigest() != SHA256:
            raise NativeContractError('Unsupported Rekordbox executable')
        # Explizite Laufzeitabhängigkeit; keine temporären Forschungspfade.
        import pefile
        pe = pefile.PE(data=raw, fast_load=True)
        pe.parse_data_directories(directories=[1, 5])
        if pe.FILE_HEADER.Machine != 0x8664 or pe.OPTIONAL_HEADER.Magic != 0x20b:
            raise NativeContractError('Unsupported PE architecture')
        size = pe.OPTIONAL_HEADER.SizeOfImage
        if size != 106377216:
            raise NativeContractError('Unexpected pinned image size')
        self.kernel = _kernel()
        self.base = self.kernel.VirtualAlloc(None, size, 0x3000, 0x04)
        if not self.base:
            raise ct.WinError(ct.get_last_error())
        # Nach einem Teilfehler ebenfalls resident lassen: native FLS-/Unwind-
        # Zeiger dürfen nie vor dem Prozessende auf freigegebenen Code zeigen.
        _resident_images.append(self)
        image = bytearray(size)
        header_size = pe.OPTIONAL_HEADER.SizeOfHeaders
        image[:header_size] = raw[:header_size]
        for section in pe.sections:
            data = section.get_data()
            start = section.VirtualAddress
            if start + len(data) > size:
                raise NativeContractError('Invalid section bounds')
            image[start:start + len(data)] = data
        delta = self.base - pe.OPTIONAL_HEADER.ImageBase
        for block in pe.DIRECTORY_ENTRY_BASERELOC:
            for entry in block.entries:
                if entry.type == 0:
                    continue
                if entry.type != 10 or not 0 <= entry.rva <= size - 8:
                    raise NativeContractError('Unsupported relocation')
                value = struct.unpack_from('<Q', image, entry.rva)[0]
                struct.pack_into('<Q', image, entry.rva, (value + delta) & ((1 << 64) - 1))
        kernel_handle = self.kernel.GetModuleHandleW('kernel32.dll')
        if not kernel_handle:
            raise ct.WinError(ct.get_last_error())
        for descriptor in pe.DIRECTORY_ENTRY_IMPORT:
            allowed = descriptor.dll.lower() == b'kernel32.dll'
            for symbol in descriptor.imports:
                address = 0
                if allowed:
                    if not symbol.name:
                        raise NativeContractError('Unexpected kernel ordinal')
                    address = self.kernel.GetProcAddress(kernel_handle, symbol.name)
                    if not address:
                        raise NativeContractError('Missing kernel import: ' + symbol.name.decode('ascii'))
                rva = symbol.address - pe.OPTIONAL_HEADER.ImageBase
                if not 0 <= rva <= size - 8:
                    raise NativeContractError('Invalid import bounds')
                struct.pack_into('<Q', image, rva, address)
        ct.memmove(self.base, bytes(image), size)
        del image, raw
        self._protect(self.base, header_size, 0x02)
        for section in pe.sections:
            execute = bool(section.Characteristics & 0x20000000)
            write = bool(section.Characteristics & 0x80000000)
            protection = (0x40 if write else 0x20) if execute else (0x04 if write else 0x02)
            self._protect(self.base + section.VirtualAddress,
                          max(section.Misc_VirtualSize, section.SizeOfRawData), protection)
        exception = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
        if (not exception.VirtualAddress or exception.Size % 12
                or exception.VirtualAddress + exception.Size > size):
            raise NativeContractError('Invalid unwind table')
        if not self.kernel.RtlAddFunctionTable(self.base + exception.VirtualAddress,
                                              exception.Size // 12, self.base):
            raise NativeContractError('Could not register unwind table')
        if not self.kernel.FlushInstructionCache(self.kernel.GetCurrentProcess(), self.base, size):
            raise ct.WinError(ct.get_last_error())
        # Separat rekonstruierte CRT-Tabelle 0x40a6a50..0x40a6b50;
        # keine globale App-Initialisierung über den EXE-Einstieg.
        if not self.function(0x29c13ac, ct.c_ubyte)():
            raise NativeContractError('Native CRT initialization failed')

    def _protect(self, address, size, protection):
        old = wt.DWORD()
        if size and not self.kernel.VirtualProtect(address, size, protection, ct.byref(old)):
            raise ct.WinError(ct.get_last_error())

    def function(self, rva, result, *arguments):
        return ct.WINFUNCTYPE(result, *arguments)(self.base + rva)


class NativeResult(ct.Structure):
    _fields_ = [('header', ct.c_int32 * 7), ('padding', ct.c_int32),
                ('arrays', ct.c_void_p * 11)]


ARRAY_NAMES = ('beat_positions', 'kind', 'beat_4', 'moriage', 'moriage_pos_judge',
               'moriage_pos_4_pos_start', 'moriage_pos_8_pos_start',
               'moriage_pos_16_pos_start', 'aori', 'fill_in', 'fill_in_pos_start')


def _source_identity(path):
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns, stat.st_dev, stat.st_ino]


def generate(request):
    """Liest Originalaudio nur lesend, gibt ausschließlich rohe native Werte ab.

    Keine Taktfreigabe und keine HPG-Phrasenlabels. Das vollständige native
    Headerlayout bleibt als Rohwerte sichtbar, bis die Semantik belegt ist.
    """
    import numpy as np
    import soundfile as sf
    required = {'path', 'source_identity', 'bpm_hundredths', 'offset_ms', 'bar_position', 'key_index'}
    if type(request) is not dict or set(request) != required:
        raise NativeContractError('Invalid request fields')
    path = Path(request['path'])
    if not path.is_absolute() or not path.is_file():
        raise NativeContractError('Absolute existing source path required')
    if _source_identity(path) != request['source_identity']:
        raise NativeContractError('Source identity mismatch')
    bpm, offset, position, key = (request[name] for name in
                                 ('bpm_hundredths', 'offset_ms', 'bar_position', 'key_index'))
    if (any(type(value) is not int for value in (bpm, offset, position, key))
            or not 1 <= bpm <= 100000 or not 0 <= offset <= 6000000 / bpm
            or not 1 <= position <= 4 or not 0 <= key < 24):
        raise NativeContractError('Invalid native grid parameters')
    with sf.SoundFile(str(path), mode='r') as source:
        frames, rate, channels = len(source), source.samplerate, source.channels
        if (not 1 <= frames < 2**31 or rate <= 0 or channels not in (1, 2)
                or frames / rate > 7200):
            raise NativeContractError('Unsupported source dimensions')
        if source.subtype in ('FLOAT', 'DOUBLE'):
            # libsndfile skaliert Float-Dateien beim Lesen als int16 nicht
            # automatisch auf PCM16. Ohne belegte native Konversion ablehnen.
            raise NativeContractError('Floating-point source conversion not reconstructed')
        image = NativeImage()
        constructor = image.function(0x12ce6c0, ct.c_void_p, ct.c_void_p)
        initialize = image.function(0x12cf6e0, ct.c_ubyte, ct.c_void_p,
            ct.c_int32, ct.c_int32, ct.c_int32, ct.c_int32, ct.c_int32, ct.c_uint32,
            ct.c_ubyte, ct.c_ubyte, ct.c_ubyte, ct.c_void_p)
        destructor = image.function(0x12ceff0, None, ct.c_void_p)
        release_result = image.function(0x11ee2f0, None, ct.c_void_p)
        passes = [image.function(rva, ct.c_int32, ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_int32)
                  for rva in (0x12cf990, 0x12cfaf0)]
        storage = ct.create_string_buffer(0x1d80)
        result = NativeResult()
        # Geliehener Ergebniszeiger: rekonstruierte Shared-Pointer-Helfer
        # überspringen Refcount/virtuelle Freigabe bei null Controlblock.
        pair = (ct.c_void_p * 2)(ct.addressof(result), None)
        constructed = False
        completed = False
        try:
            constructor(ct.addressof(storage))
            constructed = True
            if not initialize(ct.addressof(storage), frames, rate, bpm, offset,
                              position, key, 0, 1, 1, ct.addressof(pair)):
                raise NativeContractError('Generator initialization failed')
            block_size = rate * 128 // 75
            for function, expected in zip(passes, (3, 5)):
                source.seek(0)
                state = 0
                while source.tell() < frames:
                    # Native121a780 wandelt signed16 direkt zu Float32, ohne
                    # Normierung. HPG verwendet hier libsndfile; Decoder-
                    # Bitgleichheit zum Rekordbox-Decoder ist nicht behauptet.
                    pcm = source.read(min(block_size, frames-source.tell()), dtype='int16', always_2d=True)
                    if not len(pcm):
                        raise NativeContractError('Unexpected source EOF')
                    left = np.ascontiguousarray(pcm[:, 0], dtype=np.float32)
                    right = np.ascontiguousarray(pcm[:, channels-1], dtype=np.float32)
                    state = function(ct.addressof(storage), left.ctypes.data, right.ctypes.data, len(left))
                    if state < 0:
                        raise NativeContractError('Native generator failure')
                    if state >= expected:
                        break
                if state != expected:
                    raise NativeContractError('Incomplete native pass')
            completed = True
            count = result.header[0]
            if not 1 <= count <= 65535:
                raise NativeContractError('Invalid native result count')
            arrays = {}
            for name, address in zip(ARRAY_NAMES, result.arrays):
                if not address:
                    raise NativeContractError('Missing native result array')
                arrays[name] = list(struct.unpack('<' + 'i'*count, ct.string_at(address, count*4)))
            if _source_identity(path) != request['source_identity']:
                raise NativeContractError('Source changed while reading')
            return dict(status='ok', contract=CONTRACT_VERSION, executable_sha256=SHA256,
                        header=list(result.header), arrays=arrays, frames=frames, sample_rate=rate,
                        input_grid=dict(bpm_hundredths=bpm, offset_ms=offset,
                                        bar_position=position, key_index=key))
        finally:
            # Auf Fehlerpfaden kann native Ausgabe bereits intern freigegeben
            # sein. Dann kein zweites free und keine weiteren nativen Aufrufe;
            # der Einmal-Prozess samt Job wird vom Owner vollständig beendet.
            if constructed and completed:
                destructor(ct.addressof(storage))
                release_result(ct.addressof(result))


def handle(payload):
    """Ein Auftrag pro OwnedModelProcess; keine native Zustandswiederverwendung."""
    global _used
    if _used or len(payload) > 16384:
        raise NativeContractError('Single request per worker required')
    _used = True
    request = json.loads(payload)
    try:
        result = generate(request)
    except Exception as error:
        result = dict(status='unavailable', reason=type(error).__name__ + ': ' + str(error),
                      contract=CONTRACT_VERSION, executable_sha256=SHA256)
    return json.dumps(result, allow_nan=False, separators=(',', ':')).encode('utf8')

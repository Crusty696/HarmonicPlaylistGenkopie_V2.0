"""Gepinnter Rekordbox-Dateireader, ausschließlich im begrenzten Einmalprozess.

RVA2cdda20/2cdd910/1113330: Originaldecoder, native Sampleratenwandlung und planare
Float-Ausgabe. Keine Kopie der Quelldatei und kein Dateischreibpfad in HPG.
"""
import ctypes as ct
from pathlib import Path

import numpy as np

from .native_phrase_worker import EXE, NativeContractError, _source_identity

CONTRACT = 'rb-7.2.19-file-reader-v1'
RATE = 44100
MAX_SECONDS = 1200


def bind_reader_imports(image):
    """Nur Windows-Systembibliotheken für Dateireader/Threads/Medien anbinden."""
    import pefile
    allowed = {b'advapi32.dll', b'user32.dll', b'gdi32.dll', b'shell32.dll',
               b'ole32.dll', b'oleaut32.dll', b'version.dll', b'shlwapi.dll',
               b'winmm.dll', b'mfreadwrite.dll', b'mf.dll', b'propsys.dll'}
    libraries = []
    pe = pefile.PE(str(EXE), fast_load=True)
    try:
        pe.parse_data_directories(directories=[1])
        for descriptor in pe.DIRECTORY_ENTRY_IMPORT:
            if descriptor.dll.lower() not in allowed:
                continue
            library = ct.WinDLL(descriptor.dll.decode('ascii'), winmode=0x800)
            libraries.append(library)
            for symbol in descriptor.imports:
                if not symbol.name and (descriptor.dll.lower(), symbol.ordinal) != (b'shlwapi.dll', 12):
                    raise NativeContractError('Unexpected reader import ordinal')
                export = symbol.name or ct.cast(ct.c_void_p(symbol.ordinal), ct.c_char_p)
                address = image.kernel.GetProcAddress(library._handle, export)
                if not address:
                    raise NativeContractError('Missing reader system import')
                slot = image.base + symbol.address - pe.OPTIONAL_HEADER.ImageBase
                image._protect(slot, 8, 0x04)
                ct.c_void_p.from_address(slot).value = address
                image._protect(slot, 8, 0x02)
    finally:
        pe.close()
    image.reader_libraries = libraries
    # RVA11236f9/112373c: zwei private Resampler-Critical-Sections.
    # Manuell gemappte EXE besitzt keine registrierte statische PE-TLS.
    initialize = image.kernel.InitializeCriticalSection
    initialize.argtypes, initialize.restype = [ct.c_void_p], None
    for rva in (0x61ac388, 0x61ac1c8):
        initialize(image.base + rva)
    for rva in (0x61ac1c0, 0x61ac590):
        ct.c_int32.from_address(image.base + rva).value = -(2**31)


class NativeAudioReader:
    """Synchrone native WAV/AIFF-Decoder und originaler Resampler.

    Explizite native WAV/AIFF-Factory statt Rekordbox-App-/Plugininitialisierung.
    Das belegt nicht die Auswahl externer Rekordbox-Codecplugins.
    Native Objekte bleiben ausschließlich bis zum Ende des Einmalprozesses.
    """
    def __init__(self, image, path):
        self.image = image
        self.path = Path(path).resolve(strict=True)
        self.identity = _source_identity(self.path)
        if self.path.suffix.lower() not in ('.wav', '.aif', '.aiff'):
            raise NativeContractError('Native builtin reader supports WAV/AIFF only')
        if self.path.stat().st_size > 2**31 - 1:
            raise NativeContractError('Native reader file size exceeded')
        self.owner = ct.create_string_buffer(0x28)
        image.function(0x1104730, ct.c_void_p, ct.c_void_p)(self.owner)
        name = ct.c_void_p()
        image.function(0x2a6e420, ct.c_void_p, ct.c_void_p, ct.c_char_p)(
            ct.byref(name), str(self.path).encode('utf8'))
        try:
            factory_rva = 0x2cdda20 if self.path.suffix.lower() == '.wav' else 0x2cdd910
            decoder = image.function(factory_rva, ct.c_void_p, ct.c_void_p,
                                     ct.c_void_p)(None, ct.byref(name))
            if not decoder:
                raise NativeContractError('Native decoder factory rejected extension')
            # RVA2d36e60: Modus0 liest direkt aus dem nativen Dateistream.
            # Modus2 benötigt Rekordbox-eigene asynchrone Vorladekoordination.
            # Dekodierung und Resampling bleiben die originalen Routinen.
            ct.c_int32.from_address(decoder + 0x90).value = 0
            if not self._virtual(decoder, 8, ct.c_ubyte, ct.c_void_p)(decoder, ct.byref(name)):
                raise NativeContractError('Native file open failed')
            # Ein eigener Referenzanteil wird von RVA1113330 konsumiert.
            ct.c_int32.from_address(decoder + 8).value = 1
            reference = ct.c_void_p(decoder)
            opened = image.function(0x1113330, ct.c_ubyte, ct.c_void_p,
                ct.c_void_p, ct.c_int32, ct.c_void_p)(
                    self.owner, ct.byref(reference), RATE, ct.byref(name))
        finally:
            image.function(0x2a6e690, None, ct.c_void_p)(ct.byref(name))
        if not opened:
            raise NativeContractError('Native builtin decoder could not open source')
        decoder = ct.c_void_p.from_buffer(self.owner, 8).value
        resampler = ct.c_void_p.from_buffer(self.owner, 16).value
        self.source_rate = self._virtual(decoder, 0x60, ct.c_int32)(decoder)
        self.channels = self._virtual(decoder, 0x88, ct.c_uint16)(decoder)
        self.bit_depth = self._virtual(decoder, 0x78, ct.c_uint16)(decoder)
        self.source_frames = self._virtual(decoder, 0x38, ct.c_int32)(decoder)
        self.frames = (self._virtual(resampler, 0x18, ct.c_int32)(resampler)
                       if resampler else self.source_frames)
        if (not RATE <= self.frames <= RATE * MAX_SECONDS
                or self.channels not in (1, 2) or not 8000 <= self.source_rate <= 384000):
            raise NativeContractError('Native reader rejected source dimensions')
        self.decoder = resampler or decoder
        self.read_function = self._virtual(self.decoder, 0x10 if resampler else 0x18,
            None, ct.c_int32, ct.c_void_p, ct.c_int32)

    def _virtual(self, address, offset, result, *args):
        if not address:
            raise NativeContractError('Missing native reader object')
        table = ct.c_void_p.from_address(address).value
        target = ct.c_void_p.from_address(table + offset).value
        if not self.image.base <= target < self.image.base + 106377216:
            raise NativeContractError('Unexpected native reader function')
        return ct.WINFUNCTYPE(result, ct.c_void_p, *args)(target)

    def read(self, start, count):
        if (type(start) is not int or type(count) is not int or start < 0
                or not 1 <= count <= 512 or start + count > self.frames):
            raise NativeContractError('Invalid native reader window')
        # Native Decoder schreiben vier Float-Lanes pro Frame, nicht zwei.
        samples = np.full((count, 4), np.nan, dtype=np.float32)
        self.read_function(self.decoder, start, samples.ctypes.data, count)
        if not np.isfinite(samples[:, :self.channels]).all():
            raise NativeContractError('Incomplete or nonfinite native audio')
        left = np.ascontiguousarray(samples[:, 0])
        right = np.ascontiguousarray(samples[:, 1]) if self.channels == 2 else left.copy()
        return left, right

    def metadata(self):
        if _source_identity(self.path) != self.identity:
            raise NativeContractError('Source changed during native reading')
        return dict(contract=CONTRACT, source_sample_rate=self.source_rate,
                    source_channels=self.channels, source_bit_depth=self.bit_depth,
                    source_frames=self.source_frames,
                    output_sample_rate=RATE, output_frames=self.frames)

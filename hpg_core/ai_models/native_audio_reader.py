"""Gepinnter Rekordbox-Dateireader, ausschließlich im begrenzten Einmalprozess.

RVA2cdda20/2cdd910/1113330: Originaldecoder, native Sampleratenwandlung und planare
Float-Ausgabe. Keine Kopie der Quelldatei und kein Dateischreibpfad in HPG.
"""
import ctypes as ct
import atexit
import hashlib
import math
import multiprocessing
import os
from pathlib import Path
import sys
import threading

import numpy as np

from .feature_audio import mono_downmix
from .native_phrase_worker import EXE, NativeContractError, _source_identity

CONTRACT = 'rb-7.2.19-file-reader-v29'
RATE = 44100
MAX_SECONDS = 7200
NATIVE_REKORDBOX_FACTORIES = {
    '.mp3': 0x2cdd8a0,
    '.wav': 0x2cdda20,
    '.wave': 0x2cdda20,
    '.aif': 0x2cdd910,
    '.aiff': 0x2cdd910,
    '.flac': 0x2cdd6e0,
    '.fla': 0x2cdd6e0,
    '.m4a': 0x2cdd760,
    '.mp4': 0x2cdd760,
    '.aac': 0x2cdd7f0,
}
NATIVE_REKORDBOX_READER_EXTENSIONS = frozenset(NATIVE_REKORDBOX_FACTORIES)
MPG123_DLL_SHA256 = '2c3dcb9fa2a47cfd30fef8cb03d13f573457fbca5bf38abfe3b5980d6e4496df'
MPG123_ENC_SIGNED_16 = 0xD0
MPG123_DONE = -12
MPG123_NEW_FORMAT = -11
_MPG123_RUNTIME_LOCK = threading.Lock()
_MPG123_LIBRARY = None
_MPG123_DLL_DIRECTORY = None
_MPG123_VERIFIED_FILE = None
_READER_IMAGE_LOCK = threading.Lock()
_READER_IMAGE = None
_READER_IMAGE_ERROR = None


def _ceil_resampled_frames(source_frames, source_rate):
    """Berechne die 44,1-kHz-Länge ohne Float-Rundungsfehler."""
    return (source_frames * RATE + source_rate - 1) // source_rate


def _close_mpg123_decoder(library, decoder):
    """Fehlgeschlagenes Decoder-Close nicht als sauberes Ende verbuchen."""
    if library.mpg123_close(decoder) != 0:
        raise NativeContractError('Rekordbox mpg123 decoder close failed')


def _shutdown_mpg123():
    """Beende die pro Prozess einmal initialisierte Decoderbibliothek."""
    with _MPG123_RUNTIME_LOCK:
        if _MPG123_LIBRARY is not None:
            _MPG123_LIBRARY.mpg123_exit()


def _mpg123_library(dll_path):
    """Teilt nur die globale Bibliotheksinitialisierung; Decoder bleiben lokal."""
    global _MPG123_LIBRARY, _MPG123_DLL_DIRECTORY
    with _MPG123_RUNTIME_LOCK:
        if _MPG123_LIBRARY is not None:
            return _MPG123_LIBRARY
        dll_directory = None
        try:
            dll_directory = os.add_dll_directory(str(dll_path.parent))
            library = ct.CDLL(str(dll_path), winmode=0x1100)
            signatures = {
                'mpg123_init': ([], ct.c_int),
                'mpg123_exit': ([], None),
                'mpg123_new': ([ct.c_char_p, ct.POINTER(ct.c_int)], ct.c_void_p),
                'mpg123_delete': ([ct.c_void_p], None),
                'mpg123_format_none': ([ct.c_void_p], ct.c_int),
                'mpg123_param': ([ct.c_void_p, ct.c_int, ct.c_long, ct.c_double], ct.c_int),
                'mpg123_format': ([ct.c_void_p, ct.c_long, ct.c_int, ct.c_int], ct.c_int),
                'mpg123_rates': ([ct.POINTER(ct.POINTER(ct.c_long)), ct.POINTER(ct.c_size_t)], None),
                'mpg123_encodings': ([ct.POINTER(ct.POINTER(ct.c_int)), ct.POINTER(ct.c_size_t)], None),
                'mpg123_replace_reader_handle': ([ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_void_p], ct.c_int),
                'mpg123_open_handle': ([ct.c_void_p, ct.c_void_p], ct.c_int),
                'mpg123_getformat': ([ct.c_void_p, ct.POINTER(ct.c_long), ct.POINTER(ct.c_int), ct.POINTER(ct.c_int)], ct.c_int),
                'mpg123_length': ([ct.c_void_p], ct.c_longlong),
                'mpg123_outblock': ([ct.c_void_p], ct.c_size_t),
                'mpg123_read': ([ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.POINTER(ct.c_size_t)], ct.c_int),
                'mpg123_seek': ([ct.c_void_p, ct.c_longlong, ct.c_int], ct.c_longlong),
                'mpg123_close': ([ct.c_void_p], ct.c_int),
            }
            for name, (arguments, result) in signatures.items():
                try:
                    function = getattr(library, name)
                except AttributeError as missing:
                    raise NativeContractError(
                        f'Rekordbox mpg123 export missing: {name}'
                    ) from missing
                function.argtypes, function.restype = arguments, result
            if library.mpg123_init() != 0:
                raise NativeContractError('Rekordbox mpg123 initialization failed')
        except Exception as error:
            if dll_directory is not None:
                try:
                    dll_directory.close()
                except Exception:
                    pass
            if isinstance(error, NativeContractError):
                raise
            raise NativeContractError('Bundled Rekordbox mpg123 failed to initialize') from error
        _MPG123_DLL_DIRECTORY = dll_directory
        _MPG123_LIBRARY = library
        atexit.register(_shutdown_mpg123)
        return library


def _verify_mpg123_binary(dll_path):
    """Prüfe gepinnte DLL einmal je unveränderter Dateisignatur pro Prozess."""
    global _MPG123_VERIFIED_FILE
    dll_path = Path(dll_path).resolve()
    try:
        stat = dll_path.stat()
    except OSError as error:
        raise NativeContractError('Bundled Rekordbox mpg123 is unavailable') from error
    signature = (str(dll_path), stat.st_size, stat.st_mtime_ns,
                 stat.st_ctime_ns, getattr(stat, 'st_ino', 0))
    with _MPG123_RUNTIME_LOCK:
        if _MPG123_VERIFIED_FILE == signature:
            return
        digest = hashlib.sha256()
        try:
            with dll_path.open('rb') as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(chunk)
            after = dll_path.stat()
        except OSError as error:
            raise NativeContractError('Bundled Rekordbox mpg123 is unavailable') from error
        after_signature = (str(dll_path), after.st_size, after.st_mtime_ns,
                           after.st_ctime_ns, getattr(after, 'st_ino', 0))
        if after_signature != signature:
            raise NativeContractError('Rekordbox mpg123 changed during verification')
        if digest.hexdigest() != MPG123_DLL_SHA256:
            raise NativeContractError('Unsupported Rekordbox mpg123 binary')
        _MPG123_VERIFIED_FILE = signature


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
    # AAC-Konstruktor RVA2d0ee30 betritt die globale Sperre 0x1461a5670
    # (Image-RVA 0x61a5670), bevor er seinen Decoder-Singleton erzeugt.
    # Die EXE-Startupinitialisierung wurde im isolierten Readerprozess nicht
    # ausgeführt; die private Sperre muss daher wie die Resampler-Sperren
    # genau einmal vor dem ersten nativen Factory-Aufruf angelegt werden.
    for rva in (0x61ac388, 0x61ac1c8, 0x61a5670):
        initialize(image.base + rva)
    for rva in (0x61ac1c0, 0x61ac590):
        ct.c_int32.from_address(image.base + rva).value = -(2**31)


def _reader_image():
    """Halte das grosse Rekordbox-Abbild pro Workerprozess nur einmal resident."""
    global _READER_IMAGE, _READER_IMAGE_ERROR
    if _READER_IMAGE_ERROR is not None:
        raise NativeContractError(_READER_IMAGE_ERROR)
    if _READER_IMAGE is not None:
        return _READER_IMAGE
    with _READER_IMAGE_LOCK:
        if _READER_IMAGE_ERROR is not None:
            raise NativeContractError(_READER_IMAGE_ERROR)
        if _READER_IMAGE is None:
            try:
                from .native_phrase_worker import NativeImage
                image = NativeImage()
                bind_reader_imports(image)
                _READER_IMAGE = image
            except Exception as error:
                # NativeImage bleibt bei Teilfehlern absichtlich resident;
                # nicht bei jeder Vorschau ein weiteres 106-MB-Abbild anlegen.
                _READER_IMAGE_ERROR = (
                    f'Rekordbox reader image initialization failed: '
                    f'{type(error).__name__}: {error}')
                raise
    return _READER_IMAGE


class NativeAudioReader:
    """Gepinnte Rekordbox-Reader; nur nicht unterstützte Quellen fallen zurück."""
    def __init__(self, image, path, *, max_seconds=MAX_SECONDS, start_seconds=0.0,
                 use_rekordbox=True):
        self.image = image
        self.path = Path(path).resolve(strict=True)
        self.identity = _source_identity(self.path)
        self._mpg123_state = None
        self._soundfile_state = None
        self._audioread_state = None
        if type(use_rekordbox) is not bool:
            raise NativeContractError('Invalid native reader selection')
        if (type(max_seconds) not in (int, float) or not math.isfinite(max_seconds)
                or not 0 < max_seconds <= MAX_SECONDS):
            raise NativeContractError('Invalid native reader duration limit')
        self.max_seconds = float(max_seconds)
        if (type(start_seconds) not in (int, float) or not math.isfinite(start_seconds)
                or start_seconds < 0 or start_seconds + self.max_seconds > MAX_SECONDS):
            raise NativeContractError('Invalid native reader start/duration')
        self.start_seconds = float(start_seconds)
        if self.path.stat().st_size > 2**31 - 1:
            raise NativeContractError('Native reader file size exceeded')
        self.owner = ct.create_string_buffer(0x28)
        suffix = self.path.suffix.lower()
        if not use_rekordbox:
            self._open_fallback()
            return
        if suffix == '.mp3' and image is None:
            try:
                self._open_rekordbox_mpg123()
                return
            except Exception:
                # Auch Fehler aus DLL-Bindung oder Resampler-Initialisierung
                # muessen den vorhandenen HPG-Reader-Fallback erreichen.
                # _open_rekordbox_mpg123 raeumt einen begonnenen Open-Versuch
                # vor dem Weiterwerfen auf; der Fallback bleibt separat sichtbar.
                self._open_fallback()
                return
        if suffix not in NATIVE_REKORDBOX_FACTORIES:
            self._open_fallback()
            return
        if image is None:
            # WAV/AIFF brauchen hier ein initialisiertes Image. Der
            # NativeAudioStream waehlt vor diesem Aufruf den HPG-Fallback.
            if suffix in ('.wav', '.wave', '.aif', '.aiff'):
                raise NativeContractError('Required Rekordbox reader unavailable')
            self._open_fallback()
            return
        factory_rva = NATIVE_REKORDBOX_FACTORIES[suffix]
        self.backend = {
            '.mp3': 'rekordbox-builtin-mp3',
            '.flac': 'rekordbox-builtin-flac',
            '.fla': 'rekordbox-builtin-flac',
            '.m4a': 'rekordbox-builtin-mp4',
            '.mp4': 'rekordbox-builtin-mp4',
            '.aac': 'rekordbox-builtin-aac',
        }.get(suffix, 'rekordbox-builtin')
        image.function(0x1104730, ct.c_void_p, ct.c_void_p)(self.owner)
        name = ct.c_void_p()
        image.function(0x2a6e420, ct.c_void_p, ct.c_void_p, ct.c_char_p)(
            ct.byref(name), str(self.path).encode('utf8'))
        try:
            decoder = image.function(factory_rva, ct.c_void_p, ct.c_void_p,
                                     ct.c_void_p)(None, ct.byref(name))
            if not decoder:
                # Factory hat kein Decoderobjekt geliefert: Es gibt keinen
                # nativen Reader freizugeben. HPG darf das Format read-only
                # selbst dekodieren; Fehler nach erfolgreicher Factory bleiben
                # fail-closed, da deren native Ownership hier nicht belegt ist.
                self._open_fallback()
                return
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
        self.source_channels = self.channels
        self.bit_depth = self._virtual(decoder, 0x78, ct.c_uint16)(decoder)
        self.source_frames = self._virtual(decoder, 0x38, ct.c_int32)(decoder)
        decoded_frames = (self._virtual(resampler, 0x18, ct.c_int32)(resampler)
                          if resampler else self.source_frames)
        if (not 0 < self.source_frames <= 2**31 - 1
                or not RATE <= decoded_frames <= RATE * MAX_SECONDS
                or self.channels not in (1, 2) or not 8000 <= self.source_rate <= 384000):
            raise NativeContractError('Native reader rejected source dimensions')
        # The native read vtable accepts an absolute frame index (used below
        # for windowed reads). Its output is at RATE after the native resampler.
        self._native_start_frame = round(self.start_seconds * RATE)
        if self._native_start_frame >= decoded_frames:
            raise NativeContractError('Native reader start exceeds source duration')
        self.frames = min(decoded_frames - self._native_start_frame,
                          math.ceil(self.max_seconds * RATE))
        self.decoder = resampler or decoder
        self.read_function = self._virtual(self.decoder, 0x10 if resampler else 0x18,
            None, ct.c_int32, ct.c_void_p, ct.c_int32)

    def _open_rekordbox_mpg123(self):
        """Dekodiere MP3 mit Rekordbox' versionsgepinntem libmpg123.dll.

        Der App-Reader-Registry-Dispatcher ist hier absichtlich nicht aufgerufen:
        sein globaler App-Manager wird erst durch Rekordbox' Startup konstruiert.
        Die exportierte libmpg123-API läuft dagegen eigenständig im Analysekind.
        """
        if multiprocessing.current_process().name == 'MainProcess':
            raise NativeContractError('Rekordbox mpg123 requires an isolated worker process')
        if os.name != 'nt' or ct.sizeof(ct.c_void_p) != 8:
            raise NativeContractError('Rekordbox mpg123 requires Windows x64')
        dll_path = EXE.parent / 'libmpg123.dll'
        _verify_mpg123_binary(dll_path)
        library = _mpg123_library(dll_path)
        error_code = ct.c_int()
        decoder = library.mpg123_new(None, ct.byref(error_code))
        if not decoder:
            raise NativeContractError('Rekordbox mpg123 decoder creation failed')
        try:
            file_reader = _WinMpg123File(self.path)
        except OSError as error:
            library.mpg123_delete(decoder)
            raise NativeContractError('Unable to open MP3 source read-only') from error
        except Exception:
            library.mpg123_delete(decoder)
            raise
        read_type = ct.CFUNCTYPE(ct.c_ssize_t, ct.c_void_p, ct.c_void_p, ct.c_size_t)
        seek_type = ct.CFUNCTYPE(ct.c_longlong, ct.c_void_p, ct.c_longlong, ct.c_int)
        cleanup_type = ct.CFUNCTYPE(None, ct.c_void_p)

        def read_callback(handle, buffer, size):
            try:
                amount = min(int(size), 0x7fffffff)
                count = ct.c_uint32()
                if not file_reader.kernel.ReadFile(handle, buffer, amount, ct.byref(count), None):
                    return -1
                return count.value
            except Exception:
                return -1

        def seek_callback(handle, offset, origin):
            try:
                position = ct.c_longlong()
                if origin not in (0, 1, 2) or not file_reader.kernel.SetFilePointerEx(
                        handle, offset, ct.byref(position), origin):
                    return -1
                return position.value
            except Exception:
                return -1

        def cleanup_callback(handle):
            file_reader.close()

        read_hook, seek_hook, cleanup_hook = (
            read_type(read_callback), seek_type(seek_callback), cleanup_type(cleanup_callback))
        opened = False
        streaming = False
        try:
            # Rekordbox 7.2.19 initializes its decoder with these exact calls
            # before selecting the output formats (FUN_142d0c5e0).
            for parameter, value in ((0, 0), (1, 0x300), (15, -1)):
                if library.mpg123_param(decoder, parameter, value, 0.0) != 0:
                    raise NativeContractError('Rekordbox mpg123 parameter setup failed')
            if library.mpg123_format_none(decoder) != 0:
                raise NativeContractError('Rekordbox mpg123 format reset failed')
            encodings_pointer = ct.POINTER(ct.c_int)()
            encodings_count = ct.c_size_t()
            library.mpg123_encodings(ct.byref(encodings_pointer), ct.byref(encodings_count))
            encodings = [int(encodings_pointer[index]) for index in range(min(encodings_count.value, 64))]
            if MPG123_ENC_SIGNED_16 not in encodings:
                raise NativeContractError('Rekordbox mpg123 lacks its native signed-16 format')
            # Rekordbox 7.2.19 liest zuerst Samplerate und Kanalzahl aus dem
            # MP3-Header und übergibt genau diese Werte an mpg123_format.
            # HPG erlaubt dieselben MPEG-Quellformate; mpg123 wählt daraus die
            # Rate und Kanalzahl des jeweiligen Tracks statt sie umzuwandeln.
            rates_pointer = ct.POINTER(ct.c_long)()
            rates_count = ct.c_size_t()
            library.mpg123_rates(ct.byref(rates_pointer), ct.byref(rates_count))
            if not 0 < rates_count.value <= 64:
                raise NativeContractError('Rekordbox mpg123 returned invalid sample rates')
            native_rates = tuple(int(rates_pointer[index]) for index in range(rates_count.value))
            if any(not 8000 <= rate <= 384000 for rate in native_rates):
                raise NativeContractError('Rekordbox mpg123 returned invalid sample rates')
            for native_rate in native_rates:
                if library.mpg123_format(
                        decoder, native_rate, 1 | 2, MPG123_ENC_SIGNED_16) != 0:
                    raise NativeContractError('Rekordbox mpg123 rejected native MP3 formats')
            if library.mpg123_replace_reader_handle(
                    decoder, ct.cast(read_hook, ct.c_void_p),
                    ct.cast(seek_hook, ct.c_void_p),
                    ct.cast(cleanup_hook, ct.c_void_p)) != 0:
                raise NativeContractError('Rekordbox mpg123 reader callbacks rejected')
            if library.mpg123_open_handle(decoder, file_reader.handle) != 0:
                raise NativeContractError('Rekordbox mpg123 could not open MP3')
            opened = True
            source_rate, channels, encoding = ct.c_long(), ct.c_int(), ct.c_int()

            def get_format():
                if library.mpg123_getformat(decoder, ct.byref(source_rate),
                        ct.byref(channels), ct.byref(encoding)) != 0:
                    raise NativeContractError('Rekordbox mpg123 could not read MP3 format')
                if (source_rate.value not in native_rates or channels.value not in (1, 2)
                        or encoding.value != MPG123_ENC_SIGNED_16):
                    raise NativeContractError('Unsupported Rekordbox mpg123 output format')

            get_format()
            # Nicht wie ein begrenztes Analysefenster als vollständigen Track
            # ausgeben: Das Rekordbox-mpg123 muss die gleiche Quelldauergrenze
            # wie WAV/AIFF einhalten. mpg123_length liefert Samples im aktuell
            # ausgehandelten Quellformat. Ohne belastbare Gesamtlänge wird
            # der sichere HPG-Fallback verwendet statt einen Track abzuschneiden.
            source_length = int(library.mpg123_length(decoder))
            if source_length <= 0:
                raise NativeContractError('Rekordbox mpg123 could not determine source duration')
            if source_length > source_rate.value * MAX_SECONDS:
                raise NativeContractError('Native reader duration exceeded')
            source_start = round(self.start_seconds * source_rate.value)
            if source_start >= source_length:
                raise NativeContractError('Native reader start exceeds source duration')
            if self.start_seconds:
                actual_frame = library.mpg123_seek(decoder, source_start, 0)
                if actual_frame != source_start:
                    raise NativeContractError('Rekordbox mpg123 could not seek exactly')
            import soxr

            def get_stream_format():
                current_rate, current_channels, current_encoding = ct.c_long(), ct.c_int(), ct.c_int()
                if library.mpg123_getformat(decoder, ct.byref(current_rate),
                        ct.byref(current_channels), ct.byref(current_encoding)) != 0:
                    raise NativeContractError('Rekordbox mpg123 could not read MP3 format')
                return current_rate.value, current_channels.value, current_encoding.value

            stream_resampler = (soxr.ResampleStream(
                source_rate.value, RATE, channels.value, dtype='float32', quality='HQ')
                if source_rate.value != RATE else None)
            output_size = max(4096, min(
                int(library.mpg123_outblock(decoder)), 1024 * 1024))
            self.backend = ('rekordbox-mpg123-soxr-hq-stream'
                            if stream_resampler is not None else 'rekordbox-mpg123-stream')
            self.source_rate = int(source_rate.value)
            self.channels = int(channels.value)
            self.source_channels = self.channels
            self.bit_depth = 0
            self.source_frames = source_length
            remaining_source_frames = source_length - source_start
            expected_output_frames = _ceil_resampled_frames(
                remaining_source_frames, source_rate.value)
            self.frames = min(expected_output_frames, math.ceil(self.max_seconds * RATE))
            self.decoder = decoder
            self.read_function = None
            self._mpg123_state = dict(
                library=library, decoder=decoder, file_reader=file_reader,
                hooks=(read_hook, seek_hook, cleanup_hook),
                output=ct.create_string_buffer(output_size), output_size=output_size,
                resampler=stream_resampler, resampler_factory=soxr.ResampleStream,
                format_reader=get_stream_format,
                source_rate=int(source_rate.value), channels=int(channels.value),
                encoding=int(encoding.value), source_start=source_start,
                source_length=source_length, pending=np.empty((0, channels.value), np.float32),
                position=0, eof=False, stalls=0, generated=0,
                expected_output_frames=expected_output_frames,
                complete_window=(self.frames == expected_output_frames),
            )
            streaming = True
            return
        finally:
            if not streaming:
                active_error = sys.exc_info()[0] is not None
                cleanup_errors = []
                cleanup_actions = [file_reader.close,
                    lambda: library.mpg123_delete(decoder)]
                if opened:
                    cleanup_actions.insert(0, lambda: _close_mpg123_decoder(library, decoder))
                for cleanup in cleanup_actions:
                    try:
                        cleanup()
                    except Exception as error:
                        cleanup_errors.append(error)
                if cleanup_errors and not active_error:
                    raise NativeContractError('Rekordbox mpg123 cleanup failed') from cleanup_errors[0]

    def _reset_mpg123_stream(self):
        state = self._mpg123_state
        if state is None:
            raise NativeContractError('Rekordbox MP3 stream is closed')
        requested = state['source_start']
        actual = state['library'].mpg123_seek(state['decoder'], requested, 0)
        if actual != requested:
            raise NativeContractError('Rekordbox mpg123 could not reset stream position')
        state['resampler'] = (None if state['source_rate'] == RATE else
            state['resampler_factory'](state['source_rate'], RATE, state['channels'],
                                       dtype='float32', quality='HQ'))
        state['pending'] = np.empty((0, state['channels']), np.float32)
        state['position'] = 0
        state['eof'] = False
        state['stalls'] = 0
        state['generated'] = 0

    def _pull_mpg123_stream(self):
        state = self._mpg123_state
        written = ct.c_size_t()
        status = state['library'].mpg123_read(
            state['decoder'], state['output'], state['output_size'], ct.byref(written))
        if status == MPG123_NEW_FORMAT:
            if state['format_reader']() != (
                    state['source_rate'], state['channels'], state['encoding']):
                raise NativeContractError('Rekordbox mpg123 format changed mid-track')
        elif status not in (0, MPG123_DONE):
            raise NativeContractError(f'Rekordbox mpg123 decode failed ({status})')
        if written.value % (state['channels'] * 2):
            raise NativeContractError('Rekordbox mpg123 returned a partial frame')
        if written.value:
            source = (np.frombuffer(state['output'].raw[:written.value], dtype='<i2')
                      .reshape(-1, state['channels']).astype(np.float32) / 32768.0)
            state['stalls'] = 0
        else:
            source = np.empty((0, state['channels']), np.float32)
            if status != MPG123_DONE:
                state['stalls'] += 1
                if state['stalls'] > 2:
                    raise NativeContractError('Rekordbox mpg123 decoder stalled')
        last = status == MPG123_DONE
        if state['resampler'] is not None:
            output = state['resampler'].resample_chunk(source, last=last)
        else:
            output = source
        state['eof'] = last
        if (output.ndim != 2 or output.shape[1] != state['channels']
                or not np.isfinite(output).all()):
            raise NativeContractError('Rekordbox mpg123 produced invalid stream audio')
        state['generated'] += len(output)
        return np.ascontiguousarray(output, dtype=np.float32)

    def _replay_mpg123_stream_to(self, target):
        """Replay from the original stream start to an arbitrary output frame.

        mpg123 can seek in the compressed source, but restarting the HQ
        resampler at that point changes its filter history and can shift a
        segment seam. Replaying and discarding output preserves the exact same
        decoder/resampler path used by sequential reads.
        """
        state = self._mpg123_state
        while state['position'] < target:
            if not len(state['pending']):
                if state['eof']:
                    raise NativeContractError('MP3 stream ended before requested frame')
                state['pending'] = self._pull_mpg123_stream()
                if not len(state['pending']) and state['eof']:
                    raise NativeContractError('MP3 stream ended before requested frame')
            discard = min(target-state['position'], len(state['pending']))
            state['pending'] = state['pending'][discard:]
            state['position'] += discard

    def _read_mpg123_stream(self, start, count):
        state = self._mpg123_state
        if state is None:
            raise NativeContractError('Rekordbox MP3 stream is closed')
        if start != state['position']:
            try:
                if start < state['position']:
                    self._reset_mpg123_stream()
                self._replay_mpg123_stream_to(start)
            except NativeContractError as error:
                # Kein Decoderwechsel mitten in derselben Modellinferenz:
                # fehlgeschlagener Reset/Replay sperrt das native Ergebnis.
                raise NativeContractError(
                    'Rekordbox mpg123 stream could not reposition consistently') from error
            state = self._mpg123_state
        while len(state['pending']) < count and not state['eof']:
            decoded = self._pull_mpg123_stream()
            if len(decoded):
                state['pending'] = (decoded if not len(state['pending']) else
                                    np.concatenate((state['pending'], decoded), axis=0))
        if len(state['pending']) < count:
            raise NativeContractError('Incomplete Rekordbox mpg123 stream window')
        samples = state['pending'][:count]
        state['pending'] = state['pending'][count:]
        state['position'] += count
        if state['position'] == self.frames and state['complete_window']:
            extra_frames = len(state['pending'])
            if extra_frames > 2:
                raise NativeContractError('Rekordbox mpg123 exceeded reported source duration')
            state['pending'] = np.empty((0, state['channels']), np.float32)
            while not state['eof']:
                extra_frames += len(self._pull_mpg123_stream())
                if extra_frames > 2:
                    raise NativeContractError('Rekordbox mpg123 exceeded reported source duration')
            if abs(state['generated']-state['expected_output_frames']) > 2:
                raise NativeContractError('Rekordbox mpg123 source duration mismatch')
        left = np.ascontiguousarray(samples[:, 0])
        right = (np.ascontiguousarray(samples[:, 1]) if self.channels == 2
                 else left.copy())
        return left, right

    def _reset_soundfile_stream(self):
        state = self._soundfile_state
        if state is None:
            raise NativeContractError('SoundFile stream is closed')
        state['source'].seek(state['frame_offset'])
        state['source_read'] = 0
        state['resampler'] = (None if state['source_rate'] == RATE else
            state['resampler_factory'](state['source_rate'], RATE, state['channels'],
                                       dtype='float32', quality='HQ'))
        state['pending'] = np.empty((0, state['channels']), np.float32)
        state['position'] = 0
        state['generated'] = 0
        state['eof'] = False

    def _pull_soundfile_stream(self):
        state = self._soundfile_state
        count = min(65536, state['window_frames']-state['source_read'])
        decoded = state['source'].read(count, dtype='float32', always_2d=True)
        if (decoded.ndim != 2 or decoded.shape[1] != state['source_channels']
                or len(decoded) != count or not np.isfinite(decoded).all()):
            raise NativeContractError('Incomplete SoundFile decode block')
        state['source_read'] += len(decoded)
        if state['source_channels'] > 2:
            decoded = mono_downmix(decoded)
        last = state['source_read'] == state['window_frames']
        if state['resampler'] is not None:
            decoded = state['resampler'].resample_chunk(decoded, last=last)
        state['eof'] = last
        if (decoded.ndim != 2 or decoded.shape[1] != state['channels']
                or not np.isfinite(decoded).all()):
            raise NativeContractError('Invalid SoundFile resampler output')
        state['generated'] += len(decoded)
        return np.ascontiguousarray(decoded, dtype=np.float32)

    def _replay_soundfile_stream_to(self, target):
        state = self._soundfile_state
        while state['position'] < target:
            if not len(state['pending']):
                if state['eof']:
                    raise NativeContractError('SoundFile stream ended before requested frame')
                state['pending'] = self._pull_soundfile_stream()
            discard = min(target-state['position'], len(state['pending']))
            if not discard:
                raise NativeContractError('SoundFile stream made no forward progress')
            state['pending'] = state['pending'][discard:]
            state['position'] += discard

    def _read_soundfile_stream(self, start, count):
        state = self._soundfile_state
        if state is None:
            raise NativeContractError('SoundFile stream is closed')
        if start != state['position']:
            try:
                if start < state['position']:
                    self._reset_soundfile_stream()
                self._replay_soundfile_stream_to(start)
            except Exception as error:
                raise NativeContractError('SoundFile stream could not reposition consistently') from error
        while len(state['pending']) < count and not state['eof']:
            decoded = self._pull_soundfile_stream()
            if len(decoded):
                state['pending'] = (decoded if not len(state['pending']) else
                                    np.concatenate((state['pending'], decoded), axis=0))
        if len(state['pending']) < count:
            raise NativeContractError('Incomplete SoundFile stream window')
        samples = state['pending'][:count]
        state['pending'] = state['pending'][count:]
        state['position'] += count
        if state['position'] == self.frames and state['complete_window']:
            extra = len(state['pending'])
            if extra > 2:
                raise NativeContractError('SoundFile stream exceeded source duration')
            state['pending'] = np.empty((0, state['channels']), np.float32)
            while not state['eof']:
                extra += len(self._pull_soundfile_stream())
                if extra > 2:
                    raise NativeContractError('SoundFile stream exceeded source duration')
            if abs(state['generated']-state['expected_output_frames']) > 2:
                raise NativeContractError('SoundFile stream duration mismatch')
        left = np.ascontiguousarray(samples[:, 0])
        right = (np.ascontiguousarray(samples[:, 1]) if self.channels == 2
                 else left.copy())
        return left, right

    @staticmethod
    def _audioread_source(path):
        import audioread
        return audioread.audio_open(str(path))

    def _count_audioread_frames(self):
        source = self._audioread_source(self.path)
        try:
            rate, channels = int(source.samplerate), int(source.channels)
            if not 0 < rate <= 384000 or not 1 <= channels <= 32:
                raise NativeContractError('Unsupported audioread dimensions')
            frame_bytes = channels * 2
            frames = 0
            for block in source:
                if len(block) % frame_bytes:
                    raise NativeContractError('Audioread returned a partial PCM frame')
                frames += len(block) // frame_bytes
                if frames > rate * MAX_SECONDS:
                    raise NativeContractError('Native reader duration exceeded')
            if frames < 1:
                raise NativeContractError('Audioread returned no audio frames')
            return rate, channels, frames
        finally:
            source.close()

    def _fill_audioread_pending(self, needed):
        state = self._audioread_state
        while len(state['pending']) < needed and not state['source_eof']:
            try:
                block = next(state['iterator'])
            except StopIteration:
                state['source_eof'] = True
                break
            if not block:
                state['empty_blocks'] += 1
                if state['empty_blocks'] > 2:
                    raise NativeContractError('Audioread decoder stalled')
                continue
            state['empty_blocks'] = 0
            frame_bytes = state['source_channels'] * 2
            if len(block) % frame_bytes:
                raise NativeContractError('Audioread returned a partial PCM frame')
            values = np.frombuffer(block, dtype='<i2')
            values = values.reshape(-1, state['source_channels']).astype(np.float32)
            values *= np.float32(1. / 32768.)
            state['pending'] = (values if not len(state['pending']) else
                                np.concatenate((state['pending'], values), axis=0))

    def _skip_audioread_frames(self, count):
        state = self._audioread_state
        skipped = 0
        while skipped < count:
            self._fill_audioread_pending(min(65536, count-skipped))
            discard = min(count-skipped, len(state['pending']))
            if not discard:
                raise NativeContractError('Audioread ended before selected source window')
            state['pending'] = state['pending'][discard:]
            skipped += discard

    def _reset_audioread_stream(self):
        state = self._audioread_state
        if state is None:
            raise NativeContractError('Audioread stream is closed')
        state['source'].close()
        state['source'] = self._audioread_source(self.path)
        state['iterator'] = iter(state['source'])
        state['pending'] = np.empty((0, state['source_channels']), np.float32)
        state['source_eof'] = False
        state['empty_blocks'] = 0
        state['source_read'] = 0
        state['resampler'] = (None if state['source_rate'] == RATE else
            state['resampler_factory'](state['source_rate'], RATE, state['channels'],
                                       dtype='float32', quality='HQ'))
        state['position'] = 0
        state['generated'] = 0
        self._skip_audioread_frames(state['frame_offset'])

    def _pull_audioread_stream(self):
        state = self._audioread_state
        count = min(65536, state['window_frames']-state['source_read'])
        self._fill_audioread_pending(count)
        if len(state['pending']) < count:
            raise NativeContractError('Audioread ended before declared duration')
        decoded = state['pending'][:count]
        state['pending'] = state['pending'][count:]
        state['source_read'] += count
        if state['source_channels'] > 2:
            decoded = mono_downmix(decoded)
        last = state['source_read'] == state['window_frames']
        if state['resampler'] is not None:
            decoded = state['resampler'].resample_chunk(decoded, last=last)
        state['eof'] = last
        if (decoded.ndim != 2 or decoded.shape[1] != state['channels']
                or not np.isfinite(decoded).all()):
            raise NativeContractError('Invalid audioread resampler output')
        state['generated'] += len(decoded)
        return np.ascontiguousarray(decoded, dtype=np.float32)

    def _replay_audioread_stream_to(self, target):
        state = self._audioread_state
        while state['position'] < target:
            if not len(state['pending_output']):
                if state['eof']:
                    raise NativeContractError('Audioread stream ended before requested frame')
                state['pending_output'] = self._pull_audioread_stream()
            discard = min(target-state['position'], len(state['pending_output']))
            if not discard:
                raise NativeContractError('Audioread stream made no forward progress')
            state['pending_output'] = state['pending_output'][discard:]
            state['position'] += discard

    def _read_audioread_stream(self, start, count):
        state = self._audioread_state
        if state is None:
            raise NativeContractError('Audioread stream is closed')
        if start != state['position']:
            try:
                if start < state['position']:
                    self._reset_audioread_stream()
                self._replay_audioread_stream_to(start)
            except Exception as error:
                raise NativeContractError('Audioread stream could not reposition consistently') from error
        while len(state['pending_output']) < count and not state['eof']:
            decoded = self._pull_audioread_stream()
            if len(decoded):
                state['pending_output'] = (decoded if not len(state['pending_output']) else
                    np.concatenate((state['pending_output'], decoded), axis=0))
        if len(state['pending_output']) < count:
            raise NativeContractError('Incomplete audioread stream window')
        samples = state['pending_output'][:count]
        state['pending_output'] = state['pending_output'][count:]
        state['position'] += count
        if state['position'] == self.frames and state['complete_window']:
            extra = len(state['pending_output'])
            if extra > 2:
                raise NativeContractError('Audioread stream exceeded source duration')
            state['pending_output'] = np.empty((0, state['channels']), np.float32)
            while not state['eof']:
                extra += len(self._pull_audioread_stream())
                if extra > 2:
                    raise NativeContractError('Audioread stream exceeded source duration')
            if abs(state['generated']-state['expected_output_frames']) > 2:
                raise NativeContractError('Audioread stream duration mismatch')
        left = np.ascontiguousarray(samples[:, 0])
        right = (np.ascontiguousarray(samples[:, 1]) if self.channels == 2
                 else left.copy())
        return left, right

    def close(self):
        """Schließe aktive Decoder und gib blockweise Audioressourcen frei."""
        errors = []
        owner = getattr(self, 'owner', None)
        if owner is not None:
            # RVA1113330 gibt Decoder- (owner+8) und Resampler-Referenz
            # (owner+16) frei. Erst den Zeiger lösen, dann wie dort den
            # Rekordbox-Refcount atomar senken und bei letzter Referenz den
            # virtuellen Destruktor mit deleting=1 aufrufen.
            decrement = None
            for offset in (8, 16):
                try:
                    slot = ct.c_void_p.from_buffer(owner, offset)
                    pointer, slot.value = slot.value, None
                    if not pointer or ct.c_int32.from_address(pointer + 12).value != 0x52434F58:
                        continue
                    if decrement is None:
                        kernel = ct.WinDLL('kernel32', use_last_error=True)
                        decrement = kernel.InterlockedDecrement
                        decrement.argtypes = [ct.POINTER(ct.c_long)]
                        decrement.restype = ct.c_long
                    count = ct.cast(pointer + 8, ct.POINTER(ct.c_long))
                    if decrement(count) == 0:
                        vtable = ct.c_void_p.from_address(pointer).value
                        if not vtable:
                            raise NativeContractError('Native reader has no deleting vtable')
                        destructor = ct.c_void_p.from_address(vtable).value
                        if not destructor:
                            raise NativeContractError('Native reader has no deleting destructor')
                        ct.CFUNCTYPE(None, ct.c_void_p, ct.c_int32)(destructor)(pointer, 1)
                except Exception as error:
                    errors.append(error)
        state, self._mpg123_state = self._mpg123_state, None
        if state is not None:
            for cleanup in (
                    lambda: _close_mpg123_decoder(state['library'], state['decoder']),
                    state['file_reader'].close,
                    lambda: state['library'].mpg123_delete(state['decoder'])):
                try:
                    cleanup()
                except Exception as error:
                    errors.append(error)
        stream, self._soundfile_state = self._soundfile_state, None
        if stream is not None:
            try:
                stream['source'].close()
            except Exception as error:
                errors.append(error)
        audio_stream, self._audioread_state = self._audioread_state, None
        if audio_stream is not None:
            try:
                audio_stream['source'].close()
            except Exception as error:
                errors.append(error)
        if errors:
            raise NativeContractError('Audio reader cleanup failed') from errors[0]

    def __del__(self):
        try:
            self.close()
        except Exception:
            # Interpreter-Shutdown darf keine nativen Fehler weiterreichen.
            pass

    def _open_fallback(self):
        """Nutze HPG-Decoder ohne den vollständigen Track in RAM zu laden."""
        import soundfile as sf
        import soxr

        source_rate = source_channels = source_frames = bit_depth = None
        source = None
        try:
            info = sf.info(str(self.path))
            source_rate, source_channels, source_frames = int(info.samplerate), int(info.channels), int(info.frames)
            subtype = str(info.subtype)
            bit_depth = next((bits for marker, bits in (
                ('PCM_U8', 8), ('PCM_16', 16), ('PCM_24', 24),
                ('PCM_32', 32), ('FLOAT', 32), ('DOUBLE', 64)) if marker in subtype), 0)
            if not 0 < source_rate <= 384000 or not 1 <= source_channels <= 32 or source_frames < 1:
                raise NativeContractError('Unsupported fallback audio dimensions')
            if source_frames > source_rate * MAX_SECONDS:
                raise NativeContractError('Native reader duration exceeded')
            frame_offset = round(self.start_seconds * source_rate)
            window_frames = min(math.ceil(self.max_seconds * source_rate),
                                source_frames - frame_offset)
            if window_frames < 1:
                raise NativeContractError('Fallback audio window starts beyond source')
            source = sf.SoundFile(str(self.path))
            if int(source.samplerate) != source_rate or int(source.channels) != source_channels:
                raise NativeContractError('Fallback decoder metadata mismatch')
            source.seek(frame_offset)
            output_channels = 1 if source_channels > 2 else source_channels
            expected_output_frames = _ceil_resampled_frames(window_frames, source_rate)
            self.frames = min(expected_output_frames, math.ceil(self.max_seconds * RATE))
            stream_resampler = (soxr.ResampleStream(
                source_rate, RATE, output_channels, dtype='float32', quality='HQ')
                if source_rate != RATE else None)
            backend = ('hpg-libsndfile-mono-downmix-44100' if source_channels > 2 else
                       'hpg-libsndfile-soxr-hq-44100' if source_rate != RATE else
                       'hpg-libsndfile-pcm16-44100' if bit_depth != 16 else
                       'hpg-libsndfile')
            self._soundfile_state = dict(
                source=source, source_rate=source_rate, source_channels=source_channels,
                channels=output_channels, frame_offset=frame_offset, window_frames=window_frames,
                source_read=0, resampler=stream_resampler, resampler_factory=soxr.ResampleStream,
                pending=np.empty((0, output_channels), np.float32), position=0, generated=0,
                eof=False, expected_output_frames=expected_output_frames,
                complete_window=(frame_offset+window_frames == source_frames),
            )
            self.source_rate = source_rate
            self.source_channels = source_channels
            self.channels = output_channels
            self.bit_depth = bit_depth
            self.source_frames = source_frames
            self.decoder = None
            self.read_function = None
            self.backend = backend
            return
        except NativeContractError:
            if source is not None:
                source.close()
            raise
        except Exception:
            if source is not None:
                source.close()
                source = None
            # Audioread zählt und streamt Decoderformate, die libsndfile nicht abdeckt.
            try:
                source_rate, source_channels, source_frames = self._count_audioread_frames()
                if (not 0 < source_rate <= 384000 or not 1 <= source_channels <= 32
                        or source_frames < 1 or source_frames > source_rate * MAX_SECONDS):
                    raise NativeContractError('Unsupported fallback audio dimensions')
                frame_offset = round(self.start_seconds * source_rate)
                window_frames = min(math.ceil(self.max_seconds * source_rate),
                                    source_frames - frame_offset)
                if window_frames < 1:
                    raise NativeContractError('Fallback audio window starts beyond source')
                output_channels = 1 if source_channels > 2 else source_channels
                expected_output_frames = _ceil_resampled_frames(window_frames, source_rate)
                self.frames = min(expected_output_frames, math.ceil(self.max_seconds * RATE))
                source = self._audioread_source(self.path)
                if (int(source.samplerate) != source_rate
                        or int(source.channels) != source_channels):
                    source.close()
                    source = None
                    raise NativeContractError('Audioread source changed between passes')
                resampler = (soxr.ResampleStream(
                    source_rate, RATE, output_channels, dtype='float32', quality='HQ')
                    if source_rate != RATE else None)
                backend = ('hpg-audioread-mono-downmix-44100' if source_channels > 2 else
                           'hpg-audioread-soxr-hq-44100' if source_rate != RATE else
                           'hpg-audioread-pcm16-44100')
                self._audioread_state = dict(
                    source=source, iterator=iter(source), source_rate=source_rate,
                    source_channels=source_channels, channels=output_channels,
                    frame_offset=frame_offset, window_frames=window_frames, source_read=0,
                    pending=np.empty((0, source_channels), np.float32), source_eof=False,
                    empty_blocks=0,
                    resampler=resampler, resampler_factory=soxr.ResampleStream,
                    pending_output=np.empty((0, output_channels), np.float32),
                    position=0, generated=0, eof=False,
                    expected_output_frames=expected_output_frames,
                    complete_window=(frame_offset+window_frames == source_frames),
                )
                self._skip_audioread_frames(frame_offset)
                bit_depth = 0
                self.source_rate = source_rate
                self.source_channels = source_channels
                self.channels = output_channels
                self.bit_depth = bit_depth
                self.source_frames = source_frames
                self.decoder = None
                self.read_function = None
                self.backend = backend
                return
            except NativeContractError:
                if source is not None:
                    source.close()
                self._audioread_state = None
                raise
            except Exception as error:
                if source is not None:
                    source.close()
                self._audioread_state = None
                raise NativeContractError('No HPG decoder accepts source format') from error

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
        if self.backend in {'rekordbox-mpg123-stream',
                            'rekordbox-mpg123-soxr-hq-stream'}:
            return self._read_mpg123_stream(start, count)
        if not self.backend.startswith('rekordbox-builtin'):
            if self._audioread_state is not None:
                return self._read_audioread_stream(start, count)
            if self._soundfile_state is not None:
                return self._read_soundfile_stream(start, count)
            raise NativeContractError('No active fallback audio stream')
        # Native Decoder schreiben vier Float-Lanes pro Frame, nicht zwei.
        samples = np.full((count, 4), np.nan, dtype=np.float32)
        self.read_function(self.decoder, self._native_start_frame + start,
                           samples.ctypes.data, count)
        if not np.isfinite(samples[:, :self.channels]).all():
            raise NativeContractError('Incomplete or nonfinite native audio')
        left = np.ascontiguousarray(samples[:, 0])
        right = np.ascontiguousarray(samples[:, 1]) if self.channels == 2 else left.copy()
        return left, right

    def metadata(self):
        if _source_identity(self.path) != self.identity:
            raise NativeContractError('Source changed during native reading')
        return dict(contract=CONTRACT, source_sample_rate=self.source_rate,
                    source_channels=self.source_channels, output_channels=self.channels,
                    source_bit_depth=self.bit_depth,
                    source_frames=self.source_frames,
                    output_sample_rate=RATE, output_frames=self.frames,
                    backend=self.backend)


class _WinMpg123File:
    """Read-only Unicode Windows file handle passed to libmpg123 callbacks."""
    def __init__(self, path):
        from ctypes import wintypes as wt

        self.kernel = ct.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD,
            ct.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
        self.kernel.CreateFileW.restype = wt.HANDLE
        self.kernel.ReadFile.argtypes = [wt.HANDLE, ct.c_void_p, wt.DWORD,
            ct.POINTER(wt.DWORD), ct.c_void_p]
        self.kernel.ReadFile.restype = wt.BOOL
        self.kernel.SetFilePointerEx.argtypes = [wt.HANDLE, ct.c_longlong,
            ct.POINTER(ct.c_longlong), wt.DWORD]
        self.kernel.SetFilePointerEx.restype = wt.BOOL
        self.kernel.CloseHandle.argtypes = [wt.HANDLE]
        self.kernel.CloseHandle.restype = wt.BOOL
        self.handle = self.kernel.CreateFileW(str(path), 0x80000000,
            0x00000001, None, 3, 0x08000000, None)
        if self.handle == wt.HANDLE(-1).value:
            raise NativeContractError('Unable to open MP3 source read-only') from ct.WinError(ct.get_last_error())

    def close(self):
        handle = self.handle
        if handle and handle != ct.c_void_p(-1).value:
            if not self.kernel.CloseHandle(handle):
                raise NativeContractError(
                    'Unable to close MP3 source handle read-only'
                ) from ct.WinError(ct.get_last_error())
            self.handle = None


def _source_channel_count(path):
    """Bestimme Mono/Stereo ohne Audio-Decode, auch für AAC/MP4-Metadaten."""
    try:
        import soundfile as sf
        channels = sf.info(str(path)).channels
    except Exception:
        channels = None
    if type(channels) is int and 1 <= channels <= 32:
        return channels
    try:
        import mutagen
        audio = mutagen.File(str(path), easy=False)
        info = getattr(audio, 'info', None)
        channels = getattr(info, 'channels', None)
    except Exception:
        channels = None
    return channels if type(channels) is int and 1 <= channels <= 32 else None


class NativeAudioStream:
    """SoundFile-artige Leseansicht über Rekordbox-Reader und HPG-Fallback."""
    subtype = 'PCM_16'

    def __init__(self, path, *, duration=None, offset=0.0, use_rekordbox=True):
        path = Path(path)
        suffix = path.suffix.lower()
        if type(use_rekordbox) is not bool:
            raise NativeContractError('Invalid native reader selection')
        if (duration is not None
                and (type(duration) not in (int, float) or not math.isfinite(duration)
                     or duration <= 0)):
            raise NativeContractError('Invalid audio-reader duration')
        if (type(offset) not in (int, float) or not math.isfinite(offset)
                or offset < 0):
            raise NativeContractError('Invalid audio-reader offset')
        remaining = MAX_SECONDS - float(offset)
        if remaining <= 0:
            raise NativeContractError('Invalid audio-reader start/duration')
        limit = remaining if duration is None else min(remaining, float(duration))
        if limit <= 0:
            raise NativeContractError('Invalid audio-reader start/duration')
        self.image = None
        native_selection = use_rekordbox
        if use_rekordbox and suffix == '.mp3':
            try:
                self.image = _reader_image()
            except Exception:
                self.image = None
        elif use_rekordbox and suffix in NATIVE_REKORDBOX_READER_EXTENSIONS:
            optional_codec = suffix in ('.flac', '.fla', '.m4a', '.mp4', '.aac')
            channels = _source_channel_count(path)
            if optional_codec and channels not in (None, 1, 2):
                # Bekannte Mehrkanalquellen direkt im HPG-Reader downmixen;
                # nach erfolgreichem nativen Open ist Ownership nicht belegt.
                native_selection = False
            elif optional_codec or channels in (1, 2):
                try:
                    # Optional-Codec-Vertrag kann unbekannte Kanäle intern
                    # prüfen und kontrolliert auf den HPG-Reader zurückfallen.
                    self.image = _reader_image()
                except Exception:
                    self.image = None
            if self.image is None and suffix != '.mp3':
                # Vor dem Anlegen eines nativen Decoders ist HPG-Fallback
                # sicher. Das gilt auch für WAV/AIFF, wenn das Rekordbox-Abbild
                # nicht bereitgestellt werden kann.
                native_selection = False
            if (suffix in ('.wav', '.wave', '.aif', '.aiff')
                    and channels not in (1, 2)):
                # Der native Beatpfad verarbeitet nur Mono/Stereo. Mehrkanal-
                # und nicht lesbare Kanalmetadaten nutzen den HPG-Decoder.
                native_selection = False
        def mp3_fallback():
            try:
                return NativeAudioReader(None, path, max_seconds=limit,
                    start_seconds=offset, use_rekordbox=True)
            except Exception:
                return NativeAudioReader(None, path, max_seconds=limit,
                    start_seconds=offset, use_rekordbox=False)

        try:
            self.reader = NativeAudioReader(self.image, path, max_seconds=limit,
                                            start_seconds=offset,
                                            use_rekordbox=native_selection)
        except NativeContractError:
            # Native Decoder ohne belegten Freigabepfad bleiben bis zum Ende
            # dieses Kindprozesses resident. HPG kann dieselbe Quelle danach
            # neu und read-only dekodieren; fehlende Unterstützung liefert
            # weiterhin einen kontrollierten Fehler.
            if suffix not in NATIVE_REKORDBOX_FACTORIES:
                raise
            if suffix == '.mp3' and native_selection:
                # Erst Rekordbox' mpg123-Bundle, HPG-Reader als letzte Wahl.
                self.reader = mp3_fallback()
            else:
                self.reader = NativeAudioReader(None, path, max_seconds=limit,
                    start_seconds=offset, use_rekordbox=False)
        except Exception:
            if suffix != '.mp3':
                raise
            # Ein nativer MP3-Factoryfehler bleibt im Analysekind isoliert;
            # danach steht Rekordbox' gebündeltes mpg123 als Fallback bereit.
            self.reader = mp3_fallback()
        self.frames = min(self.reader.frames, math.ceil(limit * RATE))
        self.samplerate = RATE
        self.channels = self.reader.channels
        self.backend = self.reader.backend
        self.position = 0
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
        return False

    def close(self):
        """Gib Fallbackpuffer frei und schließe einen aktiven mpg123-Decoder."""
        if self.closed:
            return
        try:
            self.reader.close()
        finally:
            self.closed = True

    def __len__(self):
        return self.frames

    def tell(self):
        if self.closed:
            raise NativeContractError('Audio reader is closed')
        return self.position

    def seek(self, frame):
        if self.closed or type(frame) is not int or not 0 <= frame <= self.frames:
            raise NativeContractError('Invalid audio-reader seek')
        self.position = frame
        return frame

    def read(self, count, *, dtype, always_2d):
        if (self.closed or dtype not in ('float32', 'int16') or always_2d is not True
                or type(count) is not int or count < 0):
            raise NativeContractError('Invalid audio-reader request')
        start = self.position
        end = min(self.frames, start + count)
        blocks = []
        position = self.position
        while position < end:
            amount = min(512, end-position)
            left, right = self.reader.read(position, amount)
            blocks.append(np.column_stack((left, right))[:, :self.channels])
            position += amount
        samples = np.concatenate(blocks, axis=0) if blocks else np.empty(
            (0, self.channels), dtype=np.float32)
        self.position = end
        self.backend = self.reader.backend
        if len(samples) != end-start:
            raise NativeContractError('Incomplete decoded audio window')
        if _source_identity(self.reader.path) != self.reader.identity:
            raise NativeContractError('Source changed during native audio read')
        if dtype == 'int16':
            return np.clip(np.rint(samples * 32768.0), -32768, 32767).astype(np.int16)
        return np.ascontiguousarray(samples, dtype=np.float32)

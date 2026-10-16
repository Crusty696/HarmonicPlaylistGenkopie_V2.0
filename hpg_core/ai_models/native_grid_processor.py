"""Native DSP-Voranalyse und Endgrid im selben begrenzten Reader-Prozess."""
import ctypes as ct
import tempfile
import numpy as np
from .native_phrase_worker import NativeContractError
from .native_grid_refinement_worker import Triple


class NativeGridProcessor:
    def __init__(self, image, reader):
        frames = reader.frames
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
        storage = ct.create_string_buffer(24)
        image.function(0x11db2e0, ct.c_void_p, ct.c_void_p, ct.c_int32)(storage, 2)
        initialize = image.function(0x11db350, ct.c_ubyte, ct.c_void_p, ct.c_ubyte,
            ct.c_int32, ct.c_int32, ct.c_uint32, ct.c_ubyte, ct.c_ubyte, ct.c_ubyte)
        # Beatverarbeitung aktiv, optionale Zusatzanalysen aus; kein App-Start.
        if not initialize(storage, 0, 44100, frames, 32, 0, 0, 0):
            raise NativeContractError('Native grid initialization failed')
        feed = image.function(0x11db540, ct.c_ubyte, ct.c_void_p,
                              ct.c_void_p, ct.c_void_p, ct.c_int32)
        for start in range(0, frames, 512):
            left, right = reader.read(start, min(512, frames-start))
            left, right = left * np.float32(32768), right * np.float32(32768)
            if not feed(storage, left.ctypes.data, right.ctypes.data, len(left)):
                raise NativeContractError('Native grid feed rejected')
        self.storage = storage
        self.image = image
        self.diagnostic_dir = diagnostic_dir
        self.folder_callback = research_folder
        self.initial_bpm = image.function(0x11db6c0, ct.c_int32, ct.c_void_p)(storage)
        self.initial_count = image.function(0x11db6f0, ct.c_int32, ct.c_void_p)(storage)
        self.window_start = image.function(0x11db770, ct.c_int32, ct.c_void_p)(storage)
        self.stored_mode = bool(image.function(0x11db7d0, ct.c_ubyte, ct.c_void_p)(storage))
        if not 0 < self.initial_bpm <= 100000 or not 0 < self.initial_count <= 6000:
            raise NativeContractError('Native initial grid unavailable')

    def refine(self, grid, bpm, selected):
        image, storage = self.image, self.storage
        image.function(0x11db7a0, None, ct.c_void_p, ct.c_ubyte)(storage, selected)
        triples = (Triple * len(grid))(*(Triple(r['pos'], r['numBar'], r['bpm']) for r in grid))
        refine = image.function(0x11db800, ct.c_ubyte, ct.c_void_p, ct.c_int32,
            ct.c_int32, ct.c_int32, ct.POINTER(Triple), ct.c_int32, ct.c_int32)
        refine(storage, 0, self.initial_count, self.initial_bpm, triples, len(grid), bpm)
        final_bpm = image.function(0x11db860, ct.c_int32, ct.c_void_p)(storage)
        count = image.function(0x11db890, ct.c_int32, ct.c_void_p)(storage)
        if not 0 < count <= 6000 or not 0 < final_bpm <= 100000:
            raise NativeContractError('Native final grid unavailable')
        output = (Triple * count)()
        image.function(0x11db8c0, None, ct.c_void_p, ct.POINTER(Triple))(storage, output)
        rows = [dict(pos=r.pos, numBar=r.numBar, bpm=r.bpm) for r in output]
        return rows, final_bpm

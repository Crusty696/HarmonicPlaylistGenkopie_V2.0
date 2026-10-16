"""Rekordbox-Modellaufruf und Beatdecoder im isolierten Forschungsprozess.

Native WAV/AIFF-Decoder, Moduswahl und Original-Grenzkorrekturen.
Musikalische Gleichwertigkeit bleibt ein getrennter Nachweis.
"""
import ctypes as ct
import hashlib
import json
from pathlib import Path

import numpy as np

from .native_phrase_worker import NativeImage, NativeContractError, EXE, SHA256, _source_identity
from .beat_predictor import _hashes
from .native_audio_reader import NativeAudioReader, bind_reader_imports
from .native_beat_selection import select_model
from .native_grid_processor import NativeGridProcessor

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


def validate_model_rows(values, window_frames):
    # Ein Modell8-Ereignis darf genau auf dem Ende des 60s-Fensters liegen.
    # Es ist weiterhin an die Quelldauer gebunden, nachdem der Start addiert ist.
    if (values.ndim != 2 or values.shape[1] != 2
            or not np.isfinite(values).all() or np.any(values[:, 0] < 0)
            or np.any(values[:, 0] > window_frames / 44100)
            or np.any(np.diff(values[:, 0]) <= 0)
            or not np.isin(values[:, 1], [1, 2, 3, 4]).all()):
        raise NativeContractError('Invalid native pipeline beats')
    return values.tolist()


def _handle(payload):
    global _used
    if _used:
        raise NativeContractError('Single-use native pipeline required')
    _used = True
    request = json.loads(payload)
    if type(request) is not dict or set(request) != {'path', 'source_identity', 'configuration'}:
        raise NativeContractError('Invalid pipeline request')
    path = Path(request['path'])
    if not path.is_absolute() or _source_identity(path) != request['source_identity']:
        raise NativeContractError('Invalid pipeline source')
    mode = request['configuration']
    if type(mode) is not int or mode not in (2, 3, 4):
        raise NativeContractError('Unsupported native configuration')
    image = NativeImage()
    bind_reader_imports(image)
    library = _bind_tensorflow(image)
    if image.function(0x2998258, ct.c_int32)() != 0:
        raise NativeContractError('Native standard-stream initialization failed')
    reader = NativeAudioReader(image, path)
    processor = NativeGridProcessor(image, reader)
    selection = select_model(mode, processor.stored_mode)
    model_id = selection['model_id']
    directory = EXE.parent / 'models' / 'detect_beat' / model_id
    hashes = _hashes(directory, model_id)
    frames = reader.frames
    from .native_beat_boundaries import run as correct_boundaries, VERSION as boundary_contract
    grid, bpm_hundredths, rows, coverage = correct_boundaries(image, reader, selection, processor.window_start)
    grid, final_bpm = processor.refine(grid, int(bpm_hundredths), selection['chunked'])
    verification = None
    if not selection['chunked']:
        # Modell8 beobachtet nur 60 Sekunden. Für unabhängige Audiofenster
        # liefert der originale Modell7-Lauf zusätzlich die ganze Beatfolge.
        # Das ausgewählte Endgrid und seine Taktnummern bleiben unverändert.
        verification_hashes = _hashes(EXE.parent/'models'/'detect_beat'/'model7', 'model7')
        _, _, verification_rows, verification_coverage = correct_boundaries(
            image, reader, select_model(4), 0)
        verification = dict(model_id='model7', model_hashes=verification_hashes,
                            beats=verification_rows, coverage=verification_coverage)
    reader_metadata = reader.metadata()
    if _source_identity(path) != request['source_identity']:
        raise NativeContractError('Source changed during native pipeline')
    return json.dumps(dict(contract='rb-7.2.19-native-beat-pipeline-research-v4',
        executable_sha256=SHA256, tensorflow_sha256=TF_SHA256, model_id=model_id,
        model_hashes=hashes, verified=False, beats=rows, grid=grid, bpm=final_bpm/100., selection=selection, reader=reader_metadata,
        input_convention='rekordbox-builtin-planar-float32', frames=frames,
        chunked=selection['chunked'], boundary_contract=boundary_contract,
        model_coverage=coverage, verification=verification),
        allow_nan=False).encode('utf8')


def handle(payload):
    try:
        return _handle(payload)
    except Exception as error:
        # Python-Vertragsfehler nicht als nativen Prozessabsturz verschleiern.
        return json.dumps(dict(status='unavailable', reason=f'{type(error).__name__}: {error}')).encode()

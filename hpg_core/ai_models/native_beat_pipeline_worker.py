"""Rekordbox-Modellaufruf und Beatdecoder im isolierten HPG-Forschungsprozess.

Native WAV/AIFF-Reader und direkter MP3-Bundledecoder, Moduswahl und
Original-Grenzkorrekturen. Die Rekordbox-App wird nicht gestartet.
Musikalische Gleichwertigkeit bleibt ein getrennter Nachweis.
"""
import ctypes as ct
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .native_phrase_worker import NativeImage, NativeContractError, EXE, SHA256, _source_identity
from .beat_predictor import _hashes
from .native_audio_reader import NativeAudioReader, bind_reader_imports
from .native_beat_selection import (
    MAX_NATIVE_BEAT_WINDOW_SECONDS, select_model,
)
from .native_grid_processor import NativeGridProcessor

TF_SHA256 = 'b158ff8fdd75723871c5966ec8c1f7c8cda888c9d836365e3b1976966c718424'
_used = False
_SAMPLE_RATE = 44100
_BEAT_PHASE_TOLERANCE_SECONDS = .006
_MODEL_TIME_QUANTUM_SECONDS = .01


class _ReaderWindow:
    """Begrenzt native Modellaufrufe auf Quellfenster ohne Audiokopie."""
    def __init__(self, reader, start_frame, end_frame):
        if (type(start_frame) is not int or type(end_frame) is not int
                or not 0 <= start_frame < end_frame <= reader.frames):
            raise NativeContractError('Invalid bounded beat window')
        self.reader = reader
        self.start_frame = start_frame
        self.frames = end_frame - start_frame
        self.path = reader.path
        self.owner = reader.owner

    def read(self, start, count):
        if (type(start) is not int or type(count) is not int or start < 0
                or not 1 <= count <= 512 or start + count > self.frames):
            raise NativeContractError('Invalid bounded beat read')
        return self.reader.read(self.start_frame + start, count)


def _window_ranges(frames):
    window_frames = MAX_NATIVE_BEAT_WINDOW_SECONDS * _SAMPLE_RATE
    if frames <= window_frames:
        return [(0, frames)]
    # Zehn Beats bei der bestehenden Untergrenze von 55 BPM. Davon genügen
    # acht für stable_model_window, mit einem Beat Rand je Seite.
    overlap_frames = math.ceil(10 * 60 / 55 * _SAMPLE_RATE)
    ranges = []
    start = 0
    while start < frames:
        end = min(frames, start + window_frames)
        ranges.append((start, end))
        if end == frames:
            break
        start = end - overlap_frames
    return ranges


def _join_overlapping_rows(previous_rows, local_rows, start_frame, previous_end_frame,
                           *, grid_rows):
    """Stitcht nur eindeutige Beat-/Taktfolgen; Nahtabweichung sperrt Gesamtgrid."""
    start_s = start_frame / _SAMPLE_RATE
    previous_end_s = previous_end_frame / _SAMPLE_RATE
    if grid_rows:
        current = [dict(row, pos=row['pos'] + start_frame) for row in local_rows]
        time = lambda row: row['pos'] / _SAMPLE_RATE
        position = lambda row: row['pos']
        phase = lambda row: row['numBar']
        tolerance = _BEAT_PHASE_TOLERANCE_SECONDS
    else:
        current = [[row[0] + start_s, row[1]] for row in local_rows]
        time = lambda row: row['pos'] / _SAMPLE_RATE if grid_rows else row[0]
        position = lambda row: row['pos'] if grid_rows else row[0]
        phase = lambda row: row['numBar'] if grid_rows else row[1]
        # Native model activations use a 100-Hz time grid; this tolerance only
        # deduplicates the same observed activation. Final grid stays at 6 ms.
        tolerance = _MODEL_TIME_QUANTUM_SECONDS + 1e-9
    left = [row for row in previous_rows if start_s <= time(row) < previous_end_s]
    right = [row for row in current if start_s <= time(row) < previous_end_s]
    if len(left) < 8 or len(left) != len(right):
        raise NativeContractError('Ambiguous native beat seam coverage')
    for old, new in zip(left, right):
        if (phase(old) != phase(new)
                or abs(time(old) - time(new)) > tolerance):
            raise NativeContractError('Native beat seam phase mismatch')
    # Previous window owns its complete coverage. Keep only new events beyond it.
    return previous_rows + [row for row in current if time(row) >= previous_end_s]


def _join_model8_coverage(previous_rows, local_rows, source_start_frame,
                          overlap_start_frame, overlap_end_frame):
    """Merges model8 observations only when overlapping coverage proves phase."""
    overlap_start = overlap_start_frame / _SAMPLE_RATE
    overlap_end = overlap_end_frame / _SAMPLE_RATE
    if overlap_end <= overlap_start:
        raise NativeContractError('Disconnected model8 coverage cannot establish bar phase')
    source_offset = source_start_frame / _SAMPLE_RATE
    current = [[row[0] + source_offset, row[1]] for row in local_rows]
    left = [row for row in previous_rows if overlap_start <= row[0] < overlap_end]
    right = [row for row in current if overlap_start <= row[0] < overlap_end]
    if len(left) < 8 or len(left) != len(right):
        raise NativeContractError('Ambiguous model8 overlap coverage')
    for old, new in zip(left, right):
        if (old[1] != new[1]
                or abs(old[0] - new[0]) > _MODEL_TIME_QUANTUM_SECONDS + 1e-9):
            raise NativeContractError('Model8 overlap bar phase mismatch')
    # Keep both windows' non-overlap evidence, deduplicate only matched events.
    return previous_rows + [row for row in current
                            if row[0] < overlap_start or row[0] >= overlap_end]


def _constant_grid_bpm(grid):
    if len(grid) < 4:
        raise NativeContractError('Native segment grid too short')
    times = np.asarray([row['pos'] / _SAMPLE_RATE for row in grid], dtype=np.float64)
    beats = np.arange(len(times), dtype=np.float64)
    centered = beats - float(np.mean(beats))
    period = float(np.dot(centered, times - float(np.mean(times)))
                    / np.dot(centered, centered))
    if not math.isfinite(period) or period <= 0:
        raise NativeContractError('Invalid stitched beat period')
    residual = times - (times[0] + beats * period)
    if float(np.max(np.abs(residual))) > _BEAT_PHASE_TOLERANCE_SECONDS:
        raise NativeContractError('Stitched grid exceeds 6-ms phase contract')
    bpm = 60. / period
    if not 55 <= bpm <= 215:
        raise NativeContractError('Stitched BPM outside native range')
    return bpm


def _segmented_pipeline(image, reader, selection, first_processor=None):
    """Process only long sources in bounded overlapping native windows."""
    from .native_beat_boundaries import run as correct_boundaries
    from .native_grid_processor import NativeGridProcessor

    ranges = _window_ranges(reader.frames)
    merged_grid = []
    merged_model_beats = []
    merged_verification_beats = []
    selected_coverage_segments = []
    for index, (start, end) in enumerate(ranges):
        window = _ReaderWindow(reader, start, end)
        processor = (first_processor if index == 0 and first_processor is not None
                     else NativeGridProcessor(image, window))
        grid, bpm_hundredths, model_rows, coverage = correct_boundaries(
            image, window, selection, processor.window_start)
        grid, final_bpm = processor.refine(
            grid, int(bpm_hundredths), selection['chunked'])
        if not 5500 <= int(round(final_bpm)) <= 21500:
            raise NativeContractError('Native segment BPM outside supported range')

        previous_end = ranges[index - 1][1] if index else None
        coverage_frame_range = None
        if not selection['chunked']:
            coverage_start_frame = start + round(coverage['start_s'] * _SAMPLE_RATE)
            coverage_end_frame = start + round(coverage['end_s'] * _SAMPLE_RATE)
            coverage_frame_range = (coverage_start_frame, coverage_end_frame)
        if index:
            merged_grid = _join_overlapping_rows(
                merged_grid, grid, start, previous_end, grid_rows=True)
            if selection['chunked']:
                merged_model_beats = _join_overlapping_rows(
                    merged_model_beats, model_rows, start, previous_end,
                    grid_rows=False)
            else:
                previous_coverage = selected_coverage_segments[-1]
                overlap_start_frame = max(
                    round(previous_coverage['start_s'] * _SAMPLE_RATE),
                    coverage_frame_range[0])
                overlap_end_frame = min(
                    round(previous_coverage['end_s'] * _SAMPLE_RATE),
                    coverage_frame_range[1])
                merged_model_beats = _join_model8_coverage(
                    merged_model_beats, model_rows, start,
                    overlap_start_frame, overlap_end_frame)
        else:
            merged_grid = [dict(row) for row in grid]
            merged_model_beats = [
                [row[0], row[1]] for row in model_rows]
        if not selection['chunked']:
            # Sekunden bleiben abwaertskompatibel; die Addition geschieht in
            # ganzzahligen Quellframes, damit Segmentgrenzen exakt gebunden sind.
            coverage_start_frame, coverage_end_frame = coverage_frame_range
            coverage_start = coverage_start_frame / _SAMPLE_RATE
            coverage_end = coverage_end_frame / _SAMPLE_RATE
            selected_coverage_segments.append(dict(start_s=coverage_start,
                                                   end_s=coverage_end))

        if not selection['chunked']:
            _, _, verification_rows, verification_coverage = correct_boundaries(
                image, window, select_model(4), 0)
            if (verification_coverage['start_s'] != 0.
                    or verification_coverage['end_s'] < (window.frames - 1) / _SAMPLE_RATE - 1e-9):
                raise NativeContractError('Incomplete model7 verification window')
            if index:
                merged_verification_beats = _join_overlapping_rows(
                    merged_verification_beats, verification_rows, start,
                    previous_end, grid_rows=False)
            else:
                merged_verification_beats = [list(row) for row in verification_rows]

    merged_grid.sort(key=lambda row: row['pos'])
    if any(right['numBar'] != left['numBar'] % 4 + 1
           for left, right in zip(merged_grid, merged_grid[1:])):
        raise NativeContractError('Stitched native bar positions are discontinuous')
    bpm = _constant_grid_bpm(merged_grid)
    model_coverage = (dict(start_s=0., end_s=(reader.frames - 1) / _SAMPLE_RATE)
                      if selection['chunked'] else selected_coverage_segments[0])
    verification = None
    if not selection['chunked']:
        verification = dict(
            model_id='model7',
            model_hashes=_hashes(EXE.parent/'models'/'detect_beat'/'model7', 'model7'),
            beats=merged_verification_beats,
            coverage=dict(start_s=0., end_s=(reader.frames - 1) / _SAMPLE_RATE),
        )
    return dict(grid=merged_grid, bpm=bpm, beats=merged_model_beats,
                model_coverage=model_coverage,
                model_coverage_segments=(selected_coverage_segments
                    if not selection['chunked'] else None),
                verification=verification)


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
    try:
        import soundfile as sf
        source_channels = int(sf.info(str(path)).channels)
    except Exception:
        source_channels = None
    # Rekordbox' privater PCM-Reader akzeptiert nur Mono/Stereo. Breitere
    # Layouts nutzen begrenztes HPG-Decoding und denselben Mono-Downmix wie DSP.
    reader = NativeAudioReader(image, path,
        use_rekordbox=source_channels is None or source_channels <= 2)
    frames = reader.frames
    from .native_beat_boundaries import run as correct_boundaries, VERSION as boundary_contract
    if frames <= MAX_NATIVE_BEAT_WINDOW_SECONDS * _SAMPLE_RATE:
        # Keep existing one-window processing and its evidence shape unchanged.
        processor = NativeGridProcessor(image, reader)
        selection = select_model(mode, processor.stored_mode)
        segmented = None
    else:
        first_end = min(frames, MAX_NATIVE_BEAT_WINDOW_SECONDS * _SAMPLE_RATE)
        first_window = _ReaderWindow(reader, 0, first_end)
        processor = NativeGridProcessor(image, first_window)
        selection = select_model(mode, processor.stored_mode)
        segmented = _segmented_pipeline(image, reader, selection, processor)
    model_id = selection['model_id']
    directory = EXE.parent / 'models' / 'detect_beat' / model_id
    hashes = _hashes(directory, model_id)
    if segmented is None:
        grid, bpm_hundredths, rows, coverage = correct_boundaries(
            image, reader, selection, processor.window_start)
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
    else:
        grid, rows = segmented['grid'], segmented['beats']
        final_bpm, verification = segmented['bpm'], segmented['verification']
        coverage = segmented['model_coverage']
    reader_metadata = reader.metadata()
    if _source_identity(path) != request['source_identity']:
        raise NativeContractError('Source changed during native pipeline')
    payload_result = dict(contract='rb-7.2.19-native-beat-pipeline-research-v10',
        executable_sha256=SHA256, tensorflow_sha256=TF_SHA256, model_id=model_id,
        model_hashes=hashes, verified=False, beats=rows, grid=grid,
        bpm=final_bpm if segmented is not None else final_bpm/100., selection=selection, reader=reader_metadata,
        input_convention=f"{reader.backend}-planar-float32", frames=frames,
        chunked=selection['chunked'], boundary_contract=boundary_contract,
        model_coverage=coverage, verification=verification)
    if segmented is not None and segmented['model_coverage_segments'] is not None:
        payload_result['model_coverage_segments'] = segmented['model_coverage_segments']
    return json.dumps(payload_result, allow_nan=False).encode('utf8')


def handle(payload):
    try:
        return _handle(payload)
    except Exception as error:
        # Python-Vertragsfehler nicht als nativen Prozessabsturz verschleiern.
        return json.dumps(dict(status='unavailable', reason=f'{type(error).__name__}: {error}')).encode()

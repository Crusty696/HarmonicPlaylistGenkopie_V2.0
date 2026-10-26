"""HPG-Vertrag für den isolierten nativen Phrasengenerator.

Originalmusik bleibt am Quellort. Der Owner beendet den Einmal-Prozess auch
nach erfolgreicher Antwort; native FLS-Zeiger bleiben bis dahin resident.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time

from .native_phrase_worker import (
    CONTRACT_VERSION, EXE, SHA256, configured_native_flags, valid_native_flags,
    NATIVE_BAR_POSITION_MAP,
)
from .native_beat_selection import (
    MAX_NATIVE_TRACK_JOB_SECONDS, native_track_job_timeout_seconds,
)
from .native_key import KEY_MAPPING_VERSION, native_key_index
from .reader_contract import READER_BACKENDS, source_duration_tolerance

_IDENTITY_LOCK = threading.Lock()
_IDENTITY_SIGNATURE = None
_IDENTITY_DIGEST = None


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _normalize_grid_origin(times, positions, *, bpm):
    """Ergänzt Takte vor dem ersten Treffer bis zum nativen Offsetbereich.

    Der native Generator nimmt nur einen gerundeten Startoffset unter einer
    Beatperiode an. Ein verifiziertes Grid kann wegen Stille, Rundung oder
    eines späten ersten Treffers davor liegen. Fehlende Ticks werden rückwärts
    aus derselben Periode und Taktphase abgeleitet; vorhandene Gridpunkte
    bleiben erhalten.
    """
    if (not times or not positions or not _finite_number(bpm) or bpm <= 0
            or type(times[0]) not in (int, float) or not math.isfinite(times[0])
            or type(positions[0]) is not int or not 1 <= positions[0] <= 4):
        return times, positions, 0
    period = 60.0 / bpm
    bpm_hundredths = int(math.floor(bpm * 100 + .5))
    native_period_ms = 6000000.0 / bpm_hundredths
    prepend_count = max(0, int(math.floor(times[0] / period)))
    while prepend_count <= 120001:
        candidate_offset = times[0] - prepend_count * period
        offset_ms = int(math.floor(candidate_offset * 1000 + .5))
        if 0 <= offset_ms < native_period_ms:
            break
        prepend_count += 1
    if prepend_count > 120001:
        return times, positions, 0
    if prepend_count == 0:
        return times, positions, 0
    prefix_times = [times[0] - step * period
                    for step in range(prepend_count, 0, -1)]
    if prefix_times and -.006 <= prefix_times[0] < 0:
        prefix_times[0] = 0.0
    prefix_positions = [(positions[0] - step - 1) % 4 + 1
                        for step in range(prepend_count, 0, -1)]
    return prefix_times + times, prefix_positions + positions, prepend_count


def enabled():
    """Nativer Pfad für die gepinnte EXE; explizit mit 0 abschaltbar."""
    return os.environ.get('HPG_NATIVE_PHRASE', '1') == '1'


def identity():
    global _IDENTITY_SIGNATURE, _IDENTITY_DIGEST
    active = enabled()
    flags = configured_native_flags()
    try:
        actual = None
        if active:
            executable = EXE.resolve(strict=True)
            stat = executable.stat()
            signature = (str(executable), stat.st_size, stat.st_mtime_ns,
                         stat.st_ctime_ns, getattr(stat, 'st_ino', 0))
            with _IDENTITY_LOCK:
                if signature != _IDENTITY_SIGNATURE:
                    with executable.open('rb') as stream:
                        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                    after = executable.stat()
                    after_signature = (str(executable), after.st_size,
                        after.st_mtime_ns, after.st_ctime_ns,
                        getattr(after, 'st_ino', 0))
                    if after_signature != signature:
                        return dict(contract=CONTRACT_VERSION,
                            key_mapping=KEY_MAPPING_VERSION, enabled=active,
                            expected_sha256=SHA256, actual_sha256=None,
                            native_flags=list(flags) if flags is not None else None)
                    _IDENTITY_SIGNATURE, _IDENTITY_DIGEST = signature, digest
                actual = _IDENTITY_DIGEST
    except OSError:
        actual = None
    return dict(contract=CONTRACT_VERSION, key_mapping=KEY_MAPPING_VERSION,
                enabled=active, expected_sha256=SHA256,
                actual_sha256=actual,
                native_flags=list(flags) if flags is not None else None)


def generate_phrases(path, *, beat_times, beat_positions, bpm, duration,
                     verified_grid, key_index, cancel_event=None,
                     timeout_s=MAX_NATIVE_TRACK_JOB_SECONDS,
                     transport=None, native_flags=None):
    """Erzeugt native Kandidaten auf einem ausdrücklich bestätigten Eingangsgrid.

    Gibt keine neue Gridfreigabe aus. Header[6] ist die native Schlussgrenze:
    12e95d0 erzeugt sie, 12d9b20 hängt sie an die Startpositionen zur Berechnung
    der Abschnittslängen an, 12f7420 schreibt sie nach Ergebnis+0x18.
    Sie verwendet dasselbe einsbasierte Beatraster wie die Phrasenstarts.
    """
    from hpg_core.ai_models.process_runtime import OwnedModelProcess
    from hpg_core.config import MODEL_PROCESS_MEMORY_LIMIT_BYTES
    from hpg_core.rekordbox_phrases import phrase_label

    unavailable = lambda reason: dict(status='unavailable', reason=reason, phrases=[])
    if verified_grid is not True:
        return unavailable('unverified_input_grid')
    # Der Trackaufruf uebergibt seinen einmal gelesenen Konfigurationsstand;
    # direkte Aufrufer behalten den bisherigen Umgebungsvariablen-Fallback.
    native_flags = (configured_native_flags() if native_flags is None
                    else tuple(native_flags)
                    if type(native_flags) in (list, tuple) else None)
    if not valid_native_flags(native_flags):
        return unavailable('invalid_native_flags')
    if native_flags[0]:
        return unavailable('native_phrase_generation_disabled')
    if (type(beat_times) is not list or type(beat_positions) is not list
            or len(beat_times) != len(beat_positions) or len(beat_times) < 32
            or any(not _finite_number(x) for x in beat_times)
            or any(type(x) is not int or not 1 <= x <= 4 for x in beat_positions)
            or not _finite_number(bpm) or not 0 < bpm <= 1000
            or not _finite_number(duration) or duration <= 0
            or type(key_index) is not int or not 0 <= key_index < 24
            or not _finite_number(timeout_s)
            or not 0 < timeout_s <= MAX_NATIVE_TRACK_JOB_SECONDS):
        return unavailable('invalid_input_contract')
    beat_period = 60.0 / bpm
    if (not 0 <= beat_times[0] < beat_period
            or beat_times[-1] > duration
            or any(right <= left or abs(right-left-beat_period) > .006
                   for left, right in zip(beat_times, beat_times[1:]))
            or any(right != left % 4 + 1 for left, right in zip(beat_positions, beat_positions[1:]))):
        return unavailable('unsupported_grid_geometry')
    bpm_hundredths = int(math.floor(bpm * 100 + .5))
    offset_ms = int(math.floor(beat_times[0] * 1000 + .5))
    # Native Eingabe kann nur Integer-BPM/100 und Integer-Millisekunden.
    # Größere kumulative Abweichungen werden nicht still durchgewunken.
    native_period = 6000.0 / bpm_hundredths
    # Rounden kann einen Offset knapp unter der Beatperiode auf genau eine
    # Periode schieben. Das waere im nativen Raster Phase 0 des Folgebeats,
    # aber ohne passende Rotation von bar_position; deshalb strikt ablehnen.
    if (offset_ms >= native_period * 1000 or
            any(abs(offset_ms / 1000 + index * native_period - stamp) > .006
                for index, stamp in enumerate(beat_times))):
        return unavailable('native_grid_precision_mismatch')
    source = Path(path)
    try:
        source = source.resolve(strict=True)
        before = source.stat()
        identity = [before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                    before.st_dev, before.st_ino]
        request = dict(path=str(source), source_identity=identity, bpm_hundredths=bpm_hundredths,
                       offset_ms=offset_ms, bar_position=beat_positions[0], key_index=key_index,
                       native_flags=list(native_flags))
        if transport is not None:
            result = transport(request, timeout_s=timeout_s)
        else:
            with OwnedModelProcess('hpg_core.ai_models.native_phrase_worker', 'handle',
                                   max_payload_bytes=8*1024*1024,
                                   memory_limit_bytes=MODEL_PROCESS_MEMORY_LIMIT_BYTES) as owner:
                payload = owner.call(json.dumps(request, allow_nan=False).encode('utf8'),
                                     deadline=time.monotonic()+timeout_s, cancel_event=cancel_event)
            result = json.loads(payload)
        after = source.stat()
        if identity != [after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                        after.st_dev, after.st_ino]:
            return unavailable('source_changed')
    except Exception as error:
        return unavailable(type(error).__name__ + ': ' + str(error))
    if not isinstance(result, dict) or result.get('status') != 'ok':
        return unavailable(result.get('reason', 'native_worker_failure') if isinstance(result, dict)
                           else 'invalid_worker_result')
    if (result.get('contract') != CONTRACT_VERSION or result.get('executable_sha256') != SHA256
            or result.get('reader_backend') not in READER_BACKENDS
            or result.get('input_grid') != {key: request[key] for key in
                ('bpm_hundredths', 'offset_ms', 'bar_position', 'key_index')}):
        return unavailable('native_identity_mismatch')
    expected_native_call = dict(
        frames=result.get('frames'), sample_rate=result.get('sample_rate'),
        bpm_hundredths=bpm_hundredths, offset_ms=offset_ms,
        first_downbeat=NATIVE_BAR_POSITION_MAP[beat_positions[0]], key_index=key_index,
        flags=list(native_flags))
    if result.get('native_call') != expected_native_call:
        return unavailable('native_argument_mismatch')
    header, arrays = result.get('header'), result.get('arrays')
    if (type(header) is not list or len(header) != 7 or any(type(x) is not int for x in header)
            or type(arrays) is not dict or not 1 <= header[0] <= 65535
            or header[2] not in (1, 2, 3)
            or header[1] != offset_ms
            or NATIVE_BAR_POSITION_MAP.get(header[3]) != beat_positions[0]):
        return unavailable('invalid_native_header_or_grid_change')
    positions, kinds, fills = (arrays.get(name) for name in ('beat_positions', 'kind', 'fill_in'))
    if (any(type(values) is not list or len(values) != header[0] for values in (positions, kinds, fills))
            or any(type(x) is not int or not 1 <= x <= len(beat_times) for x in positions)
            or any(right <= left for left, right in zip(positions, positions[1:]))
            or any(type(x) is not int or not 1 <= x <= 10 for x in kinds)
            or any(type(x) is not int or x not in (0, 1) for x in fills)):
        return unavailable('invalid_native_phrase_arrays')
    if (type(result.get('sample_rate')) is not int or result['sample_rate'] <= 0
            or type(result.get('frames')) is not int or result['frames'] <= 0
            or abs(result['frames']/result['sample_rate'] - duration) >
                source_duration_tolerance(source, sample_rate=result['sample_rate'])):
        return unavailable('source_duration_mismatch')
    starts = [beat_times[index-1] for index in positions]
    terminal_beat = header[6]
    if not positions[-1] < terminal_beat <= len(beat_times):
        return unavailable('invalid_native_terminal_beat')
    terminal_s = beat_times[terminal_beat-1]
    if not starts[-1] < terminal_s <= duration:
        return unavailable('invalid_native_terminal_time')
    phrases = [dict(start_s=start, end_s=end, kind=kind, mood=header[2], fill=fill,
                    label=phrase_label(header[2], kind))
               for start, end, kind, fill in zip(starts, starts[1:]+[terminal_s], kinds, fills)]
    return dict(status='ok', reason=None, phrases=phrases,
                source='rekordbox_native_phrase_generator', raw_result=result,
                reader_backend=result['reader_backend'],
                terminal_boundary_source='native_terminal_beat', terminal_beat=terminal_beat)


def analyze_track_phrases(path, **parameters):
    """Native Zusatzanalyse darf bei einem Fehler die DSP-Auswertung erhalten."""
    try:
        return _analyze_track_phrases(path, **parameters)
    except Exception as error:
        native_flags = configured_native_flags()
        return dict(version=7, status='unavailable', reason=type(error).__name__,
            source='rekordbox_native_phrase_generator', contract=CONTRACT_VERSION,
            executable_sha256=SHA256, phrases=[], input_grid={},
            terminal_boundary_source='native_terminal_beat', key_source='native_unknown_fallback_zero',
            reader_backend=None,
            native_flags=(list(native_flags) if native_flags is not None else None))


def _analyze_track_phrases(path, *, bpm, duration, first_downbeat, grid_usable,
                         usage_blocked, imported_phrases, reference_grid, grid_source,
                         native_beat_analysis=None,
                         key_note='', key_mode=''):
    """Ein gemeinsamer Aufruf für Fast-/Vollpfad; PSSI behält Vorrang.

    Rekonstruierter nativer Caller verwendet bei unbekanntem Key den Index 0.
    Bekannte Tonarten werden über die ausgelesene native Namenstabelle zugeordnet.
    """
    key_index = native_key_index(key_note, key_mode)
    key_source = ('hpg_key_native_table' if key_index is not None
                  else 'native_unknown_fallback_zero')
    native_flags = configured_native_flags()
    snapshot = dict(version=7, status='skipped', reason='imported_phrases_preferred',
        source='rekordbox_native_phrase_generator', contract=CONTRACT_VERSION,
        executable_sha256=SHA256, phrases=[], input_grid={},
        terminal_boundary_source='native_terminal_beat', key_source=key_source,
        reader_backend=None,
        native_flags=(list(native_flags) if native_flags is not None else None))
    if imported_phrases:
        return snapshot
    if not enabled():
        snapshot.update(status='disabled', reason='disabled_by_configuration')
        return snapshot
    if native_flags is None:
        snapshot.update(status='unavailable', reason='invalid_native_flags')
        return snapshot
    if native_flags[0]:
        snapshot.update(status='disabled', reason='native_phrase_generation_disabled')
        return snapshot
    if usage_blocked or not grid_usable:
        snapshot.update(reason='unverified_or_blocked_grid')
        return snapshot
    if identity()['actual_sha256'] != SHA256:
        snapshot.update(reason='unsupported_native_executable')
        return snapshot
    if grid_source == 'rekordbox':
        times = [point['time'] for point in reference_grid]
        positions = [point['beat'] for point in reference_grid]
        basis = 'verified_rekordbox_grid'
    elif (grid_source == 'audio' and type(native_beat_analysis) is dict
            and native_beat_analysis.get('status') == 'ok'):
        # Die akzeptierte native Analyse liefert bereits die Beatzeiten und
        # Taktpositionen. Eine bestaetigte Audiokorrektur wird nur auf das
        # abgeleitete Eingaberaster angewandt; der native Rohgrid bleibt intakt.
        from .native_beat_alignment import active_anchor
        offset = (native_beat_analysis['audio_alignment']['offset_seconds']
                  if 'audio_alignment' in native_beat_analysis else 0.0)
        native_times = [row['pos'] / 44100.0 + offset
                        for row in native_beat_analysis['grid']]
        native_positions = [row['numBar'] for row in native_beat_analysis['grid']]
        first_native_downbeat = active_anchor(native_beat_analysis)
        if abs(first_native_downbeat - first_downbeat) > .006:
            snapshot.update(status='unavailable', reason='native_anchor_mismatch')
            return snapshot
        valid_rows = [(stamp, position) for stamp, position in
                      zip(native_times, native_positions) if 0.0 <= stamp <= duration]
        times, positions = [row[0] for row in valid_rows], [row[1] for row in valid_rows]
        basis = 'native_verified_audio_grid'
    elif grid_source == 'audio':
        period = 60. / bpm
        # Konstantes, technisch bestätigtes HPG-Raster. Keine neue Messung
        # und kein unabhängiger Nachweis der musikalischen Takt-1-Position.
        first_index = -int(math.floor(first_downbeat / period))
        first_tick = first_downbeat + first_index * period
        count = max(0, int(math.ceil((duration-first_tick) / period)))
        times = [first_tick + index*period for index in range(count)]
        positions = [(first_index+index) % 4 + 1 for index in range(count)]
        basis = 'hpg_verified_constant_grid'
    else:
        # Unbekannte Quellen duerfen nicht still als HPG-Audio-Raster gelten.
        snapshot.update(status='unavailable', reason='unsupported_grid_source')
        return snapshot
    source_beat_count = len(times)
    times, positions, origin_extension_beats = _normalize_grid_origin(times, positions, bpm=bpm)
    from .cue_service import session
    with session() as client:
        result = generate_phrases(path, beat_times=times, beat_positions=positions,
            bpm=bpm, duration=duration, verified_grid=True,
            key_index=0 if key_index is None else key_index,
            timeout_s=native_track_job_timeout_seconds(duration),
            transport=client.native_phrases, native_flags=native_flags)
    snapshot.update(status=result['status'], reason=result['reason'])
    if result['status'] == 'ok':
        snapshot.update(phrases=result['phrases'], input_grid=dict(
            result['raw_result']['input_grid'], basis=basis,
            beat_count=len(times), first_tick_s=times[0], last_tick_s=times[-1],
            terminal_beat=result['terminal_beat'],
            origin_extension_beats=origin_extension_beats,
            source_beat_count=source_beat_count),
            reader_backend=result['reader_backend'])
    try:
        validate_snapshot(snapshot, duration=duration, grid_verified=grid_usable,
                          usage_blocked=usage_blocked)
    except ValueError:
        snapshot.update(status='unavailable', reason='invalid_native_snapshot', phrases=[], input_grid={})
    return snapshot


def validate_snapshot(value, *, duration, grid_verified, usage_blocked):
    """Persistenzvertrag ohne Ausführung oder Laden nativen Codes."""
    if value == {}:
        return
    fields = {'version', 'status', 'reason', 'source', 'contract', 'executable_sha256',
              'phrases', 'input_grid', 'terminal_boundary_source', 'key_source', 'reader_backend',
              'native_flags'}
    if (type(value) is not dict or set(value) != fields
            or type(value['version']) is not int or value['version'] != 7
            or value['source'] != 'rekordbox_native_phrase_generator'
            or value['contract'] != CONTRACT_VERSION or value['executable_sha256'] != SHA256
            or value['terminal_boundary_source'] != 'native_terminal_beat'
            or value['key_source'] not in ('native_unknown_fallback_zero', 'hpg_key_native_table')
            or (value['native_flags'] is not None
                and not valid_native_flags(value['native_flags']))
            or type(value['phrases']) is not list or type(value['input_grid']) is not dict):
        raise ValueError('Invalid native phrase snapshot')
    if value['status'] != 'ok':
        if (value['status'] not in ('disabled', 'skipped', 'unavailable')
                or type(value['reason']) is not str or not value['reason']
                or value['phrases'] or value['input_grid'] or value['reader_backend'] is not None):
            raise ValueError('Invalid native phrase failure')
        return
    if (value['native_flags'] is None or value['native_flags'][0]
            or value['reason'] is not None or not grid_verified or usage_blocked
            or value['reader_backend'] not in READER_BACKENDS):
        raise ValueError('Native phrases require usable verified grid')
    from ..rekordbox_phrases import phrase_label
    phrases, grid = value['phrases'], value['input_grid']
    keys = {'bpm_hundredths', 'offset_ms', 'bar_position', 'key_index', 'basis',
            'beat_count', 'first_tick_s', 'last_tick_s', 'terminal_beat',
            'origin_extension_beats', 'source_beat_count'}
    if (set(grid) != keys or grid['basis'] not in
            ('verified_rekordbox_grid', 'hpg_verified_constant_grid',
             'native_verified_audio_grid')
            or any(type(grid[key]) is not int for key in
                ('bpm_hundredths', 'offset_ms', 'bar_position', 'key_index', 'beat_count', 'terminal_beat',
                 'origin_extension_beats', 'source_beat_count'))
            or not 1 <= grid['bpm_hundredths'] <= 100000
            or not 0 <= grid['offset_ms'] <= 6000000 / grid['bpm_hundredths']
            or not 1 <= grid['bar_position'] <= 4 or not 0 <= grid['key_index'] < 24
            or (value['key_source'] == 'native_unknown_fallback_zero' and grid['key_index'] != 0)
            or not 32 <= grid['beat_count'] <= 120001
            or not 32 <= grid['source_beat_count'] <= grid['beat_count']
            or grid['origin_extension_beats'] != grid['beat_count'] - grid['source_beat_count']
            or not 1 < grid['terminal_beat'] <= grid['beat_count']
            or any(not _finite_number(grid[key])
                   for key in ('first_tick_s', 'last_tick_s'))
            or not 0 <= grid['first_tick_s'] < grid['last_tick_s'] <= duration
            or not 1 <= len(phrases) <= 65535):
        raise ValueError('Invalid native phrase input grid')
    previous = None
    period = 6000. / grid['bpm_hundredths']
    if (abs(grid['offset_ms']/1000 - grid['first_tick_s']) > .006
            or abs(grid['offset_ms']/1000 + (grid['beat_count']-1)*period - grid['last_tick_s']) > .006):
        raise ValueError('Native phrase grid geometry mismatch')
    for phrase in phrases:
        if (type(phrase) is not dict or set(phrase) != {'start_s', 'end_s', 'kind', 'mood', 'fill', 'label'}
                or any(not _finite_number(phrase[k]) for k in ('start_s', 'end_s'))
                or not 0 <= phrase['start_s'] < phrase['end_s'] <= duration
                or (previous is not None and phrase['start_s'] != previous)
                or type(phrase['kind']) is not int or not 1 <= phrase['kind'] <= 10
                or type(phrase['mood']) is not int or phrase['mood'] not in (1, 2, 3)
                or type(phrase['fill']) is not int or phrase['fill'] not in (0, 1)
                or phrase['label'] != phrase_label(phrase['mood'], phrase['kind'])):
            raise ValueError('Invalid native phrase interval')
        beat_index = round((phrase['start_s'] - grid['offset_ms']/1000) / period)
        if (not 0 <= beat_index < grid['beat_count']
                or abs(phrase['start_s'] - (grid['offset_ms']/1000 + beat_index*period)) > .006):
            raise ValueError('Native phrase outside input grid')
        previous = phrase['end_s']
    terminal_s = grid['offset_ms']/1000 + (grid['terminal_beat']-1)*period
    if abs(previous - terminal_s) > .006:
        raise ValueError('Native phrase terminal policy mismatch')

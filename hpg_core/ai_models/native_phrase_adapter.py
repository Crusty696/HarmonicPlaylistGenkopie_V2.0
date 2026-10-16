"""HPG-Vertrag für den isolierten nativen Phrasengenerator.

Originalmusik bleibt am Quellort. Der Owner beendet den Einmal-Prozess auch
nach erfolgreicher Antwort; native FLS-Zeiger bleiben bis dahin resident.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import time

from .native_phrase_worker import CONTRACT_VERSION, EXE, SHA256
from .native_key import KEY_MAPPING_VERSION, native_key_index


def enabled():
    """Nativer Pfad für die gepinnte EXE; explizit mit 0 abschaltbar."""
    return os.environ.get('HPG_NATIVE_PHRASE', '1') == '1'


def identity():
    import hashlib
    active = enabled()
    try:
        actual = None
        if active:
            with EXE.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    except OSError:
        actual = None
    return dict(contract=CONTRACT_VERSION, key_mapping=KEY_MAPPING_VERSION,
                enabled=active, expected_sha256=SHA256,
                actual_sha256=actual)


def generate_phrases(path, *, beat_times, beat_positions, bpm, duration,
                     verified_grid, key_index, cancel_event=None, timeout_s=180.0,
                     transport=None):
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
    if (type(beat_times) is not list or type(beat_positions) is not list
            or len(beat_times) != len(beat_positions) or len(beat_times) < 32
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in beat_times)
            or any(type(x) is not int or not 1 <= x <= 4 for x in beat_positions)
            or type(bpm) not in (int, float) or not math.isfinite(bpm) or not 0 < bpm <= 1000
            or type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0
            or type(key_index) is not int or not 0 <= key_index < 24
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 180.0):
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
    if (offset_ms > native_period * 1000 or
            any(abs(offset_ms / 1000 + index * native_period - stamp) > .006
                for index, stamp in enumerate(beat_times))):
        return unavailable('native_grid_precision_mismatch')
    source = Path(path)
    try:
        source = source.resolve(strict=True)
        before = source.stat()
        identity = [before.st_size, before.st_mtime_ns, before.st_dev, before.st_ino]
        request = dict(path=str(source), source_identity=identity, bpm_hundredths=bpm_hundredths,
                       offset_ms=offset_ms, bar_position=beat_positions[0], key_index=key_index)
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
        if identity != [after.st_size, after.st_mtime_ns, after.st_dev, after.st_ino]:
            return unavailable('source_changed')
    except Exception as error:
        return unavailable(type(error).__name__ + ': ' + str(error))
    if not isinstance(result, dict) or result.get('status') != 'ok':
        return unavailable(result.get('reason', 'native_worker_failure') if isinstance(result, dict)
                           else 'invalid_worker_result')
    if (result.get('contract') != CONTRACT_VERSION or result.get('executable_sha256') != SHA256
            or result.get('input_grid') != {key: request[key] for key in
                ('bpm_hundredths', 'offset_ms', 'bar_position', 'key_index')}):
        return unavailable('native_identity_mismatch')
    header, arrays = result.get('header'), result.get('arrays')
    if (type(header) is not list or len(header) != 7 or any(type(x) is not int for x in header)
            or type(arrays) is not dict or not 1 <= header[0] <= 65535
            or header[2] not in (1, 2, 3)
            or header[1] != offset_ms or header[3] != beat_positions[0]):
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
            or abs(result['frames']/result['sample_rate'] - duration) > 1/result['sample_rate']):
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
                terminal_boundary_source='native_terminal_beat', terminal_beat=terminal_beat)


def analyze_track_phrases(path, **parameters):
    """Native Zusatzanalyse darf bei einem Fehler die DSP-Auswertung erhalten."""
    try:
        return _analyze_track_phrases(path, **parameters)
    except Exception as error:
        return dict(version=3, status='unavailable', reason=type(error).__name__,
            source='rekordbox_native_phrase_generator', contract=CONTRACT_VERSION,
            executable_sha256=SHA256, phrases=[], input_grid={},
            terminal_boundary_source='native_terminal_beat', key_source='native_unknown_fallback_zero')


def _analyze_track_phrases(path, *, bpm, duration, first_downbeat, grid_usable,
                         usage_blocked, imported_phrases, reference_grid, grid_source,
                         key_note='', key_mode=''):
    """Ein gemeinsamer Aufruf für Fast-/Vollpfad; PSSI behält Vorrang.

    Rekonstruierter nativer Caller verwendet bei unbekanntem Key den Index 0.
    Bekannte Tonarten werden über die ausgelesene native Namenstabelle zugeordnet.
    """
    key_index = native_key_index(key_note, key_mode)
    key_source = ('hpg_key_native_table' if key_index is not None
                  else 'native_unknown_fallback_zero')
    snapshot = dict(version=3, status='skipped', reason='imported_phrases_preferred',
        source='rekordbox_native_phrase_generator', contract=CONTRACT_VERSION,
        executable_sha256=SHA256, phrases=[], input_grid={},
        terminal_boundary_source='native_terminal_beat', key_source=key_source)
    if imported_phrases:
        return snapshot
    if not enabled():
        snapshot.update(status='disabled', reason='disabled_by_configuration')
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
    else:
        period = 60. / bpm
        # Konstantes, technisch bestätigtes HPG-Raster. Keine neue Messung
        # und kein unabhängiger Nachweis der musikalischen Takt-1-Position.
        first_index = -int(math.floor(first_downbeat / period))
        first_tick = first_downbeat + first_index * period
        count = max(0, int(math.ceil((duration-first_tick) / period)))
        times = [first_tick + index*period for index in range(count)]
        positions = [(first_index+index) % 4 + 1 for index in range(count)]
        basis = 'hpg_verified_constant_grid'
    from .cue_service import session
    with session() as client:
        result = generate_phrases(path, beat_times=times, beat_positions=positions,
            bpm=bpm, duration=duration, verified_grid=True,
            key_index=0 if key_index is None else key_index,
            transport=client.native_phrases)
    snapshot.update(status=result['status'], reason=result['reason'])
    if result['status'] == 'ok':
        snapshot.update(phrases=result['phrases'], input_grid=dict(
            result['raw_result']['input_grid'], basis=basis,
            beat_count=len(times), first_tick_s=times[0], last_tick_s=times[-1],
            terminal_beat=result['terminal_beat']))
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
              'phrases', 'input_grid', 'terminal_boundary_source', 'key_source'}
    if (type(value) is not dict or set(value) != fields
            or type(value['version']) is not int or value['version'] != 3
            or value['source'] != 'rekordbox_native_phrase_generator'
            or value['contract'] != CONTRACT_VERSION or value['executable_sha256'] != SHA256
            or value['terminal_boundary_source'] != 'native_terminal_beat'
            or value['key_source'] not in ('native_unknown_fallback_zero', 'hpg_key_native_table')
            or type(value['phrases']) is not list or type(value['input_grid']) is not dict):
        raise ValueError('Invalid native phrase snapshot')
    if value['status'] != 'ok':
        if (value['status'] not in ('disabled', 'skipped', 'unavailable')
                or type(value['reason']) is not str or not value['reason']
                or value['phrases'] or value['input_grid']):
            raise ValueError('Invalid native phrase failure')
        return
    if value['reason'] is not None or not grid_verified or usage_blocked:
        raise ValueError('Native phrases require usable verified grid')
    from ..rekordbox_phrases import phrase_label
    phrases, grid = value['phrases'], value['input_grid']
    keys = {'bpm_hundredths', 'offset_ms', 'bar_position', 'key_index', 'basis',
            'beat_count', 'first_tick_s', 'last_tick_s', 'terminal_beat'}
    if (set(grid) != keys or grid['basis'] not in
            ('verified_rekordbox_grid', 'hpg_verified_constant_grid')
            or any(type(grid[key]) is not int for key in
                ('bpm_hundredths', 'offset_ms', 'bar_position', 'key_index', 'beat_count', 'terminal_beat'))
            or not 1 <= grid['bpm_hundredths'] <= 100000
            or not 0 <= grid['offset_ms'] <= 6000000 / grid['bpm_hundredths']
            or not 1 <= grid['bar_position'] <= 4 or not 0 <= grid['key_index'] < 24
            or (value['key_source'] == 'native_unknown_fallback_zero' and grid['key_index'] != 0)
            or not 32 <= grid['beat_count'] <= 120001
            or not 1 < grid['terminal_beat'] <= grid['beat_count']
            or any(type(grid[key]) not in (int, float) or not math.isfinite(grid[key])
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
                or any(type(phrase[k]) not in (int, float) or not math.isfinite(phrase[k]) for k in ('start_s', 'end_s'))
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

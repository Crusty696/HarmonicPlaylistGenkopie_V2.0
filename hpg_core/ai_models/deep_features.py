"""Gemeinsamer Track-/Cachevertrag für Stems und Audio-Embeddings.

Noch unkalibrierte Merkmale bleiben diagnostisch. Fehlende Messungen sind
keine Nullwerte und ändern weder Synchron-Gates noch Playlist-Gewichte.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

from .feature_audio import source_identity
from .stem_model_hashes import MODEL_HASHES

EMBEDDING_HASH = '27d9ad6e13c077f0c0a20cd786b0c746312aebfc1063f56011defdc10e574c4e'
DLL_HASH = 'a94ddfd5e45507f0be5cadb9e46b929433cbe2a26191ee0afb762053148bdd4b'


def config():
    root = Path(r'C:\Program Files\rekordbox\rekordbox 7.2.19')
    return dict(stem_dll=str(root/'Demucs3.dll'),
        stem_dir=os.environ.get('HPG_STEM_MODEL_DIR', str(Path.home()/'.hpg/models/demucs3_model')),
        embedding_model=os.environ.get('HPG_EMBEDDING_MODEL', str(root/'models/embed_model/cnn_embedding.onnx')),
        prefer_directml=True, stems_enabled=os.environ.get('HPG_STEMS', '1') == '1',
        embedding_enabled=os.environ.get('HPG_EMBEDDINGS', '1') == '1')


def _digest(path):
    try:
        with Path(path).open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    except OSError:
        return None


def identities(settings):
    return dict(dll=_digest(settings['stem_dll']) if settings['stems_enabled'] else None,
        stems=({name: _digest(Path(settings['stem_dir'])/name) for name in MODEL_HASHES}
               if settings['stems_enabled'] else {}),
        embedding=_digest(settings['embedding_model']) if settings['embedding_enabled'] else None)


def config_fingerprint(settings=None):
    settings = config() if settings is None else settings
    return hashlib.sha256(json.dumps(dict(version=1, config=settings, hashes=identities(settings)),
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _empty(kind, duration, fingerprint, status, reason):
    return dict(version=1, kind=kind, duration=duration, fingerprint=fingerprint,
                status=status, reason=reason, data={})


def attach(track):
    try:
        _attach(track)
    except Exception as error:
        # Zusatzmodelle dürfen einen verwendbaren DSP-Track nicht verwerfen.
        for kind, field in (('stems', 'stem_analysis'), ('embedding', 'embedding_analysis')):
            setattr(track, field, _empty(kind, track.duration, '0'*64, 'unavailable',
                                        type(error).__name__))
        track.audio_embedding = []


def _attach(track):
    """Fast-/Vollpfad teilen diesen Aufruf nach Fertigstellung der Basisanalyse."""
    from .cue_service import session
    settings = config()
    fingerprint = config_fingerprint(settings)
    from .feature_reuse import load
    reused = load(track, fingerprint)
    if reused is not None:
        for field, value in reused.items():
            setattr(track, field, value)
        track.audio_embedding = track.embedding_analysis['data']['vector']
        return
    found = identities(settings)
    path = Path(track.filePath).resolve(strict=True)
    identity = source_identity(path)
    with session() as client:
        # Kurze Embedding-Inferenz vor der erheblich längeren Stem-Trennung.
        for kind, field in (('embedding', 'embedding_analysis'), ('stems', 'stem_analysis')):
            if not settings[kind+'_enabled']:
                result = _empty(kind, track.duration, fingerprint, 'disabled', 'disabled_by_configuration')
            elif ((kind == 'stems' and (found['dll'] != DLL_HASH or found['stems'] != MODEL_HASHES))
                  or (kind == 'embedding' and found['embedding'] != EMBEDDING_HASH)):
                result = _empty(kind, track.duration, fingerprint, 'unsupported', 'missing_or_changed_model')
            else:
                parameters = dict(path=str(path), identity=identity, kind=kind,
                                  config=settings, fingerprint=fingerprint)
                result = client.deep_features(parameters, timeout_s=30. if kind == 'embedding' else 180.)
                if result.get('status') != 'ok':
                    result = _empty(kind, track.duration, fingerprint, 'unavailable',
                                    str(result.get('reason', 'service_failure')))
                else:
                    try:
                        validate(result, kind=kind, duration=track.duration)
                        if result['fingerprint'] != fingerprint or source_identity(path) != identity:
                            raise ValueError('Feature identity changed')
                    except (ValueError, TypeError, KeyError):
                        result = _empty(kind, track.duration, fingerprint, 'unavailable', 'invalid_feature_result')
            setattr(track, field, result)
    track.audio_embedding = track.embedding_analysis.get('data', {}).get('vector', [])


def transient_failure(track):
    return any(getattr(track, field, {}).get('status') == 'unavailable'
               for field in ('stem_analysis', 'embedding_analysis'))


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _unit(vector):
    return (type(vector) is list and len(vector) == 64 and all(_finite(x) for x in vector)
            and abs(sum(x*x for x in vector)-1.) <= 1e-4)


def _local_stems(track, start, end):
    snapshot = getattr(track, 'stem_analysis', {})
    if snapshot.get('status') != 'ok' or not 0 <= start < end <= track.duration:
        return None
    curves = snapshot['data']['curves']
    result = {}
    for name, curve in curves.items():
        energy, covered = 0., 0.
        for index in range(int(math.floor(start)), int(math.ceil(end))):
            if index >= len(curve):
                return None
            weight = min(end, index+1.)-max(start, float(index))
            energy += weight*curve[index]**2
            covered += weight
        if covered <= 0:
            return None
        result[name] = math.sqrt(energy/covered)
    return result


def _local_embedding(track, start, end):
    snapshot = getattr(track, 'embedding_analysis', {})
    if snapshot.get('status') != 'ok' or not 0 <= start < end <= track.duration:
        return None
    values = [0.]*64
    covered = 0.
    for row in snapshot['data']['windows']:
        weight = max(0., min(end, row['end_s'])-max(start, row['start_s']))
        covered += weight
        for index, value in enumerate(row['vector']):
            values[index] += weight*value
    norm = math.sqrt(sum(x*x for x in values))
    if abs(covered-(end-start)) > 1e-5 or norm <= 0:
        return None
    return [x/norm for x in values]


def pair_diagnostics(track_a, track_b, start_a, start_b, blend_bars):
    """Zusatzmessungen am konkreten Paarfenster; keine kalibrierten Gates."""
    if not (_finite(track_a.bpm) and _finite(track_b.bpm) and track_a.bpm > 0 and track_b.bpm > 0):
        return {}
    end_a = start_a + blend_bars*4*60./track_a.bpm
    end_b = start_b + blend_bars*4*60./track_b.bpm
    stems_a, stems_b = _local_stems(track_a, start_a, end_a), _local_stems(track_b, start_b, end_b)
    embedding_a = _local_embedding(track_a, start_a, end_a)
    embedding_b = _local_embedding(track_b, start_b, end_b)
    similarity = None
    if embedding_a is not None and embedding_b is not None:
        similarity = max(-1., min(1., sum(a*b for a, b in zip(embedding_a, embedding_b))))
    if stems_a is None and stems_b is None and similarity is None:
        return {}
    bass_swap = None
    if stems_a is not None and stems_b is not None and type(blend_bars) is int and blend_bars > 1:
        candidates = []
        for bar in sorted({max(1, min(blend_bars-1, round(blend_bars*f))) for f in (.25, .5, .75)}):
            time_a, time_b = start_a+bar*240./track_a.bpm, start_b+bar*240./track_b.bpm
            local_a = _local_stems(track_a, time_a, min(end_a, time_a+60./track_a.bpm))
            local_b = _local_stems(track_b, time_b, min(end_b, time_b+60./track_b.bpm))
            if local_a is not None and local_b is not None:
                candidates.append((local_a['bass']+local_b['bass'], bar, time_a, time_b))
        if candidates:
            _, bar, time_a, time_b = min(candidates)
            bass_swap = dict(relative_bar=bar, time_a_s=time_a, time_b_s=time_b,
                             recommendation_only=True, observed_bass_stop=False)
    return dict(stems_a=stems_a, stems_b=stems_b, embedding_cosine=similarity,
                stem_resolution_s=1., embedding_resolution_s=29., calibrated=False,
                bass_swap=bass_swap, affects_score=False)


def validate(value, *, kind, duration):
    if value == {}:
        return
    if (type(value) is not dict or set(value) != {'version', 'kind', 'duration', 'fingerprint', 'status', 'reason', 'data'}
            or type(value['version']) is not int or value['version'] != 1 or value['kind'] != kind
            or not _finite(value['duration']) or abs(value['duration']-duration) > 1/16000.
            or type(value['fingerprint']) is not str or len(value['fingerprint']) != 64
            or any(c not in '0123456789abcdef' for c in value['fingerprint'])
            or type(value['data']) is not dict):
        raise ValueError('Invalid deep-feature provenance')
    if value['status'] != 'ok':
        if (value['status'] not in ('disabled', 'unsupported', 'unavailable') or value['data']
                or type(value['reason']) is not str or not value['reason']):
            raise ValueError('Invalid deep-feature failure')
        return
    if value['reason'] is not None:
        raise ValueError('Successful feature has failure reason')
    data = value['data']
    if kind == 'stems':
        fields = {'curves', 'hop_s', 'sample_rate', 'samples', 'model_sha256', 'dll_sha256',
                  'provider_request', 'provider_verified', 'scale', 'calibrated'}
        if (set(data) != fields or data['model_sha256'] != MODEL_HASHES['hdemucs.onnx']
                or data['dll_sha256'] != DLL_HASH or data['hop_s'] != 1.
                or type(data['sample_rate']) is not int or data['sample_rate'] != 44100
                or type(data['samples']) is not int or abs(data['samples']/44100.-duration) > 1/44100.
                or data['scale'] != 'stereo_rms_normalized_pcm' or data['calibrated'] is not False
                or data['provider_verified'] is not False or data['provider_request'] not in ('DirectML', 'CPU')
                or type(data['curves']) is not dict or set(data['curves']) != {'vocals', 'bass', 'drums', 'other'}):
            raise ValueError('Invalid stem contract')
        for curve in data['curves'].values():
            if (type(curve) is not list or len(curve) != math.ceil(data['samples']/44100.)
                    or any(not _finite(x) or x < 0 for x in curve)):
                raise ValueError('Invalid stem curve')
    elif kind == 'embedding':
        if (set(data) != {'vector', 'windows', 'model_sha256', 'providers', 'calibrated', 'aggregation'}
                or data['model_sha256'] != EMBEDDING_HASH or not _unit(data['vector'])
                or data['aggregation'] != 'hpg_duration_weighted_unit_mean_v1'
                or data['calibrated'] is not False or type(data['providers']) is not list
                or not data['providers'] or any(x not in ('DmlExecutionProvider', 'CPUExecutionProvider') for x in data['providers'])
                or type(data['windows']) is not list or not 1 <= len(data['windows']) <= 249):
            raise ValueError('Invalid embedding contract')
        previous = 0.
        for row in data['windows']:
            if (type(row) is not dict or set(row) != {'start_s', 'end_s', 'vector'}
                    or not _finite(row['start_s']) or not _finite(row['end_s'])
                    or row['start_s'] != previous or not previous < row['end_s'] <= duration
                    or not _unit(row['vector'])):
                raise ValueError('Invalid embedding coverage')
            previous = row['end_s']
        if abs(previous-duration) > 1/16000.:
            raise ValueError('Incomplete embedding coverage')
    else:
        raise ValueError('Unknown feature kind')

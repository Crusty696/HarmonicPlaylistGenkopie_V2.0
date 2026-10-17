"""Gemeinsamer Track-/Cachevertrag für Stems und Audio-Embeddings.

Noch unkalibrierte Merkmale bleiben diagnostisch. Fehlende Messungen sind
keine Nullwerte und ändern weder Synchron-Gates noch Playlist-Gewichte.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import threading

from .feature_audio import source_identity
from .rekordbox_runtime import REKORDBOX_ROOT
from .stem_model_hashes import MODEL_HASHES
from .reader_contract import READER_BACKENDS, source_duration_tolerance as _source_duration_tolerance

EMBEDDING_HASH = '27d9ad6e13c077f0c0a20cd786b0c746312aebfc1063f56011defdc10e574c4e'
ENERGY_HASH = 'c6818a83050beecbb4e701e5092a9670ac74ca787f505bf79797b2eba6f5b69b'
UMAP_HASHES = {
    'umap_norm_before': '9c5b7c9866e77da5d68725d6244cb5c41004f9e7849c5edd404128aabd237bb2',
    'umap_model': 'ba50cc71849ffef6c1eb6d7fb4e46b56094c4e7e3f092b74c831741acc583323',
    'umap_norm_after': '4fe1a26467ce24eb144ad6acb4307abfd6f64143f40d781b03a8496236e25aa2',
}
DLL_HASH = 'a94ddfd5e45507f0be5cadb9e46b929433cbe2a26191ee0afb762053148bdd4b'
EMBEDDING_WINDOW_SECONDS = 29.

_DIGEST_LOCK = threading.Lock()
_DIGEST_CACHE = {}
_COMMON_PRODUCER_FILES = (
    'hpg_core/audio_decoder.py',
    'hpg_core/ai_models/feature_audio.py',
    'hpg_core/ai_models/native_audio_reader.py',
    'hpg_core/ai_models/reader_contract.py',
    'hpg_core/ai_models/deep_features.py',
    'hpg_core/ai_models/feature_reuse.py',
)
PRODUCER_FILES_BY_KIND = {
    'stems': _COMMON_PRODUCER_FILES + (
        'hpg_core/ai_models/stem_model_hashes.py',
        'hpg_core/stem_analyzer.py',
    ),
    'embedding': _COMMON_PRODUCER_FILES + (
        'hpg_core/ai_models/embedding_predictor.py',
        'hpg_core/ai_models/onnx_engine.py',
    ),
}


def source_duration_tolerance(path):
    """Decoderdauer tolerieren; verlustfreie PCM-Dateien bleiben samplegenau."""
    return _source_duration_tolerance(path)


def _feature_timeout_seconds(kind, duration):
    """Begrenzt Zusatzinferenz passend zur Zahl ihrer festen Quellfenster."""
    if kind == 'embedding':
        if not _finite(duration) or duration <= 0:
            raise ValueError('Invalid embedding duration')
        windows_count = math.ceil(duration / EMBEDDING_WINDOW_SECONDS)
        return min(180., max(30., 15. + windows_count))
    if kind == 'stems':
        return 240.
    raise ValueError('Unknown deep-feature kind')


def config():
    root = REKORDBOX_ROOT
    embed_root = root/'models'/'embed_model'
    return dict(stem_dll=str(root/'Demucs3.dll'),
        stem_dir=os.environ.get('HPG_STEM_MODEL_DIR', str(Path.home()/'.hpg/models/demucs3_model')),
        embedding_model=os.environ.get('HPG_EMBEDDING_MODEL', str(embed_root/'cnn_embedding.onnx')),
        energy_model=str(embed_root/'model_energy.onnx'),
        umap_norm_before=str(embed_root/'norm_before_umap.onnx'),
        umap_model=str(embed_root/'umap_embedder.onnx'),
        umap_norm_after=str(embed_root/'norm_after_umap.onnx'),
        # Die beauftragten Zusatzanalysen laufen standardmaessig mit; ihre
        # unkalibrierten Werte bleiben diagnostisch und veraendern das Scoring
        # erst bei einer ausdruecklich gesetzten Ablationsgewichtung.
        prefer_directml=True, stems_enabled=os.environ.get('HPG_STEMS', '1') == '1',
        embedding_enabled=os.environ.get('HPG_EMBEDDINGS', '1') == '1')


def _digest(path):
    try:
        resolved = Path(path).resolve(strict=True)
        stat = resolved.stat()
        signature = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
    except OSError:
        return None
    key = os.path.normcase(str(resolved))
    with _DIGEST_LOCK:
        cached = _DIGEST_CACHE.get(key)
        if cached is not None and cached[0] == signature:
            return cached[1]
        try:
            with resolved.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            current = resolved.stat()
            current_signature = (current.st_size, current.st_mtime_ns,
                                 current.st_ctime_ns, current.st_ino)
            if current_signature != signature:
                return None
        except OSError:
            return None
        _DIGEST_CACHE[key] = (signature, digest)
        return digest


def identities(settings, kind=None):
    if kind is None:
        return {name: identities(settings, name) for name in ('stems', 'embedding')}
    if kind == 'stems':
        return dict(dll=_digest(settings['stem_dll']) if settings['stems_enabled'] else None,
            stems=({name: _digest(Path(settings['stem_dir'])/name) for name in MODEL_HASHES}
                   if settings['stems_enabled'] else {}))
    if kind == 'embedding':
        names = ('embedding_model', 'energy_model', 'umap_norm_before', 'umap_model', 'umap_norm_after')
        return {name: (_digest(settings[name]) if settings['embedding_enabled'] else None)
                for name in names}
    raise ValueError('Unknown deep-feature kind')


def config_fingerprint(settings=None, kind=None):
    settings = config() if settings is None else settings
    if kind is None:
        return {name: config_fingerprint(settings, name) for name in ('stems', 'embedding')}
    if kind not in PRODUCER_FILES_BY_KIND:
        raise ValueError('Unknown deep-feature kind')
    from .native_audio_reader import CONTRACT as audio_reader_contract
    from ..config import SUPPORTED_AUDIO_EXTENSIONS
    root = Path(__file__).resolve().parents[2]
    producer_hashes = {name: _digest(root / name) for name in PRODUCER_FILES_BY_KIND[kind]}
    from .deep_feature_worker import producer_digest
    producer_hashes['hpg_core/ai_models/deep_feature_worker.py#' + kind] = producer_digest(kind)
    if any(value is None for value in producer_hashes.values()):
        raise ValueError('Deep-feature producer identity unavailable')
    # Native reader and format fallback can use these for either feature type.
    distributions = ('numpy', 'soundfile', 'soxr', 'audioread', 'imageio-ffmpeg',
                     'pefile', 'mutagen')
    if kind == 'embedding':
        distributions += ('onnxruntime', 'onnxruntime-directml')
    runtime_versions = {}
    for distribution in distributions:
        try:
            runtime_versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            runtime_versions[distribution] = None
    try:
        import soundfile as sf
        libsndfile_version = sf.__libsndfile_version__
    except (ImportError, AttributeError):
        libsndfile_version = None
    try:
        import sys
        python_version = '.'.join(map(str, sys.version_info[:3]))
    except Exception:
        python_version = None
    kind_settings = ({key: settings[key] for key in
                      ('stems_enabled', 'stem_dll', 'stem_dir', 'prefer_directml')}
                     if kind == 'stems' else
                     {key: settings[key] for key in
                      ('embedding_enabled', 'embedding_model', 'energy_model', 'umap_norm_before',
                       'umap_model', 'umap_norm_after', 'prefer_directml')})
    return hashlib.sha256(json.dumps(dict(version=5, kind=kind, config=kind_settings,
        hashes=identities(settings, kind), audio_reader_contract=audio_reader_contract,
        audio_extensions=sorted(SUPPORTED_AUDIO_EXTENSIONS),
        producer_hashes=producer_hashes, runtime_versions=runtime_versions,
        libsndfile_version=libsndfile_version, python_version=python_version),
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _empty(kind, duration, fingerprint, status, reason):
    return dict(version=1, kind=kind, duration=duration, fingerprint=fingerprint,
                status=status, reason=reason, data={})


def attach(track):
    try:
        _attach(track)
    except Exception as error:
        # Fehler einer späteren Zusatzmessung verwerfen keine bereits
        # abgeschlossene Stem- oder Embeddingmessung.
        try:
            expected_fingerprints = config_fingerprint()
        except Exception:
            expected_fingerprints = {}
        for kind, field in (('stems', 'stem_analysis'), ('embedding', 'embedding_analysis')):
            expected_fingerprint = expected_fingerprints.get(kind)
            fallback_fingerprint = expected_fingerprint or '0'*64
            current = getattr(track, field, {})
            try:
                validate(current, kind=kind, duration=track.duration,
                         duration_tolerance=source_duration_tolerance(track.filePath))
                expected_version = 5 if kind == 'embedding' else 3
                if (current.get('status') != 'ok' or current.get('version') != expected_version
                        or (expected_fingerprint is not None
                            and current.get('fingerprint') != expected_fingerprint)):
                    raise ValueError('no completed feature result')
            except Exception:
                current = _empty(kind, track.duration, fallback_fingerprint, 'unavailable',
                                 type(error).__name__)
                setattr(track, field, current)


def _attach(track):
    """Fast-/Vollpfad teilen diesen Aufruf nach Fertigstellung der Basisanalyse."""
    settings = config()
    fingerprints = config_fingerprint(settings)
    if not settings['stems_enabled'] and not settings['embedding_enabled']:
        for kind, field in (('stems', 'stem_analysis'),
                            ('embedding', 'embedding_analysis')):
            setattr(track, field, _empty(
                kind, track.duration, fingerprints[kind], 'disabled',
                'disabled_by_configuration'))
        return
    from .cue_service import session
    from .feature_reuse import load
    reused = load(track, fingerprints)
    if reused is not None:
        for field, value in reused.items():
            setattr(track, field, value)
        return
    found = identities(settings)
    path = Path(track.filePath).resolve(strict=True)
    identity = source_identity(path)
    with session() as client:
        # Kurze Embedding-Inferenz vor der erheblich längeren Stem-Trennung.
        for kind, field in (('embedding', 'embedding_analysis'), ('stems', 'stem_analysis')):
            fingerprint = fingerprints[kind]
            current = getattr(track, field, {})
            expected_version = 5 if kind == 'embedding' else 3
            if (type(current) is dict and current.get('status') == 'ok'
                    and current.get('version') == expected_version
                    and current.get('fingerprint') == fingerprint):
                try:
                    validate(current, kind=kind, duration=track.duration,
                             duration_tolerance=source_duration_tolerance(path))
                    continue
                except (ValueError, TypeError, KeyError):
                    pass
            if not settings[kind+'_enabled']:
                result = _empty(kind, track.duration, fingerprint, 'disabled', 'disabled_by_configuration')
            elif ((kind == 'stems' and (found[kind]['dll'] != DLL_HASH or found[kind]['stems'] != MODEL_HASHES))
                  or (kind == 'embedding' and (
                      found[kind].get('embedding_model') != EMBEDDING_HASH
                      or found[kind].get('energy_model') != ENERGY_HASH
                      or any(found[kind].get(name) != digest
                             for name, digest in UMAP_HASHES.items())))):
                result = _empty(kind, track.duration, fingerprint, 'unsupported', 'missing_or_changed_model')
            else:
                parameters = dict(path=str(path), identity=identity, kind=kind,
                                  config=settings, fingerprint=fingerprint)
                try:
                    result = client.deep_features(
                        parameters,
                        timeout_s=_feature_timeout_seconds(kind, track.duration),
                    )
                except Exception as error:
                    result = _empty(kind, track.duration, fingerprint, 'unavailable',
                                    type(error).__name__)
                if type(result) is not dict:
                    result = _empty(kind, track.duration, fingerprint, 'unavailable',
                                    'invalid_feature_result_type')
                elif result.get('status') != 'ok':
                    result = _empty(kind, track.duration, fingerprint, 'unavailable',
                                    str(result.get('reason', 'service_failure')))
                else:
                    try:
                        validate(result, kind=kind, duration=track.duration,
                                 duration_tolerance=source_duration_tolerance(path))
                        if result['fingerprint'] != fingerprint or source_identity(path) != identity:
                            raise ValueError('Feature identity changed')
                    except (ValueError, TypeError, KeyError):
                        result = _empty(kind, track.duration, fingerprint, 'unavailable', 'invalid_feature_result')
            setattr(track, field, result)


def needs_refresh(track):
    """Erneuert nur optionale Merkmale, die laut aktueller Konfiguration fehlen."""
    try:
        settings = config()
        fingerprints = config_fingerprint(settings)
    except Exception:
        return any(
            type(snapshot := getattr(track, field, {})) is dict
            and snapshot.get('status') == 'ok'
            for field in ('stem_analysis', 'embedding_analysis')
        )
    for kind, field in (('stems', 'stem_analysis'), ('embedding', 'embedding_analysis')):
        if not settings[kind + '_enabled']:
            snapshot = getattr(track, field, {})
            if (type(snapshot) is not dict
                    or snapshot.get('status') != 'disabled'
                    or snapshot.get('reason') != 'disabled_by_configuration'
                    or snapshot.get('fingerprint') != fingerprints.get(kind)):
                return True
            continue
        snapshot = getattr(track, field, {})
        fingerprint = fingerprints.get(kind)
        if type(snapshot) is not dict or snapshot.get('fingerprint') != fingerprint:
            return True
        status = snapshot.get('status')
        if status == 'unavailable':
            return True
        if status == 'unsupported':
            continue
        expected_version = 5 if kind == 'embedding' else 3
        if status != 'ok' or snapshot.get('version') != expected_version:
            return True
        try:
            validate(snapshot, kind=kind, duration=track.duration,
                     duration_tolerance=source_duration_tolerance(track.filePath))
        except (ValueError, TypeError, KeyError):
            return True
    return False


def transient_failure(track):
    return any(getattr(track, field, {}).get('status') == 'unavailable'
               for field in ('stem_analysis', 'embedding_analysis'))


def _finite(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _unit(vector):
    return (type(vector) is list and len(vector) == 64 and all(_finite(x) for x in vector)
            and abs(sum(x*x for x in vector)-1.) <= 1e-4)


def _local_stems(track, start, end):
    snapshot = getattr(track, 'stem_analysis', {})
    if (type(snapshot) is not dict or snapshot.get('status') != 'ok'
            or not _finite(start) or not _finite(end)
            or not _finite(getattr(track, 'duration', None))
            or not 0 <= start < end <= track.duration):
        return None
    measured_duration = snapshot.get('duration')
    duration_tolerance = source_duration_tolerance(track.filePath)
    if (not _finite(measured_duration)
            or abs(measured_duration-track.duration) > duration_tolerance):
        return None
    data = snapshot.get('data')
    curves = data.get('curves') if type(data) is dict else None
    if type(curves) is not dict or set(curves) != {'vocals', 'bass', 'drums', 'other'}:
        return None
    result = {}
    for name, curve in curves.items():
        if type(curve) is not list or len(curve) != math.ceil(measured_duration):
            return None
        energy, covered = 0., 0.
        for index in range(int(math.floor(start)), int(math.ceil(end))):
            if index >= len(curve) or not _finite(curve[index]) or curve[index] < 0:
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
    if (type(snapshot) is not dict or snapshot.get('status') != 'ok'
            or not _finite(start) or not _finite(end)
            or not _finite(getattr(track, 'duration', None))
            or not 0 <= start < end <= track.duration):
        return None
    measured_duration = snapshot.get('duration')
    duration_tolerance = source_duration_tolerance(track.filePath)
    if (not _finite(measured_duration)
            or abs(measured_duration-track.duration) > duration_tolerance):
        return None
    data = snapshot.get('data')
    rows = data.get('windows') if type(data) is dict else None
    if type(rows) is not list:
        return None
    values = [0.]*64
    covered = 0.
    expected_start = 0.
    for row in rows:
        if (type(row) is not dict or set(row) != {'start_s', 'end_s', 'vector'}
                or not _finite(row['start_s']) or not _finite(row['end_s'])
                or row['start_s'] != expected_start or row['start_s'] >= row['end_s']
                or row['end_s'] > measured_duration
                or not _unit(row['vector'])):
            return None
        expected_start = row['end_s']
        weight = max(0., min(end, row['end_s'])-max(start, row['start_s']))
        covered += weight
        for index, value in enumerate(row['vector']):
            values[index] += weight*value
    norm = math.sqrt(sum(x*x for x in values))
    if (abs(expected_start-measured_duration) > 1/16000.
            or abs(covered-(end-start)) > 1e-5 or norm <= 0):
        return None
    return [x/norm for x in values]


def pair_diagnostics(track_a, track_b, start_a, start_b, blend_bars, *,
                     overlap_sec=None, source_b_rate=1.0):
    """Zusatzmessungen am konkreten Paarfenster; keine kalibrierten Gates."""
    if (type(blend_bars) is not int or blend_bars <= 0
            or not (_finite(start_a) and _finite(start_b)
                    and _finite(track_a.bpm) and _finite(track_b.bpm)
                    and _finite(track_a.duration) and _finite(track_b.duration))
            or track_a.bpm <= 0 or track_b.bpm <= 0):
        return {}
    if overlap_sec is None:
        overlap_sec = blend_bars*4*60./track_a.bpm
    if (not _finite(overlap_sec) or overlap_sec <= 0
            or not _finite(source_b_rate) or source_b_rate <= 0):
        return {}
    # Track B wird im Renderer auf die Dauer von A gestreckt. Seine Quellzeit
    # fuer dieselbe Hoerzeit ist daher overlap * rate (librosa: t_out=t_in/rate).
    end_a = start_a + overlap_sec
    end_b = start_b + overlap_sec*source_b_rate
    if end_a <= start_a or end_b <= start_b:
        return {}
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
        if blend_bars <= 256:
            candidate_bars = range(1, blend_bars)
        else:
            candidate_bars = sorted({
                max(1, min(blend_bars-1, round(blend_bars*f)))
                for f in (.25, .5, .75)
            })
        bar_duration = overlap_sec / blend_bars
        for bar in candidate_bars:
            fraction = bar / blend_bars
            time_a = start_a + overlap_sec*fraction
            time_b = start_b + overlap_sec*fraction*source_b_rate
            local_a = _local_stems(track_a, time_a, min(end_a, time_a+bar_duration))
            local_b = _local_stems(track_b, time_b,
                                   min(end_b, time_b+bar_duration*source_b_rate))
            if local_a is not None and local_b is not None:
                bass_a, bass_b = local_a['bass'], local_b['bass']
                if max(bass_a, bass_b) <= 1e-8:
                    continue
                imbalance = abs(bass_a-bass_b) / max(bass_a, bass_b, 1e-8)
                shared_activity = min(bass_a, bass_b)
                candidates.append((imbalance, -shared_activity, bar, time_a, time_b))
        if candidates:
            _, _, bar, time_a, time_b = min(candidates)
            bass_swap = dict(relative_bar=bar, time_a_s=time_a, time_b_s=time_b,
                             recommendation_only=True, observed_bass_stop=False)
    return dict(stems_a=stems_a, stems_b=stems_b, embedding_cosine=similarity,
                stem_resolution_s=1., embedding_resolution_s=29., calibrated=False,
                bass_swap=bass_swap, affects_score=False)


def validate(value, *, kind, duration, duration_tolerance=1/16000.):
    if value == {}:
        return
    if (type(value) is not dict or set(value) != {'version', 'kind', 'duration', 'fingerprint', 'status', 'reason', 'data'}
            or type(value['version']) is not int or value['version'] not in (1, 2, 3, 4, 5) or value['kind'] != kind
            or not _finite(value['duration'])
            or abs(value['duration']-duration) > duration_tolerance
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
    measured_duration = value['duration']
    from .native_audio_reader import CONTRACT as audio_reader_contract
    if (value['version'] >= 2 and data.get('reader_backend') not in READER_BACKENDS
            or value['version'] == 1 and 'reader_backend' in data
            or value['version'] in (3, 4, 5) and data.get('reader_contract') != audio_reader_contract
            or value['version'] < 3 and 'reader_contract' in data):
        raise ValueError('Invalid deep-feature reader provenance')
    if kind == 'stems':
        fields = {'curves', 'hop_s', 'sample_rate', 'samples', 'model_sha256', 'dll_sha256',
                  'provider_request', 'provider_verified', 'scale', 'calibrated'}
        if value['version'] >= 2:
            fields.add('reader_backend')
        if value['version'] == 3:
            fields.add('reader_contract')
        if (set(data) != fields or data['model_sha256'] != MODEL_HASHES['hdemucs.onnx']
                or data['dll_sha256'] != DLL_HASH or data['hop_s'] != 1.
                or type(data['sample_rate']) is not int or data['sample_rate'] != 44100
                or type(data['samples']) is not int
                or abs(data['samples']/44100.-measured_duration) > 1/44100.
                or data['scale'] != 'stereo_rms_normalized_pcm' or data['calibrated'] is not False
                or data['provider_verified'] is not False or data['provider_request'] not in ('DirectML', 'CPU')
                or type(data['curves']) is not dict or set(data['curves']) != {'vocals', 'bass', 'drums', 'other'}):
            raise ValueError('Invalid stem contract')
        for curve in data['curves'].values():
            if (type(curve) is not list or len(curve) != math.ceil(data['samples']/44100.)
                    or any(not _finite(x) or x < 0 for x in curve)):
                raise ValueError('Invalid stem curve')
    elif kind == 'embedding':
        fields = {'vector', 'windows', 'model_sha256', 'providers', 'calibrated', 'aggregation'}
        if value['version'] >= 2:
            fields.add('reader_backend')
        if value['version'] in (3, 4, 5):
            fields.add('reader_contract')
        if value['version'] == 4:
            fields.add('visualization')
        if value['version'] == 5:
            fields.update(('visualization', 'danceability'))
        if (set(data) != fields
                or data['model_sha256'] != EMBEDDING_HASH or not _unit(data['vector'])
                or data['aggregation'] != 'hpg_duration_weighted_unit_mean_v1'
                or data['calibrated'] is not False or type(data['providers']) is not list
                or not data['providers'] or any(x not in ('DmlExecutionProvider', 'CPUExecutionProvider') for x in data['providers'])
                or type(data['windows']) is not list or not 1 <= len(data['windows']) <= 249):
            raise ValueError('Invalid embedding contract')
        rows = data['windows']
        previous = 0.
        for row in rows:
            if (type(row) is not dict or set(row) != {'start_s', 'end_s', 'vector'}
                    or not _finite(row['start_s']) or not _finite(row['end_s'])
                    or row['start_s'] != previous or not previous < row['end_s'] <= measured_duration
                    or not _unit(row['vector'])):
                raise ValueError('Invalid embedding coverage')
            previous = row['end_s']
        if abs(previous-measured_duration) > 1/16000.:
            raise ValueError('Incomplete embedding coverage')
        if value['version'] in (4, 5):
            visualization = data['visualization']
            if (type(visualization) is not dict
                    or set(visualization) != {'status', 'reason', 'coordinates', 'model_hashes', 'calibrated'}
                    or visualization['status'] not in ('ok', 'unavailable')
                    or visualization['calibrated'] is not False
                    or type(visualization['coordinates']) is not list
                    or len(visualization['coordinates']) != len(rows)
                    or type(visualization['model_hashes']) is not list):
                raise ValueError('Invalid embedding visualization contract')
            allowed_hashes = dict(zip(
                ('norm_before_umap', 'umap_embedder', 'norm_after_umap'),
                (UMAP_HASHES['umap_norm_before'], UMAP_HASHES['umap_model'],
                 UMAP_HASHES['umap_norm_after']),
            ))
            observed_hashes = {}
            for model in visualization['model_hashes']:
                if (type(model) is not dict or set(model) != {'role', 'sha256'}
                        or model['role'] not in allowed_hashes
                        or model['sha256'] != allowed_hashes[model['role']]
                        or model['role'] in observed_hashes):
                    raise ValueError('Invalid UMAP model provenance')
                observed_hashes[model['role']] = model['sha256']
            if visualization['status'] == 'ok':
                if (visualization['reason'] is not None
                        or set(observed_hashes) != set(allowed_hashes)
                        or any(type(row) is not list or len(row) != 2
                               or any(not _finite(x) for x in row)
                               for row in visualization['coordinates'])):
                    raise ValueError('Invalid embedding visualization output')
            elif (type(visualization['reason']) is not str or not visualization['reason']
                    or any(row is not None for row in visualization['coordinates'])):
                raise ValueError('Invalid unavailable embedding visualization')
        if value['version'] == 5:
            danceability = data['danceability']
            if (type(danceability) is not dict
                    or set(danceability) != {'status', 'reason', 'values', 'model_sha256', 'providers', 'calibrated'}
                    or danceability['status'] not in ('ok', 'unavailable')
                    or danceability['calibrated'] is not False
                    or type(danceability['values']) is not list
                    or len(danceability['values']) != len(rows)
                    or type(danceability['providers']) is not list):
                raise ValueError('Invalid Rekordbox energy-model diagnostic')
            if danceability['status'] == 'ok':
                if (danceability['reason'] is not None
                        or danceability['model_sha256'] != ENERGY_HASH
                        or not danceability['providers']
                        or any(provider not in ('DmlExecutionProvider', 'CPUExecutionProvider')
                               for provider in danceability['providers'])
                        or any(not _finite(score) for score in danceability['values'])):
                    raise ValueError('Invalid danceability model result')
            elif (type(danceability['reason']) is not str or not danceability['reason']
                    or danceability['model_sha256'] not in (None, ENERGY_HASH)
                    or danceability['providers']
                    or any(score is not None for score in danceability['values'])):
                raise ValueError('Invalid unavailable danceability result')
    else:
        raise ValueError('Unknown feature kind')

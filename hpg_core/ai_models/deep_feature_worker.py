"""Einmalprozess für Stem- oder Embedding-Merkmale, ohne Audio-Ausgabedateien."""
import json
import ast
from pathlib import Path

import numpy as np

from .feature_audio import source_identity, windows

_used = False


def generate(request):
    import soundfile as sf
    from .deep_features import EMBEDDING_WINDOW_SECONDS, config_fingerprint

    required = {'path', 'identity', 'kind', 'config', 'fingerprint'}
    if (type(request) is not dict or set(request) not in (required, required | {'cpu_fallback'})
            or type(request.get('cpu_fallback', False)) is not bool):
        raise ValueError('Invalid feature request')
    path = Path(request['path'])
    if not path.is_absolute() or source_identity(path) != request['identity']:
        raise ValueError('Feature source identity mismatch')
    if config_fingerprint(request['config'], kind=request['kind']) != request['fingerprint']:
        raise ValueError('Feature model identity mismatch')
    from .native_audio_reader import CONTRACT as audio_reader_contract, NativeAudioStream
    from ..config import SUPPORTED_AUDIO_EXTENSIONS
    if path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
        # Float-PCM bleibt beim HPG-Decoder; andere unterstützte Formate
        # verwenden auch bei langen Quellen den nativen blockweisen Stream.
        try:
            info = sf.info(str(path))
        except Exception:
            info = None
        if (info is not None and path.suffix.lower() in ('.wav', '.wave', '.aif', '.aiff')
                and info.subtype in ('FLOAT', 'DOUBLE')):
            source_context = sf.SoundFile(str(path), mode='r')
        else:
            source_context = NativeAudioStream(path)
    else:
        source_context = sf.SoundFile(str(path), mode='r')
    with source_context as source:
        duration = len(source)/source.samplerate
        if request['kind'] == 'stems':
            result = _generate_stems(source, request)
        elif request['kind'] == 'embedding':
            result = _generate_embedding(source, request, duration)
        else:
            raise ValueError('Unknown feature kind')
        result['reader_backend'] = getattr(source, 'backend', 'hpg-libsndfile')
        if source.channels > 2:
            result['reader_backend'] = 'hpg-libsndfile-mono-downmix-44100'
        result['reader_contract'] = audio_reader_contract
    if source_identity(path) != request['identity']:
        raise ValueError('Feature source changed')
    version = 5 if request['kind'] == 'embedding' else 3
    return dict(version=version, status='ok', reason=None, kind=request['kind'],
                duration=duration, fingerprint=request['fingerprint'], data=result)


def _generate_stems(source, request):
    from ..stem_analyzer import analyze
    return analyze(source, dll_path=request['config']['stem_dll'],
        model_dir=request['config']['stem_dir'],
        prefer_directml=request['config']['prefer_directml'] and not request.get('cpu_fallback', False))


def _generate_embedding(source, request, duration):
    from .embedding_predictor import infer_embedding, infer_danceability, project_umap
    from .deep_features import ENERGY_HASH, UMAP_HASHES
    # Native Caller: 16 kHz, Mono, STFT 512/256, Pads [0,256,0,256].
    # HPG uses disjoint 29-s windows and duration-weighted mean, not RB identity.
    rows = []
    projections = []
    visualization_models = []
    energy_values = []
    energy_providers = []
    energy_reason = None
    pooled = np.zeros(64, np.float64)
    weight = 0
    model = None
    providers = []
    window_samples = int(EMBEDDING_WINDOW_SECONDS * 16000)
    for start, count, block in windows(source, 16000, window_samples, window_samples):
        mono = np.mean(block, axis=0, keepdims=True, dtype=np.float32)
        output = infer_embedding(mono,
            frame_step=np.array([256], np.int64), frame_length=np.array([512], np.int64),
            pads=np.array([0, 256, 0, 256], np.int64),
            model_path=request['config']['embedding_model'],
            prefer_directml=(request['config']['prefer_directml']
                             and not request.get('cpu_fallback', False)))
        if output.status in ('unavailable', 'model_error'):
            # CueClient starts a fresh CPU process for fallback.
            raise RuntimeError(f'Embedding inference {output.status}: {output.reason}')
        if output.status != 'ok' or output.features.shape != (1, 64):
            raise ValueError('Embedding model failed or unexpected feature shape')
        try:
            energy = infer_danceability(output.features,
                model_path=request['config']['energy_model'],
                prefer_directml=(request['config']['prefer_directml']
                                 and not request.get('cpu_fallback', False)))
            scores, energy_providers_for_window = energy.get('scores'), energy.get('providers')
            if (energy.get('status') != 'ok' or energy.get('model_sha256') != ENERGY_HASH
                    or type(scores) is not list or len(scores) != 1
                    or type(scores[0]) not in (int, float) or not np.isfinite(scores[0])
                    or type(energy_providers_for_window) is not list
                    or not energy_providers_for_window
                    or any(provider not in ('DmlExecutionProvider', 'CPUExecutionProvider')
                           for provider in energy_providers_for_window)):
                raise ValueError('invalid_energy_result')
            energy_values.append(float(scores[0]))
            for provider in energy_providers_for_window:
                if provider not in energy_providers:
                    energy_providers.append(provider)
        except Exception as error:
            # Ein optionaler Energiekopf darf gültige Audio-Embeddings nicht verwerfen.
            energy_values.append(None)
            energy_reason = energy_reason or f'{type(error).__name__}: energy_unavailable'
        try:
            projection = project_umap(output.features,
                norm_before_path=request['config']['umap_norm_before'],
                umap_path=request['config']['umap_model'],
                norm_after_path=request['config']['umap_norm_after'],
                prefer_directml=(request['config']['prefer_directml']
                                 and not request.get('cpu_fallback', False)))
            coordinates = projection.get('coordinates')
            model_hashes = projection.get('model_hashes')
            allowed_hashes = {
                'norm_before_umap': UMAP_HASHES['umap_norm_before'],
                'umap_embedder': UMAP_HASHES['umap_model'],
                'norm_after_umap': UMAP_HASHES['umap_norm_after'],
            }
            observed = set()
            if type(model_hashes) is list:
                for model in model_hashes:
                    if (type(model) is not dict or set(model) != {'role', 'sha256'}
                            or model['role'] not in allowed_hashes
                            or model['sha256'] != allowed_hashes[model['role']]
                            or model['role'] in observed):
                        raise ValueError('invalid_projection_provenance')
                    observed.add(model['role'])
            if (projection.get('status') != 'ok' or type(coordinates) is not list
                    or len(coordinates) != 1 or type(coordinates[0]) is not list
                    or len(coordinates[0]) != 2
                    or any(type(value) not in (int, float) or not np.isfinite(value)
                           for value in coordinates[0])
                    or observed != set(allowed_hashes)):
                raise ValueError('invalid_projection_result')
            projections.append([float(value) for value in coordinates[0]])
            for model in model_hashes:
                if model not in visualization_models:
                    visualization_models.append(model)
        except Exception:
            # Eine fehlerhafte optionale Projektion darf Kern-Embedding erhalten.
            projections.append(None)
        vector = output.normalized_features[0].astype(np.float64)
        # ONNX may replace DirectML with CPU during a later window.
        for provider in output.model['session_providers']:
            if provider not in providers:
                providers.append(provider)
        rows.append(dict(start_s=start/16000., end_s=min(duration,
                         (start+count)/16000.), vector=vector.tolist()))
        pooled += count*vector
        weight += count
        model = output.model
    norm = np.linalg.norm(pooled)
    if not weight or not np.isfinite(norm) or norm <= 0:
        raise ValueError('Invalid embedding aggregate')
    visualization_ok = all(value is not None for value in projections)
    energy_ok = all(value is not None for value in energy_values)
    return dict(vector=(pooled/norm).tolist(), windows=rows,
                visualization=dict(status='ok' if visualization_ok else 'unavailable',
                    reason=None if visualization_ok else 'projection_unavailable',
                    coordinates=projections if visualization_ok else [None] * len(projections),
                    model_hashes=visualization_models,
                    calibrated=False),
                danceability=dict(status='ok' if energy_ok else 'unavailable',
                    reason=None if energy_ok else energy_reason or 'energy_model_unavailable',
                    values=energy_values if energy_ok else [None] * len(energy_values),
                    model_sha256=ENERGY_HASH if energy_ok else None,
                    providers=energy_providers if energy_ok else [], calibrated=False),
                model_sha256=model['sha256'], providers=providers,
                calibrated=False, aggregation='hpg_duration_weighted_unit_mean_v1')


def producer_digest(kind):
    """Hash shared dispatcher plus only selected model-generation branch."""
    if kind not in ('stems', 'embedding'):
        raise ValueError('Unknown feature kind')
    source = Path(__file__).read_text(encoding='utf-8')
    tree = ast.parse(source)
    selected = {'generate', '_generate_stems' if kind == 'stems' else '_generate_embedding'}
    parts = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            parts.append(ast.get_source_segment(source, node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in selected:
            parts.append(ast.get_source_segment(source, node))
    return __import__('hashlib').sha256('\n'.join(parts).encode('utf-8')).hexdigest()


def handle(payload):
    global _used
    if _used or len(payload) > 32768:
        raise ValueError('Single bounded feature request required')
    _used = True
    request = json.loads(payload)
    try:
        result = generate(request)
    except Exception as error:
        result = dict(status='unavailable', reason=type(error).__name__+': '+str(error))
    return json.dumps(result, allow_nan=False, separators=(',', ':')).encode('utf-8')

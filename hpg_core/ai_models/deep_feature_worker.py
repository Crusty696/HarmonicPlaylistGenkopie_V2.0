"""Einmalprozess für Stem- oder Embedding-Merkmale, ohne Audio-Ausgabedateien."""
import json
from pathlib import Path

import numpy as np

from .feature_audio import source_identity, windows

_used = False


def generate(request):
    import soundfile as sf
    from .deep_features import config_fingerprint

    required = {'path', 'identity', 'kind', 'config', 'fingerprint'}
    if (type(request) is not dict or set(request) not in (required, required | {'cpu_fallback'})
            or type(request.get('cpu_fallback', False)) is not bool):
        raise ValueError('Invalid feature request')
    path = Path(request['path'])
    if not path.is_absolute() or source_identity(path) != request['identity']:
        raise ValueError('Feature source identity mismatch')
    if config_fingerprint(request['config']) != request['fingerprint']:
        raise ValueError('Feature model identity mismatch')
    with sf.SoundFile(str(path), mode='r') as source:
        duration = len(source)/source.samplerate
        if request['kind'] == 'stems':
            from ..stem_analyzer import analyze
            result = analyze(source, dll_path=request['config']['stem_dll'],
                model_dir=request['config']['stem_dir'],
                prefer_directml=request['config']['prefer_directml'] and not request.get('cpu_fallback', False))
        elif request['kind'] == 'embedding':
            from .embedding_predictor import infer_embedding
            # Native Caller: 16 kHz, Mono, STFT 512/256, Pads [0,256,0,256].
            # HPG verwendet disjunkte 29-s-Fenster und dauergewichtetes Mittel,
            # ausdrücklich einen eigenen Aggregationsvertrag statt RB-Identität.
            rows = []
            pooled = np.zeros(64, np.float64)
            weight = 0
            model = None
            for start, count, block in windows(source, 16000, 464000, 464000):
                mono = np.mean(block, axis=0, keepdims=True, dtype=np.float32)
                output = infer_embedding(mono,
                    frame_step=np.array([256], np.int64), frame_length=np.array([512], np.int64),
                    pads=np.array([0, 256, 0, 256], np.int64),
                    model_path=request['config']['embedding_model'],
                    prefer_directml=request['config']['prefer_directml'])
                if output.status != 'ok' or output.features.shape != (1, 64):
                    raise ValueError('Embedding model failed or unexpected feature shape')
                vector = output.normalized_features[0].astype(np.float64)
                rows.append(dict(start_s=start/16000., end_s=min(duration, (start+count)/16000.),
                                 vector=vector.tolist()))
                pooled += count*vector
                weight += count
                model = output.model
            norm = np.linalg.norm(pooled)
            if not weight or not np.isfinite(norm) or norm <= 0:
                raise ValueError('Invalid embedding aggregate')
            result = dict(vector=(pooled/norm).tolist(), windows=rows,
                          model_sha256=model['sha256'], providers=model['session_providers'],
                          calibrated=False, aggregation='hpg_duration_weighted_unit_mean_v1')
        else:
            raise ValueError('Unknown feature kind')
    if source_identity(path) != request['identity']:
        raise ValueError('Feature source changed')
    return dict(version=1, status='ok', reason=None, kind=request['kind'],
                duration=duration, fingerprint=request['fingerprint'], data=result)


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

"""Isolierter Adapter fuer Rekordbox cnn_embedding.onnx.

Die Vorverarbeitung bleibt Aufruferverantwortung: Sample-Rate, Normalisierung,
STFT-Parameter und Zeitraster sind fuer HPG noch nicht unabhaengig bestaetigt.
Dieses Modul liefert deshalb nur rohe Modellfeatures und deren L2-Normalisierung;
es aendert weder Trackentscheidungen noch Playlist-Scores.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import onnx_engine


MAX_SIGNAL_BYTES = 64 * 1024 * 1024
MODEL_INPUTS = frozenset({'signal', 'frame_step', 'frame_length', 'pads'})
FEATURE_OUTPUT = 'features'


@dataclass(frozen=True)
class EmbeddingResult:
    status: str
    reason: str | None = None
    features: np.ndarray | None = None
    normalized_features: np.ndarray | None = None
    model: dict | None = None


def _valid_parameters(signal, frame_step, frame_length, pads):
    if (not isinstance(signal, np.ndarray) or signal.dtype != np.float32
            or signal.ndim != 2 or signal.shape[0] < 1 or signal.shape[1] < 1
            or signal.nbytes > MAX_SIGNAL_BYTES or not np.isfinite(signal).all()):
        return False
    for value in (frame_step, frame_length):
        if (not isinstance(value, np.ndarray) or value.dtype != np.int64
                or value.shape != (1,) or not 0 < int(value[0]) <= signal.shape[1]):
            return False
    return (isinstance(pads, np.ndarray) and pads.dtype == np.int64
            and pads.shape == (4,) and np.all((pads >= 0) & (pads <= signal.shape[1])))


def _normalize_rows(features):
    if (not isinstance(features, np.ndarray) or features.dtype != np.float32
            or features.ndim != 2 or features.shape[0] < 1
            or features.shape[1] < 1 or not np.isfinite(features).all()):
        return None
    norms = np.linalg.norm(features.astype(np.float64), axis=1)
    if not np.isfinite(norms).all() or np.any(norms <= 0):
        return None
    return np.ascontiguousarray(features / norms[:, None], dtype=np.float32)


def infer_embedding(signal, *, frame_step, frame_length, pads, model_path,
                    prefer_directml=True) -> EmbeddingResult:
    """Run model on caller-prepared channels-first float32 waveform.

    STFT arguments are mandatory. The adapter does not infer them from sample
    rate or audio, and rejects zero feature rows instead of inventing cosine
    distance for missing embeddings.
    """
    if (not _valid_parameters(signal, frame_step, frame_length, pads)
            or not isinstance(model_path, (str, Path)) or not str(model_path)):
        return EmbeddingResult('invalid_input', 'input_contract')
    try:
        model = onnx_engine.get_model(Path(model_path), prefer_directml=prefer_directml)
        details = model.describe()
        if ({item['name'] for item in details['inputs']} != MODEL_INPUTS
                or FEATURE_OUTPUT not in {item['name'] for item in details['outputs']}):
            return EmbeddingResult('unsupported_model', 'tensor_names', model=details)
        (features,) = model.run({
            'signal': signal,
            'frame_step': frame_step,
            'frame_length': frame_length,
            'pads': pads,
        }, output_names=[FEATURE_OUTPUT])
        normalized = _normalize_rows(features)
        if normalized is None:
            return EmbeddingResult('invalid_output', 'feature_tensor', model=details)
        return EmbeddingResult('ok', features=features.copy(),
                               normalized_features=normalized, model=details)
    except onnx_engine.ModelUnavailableError as exc:
        return EmbeddingResult('unavailable', type(exc).__name__)
    except onnx_engine.ModelInputError as exc:
        return EmbeddingResult('invalid_input', type(exc).__name__)
    except onnx_engine.ModelInferenceError as exc:
        return EmbeddingResult('model_error', type(exc).__name__)
    except (OSError, TypeError, ValueError) as exc:
        return EmbeddingResult('unavailable', type(exc).__name__)

"""Begrenzter Einzelaufruf des nativen Rekordbox-Decoders ohne Audio-Inferenz."""
from __future__ import annotations

import json
import math
import time

import numpy as np

from .native_beat_worker import CONTRACT_VERSION, MAX_FRAMES, SHA256
from .process_runtime import OwnedModelProcess


def decode_native_beats(activations, *, timeout_s=30., cancel_event=None):
    """Nur vorhandene Aktivierungen; keine Stem-, Modell- oder Audioläufe."""
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 120):
        raise ValueError('Invalid native beat timeout')
    if (not isinstance(activations, np.ndarray) or activations.ndim != 2
            or activations.shape[1] != 2 or activations.dtype.kind != 'f'
            or not 1 <= len(activations) <= MAX_FRAMES
            or not np.isfinite(activations).all() or np.any(activations < 0)
            or np.any(activations > 1)
            or np.any(activations.sum(axis=1) > 1 + 1e-6)):
        raise ValueError('Invalid native beat activations')
    from ..config import MODEL_PROCESS_MEMORY_LIMIT_BYTES
    deadline = time.monotonic() + timeout_s
    with OwnedModelProcess('hpg_core.ai_models.native_beat_worker', 'handle',
                           max_payload_bytes=1024 * 1024,
                           memory_limit_bytes=MODEL_PROCESS_MEMORY_LIMIT_BYTES) as owner:
        payload = owner.call(np.asarray(activations, dtype='<f4').tobytes(),
                             deadline=deadline, cancel_event=cancel_event)
    result = json.loads(payload)
    if (type(result) is not dict or result.get('status') != 'ok'
            or result.get('contract') != CONTRACT_VERSION
            or result.get('executable_sha256') != SHA256
            or result.get('verified') is not False or result.get('frame_rate') != 100.
            or type(result.get('beats')) is not list
            or len(result['beats']) > len(activations)):
        raise ValueError('Invalid native beat result')
    previous = -1.
    for row in result['beats']:
        if (type(row) is not list or len(row) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in row)
                or not previous < row[0] < len(activations) / 100.
                or row[0] < 0 or row[1] not in (1, 2, 3, 4)):
            raise ValueError('Invalid native beat row')
        previous = row[0]
    return result

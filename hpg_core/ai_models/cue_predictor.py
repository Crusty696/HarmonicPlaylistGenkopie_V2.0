"""Diagnostische Cue-Rohscores für vorhandene PSSI-Kandidaten.

Keine Strukturklassifikation. HPG verwendet librosa-Resampling und einen
expliziten Sample-Floor; Bitgleichheit zur nativen Rekordbox-Vorbereitung
wird nicht behauptet. Modelle werden ausschließlich lokal gelesen.
"""
from collections.abc import Mapping
import hashlib
import math
from numbers import Integral, Real
from pathlib import Path

import numpy as np

from . import onnx_engine


PREPROCESS_VERSION = 'hpg-cue-22050-librosa-soxr-hq-floor-batch4-v2'
MODEL_HASHES = {
    'samplecnn': '3eb5d897a615d84727d48ee94ddec48370d674548fadcf8a93fafd1ff0a02bfc',
    'cue': '288305d581e941e5dbde32bace4f3f71bc651c03621d422c6b4bf17eb04e8bd7',
}
# Statischer Vertrag der beiden oben gepinnten Modelle: sechs Fenster,
# 59049 Samples je Fenster, 512 Features je Fenster und 13 PSSI-Onehots.
_RATE = 22050
_BLOCK = 59049
_HALF = 3 * _BLOCK
# Höchstens vier Kandidaten: 24 CNN-Fenster, kein trackweites Tensor-Batching.
_CANDIDATE_BATCH_SIZE = 4


def _file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _number(value):
    return isinstance(value, Real) and not isinstance(value, (bool, np.bool_)) and math.isfinite(value)


def score_phrase_candidates(audio, sample_rate, candidates, *, samplecnn_path,
                            cue_model_path, window_start_s, track_duration_s,
                            verified_grid, prefer_directml=True):
    """Eine Ergebnis-Dict pro Kandidat, gleiche Reihenfolge, auch bei Duplikaten.

    Kandidaten sind Mappings mit start_s (absolute Sekunden), kind (1..10),
    mood (1..3). Aufrufer bestätigt die PSSI/Beatgrid-Herkunft mit exakt True.
    Audio ist ein zusammenhängendes Mono-Float-Fenster ohne interne Lücken.
    Status: ok, invalid_input, unavailable, unsupported_model oder model_error.
    raw_score bleibt bei Ausfall None; negative Rohscores sind gültig und
    weder Wahrscheinlichkeiten noch Labels. coverage beschreibt das gelieferte
    Fenster und das benötigte Sampleintervall relativ zu diesem Fenster.
    Modell-/DSP-Ausfälle werden als Diagnostik zurückgegeben, nicht geworfen.
    Ein nicht iterierbarer Kandidatencontainer liefert eine leere Ergebnisliste.
    """
    try:
        items = list(candidates)
    except (TypeError, ValueError):
        return []
    results = [dict(index=i, status='unavailable', reason='not_scored', raw_score=None,
                    source='rekordbox_pssi_cue_regressor', model_hashes={},
                    preprocess_version=PREPROCESS_VERSION, coverage={})
               for i in range(len(items))]

    def fail_all(status, reason):
        for result in results:
            result.update(status=status, reason=reason)
        return results

    if not results:
        return results
    if verified_grid is not True:
        return fail_all('unavailable', 'unverified_grid')
    if (not _number(sample_rate) or sample_rate < 1 or sample_rate % 1 != 0
            or not _number(window_start_s) or window_start_s < 0
            or not _number(track_duration_s) or track_duration_s <= window_start_s
            or not isinstance(audio, np.ndarray) or audio.ndim != 1
            or audio.dtype.kind != 'f' or not audio.size or not np.isfinite(audio).all()):
        return fail_all('invalid_input', 'invalid_audio_or_window')
    end_s = window_start_s + len(audio) / sample_rate
    # Eine Sampleperiode deckt die Quantisierung der gemeldeten Trackdauer ab.
    if not math.isfinite(end_s) or end_s > track_duration_s + 1 / sample_rate:
        return fail_all('invalid_input', 'window_exceeds_track')
    valid = []
    for item, result in zip(items, results):
        if (not isinstance(item, Mapping) or not _number(item.get('start_s'))
                or not 0 <= item['start_s'] < track_duration_s
                or any(not isinstance(item.get(key), Integral)
                       or isinstance(item[key], (bool, np.bool_))
                       or not 1 <= item[key] <= limit
                       for key, limit in [('kind', 10), ('mood', 3)])):
            result.update(status='invalid_input', reason='invalid_pssi_candidate')
            continue
        relative = (item['start_s'] - window_start_s) * _RATE
        if not math.isfinite(relative):
            result.update(status='invalid_input', reason='invalid_sample_coordinate')
            continue
        center = math.floor(relative)
        low, high = center - _HALF, center + _HALF
        coverage = dict(window_start_s=float(window_start_s), window_end_s=float(end_s),
                        track_duration_s=float(track_duration_s),
                        required_start_sample=low, required_end_sample=high,
                        sample_rate=_RATE, source_sample_rate=int(sample_rate),
                        source_sample_count=len(audio))
        result['coverage'] = coverage
        # Kontext darf nur jenseits tatsächlicher Trackränder mit Nullen enden.
        available = math.ceil(len(audio) * _RATE / sample_rate)
        if (item['start_s'] < window_start_s or item['start_s'] >= end_s
                or (low < 0 and window_start_s != 0)
                or (high > available and abs(end_s - track_duration_s) > 1 / sample_rate)):
            result.update(reason='missing_window_context')
            continue
        valid.append((item, result, low, high))
    if not valid:
        return results
    try:
        signal = audio
        if sample_rate != _RATE:
            import librosa
            signal = librosa.resample(audio, orig_sr=sample_rate, target_sr=_RATE,
                                      res_type='soxr_hq')
        signal = np.asarray(signal, dtype=np.float32)
        if (signal.ndim != 1 or len(signal) != math.ceil(len(audio) * _RATE / sample_rate)
                or not np.isfinite(signal).all()):
            raise ValueError('Invalid resampled audio')
    except Exception as exc:
        for _, result, _, _ in valid:
            result.update(status='unavailable', reason=f'preprocess_error: {type(exc).__name__}')
        return results
    paths = dict(samplecnn=samplecnn_path, cue=cue_model_path)
    try:
        hashes = {name: _file_hash(path) for name, path in paths.items()}
        for result in results:
            result['model_hashes'] = dict(hashes)
        if hashes != MODEL_HASHES:
            for _, result, _, _ in valid:
                result.update(status='unsupported_model', reason='model_hash_mismatch')
            return results
        models = {name: onnx_engine.get_model(path, prefer_directml=prefer_directml)
                  for name, path in paths.items()}
        if any(models[name].describe()['sha256'] != hashes[name] for name in models):
            raise ValueError('Model identity changed during load')
    except Exception as exc:
        for _, result, _, _ in valid:
            result.update(status='model_error', reason=f'model_load_error: {type(exc).__name__}')
        return results
    for offset in range(0, len(valid), _CANDIDATE_BATCH_SIZE):
        batch = valid[offset:offset + _CANDIDATE_BATCH_SIZE]
        count = len(batch)
        try:
            waveform = np.zeros((count, 6 * _BLOCK), dtype=np.float32)
            for index, (item, result, low, high) in enumerate(batch):
                left, right = max(0, low), min(len(signal), high)
                waveform[index, left-low:right-low] = signal[left:right]
                result['coverage'].update(padded_left_samples=max(0, -low),
                                          padded_right_samples=max(0, high-len(signal)))
            features = models['samplecnn'].run({'waveform': waveform.reshape(count * 6, _BLOCK)},
                                               output_names=['features'])[0]
            if (not isinstance(features, np.ndarray) or features.shape != (count * 6, 512)
                    or features.dtype != np.float32 or not np.isfinite(features).all()):
                raise ValueError('Invalid SampleCNN features')
            rows = np.zeros((count, 3085), dtype=np.float64)
            for index, (item, _, _, _) in enumerate(batch):
                rows[index, item['kind']-1] = 1
                rows[index, 10+item['mood']-1] = 1
            # Pro Kandidat bleiben seine sechs chronologischen Fenster zusammen.
            rows[:, 13:] = features.reshape(count, 6 * 512, order='C')
            output = models['cue'].run({'input': rows}, output_names=['variable'])[0]
            if (not isinstance(output, np.ndarray) or output.shape != (count, 1)
                    or output.dtype != np.float32 or not np.isfinite(output).all()):
                raise ValueError('Invalid cue output')
            for index, (_, result, _, _) in enumerate(batch):
                result.update(status='ok', reason=None, raw_score=float(output[index, 0]))
        except Exception as exc:
            for _, result, _, _ in batch:
                result.update(status='model_error', reason=f'inference_error: {type(exc).__name__}')
    return results

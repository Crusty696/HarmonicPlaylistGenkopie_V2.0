"""Explizite Wiederverwendung belegter Zusatzmerkmale bei DSP-Neuanalyse.

Nur Metadaten lesen. Kein automatischer Import alter Track-Caches; Herkunft,
Quellinhalt, Modellkonfiguration und Produzentencode muessen gleich bleiben.
Bei angeforderter Wiederverwendung nie still einen teuren Ersatzlauf starten.
"""
import hashlib
import json
import os
from pathlib import Path


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(track, fingerprint):
    directory = os.environ.get('HPG_FEATURE_REUSE_REPORT', '').strip()
    if not directory:
        return None
    root = Path(directory)
    report = json.loads((root / 'report.json').read_text(encoding='utf-8'))
    path = Path(track.filePath).resolve(strict=True)
    source = report['sources'][str(path)]
    if (source.get('unchanged') is not True
            or source['before_sha256'] != source['after_sha256']
            or digest(path) != source['before_sha256']):
        raise ValueError('Feature reuse source changed')
    project = Path(__file__).resolve().parents[2]
    # Diese Dateien bestimmen Vorverarbeitung, Modellaufruf und Ergebnis.
    # cue_service transportiert nur den im Worker erneut validierten Auftrag.
    # Neue Beat-Routen dort invalidieren keine unveränderten Stem-Messwerte.
    producers = ('hpg_core/ai_models/feature_audio.py',
                 'hpg_core/ai_models/deep_feature_worker.py',
                 'hpg_core/ai_models/onnx_engine.py',
                 'hpg_core/ai_models/embedding_predictor.py',
                 'hpg_core/stem_analyzer.py')
    for name in producers:
        saved = report['code_sha256'].get(name.replace('/', '\\'),
                                              report['code_sha256'].get(name))
        if saved != digest(project / name):
            raise ValueError('Feature reuse producer changed: ' + name)
    from .deep_features import validate
    for snapshot in root.glob('track-*.json'):
        data = json.loads(snapshot.read_text(encoding='utf-8'))
        if Path(data['filePath']).resolve() != path:
            continue
        result = {}
        for kind, field in (('stems', 'stem_analysis'), ('embedding', 'embedding_analysis')):
            value = data[field]
            validate(value, kind=kind, duration=track.duration)
            if value.get('status') != 'ok' or value['fingerprint'] != fingerprint:
                raise ValueError('Feature reuse configuration changed')
            result[field] = value
        return result
    raise ValueError('Feature reuse snapshot missing')

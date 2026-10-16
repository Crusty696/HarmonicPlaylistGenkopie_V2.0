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
    # Der Fingerprint und die explizite Wiederverwendung binden denselben
    # vollständigen Produzentensatz, unabhängig vom gewählten Decoderpfad.
    from .deep_features import (PRODUCER_FILES_BY_KIND, _empty,
                                source_duration_tolerance, validate)
    if type(fingerprint) is str:
        fingerprints = {'stems': fingerprint, 'embedding': fingerprint}
    elif type(fingerprint) is dict and set(fingerprint) == {'stems', 'embedding'}:
        fingerprints = fingerprint
    else:
        raise ValueError('Invalid feature fingerprint contract')
    invalid = set()
    code_hashes = report.get('code_sha256')
    if type(code_hashes) is not dict:
        invalid.update(('stems', 'embedding'))
    else:
        for kind, files in PRODUCER_FILES_BY_KIND.items():
            for name in files:
                saved = code_hashes.get(name.replace('/', '\\'), code_hashes.get(name))
                if saved != digest(project / name):
                    invalid.add(kind)
    for snapshot in root.glob('track-*.json'):
        data = json.loads(snapshot.read_text(encoding='utf-8'))
        if Path(data['filePath']).resolve() != path:
            continue
        result = {}
        for kind, field in (('stems', 'stem_analysis'), ('embedding', 'embedding_analysis')):
            value = data[field]
            validate(value, kind=kind, duration=track.duration,
                     duration_tolerance=source_duration_tolerance(path))
            expected_version = 5 if kind == 'embedding' else 3
            if value.get('status') == 'ok' and value.get('version') != expected_version:
                raise ValueError('Feature snapshot lacks reader provenance')
            if (kind in invalid or value.get('status') != 'ok'
                    or value['fingerprint'] != fingerprints[kind]):
                result[field] = _empty(kind, track.duration, fingerprints[kind],
                                       'unavailable', 'stale_feature_producer')
            else:
                result[field] = value
        if all(value.get('reason') == 'stale_feature_producer' for value in result.values()):
            raise ValueError('No feature snapshot matches current producers')
        return result
    raise ValueError('Feature reuse snapshot missing')

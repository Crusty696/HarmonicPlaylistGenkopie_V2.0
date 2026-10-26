"""Expliziter Metadaten-Replay darf bei Konflikten keine Modelle starten."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from hpg_core.ai_models import feature_reuse as reuse, deep_features as features
from tests.test_deep_features import embedding
from hpg_core.ai_models.native_audio_reader import CONTRACT


@pytest.mark.parametrize('damage', [None, 'source', 'producer', 'config', 'missing'])
def test_reuse_binds_source_producer_configuration_and_features(tmp_path, monkeypatch, damage):
    source = tmp_path / 'source.bin'
    source.write_bytes(b'unveraenderte Testquelle')
    sha = reuse.digest(source)
    project = Path(reuse.__file__).resolve().parents[2]
    hashes = {str(p.relative_to(project)): reuse.digest(p) for p in (project/'hpg_core').rglob('*.py')}
    report = dict(sources={str(source): dict(unchanged=True, before_sha256=sha, after_sha256=sha)}, code_sha256=hashes)
    vector = embedding()
    vector['version'] = 5
    vector['data'].update(
        reader_backend='rekordbox-mpg123', reader_contract=CONTRACT,
        visualization=dict(status='unavailable', reason='models_unavailable',
            coordinates=[None, None], model_hashes=[], calibrated=False),
        danceability=dict(status='unavailable', reason='models_unavailable',
            values=[None, None], model_sha256=features.ENERGY_HASH,
            providers=[], calibrated=False),
    )
    stem = dict(version=3, kind='stems', duration=58., fingerprint='a'*64,
        status='ok', reason=None, data=dict(curves={n: [0.]*58 for n in ('vocals','bass','drums','other')},
        hop_s=1., sample_rate=44100, samples=58*44100,
        reader_backend='rekordbox-mpg123', reader_contract=CONTRACT,
        model_sha256=features.MODEL_HASHES['hdemucs.onnx'], dll_sha256=features.DLL_HASH,
        provider_request='CPU', provider_verified=False, scale='stereo_rms_normalized_pcm', calibrated=False))
    snapshot = dict(filePath=str(source), stem_analysis=stem, embedding_analysis=vector)
    if damage == 'source':
        source.write_bytes(b'geanderte Quelle')
    if damage == 'producer':
        report['code_sha256'] = {}
    (tmp_path/'report.json').write_text(json.dumps(report))
    if damage != 'missing':
        (tmp_path/'track-0.json').write_text(json.dumps(snapshot))
    monkeypatch.setenv('HPG_FEATURE_REUSE_REPORT', str(tmp_path))
    track = SimpleNamespace(filePath=str(source), duration=58.)
    if damage:
        with pytest.raises(ValueError):
            reuse.load(track, 'b'*64 if damage == 'config' else 'a'*64)
    else:
        assert reuse.load(track, 'a'*64)['embedding_analysis'] == vector

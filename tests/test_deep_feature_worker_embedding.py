"""Embedding-Worker einschließlich echter Fensterbildung, ohne Modellinferenz."""
from types import SimpleNamespace

import numpy as np
import soundfile as sf

from hpg_core.ai_models import deep_feature_worker as worker
from hpg_core.ai_models import deep_features, embedding_predictor
from hpg_core.ai_models.feature_audio import source_identity


def test_embedding_worker_covers_tail_and_weights_by_valid_audio(monkeypatch, tmp_path):
    source = tmp_path / "synthetic.wav"
    sf.write(source, np.full((30 * 16000, 2), 0.1, dtype=np.float32), 16000, subtype="FLOAT")
    vectors = np.eye(64, dtype=np.float32)[:2]
    calls = []

    def infer(audio, **parameters):
        assert audio.shape == (1, 29 * 16000)
        assert parameters["frame_step"].tolist() == [256]
        assert parameters["frame_length"].tolist() == [512]
        assert parameters["pads"].tolist() == [0, 256, 0, 256]
        index = len(calls)
        calls.append(audio.copy())
        vector = vectors[index:index + 1]
        return SimpleNamespace(status="ok", features=vector, normalized_features=vector,
                               model={"sha256": deep_features.EMBEDDING_HASH,
                                      "session_providers": ["CPUExecutionProvider"]})

    monkeypatch.setattr(embedding_predictor, "infer_embedding", infer)
    monkeypatch.setattr(embedding_predictor, "infer_danceability", lambda *a, **k: {"status": "unavailable"})
    monkeypatch.setattr(embedding_predictor, "project_umap", lambda *a, **k: {"status": "unavailable"})
    monkeypatch.setattr(deep_features, "config_fingerprint", lambda *a, **k: "a" * 64)
    request = dict(path=str(source), identity=source_identity(source), kind="embedding",
                   fingerprint="a" * 64, config=dict(prefer_directml=False,
                   embedding_model="synthetic", energy_model="synthetic",
                   umap_norm_before="synthetic", umap_model="synthetic", umap_norm_after="synthetic"))

    result = worker.generate(request)

    assert result["status"] == "ok" and result["duration"] == 30.
    data = result["data"]
    assert [(row["start_s"], row["end_s"]) for row in data["windows"]] == [(0., 29.), (29., 30.)]
    assert len(calls) == 2
    assert np.allclose(calls[1][:, :16000], 0.1)
    assert np.count_nonzero(calls[1][:, 16000:]) == 0
    expected = 29 * vectors[0] + vectors[1]
    expected /= np.linalg.norm(expected)
    assert np.allclose(data["vector"], expected)
    assert data["danceability"]["status"] == "unavailable"
    assert data["visualization"]["status"] == "unavailable"
    assert data["providers"] == ["CPUExecutionProvider"]

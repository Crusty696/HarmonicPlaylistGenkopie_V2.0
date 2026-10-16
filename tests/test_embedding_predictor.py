import numpy as np

from hpg_core.ai_models import embedding_predictor
from hpg_core.ai_models.embedding_predictor import _normalize_rows, _valid_parameters


def test_embedding_rows_are_normalized_independently():
    features = np.asarray([[3.0, 4.0], [5.0, 12.0]], dtype=np.float32)

    result = _normalize_rows(features)

    assert result is not None
    np.testing.assert_allclose(np.linalg.norm(result, axis=1), [1.0, 1.0])
    np.testing.assert_allclose(result, [[0.6, 0.8], [5.0 / 13.0, 12.0 / 13.0]])


def test_zero_or_malformed_embedding_is_not_a_cosine_vector():
    assert _normalize_rows(np.zeros((1, 4), dtype=np.float32)) is None
    assert _normalize_rows(np.zeros((4,), dtype=np.float32)) is None


def test_nonfinite_embedding_is_rejected():
    features = np.asarray([[1.0, np.inf]], dtype=np.float32)

    assert _normalize_rows(features) is None


def test_model_inputs_require_explicit_int64_stft_parameters():
    signal = np.zeros((1, 4096), dtype=np.float32)
    step = np.asarray([512], dtype=np.int64)
    length = np.asarray([2048], dtype=np.int64)
    pads = np.asarray([0, 0, 0, 0], dtype=np.int64)

    assert _valid_parameters(signal, step, length, pads)
    assert not _valid_parameters(signal, None, length, pads)
    assert not _valid_parameters(signal, step, length, np.zeros(4, dtype=np.int32))
    assert not _valid_parameters(signal, np.asarray([4097], dtype=np.int64), length, pads)


def test_infer_embedding_uses_explicit_model_and_only_feature_output(monkeypatch, tmp_path):
    class FakeModel:
        def describe(self):
            return {
                'inputs': [{'name': name} for name in embedding_predictor.MODEL_INPUTS],
                'outputs': [{'name': 'output'}, {'name': 'features'}],
            }

        def run(self, inputs, output_names=None):
            assert set(inputs) == embedding_predictor.MODEL_INPUTS
            assert output_names == ['features']
            return [np.asarray([[3.0, 4.0]], dtype=np.float32)]

    model_path = tmp_path / 'cnn_embedding.onnx'
    requested_paths = []
    monkeypatch.setattr(embedding_predictor.onnx_engine, 'get_model',
                        lambda path, *, prefer_directml: (requested_paths.append(path) or FakeModel()))
    result = embedding_predictor.infer_embedding(
        np.zeros((1, 4096), dtype=np.float32),
        frame_step=np.asarray([512], dtype=np.int64),
        frame_length=np.asarray([2048], dtype=np.int64),
        pads=np.asarray([0, 0, 0, 0], dtype=np.int64),
        model_path=model_path,
    )

    assert result.status == 'ok'
    assert requested_paths == [model_path]
    np.testing.assert_allclose(result.features, [[3.0, 4.0]])
    np.testing.assert_allclose(result.normalized_features, [[0.6, 0.8]])

"""Neue Reader-/Modusverträge ohne Audioinferenz oder Produktivcache."""
from copy import deepcopy
import pytest

from hpg_core.ai_models.native_beat_selection import select_model, validate_selection, configured_mode
from hpg_core.ai_models import native_track_beats as native
from hpg_core.ai_models.native_audio_reader import NativeAudioReader
from hpg_core.ai_models.native_phrase_worker import NativeContractError
from hpg_core.ai_models import native_audio_reader as reader_module
from tests.test_native_track_beats import snapshot


@pytest.mark.parametrize('suffix', ['.m4a', '.mp4', '.M4A'])
@pytest.mark.parametrize('codec,expected', [('alac', 0x2cdd630), ('mp4a.40.2', 0x2cdd760)])
def test_mp4_native_factory_uses_codec_metadata(monkeypatch, suffix, codec, expected):
    from pathlib import Path
    from types import SimpleNamespace
    import mutagen.mp4
    monkeypatch.setattr(mutagen.mp4, 'MP4', lambda path: SimpleNamespace(
        info=SimpleNamespace(codec=codec, channels=2, bits_per_sample=24)))
    assert reader_module._native_factory_for_source(Path('source' + suffix)) == expected


@pytest.mark.parametrize('channels,bits', [(6, 24), (2, 32)])
def test_native_alac_rejects_unsupported_dimensions_before_factory(monkeypatch, channels, bits):
    from pathlib import Path
    from types import SimpleNamespace
    import mutagen.mp4
    monkeypatch.setattr(mutagen.mp4, 'MP4', lambda path: SimpleNamespace(
        info=SimpleNamespace(codec='alac', channels=channels, bits_per_sample=bits)))
    with pytest.raises(NativeContractError, match='ALAC dimensions'):
        reader_module._native_factory_for_source(Path('source.m4a'))


@pytest.mark.parametrize('mode,stored,model,chunked', [
    (4, None, 'model7', True), (3, None, 'model8', False),
    (2, True, 'model7', True), (2, False, 'model8', False)])
def test_native_mode_routes_explicitly(mode, stored, model, chunked):
    result = select_model(mode, stored)
    validate_selection(result)
    assert (result['model_id'], result['chunked']) == (model, chunked)


@pytest.mark.parametrize('mode,stored', [(True, None), (1, None), (5, None),
                                       (2, None), (2, 1), ('4', None)])
def test_unknown_configuration_never_guesses(mode, stored):
    with pytest.raises(ValueError):
        select_model(mode, stored)


def test_configuration_environment_is_explicit(monkeypatch):
    monkeypatch.delenv('HPG_NATIVE_BEAT_MODE', raising=False)
    assert configured_mode() == 2
    monkeypatch.setenv('HPG_NATIVE_BEAT_MODE', '3')
    assert configured_mode() == 3
    monkeypatch.setenv('HPG_NATIVE_BEAT_MODE', 'auto')
    with pytest.raises(ValueError):
        configured_mode()


def test_model8_snapshot_retains_its_own_hashes():
    data = snapshot()
    data.update(selection=select_model(3), model_id='model8',
                model_hashes=deepcopy(native.MODEL_HASHES['model8']))
    data['verification'] = {
        'model_id': 'model7',
        'model_hashes': deepcopy(native.MODEL_HASHES['model7']),
        'beats': [[row['pos'] / 44100, row['numBar']] for row in data['grid']],
        'coverage': {'start_s': 0., 'end_s': (data['frames'] - 1) / 44100},
    }
    data['model_beats'] = [[row['pos'] / 44100, row['numBar']]
                           for row in data['grid']]
    native.validate_snapshot(data, duration=48.)
    data['model_hashes'] = deepcopy(native.MODEL_HASHES['model7'])
    with pytest.raises(ValueError):
        native.validate_snapshot(data, duration=48.)


@pytest.mark.parametrize('field,value', [('source_sample_rate', 48000),
    ('output_frames', 1), ('source_channels', 3), ('source_bit_depth', True),
    ('contract', 'unverified-reader')])
def test_reader_provenance_is_bound_to_audio(field, value):
    data = snapshot()
    data['reader'][field] = value
    with pytest.raises(ValueError):
        native.validate_snapshot(data, duration=48.)


@pytest.mark.parametrize('suffix', ['.wav', '.wave', '.aif', '.aiff'])
def test_required_native_reader_never_silently_falls_back(tmp_path, suffix):
    source = tmp_path / f'input{suffix}'
    source.write_bytes(b'')

    with pytest.raises(NativeContractError, match='Required Rekordbox reader unavailable'):
        NativeAudioReader(None, source)


@pytest.mark.parametrize('channels', [None, 6])
def test_unsupported_wav_channel_layout_uses_hpg_reader(monkeypatch, tmp_path, channels):
    source = tmp_path / 'multichannel.wav'
    source.write_bytes(b'')
    calls = []

    class Reader:
        def __init__(self, image, path, **kwargs):
            calls.append((image, path, kwargs['use_rekordbox']))
            self.frames = 44100
            self.channels = 6
            self.backend = 'hpg-libsndfile'

    monkeypatch.setattr(reader_module, '_source_channel_count', lambda _path: channels)
    monkeypatch.setattr(reader_module, 'NativeAudioReader', Reader)

    stream = reader_module.NativeAudioStream(source)

    assert calls == [(None, source, False)]
    assert stream.backend == 'hpg-libsndfile'


def test_supported_wav_reader_initialization_failure_uses_hpg_fallback(
        monkeypatch, tmp_path):
    source = tmp_path / 'stereo.wav'
    source.write_bytes(b'')
    image = object()
    calls = []

    class Reader:
        def __init__(self, selected_image, path, **kwargs):
            native = kwargs['use_rekordbox']
            calls.append((selected_image, path, native))
            if native:
                raise NativeContractError('Native builtin decoder could not open source')
            self.frames = 44100
            self.channels = 2
            self.backend = 'hpg-libsndfile'

    monkeypatch.setattr(reader_module, '_source_channel_count', lambda _path: 2)
    monkeypatch.setattr(reader_module, '_reader_image', lambda: image)
    monkeypatch.setattr(reader_module, 'NativeAudioReader', Reader)

    stream = reader_module.NativeAudioStream(source)

    assert calls == [(image, source, True), (None, source, False)]
    assert stream.backend == 'hpg-libsndfile'


def test_aac_factory_route_survives_unknown_channel_metadata(monkeypatch, tmp_path):
    from hpg_core.ai_models.reader_contract import NATIVE_BEAT_INPUT_CONVENTIONS

    source = tmp_path / 'unknown-channels.aac'
    source.write_bytes(b'')
    image = object()
    calls = []

    class Reader:
        def __init__(self, selected_image, path, **kwargs):
            calls.append((selected_image, path, kwargs['use_rekordbox']))
            self.frames = 44100
            self.channels = 2
            self.backend = 'rekordbox-builtin-aac'

    monkeypatch.setattr(reader_module, '_source_channel_count', lambda _path: None)
    monkeypatch.setattr(reader_module, '_reader_image', lambda: image)
    monkeypatch.setattr(reader_module, 'NativeAudioReader', Reader)

    stream = reader_module.NativeAudioStream(source)

    assert calls == [(image, source, True)]
    assert stream.backend == 'rekordbox-builtin-aac'
    assert NATIVE_BEAT_INPUT_CONVENTIONS[stream.backend] == (
        'rekordbox-builtin-aac-planar-float32')


def test_resampled_metadata_uses_source_and_output_timebases():
    data = snapshot()
    data['reader'].update(source_sample_rate=48000, source_frames=48*48000,
                          source_channels=1, output_channels=1)
    native.validate_snapshot(data, duration=48.)


def test_parent_requests_selected_mode_once(tmp_path, monkeypatch):
    monkeypatch.setenv('HPG_NATIVE_BEAT', '1')
    source = tmp_path/'not-decoded-in-parent.wav'
    source.write_bytes(b'parent must only stat this source')
    monkeypatch.setenv('HPG_NATIVE_BEAT_MODE', '3')
    data = snapshot()
    calls = []
    def transport(job, request, **kwargs):
        calls.append((job, request))
        return dict(contract='rb-7.2.19-native-beat-pipeline-research-v17',
            executable_sha256=native.SHA256, tensorflow_sha256=native.TF_SHA256,
            model_id='model8', model_hashes=native.MODEL_HASHES['model8'],
            selection=select_model(3), boundary_contract=native.BOUNDARY_CONTRACT, model_coverage=data['model_coverage'], reader=data['reader'], frames=data['frames'],
            verified=False, bpm=data['bpm'], grid=data['grid'],
            input_convention=data['input_convention'],
            beats=[[row['pos'] / 44100, row['numBar']]
                   for row in data['grid']],
            verification=dict(
                model_id='model7',
                model_hashes=native.MODEL_HASHES['model7'],
                beats=[[row['pos'] / 44100, row['numBar']]
                       for row in data['grid']],
                coverage=dict(start_s=0., end_s=(data['frames'] - 1) / 44100),
            ))
    result = native.analyze(source, transport=transport)
    assert result['status'] == 'ok', result
    assert len(calls) == 1
    assert calls[0][0] == 'native_beat'
    assert calls[0][1]['configuration'] == 3
    assert result['model_id'] == 'model8'


def test_model8_window_endpoint_is_valid_but_excess_is_not():
    import numpy as np
    from hpg_core.ai_models.native_beat_pipeline_worker import validate_model_rows
    from hpg_core.ai_models.native_phrase_worker import NativeContractError
    rows = np.array([[.01, 1], [.5, 2], [1., 3], [60., 4]], dtype=np.float32)
    assert validate_model_rows(rows, 60*44100)[-1] == [60., 4.]
    rows[-1, 0] = 60.01
    with pytest.raises(NativeContractError):
        validate_model_rows(rows, 60*44100)

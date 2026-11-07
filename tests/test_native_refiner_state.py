"""Alternativraster dürfen keinen Zustand des verworfenen Introgrids erben."""
import json
from types import SimpleNamespace

import pytest

from hpg_core.ai_models import native_beat_boundaries as boundaries
from hpg_core.ai_models import native_beat_pipeline_worker as worker


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    source = tmp_path / 'source.aiff'
    identity = {'fixture': True}
    full_rows = [[index * 60 / 135, index % 4 + 1] for index in range(1055)]
    calls = []
    refinements = []
    processors = []
    scenario = SimpleNamespace(stable_start=348 * 44100, replacement_bpm=13636)
    reader = SimpleNamespace(frames=469 * 44100, backend='fixture',
                             metadata=lambda: {'fixture': True})
    monkeypatch.setattr(worker, '_used', False)
    monkeypatch.setattr(worker, '_source_identity', lambda path: identity)
    monkeypatch.setattr(worker, 'NativeImage', lambda: SimpleNamespace(
        function=lambda *args: lambda: 0))
    monkeypatch.setattr(worker, 'bind_reader_imports', lambda image: None)
    monkeypatch.setattr(worker, '_bind_tensorflow', lambda image: None)
    monkeypatch.setattr(worker, 'NativeAudioReader', lambda *args, **kwargs: reader)
    monkeypatch.setattr(worker, '_hashes', lambda *args: {'fixture': 'hash'})

    def stable_start(rows, frames):
        assert rows is full_rows
        assert frames == reader.frames
        return scenario.stable_start

    monkeypatch.setattr(worker, 'stable_full_window_start', stable_start)

    class StatefulProcessor:
        def __init__(self, image, selected_reader):
            assert selected_reader is reader
            self.stored_mode = False
            self.window_start = 0
            self.final_bpm = None
            processors.append(self)

        def refine(self, grid, bpm, selected):
            # Beobachtete Semantik: weiteres Refinement behält das erste Tempo.
            if self.final_bpm is None:
                self.final_bpm = 13500 if bpm == 13636 else bpm
            refinements.append((self, bpm, selected, self.final_bpm))
            return grid, self.final_bpm

    monkeypatch.setattr(worker, 'NativeGridProcessor', StatefulProcessor)

    def run(image, selected_reader, selection, start):
        calls.append((selection['model_id'], start))
        if selection['chunked']:
            bpm, rows = 13500, full_rows
        else:
            bpm = 8100 if start == 0 else scenario.replacement_bpm
            rows = [[start / 44100, 1], [start / 44100 + 60 / (bpm / 100), 2]]
        return [{'pos': 0, 'numBar': 1, 'bpm': bpm}], bpm, rows, {
            'start_s': start / 44100, 'end_s': 469 if selection['chunked'] else start / 44100 + 60}

    monkeypatch.setattr(boundaries, 'run', run)

    def invoke(mode=2):
        return json.loads(worker.handle(json.dumps(dict(path=str(source),
            source_identity=identity, configuration=mode)).encode()))

    return scenario, invoke, calls, refinements, processors


def test_stable_window_replaces_latched_intro_tempo(pipeline):
    scenario, invoke, calls, refinements, processors = pipeline
    result = invoke()
    assert result['bpm'] == 135.0
    assert result['model_id'] == 'model8'
    assert result['model_coverage']['start_s'] == 348
    assert result['verification']['model_id'] == 'model7'
    assert result['verified'] is False
    assert calls == [('model8', 0), ('model7', 0), ('model8', 348 * 44100)]
    assert [entry[3] for entry in refinements] == [8100, 13500]
    assert refinements[0][0] is not refinements[1][0]


def test_full_sequence_fallback_replaces_latched_intro_tempo(pipeline):
    scenario, invoke, calls, refinements, processors = pipeline
    scenario.stable_start = None
    result = invoke()
    assert result['bpm'] == 135.0
    assert result['model_id'] == 'model7'
    assert result['requested_configuration'] == 2
    assert result['selection']['configuration'] == 4
    assert result['verification'] is None
    assert result['verified'] is False
    assert calls == [('model8', 0), ('model7', 0)]
    assert [entry[3] for entry in refinements] == [8100, 13500]
    assert refinements[1][2] is True
    assert refinements[0][0] is not refinements[1][0]


def test_fresh_refiner_does_not_release_a_still_contradictory_window(pipeline):
    scenario, invoke, calls, refinements, processors = pipeline
    scenario.replacement_bpm = 8100
    result = invoke()
    assert result == {'status': 'unavailable', 'reason':
        'NativeContractError: Stable model window still contradicts full sequence'}


def test_explicit_short_model_keeps_its_requested_selection(pipeline):
    scenario, invoke, calls, refinements, processors = pipeline
    result = invoke(3)
    assert result['selection']['configuration'] == 3
    assert result['bpm'] == 81.0
    assert calls == [('model8', 0), ('model7', 0)]
    assert len(refinements) == 1

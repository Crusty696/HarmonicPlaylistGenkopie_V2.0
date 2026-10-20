"""Alle nativen Satzmodi müssen Renderfehler vor Veröffentlichung abfangen."""
from dataclasses import replace

import pytest

from hpg_core.hearing_workflow import (
    CancellationToken, HearingOperationError, _producer_namespace, create_set,
)
from hpg_core.hearing_sources import SourceRenderSink
from hpg_core.transition_renderer import TransitionClipSpec
from tests.test_hearing_workflow import config_fixture


@pytest.mark.parametrize("mode", ["einzel", "dramaturgie"])
@pytest.mark.parametrize("accepted", [True, False])
def test_source_sink_requires_renderability(config_fixture, tmp_path, mode, accepted):
    config = replace(config_fixture, mode=mode)
    stage = tmp_path / "stage"
    stage.mkdir()
    sink = SourceRenderSink(stage, config.source_roots)
    root = config.source_roots[0]
    spec = TransitionClipSpec(str(root / "a.wav"), str(root / "b.mp3"), 20., 0., 8.)
    calls = []

    def preflight(value, sources):
        from hpg_core.hearing_playback import _check_sources
        calls.append(value)
        _check_sources(sources)
        assert {source["path"] for source in sources} == {
            spec.track_a_path, spec.track_b_path,
        }
        return accepted

    args = _producer_namespace(config, stage, config.output_dir, sink,
                               CancellationToken(), None, preflight)
    if accepted:
        args.hpg_render_sink(spec, stage / "clips/001.wav")
        assert sink.failure is None
    else:
        with pytest.raises(HearingOperationError, match="nicht renderbar"):
            args.hpg_render_sink(spec, stage / "clips/001.wav")
        assert sink.failure is not None
    assert calls == [spec]
    assert not list(stage.rglob("*.wav"))


def test_single_set_failed_render_never_publishes(config_fixture):
    with pytest.raises(HearingOperationError, match="nicht renderbar"):
        create_set(config_fixture, preflight=lambda *_: False)
    assert not config_fixture.output_dir.exists()
    assert not list(config_fixture.output_dir.parent.glob(".result.staging-*"))


@pytest.mark.parametrize("mode", ["einzel", "kandidaten", "dramaturgie"])
def test_native_worker_installs_preflight_for_every_mode(config_fixture, monkeypatch, mode):
    from hpg_core import hearing_jobs, hearing_workflow

    observed = []

    def create(config, **kwargs):
        observed.append(config.mode)
        assert callable(kwargs["preflight"])
        raise hearing_workflow.HearingCancelledError("Kontrollierter Testabbruch")

    monkeypatch.setattr(hearing_workflow, "create_set", create)
    worker = hearing_jobs.HearingPrepareWorker(replace(config_fixture, mode=mode))
    results = []
    worker.completed.connect(results.append)
    worker.run()
    assert observed == [mode]
    assert results[0]["cancelled"] is True

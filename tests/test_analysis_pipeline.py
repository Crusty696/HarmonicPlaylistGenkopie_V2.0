"""Gemeinsamer Abschluss beider Analysepfade ohne Audio oder Produktivcache."""
import importlib.util
import logging
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("policy,degraded,transient,phrase_status,persisted,expected_writes,success", [
    ("fresh", False, False, "ok", True, 0, True),
    ("reuse", False, False, "ok", True, 1, True),
    ("reuse", False, False, "ok", False, 1, False),
    ("reuse", True, False, "ok", True, 0, True),
    ("reuse", False, True, "ok", True, 0, True),
    ("reuse", False, False, "unavailable", True, 0, True),
])
def test_gemeinsamer_abschluss_bewahrt_cachevertrag(
    policy, degraded, transient, phrase_status, persisted, expected_writes, success,
):
    assert importlib.util.find_spec("hpg_core.analysis_pipeline") is not None
    from hpg_core.analysis_pipeline import finalize_track
    track = SimpleNamespace(neural_analysis={}, native_phrase_analysis={"status": phrase_status}, filePath="test.wav")
    attached, writes = [], []

    def persist(key, value):
        writes.append((key, value))
        return persisted

    result = finalize_track(
        track, cache_policy=policy, cache_key="test", analysis_degraded=degraded,
        anchor_transient=transient, attach_features=attached.append,
        transient_failure=lambda value: False, persist=persist,
        logger=logging.getLogger(__name__),
    )
    assert attached == [track]
    assert len(writes) == expected_writes
    assert (result is track) == success
    assert track.analysis_origin == "fresh"

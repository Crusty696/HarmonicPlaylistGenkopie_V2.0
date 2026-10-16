"""Audio-Raster darf internen Drift beheben, nie externe Taktnummern ersetzen."""
import numpy as np
import pytest
from hpg_core import downbeat as d
from tests.test_downbeat import SR, _make_four_on_floor


@pytest.mark.parametrize('verified', [True, False])
def test_drifting_tracker_requires_audio_grid_and_keeps_known_downbeat(monkeypatch, verified):
    audio = _make_four_on_floor(128., 60., .3)
    times = np.arange(.3, 59., 60 / 128.)
    frames = np.rint((times + np.linspace(0, .8, len(times))) * SR / d.HOP_LENGTH).astype(int)
    monkeypatch.setattr(d.librosa.beat, 'beat_track', lambda **kw: (128., frames))
    if not verified:
        monkeypatch.setattr(d, 'validate_beatgrid_windows',
            lambda *a, **kw: d.BeatgridValidation('mismatch', 3, 20.))
    diagnostic = {}
    anchor, confidence = d.estimate_first_downbeat(audio, SR, 128.,
        diagnostics=diagnostic, _allow_metric_retry=False)
    if verified:
        assert confidence >= d.DOWNBEAT_RELIABLE_MIN
        assert anchor == pytest.approx(.3, abs=d.EXACT_BEAT_SYNC_TOLERANCE_SECONDS)
    else:
        assert (anchor, confidence) == (0., 0.)
        assert diagnostic['reason'] == 'fold_alignment'


def test_external_grid_never_uses_internal_recovery(monkeypatch):
    audio = _make_four_on_floor(120., 60., .3)
    events = [dict(time_s=float(t), position=i % 4 + 1, observed=True)
              for i, t in enumerate(np.arange(.3, 59., .5))]
    monkeypatch.setattr(d, '_align_beat_feature_grid', lambda *a: None)
    def forbidden(*a, **kw):
        pytest.fail('Externe Beatnummern duerfen nicht durch internes Raster ersetzt werden')
    monkeypatch.setattr(d, 'validate_beatgrid_windows', forbidden)
    diagnostic = {}
    assert d.estimate_first_downbeat(audio, SR, 120., external_beats=events,
        diagnostics=diagnostic) == (0., 0.)
    assert diagnostic['reason'] == 'external_alignment'

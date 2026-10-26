"""Lokaler Retry: drei getrennte Taktphasen plus unveraendertes Gesamtgrid."""
import numpy as np
import pytest
from hpg_core import analysis


@pytest.mark.parametrize('failure', [None, 'weak', 'rotation', 'grid'])
def test_local_retry_requires_every_window_and_grid(monkeypatch, failure):
    def full(*args, diagnostics, **kwargs):
        diagnostics.update(reason='fold_alignment', stage='fold')
        return 0., 0.
    monkeypatch.setattr(analysis, '_estimate_audio_downbeat_full', full)
    seen = []
    def estimate(audio, sr, bpm, **kwargs):
        seen.append(float(audio[0]))
        assert len(audio) == 160 and kwargs['_fixed_bpm'] is True
        kwargs['diagnostics'].update(reason='ok', stage='result')
        return (.7 if failure == 'rotation' and len(seen) == 2 else .2,
                .1 if failure == 'weak' and len(seen) == 2 else .6)
    monkeypatch.setattr(analysis, 'estimate_first_downbeat', estimate)
    grids = []
    def grid(*args, **kwargs):
        grids.append(args[3])
        return analysis.BeatgridValidation('mismatch' if failure == 'grid' else 'verified', 3, 0.)
    monkeypatch.setattr(analysis, '_validate_track_beatgrid', grid)
    diagnostic = {}
    result = analysis._estimate_audio_downbeat(np.arange(1000.), 10, 120.,
        file_path='unused', duration=100., diagnostics=diagnostic)
    if failure is None:
        assert result == pytest.approx((.2, .6))
        assert seen == [120., 420., 720.]
        assert grids == pytest.approx([.2])
        assert diagnostic['retry_reason'] == 'fold_alignment'
    else:
        assert result == (0., 0.)
        assert diagnostic['reason'] == 'fold_alignment'
        if failure != 'grid':
            assert grids == []

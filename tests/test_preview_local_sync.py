"""Lokaler Beatversatz zwischen den bisherigen drei Messfenstern."""
import numpy as np
import pytest
from hpg_core.transition_renderer import (
    BeatSyncError, _kick_lags_across_overlap, _synchronize_and_verify_kicks,
)


@pytest.mark.parametrize('local_delay', [0.0, 0.025])
def test_sync_covers_local_drift_between_three_probes(local_delay):
    sr = 8000
    count = sr * 32
    a, b = np.zeros(count), np.zeros(count)
    t = np.arange(int(sr * 0.15)) / sr
    kick = np.sin(2 * np.pi * 65 * t) * np.exp(-t * 35)
    for beat in np.arange(0.25, 31.5, 0.5):
        pos_a = round(beat * sr)
        pos_b = pos_a + (round(local_delay * sr) if 4 <= beat < 6 else 0)
        a[pos_a:pos_a + len(kick)] += kick
        b[pos_b:pos_b + len(kick)] += kick
    a, b = np.column_stack((a, a)), np.column_stack((b, b))
    # Die alte Stichprobe akzeptiert auch den absichtlich gestoerten Fall.
    assert max(abs(x) for x in _kick_lags_across_overlap(a, b, sr, 120, count)) < 0.006
    if local_delay:
        with pytest.raises(BeatSyncError, match='Blendenabschnitt'):
            _synchronize_and_verify_kicks(a, b, sr, 120, count)
    else:
        np.testing.assert_allclose(_synchronize_and_verify_kicks(a, b, sr, 120, count), b)

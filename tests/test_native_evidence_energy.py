"""Break-Auswahl unabhängig von Referenzphase und Lautheitsnormalisierung."""
import numpy as np
import pytest

from hpg_core.ai_models.native_evidence_energy import (
    eligible_starts, second_energy, source_energy,
)


def test_break_is_excluded_before_any_phase_measurement():
    energy = np.ones(160)
    energy[65:95] = .1
    selected = eligible_starts(energy, 16)
    assert 0 in selected and 120 in selected
    assert all(start + 16 <= 65 or start >= 95 for start in selected)
    assert selected == eligible_starts(energy * .001, 16)


def test_silence_cannot_supply_evidence_windows():
    assert not eligible_starts(np.zeros(160), 16)


def test_energy_is_band_limited_not_a_high_frequency_hat_measurement():
    sr = 4000
    time = np.arange(sr * 20) / sr
    bass = second_energy(np.sin(2 * np.pi * 70 * time), sr)[1:]
    hats = second_energy(np.sin(2 * np.pi * 1700 * time), sr)[1:]
    assert bass.mean() > .4
    assert hats.mean() < bass.mean() * .001


@pytest.mark.parametrize('energy', [[-1., 1.], [float('nan')], [float('inf')]])
def test_invalid_energy_is_not_accepted(energy):
    with pytest.raises(ValueError):
        eligible_starts(energy, 16)


def test_existing_head_is_not_decoded_again_and_tail_reads_are_bounded():
    calls = []
    def loader(path, *, sr, offset, duration):
        calls.append((offset, duration))
        return np.zeros(sr * duration), sr
    energy = source_energy("fixture", 141.5, np.zeros(8000 * 20), 8000, loader)
    assert len(energy) == 141
    assert calls == [(20, 60), (80, 60), (140, 1)]


def test_six_model_windows_avoid_break_before_phase_is_known():
    from hpg_core.ai_models.native_beat_alignment import single_window_evidence_plan
    from tests.test_native_track_beats import snapshot
    native = snapshot(240.)
    native['model_beats'] = [[float(t), i % 4 + 1]
                             for i, t in enumerate(np.arange(.5, 240, .5))]
    energy = np.ones(240)
    energy[100:145] = .1
    allowed = eligible_starts(energy, 16)
    plan = single_window_evidence_plan(native, 240., 16., eligible_starts=allowed)
    assert plan is not None
    starts = sum(plan, ())
    assert len(starts) == 6 and all(start in allowed for start in starts)
    assert all(abs(a - b) >= 16 for i, a in enumerate(starts) for b in starts[i+1:])

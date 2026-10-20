"""Modellfenster aus gespeicherten Beats, ohne weitere Audio-/Modellläufe."""
from hpg_core.ai_models.native_beat_selection import stable_full_window_start


def test_skips_variable_intro_and_keeps_chunk_seams():
    rows = [[float(i) * .8, i % 4 + 1] for i in range(50)]
    rows += [[40. + i * .5, i % 4 + 1] for i in range(280)]
    rows.insert(next(i for i, row in enumerate(rows) if row[0] == 60.), [60., 4])
    start = stable_full_window_start(rows, 180 * 44100)
    assert start is not None and 39 * 44100 <= start <= 41 * 44100


def test_missing_coverage_does_not_supply_a_window():
    assert stable_full_window_start([[float(i), 1] for i in range(65)], 60 * 44100) is None
    assert stable_full_window_start([], 180 * 44100) is None

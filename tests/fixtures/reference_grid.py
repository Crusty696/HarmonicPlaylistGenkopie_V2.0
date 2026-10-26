"""Kontrollierter Taktvergleich für Pipeline-Tests, kein Modellnachweis."""

# Vor dem Monkeypatch binden, damit der echte Vergleich keine Rekursion auslöst.
from hpg_core.analysis import _compare_rekordbox_bar_positions as _compare


def aligned_comparison(bpm, grid, _windows, **_kwargs):
    windows = []
    for start in (0., 8., 16.):
        beats = [
            dict(time_s=row["time"], position=row["beat"], observed=True)
            for row in grid if start <= row["time"] < start + 8.
        ]
        windows.append(dict(start_s=start, duration_s=8., results=[
            dict(model_id=model, status="ok",
                 decoder=dict(status="ok", ambiguous=False, beats=beats))
            for model in ("model7", "model8")
        ]))
    return _compare(bpm, grid, windows)



"""Fraktionale Originaltrack-Dauern dürfen keine Sektionsüberlappung erzeugen."""
from dataclasses import asdict

import numpy as np
import pytest

from hpg_core import analysis
from hpg_core.caching import _validate_sections, _validate_coverage_sections
from hpg_core.structure_analyzer import TrackSection, TrackStructure


@pytest.mark.parametrize("duration", [576.0869614512471, 542.5351020408164])
def test_tail_gap_has_exact_shared_boundary(monkeypatch, duration):
    def structure(audio, sr, *args, **kwargs):
        return TrackStructure(
            sections=[TrackSection("main", 0., len(audio) / sr, 0, 100, 50.)],
            total_bars=100, phrase_unit=8,
        )

    monkeypatch.setattr(analysis, "analyze_structure", structure)
    monkeypatch.setattr(
        analysis, "_load_analysis_audio",
        lambda *args, **kwargs: (np.zeros(1800, dtype=np.float32), 10),
    )
    result, coverage, _ = analysis.analyze_structure_windows(
        "source.aiff", np.zeros(3600, dtype=np.float32), 10,
        140., "Psytrance", duration,
    )
    sections = [asdict(section) for section in result.sections]
    _validate_sections(sections, duration)
    _validate_coverage_sections(
        [(part["start"], part["end"]) for part in coverage], sections, duration,
    )
    gap = next(i for i, section in enumerate(sections)
               if section["label"] == "unanalysed")
    assert sections[gap]["end_time"] == sections[gap + 1]["start_time"]

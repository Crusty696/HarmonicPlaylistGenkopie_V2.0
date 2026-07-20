"""Regressionstests fuer Tail-Coverage und vollstaendige LUFS-Provenienz."""

import numpy as np

from hpg_core.analysis import analyze_structure_windows, calculate_file_lufs
from hpg_core.structure_analyzer import TrackSection, TrackStructure


def test_structure_windows_include_real_tail_and_mark_gap(monkeypatch):
  from hpg_core import analysis

  sr = 10
  head = np.zeros(360 * sr, dtype=np.float32)
  tail = np.zeros(180 * sr, dtype=np.float32)

  def fake_structure(audio, sample_rate, bpm, genre, anchor=0.0):
    duration = len(audio) / sample_rate
    return TrackStructure(
      sections=[
        TrackSection("main", 0.0, duration / 2, 0, 32, 70.0),
        TrackSection("outro", duration / 2, duration, 32, 64, 30.0),
      ],
      total_bars=64,
      phrase_unit=8,
    )

  monkeypatch.setattr(analysis, "analyze_structure", fake_structure)
  monkeypatch.setattr(analysis.librosa, "load", lambda *args, **kwargs: (tail, sr))

  structure, coverage, outro_covered = analyze_structure_windows(
    "long.wav", head, sr, 120.0, "Techno", 600.0
  )

  assert coverage == [{"start": 0.0, "end": 360.0}, {"start": 420.0, "end": 600.0}]
  assert any(section.label == "unanalysed" for section in structure.sections)
  assert structure.sections[-1].label == "outro"
  assert structure.sections[-1].end_time == 600.0
  assert outro_covered is True


def test_file_lufs_uses_complete_native_stereo(tmp_path):
  import soundfile as sf

  sr = 48000
  seconds = 3
  time = np.arange(sr * seconds) / sr
  mono = 0.1 * np.sin(2 * np.pi * 440 * time)
  stereo = np.column_stack([mono, mono]).astype(np.float32)
  path = tmp_path / "stereo.wav"
  sf.write(path, stereo, sr)

  lufs, status, coverage, channels, sample_rate = calculate_file_lufs(str(path))

  assert lufs < 0
  assert status == "complete"
  assert coverage == seconds
  assert channels == 2
  assert sample_rate == sr

"""Regressionstests fuer Tail-Coverage und vollstaendige LUFS-Provenienz."""

import numpy as np

from hpg_core.analysis import (
  FeatureCache,
  _median_seconds_per_bar,
  analyze_structure_windows,
  calculate_file_lufs,
)
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


def test_structure_windows_degrades_when_tail_decode_fails(monkeypatch):
  from hpg_core import analysis

  sr = 10
  head_audio = np.zeros(360 * sr, dtype=np.float32)

  def fake_structure(audio, sample_rate, bpm, genre, anchor=0.0):
    duration = len(audio) / sample_rate
    return TrackStructure(
      sections=[TrackSection("outro", 0.0, duration, 0, 180, 50.0)],
      total_bars=180,
      phrase_unit=8,
    )

  monkeypatch.setattr(analysis, "analyze_structure", fake_structure)

  def fail_tail_decode(*args, **kwargs):
    raise RuntimeError("tail decode failed")

  monkeypatch.setattr(analysis.librosa, "load", fail_tail_decode)

  structure, coverage, outro_covered = analyze_structure_windows(
    "long.wav", head_audio, sr, 120.0, "Techno", 600.0
  )

  assert coverage == [{"start": 0.0, "end": 360.0}]
  assert structure.sections[0].label == "main"
  assert structure.sections[-1].label == "unanalysed"
  assert structure.sections[-1].end_time == 600.0
  assert outro_covered is False


def test_structure_windows_rounding_never_exceeds_raw_duration(monkeypatch):
  """Eine auf Centisekunden gerundete Grenze bleibt cache-validierbar."""
  from hpg_core import analysis

  sr = 100
  raw_duration = 367.0668480725624
  head_audio = np.zeros(10 * sr, dtype=np.float32)
  tail_audio = np.zeros(180 * sr, dtype=np.float32)

  def fake_structure(audio, sample_rate, bpm, genre, anchor=0.0):
    local_duration = len(audio) / sample_rate
    return TrackStructure(
      sections=[TrackSection("main", 0.0, local_duration, 0, 1, 50.0)],
      total_bars=1,
      phrase_unit=8,
    )

  monkeypatch.setattr(analysis, "analyze_structure", fake_structure)
  monkeypatch.setattr(
    analysis.librosa,
    "load",
    lambda *args, **kwargs: (tail_audio, sr),
  )

  structure, coverage, _ = analyze_structure_windows(
    "fractional.aif", head_audio, sr, 140.0, "Psytrance", raw_duration
  )

  assert coverage[-1]["end"] == raw_duration
  assert all(window["end"] <= raw_duration for window in coverage)
  assert all(section.end_time <= raw_duration for section in structure.sections)


def test_complete_head_fractional_duration_is_cache_valid(monkeypatch):
  from hpg_core import analysis
  from hpg_core.caching import track_to_dict, validate_track_dict
  from hpg_core.models import Track

  sr = 100
  raw_duration = 367.0668480725624
  head_audio = np.zeros(368 * sr, dtype=np.float32)

  monkeypatch.setattr(
    analysis,
    "analyze_structure",
    lambda *args, **kwargs: TrackStructure(
      sections=[TrackSection("main", 0.0, raw_duration, 0, 1, 50.0)],
      total_bars=1,
      phrase_unit=8,
    ),
  )

  structure, coverage, _ = analyze_structure_windows(
    "fractional.aif", head_audio, sr, 140.0, "Psytrance", raw_duration
  )
  track = Track(
    filePath="C:/fractional.aif",
    fileName="fractional.aif",
    duration=raw_duration,
    bpm=140.0,
    analysis_mode="librosa_full_or_tail",
    sections=[section.to_dict() for section in structure.sections],
    analysis_coverage=coverage,
  )

  validated = validate_track_dict(track_to_dict(track))
  assert validated["analysis_coverage"] == [{"start": 0.0, "end": raw_duration}]


def test_fractional_tail_decode_error_remains_within_duration(monkeypatch):
  from hpg_core import analysis

  sr = 100
  raw_duration = 600.006
  head_audio = np.zeros(360 * sr, dtype=np.float32)
  monkeypatch.setattr(
    analysis,
    "analyze_structure",
    lambda *args, **kwargs: TrackStructure(
      sections=[TrackSection("outro", 0.0, 360.0, 0, 1, 50.0)],
      total_bars=1,
      phrase_unit=8,
    ),
  )
  monkeypatch.setattr(
    analysis.librosa,
    "load",
    lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("tail kaputt")),
  )

  structure, coverage, _ = analyze_structure_windows(
    "fractional.aif", head_audio, sr, 140.0, "Psytrance", raw_duration
  )

  assert coverage[0]["end"] <= raw_duration
  assert structure.sections[-1].end_time == raw_duration


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


def test_file_lufs_blockwise_matches_pyloudnorm(tmp_path):
  """Blockweises LUFS bleibt numerisch auf der bisherigen Referenz."""
  import pyloudnorm as pyln
  import soundfile as sf

  sr = 48000
  rng = np.random.default_rng(42)
  audio = (0.1 * rng.standard_normal((sr * 3, 2))).astype(np.float32)
  path = tmp_path / "reference.wav"
  sf.write(path, audio, sr)

  streamed, status, *_ = calculate_file_lufs(str(path))
  reference = pyln.Meter(sr, filter_class="DeMan").integrated_loudness(
    audio.astype(np.float64)
  )

  assert status == "complete"
  assert abs(streamed - round(float(reference), 2)) <= 0.01


def test_feature_cache_reuses_same_feature_matrix():
  """Wiederholte Feature-Anfragen führen keine zweite Berechnung aus."""
  sr = 22050
  audio = np.zeros(sr * 2, dtype=np.float32)
  cache = FeatureCache(audio, sr)

  first_mfcc = cache.get_mfcc(n_mfcc=13, hop_length=1024)
  second_mfcc = cache.get_mfcc(n_mfcc=13, hop_length=1024)
  first_rms = cache.get_rms(hop_length=1024)
  second_rms = cache.get_rms(hop_length=1024)

  assert first_mfcc is second_mfcc
  assert first_rms is second_rms


def test_median_ibi_reuse_returns_bar_length():
  """Die Struktur kann die gemessene statt der gerundeten BPM-Taktlänge nutzen."""
  frames = np.array([0, 100, 201, 301, 402, 502, 603, 703], dtype=np.int64)
  bar_length = _median_seconds_per_bar(
    frames,
    sr=1000,
    bpm=60.0,
    hop_length=10,
  )

  assert bar_length is not None
  assert abs(bar_length - 4.0) < 0.05

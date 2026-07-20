"""Realer Decode-Smoke-Test fuer alle von der GUI angebotenen Audioformate."""

import math

import numpy as np
import pytest
import soundfile as sf

from hpg_core.analysis import analyze_track


@pytest.mark.integration
@pytest.mark.requires_audio
@pytest.mark.parametrize(
  ("extension", "container", "subtype"),
  [
    ("wav", "WAV", "PCM_16"),
    ("aiff", "AIFF", "PCM_16"),
    ("flac", "FLAC", "PCM_16"),
    ("mp3", "MP3", "MPEG_LAYER_III"),
  ],
)
def test_supported_codec_decodes_through_full_pipeline(
  tmp_path, monkeypatch, extension, container, subtype
):
  """Prueft den technischen Decode-Vertrag, nicht musikalische Genauigkeit."""
  sample_rate = 22050
  duration = 6.0
  samples = np.arange(int(sample_rate * duration), dtype=np.float64)
  tone = 0.2 * np.sin(2.0 * np.pi * 220.0 * samples / sample_rate)
  click_interval = sample_rate // 2
  tone[::click_interval] += 0.7
  audio_path = tmp_path / f"codec_probe.{extension}"
  sf.write(audio_path, tone, sample_rate, format=container, subtype=subtype)
  monkeypatch.setattr(
    "hpg_core.analysis.get_rekordbox_importer",
    lambda: type("NoRekordbox", (), {"get_track_data": lambda self, _path: None})(),
  )

  track = analyze_track(str(audio_path))

  assert track is not None
  assert track.fileName == audio_path.name
  assert track.duration == pytest.approx(duration, abs=0.25)
  assert math.isfinite(track.bpm) and track.bpm > 0
  assert math.isfinite(float(track.energy))
  assert 0 <= float(track.energy) <= 100
  assert track.analysis_mode

from types import SimpleNamespace

from tools.run_ground_truth_predictions import prediction_from_track


def test_prediction_from_track_uses_analysis_contract_fields():
  track = SimpleNamespace(
    bpm=128.0,
    keyNote="A",
    keyMode="Minor",
    detected_genre="Tech House",
    genre="House",
    mix_in_point=16.0,
    mix_out_point=200.0,
    sections=[{"start_time": 0.0}, {"start_time": 32.0}],
    analysis_mode="full",
    analysis_coverage=[{"start": 0.0, "end": 240.0}],
  )

  result = prediction_from_track("t1", "a" * 64, track)

  assert result["track_id"] == "t1"
  assert result["audio_sha256"] == "a" * 64
  assert result["genre"] == "Tech House"
  assert result["sections"] == track.sections

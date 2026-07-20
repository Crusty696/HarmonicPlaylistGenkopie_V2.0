import pytest

from tools.evaluate_ground_truth import (
  boundary_counts,
  evaluate,
  key_classification,
  validate_ground_truth_provenance,
  validate_prediction_metadata,
)


def test_key_classification_contract():
  assert key_classification("A", "Minor", "A", "Minor") == "exact"
  assert key_classification("C", "Major", "A", "Minor") == "relative"
  assert key_classification("E", "Minor", "A", "Minor") == "fifth"
  assert key_classification("gb", "major", "F#", "Major") == "exact"
  assert key_classification("?", "Minor", "A", "Minor") == "invalid"


def test_boundary_matching_is_one_to_one():
  assert boundary_counts([9.5, 10.5, 30.0], [10.0, 30.0]) == (2, 3, 2)
  assert boundary_counts([1, 4], [2.9, 5], tolerance=2) == (2, 2, 2)


def test_evaluate_reports_only_present_labels():
  truth = [{
    "track_id": "t1",
    "label_status": "adjudicated",
    "truth_bpm": "128",
    "truth_key_note": "A",
    "truth_key_mode": "Minor",
    "truth_genre": "Tech House",
    "truth_mix_in_seconds": "16",
    "truth_mix_out_seconds": "200",
    "truth_sections_json": "[32, 64, 128]",
  }]
  predictions = [{
    "track_id": "t1",
    "bpm": 64,
    "key_note": "A",
    "key_mode": "Minor",
    "genre": "tech_house",
    "mix_in_seconds": 18,
    "mix_out_seconds": 196,
    "sections": [{"start_time": 0}, {"start_time": 31}, {"start_time": 65}, {"start_time": 128}],
  }]

  result = evaluate(truth, predictions)

  assert result["matched_tracks"] == 1
  assert result["bpm"]["within_0_5"] == 1.0
  assert result["key"]["counts"]["exact"] == 1
  assert result["genre"]["exact_accuracy"] == 1.0
  assert result["cues"]["mix_in"]["mae_seconds"] == 2.0
  assert result["sections"]["f1"] == 1.0


def test_evaluate_does_not_invent_missing_measurements():
  result = evaluate(
    [{"track_id": "t1", "label_status": "adjudicated"}],
    [{"track_id": "t1"}],
  )
  assert result["bpm"]["labeled"] == 0
  assert result["bpm"]["mae_octave_aware"] is None
  assert result["genre"]["exact_accuracy"] is None


def test_excluded_rows_do_not_contribute_and_missing_predictions_reduce_coverage():
  truth = [
    {"track_id": "excluded", "label_status": "excluded", "truth_bpm": "128"},
    {"track_id": "covered", "label_status": "adjudicated", "truth_bpm": "128"},
    {"track_id": "missing", "label_status": "adjudicated", "truth_bpm": "130"},
  ]
  result = evaluate(truth, [{"track_id": "covered", "bpm": 128}])
  assert result["adjudicated_ground_truth_tracks"] == 2
  assert result["prediction_track_coverage"] == 0.5
  assert result["bpm"]["prediction_coverage"] == 0.5


def test_zero_section_matches_report_zero_f1():
  truth = [{
    "track_id": "t1",
    "label_status": "adjudicated",
    "truth_sections_json": "[10]",
  }]
  result = evaluate(truth, [{"track_id": "t1", "sections": [30]}])
  assert result["sections"]["f1"] == 0.0


def test_missing_section_predictions_reduce_recall_and_coverage():
  truth = [
    {
      "track_id": "covered",
      "label_status": "adjudicated",
      "truth_sections_json": "[10]",
    },
    {
      "track_id": "missing",
      "label_status": "adjudicated",
      "truth_sections_json": "[20]",
    },
  ]
  result = evaluate(truth, [{"track_id": "covered", "sections": [10]}])
  assert result["sections"]["prediction_coverage"] == 0.5
  assert result["sections"]["truth_boundaries"] == 2
  assert result["sections"]["recall"] == 0.5


def test_duplicate_ids_are_rejected():
  truth = [{"track_id": "t1", "label_status": "adjudicated"}]
  with pytest.raises(ValueError, match="Doppelte track_id"):
    evaluate(truth, [{"track_id": "t1"}, {"track_id": "t1"}])


def test_adjudicated_cli_data_requires_provenance():
  with pytest.raises(ValueError, match="ohne"):
    validate_ground_truth_provenance([
      {"track_id": "t1", "label_status": "adjudicated"}
    ])

  validate_ground_truth_provenance([{
    "track_id": "t1",
    "label_status": "adjudicated",
    "audio_sha256": "a" * 64,
    "label_source": "independent review",
    "annotator_1": "dj-01",
    "annotator_2": "dj-02",
    "adjudicator": "dj-03",
  }])


def test_prediction_metadata_contract():
  with pytest.raises(ValueError, match="unvollstaendig"):
    validate_prediction_metadata({})
  validate_prediction_metadata({
    "app_version": "3.7.0",
    "source_commit": "abc123",
    "config_sha256": "b" * 64,
    "created_at": "2026-07-20T00:00:00Z",
  })

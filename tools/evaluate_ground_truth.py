"""Bewertet HPG-Vorhersagen gegen unabhaengig gepflegte Ground-Truth-Labels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hpg_core.models import CAMELOT_MAP, get_camelot_components  # noqa: E402


FLAT_TO_SHARP = {"DB": "C#", "EB": "D#", "GB": "F#", "AB": "G#", "BB": "A#"}


def _file_sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def _is_sha256(value: str) -> bool:
  return len(value) == 64 and all(char in "0123456789abcdef" for char in value.casefold())


def validate_ground_truth_provenance(rows: list[dict]) -> None:
  required = ("audio_sha256", "label_source", "annotator_1", "annotator_2", "adjudicator")
  for row in rows:
    if _normalized(row.get("label_status")) != "adjudicated":
      continue
    missing = [name for name in required if not str(row.get(name, "")).strip()]
    if missing:
      raise ValueError(f"Adjudicated Track {row.get('track_id')} ohne {missing}")
    if not _is_sha256(str(row["audio_sha256"]).strip()):
      raise ValueError(f"Ungueltiger audio_sha256 fuer {row.get('track_id')}")


def validate_prediction_metadata(metadata) -> None:
  required = ("app_version", "source_commit", "config_sha256", "created_at")
  if not isinstance(metadata, dict):
    raise ValueError("Vorhersagen brauchen ein metadata-Objekt")
  missing = [name for name in required if not str(metadata.get(name, "")).strip()]
  if missing:
    raise ValueError(f"Prediction-Metadaten unvollstaendig: {missing}")
  if not _is_sha256(str(metadata["config_sha256"]).strip()):
    raise ValueError("Prediction config_sha256 ist ungueltig")


def _optional_float(value):
  if value in (None, ""):
    return None
  number = float(value)
  if not math.isfinite(number):
    raise ValueError("Nicht-endlicher Zahlenwert in Validierungsdaten")
  return number


def _normalized(value) -> str:
  return " ".join(str(value or "").casefold().replace("_", " ").split())


def _normalized_note(value) -> str:
  note = str(value or "").strip().upper()
  return FLAT_TO_SHARP.get(note, note.replace("B", "b") if len(note) == 2 else note)


def _normalized_mode(value) -> str:
  mode = str(value or "").strip().casefold()
  return {"major": "Major", "minor": "Minor"}.get(mode, "")


def octave_aware_bpm_error(predicted: float, truth: float) -> float:
  return min(
    abs(predicted - truth),
    abs(predicted * 2.0 - truth),
    abs(predicted / 2.0 - truth),
  )


def key_classification(pred_note, pred_mode, truth_note, truth_mode) -> str:
  predicted = CAMELOT_MAP.get(
    (_normalized_note(pred_note), _normalized_mode(pred_mode)), ""
  )
  truth = CAMELOT_MAP.get(
    (_normalized_note(truth_note), _normalized_mode(truth_mode)), ""
  )
  if not predicted or not truth:
    return "invalid"
  if predicted == truth:
    return "exact"
  pred_num, pred_letter = get_camelot_components(predicted)
  truth_num, truth_letter = get_camelot_components(truth)
  distance = min(abs(pred_num - truth_num), 12 - abs(pred_num - truth_num))
  if distance == 0 and pred_letter != truth_letter:
    return "relative"
  if distance == 1 and pred_letter == truth_letter:
    return "fifth"
  return "wrong"


def _boundaries(value) -> list[float]:
  if value in (None, "", []):
    return []
  parsed = json.loads(value) if isinstance(value, str) else value
  if not isinstance(parsed, list):
    raise ValueError("Sektionslabels muessen eine JSON-Liste sein")
  if all(isinstance(item, (int, float)) for item in parsed):
    result = [float(item) for item in parsed if float(item) > 0]
  else:
    result = [float(item["start_time"]) for item in parsed if float(item["start_time"]) > 0]
  if not all(math.isfinite(item) and item >= 0 for item in result):
    raise ValueError("Ungueltige Sektionsgrenze")
  return sorted(set(result))


def boundary_counts(predicted, truth, tolerance=2.0) -> tuple[int, int, int]:
  predicted_boundaries = _boundaries(predicted)
  truth_boundaries = _boundaries(truth)
  matched_prediction: dict[int, int] = {}

  def augment(truth_index: int, visited: set[int]) -> bool:
    candidates = sorted(
      range(len(predicted_boundaries)),
      key=lambda index: abs(predicted_boundaries[index] - truth_boundaries[truth_index]),
    )
    for prediction_index in candidates:
      if prediction_index in visited:
        continue
      if abs(predicted_boundaries[prediction_index] - truth_boundaries[truth_index]) > tolerance:
        continue
      visited.add(prediction_index)
      previous_truth = matched_prediction.get(prediction_index)
      if previous_truth is None or augment(previous_truth, visited):
        matched_prediction[prediction_index] = truth_index
        return True
    return False

  matches = sum(augment(index, set()) for index in range(len(truth_boundaries)))
  return matches, len(predicted_boundaries), len(truth_boundaries)


def _unique_by_track_id(rows: list[dict], source: str) -> dict[str, dict]:
  indexed = {}
  for row in rows:
    track_id = str(row.get("track_id", "")).strip()
    if not track_id:
      raise ValueError(f"Jeder {source}-Datensatz braucht track_id")
    if track_id in indexed:
      raise ValueError(f"Doppelte track_id in {source}: {track_id}")
    indexed[track_id] = row
  return indexed


def evaluate(ground_truth: list[dict], predictions: list[dict]) -> dict:
  all_truth_by_id = _unique_by_track_id(ground_truth, "Ground Truth")
  prediction_by_id = _unique_by_track_id(predictions, "Vorhersage")
  truth_by_id = {
    track_id: row
    for track_id, row in all_truth_by_id.items()
    if _normalized(row.get("label_status")) == "adjudicated"
  }

  bpm_errors = []
  key_results = []
  genre_matches = []
  cue_errors = {"mix_in": [], "mix_out": []}
  boundary_total = [0, 0, 0]
  predicted_section_tracks = 0
  matched_tracks = 0

  field_truth_counts = {"bpm": 0, "key": 0, "genre": 0, "mix_in": 0, "mix_out": 0, "sections": 0}

  for track_id, truth in truth_by_id.items():
    prediction = prediction_by_id.get(track_id)

    truth_bpm = _optional_float(truth.get("truth_bpm"))
    if truth_bpm is not None:
      if truth_bpm <= 0:
        raise ValueError(f"truth_bpm muss positiv sein: {track_id}")
      field_truth_counts["bpm"] += 1

    has_truth_key = bool(truth.get("truth_key_note") and truth.get("truth_key_mode"))
    field_truth_counts["key"] += int(has_truth_key)
    field_truth_counts["genre"] += int(bool(truth.get("truth_genre")))
    truth_cues = {}
    for name in cue_errors:
      expected = _optional_float(truth.get(f"truth_{name}_seconds"))
      truth_cues[name] = expected
      if expected is not None:
        if expected < 0:
          raise ValueError(f"truth_{name}_seconds ist negativ: {track_id}")
        field_truth_counts[name] += 1
    if (
      truth_cues["mix_in"] is not None
      and truth_cues["mix_out"] is not None
      and truth_cues["mix_in"] >= truth_cues["mix_out"]
    ):
      raise ValueError(f"Ground-Truth-Mixfenster ist ungueltig: {track_id}")
    truth_sections = truth.get("truth_sections_json")
    field_truth_counts["sections"] += int(bool(truth_sections))

    if prediction is None:
      if truth_sections:
        boundary_total[2] += len(_boundaries(truth_sections))
      continue
    truth_hash = str(truth.get("audio_sha256", "")).strip().casefold()
    prediction_hash = str(prediction.get("audio_sha256", "")).strip().casefold()
    if truth_hash and truth_hash != prediction_hash:
      raise ValueError(f"Audio-Hash stimmt nicht ueberein: {track_id}")
    matched_tracks += 1
    pred_bpm = _optional_float(prediction.get("bpm"))
    if truth_bpm is not None and pred_bpm is not None:
      bpm_errors.append(octave_aware_bpm_error(pred_bpm, truth_bpm))

    if has_truth_key and prediction.get("key_note") and prediction.get("key_mode"):
      key_results.append(key_classification(
        prediction["key_note"], prediction["key_mode"],
        truth["truth_key_note"], truth["truth_key_mode"],
      ))

    if truth.get("truth_genre") and prediction.get("genre"):
      genre_matches.append(
        _normalized(truth["truth_genre"]) == _normalized(prediction["genre"])
      )

    for name in cue_errors:
      expected = _optional_float(truth.get(f"truth_{name}_seconds"))
      actual = _optional_float(prediction.get(f"{name}_seconds"))
      if expected is not None and actual is not None:
        cue_errors[name].append(abs(actual - expected))

    if truth_sections:
      if prediction.get("sections") is not None:
        predicted_section_tracks += 1
        counts = boundary_counts(prediction["sections"], truth_sections)
        boundary_total = [a + b for a, b in zip(boundary_total, counts)]
      else:
        boundary_total[2] += len(_boundaries(truth_sections))

  matches, predicted_count, truth_count = boundary_total
  precision = matches / predicted_count if predicted_count else None
  recall = matches / truth_count if truth_count else None
  if truth_count and matches == 0:
    f1 = 0.0
  elif precision is not None and recall is not None and precision + recall:
    f1 = 2 * precision * recall / (precision + recall)
  else:
    f1 = None

  return {
    "schema_version": 1,
    "ground_truth_tracks": len(ground_truth),
    "adjudicated_ground_truth_tracks": len(truth_by_id),
    "prediction_tracks": len(predictions),
    "matched_tracks": matched_tracks,
    "prediction_track_coverage": matched_tracks / len(truth_by_id) if truth_by_id else None,
    "bpm": {
      "truth_labeled": field_truth_counts["bpm"],
      "labeled": len(bpm_errors),
      "prediction_coverage": len(bpm_errors) / field_truth_counts["bpm"] if field_truth_counts["bpm"] else None,
      "mae_octave_aware": sum(bpm_errors) / len(bpm_errors) if bpm_errors else None,
      "within_0_5": sum(error <= 0.5 for error in bpm_errors) / len(bpm_errors) if bpm_errors else None,
    },
    "key": {
      "truth_labeled": field_truth_counts["key"],
      "labeled": len(key_results),
      "prediction_coverage": len(key_results) / field_truth_counts["key"] if field_truth_counts["key"] else None,
      "counts": {name: key_results.count(name) for name in ("exact", "relative", "fifth", "wrong", "invalid")},
    },
    "genre": {
      "truth_labeled": field_truth_counts["genre"],
      "labeled": len(genre_matches),
      "prediction_coverage": len(genre_matches) / field_truth_counts["genre"] if field_truth_counts["genre"] else None,
      "exact_accuracy": sum(genre_matches) / len(genre_matches) if genre_matches else None,
    },
    "cues": {
      name: {
        "truth_labeled": field_truth_counts[name],
        "labeled": len(errors),
        "prediction_coverage": len(errors) / field_truth_counts[name] if field_truth_counts[name] else None,
        "mae_seconds": sum(errors) / len(errors) if errors else None,
      }
      for name, errors in cue_errors.items()
    },
    "sections": {
      "truth_labeled_tracks": field_truth_counts["sections"],
      "predicted_labeled_tracks": predicted_section_tracks,
      "prediction_coverage": (
        predicted_section_tracks / field_truth_counts["sections"]
        if field_truth_counts["sections"] else None
      ),
      "matched_boundaries": matches,
      "predicted_boundaries": predicted_count,
      "truth_boundaries": truth_count,
      "tolerance_seconds": 2.0,
      "precision": precision,
      "recall": recall,
      "f1": f1,
    },
  }


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--ground-truth", required=True, type=Path)
  parser.add_argument("--predictions", required=True, type=Path)
  parser.add_argument("--output", required=True, type=Path)
  args = parser.parse_args()

  with args.ground_truth.open(encoding="utf-8-sig", newline="") as handle:
    truth = list(csv.DictReader(handle))
  validate_ground_truth_provenance(truth)
  prediction_document = json.loads(args.predictions.read_text(encoding="utf-8"))
  if not isinstance(prediction_document, dict) or not isinstance(
    prediction_document.get("predictions"), list
  ):
    raise ValueError("Vorhersagen brauchen metadata und eine predictions-Liste")
  metadata = prediction_document.get("metadata")
  validate_prediction_metadata(metadata)
  result = evaluate(truth, prediction_document["predictions"])
  result["prediction_metadata"] = metadata
  result["input_sha256"] = {
    "ground_truth": _file_sha256(args.ground_truth),
    "predictions": _file_sha256(args.predictions),
  }
  args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

"""Erzeugt reproduzierbare HPG-Predictions fuer ein Ground-Truth-Manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def file_sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def git_commit() -> str:
  result = subprocess.run(
    ["git", "rev-parse", "HEAD"],
    cwd=ROOT,
    capture_output=True,
    text=True,
    check=True,
  )
  return result.stdout.strip()


def prediction_from_track(track_id: str, audio_sha256: str, track) -> dict:
  return {
    "track_id": track_id,
    "audio_sha256": audio_sha256,
    "bpm": track.bpm,
    "key_note": track.keyNote,
    "key_mode": track.keyMode,
    "genre": track.detected_genre or track.genre,
    "mix_in_seconds": track.mix_in_point,
    "mix_out_seconds": track.mix_out_point,
    "sections": track.sections,
    "analysis_mode": track.analysis_mode,
    "analysis_coverage": track.analysis_coverage,
  }


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--ground-truth", required=True, type=Path)
  parser.add_argument("--output", required=True, type=Path)
  parser.add_argument(
    "--audio-root",
    type=Path,
    help="Erlaubter Audio-Root; Standard ist das Verzeichnis des Manifests.",
  )
  parser.add_argument("--allow-rekordbox", action="store_true")
  args = parser.parse_args()

  if not args.allow_rekordbox:
    os.environ["HPG_DISABLE_REKORDBOX"] = "1"

  from hpg_core.analysis import analyze_track
  from hpg_core.app_metadata import APP_VERSION
  from tools.evaluate_ground_truth import validate_ground_truth_provenance

  with args.ground_truth.open(encoding="utf-8-sig", newline="") as handle:
    rows = list(csv.DictReader(handle))
  validate_ground_truth_provenance(rows)
  eligible = [
    row for row in rows
    if str(row.get("label_status", "")).strip().casefold() == "adjudicated"
  ]

  predictions = []
  audio_root = (args.audio_root or args.ground_truth.parent).resolve()
  for row in eligible:
    audio_path = Path(row["audio_path"])
    if not audio_path.is_absolute():
      audio_path = args.ground_truth.resolve().parent / audio_path
    audio_path = audio_path.resolve()
    if not audio_path.is_relative_to(audio_root):
      raise ValueError(
        f"Audio-Pfad ausserhalb des erlaubten Audio-Roots fuer {row['track_id']}: "
        f"{audio_path}"
      )
    if not audio_path.is_file():
      raise FileNotFoundError(f"Audio fehlt fuer {row['track_id']}: {audio_path}")
    digest = file_sha256(audio_path)
    if digest.casefold() != row["audio_sha256"].strip().casefold():
      raise ValueError(f"Audio-Hash stimmt nicht fuer {row['track_id']}")
    track = analyze_track(str(audio_path))
    if track is None:
      raise RuntimeError(f"Analyse fehlgeschlagen fuer {row['track_id']}")
    predictions.append(prediction_from_track(row["track_id"], digest, track))

  document = {
    "metadata": {
      "app_version": APP_VERSION,
      "source_commit": git_commit(),
      "config_sha256": file_sha256(ROOT / "hpg_core" / "config.py"),
      "created_at": datetime.now(timezone.utc).isoformat(),
      "rekordbox_enabled": args.allow_rekordbox,
    },
    "predictions": predictions,
  }
  args.output.parent.mkdir(parents=True, exist_ok=True)
  temporary = args.output.with_name(f".{args.output.name}.tmp")
  temporary.write_text(json.dumps(document, indent=2), encoding="utf-8")
  temporary.replace(args.output)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

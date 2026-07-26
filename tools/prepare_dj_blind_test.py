"""Kopiert Transition-Clips unter neutralen A/B-Namen und trennt den Schluessel."""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import tempfile
import uuid
from pathlib import Path

import soundfile as sf


def _sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def _write_csv(path: Path, data: list[dict]) -> None:
  with path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(data[0]))
    writer.writeheader()
    writer.writerows(data)


def prepare(
  manifest: Path,
  output_dir: Path,
  key_path: Path,
  seed: int | None = None,
  source_root: Path | None = None,
) -> tuple[Path, Path]:
  if output_dir.exists():
    raise FileExistsError(f"Ausgabeordner existiert bereits: {output_dir}")
  if key_path.exists():
    raise FileExistsError(f"Schluesseldatei existiert bereits: {key_path}")
  output_resolved = output_dir.resolve()
  key_resolved = key_path.resolve()
  if output_resolved == key_resolved.parent or output_resolved in key_resolved.parents:
    raise ValueError("Schluesseldatei muss ausserhalb des Session-Ordners liegen")

  manifest = manifest.resolve()
  allowed_root = (source_root or manifest.parent).resolve()
  rows = list(csv.DictReader(manifest.open(encoding="utf-8-sig", newline="")))
  required = {"pair_id", "hpg_clip", "baseline_clip"}
  if not rows or not required.issubset(rows[0]):
    raise ValueError(f"Manifest braucht Spalten: {sorted(required)}")

  validated = []
  seen_pair_ids = set()
  seen_pairs = set()
  for index, row in enumerate(rows, 1):
    pair_id = str(row["pair_id"]).strip()
    if not pair_id or pair_id in seen_pair_ids:
      raise ValueError(f"Leere oder doppelte pair_id: {pair_id or index}")
    seen_pair_ids.add(pair_id)
    sources = []
    for field in ("hpg_clip", "baseline_clip"):
      source = Path(row[field])
      if not source.is_absolute():
        source = manifest.parent / source
      source = source.resolve()
      if not source.is_relative_to(allowed_root):
        raise ValueError(
          f"Clip ausserhalb des erlaubten Source-Roots in Paar {pair_id}: {source}"
        )
      if not source.is_file():
        raise ValueError(f"Clip fehlt in Paar {pair_id}: {source}")
      sources.append(source)
    hashes = tuple(_sha256(source) for source in sources)
    if hashes[0] == hashes[1]:
      raise ValueError(f"A/B-Clips sind byte-identisch: {pair_id}")
    pair_signature = tuple(sorted(hashes))
    if pair_signature in seen_pairs:
      raise ValueError(f"Doppeltes Clip-Paar: {pair_id}")
    seen_pairs.add(pair_signature)
    infos = [sf.info(source) for source in sources]
    if infos[0].samplerate != infos[1].samplerate or infos[0].channels != infos[1].channels:
      raise ValueError(f"Samplerate/Kanalzahl unterscheiden sich: {pair_id}")
    if abs(infos[0].duration - infos[1].duration) > 0.01:
      raise ValueError(f"Clipdauer unterscheidet sich um mehr als 10 ms: {pair_id}")
    validated.append((pair_id, sources, hashes))

  rng = random.Random(seed) if seed is not None else random.SystemRandom()
  session_id = uuid.uuid4().hex[:12]
  rng.shuffle(validated)
  hpg_on_a = [True] * (len(validated) // 2) + [False] * (len(validated) - len(validated) // 2)
  rng.shuffle(hpg_on_a)

  output_dir.parent.mkdir(parents=True, exist_ok=True)
  staging = Path(tempfile.mkdtemp(prefix="hpg_blind_", dir=output_dir.parent))
  clips_dir = staging / "clips"
  clips_dir.mkdir(parents=True)
  public_rows = []
  key_rows = []

  for index, ((pair_id, sources, _hashes), place_hpg_on_a) in enumerate(
    zip(validated, hpg_on_a), 1
  ):
    hpg, baseline = sources
    systems = [("HPG", hpg), ("baseline", baseline)]
    if not place_hpg_on_a:
      systems.reverse()
    blinded = []
    for side, (system, source) in zip(("A", "B"), systems):
      candidate_id = f"pair_{index:03d}_{side}"
      target = clips_dir / f"{candidate_id}.wav"
      audio, sample_rate = sf.read(source, always_2d=True)
      sf.write(target, audio, sample_rate, format="WAV", subtype="PCM_16")
      blinded.append((candidate_id, target.relative_to(staging).as_posix()))
      key_rows.append({
        "session_id": session_id,
        "pair_id": pair_id,
        "candidate": side,
        "system": system,
        "source_sha256": _sha256(source),
        "blinded_sha256": _sha256(target),
      })
    public_rows.append({
      "session_id": session_id,
      "pair_id": pair_id,
      "candidate_a_id": blinded[0][0],
      "candidate_a_clip": blinded[0][1],
      "candidate_b_id": blinded[1][0],
      "candidate_b_clip": blinded[1][1],
    })

  public_path = staging / "blind_session.csv"
  _write_csv(public_path, public_rows)
  key_path.parent.mkdir(parents=True, exist_ok=True)
  temporary_key = key_path.with_name(f".{key_path.name}.{uuid.uuid4().hex}.tmp")
  _write_csv(temporary_key, key_rows)
  staging.rename(output_dir)
  temporary_key.rename(key_path)
  public_path = output_dir / "blind_session.csv"
  return public_path, key_path


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--manifest", required=True, type=Path)
  parser.add_argument("--output-dir", required=True, type=Path)
  parser.add_argument("--key-output", required=True, type=Path)
  parser.add_argument(
    "--source-root",
    type=Path,
    help="Erlaubter Clip-Root; Standard ist das Verzeichnis des Manifests.",
  )
  args = parser.parse_args()
  prepare(args.manifest, args.output_dir, args.key_output, source_root=args.source_root)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

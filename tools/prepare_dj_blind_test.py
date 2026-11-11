"""Kopiert Transition-Clips unter neutralen A/B-Namen und trennt den Schluessel."""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import shutil
import tempfile
import uuid
from pathlib import Path

import soundfile as sf


def _sha256(path: Path, checkpoint=None) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as handle:
    while True:
      if checkpoint:
        checkpoint()
      chunk = handle.read(1024 * 1024)
      if not chunk:
        break
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
  key_published = False
  try:
    # Erst der private Schluessel, dann die Session. Schlaegt die zweite
    # Publikation fehl, wird der Schluessel wieder entfernt; eine sichtbare
    # Session ohne zugehoerigen Schluessel kann so nicht entstehen.
    temporary_key.replace(key_path)
    key_published = True
    staging.rename(output_dir)
  except Exception:
    if key_published:
      key_path.unlink(missing_ok=True)
    raise
  finally:
    temporary_key.unlink(missing_ok=True)
    if staging.exists():
      shutil.rmtree(staging, ignore_errors=True)
  public_path = output_dir / "blind_session.csv"
  return public_path, key_path


def validate_portable_session(public_path: Path, key_path: Path, *, checkpoint=None) -> dict:
  """Prueft CSV-Bindung, getrennten Schluessel und alle neutralen Clipkopien."""
  def check():
    if checkpoint:
      checkpoint()

  check()
  public_path, key_path = Path(public_path), Path(key_path)
  if public_path.name != "blind_session.csv" or public_path.is_symlink() or getattr(public_path, "is_junction", lambda: False)():
    raise ValueError("Oeffentliche Session muss eine regulaere blind_session.csv sein")
  if key_path.is_symlink() or getattr(key_path, "is_junction", lambda: False)():
    raise ValueError("Privater Schluessel ist ein symbolischer Link")
  session_root = public_path.parent.resolve(strict=True)
  public_path = public_path.resolve(strict=True)
  key_path = key_path.resolve(strict=True)
  if not public_path.is_file() or not key_path.is_file():
    raise ValueError("Session oder privater Schluessel fehlt")
  if key_path == session_root or key_path.is_relative_to(session_root):
    raise ValueError("Privater Schluessel liegt im Session-Ordner")

  public_fields = (
    "session_id", "pair_id", "candidate_a_id", "candidate_a_clip",
    "candidate_b_id", "candidate_b_clip",
  )
  key_fields = (
    "session_id", "pair_id", "candidate", "system", "source_sha256",
    "blinded_sha256",
  )
  with public_path.open("r", encoding="utf-8-sig", newline="") as handle:
    reader = csv.DictReader(handle)
    if tuple(reader.fieldnames or ()) != public_fields:
      raise ValueError("Oeffentliche Session hat ein unbekanntes CSV-Schema")
    public_rows = list(reader)
  with key_path.open("r", encoding="utf-8-sig", newline="") as handle:
    reader = csv.DictReader(handle)
    if tuple(reader.fieldnames or ()) != key_fields:
      raise ValueError("Privater Schluessel hat ein unbekanntes CSV-Schema")
    key_rows = list(reader)
  check()
  if not public_rows or len(key_rows) != len(public_rows) * 2:
    raise ValueError("Session und Schluessel haben unvollstaendige Paarzahlen")
  if any(None in row or any(row.get(field) is None for field in public_fields) for row in public_rows):
    raise ValueError("Oeffentliche Session enthaelt unvollstaendige CSV-Zeilen")
  if any(None in row or any(row.get(field) is None for field in key_fields) for row in key_rows):
    raise ValueError("Privater Schluessel enthaelt unvollstaendige CSV-Zeilen")

  session_ids = {str(row["session_id"]) for row in public_rows}
  if len(session_ids) != 1:
    raise ValueError("Oeffentliche Session mischt mehrere Sitzungskennungen")
  session_id = next(iter(session_ids))
  if len(session_id) != 12 or any(character not in "0123456789abcdef" for character in session_id):
    raise ValueError("Sitzungskennung ist ungueltig")

  key_by_pair_side = {}
  for row in key_rows:
    identity = (row["pair_id"], row["candidate"])
    if (row["session_id"] != session_id or row["candidate"] not in {"A", "B"}
        or row["system"] not in {"HPG", "baseline"} or identity in key_by_pair_side):
      raise ValueError("Privater Schluessel ist inkonsistent")
    for digest_name in ("source_sha256", "blinded_sha256"):
      digest = row[digest_name]
      if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError("Privater Schluessel enthaelt einen ungueltigen SHA-256-Wert")
    key_by_pair_side[identity] = row

  seen_pair_ids = set()
  seen_clip_ids = set()
  for index, row in enumerate(public_rows, 1):
    check()
    pair_id = row["pair_id"]
    if not pair_id or pair_id in seen_pair_ids or row["session_id"] != session_id:
      raise ValueError("Oeffentliche Session hat leere oder doppelte Paar-IDs")
    seen_pair_ids.add(pair_id)
    systems = set()
    for side, id_field, clip_field in (
      ("A", "candidate_a_id", "candidate_a_clip"),
      ("B", "candidate_b_id", "candidate_b_clip"),
    ):
      candidate_id = f"pair_{index:03d}_{side}"
      if row[id_field] != candidate_id or candidate_id in seen_clip_ids:
        raise ValueError("Kandidaten-ID ist nicht kanonisch")
      seen_clip_ids.add(candidate_id)
      relative_clip = f"clips/{candidate_id}.wav"
      if row[clip_field] != relative_clip:
        raise ValueError("Clip-Pfad ist nicht kanonisch")
      key = key_by_pair_side.get((pair_id, side))
      if key is None:
        raise ValueError("Schluesselzuordnung fuer Kandidat fehlt")
      systems.add(key["system"])
      clip_path = session_root / relative_clip
      clip_path_resolved = clip_path.resolve(strict=True)
      if not clip_path_resolved.is_relative_to(session_root):
        raise ValueError("Clip verlaesst den Session-Ordner")
      current = clip_path
      while current != session_root:
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
          raise ValueError("Clip-Pfad enthaelt einen symbolischen Link")
        current = current.parent
      before = clip_path_resolved.stat()
      info = sf.info(clip_path_resolved)
      if info.format != "WAV" or info.subtype != "PCM_16" or info.frames <= 0:
        raise ValueError("Neutraler Clip ist kein gueltiges PCM-16-WAV")
      digest = _sha256(clip_path_resolved, check)
      after = clip_path_resolved.stat()
      signature = lambda stat: (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, stat.st_dev)
      if signature(before) != signature(after):
        raise ValueError("Neutraler Clip wurde waehrend der Pruefung veraendert")
      if digest != key["blinded_sha256"]:
        raise ValueError("Neutraler Clip stimmt nicht mit dem privaten Schluessel ueberein")
    if systems != {"HPG", "baseline"}:
      raise ValueError("A/B-Paar enthaelt nicht genau ein HPG- und ein Baseline-Element")

  if len(key_by_pair_side) != len(public_rows) * 2:
    raise ValueError("Privater Schluessel enthaelt zusaetzliche Paarzuordnungen")
  return {"session_id": session_id, "pair_count": len(public_rows),
          "clip_count": len(public_rows) * 2}


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

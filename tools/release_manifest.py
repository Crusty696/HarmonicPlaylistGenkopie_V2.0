"""Erzeugt ein nachvollziehbares SHA256-/Commit-Manifest fuer Release-Artefakte."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hpg_core.app_metadata import APP_NAME, APP_VERSION

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha256(path):
  digest = hashlib.sha256()
  with open(path, "rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def git_commit():
  result = subprocess.run(
    ["git", "rev-parse", "HEAD"], cwd=ROOT,
    capture_output=True, text=True, check=True
  )
  return result.stdout.strip()


def git_is_clean():
  result = subprocess.run(
    ["git", "status", "--porcelain"], cwd=ROOT,
    capture_output=True, text=True, check=True
  )
  return not result.stdout.strip()


def build_manifest(paths, allow_dirty=False):
  source_clean = git_is_clean()
  if not source_clean and not allow_dirty:
    raise RuntimeError(
      "Release-Manifest verweigert dirty Worktree; zuerst committen oder "
      "fuer ein reines Verifikationsmanifest --allow-dirty setzen"
    )
  artifacts = []
  for path in paths:
    absolute = os.path.abspath(path)
    if not os.path.isfile(absolute):
      raise FileNotFoundError(absolute)
    artifacts.append({
      "path": os.path.basename(absolute),
      "size": os.path.getsize(absolute),
      "sha256": sha256(absolute),
    })
  return {
    "product": APP_NAME,
    "version": APP_VERSION,
    "commit": git_commit(),
    "source_clean": source_clean,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "artifacts": artifacts,
  }


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("paths", nargs="+")
  parser.add_argument("--output", default="release-manifest.json")
  parser.add_argument("--allow-dirty", action="store_true")
  args = parser.parse_args()
  manifest = build_manifest(args.paths, allow_dirty=args.allow_dirty)
  with open(args.output, "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2)
  print(args.output)


if __name__ == "__main__":
  main()

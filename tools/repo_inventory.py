#!/usr/bin/env python3
"""Read-only inventory of tracked and local HPG workspace files.

No audio is opened. No file is modified or deleted. Ignored/untracked directories
are reported as directory entries (their internal contents are not traversed).
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import stat
import subprocess


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def _paths(root: Path, *args: str) -> list[str]:
    return sorted(os.fsdecode(raw) for raw in _git(root, "ls-files", *args, "-z").split(b"\0") if raw)


def _mirror_pair(paths: list[str]) -> bool:
    return (len(paths) == 2
            and sorted(path.split("/", 1)[0] for path in paths) == [".agents", ".claude"]
            and paths[0].split("/", 1)[1] == paths[1].split("/", 1)[1])


def build_inventory(root: Path) -> dict:
    root = root.resolve(strict=True)
    if not (root / ".git").exists():
        raise ValueError("Nur den Stamm eines Git-Repositories angeben")

    tracked = []
    duplicates: dict[str, list[str]] = defaultdict(list)
    folders: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "bytes": 0})
    missing = []
    for record in _git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not record:
            continue
        metadata, sep, raw_path = record.partition(b"\t")
        if not sep:
            raise ValueError("Unerwarteter Git-Index-Eintrag")
        mode, blob, stage = metadata.decode("ascii").split()
        if stage != "0":
            raise ValueError("Ungeloester Git-Merge: Inventar erst nach Konfliktklaerung")
        rel = os.fsdecode(raw_path)
        location = root / rel
        try:
            info = location.lstat()  # Never follow symlinks.
        except FileNotFoundError:
            missing.append(rel)
            size, kind = 0, "missing"
        else:
            size = info.st_size if stat.S_ISREG(info.st_mode) else 0
            kind = ("symlink" if stat.S_ISLNK(info.st_mode)
                    else "file" if stat.S_ISREG(info.st_mode) else "other")
        tracked.append({"path": rel, "size": size, "kind": kind, "mode": mode})
        duplicates[blob].append(rel)
        folder = rel.split("/", 1)[0] if "/" in rel else "(root)"
        folders[folder]["files"] += 1
        folders[folder]["bytes"] += size

    groups = [sorted(paths) for paths in duplicates.values() if len(paths) > 1]
    mirrors = [paths for paths in groups if _mirror_pair(paths)]
    other = [paths for paths in groups if not _mirror_pair(paths)]
    large = sorted((item for item in tracked if item["size"] >= 1_000_000),
                   key=lambda item: -item["size"])
    suffixes = (".bak", ".old", ".orig", ".tmp", ".temp", ".backup")
    review = [item["path"] for item in tracked
              if item["path"].lower().endswith(suffixes)]
    return {
        "scope": "only the specified Git worktree; no audio contents read; no changes",
        "root": str(root),
        "tracked_file_count": len(tracked),
        "tracked_bytes": sum(item["size"] for item in tracked),
        "folders": dict(sorted(folders.items())),
        "identical_blob_groups": len(groups),
        "intentional_agent_mirror_pairs": len(mirrors),
        "other_identical_groups": other,
        "tracked_large_files": large,
        "review_name_candidates": review,
        "missing_tracked_files": missing,
        "untracked_entries": _paths(root, "--others", "--exclude-standard", "--directory"),
        "ignored_entries": _paths(root, "--others", "--ignored", "--exclude-standard", "--directory"),
        "local_listing_note": "untracked/ignored directories are grouped; contents not traversed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HPG Dateibestand kontrollieren (nur lesen)")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="Maschinenlesbaren Bericht nach stdout ausgeben")
    args = parser.parse_args(argv)
    try:
        inventory = build_inventory(args.root)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        parser.exit(2, f"Inventar fehlgeschlagen: {exc}\n")
    if args.json:
        print(json.dumps(inventory, indent=2, ensure_ascii=True))
    else:
        print("HPG-Dateiinventar (nur lesend, nichts geloescht)")
        print(f"Versionierte Dateien: {inventory['tracked_file_count']}")
        print(f"Identische Blob-Gruppen: {inventory['identical_blob_groups']}, "
              f"davon Agenten-Spiegel: {inventory['intentional_agent_mirror_pairs']}")
        for folder, count in inventory["folders"].items():
            print(f"  {folder:35} {count['files']:>4} Dateien {count['bytes']:>11} Byte")
        print("Unversionierte Eintraege:", len(inventory["untracked_entries"]))
        print("Ignorierte Eintraege:", len(inventory["ignored_entries"]))
        for group, items in (("Grosse Dateien", inventory["tracked_large_files"]),
                             ("Pruefkandidaten", inventory["review_name_candidates"]),
                             ("Sonstige Duplikate", inventory["other_identical_groups"])):
            if items:
                print(group + ":")
                for item in items:
                    print(" ", item)
        print("Eintragelisten und volle Daten: --json. Ignorierte Ordner werden nicht rekursiv geoeffnet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

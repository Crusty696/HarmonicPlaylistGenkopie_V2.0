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
import time


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


def deep_local_file_inventory(root: Path, paths: list[str], max_entries: int = 100_000) -> dict:
    """Scan untracked and ignored subfolders by metadata only, without links."""
    if max_entries < 1:
        raise ValueError("max_entries muss positiv sein")
    stack = [root / rel for rel in paths]
    visited = set()
    files = dirs = links = total_bytes = 0
    review = []
    failures = []
    now = time.time()
    while stack and len(visited) < max_entries:
        path = stack.pop()
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if relative == ".git" or relative.startswith(".git/") or relative in visited:
            continue
        visited.add(relative)
        try:
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                links += 1
                continue  # External trees must never be followed.
            if stat.S_ISDIR(info.st_mode):
                dirs += 1
                with os.scandir(path) as children:
                    stack.extend(Path(child.path) for child in children)
            elif stat.S_ISREG(info.st_mode):
                files += 1
                total_bytes += info.st_size
                if now - info.st_mtime >= 90 * 86400:
                    review.append((info.st_size, relative))
                    review.sort(reverse=True)
                    if len(review) > 30:
                        review.pop()
        except OSError as exc:
            if len(failures) < 30:
                failures.append(f"{relative}: {type(exc).__name__}")
    return {
        "files": files, "directories": dirs, "links_not_followed": links,
        "total_file_bytes": total_bytes, "entries_examined": len(visited),
        "limit": max_entries, "truncated": bool(stack),
        "largest_old_by_mtime": [{"path": rel, "bytes": size} for size, rel in review],
        "old_note": "Older than 90 days by local mtime is a REVIEW hint, not deletion approval",
        "errors_sample": failures,
    }


def build_inventory(root: Path, *, deep_local: bool = False, max_entries: int = 100_000) -> dict:
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
    report = {
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
    if deep_local:
        report["local_deep_scan"] = deep_local_file_inventory(
            root, report["untracked_entries"] + report["ignored_entries"], max_entries
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HPG Dateibestand kontrollieren (nur lesen)")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="Maschinenlesbaren Bericht nach stdout ausgeben")
    parser.add_argument("--deep-local", action="store_true", help="Unversionierte/ignorierte Ordner in der Tiefe lesen")
    parser.add_argument("--max-entries", type=int, default=100_000, help="Grenze fuer tiefe Metadatenpruefung")
    args = parser.parse_args(argv)
    try:
        inventory = build_inventory(args.root, deep_local=args.deep_local, max_entries=args.max_entries)
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
        if "local_deep_scan" in inventory:
            print("Tiefe lokale Metadatenpruefung:", inventory["local_deep_scan"])
        print("Alle Eintragelisten: --json. Tiefe lokale Pruefung nur mit --deep-local.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

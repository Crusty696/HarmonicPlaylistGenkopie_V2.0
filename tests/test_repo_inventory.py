"""Read-only workspace inventory: no music, DB, or user-state modifications."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from tools.repo_inventory import _mirror_pair, build_inventory, main


def test_only_true_agent_mirrors_are_classified_as_intentional():
    assert _mirror_pair([".agents/skills/a/SKILL.md", ".claude/skills/a/SKILL.md"])
    assert not _mirror_pair([".agents/a.txt", ".claude/b.txt"])
    assert not _mirror_pair(["hpg_core/data/a.json", "hpg_core/data/b.json"])


@pytest.mark.skipif(shutil.which("git") is None, reason="Git erforderlich")
def test_inventory_includes_local_ignored_and_does_not_modify_files(tmp_path, capsys):
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for name in (".agents/skills/x.md", ".claude/skills/x.md",
                 "hpg_core/data/a.json", "hpg_core/data/b.json"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("mirror" if name.startswith(".") else "{}", encoding="utf-8")
    (root / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (root / "ignored.log").write_text("private log must remain", encoding="utf-8")
    (root / "note.txt").write_text("untracked", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", ".agents", ".claude",
                    "hpg_core", ".gitignore"], check=True)
    report = build_inventory(root)
    assert report["tracked_file_count"] == 5
    assert report["identical_blob_groups"] == 2
    assert report["intentional_agent_mirror_pairs"] == 1
    assert report["other_identical_groups"] == [["hpg_core/data/a.json", "hpg_core/data/b.json"]]
    assert report["ignored_entries"] == ["ignored.log"]
    assert report["untracked_entries"] == ["note.txt"]
    assert (root / "ignored.log").read_text(encoding="utf-8") == "private log must remain"
    assert (root / "note.txt").read_text(encoding="utf-8") == "untracked"
    assert main(["--root", str(root), "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["tracked_file_count"] == 5

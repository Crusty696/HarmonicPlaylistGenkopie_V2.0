"""Konsistenztests fuer Dokumentation und reproduzierbare Release-Metadaten."""

from pathlib import Path

import pytest

from hpg_core.app_metadata import APP_VERSION, MIN_PYTHON
from hpg_core.playlist import STRATEGIES
from tools import release_manifest


ROOT = Path(__file__).resolve().parents[1]


def test_version_is_consistent_across_user_facing_release_files():
  assert f"v{APP_VERSION}" in (ROOT / "README.md").read_text(encoding="utf-8")
  assert f"AppVersion={APP_VERSION}" in (ROOT / "installer.iss").read_text(encoding="utf-8")
  assert f"ProductVersion', u'{APP_VERSION}'" in (
    ROOT / "version_info.txt"
  ).read_text(encoding="utf-8")
  assert f"v{APP_VERSION}" in (ROOT / "build.bat").read_text(encoding="utf-8")


def test_readme_strategy_count_and_python_floor_match_source():
  readme = (ROOT / "README.md").read_text(encoding="utf-8")
  assert f"{len(STRATEGIES)} sorting strategies" in readme
  assert f"Python {MIN_PYTHON}+" in readme


def test_pyinstaller_embeds_windows_version_resource():
  assert "version='version_info.txt'" in (ROOT / "HPG.spec").read_text(encoding="utf-8")


def test_release_manifest_contains_commit_size_and_sha256(tmp_path, monkeypatch):
  artifact = tmp_path / "artifact.bin"
  artifact.write_bytes(b"verified artifact")
  monkeypatch.setattr(release_manifest, "git_commit", lambda: "abc123")
  monkeypatch.setattr(release_manifest, "git_is_clean", lambda: True)

  manifest = release_manifest.build_manifest([str(artifact)])

  assert manifest["version"] == APP_VERSION
  assert manifest["commit"] == "abc123"
  assert manifest["source_clean"] is True
  assert manifest["artifacts"][0]["size"] == len(b"verified artifact")
  assert len(manifest["artifacts"][0]["sha256"]) == 64


def test_release_manifest_rejects_dirty_source(tmp_path, monkeypatch):
  artifact = tmp_path / "artifact.bin"
  artifact.write_bytes(b"dirty artifact")
  monkeypatch.setattr(release_manifest, "git_is_clean", lambda: False)

  with pytest.raises(RuntimeError, match="dirty Worktree"):
    release_manifest.build_manifest([str(artifact)])

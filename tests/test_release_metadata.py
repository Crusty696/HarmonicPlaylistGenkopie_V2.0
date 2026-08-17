"""Konsistenztests fuer Dokumentation und reproduzierbare Release-Metadaten."""

from pathlib import Path

import pytest

import hpg_core
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
  installer = (ROOT / "installer.iss").read_text(encoding="utf-8")
  assert f"OutputBaseFilename=HPG_v{APP_VERSION}_Setup" in installer
  assert f"v{APP_VERSION} Setup" in installer
  assert f"HPG_v{APP_VERSION}_Setup.exe" in (
    ROOT / "build_installer.bat"
  ).read_text(encoding="utf-8")


def test_package_version_mirrors_single_metadata_source():
  # Verhindert das Auseinanderlaufen der frueher doppelten Versionsquellen.
  assert hpg_core.__version__ == APP_VERSION


def test_readme_strategy_count_and_python_floor_match_source():
  readme = (ROOT / "README.md").read_text(encoding="utf-8")
  assert f"{len(STRATEGIES)} sorting strategies" in readme
  assert f"Python {MIN_PYTHON}+" in readme


def test_pyinstaller_embeds_windows_version_resource():
  assert "version='version_info.txt'" in (ROOT / "HPG.spec").read_text(encoding="utf-8")


def test_build_and_ci_use_pinned_pyinstaller_and_hard_release_gates():
  requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
  build = (ROOT / "build.bat").read_text(encoding="utf-8")
  release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
  installer_ci = (
    ROOT / ".github/workflows/test-installer.yml"
  ).read_text(encoding="utf-8")

  assert "pyinstaller==6.21.0" in requirements.casefold()
  assert "-m PyInstaller" in build
  assert "sys.version_info >= (3, 12, 1)" in build
  assert "Run release test gate" in release
  assert "Verify tag matches application version" in release
  assert "Create release manifest" in release
  assert "build_installer.bat" in release
  assert "HPG_${{ github.ref_name }}_Setup.exe" in release
  assert f"HPG_v{APP_VERSION}_Setup.exe" not in release
  assert "Silent install, startup smoke, and uninstall" in installer_ci
  assert 'Get-ChildItem "installer_output" -Filter "HPG_v*_Setup.exe"' in installer_ci


def test_custom_installer_dialogs_are_disabled_in_silent_mode():
  installer = (ROOT / "installer.iss").read_text(encoding="utf-8")

  assert "if not WizardSilent then" in installer
  assert "if (CurStep = ssPostInstall) and (not WizardSilent) then" in installer


def test_auto_merge_cleanup_is_limited_to_confirmed_merged_heads():
  workflow = (
    ROOT / ".github/workflows/auto-merge-all-prs.yml"
  ).read_text(encoding="utf-8")

  assert "if not result.merged" in workflow
  assert "merged_heads.append" in workflow
  assert "for branch_name in sorted(set(merged_heads))" in workflow
  assert "for branch in branches" not in workflow


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

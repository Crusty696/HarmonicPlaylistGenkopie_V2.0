"""Konsistenztests fuer Dokumentation und reproduzierbare Release-Metadaten."""

import re
from pathlib import Path

import pytest

import hpg_core
from hpg_core.app_metadata import APP_VERSION, MIN_PYTHON
from hpg_core.caching import CACHE_VERSION
from hpg_core.playlist import STRATEGIES
from tools import release_manifest


ROOT = Path(__file__).resolve().parents[1]


def _exact_requirement_pins(path):
  pins = {}
  for raw_line in path.read_text(encoding="utf-8").splitlines():
    requirement = raw_line.partition("#")[0].strip()
    if "==" not in requirement:
      continue
    package, version = requirement.split("==", 1)
    normalized_package = re.sub(r"[-_.]+", "-", package.strip()).casefold()
    pins[normalized_package] = version.strip()
  return pins


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


def test_living_docs_reference_current_cache_contract():
  expected_version = f"CACHE_VERSION {CACHE_VERSION}"
  expected_path = f"hpg_cache_v{CACHE_VERSION}.db"
  for relative_path in ("AGENTS.md", "CLAUDE.md", "docs/QUICK_START.txt"):
    content = (ROOT / relative_path).read_text(encoding="utf-8")
    assert expected_version in content, relative_path
    assert expected_path in content, relative_path

  production_status = (ROOT / "PRODUCTION_STATUS.md").read_text(encoding="utf-8")
  assert f"Cache-Version {CACHE_VERSION}" in production_status


def test_pyinstaller_embeds_windows_version_resource():
  assert "version='version_info.txt'" in (ROOT / "HPG.spec").read_text(encoding="utf-8")


def test_pyinstaller_bundles_hpg_core_data_json():
  """tolerances.py / candidate_preferences.py lesen Path(__file__).parent / 'data';
  der gefrorene Build muss hpg_core/data/*.json mitbringen."""
  spec = (ROOT / "HPG.spec").read_text(encoding="utf-8")
  assert "os.path.join(SPECPATH, 'hpg_core', 'data')" in spec and "f.endswith('.json')" in spec
  vorhanden = sorted(p.name for p in (ROOT / "hpg_core" / "data").glob("*.json"))
  assert vorhanden == ["candidate_preferences.json", "transition_tolerances.json"]


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
  assert "Silent install, frozen worker, GUI, and uninstall smoke" in installer_ci
  assert 'installer_output/HPG_v$($appVersion)_Setup.exe' in installer_ci
  assert "Get-ChildItem -Recurse" not in installer_ci
  assert '"HarmonicPlaylistGenerator.exe"' in installer_ci
  assert "dist/HarmonicPlaylistGenerator.exe" not in installer_ci


def test_release_and_main_ci_share_one_strong_installer_runtime_gate():
  release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
  installer_ci = (
    ROOT / ".github/workflows/test-installer.yml"
  ).read_text(encoding="utf-8")
  smoke = (
    ROOT / ".github/scripts/test_installer_runtime.ps1"
  ).read_text(encoding="utf-8")
  script_path = ".github/scripts/test_installer_runtime.ps1"

  assert release.count(script_path) == 1
  assert installer_ci.count(script_path) == 1
  assert "/VERYSILENT" not in release
  assert "/VERYSILENT" not in installer_ci
  for marker in (
    "/VERYSILENT",
    "--worker-smoke",
    "Frozen worker smoke did not persist both isolated tracks",
    "SELECT COUNT(*) FROM cache WHERE key <> ?",
    "Installed application exited",
    "Uninstaller missing after successful installation",
    "process tree did not stop",
    "Installed executable differs from standalone release executable",
  ):
    assert marker in smoke


def test_release_publishes_only_verified_sha_bound_candidate():
  release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

  assert "permissions:\n  contents: read" in release
  assert "publish:\n    needs: build-and-verify" in release
  publish = release.split("\n  publish:\n", 1)[1]
  assert "contents: write" in publish
  assert "contents: write" not in release.split("\n  publish:\n", 1)[0]
  assert release.count("hpg-release-candidate-${{ github.sha }}") == 2
  assert "HarmonicPlaylistGenerator.exe" in release
  assert "dist/HarmonicPlaylistGenerator.exe" not in release
  assert "installer_output/HPG_${{ github.ref_name }}_Setup.exe" in release
  assert release.index("test_installer_runtime.ps1") < release.index(
    "Upload verified release candidate"
  )
  assert publish.index("Verify candidate boundary and manifest") < publish.index(
    "softprops/action-gh-release@v2"
  )
  for marker in (
    "Manifest commit does not match release commit",
    "Manifest source was not clean",
    "Manifest integrity mismatch",
    "Release candidate boundary mismatch",
  ):
    assert marker in publish


def test_release_notes_do_not_link_to_missing_changelog():
  release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

  assert "CHANGELOG.md" not in release
  assert "generate_release_notes: true" in release


def test_optional_performance_requirements_do_not_conflict_with_main_pins():
  main_pins = _exact_requirement_pins(ROOT / "requirements.txt")
  performance_pins = _exact_requirement_pins(ROOT / "requirements-performance.txt")

  shared_packages = main_pins.keys() & performance_pins.keys()
  conflicts = {
    package: (main_pins[package], performance_pins[package])
    for package in shared_packages
    if main_pins[package] != performance_pins[package]
  }
  assert conflicts == {}


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


def test_auto_merge_requires_completed_ci_and_binds_checked_head_sha():
  workflow = (
    ROOT / ".github/workflows/auto-merge-all-prs.yml"
  ).read_text(encoding="utf-8")

  assert "checks: read" in workflow
  assert "statuses: read" in workflow
  assert "pr = repo.get_pull(pr.number)" in workflow
  assert "if pr.draft" in workflow
  assert "pr.mergeable is not True" in workflow
  assert "pr.mergeable_state != 'clean'" in workflow
  assert "check_runs = list(head_commit.get_check_runs())" in workflow
  assert "if not check_runs" in workflow
  assert "check.status != 'completed'" in workflow
  assert "{'success', 'neutral', 'skipped'}" in workflow
  assert "combined_status.statuses and combined_status.state != 'success'" in workflow
  assert workflow.count("sha=head_sha") == 3
  trigger_block = workflow.split("\non:\n", 1)[1].split("\npermissions:\n", 1)[0]
  top_level_triggers = re.findall(
    r"^  ([A-Za-z_][\w-]*):", trigger_block, re.MULTILINE
  )
  assert top_level_triggers == ["workflow_dispatch"]


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

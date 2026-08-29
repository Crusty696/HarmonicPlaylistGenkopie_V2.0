from types import SimpleNamespace
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

import e2e_check
from hpg_core.config import PAAR_BPM_MAX
from hpg_core.models import Track


def _track(name):
  return SimpleNamespace(filePath=f"C:/{name}.wav", fileName=f"{name}.wav")


def test_find_first_local_pair_skips_three_incompatible_tracks(monkeypatch):
  tracks = [_track(name) for name in ("a", "b", "c", "d", "e")]

  def compatibility(source, target, *args, **kwargs):
    kandidat = object() if (source.fileName, target.fileName) == ("d.wav", "e.wav") else None
    return SimpleNamespace(kandidat=kandidat)

  monkeypatch.setattr(e2e_check, "calculate_enhanced_compatibility", compatibility)

  assert e2e_check.find_first_local_pair(
    tracks, e2e_check.E2E_BPM_TOLERANCE, {}
  ) == tracks[3:5]


def test_find_first_local_pair_returns_none_without_edge(monkeypatch):
  monkeypatch.setattr(
    e2e_check,
    "calculate_enhanced_compatibility",
    lambda *args, **kwargs: SimpleNamespace(kandidat=None),
  )

  assert e2e_check.find_first_local_pair(
    [_track("a"), _track("b")], e2e_check.E2E_BPM_TOLERANCE, {}
  ) is None


def test_has_local_edge_prueft_die_tatsaechliche_richtung(monkeypatch):
  a, b = _track("a"), _track("b")
  monkeypatch.setattr(
    e2e_check,
    "calculate_enhanced_compatibility",
    lambda source, target, *args, **kwargs: SimpleNamespace(
      kandidat=object() if (source is a and target is b) else None
    ),
  )
  assert e2e_check.has_local_edge([a, b], e2e_check.E2E_BPM_TOLERANCE, {})
  assert not e2e_check.has_local_edge(
    [b, a], e2e_check.E2E_BPM_TOLERANCE, {}
  )


def test_e2e_uses_the_absolute_pair_bpm_contract():
  assert e2e_check.E2E_BPM_TOLERANCE == PAAR_BPM_MAX == 2.0


def test_e2e_help_exits_without_running_analysis(capsys):
  with pytest.raises(SystemExit, match="0"):
    e2e_check.main(["--help"])

  assert "--max-fixtures" in capsys.readouterr().out


def test_e2e_help_documents_explicit_audio_files(capsys):
  with pytest.raises(SystemExit, match="0"):
    e2e_check.main(["--help"])

  assert "--audio-file" in capsys.readouterr().out


def test_e2e_rejects_fixture_limit_below_two(capsys):
  with pytest.raises(SystemExit, match="2"):
    e2e_check.main(["--max-fixtures", "1"])

  assert "muss mindestens 2 sein" in capsys.readouterr().err


def test_e2e_returns_three_when_fixture_limit_has_no_local_edge(
  monkeypatch, capsys
):
  paths = ["C:/fixtures/a.wav", "C:/fixtures/b.wav"]
  monkeypatch.setattr(e2e_check.glob, "glob", lambda *args, **kwargs: paths)
  monkeypatch.setattr(e2e_check.os.path, "getsize", lambda path: 1_000_000)
  monkeypatch.setattr(
    e2e_check,
    "analyze_track",
    lambda path: Track(
      filePath=path,
      fileName=path.rsplit("/", 1)[-1],
      bpm=128.0,
      duration=300.0,
    ),
  )
  monkeypatch.setattr(e2e_check, "find_first_local_pair", lambda *args: None)

  assert e2e_check.main(["--audio-dir", "C:/fixtures", "--max-fixtures", "2"]) == 3
  assert "FIXTURE-SATZ UNZUREICHEND" in capsys.readouterr().out


def test_e2e_returns_one_when_analysis_failure_prevents_local_edge(
  monkeypatch, capsys
):
  paths = ["C:/fixtures/a.wav", "C:/fixtures/b.wav"]
  monkeypatch.setattr(e2e_check.glob, "glob", lambda *args, **kwargs: paths)
  monkeypatch.setattr(e2e_check.os.path, "getsize", lambda path: 1_000_000)

  def analyze(path):
    if path.endswith("a.wav"):
      raise RuntimeError("Decoder defekt")
    return Track(
      filePath=path,
      fileName=path.rsplit("/", 1)[-1],
      bpm=128.0,
      duration=300.0,
    )

  monkeypatch.setattr(e2e_check, "analyze_track", analyze)
  monkeypatch.setattr(e2e_check, "find_first_local_pair", lambda *args: None)

  assert e2e_check.main(["--audio-dir", "C:/fixtures", "--max-fixtures", "2"]) == 1
  output = capsys.readouterr().out
  assert "=== FAIL ===" in output
  assert "Decoder defekt" in output
  assert "FIXTURE-SATZ UNZUREICHEND" not in output


def test_e2e_reports_disappeared_fixture_without_traceback(monkeypatch, capsys):
  path = "C:/fixtures/weg.wav"
  monkeypatch.setattr(e2e_check.glob, "glob", lambda *args, **kwargs: [path])
  monkeypatch.setattr(
    e2e_check.os.path,
    "getsize",
    Mock(side_effect=OSError("Datei verschwunden")),
  )

  assert e2e_check.main(["--audio-dir", "C:/fixtures", "--max-fixtures", "2"]) == 1
  output = capsys.readouterr().out
  assert "Audio-Fixture kann nicht gelesen werden" in output
  assert "Datei verschwunden" in output


def test_explicit_audio_files_bypass_glob_preserve_order_and_deduplicate(
  monkeypatch, capsys
):
  paths = [
    "C:/fixtures/z.aif",
    "C:/fixtures/a.aif",
    "C:/fixtures/z.aif",
    "C:/fixtures/ignored.aif",
  ]
  analyzed = []
  monkeypatch.setattr(
    e2e_check.glob,
    "glob",
    Mock(side_effect=AssertionError("glob darf nicht aufgerufen werden")),
  )
  monkeypatch.setattr(e2e_check.os.path, "getsize", lambda path: 1_000_000)

  def analyze(path):
    analyzed.append(path)
    return Track(
      filePath=path,
      fileName=path.rsplit("/", 1)[-1],
      bpm=128.0,
      duration=300.0,
    )

  monkeypatch.setattr(e2e_check, "analyze_track", analyze)
  monkeypatch.setattr(e2e_check, "find_first_local_pair", lambda *args: None)

  argv = ["--audio-dir", "C:/other", "--max-fixtures", "2"]
  for path in paths:
    argv.extend(("--audio-file", path))
  assert e2e_check.main(argv) == 3
  assert analyzed == paths[:2]
  assert "FIXTURE-SATZ UNZUREICHEND" in capsys.readouterr().out


def test_explicit_audio_files_require_two_distinct_usable_paths(monkeypatch, capsys):
  path = "C:/fixtures/einzig.aif"
  monkeypatch.setattr(e2e_check.os.path, "getsize", lambda candidate: 1_000_000)

  assert e2e_check.main(["--audio-file", path, "--audio-file", path]) == 2
  assert "mindestens 2 Audio-Fixtures" in capsys.readouterr().out


def test_explicit_unreadable_audio_file_returns_one_without_fallback(
  monkeypatch, capsys
):
  bad = "C:/fixtures/defekt.aif"
  good = "C:/fixtures/gut.aif"
  monkeypatch.setattr(
    e2e_check.glob,
    "glob",
    Mock(side_effect=AssertionError("kein automatischer Fallback erlaubt")),
  )
  monkeypatch.setattr(
    e2e_check.os.path,
    "getsize",
    Mock(side_effect=OSError("nicht lesbar")),
  )

  assert e2e_check.main(["--audio-file", bad, "--audio-file", good]) == 1
  output = capsys.readouterr().out
  assert bad in output
  assert "nicht lesbar" in output


def test_automatic_search_includes_aif_in_all_existing_search_areas(
  monkeypatch, capsys
):
  patterns = []

  def fake_glob(pattern, recursive):
    patterns.append((pattern.replace("\\", "/"), recursive))
    return []

  monkeypatch.setattr(e2e_check.glob, "glob", fake_glob)

  assert e2e_check.main(["--audio-dir", "C:/fixtures"]) == 2
  assert ("tests/**/*.aif", True) in patterns
  assert ("validation/**/*.aif", True) in patterns
  assert ("C:/fixtures/*.aif", True) in patterns
  assert "mindestens 2 Audio-Fixtures" in capsys.readouterr().out


def test_e2e_import_veraendert_cache_umgebung_nicht(tmp_path):
  env = dict(os.environ)
  env.pop("HPG_CACHE_FILE", None)
  env["TEMP"] = str(tmp_path)
  env["TMP"] = str(tmp_path)
  env["LOCALAPPDATA"] = str(tmp_path / "localappdata")
  result = subprocess.run(
    [
      sys.executable,
      "-c",
      "import os; import e2e_check; print(os.environ.get('HPG_CACHE_FILE', 'UNSET'))",
    ],
    check=True,
    capture_output=True,
    text=True,
    env=env,
    cwd=Path(__file__).resolve().parents[1],
  )

  assert result.stdout.strip() == "UNSET"
  assert not (tmp_path / "localappdata" / "HPG").exists()


def test_e2e_import_ueberschreibt_geerbte_umgebung_nicht(tmp_path):
  produktcache = tmp_path / "produkt.db"
  result = subprocess.run(
    [
      sys.executable,
      "-c",
      "import os; import e2e_check; print(os.environ['HPG_CACHE_FILE'])",
    ],
    check=True,
    capture_output=True,
    text=True,
    env={**os.environ, "HPG_CACHE_FILE": str(produktcache)},
    cwd=Path(__file__).resolve().parents[1],
  )

  assert Path(result.stdout.strip()).resolve() == produktcache.resolve()
  assert not produktcache.exists()

"""Regressionstests fuer die strikte Trennung von Test- und Produktivcache."""

import os
from pathlib import Path

from hpg_core import caching


def test_pytest_uses_dedicated_cache_file():
  """Der importierte Cache darf nie auf die Produktivdatei zeigen."""
  production_cache = (
    Path(os.environ.get("LOCALAPPDATA", Path.home()))
    / "HPG"
    / f"hpg_cache_v{caching.CACHE_VERSION}.db"
  ).resolve()
  active_cache = Path(caching.CACHE_FILE).resolve()

  assert active_cache != production_cache
  assert active_cache.name == "hpg_cache_test.db"
  assert os.environ["HPG_CACHE_FILE"] == caching.CACHE_FILE


def test_relative_cache_override_is_bound_to_absolute_path(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  resolved = caching._resolve_cache_file("relative-cache.db")

  assert Path(resolved).is_absolute()
  assert Path(resolved) == tmp_path / "relative-cache.db"


def test_test_cache_can_be_initialized_without_product_cache(tmp_path, monkeypatch):
  """Initialisierung schreibt ausschliesslich in die gesetzte Testdatei."""
  isolated_cache = tmp_path / "isolated.db"
  monkeypatch.setattr(caching, "CACHE_FILE", str(isolated_cache))
  monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "isolated.lock"))

  caching.init_cache()

  assert isolated_cache.exists()

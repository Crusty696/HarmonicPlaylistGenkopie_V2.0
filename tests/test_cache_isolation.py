"""Regressionstests fuer die strikte Trennung von Test- und Produktivcache."""

import os
from pathlib import Path

from hpg_core import caching


def test_pytest_uses_dedicated_cache_file():
  """Der importierte Cache darf nie auf die Produktivdatei zeigen."""
  project_root = Path(__file__).resolve().parents[1]
  production_cache = (project_root / "hpg_cache_v17.db").resolve()
  active_cache = Path(caching.CACHE_FILE).resolve()

  assert active_cache != production_cache
  assert active_cache.name == "hpg_cache_test.db"
  assert os.environ["HPG_CACHE_FILE"] == caching.CACHE_FILE


def test_test_cache_can_be_initialized_without_product_cache(tmp_path, monkeypatch):
  """Initialisierung schreibt ausschliesslich in die gesetzte Testdatei."""
  isolated_cache = tmp_path / "isolated.db"
  monkeypatch.setattr(caching, "CACHE_FILE", str(isolated_cache))
  monkeypatch.setattr(caching, "LOCK_FILE", str(tmp_path / "isolated.lock"))

  caching.init_cache()

  assert isolated_cache.exists()

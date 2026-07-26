"""Tests fuer hpg_core/genres.py — Single Source of Truth des Genre-Wissens.

Die Kern-Validierung laeuft bereits beim Import (_validate_genre_tables);
diese Tests machen die einzelnen Invarianten explizit und liefern bei
Verstoessen lesbare Fehlermeldungen.
"""

import pytest

from hpg_core.genres import (
  CANONICAL_GENRES,
  GENRE_PROFILES,
  GENRE_MIX_PROFILES,
  GENRE_COMPATIBILITY,
  ID3_GENRE_MAP,
  DEFAULT_MIX_PROFILE,
  _validate_genre_tables,
)


class TestKanonischeGenres:
  def test_neun_genres(self):
    assert len(CANONICAL_GENRES) == 9

  def test_keine_duplikate(self):
    assert len(set(CANONICAL_GENRES)) == len(CANONICAL_GENRES)


class TestTabellenKonsistenz:
  """Drift-Schutz: alle Tabellen decken exakt die kanonischen Genres ab."""

  def test_genre_profiles_vollstaendig(self):
    assert set(GENRE_PROFILES) == set(CANONICAL_GENRES)

  def test_mix_profiles_vollstaendig(self):
    assert set(GENRE_MIX_PROFILES) == set(CANONICAL_GENRES)

  def test_compatibility_deckt_alle_genres(self):
    compat_genres = {g for pair in GENRE_COMPATIBILITY for g in pair}
    assert compat_genres == set(CANONICAL_GENRES)

  def test_selbstpaare_sind_1(self):
    for genre in CANONICAL_GENRES:
      assert GENRE_COMPATIBILITY.get((genre, genre)) == 1.0, genre

  def test_id3_ziele_kanonisch(self):
    assert set(ID3_GENRE_MAP.values()) <= set(CANONICAL_GENRES)

  def test_validierung_laeuft_fehlerfrei(self):
    _validate_genre_tables()


class TestProfileWerte:
  def test_phrase_units_gueltig(self):
    for genre, profile in GENRE_MIX_PROFILES.items():
      assert profile.phrase_unit in (8, 16, 32), genre
    assert DEFAULT_MIX_PROFILE.phrase_unit in (8, 16, 32)

  def test_bpm_ranges_plausibel(self):
    for genre, profile in GENRE_PROFILES.items():
      lo, hi = profile.bpm_range
      assert 60 <= lo < hi <= 200, genre
      assert lo <= profile.bpm_center <= hi, genre

  def test_bar_ranges_plausibel(self):
    for genre, profile in GENRE_MIX_PROFILES.items():
      for pair in (profile.outro_bars, profile.transition_bars):
        assert 0 < pair[0] <= pair[1] <= 128, genre

  def test_compatibility_werte_in_0_1(self):
    for pair, value in GENRE_COMPATIBILITY.items():
      assert 0.0 <= value <= 1.0, pair


class TestReExportsStabil:
  """Bestehende Import-Pfade muessen weiter funktionieren (keine API-Brueche)."""

  def test_dj_brain_reexport(self):
    from hpg_core.dj_brain import GENRE_MIX_PROFILES as via_dj
    assert via_dj is GENRE_MIX_PROFILES

  def test_genre_classifier_reexport(self):
    from hpg_core.genre_classifier import GENRE_PROFILES as via_gc, ID3_GENRE_MAP as via_id3
    assert via_gc is GENRE_PROFILES
    assert via_id3 is ID3_GENRE_MAP

  def test_structure_analyzer_abgeleitet(self):
    from hpg_core.structure_analyzer import GENRE_PHRASE_UNITS
    for genre, profile in GENRE_MIX_PROFILES.items():
      assert GENRE_PHRASE_UNITS[genre] == profile.phrase_unit
    assert GENRE_PHRASE_UNITS["Unknown"] == DEFAULT_MIX_PROFILE.phrase_unit


class TestDriftErkennung:
  """Die Validierung muss echte Drift-Fehler auch wirklich melden."""

  def test_fehlendes_genre_wird_erkannt(self, monkeypatch):
    import hpg_core.genres as genres_mod
    kaputt = dict(GENRE_MIX_PROFILES)
    kaputt.pop("Psytrance")
    monkeypatch.setattr(genres_mod, "GENRE_MIX_PROFILES", kaputt)
    with pytest.raises(ValueError, match="GENRE_MIX_PROFILES"):
      genres_mod._validate_genre_tables()

  def test_falsches_id3_ziel_wird_erkannt(self, monkeypatch):
    import hpg_core.genres as genres_mod
    kaputt = dict(ID3_GENRE_MAP)
    kaputt["hardstyle"] = "Hardstyle"  # kein kanonisches Genre
    monkeypatch.setattr(genres_mod, "ID3_GENRE_MAP", kaputt)
    with pytest.raises(ValueError, match="ID3_GENRE_MAP"):
      genres_mod._validate_genre_tables()

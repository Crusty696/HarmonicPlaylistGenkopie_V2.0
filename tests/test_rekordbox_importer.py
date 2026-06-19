"""
Tests fuer RekordboxImporter.

Mockt REKORDBOX_AVAILABLE=True + Rekordbox6Database-Stub um Instanziierung zu
ermoeglichen. Testet alle Pure-Python-Methoden ohne echtes pyrekordbox.

HINWEIS: Rekordbox6Database existiert NICHT im Modul-Namespace wenn pyrekordbox
nicht installiert ist → create=True bei allen Patches erforderlich.
"""
import os
import pytest
from unittest.mock import patch
import hpg_core.rekordbox_importer as rb_module
from hpg_core.rekordbox_importer import (
  RekordboxImporter,
  RekordboxTrackData,
  get_rekordbox_importer,
)


# ─── Fake-Klassen (Stubs fuer pyrekordbox) ────────────────────────────────────

class FakeCue:
  """Simuliert ein Rekordbox Cue-Punkt-Objekt."""

  def __init__(
    self,
    in_msec=10000,
    comment="Cue 1",
    kind=1,
    hot_cue_bank_number=0,
    color_id=None,
  ):
    self.InMsec = in_msec
    self.Comment = comment
    self.Kind = kind
    self.HotCueBankNumber = hot_cue_bank_number
    self.ColorID = color_id


class FakeContent:
  """Simuliert ein Rekordbox Content-Objekt (Track in der DB)."""

  def __init__(
    self,
    folder_path="C:\\Music",
    filename="track.mp3",
    bpm=12800,
    key_name="8A",
    length=240,
    title="Test Track",
    artist_name="Test Artist",
    genre_name="Techno",
    album_name="Test Album",
    rating=3,
    color_name=None,
    cues=None,
  ):
    self.FolderPath = folder_path
    self.FileNameL = filename
    self.FileNameS = filename
    self.BPM = bpm
    self.KeyName = key_name
    self.Length = length
    self.Title = title
    self.ArtistName = artist_name
    self.GenreName = genre_name
    self.AlbumName = album_name
    self.Rating = rating
    self.ColorName = color_name
    self.Cues = cues or []


class FakeDatabase:
  """Minimal-Stub fuer Rekordbox6Database ohne pyrekordbox."""

  def __init__(self, contents=None):
    self._contents = contents or []

  def get_content(self):
    return self._contents


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def make_importer(db=None):
  """Erstellt RekordboxImporter mit REKORDBOX_AVAILABLE=True und FakeDatabase."""
  _db = db if db is not None else FakeDatabase()
  with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", True):
    with patch(
      "hpg_core.rekordbox_importer.Rekordbox6Database",
      lambda: _db,
      create=True,  # PFLICHT: Rekordbox6Database existiert nicht ohne pyrekordbox
    ):
      return RekordboxImporter()


def make_importer_with_track(
  folder_path, filename, bpm=12800, key_name="8A", cues=None
):
  """Erstellt Importer mit einem Track in der FakeDatabase."""
  content = FakeContent(
    folder_path=folder_path,
    filename=filename,
    bpm=bpm,
    key_name=key_name,
    cues=cues or [],
  )
  return make_importer(db=FakeDatabase([content]))


# ─── Tests: Initialisierung ───────────────────────────────────────────────────

class TestRekordboxImporterInit:
  """Initialisierung und Fehlerbehandlung."""

  def test_init_ohne_pyrekordbox_db_ist_none(self):
    with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
      imp = RekordboxImporter()
    assert imp.db is None

  def test_init_ohne_pyrekordbox_cache_leer(self):
    with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
      imp = RekordboxImporter()
    assert len(imp.track_cache) == 0

  def test_init_mit_db_laedt_tracks(self):
    content = FakeContent(folder_path="C:\\Music", filename="track.mp3", bpm=12800)
    imp = make_importer(db=FakeDatabase([content]))
    assert len(imp.track_cache) == 1

  def test_init_db_fehler_wird_abgefangen(self):
    """Wenn Rekordbox6Database() eine Exception wirft, bleibt db=None."""
    with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", True):
      with patch(
        "hpg_core.rekordbox_importer.Rekordbox6Database",
        side_effect=RuntimeError("DB nicht gefunden"),
        create=True,
      ):
        imp = RekordboxImporter()
    assert imp.db is None
    assert len(imp.track_cache) == 0


# ─── Tests: is_available ──────────────────────────────────────────────────────

class TestIsAvailable:
  """is_available() Logik."""

  def test_false_wenn_db_none(self):
    with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
      imp = RekordboxImporter()
    assert imp.is_available() is False

  def test_false_wenn_cache_leer(self):
    # DB vorhanden aber kein Track
    imp = make_importer(db=FakeDatabase([]))
    # db ist gesetzt aber cache ist leer
    assert imp.is_available() is False

  def test_true_mit_tracks(self):
    content = FakeContent()
    imp = make_importer(db=FakeDatabase([content]))
    assert imp.is_available() is True


# ─── Tests: _safe_bpm ─────────────────────────────────────────────────────────

class TestSafeBpm:
  """_safe_bpm() Konvertierungslogik."""

  def test_normal_bpm_wird_dividiert(self):
    assert RekordboxImporter._safe_bpm(13600) == pytest.approx(136.0)

  def test_128_bpm(self):
    assert RekordboxImporter._safe_bpm(12800) == pytest.approx(128.0)

  def test_null_ergibt_none(self):
    assert RekordboxImporter._safe_bpm(0) is None

  def test_none_ergibt_none(self):
    assert RekordboxImporter._safe_bpm(None) is None

  def test_string_numerisch(self):
    assert RekordboxImporter._safe_bpm("14000") == pytest.approx(140.0)

  def test_string_nicht_numerisch_ergibt_none(self):
    assert RekordboxImporter._safe_bpm("abc") is None

  def test_leerer_string_ergibt_none(self):
    assert RekordboxImporter._safe_bpm("") is None


# ─── Tests: _convert_key_to_camelot ──────────────────────────────────────────

class TestConvertKeyToCamelot:
  """_convert_key_to_camelot() Konvertierungslogik."""

  def test_camelot_code_wird_direkt_zurueckgegeben(self):
    imp = make_importer()
    assert imp._convert_key_to_camelot("8A") == "8A"

  def test_alle_camelot_codes_passthrough(self):
    imp = make_importer()
    for num in range(1, 13):
      assert imp._convert_key_to_camelot(f"{num}A") == f"{num}A"
      assert imp._convert_key_to_camelot(f"{num}B") == f"{num}B"

  def test_am_ergibt_8a(self):
    imp = make_importer()
    assert imp._convert_key_to_camelot("Am") == "8A"

  def test_c_dur_ergibt_8b(self):
    imp = make_importer()
    assert imp._convert_key_to_camelot("C") == "8B"

  def test_flat_minor_dbm_ergibt_12a(self):
    """Db → C# → CAMELOT_MAP[("C#","Minor")] = "12A"."""
    imp = make_importer()
    assert imp._convert_key_to_camelot("Dbm") == "12A"

  def test_flat_major_bb_ergibt_6b(self):
    """Bb → A# → CAMELOT_MAP[("A#","Major")] = "6B"."""
    imp = make_importer()
    assert imp._convert_key_to_camelot("Bb") == "6B"

  def test_unbekannte_notation_ergibt_none(self):
    imp = make_importer()
    assert imp._convert_key_to_camelot("Unknown") is None
    assert imp._convert_key_to_camelot("XY") is None

  def test_whitespace_wird_normiert(self):
    imp = make_importer()
    assert imp._convert_key_to_camelot("  8A  ") == "8A"

  def test_eb_minor_ergibt_2a(self):
    """Eb → D# → CAMELOT_MAP[("D#","Minor")] = "2A"."""
    imp = make_importer()
    assert imp._convert_key_to_camelot("Ebm") == "2A"


# ─── Tests: _extract_cue_points ───────────────────────────────────────────────

class TestExtractCuePoints:
  """_extract_cue_points() Parsing-Logik."""

  def test_cue_wird_extrahiert(self):
    imp = make_importer()
    cue = FakeCue(in_msec=5000, comment="Drop")
    result = imp._extract_cue_points([cue])
    assert len(result) == 1
    assert result[0]["position"] == pytest.approx(5.0)
    assert result[0]["name"] == "Drop"

  def test_leere_liste_ergibt_leere_liste(self):
    imp = make_importer()
    assert imp._extract_cue_points([]) == []

  def test_cue_position_in_sekunden(self):
    """InMsec=15000 ms → position=15.0 s."""
    imp = make_importer()
    cue = FakeCue(in_msec=15000)
    result = imp._extract_cue_points([cue])
    assert result[0]["position"] == pytest.approx(15.0)

  def test_mehrere_cues(self):
    imp = make_importer()
    cues = [
      FakeCue(in_msec=0, comment="Intro"),
      FakeCue(in_msec=30000, comment="Drop"),
      FakeCue(in_msec=60000, comment="Outro"),
    ]
    result = imp._extract_cue_points(cues)
    assert len(result) == 3
    names = [c["name"] for c in result]
    assert "Drop" in names

  def test_cue_fehler_kein_crash(self):
    """Wenn ein Cue eine Exception wirft, soll kein Crash passieren."""
    imp = make_importer()

    class BrokenCue:
      @property
      def InMsec(self):
        raise RuntimeError("Kaputt")

    result = imp._extract_cue_points([BrokenCue()])
    # Fehler wird abgefangen, leere Liste zurueck
    assert isinstance(result, list)


# ─── Tests: Track-Cache ───────────────────────────────────────────────────────

class TestBuildTrackCache:
  """_build_track_cache() Cache-Aufbau."""

  def test_cache_wird_aufgebaut(self):
    content = FakeContent(folder_path="C:\\Music", filename="track.mp3")
    imp = make_importer(db=FakeDatabase([content]))
    assert len(imp.track_cache) == 1

  def test_pfad_wird_normalisiert(self):
    """Cache-Key muss normalisiert (lowercase, backslash) sein."""
    content = FakeContent(folder_path="C:\\MUSIC", filename="TRACK.MP3")
    imp = make_importer(db=FakeDatabase([content]))
    # Key muss lowercase sein
    key = list(imp.track_cache.keys())[0]
    assert key == key.lower()

  def test_track_ohne_dateiname_wird_ignoriert(self):
    """Content ohne FileNameL und FileNameS wird uebersprungen."""

    class NoNameContent(FakeContent):
      def __init__(self):
        super().__init__()
        self.FileNameL = ""
        self.FileNameS = ""

    imp = make_importer(db=FakeDatabase([NoNameContent()]))
    assert len(imp.track_cache) == 0

  def test_bpm_wird_korrekt_geladen(self):
    """BPM 13600 → 136.0 BPM."""
    content = FakeContent(bpm=13600)
    imp = make_importer(db=FakeDatabase([content]))
    data = list(imp.track_cache.values())[0]
    assert data.bpm == pytest.approx(136.0)

  def test_key_camelot_wird_konvertiert(self):
    """KeyName 'Am' wird zu Camelot '8A' konvertiert."""
    content = FakeContent(key_name="Am")
    imp = make_importer(db=FakeDatabase([content]))
    data = list(imp.track_cache.values())[0]
    assert data.camelot_code == "8A"

  def test_camelot_key_bleibt_unveraendert(self):
    """KeyName '8A' (bereits Camelot) bleibt '8A'."""
    content = FakeContent(key_name="8A")
    imp = make_importer(db=FakeDatabase([content]))
    data = list(imp.track_cache.values())[0]
    assert data.camelot_code == "8A"

  def test_metadata_werden_geladen(self):
    content = FakeContent(
      title="Night Drive",
      artist_name="Djane Cosmic",
      genre_name="Techno",
    )
    imp = make_importer(db=FakeDatabase([content]))
    data = list(imp.track_cache.values())[0]
    assert data.title == "Night Drive"
    assert data.artist == "Djane Cosmic"
    assert data.genre == "Techno"

  def test_cues_werden_geladen(self):
    cue = FakeCue(in_msec=30000, comment="Drop")
    content = FakeContent(cues=[cue])
    imp = make_importer(db=FakeDatabase([content]))
    data = list(imp.track_cache.values())[0]
    assert data.cue_points is not None
    assert len(data.cue_points) == 1


# ─── Tests: get_track_data ────────────────────────────────────────────────────

class TestGetTrackData:
  """get_track_data() Lookup-Logik."""

  def test_exact_path_match(self, tmp_path):
    folder = str(tmp_path)
    filename = "track.mp3"
    imp = make_importer_with_track(folder, filename, bpm=12800)
    data = imp.get_track_data(os.path.join(folder, filename))
    assert data is not None
    assert data.bpm == pytest.approx(128.0)

  def test_filename_fallback(self, tmp_path):
    """Track in anderem Ordner, gleiches Filename → Fallback findet ihn."""
    original_folder = str(tmp_path / "original")
    filename = "track.mp3"
    imp = make_importer_with_track(original_folder, filename, bpm=14000)
    # Suche mit anderem Pfad, gleichem Dateinamen
    other_path = os.path.join(str(tmp_path / "moved"), filename)
    data = imp.get_track_data(other_path)
    assert data is not None
    assert data.bpm == pytest.approx(140.0)

  def test_nicht_gefunden_ergibt_none(self, tmp_path):
    content = FakeContent(folder_path=str(tmp_path), filename="track.mp3")
    imp = make_importer(db=FakeDatabase([content]))
    result = imp.get_track_data(str(tmp_path / "does_not_exist.mp3"))
    assert result is None

  def test_unavailable_ergibt_none(self):
    with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
      imp = RekordboxImporter()
    result = imp.get_track_data("C:\\Music\\track.mp3")
    assert result is None

  def test_pfad_case_insensitiv(self, tmp_path):
    """Windows-Pfade sind case-insensitiv — Grossbuchstaben matchen."""
    folder = str(tmp_path)
    filename = "Track.MP3"
    imp = make_importer_with_track(folder, filename)
    # Lookup mit lowercase
    lower_path = os.path.join(folder, filename.lower())
    data = imp.get_track_data(lower_path)
    # Normpath + lower macht beides gleich → Match
    assert data is not None


# ─── Tests: Statistics und Helpers ───────────────────────────────────────────

class TestStatisticsUndHelpers:
  """get_statistics(), get_available_count(), has_track()."""

  def test_get_statistics_unavailable(self):
    with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
      imp = RekordboxImporter()
    stats = imp.get_statistics()
    assert stats["available"] is False
    assert stats["total_tracks"] == 0

  def test_get_statistics_mit_tracks(self):
    content = FakeContent(bpm=12800, key_name="8A")
    imp = make_importer(db=FakeDatabase([content]))
    stats = imp.get_statistics()
    assert stats["available"] is True
    assert stats["total_tracks"] == 1
    assert stats["tracks_with_bpm"] == 1
    assert stats["tracks_with_key"] == 1

  def test_get_statistics_average_bpm(self):
    contents = [
      FakeContent(folder_path="C:\\Music", filename="a.mp3", bpm=12800),
      FakeContent(folder_path="C:\\Music", filename="b.mp3", bpm=14000),
    ]
    imp = make_importer(db=FakeDatabase(contents))
    stats = imp.get_statistics()
    assert stats["average_bpm"] == pytest.approx(134.0)

  def test_get_available_count(self):
    contents = [
      FakeContent(folder_path="C:\\Music", filename=f"t{i}.mp3")
      for i in range(4)
    ]
    imp = make_importer(db=FakeDatabase(contents))
    assert imp.get_available_count() == 4

  def test_get_available_count_ohne_db(self):
    with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
      imp = RekordboxImporter()
    assert imp.get_available_count() == 0

  def test_has_track_true(self, tmp_path):
    folder = str(tmp_path)
    filename = "track.mp3"
    imp = make_importer_with_track(folder, filename)
    assert imp.has_track(os.path.join(folder, filename)) is True

  def test_has_track_false(self, tmp_path):
    imp = make_importer(db=FakeDatabase([]))
    assert imp.has_track(str(tmp_path / "missing.mp3")) is False


# ─── Tests: RekordboxTrackData Dataclass ─────────────────────────────────────

class TestRekordboxTrackData:
  """RekordboxTrackData Datenklasse."""

  def test_default_werte_sind_none(self):
    data = RekordboxTrackData()
    assert data.bpm is None
    assert data.key is None
    assert data.camelot_code is None
    assert data.duration is None
    assert data.cue_points is None

  def test_felder_koennen_gesetzt_werden(self):
    data = RekordboxTrackData(bpm=136.0, camelot_code="8A", duration=240.0)
    assert data.bpm == 136.0
    assert data.camelot_code == "8A"
    assert data.duration == 240.0


# ─── Tests: Singleton ────────────────────────────────────────────────────────

class TestSingleton:
  """get_rekordbox_importer() Singleton-Logik."""

  def test_gibt_instanz_zurueck(self):
    rb_module._rekordbox_importer = None  # Reset
    try:
      with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
        imp = get_rekordbox_importer()
      assert isinstance(imp, RekordboxImporter)
    finally:
      rb_module._rekordbox_importer = None  # Cleanup

  def test_singleton_wird_wiederverwendet(self):
    rb_module._rekordbox_importer = None  # Reset
    try:
      with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
        i1 = get_rekordbox_importer()
        i2 = get_rekordbox_importer()
      assert i1 is i2
    finally:
      rb_module._rekordbox_importer = None  # Cleanup

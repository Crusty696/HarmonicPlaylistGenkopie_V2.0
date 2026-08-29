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


class FakeBeatEntry:
  """Simuliert einen PQTZ-Beatgrid-Eintrag ohne Rekordbox-Daten."""

  def __init__(self, beat, time):
    self.beat = beat
    self.time = time


class FakeBeatTag:
  """Simuliert beide im Importer unterstuetzten PQTZ-Tag-Formen."""

  def __init__(self, beats=None, times=None, entries=None):
    self.beats = beats
    self.times = times
    self.entries = entries


class FakeAnlzFile:
  """Minimaler ANLZ-Stub fuer Pure-Python-Downbeat-Tests."""

  def __init__(self, tag):
    self.PQTZ = tag


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
    # pyrekordbox: DjmdContent.FolderPath ist der VOLLE Dateipfad (inkl. Name),
    # nicht der Ordner. Fixture bildet das real ab (Audit-Fix 2026-07-21).
    self.FolderPath = os.path.join(folder_path, filename) if filename else folder_path
    self.ID = "1"
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


class TestSafeDuration:
  """Nur belastbare positive Rekordbox-Dauern duerfen weiterfliessen."""

  @pytest.mark.parametrize(
    "raw_duration",
    [None, "", "kaputt", 0, -1, float("nan"), float("inf"), -float("inf"), True],
  )
  def test_ungueltige_dauer_ergibt_none(self, raw_duration):
    assert RekordboxImporter._safe_duration(raw_duration) is None

  @pytest.mark.parametrize("raw_duration", [240, 240.5, "240.5"])
  def test_positive_endliche_dauer_wird_uebernommen(self, raw_duration):
    assert RekordboxImporter._safe_duration(raw_duration) == pytest.approx(240.5 if raw_duration != 240 else 240.0)


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

  def test_defekter_mittlerer_cue_verwirft_spaetere_gueltige_cues_nicht(self):
    imp = make_importer()

    class BrokenCue:
      @property
      def InMsec(self):
        raise RuntimeError("Kaputt")

    result = imp._extract_cue_points([
      FakeCue(in_msec=1000, comment="Erster"),
      BrokenCue(),
      FakeCue(in_msec=3000, comment="Letzter"),
    ])

    assert [cue["name"] for cue in result] == ["Erster", "Letzter"]
    assert [cue["position"] for cue in result] == [1.0, 3.0]


class TestRekordboxTimeHeuristic:
  """Gemeinsamer ms/s-Vertrag fuer Cues und Downbeats."""

  def test_cue_bis_einschliesslich_100_wird_als_millisekunden_interpretiert(self):
    imp = make_importer()
    result = imp._extract_cue_points([FakeCue(in_msec=100)])
    assert result[0]["position"] == pytest.approx(0.1)

  def test_cue_ueber_100_wird_ebenfalls_als_millisekunden_interpretiert(self):
    imp = make_importer()
    result = imp._extract_cue_points([FakeCue(in_msec=101)])
    assert result[0]["position"] == pytest.approx(0.101)

  @pytest.mark.parametrize(
    "raw_time, expected",
    [(12.5, 12.5), (1.5, 1.5), (100.0, 100.0), (101.0, 101.0)],
  )
  def test_downbeat_flache_tagform_verwendet_pyrekordbox_sekunden(
    self, raw_time, expected
  ):
    tag = FakeBeatTag(beats=[1], times=[raw_time])
    result = RekordboxImporter._extract_first_downbeat_from_anlz(
      [FakeAnlzFile(tag)]
    )
    assert result == pytest.approx(expected)

  def test_downbeat_entry_tagform_normalisiert_sekunden_und_ms(self):
    tag = FakeBeatTag(entries=[FakeBeatEntry(1, 1500)])
    result = RekordboxImporter._extract_first_downbeat_from_anlz(
      [FakeAnlzFile(tag)]
    )
    assert result == pytest.approx(1.5)

  def test_flache_tagform_teilt_pyrekordbox_sekunden_nicht_erneut(self):
    tag = FakeBeatTag(beats=[2, 3], times=[0.434, 0.868])

    result = RekordboxImporter._extract_beatgrid_from_anlz([FakeAnlzFile(tag)])

    assert result == [
      {"beat": 2, "time": 0.434},
      {"beat": 3, "time": 0.868},
    ]

  @pytest.mark.parametrize(
    "tag",
    [
      FakeBeatTag(beats=[1, 2, 3, 4], times=[0.0, 0.5, 1.0, 1.5]),
      FakeBeatTag(entries=[
        FakeBeatEntry(1, 0), FakeBeatEntry(2, 500),
        FakeBeatEntry(3, 1000), FakeBeatEntry(4, 1500),
      ]),
    ],
  )
  def test_vollstaendiges_beatgrid_wird_aus_beiden_tagformen_extrahiert(self, tag):
    result = RekordboxImporter._extract_beatgrid_from_anlz([FakeAnlzFile(tag)])

    assert result == [
      {"beat": 1, "time": 0.0},
      {"beat": 2, "time": 0.5},
      {"beat": 3, "time": 1.0},
      {"beat": 4, "time": 1.5},
    ]

  def test_defekter_mittlerer_entry_verwirft_gueltige_gridpunkte_nicht(self):
    tag = FakeBeatTag(entries=[
      FakeBeatEntry(1, 0),
      FakeBeatEntry("kaputt", 500),
      FakeBeatEntry(3, 1000),
    ])

    result = RekordboxImporter._extract_beatgrid_from_anlz([FakeAnlzFile(tag)])

    assert result == [
      {"beat": 1, "time": 0.0},
      {"beat": 3, "time": 1.0},
    ]

  def test_first_downbeat_wird_aus_vollstaendigem_grid_abgeleitet(self, monkeypatch):
    path = os.path.join("C:\\Music", "track.mp3")
    imp = make_importer_with_track("C:\\Music", "track.mp3")
    monkeypatch.setattr(imp, "get_beatgrid", lambda _path: [
      {"beat": 3, "time": 0.0},
      {"beat": 4, "time": 0.5},
      {"beat": 1, "time": 1.0},
      {"beat": 2, "time": 1.5},
    ])

    assert imp.get_first_downbeat(path) == pytest.approx(1.0)


class TestBeatgridCacheSignatur:
  """Manuelle Rekordbox-Gridkorrekturen muessen den HPG-Cache invalidieren."""

  def test_identisches_grid_liefert_stabile_signatur(self, monkeypatch):
    path = os.path.join("C:\\Music", "track.mp3")
    imp = make_importer_with_track("C:\\Music", "track.mp3")
    grid = [
      {"beat": 1, "time": 0.0},
      {"beat": 2, "time": 0.5},
      {"beat": 3, "time": 1.0},
    ]
    monkeypatch.setattr(imp, "get_beatgrid", lambda _path: list(grid))

    assert imp.get_track_signature(path) == imp.get_track_signature(path)

  def test_spaeter_gridtick_aendert_die_signatur(self, monkeypatch):
    path = os.path.join("C:\\Music", "track.mp3")
    imp = make_importer_with_track("C:\\Music", "track.mp3")
    grids = iter([
      [
        {"beat": 1, "time": 0.0},
        {"beat": 2, "time": 0.5},
        {"beat": 3, "time": 1.0},
      ],
      [
        {"beat": 1, "time": 0.0},
        {"beat": 2, "time": 0.5},
        {"beat": 3, "time": 1.025},
      ],
    ])
    monkeypatch.setattr(imp, "get_beatgrid", lambda _path: next(grids))

    before = imp.get_track_signature(path)
    after = imp.get_track_signature(path)

    assert before != after

  def test_geaenderte_pssi_phrasen_aendern_die_signatur(self, monkeypatch):
    path = os.path.join("C:\\Music", "track.mp3")
    imp = make_importer_with_track("C:\\Music", "track.mp3")
    monkeypatch.setattr(imp, "get_beatgrid", lambda _path: [
      {"beat": 1, "time": 0.0},
      {"beat": 2, "time": 0.5},
    ])
    phrasen = iter([
      [{"start_s": 0.0, "end_s": 16.0, "label": "Intro"}],
      [{"start_s": 0.0, "end_s": 16.0, "label": "Chorus"}],
    ])
    monkeypatch.setattr(imp, "get_phrases", lambda _path: next(phrasen))

    before = imp.get_track_signature(path)
    after = imp.get_track_signature(path)

    assert before != after

  def test_signatur_downbeat_und_phrasen_teilen_einen_anlz_snapshot(self):
    path = os.path.join("C:\\Music", "track.mp3")
    imp = make_importer_with_track("C:\\Music", "track.mp3")
    aufrufe = 0
    anlz = FakeAnlzFile(FakeBeatTag(
      beats=[1, 2, 3, 4], times=[0.0, 0.5, 1.0, 1.5],
    ))

    def read_anlz_files(_content_id):
      nonlocal aufrufe
      aufrufe += 1
      return {"ANLZ0000.DAT": anlz}

    imp.db.read_anlz_files = read_anlz_files

    assert imp.get_track_signature(path)
    assert imp.get_first_downbeat(path) == pytest.approx(0.0)
    assert imp.get_phrases(path) == []
    assert aufrufe == 1

  def test_signatur_leert_alle_dauer_memos_nur_fuer_diese_content_id(
    self, monkeypatch
  ):
    path = os.path.join("C:\\Music", "track.mp3")
    imp = make_importer_with_track("C:\\Music", "track.mp3")
    imp._phrases_cache = {
      ("1", 0.0): [{"label": "alt-null"}],
      ("1", 90.0): [{"label": "alt-90"}],
      ("andere", 120.0): [{"label": "behalten"}],
    }
    monkeypatch.setattr(imp, "get_beatgrid", lambda _path: [])
    monkeypatch.setattr(imp, "get_phrases", lambda _path: [])

    assert imp.get_track_signature(path)
    assert imp._phrases_cache == {
      ("andere", 120.0): [{"label": "behalten"}]
    }


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

  def test_defekter_mittlerer_record_verwirft_spaetere_tracks_nicht(self):
    first = FakeContent(folder_path="C:\\Music", filename="first.mp3")
    last = FakeContent(folder_path="C:\\Music", filename="last.mp3")

    class BrokenContent:
      FolderPath = "C:\\Music\\broken.mp3"
      FileNameL = "broken.mp3"
      FileNameS = "broken.mp3"
      ID = "broken"
      BPM = 12800
      KeyName = "8A"
      Length = 240

      @property
      def Title(self):
        raise RuntimeError("Kaputter Record")

    imp = make_importer(db=FakeDatabase([first, BrokenContent(), last]))

    assert set(imp.track_cache) == {
      os.path.normpath("C:\\Music\\first.mp3").lower(),
      os.path.normpath("C:\\Music\\last.mp3").lower(),
    }

  def test_unlesbarer_dateiname_im_fehlerlog_stoppt_scan_nicht(self):
    class BrokenNameContent:
      ID = "broken-name"

      @property
      def FileNameL(self):
        raise RuntimeError("Dateiname kaputt")

    last = FakeContent(folder_path="C:\\Music", filename="last.mp3")
    imp = make_importer(db=FakeDatabase([BrokenNameContent(), last]))

    assert list(imp.track_cache) == [
      os.path.normpath("C:\\Music\\last.mp3").lower()
    ]

  @pytest.mark.parametrize(
    "length",
    [0, -1, float("nan"), float("inf"), -float("inf"), "kaputt", True],
  )
  def test_ungueltige_record_dauer_wird_als_unbekannt_importiert(self, length):
    content = FakeContent(length=length)
    imp = make_importer(db=FakeDatabase([content]))

    assert next(iter(imp.track_cache.values())).duration is None

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

  def test_mehrdeutiger_filename_fallback_wird_verworfen(self, tmp_path):
    """Gleichnamige Tracks duerfen keine falschen RB-Metadaten liefern."""
    filename = "track.mp3"
    first = FakeContent(
      folder_path=str(tmp_path / "first"), filename=filename, bpm=12800
    )
    second = FakeContent(
      folder_path=str(tmp_path / "second"), filename=filename, bpm=14000
    )
    imp = make_importer(db=FakeDatabase([first, second]))

    moved_path = str(tmp_path / "moved" / filename)

    assert imp.get_track_data(moved_path) is None
    assert imp.get_track_data(str(tmp_path / "first" / filename)).bpm == pytest.approx(128.0)
    assert imp.get_track_data(str(tmp_path / "second" / filename)).bpm == pytest.approx(140.0)

  def test_widerspruechliche_records_am_exakten_pfad_werden_verworfen(self, tmp_path):
    """Auch doppelte RB-Pfad-Records duerfen nicht zufaellig gewinnen."""
    filename = "track.mp3"
    first = FakeContent(
      folder_path=str(tmp_path), filename=filename, bpm=12800, key_name="8A"
    )
    second = FakeContent(
      folder_path=str(tmp_path), filename=filename, bpm=14000, key_name="9A"
    )
    imp = make_importer(db=FakeDatabase([first, second]))

    exact_path = str(tmp_path / filename)

    assert exact_path.lower() in imp._ambiguous_paths
    assert imp.get_track_data(exact_path) is None

  def test_unanalysierter_duplicate_record_verliert_gegen_analyse(self, tmp_path):
    """Ein BPM=0-Record darf einen analysierten Record nicht ueberschreiben."""
    filename = "track.mp3"
    unanalysed = FakeContent(
      folder_path=str(tmp_path), filename=filename, bpm=0, key_name="Bmin"
    )
    analysed = FakeContent(
      folder_path=str(tmp_path), filename=filename, bpm=14000, key_name="10A"
    )
    imp = make_importer(db=FakeDatabase([unanalysed, analysed]))

    data = imp.get_track_data(str(tmp_path / filename))

    assert data is not None
    assert data.bpm == pytest.approx(140.0)
    assert data.camelot_code == "10A"

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

  def test_different_content_ids_are_conflicting(self):
    left = RekordboxTrackData(bpm=128.0, content_id="old")
    right = RekordboxTrackData(bpm=128.0, content_id="new")

    assert RekordboxImporter._track_data_conflicts(left, right) is True

  def test_different_cue_sets_are_conflicting(self):
    left = RekordboxTrackData(
      bpm=128.0, cue_points=[{"name": "MIX IN", "position": 30.0}]
    )
    right = RekordboxTrackData(
      bpm=128.0, cue_points=[{"name": "MIX IN", "position": 90.0}]
    )

    assert RekordboxImporter._track_data_conflicts(left, right) is True

  def test_same_cues_in_different_order_are_not_conflicting(self):
    cues = [
      {"name": "IN", "position": 30.0},
      {"name": "OUT", "position": 240.0},
    ]
    left = RekordboxTrackData(bpm=128.0, cue_points=cues)
    right = RekordboxTrackData(bpm=128.0, cue_points=list(reversed(cues)))

    assert RekordboxImporter._track_data_conflicts(left, right) is False


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


# --- Prozesspruefung: warnt die App, wenn Rekordbox noch offen ist? ---------


def test_is_rekordbox_running_reports_live_process(monkeypatch):
  """Laufender Prozess -> True. Rekordbox checkpointet sein WAL erst beim
  Beenden, HPG liest solange einen veralteten Stand."""
  import pyrekordbox.utils as rb_utils

  monkeypatch.setattr(rb_module, "REKORDBOX_AVAILABLE", True)
  monkeypatch.setattr(rb_utils, "get_rekordbox_pid", lambda *a, **k: 4711)
  assert rb_module.is_rekordbox_running() is True

  monkeypatch.setattr(rb_utils, "get_rekordbox_pid", lambda *a, **k: 0)
  assert rb_module.is_rekordbox_running() is False


def test_is_rekordbox_running_survives_psutil_failure(monkeypatch):
  """Ein Fehler in der Prozessliste darf den App-Start nicht kippen."""
  import pyrekordbox.utils as rb_utils

  def boom(*a, **k):
    raise OSError("Zugriff verweigert")

  monkeypatch.setattr(rb_module, "REKORDBOX_AVAILABLE", True)
  monkeypatch.setattr(rb_utils, "get_rekordbox_pid", boom)
  assert rb_module.is_rekordbox_running() is False


def test_is_rekordbox_running_false_without_pyrekordbox(monkeypatch):
  monkeypatch.setattr(rb_module, "REKORDBOX_AVAILABLE", False)
  assert rb_module.is_rekordbox_running() is False


# --- summarize_coverage: warum konnte ein Track keine RB-Daten nutzen? ------

# Keine Backslash-Literale: os.path.join baut die Windows-Pfade auf.
MUSIC_DIR = os.path.join("C:", os.sep, "Music")


def _music(name):
  return os.path.join(MUSIC_DIR, name)


class TestSummarizeCoverage:
  """Trennt analysiert / unanalysiert / mehrdeutig / nicht in Collection."""

  def test_analysierter_track_zaehlt_als_nutzbar(self):
    imp = make_importer_with_track(MUSIC_DIR, "a.mp3", bpm=14000)
    cov = imp.summarize_coverage([_music("a.mp3")])
    assert cov.available is True
    assert (cov.total, cov.with_analysis, cov.degraded) == (1, 1, 0)

  def test_record_ohne_bpm_gilt_als_unanalysiert(self):
    """Davids Realfall: Track ist in der Collection, aber nie analysiert."""
    imp = make_importer_with_track(MUSIC_DIR, "a.mp3", bpm=0)
    cov = imp.summarize_coverage([_music("a.mp3")])
    assert cov.without_analysis == 1
    assert cov.with_analysis == 0
    assert cov.not_in_collection == 0
    assert cov.degraded == 1
    assert cov.examples_without_analysis == ["a.mp3"]

  def test_fremder_track_ist_kein_befund(self):
    imp = make_importer_with_track(MUSIC_DIR, "a.mp3", bpm=14000)
    cov = imp.summarize_coverage([_music("fremd.mp3")])
    assert cov.not_in_collection == 1
    assert cov.degraded == 0

  def test_mehrdeutiger_pfad_wird_getrennt_gezaehlt(self):
    """Widerspruechliche Records fuer denselben Pfad -> bewusst verworfen."""
    contents = [
      FakeContent(folder_path=MUSIC_DIR, filename="a.mp3", bpm=12800),
      FakeContent(folder_path=MUSIC_DIR, filename="a.mp3", bpm=14000),
    ]
    imp = make_importer(db=FakeDatabase(contents))
    assert imp._ambiguous_paths, "Fixture erzeugt keinen Konflikt"
    cov = imp.summarize_coverage([_music("a.mp3")])
    assert cov.ambiguous == 1
    assert cov.without_analysis == 0
    assert cov.degraded == 1
    assert cov.examples_ambiguous == ["a.mp3"]

  def test_summanden_ergeben_immer_die_gesamtzahl(self):
    contents = [
      FakeContent(folder_path=MUSIC_DIR, filename="ok.mp3", bpm=14000),
      FakeContent(folder_path=MUSIC_DIR, filename="leer.mp3", bpm=0),
    ]
    imp = make_importer(db=FakeDatabase(contents))
    paths = [_music("ok.mp3"), _music("leer.mp3"), _music("weg.mp3")]
    cov = imp.summarize_coverage(paths)
    assert cov.total == 3
    assert (
      cov.with_analysis + cov.without_analysis
      + cov.ambiguous + cov.not_in_collection
    ) == cov.total

  def test_ohne_rekordbox_kein_befund(self):
    with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
      imp = RekordboxImporter()
    cov = imp.summarize_coverage([_music("a.mp3")])
    assert cov.available is False
    assert cov.total == 0
    assert cov.degraded == 0

  def test_beispiele_sind_gedeckelt(self):
    contents = [
      FakeContent(folder_path=MUSIC_DIR, filename=f"t{i}.mp3", bpm=0)
      for i in range(6)
    ]
    imp = make_importer(db=FakeDatabase(contents))
    cov = imp.summarize_coverage([_music(f"t{i}.mp3") for i in range(6)])
    assert cov.without_analysis == 6
    assert len(cov.examples_without_analysis) == 3


# ─── Tests: get_phrases (PSSI) ───────────────────────────────────────────────

def test_get_phrases_liest_ext_und_dat_ueber_read_anlz_files(monkeypatch):
  from types import SimpleNamespace
  import numpy as np

  imp = RekordboxImporter.__new__(RekordboxImporter)
  imp.track_cache = {}
  imp.basename_cache = {}
  imp._ambiguous_paths = set()
  imp._downbeat_cache = {}
  imp._phrases_cache = {}
  data = RekordboxTrackData(bpm=128.0, duration=60.0, content_id="42")
  imp.get_track_data = lambda path: data
  imp.is_available = lambda: True

  class _Pq:
    def get(self):
      t = np.arange(129) * 0.46875
      return np.array([(i % 4) + 1 for i in range(129)]), np.full(129, 128.0), t

  class _File:
    def __init__(self, tags):
      self._tags = tags

    def get_tag(self, k):
      if k not in self._tags:
        raise KeyError(k)
      return self._tags[k]

  pssi = SimpleNamespace(content=SimpleNamespace(mood=1, end_beat=129, entries=[
    SimpleNamespace(index=1, beat=1, kind=1, k1=0, k2=0, k3=0, fill=0, beat_fill=0),
    SimpleNamespace(index=2, beat=65, kind=5, k1=1, k2=0, k3=0, fill=0, beat_fill=0),
  ]))
  files = {"X/ANLZ0000.DAT": _File({"PQTZ": _Pq()}), "X/ANLZ0000.EXT": _File({"PSSI": pssi})}
  imp.db = SimpleNamespace(read_anlz_files=lambda cid: files)

  phrases = imp.get_phrases("C:/irgendwo/track.mp3")
  assert [p["label"] for p in phrases] == ["Intro", "Chorus"]
  assert phrases[1]["start_s"] == pytest.approx(64 * 0.46875)
  # memoisiert
  imp.db = None
  assert imp.get_phrases("C:/irgendwo/track.mp3") == phrases


def test_get_phrases_memo_trennt_effektive_dauern(monkeypatch):
  from types import SimpleNamespace
  from hpg_core import rekordbox_phrases

  imp = RekordboxImporter.__new__(RekordboxImporter)
  imp._phrases_cache = {}
  imp.db = object()
  data = RekordboxTrackData(duration=None, content_id="42")
  imp.get_track_data = lambda _path: data
  tagged = SimpleNamespace(get_tag=lambda _key: object())
  imp._read_anlz_files = lambda _content_id: [tagged]
  verwendete_dauern = []

  def fake_phrases(_ext, _dat, duration):
    verwendete_dauern.append(duration)
    return [{"start_s": 0.0, "end_s": duration, "label": "Intro"}]

  monkeypatch.setattr(rekordbox_phrases, "phrases_from_anlz", fake_phrases)

  assert imp.get_phrases("track.wav")[0]["end_s"] == 0.0
  assert imp.get_phrases("track.wav", duration=90.0)[0]["end_s"] == 90.0
  assert imp.get_phrases("track.wav", duration=90.0)[0]["end_s"] == 90.0
  assert imp.get_phrases("track.wav", duration=120.0)[0]["end_s"] == 120.0
  assert verwendete_dauern == [0.0, 90.0, 120.0]


def test_get_phrases_positiver_override_gewinnt_gegen_rb_dauer(monkeypatch):
  from types import SimpleNamespace
  from hpg_core import rekordbox_phrases

  imp = RekordboxImporter.__new__(RekordboxImporter)
  imp._phrases_cache = {}
  imp.db = object()
  imp.get_track_data = lambda _path: RekordboxTrackData(
    duration=60.0, content_id="42"
  )
  tagged = SimpleNamespace(get_tag=lambda _key: object())
  imp._read_anlz_files = lambda _content_id: [tagged]
  verwendete_dauern = []
  monkeypatch.setattr(
    rekordbox_phrases,
    "phrases_from_anlz",
    lambda _ext, _dat, duration: verwendete_dauern.append(duration) or [],
  )

  assert imp.get_phrases("track.wav", duration=90.0) == []
  assert verwendete_dauern == [90.0]
  assert set(imp._phrases_cache) == {("42", 90.0)}


@pytest.mark.parametrize("override", [float("nan"), float("inf"), -1.0, -0.0])
def test_get_phrases_ungueltige_dauer_faellt_auf_rb_dauer_zurueck(
  monkeypatch, override
):
  from types import SimpleNamespace
  from hpg_core import rekordbox_phrases

  imp = RekordboxImporter.__new__(RekordboxImporter)
  imp._phrases_cache = {}
  imp.db = object()
  imp.get_track_data = lambda _path: RekordboxTrackData(
    duration=60.0, content_id="42"
  )
  tagged = SimpleNamespace(get_tag=lambda _key: object())
  imp._read_anlz_files = lambda _content_id: [tagged]
  verwendete_dauern = []
  monkeypatch.setattr(
    rekordbox_phrases,
    "phrases_from_anlz",
    lambda _ext, _dat, duration: verwendete_dauern.append(duration) or [],
  )

  assert imp.get_phrases("track.wav", duration=override) == []
  assert verwendete_dauern == [60.0]
  assert set(imp._phrases_cache) == {("42", 60.0)}


@pytest.mark.parametrize(
  ("override", "rb_duration"),
  [
    (None, None),
    (float("nan"), float("inf")),
    (-1.0, -0.0),
  ],
)
def test_get_phrases_beide_dauern_ungueltig_verwendet_exakt_null(
  monkeypatch, override, rb_duration
):
  from types import SimpleNamespace
  from hpg_core import rekordbox_phrases

  imp = RekordboxImporter.__new__(RekordboxImporter)
  imp._phrases_cache = {}
  imp.db = object()
  imp.get_track_data = lambda _path: RekordboxTrackData(
    duration=rb_duration, content_id="42"
  )
  tagged = SimpleNamespace(get_tag=lambda _key: object())
  imp._read_anlz_files = lambda _content_id: [tagged]
  verwendete_dauern = []
  monkeypatch.setattr(
    rekordbox_phrases,
    "phrases_from_anlz",
    lambda _ext, _dat, duration: verwendete_dauern.append(duration) or [],
  )

  assert imp.get_phrases("track.wav", duration=override) == []
  assert verwendete_dauern == [0.0]
  assert set(imp._phrases_cache) == {("42", 0.0)}

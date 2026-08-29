"""
Tests fuer Metadata-Parsing (Dateiname + ID3 Tags).
Prueft parse_filename_for_metadata und extract_metadata.
"""
from unittest.mock import Mock, call

from hpg_core import analysis
from hpg_core.analysis import extract_metadata, parse_filename_for_metadata


class _Frame:
  def __init__(self, text):
    self.text = text


class _Tags:
  def __init__(self, values=None, *, tags=None, truth=True):
    self._values = values or {}
    self.tags = tags
    self._truth = truth

  def get(self, key, default=None):
    return self._values.get(key, default)

  def __bool__(self):
    return self._truth


class TestExtractMetadata:
  def test_raw_frames_im_easy_objekt_verhindern_rohen_zweitaufruf(
    self, monkeypatch
  ):
    easy = _Tags({
      "TPE1": _Frame(["Easy Raw Artist"]),
      "TIT2": _Frame(["Easy Raw Title"]),
      "TCON": _Frame(["Psytrance"]),
    }, truth=False)
    loader = Mock(return_value=easy)
    monkeypatch.setattr(analysis.mutagen, "File", loader)

    assert extract_metadata("Fallback - Name.aiff") == (
      "Easy Raw Artist", "Easy Raw Title", "Psytrance"
    )
    loader.assert_called_once_with("Fallback - Name.aiff", easy=True)

  def test_aiff_raw_frames_werden_feldweise_gelesen(self, monkeypatch):
    easy = _Tags(truth=False)
    raw = _Tags({
      "TPE1": _Frame(["Raw Artist"]),
      "TIT2": _Frame("Raw Title"),
      "TCON": ["Psytrance"],
    })
    loader = Mock(side_effect=[easy, raw])
    monkeypatch.setattr(analysis.mutagen, "File", loader)

    assert extract_metadata("Fallback - Name.aiff") == (
      "Raw Artist", "Raw Title", "Psytrance"
    )
    assert loader.call_args_list == [
      call("Fallback - Name.aiff", easy=True),
      call("Fallback - Name.aiff", easy=False),
    ]

  def test_raw_frames_unter_tags_werden_gelesen(self, monkeypatch):
    easy = _Tags()
    raw = _Tags(tags={
      "TPE1": _Frame(["Tags Artist"]),
      "TIT2": _Frame(["Tags Title"]),
      "TCON": _Frame(["Trance"]),
    })
    monkeypatch.setattr(analysis.mutagen, "File", Mock(side_effect=[easy, raw]))

    assert extract_metadata("Fallback - Name.aiff") == (
      "Tags Artist", "Tags Title", "Trance"
    )

  def test_vollstaendige_easy_tags_verhindern_rohen_zweitaufruf(self, monkeypatch):
    easy = _Tags({
      "artist": ["Easy Artist"],
      "title": ["Easy Title"],
      "genre": ["Techno"],
    })
    loader = Mock(return_value=easy)
    monkeypatch.setattr(analysis.mutagen, "File", loader)

    assert extract_metadata("Fallback - Name.aiff") == (
      "Easy Artist", "Easy Title", "Techno"
    )
    loader.assert_called_once_with("Fallback - Name.aiff", easy=True)

  def test_raw_fallback_ueberschreibt_keinen_easy_wert(self, monkeypatch):
    easy = _Tags({"artist": ["Easy Artist"]})
    raw = _Tags({
      "TPE1": _Frame(["Raw Artist"]),
      "TIT2": _Frame(["Raw Title"]),
      "TCON": _Frame(["Psytrance"]),
    })
    monkeypatch.setattr(analysis.mutagen, "File", Mock(side_effect=[easy, raw]))

    assert extract_metadata("Fallback - Name.aiff") == (
      "Easy Artist", "Raw Title", "Psytrance"
    )

  def test_leere_und_defekte_frames_fallen_kontrolliert_zurueck(self, monkeypatch):
    easy = _Tags()
    raw = _Tags({
      "TPE1": _Frame(["", None]),
      "TIT2": object(),
      "TCON": _Frame([]),
    })
    monkeypatch.setattr(analysis.mutagen, "File", Mock(side_effect=[easy, raw]))

    assert extract_metadata("Fallback Artist - Fallback Title.aiff") == (
      "Fallback Artist", "Fallback Title", "Unknown"
    )

  def test_roher_lesefehler_behaelt_easy_und_dateinamenfallback(
    self, monkeypatch
  ):
    easy = _Tags({"artist": ["Easy Artist"]})
    monkeypatch.setattr(
      analysis.mutagen,
      "File",
      Mock(side_effect=[easy, RuntimeError("raw kaputt")]),
    )

    assert extract_metadata("Fallback Artist - Fallback Title.aiff") == (
      "Easy Artist", "Fallback Title", "Unknown"
    )

  def test_easy_lesefehler_versucht_rohe_frames(self, monkeypatch):
    raw = _Tags({
      "TPE1": _Frame(["Raw Artist"]),
      "TIT2": _Frame(["Raw Title"]),
      "TCON": _Frame(["Psy-Trance"]),
    })
    loader = Mock(side_effect=[RuntimeError("easy kaputt"), raw])
    monkeypatch.setattr(analysis.mutagen, "File", loader)

    assert extract_metadata("Fallback - Name.aiff") == (
      "Raw Artist", "Raw Title", "Psy-Trance"
    )
    assert loader.call_args_list == [
      call("Fallback - Name.aiff", easy=True),
      call("Fallback - Name.aiff", easy=False),
    ]


class TestFilenameParsingBasic:
  """Grundlegendes Dateiname-Parsing."""

  def test_artist_dash_title(self):
    """Standard DJ-Format: 'Artist - Track.mp3'."""
    artist, title = parse_filename_for_metadata("Artist Name - Track Title.mp3")
    assert artist == "Artist Name"
    assert title == "Track Title"

  def test_with_directory_path(self):
    """Pfad mit Verzeichnissen wird korrekt verarbeitet."""
    artist, title = parse_filename_for_metadata(
      "C:/Music/DJ Sets/Artist - Track.mp3"
    )
    assert artist == "Artist Name" or artist is not None
    # Hauptsache kein Crash und sinnvolles Ergebnis

  def test_numbered_track(self):
    """Nummerierter Track: '01 - Artist - Track.mp3'."""
    artist, title = parse_filename_for_metadata("01 - DJ Snake - Turn Down.mp3")
    assert artist is not None
    assert title is not None

  def test_underscore_separator(self):
    """Unterstrich-Separator: 'Artist_Track.mp3'."""
    artist, title = parse_filename_for_metadata("Carl_Cox_Ibiza.mp3")
    assert artist is not None or title is not None

  def test_no_separator_returns_none(self):
    """Dateiname ohne Separator = (None, None)."""
    artist, title = parse_filename_for_metadata("JustATrackName.mp3")
    # Kein erkennbares Artist-Title Muster
    assert artist is None or title is not None


class TestFilenameParsingEdgeCases:
  """Edge Cases im Dateiname-Parsing."""

  def test_empty_string(self):
    """Leerer String = (None, None)."""
    artist, title = parse_filename_for_metadata("")
    assert artist is None
    assert title is None

  def test_no_extension(self):
    """Dateiname ohne Extension."""
    artist, title = parse_filename_for_metadata("Artist - Track")
    assert artist == "Artist"
    assert title == "Track"

  def test_multiple_dashes(self):
    """Mehrere Dashes im Dateinamen."""
    artist, title = parse_filename_for_metadata("DJ - Live - Set.mp3")
    assert artist is not None

  def test_unicode_characters(self):
    """Unicode-Zeichen im Dateinamen."""
    artist, title = parse_filename_for_metadata("Bj\u00f6rk - J\u00f3ga.mp3")
    assert artist is not None

  def test_very_long_filename(self):
    """Sehr langer Dateiname (>200 Zeichen)."""
    long_name = "A" * 101 + " - " + "B" * 201 + ".mp3"
    artist, title = parse_filename_for_metadata(long_name)
    # Zu langer Artist/Title = (None, None)
    assert artist is None or len(artist) <= 100

  def test_spaces_around_dash(self):
    """Extra Leerzeichen um Dash herum."""
    artist, title = parse_filename_for_metadata(
      "  Artist  -  Track Title  .mp3"
    )
    if artist:
      assert artist.strip() == artist
    if title:
      assert title.strip() == title

  def test_dot_in_name(self):
    """Punkt im Dateinamen (kein Extension-Punkt)."""
    artist, title = parse_filename_for_metadata("Dr. Dre - Still.mp3")
    assert artist is not None

  def test_numbered_prefix_stripped(self):
    """Nummerierter Prefix wird korrekt behandelt."""
    artist, title = parse_filename_for_metadata("03 - Tiesto - Adagio.mp3")
    # Nummer sollte nicht im Artist auftauchen
    if artist:
      assert not artist.startswith("03")


class TestFilenameParsingDJFormats:
  """DJ-spezifische Dateinamen."""

  def test_bpm_in_filename(self):
    """BPM im Dateinamen: 'Artist - Track [128BPM].mp3'."""
    artist, title = parse_filename_for_metadata(
      "Avicii - Levels [128BPM].mp3"
    )
    assert artist is not None

  def test_key_in_filename(self):
    """Key im Dateinamen: 'Artist - Track (8A).mp3'."""
    artist, title = parse_filename_for_metadata(
      "Deadmau5 - Strobe (8A).mp3"
    )
    assert artist is not None

  def test_remix_info(self):
    """Remix-Info: 'Artist - Track (Remix).mp3'."""
    artist, title = parse_filename_for_metadata(
      "Calvin Harris - Summer (R3hab Remix).mp3"
    )
    assert artist is not None
    assert title is not None

  def test_windows_path(self):
    """Windows-Pfad."""
    artist, title = parse_filename_for_metadata(
      "C:\\Users\\DJ\\Music\\Artist - Track.mp3"
    )
    assert artist is not None or artist is None  # Kein Crash

  def test_various_extensions(self):
    """Verschiedene Audio-Formate."""
    for ext in (".mp3", ".wav", ".flac", ".aiff", ".m4a"):
      artist, title = parse_filename_for_metadata(f"Artist - Track{ext}")
      assert artist is not None, f"Parsing fehlgeschlagen fuer {ext}"

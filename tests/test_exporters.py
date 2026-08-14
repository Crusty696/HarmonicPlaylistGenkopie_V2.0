"""
Tests fuer Playlist-Exporter (M3U8, Rekordbox XML, Base).
Prueft Export-Formate, Key-Mapping und Cue-Points.
"""
import os
import pytest
import tempfile
from hpg_core.exporters.base_exporter import ExportReport
from hpg_core.exporters.m3u8_exporter import M3U8Exporter
from tests.fixtures.track_factories import make_track


@pytest.fixture
def export_dir():
  """Temporaeres Verzeichnis fuer Export-Dateien."""
  with tempfile.TemporaryDirectory() as tmpdir:
    yield tmpdir


@pytest.fixture
def sample_playlist():
  """DJ-Playlist mit 3 Tracks fuer Export-Tests."""
  return [
    make_track(
      title="Summer Vibes", artist="DJ Sun",
      camelotCode="8A", bpm=128.0, duration=300.0,
      mix_in_point=30.0, mix_out_point=270.0,
      energy=75, genre="House",
    ),
    make_track(
      title="Night Drive", artist="Neon",
      camelotCode="9A", bpm=128.0, duration=330.0,
      mix_in_point=45.0, mix_out_point=285.0,
      energy=80, genre="Techno",
    ),
    make_track(
      title="Deep Blue", artist="Ocean",
      camelotCode="8A", bpm=126.0, duration=360.0,
      mix_in_point=30.0, mix_out_point=330.0,
      energy=65, genre="Deep House",
    ),
  ]


# ============================================================
# BaseExporter Tests
# ============================================================

class TestBaseExporter:
  """BaseExporter Validierung."""

  def test_validate_empty_playlist_raises(self):
    """Leere Playlist wirft ValueError."""
    exporter = M3U8Exporter()
    with pytest.raises(ValueError, match="empty"):
      exporter._validate_playlist([])

  def test_validate_invalid_objects_raises(self):
    """Nicht-Track Objekte werfen ValueError."""
    exporter = M3U8Exporter()
    with pytest.raises(ValueError, match="invalid"):
      exporter._validate_playlist(["not a track", 42])

  def test_validate_valid_playlist(self, sample_playlist):
    """Valide Playlist wirft keinen Fehler."""
    exporter = M3U8Exporter()
    exporter._validate_playlist(sample_playlist)  # Kein Exception

  def test_sanitize_filename(self):
    """Ungueltige Zeichen werden ersetzt."""
    exporter = M3U8Exporter()
    result = exporter._sanitize_filename('My:Playlist<>Test|?.m3u8')
    assert ":" not in result
    assert "<" not in result
    assert ">" not in result
    assert "|" not in result
    assert "?" not in result
    assert "*" not in result

  def test_sanitize_normal_filename(self):
    """Normaler Dateiname bleibt unveraendert."""
    exporter = M3U8Exporter()
    result = exporter._sanitize_filename("My Playlist 2024.m3u8")
    assert result == "My Playlist 2024.m3u8"


# ============================================================
# M3U8 Exporter Tests
# ============================================================

class TestM3U8ExporterBasics:
  """M3U8 Export Grundlagen."""

  def test_creates_file(self, sample_playlist, export_dir):
    """Export erstellt Datei."""
    path = os.path.join(export_dir, "test.m3u8")
    exporter = M3U8Exporter()
    exporter.export(sample_playlist, path)
    assert os.path.exists(path)

  def test_has_m3u_header(self, sample_playlist, export_dir):
    """Datei beginnt mit #EXTM3U Header."""
    path = os.path.join(export_dir, "test.m3u8")
    exporter = M3U8Exporter()
    exporter.export(sample_playlist, path)

    with open(path, "r", encoding="utf-8") as f:
      first_line = f.readline().strip()
    assert first_line == "#EXTM3U"

  def test_contains_all_tracks(self, sample_playlist, export_dir):
    """Alle Tracks sind in der Datei enthalten."""
    path = os.path.join(export_dir, "test.m3u8")
    exporter = M3U8Exporter()
    exporter.export(sample_playlist, path)

    with open(path, "r", encoding="utf-8") as f:
      content = f.read()

    for track in sample_playlist:
      assert track.filePath in content, (
        f"Track '{track.title}' fehlt in M3U8"
      )

  def test_contains_extinf_lines(self, sample_playlist, export_dir):
    """#EXTINF Zeilen fuer jeden Track vorhanden."""
    path = os.path.join(export_dir, "test.m3u8")
    exporter = M3U8Exporter()
    exporter.export(sample_playlist, path)

    with open(path, "r", encoding="utf-8") as f:
      content = f.read()

    extinf_count = content.count("#EXTINF:")
    assert extinf_count == len(sample_playlist), (
      f"{extinf_count} EXTINF-Zeilen (erwartet {len(sample_playlist)})"
    )

  def test_extinf_format(self, sample_playlist, export_dir):
    """#EXTINF Format: #EXTINF:duration,artist - title."""
    path = os.path.join(export_dir, "test.m3u8")
    exporter = M3U8Exporter()
    exporter.export(sample_playlist, path)

    with open(path, "r", encoding="utf-8") as f:
      content = f.read()

    # Erster Track
    track = sample_playlist[0]
    expected_duration = int(track.duration)
    assert f"#EXTINF:{expected_duration}," in content

  def test_playlist_name_in_header(self, sample_playlist, export_dir):
    """Playlist-Name im Header."""
    path = os.path.join(export_dir, "test.m3u8")
    exporter = M3U8Exporter()
    exporter.export(sample_playlist, path, playlist_name="My DJ Set")

    with open(path, "r", encoding="utf-8") as f:
      content = f.read()

    assert "#PLAYLIST:My DJ Set" in content

  def test_encoding_header(self, sample_playlist, export_dir):
    """Encoding-Header vorhanden."""
    path = os.path.join(export_dir, "test.m3u8")
    exporter = M3U8Exporter()
    exporter.export(sample_playlist, path)

    with open(path, "r", encoding="utf-8") as f:
      content = f.read()

    assert "#EXTENC:UTF-8" in content

  def test_relative_paths_for_usb_export(self, sample_playlist, export_dir):
    """USB-Modus schreibt Pfade relativ zum Speicherort der Playlist."""
    music_dir = os.path.join(export_dir, "music")
    usb_dir = os.path.join(export_dir, "usb")
    os.makedirs(music_dir)
    os.makedirs(usb_dir)
    sample_playlist[0].filePath = os.path.join(music_dir, "track.mp3")
    path = os.path.join(usb_dir, "set.m3u8")

    M3U8Exporter(relative_paths=True).export(sample_playlist[:1], path)

    content = open(path, "r", encoding="utf-8").read()
    assert "../music/track.mp3" in content.replace("\\", "/")


class TestM3U8Unicode:
  """M3U8 Unicode-Unterstuetzung."""

  def test_unicode_track_names(self, export_dir):
    """Unicode in Track-Namen wird korrekt exportiert."""
    tracks = [
      make_track(
        title="B\u00f6rk S\u00f6ng",
        artist="K\u00f6lner DJ",
        camelotCode="8A", bpm=128.0, duration=300.0,
      ),
    ]
    path = os.path.join(export_dir, "unicode.m3u8")
    exporter = M3U8Exporter()
    exporter.export(tracks, path)

    with open(path, "r", encoding="utf-8") as f:
      content = f.read()

    assert "K\u00f6lner DJ" in content
    assert "B\u00f6rk S\u00f6ng" in content

  def test_utf8_encoding(self, export_dir):
    """Datei ist UTF-8 encodiert."""
    tracks = [
      make_track(
        title="\u00c4\u00d6\u00dc\u00e4\u00f6\u00fc\u00df",
        artist="Test",
        camelotCode="8A", bpm=128.0, duration=300.0,
      ),
    ]
    path = os.path.join(export_dir, "utf8.m3u8")
    exporter = M3U8Exporter()
    exporter.export(tracks, path)

    # Lesen als UTF-8 darf nicht crashen
    with open(path, "r", encoding="utf-8") as f:
      content = f.read()
    assert "\u00c4\u00d6\u00dc" in content


class TestM3U8EdgeCases:
  """M3U8 Edge Cases."""

  def test_empty_playlist_raises(self, export_dir):
    """Leere Playlist wirft ValueError."""
    path = os.path.join(export_dir, "empty.m3u8")
    exporter = M3U8Exporter()
    with pytest.raises(ValueError):
      exporter.export([], path)

  def test_single_track(self, export_dir):
    """Einzelner Track wird korrekt exportiert."""
    tracks = [make_track(camelotCode="8A", bpm=128.0, duration=300.0)]
    path = os.path.join(export_dir, "single.m3u8")
    exporter = M3U8Exporter()
    exporter.export(tracks, path)

    with open(path, "r", encoding="utf-8") as f:
      content = f.read()

    assert "#EXTM3U" in content
    assert "#EXTINF:" in content

  def test_track_without_artist(self, export_dir):
    """Track ohne Artist-Info."""
    tracks = [
      make_track(
        artist=None, title="Unknown Track",
        camelotCode="8A", bpm=128.0, duration=300.0,
      ),
    ]
    path = os.path.join(export_dir, "no_artist.m3u8")
    exporter = M3U8Exporter()
    exporter.export(tracks, path)
    # Kein Crash, "Unknown Artist" als Fallback

  def test_format_info(self):
    """get_format_info gibt Dictionary zurueck."""
    exporter = M3U8Exporter()
    info = exporter.get_format_info()
    assert isinstance(info, dict)
    assert info["format"] == "M3U8"
    assert info["extension"] == ".m3u8"
    assert "compatible_with" in info


class TestExportReportContract:
  """Beide Exporter liefern denselben Rueckgabetyp: ExportReport."""

  def test_m3u8_returns_export_report(self, sample_playlist, export_dir):
    """export() gibt ExportReport zurueck, nicht None/dict."""
    path = os.path.join(export_dir, "report.m3u8")
    report = M3U8Exporter().export(sample_playlist, path)

    assert isinstance(report, ExportReport)
    assert report.success is True
    assert report.status == "success"
    assert report.output_path == path
    assert report.tracks_written == len(sample_playlist)
    # M3U8 kennt keine Cues/Beatgrids
    assert report.cues_written == 0
    assert report.beatgrids_written == 0
    assert report.errors == ()

  def test_m3u8_partial_when_track_has_no_path(self, export_dir):
    """Track ohne Dateipfad wird uebersprungen -> status='partial'."""
    tracks = [
      make_track(title="Good", duration=300.0),
      make_track(title="Broken", duration=300.0, filePath=""),
    ]
    path = os.path.join(export_dir, "partial.m3u8")
    report = M3U8Exporter().export(tracks, path)

    assert report.status == "partial"
    assert report.success is False
    assert report.tracks_written == 1
    assert len(report.errors) == 1
    assert "Broken" in report.errors[0]
    # partial ist KEIN Fehler: die Datei existiert und enthaelt den guten Track
    with open(path, "r", encoding="utf-8") as f:
      content = f.read()
    assert content.count("#EXTINF:") == 1

  def test_m3u8_all_tracks_unwritable_raises(self, export_dir):
    """Kein einziger schreibbarer Track -> IOError, keine Datei."""
    tracks = [make_track(title="Broken", duration=300.0, filePath="")]
    path = os.path.join(export_dir, "none.m3u8")
    with pytest.raises(IOError):
      M3U8Exporter().export(tracks, path)
    assert not os.path.exists(path)

  def test_both_exporters_share_report_type(self):
    """RekordboxXMLExporter nutzt denselben ExportReport aus base_exporter."""
    from hpg_core.exporters import rekordbox_xml_exporter

    assert rekordbox_xml_exporter.ExportReport is ExportReport


# ============================================================
# Rekordbox XML Exporter Tests
# ============================================================

class TestRekordboxKeyMapping:
  """Camelot -> Rekordbox Key-Konvertierung."""

  def test_mapping_exists(self):
    """CAMELOT_TO_REKORDBOX Mapping ist vorhanden."""
    try:
      from hpg_core.exporters.rekordbox_xml_exporter import (
        RekordboxXMLExporter,
      )
      assert hasattr(RekordboxXMLExporter, "CAMELOT_TO_REKORDBOX")
    except ImportError:
      pytest.skip("pyrekordbox nicht installiert")

  def test_all_24_camelot_codes_mapped(self):
    """Alle 24 Camelot-Codes sind im Mapping."""
    try:
      from hpg_core.exporters.rekordbox_xml_exporter import (
        RekordboxXMLExporter,
      )
    except ImportError:
      pytest.skip("pyrekordbox nicht installiert")

    mapping = RekordboxXMLExporter.CAMELOT_TO_REKORDBOX
    for num in range(1, 13):
      assert f"{num}A" in mapping, f"{num}A fehlt"
      assert f"{num}B" in mapping, f"{num}B fehlt"

  @pytest.mark.parametrize("camelot,expected", [
    ("8A", "Am"),   # A Minor
    ("8B", "C"),    # C Major
    ("1B", "B"),    # B Major
    ("5A", "Cm"),   # C Minor
    ("12B", "E"),   # E Major
    ("6A", "Gm"),   # G Minor
    ("9B", "G"),    # G Major
    ("11A", "Gbm"), # F# Minor
  ])
  def test_specific_mappings(self, camelot, expected):
    """Spezifische Camelot -> Key Zuordnungen."""
    try:
      from hpg_core.exporters.rekordbox_xml_exporter import (
        RekordboxXMLExporter,
      )
    except ImportError:
      pytest.skip("pyrekordbox nicht installiert")

    mapping = RekordboxXMLExporter.CAMELOT_TO_REKORDBOX
    assert mapping[camelot] == expected, (
      f"Camelot {camelot}: erwartet '{expected}', "
      f"bekommen '{mapping[camelot]}'"
    )

  def test_minor_keys_end_with_m(self):
    """Alle Minor-Keys (A) enden mit 'm'."""
    try:
      from hpg_core.exporters.rekordbox_xml_exporter import (
        RekordboxXMLExporter,
      )
    except ImportError:
      pytest.skip("pyrekordbox nicht installiert")

    mapping = RekordboxXMLExporter.CAMELOT_TO_REKORDBOX
    for num in range(1, 13):
      key = mapping[f"{num}A"]
      assert key.endswith("m"), f"{num}A -> '{key}' endet nicht mit 'm'"

  def test_major_keys_no_m_suffix(self):
    """Major-Keys (B) enden NICHT mit 'm'."""
    try:
      from hpg_core.exporters.rekordbox_xml_exporter import (
        RekordboxXMLExporter,
      )
    except ImportError:
      pytest.skip("pyrekordbox nicht installiert")

    mapping = RekordboxXMLExporter.CAMELOT_TO_REKORDBOX
    for num in range(1, 13):
      key = mapping[f"{num}B"]
      assert not key.endswith("m"), f"{num}B -> '{key}' endet mit 'm'"


class TestRekordboxFormatInfo:
  """Rekordbox Format-Informationen."""

  def test_format_info(self):
    """get_format_info gibt vollstaendiges Dictionary zurueck."""
    try:
      from hpg_core.exporters.rekordbox_xml_exporter import (
        RekordboxXMLExporter,
      )
      exporter = RekordboxXMLExporter()
    except ImportError:
      pytest.skip("pyrekordbox nicht installiert")

    info = exporter.get_format_info()
    assert info["format"] == "Rekordbox XML"
    assert info["extension"] == ".xml"
    assert "compatible_with" in info
    assert "features" in info
    assert "metadata_mapping" in info

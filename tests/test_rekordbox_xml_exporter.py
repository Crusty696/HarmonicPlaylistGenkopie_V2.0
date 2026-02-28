"""
Tests fuer RekordboxXMLExporter.

Mockt PYREKORDBOX_AVAILABLE=True + RekordboxXml-Stub um Instanziierung zu
ermoeglichen. Testet alle Pure-Python-Methoden ohne echtes pyrekordbox.

HINWEIS: RekordboxXml existiert NICHT im Modul-Namespace wenn pyrekordbox
nicht installiert ist → create=True bei allen Patches erforderlich.
"""
import os
import pytest
from unittest.mock import patch
from hpg_core.exporters.rekordbox_xml_exporter import RekordboxXMLExporter
from tests.fixtures.track_factories import make_track


# ─── Fake-Klassen (Stubs fuer pyrekordbox) ────────────────────────────────────

class FakeRbTrack(dict):
  """Simuliert ein pyrekordbox Track-Objekt (dict-like)."""
  pass


class FakePlaylist:
  def __init__(self):
    self.tracks = []

  def add_track(self, tid):
    self.tracks.append(tid)


class FakeRekordboxXml:
  """Minimal-Stub fuer RekordboxXml ohne pyrekordbox."""

  def __init__(self):
    self.tracks = []
    self.playlists = {}
    self.cues = []
    self.saved_path = None

  def add_track(self, uri):
    t = FakeRbTrack()
    t["Location"] = uri
    self.tracks.append(t)
    return t

  def get_playlist(self, group, name):
    key = f"{group}/{name}"
    if key not in self.playlists:
      self.playlists[key] = FakePlaylist()
    return self.playlists[key]

  def add_cue(self, rb_track, name, time, type):
    self.cues.append({"track": rb_track, "name": name, "time": time})

  def save(self, path):
    self.saved_path = path
    with open(path, "w") as f:
      f.write("<NML/>")


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def make_exporter():
  """Erstellt RekordboxXMLExporter mit PYREKORDBOX_AVAILABLE=True."""
  with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
    return RekordboxXMLExporter()


def make_export(playlist, out_path, fake_xml=None):
  """Fuehrt export() mit FakeRekordboxXml durch."""
  _xml = fake_xml or FakeRekordboxXml()
  with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
    with patch(
      "hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml",
      lambda: _xml,
      create=True,
    ):
      exporter = RekordboxXMLExporter()
      exporter.export(playlist, out_path)
  return _xml


# ─── Tests: Initialisierung ───────────────────────────────────────────────────

class TestRekordboxXMLExporterInit:
  """Initialisierung und Import-Fehler."""

  def test_init_ohne_pyrekordbox_raises_importerror(self):
    with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", False):
      with pytest.raises(ImportError, match="pyrekordbox"):
        RekordboxXMLExporter()

  def test_init_mit_pyrekordbox_kein_fehler(self):
    exporter = make_exporter()
    assert isinstance(exporter, RekordboxXMLExporter)


# ─── Tests: URI-Konvertierung ─────────────────────────────────────────────────

class TestRekordboxURIConvertierung:
  """_convert_to_rekordbox_uri Tests."""

  def test_windows_pfad_zu_uri(self):
    exporter = make_exporter()
    uri = exporter._convert_to_rekordbox_uri("C:\\Music\\track.mp3")
    assert uri.startswith("file://localhost")

  def test_uri_enthaelt_dateiname(self):
    exporter = make_exporter()
    uri = exporter._convert_to_rekordbox_uri("C:\\Music\\Sets\\deep_set.wav")
    assert "deep_set.wav" in uri

  def test_forward_slashes_in_uri(self):
    exporter = make_exporter()
    uri = exporter._convert_to_rekordbox_uri("C:\\A\\B\\C\\track.wav")
    assert "/" in uri
    assert "\\" not in uri

  def test_uri_format_korrekt(self):
    exporter = make_exporter()
    uri = exporter._convert_to_rekordbox_uri("C:\\Music\\track.mp3")
    # Format: file://localhost/C:/Music/track.mp3
    assert "file://" in uri
    assert "localhost" in uri


# ─── Tests: Camelot Key Konvertierung ────────────────────────────────────────

class TestCamelotKeyKonvertierung:
  """_convert_camelot_to_rekordbox_key Tests."""

  def test_8a_ergibt_am(self):
    exporter = make_exporter()
    assert exporter._convert_camelot_to_rekordbox_key("8A") == "Am"

  def test_8b_ergibt_c(self):
    exporter = make_exporter()
    assert exporter._convert_camelot_to_rekordbox_key("8B") == "C"

  def test_lowercase_wird_normalisiert(self):
    exporter = make_exporter()
    assert exporter._convert_camelot_to_rekordbox_key("8a") == "Am"
    assert exporter._convert_camelot_to_rekordbox_key("8b") == "C"

  def test_whitespace_wird_ignoriert(self):
    exporter = make_exporter()
    assert exporter._convert_camelot_to_rekordbox_key("  8A  ") == "Am"

  def test_unbekannter_code_ergibt_none(self):
    exporter = make_exporter()
    assert exporter._convert_camelot_to_rekordbox_key("13A") is None
    assert exporter._convert_camelot_to_rekordbox_key("XY") is None

  def test_leerer_string_ergibt_none(self):
    exporter = make_exporter()
    assert exporter._convert_camelot_to_rekordbox_key("") is None
    assert exporter._convert_camelot_to_rekordbox_key(None) is None

  def test_alle_24_codes_gemappt(self):
    exporter = make_exporter()
    for num in range(1, 13):
      assert exporter._convert_camelot_to_rekordbox_key(f"{num}A") is not None
      assert exporter._convert_camelot_to_rekordbox_key(f"{num}B") is not None

  def test_minor_keys_enden_auf_m(self):
    exporter = make_exporter()
    for num in range(1, 13):
      key = exporter._convert_camelot_to_rekordbox_key(f"{num}A")
      assert key.endswith("m"), f"{num}A sollte auf 'm' enden, got '{key}'"

  def test_major_keys_enden_nicht_auf_m(self):
    exporter = make_exporter()
    for num in range(1, 13):
      key = exporter._convert_camelot_to_rekordbox_key(f"{num}B")
      assert not key.endswith("m"), f"{num}B sollte nicht auf 'm' enden, got '{key}'"


# ─── Tests: Format Info ───────────────────────────────────────────────────────

class TestRekordboxFormatInfo:
  """get_format_info Vollstaendigkeit."""

  def test_format_info_vollstaendig(self):
    exporter = make_exporter()
    info = exporter.get_format_info()
    assert info["format"] == "Rekordbox XML"
    assert info["extension"] == ".xml"
    assert "Rekordbox 6.x" in info["compatible_with"]
    assert "features" in info
    assert "metadata_mapping" in info

  def test_metadata_mapping_hat_bpm_und_key(self):
    exporter = make_exporter()
    info = exporter.get_format_info()
    assert "bpm" in info["metadata_mapping"]
    assert "key" in info["metadata_mapping"]

  def test_kompatibel_mit_rekordbox_versionen(self):
    exporter = make_exporter()
    info = exporter.get_format_info()
    compatible = info["compatible_with"]
    assert any("5" in v for v in compatible)
    assert any("6" in v for v in compatible)
    assert any("7" in v for v in compatible)


# ─── Tests: Export End-to-End ─────────────────────────────────────────────────

class TestRekordboxExport:
  """export() End-to-End mit FakeRekordboxXml."""

  def test_export_erstellt_datei(self, tmp_path):
    playlist = [make_track(title="T1", bpm=128.0, camelotCode="8A", duration=300.0)]
    out = str(tmp_path / "test.xml")
    make_export(playlist, out)
    assert os.path.exists(out)

  def test_export_leere_playlist_raises(self, tmp_path):
    out = str(tmp_path / "empty.xml")
    with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
      with patch(
        "hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml",
        FakeRekordboxXml,
        create=True,
      ):
        exporter = RekordboxXMLExporter()
        with pytest.raises(ValueError):
          exporter.export([], out)

  def test_export_korrekte_anzahl_tracks(self, tmp_path):
    playlist = [
      make_track(title=f"T{i}", bpm=128.0, camelotCode="8A", duration=300.0)
      for i in range(3)
    ]
    out = str(tmp_path / "multi.xml")
    fake_xml = FakeRekordboxXml()
    make_export(playlist, out, fake_xml=fake_xml)
    assert len(fake_xml.tracks) == 3

  def test_export_setzt_bpm_metadata(self, tmp_path):
    playlist = [make_track(title="T1", bpm=133.5, camelotCode="8A", duration=300.0)]
    out = str(tmp_path / "bpm.xml")
    fake_xml = FakeRekordboxXml()
    make_export(playlist, out, fake_xml=fake_xml)
    assert fake_xml.tracks[0].get("AverageBpm") == "133.50"

  def test_export_setzt_tonality_key(self, tmp_path):
    playlist = [make_track(title="T1", bpm=128.0, camelotCode="8A", duration=300.0)]
    out = str(tmp_path / "key.xml")
    fake_xml = FakeRekordboxXml()
    make_export(playlist, out, fake_xml=fake_xml)
    assert fake_xml.tracks[0].get("Tonality") == "Am"

  def test_export_setzt_artist_und_title(self, tmp_path):
    playlist = [make_track(title="Night Drive", artist="Djane Cosmic", bpm=128.0)]
    out = str(tmp_path / "meta.xml")
    fake_xml = FakeRekordboxXml()
    make_export(playlist, out, fake_xml=fake_xml)
    assert fake_xml.tracks[0].get("Artist") == "Djane Cosmic"
    assert fake_xml.tracks[0].get("Name") == "Night Drive"

  def test_export_setzt_track_id(self, tmp_path):
    playlist = [
      make_track(title="T1"),
      make_track(title="T2"),
    ]
    out = str(tmp_path / "ids.xml")
    fake_xml = FakeRekordboxXml()
    make_export(playlist, out, fake_xml=fake_xml)
    # TrackIDs beginnen bei 1
    assert fake_xml.tracks[0].get("TrackID") == "1"
    assert fake_xml.tracks[1].get("TrackID") == "2"

  def test_export_ohne_bpm_kein_fehler(self, tmp_path):
    """Track ohne BPM darf nicht crashen."""
    playlist = [make_track(title="T1", bpm=None, camelotCode="8A", duration=300.0)]
    out = str(tmp_path / "nobpm.xml")
    # Kein Exception erwartet
    make_export(playlist, out)

  def test_export_ohne_camelot_kein_fehler(self, tmp_path):
    """Track ohne Camelot-Code darf nicht crashen."""
    playlist = [make_track(title="T1", bpm=128.0, camelotCode=None, duration=300.0)]
    out = str(tmp_path / "nokey.xml")
    # Kein Exception erwartet
    make_export(playlist, out)

  def test_export_erstellt_playlist_eintrag(self, tmp_path):
    """Playlist wird in FakeRekordboxXml angelegt."""
    playlist = [make_track(title="T1", bpm=128.0)]
    out = str(tmp_path / "pl.xml")
    fake_xml = FakeRekordboxXml()
    make_export(playlist, out, fake_xml=fake_xml)
    # Mindestens eine Playlist angelegt
    assert len(fake_xml.playlists) > 0


# ─── Tests: Cue-Punkte ───────────────────────────────────────────────────────

class TestRekordboxCuePunkte:
  """_add_cue_points Tests."""

  def test_cue_points_werden_hinzugefuegt(self, tmp_path):
    playlist = [make_track(
      title="T1", bpm=128.0, camelotCode="8A", duration=300.0,
      mix_in_point=30.0, mix_out_point=270.0,
    )]
    out = str(tmp_path / "cues.xml")
    fake_xml = FakeRekordboxXml()
    make_export(playlist, out, fake_xml=fake_xml)
    cue_names = [c["name"] for c in fake_xml.cues]
    assert "MIX IN" in cue_names
    assert "MIX OUT" in cue_names

  def test_keine_cues_wenn_mix_points_null(self, tmp_path):
    """Keine Cue-Points wenn mix_in/out = 0."""
    playlist = [make_track(
      title="T1", bpm=128.0, camelotCode="8A", duration=300.0,
      mix_in_point=0.0, mix_out_point=0.0,
    )]
    out = str(tmp_path / "nocues.xml")
    fake_xml = FakeRekordboxXml()
    make_export(playlist, out, fake_xml=fake_xml)
    assert len(fake_xml.cues) == 0

  def test_cue_exception_wird_geloggt_kein_crash(self, tmp_path):
    """Fehler in _add_cue_points darf Export nicht verhindern."""

    class BrokenXml(FakeRekordboxXml):
      def add_cue(self, *args, **kwargs):
        raise RuntimeError("Cue error")

    playlist = [make_track(
      title="T1", bpm=128.0, camelotCode="8A", duration=300.0,
      mix_in_point=30.0, mix_out_point=270.0,
    )]
    out = str(tmp_path / "cueerror.xml")
    with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
      with patch(
        "hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml",
        BrokenXml,
        create=True,
      ):
        exporter = RekordboxXMLExporter()
        exporter.export(playlist, out)  # Kein Exception — Fehler wird geloggt

    assert os.path.exists(out)

  def test_mix_in_cue_zeitstempel(self, tmp_path):
    """Mix-In Cue hat korrekten Zeitstempel."""
    playlist = [make_track(mix_in_point=45.0, mix_out_point=250.0)]
    out = str(tmp_path / "cue_time.xml")
    fake_xml = FakeRekordboxXml()
    make_export(playlist, out, fake_xml=fake_xml)
    mix_in_cues = [c for c in fake_xml.cues if c["name"] == "MIX IN"]
    assert len(mix_in_cues) == 1
    assert mix_in_cues[0]["time"] == pytest.approx(45.0)

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
  """Simuliert ein pyrekordbox Track-Objekt (dict-like, mit add_mark)."""

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.owner = None  # FakeRekordboxXml, gesetzt in add_track

  def add_mark(self, Name="", Type="cue", Start=0.0, End=None, Num=-1):
    self.owner.cues.append({"track": self, "name": Name, "time": Start, "type": Type})


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
    t.owner = self
    t["Location"] = uri
    self.tracks.append(t)
    return t

  def get_playlist(self, group, name):
    key = f"{group}/{name}"
    if key not in self.playlists:
      self.playlists[key] = FakePlaylist()
    return self.playlists[key]

  def add_playlist_folder(self, name):
    # Echte API: Ordner explizit anlegen, Playlist darauf erzeugen
    parent = self

    class _FakeFolder:
      def add_playlist(self, playlist_name):
        return parent.get_playlist(name, playlist_name)

    return _FakeFolder()

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


# ─── Tests: Location-Kodierung (End-to-End) ───────────────────────────────────

class TestRekordboxLocationEncoding:
  """CRITICAL-Regression: pyrekordbox kodiert die file://localhost-URI selbst.
  HPG darf nur den ROHEN Pfad uebergeben, sonst doppelte Kodierung → Rekordbox
  findet nach dem Import keine Datei."""

  def _exported_location(self, tmp_path, file_path):
    import re
    from hpg_core.models import Track
    exporter = make_exporter()
    track = Track(filePath=file_path, fileName="t.wav", title="T", artist="A")
    out = str(tmp_path / "set.xml")
    exporter.export([track], out)
    with open(out, encoding="utf-8") as f:
      xml_text = f.read()
    m = re.search(r'Location="([^"]*)"', xml_text)
    assert m, "Keine Location im Export"
    return m.group(1)

  def test_location_nicht_doppelt_kodiert(self, tmp_path):
    loc = self._exported_location(tmp_path, "C:\\Music\\Track A.wav")
    # genau EIN file://localhost-Prefix, kein verschachteltes zweites
    assert loc.count("file://") == 1, f"Doppelt kodierte Location: {loc}"
    assert "localhost/file:" not in loc, f"Doppelt kodierte Location: {loc}"
    assert loc.startswith("file://localhost/"), loc

  def test_location_sonderzeichen_kodiert(self, tmp_path):
    loc = self._exported_location(tmp_path, "C:\\Übergäng & Söngs\\Track's #1.wav")
    assert loc.count("file://") == 1, f"Doppelt kodierte Location: {loc}"
    assert " " not in loc and "&" not in loc, f"Unkodierte Sonderzeichen: {loc}"


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
    # Distinkte filePaths: Rekordbox lehnt doppelte Locations ab (Dedup im Export)
    playlist = [
      make_track(title=f"T{i}", filePath=f"/test/track_{i}.mp3",
                 bpm=128.0, camelotCode="8A", duration=300.0)
      for i in range(3)
    ]
    out = str(tmp_path / "multi.xml")
    fake_xml = FakeRekordboxXml()
    make_export(playlist, out, fake_xml=fake_xml)
    assert len(fake_xml.tracks) == 3

  def test_export_dedupliziert_gleiche_location(self, tmp_path):
    """Audit-Fix 2026-07-21: doppelte Location darf den Export nicht killen —
    Duplikat wird uebersprungen, restliche Tracks bleiben erhalten."""
    playlist = [
      make_track(title="A", filePath="/test/dup.mp3", bpm=128.0, camelotCode="8A", duration=300.0),
      make_track(title="B", filePath="/test/dup.mp3", bpm=128.0, camelotCode="8A", duration=300.0),
      make_track(title="C", filePath="/test/unique.mp3", bpm=128.0, camelotCode="8A", duration=300.0),
    ]
    out = str(tmp_path / "dup.xml")
    fake_xml = FakeRekordboxXml()
    make_export(playlist, out, fake_xml=fake_xml)
    assert len(fake_xml.tracks) == 2

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

  def test_export_prefers_detected_genre(self, tmp_path):
    playlist = [
      make_track(
        title="T1", genre="Unknown", detected_genre="Techno", bpm=128.0
      )
    ]
    out = str(tmp_path / "genre.xml")
    fake_xml = FakeRekordboxXml()

    make_export(playlist, out, fake_xml=fake_xml)

    assert fake_xml.tracks[0].get("Genre") == "Techno"

  def test_export_skips_track_without_path(self, tmp_path):
    playlist = [
      make_track(title="Pathless", filePath=""),
      make_track(title="Valid", filePath="/test/valid.mp3"),
    ]
    out = str(tmp_path / "pathless.xml")
    fake_xml = FakeRekordboxXml()

    make_export(playlist, out, fake_xml=fake_xml)

    assert len(fake_xml.tracks) == 1
    assert fake_xml.tracks[0]["Location"] == os.path.abspath("/test/valid.mp3")

  def test_export_setzt_track_id(self, tmp_path):
    playlist = [
      make_track(title="T1", filePath="/test/track_1.mp3"),
      make_track(title="T2", filePath="/test/track_2.mp3"),
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
      mix_in_point=30.0, mix_out_point=270.0, outro_covered=True,
    )]
    out = str(tmp_path / "cues.xml")
    fake_xml = FakeRekordboxXml()
    make_export(playlist, out, fake_xml=fake_xml)
    cue_names = [c["name"] for c in fake_xml.cues]
    assert "MIX IN" in cue_names
    assert "MIX OUT" in cue_names

  def test_keine_cues_wenn_mix_points_nicht_gesetzt(self, tmp_path):
    """Keine Cue-Points wenn mix_in/out den Sentinel tragen."""
    playlist = [make_track(
      title="T1", bpm=128.0, camelotCode="8A", duration=300.0,
      mix_in_point=-1.0, mix_out_point=-1.0,
    )]
    out = str(tmp_path / "nocues.xml")
    fake_xml = FakeRekordboxXml()
    make_export(playlist, out, fake_xml=fake_xml)
    assert len(fake_xml.cues) == 0

  def test_cue_exception_wird_geloggt_kein_crash(self, tmp_path):
    """Fehler in _add_cue_points darf Export nicht verhindern."""

    class BrokenTrack(FakeRbTrack):
      def add_mark(self, *args, **kwargs):
        raise RuntimeError("Cue error")

    class BrokenXml(FakeRekordboxXml):
      def add_track(self, uri):
        t = BrokenTrack()
        t.owner = self
        t["Location"] = uri
        self.tracks.append(t)
        return t

    playlist = [make_track(
      title="T1", bpm=128.0, camelotCode="8A", duration=300.0,
      mix_in_point=30.0, mix_out_point=270.0, outro_covered=True,
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
    playlist = [make_track(
      duration=300.0, mix_in_point=45.0, mix_out_point=250.0,
      outro_covered=True,
    )]
    out = str(tmp_path / "cue_time.xml")
    fake_xml = FakeRekordboxXml()
    make_export(playlist, out, fake_xml=fake_xml)
    mix_in_cues = [c for c in fake_xml.cues if c["name"] == "MIX IN"]
    # M9-Fix: Mix-In wird doppelt geschrieben — Hot Cue A (Num=0) + Memory Cue (Num=-1)
    assert len(mix_in_cues) == 2
    for cue in mix_in_cues:
      assert cue["time"] == pytest.approx(45.0)

  def test_partial_report_for_track_without_tail_coverage(self, tmp_path):
    playlist = [make_track(
      duration=300.0, mix_in_point=30.0, mix_out_point=270.0,
      outro_covered=False,
    )]
    fake_xml = FakeRekordboxXml()
    out = str(tmp_path / "partial.xml")
    with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
      with patch(
        "hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml",
        lambda: fake_xml,
        create=True,
      ):
        report = RekordboxXMLExporter().export(playlist, out)

    assert report.status == "partial"
    assert report.cues_written == 0
    assert any("Cues ausgelassen" in error for error in report.errors)

  def test_invalid_xml_does_not_replace_existing_output(self, tmp_path):
    class InvalidXml(FakeRekordboxXml):
      def save(self, path):
        with open(path, "w") as handle:
          handle.write("<broken")

    out = tmp_path / "existing.xml"
    out.write_text("<existing/>", encoding="utf-8")
    with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
      with patch(
        "hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml",
        InvalidXml,
        create=True,
      ):
        with pytest.raises(IOError):
          RekordboxXMLExporter().export([make_track()], str(out))

    assert out.read_text(encoding="utf-8") == "<existing/>"

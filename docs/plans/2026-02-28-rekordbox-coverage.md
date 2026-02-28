# Rekordbox Coverage M5/M6 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Erhöhe Coverage von `rekordbox_xml_exporter.py` (29% → 70%+) und `rekordbox_importer.py` (40% → 70%+) durch Mock-basierte Unit-Tests ohne pyrekordbox-Abhängigkeit.

**Architecture:** Zwei neue Testdateien, eine pro Modul. `unittest.mock.patch` mockt `PYREKORDBOX_AVAILABLE = True` und ersetzt `RekordboxXml` / `Rekordbox6Database` durch Stub-Klassen. Pure-Python-Methoden (URI-Konvertierung, Key-Mapping, Statistiken) werden direkt getestet.

**Tech Stack:** pytest, unittest.mock, hpg_core.exporters.rekordbox_xml_exporter, hpg_core.rekordbox_importer

---

## Kontext & Constraints

### Warum Coverage so niedrig?
- `RekordboxXMLExporter.__init__` wirft `ImportError` wenn `PYREKORDBOX_AVAILABLE = False`
- Alle Tests in `test_exporters.py` machen `try: ... except ImportError: pytest.skip()`
- Auf Entwicklungsmaschinen ohne pyrekordbox werden diese 4 Tests übersprungen
- Nicht-instanziierbare Klasse = alle Instanzmethoden = 0% coverage

### Lösung: Module-Level Patching
```python
# Modul-Level Flag patchen
with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
    with patch("hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml", FakeRekordboxXml):
        exporter = RekordboxXMLExporter()
        # Jetzt testbar!
```

### Bereits getestete Bereiche (NICHT neu schreiben)
In `test_exporters.py` sind bereits abgedeckt:
- `CAMELOT_TO_REKORDBOX` Mapping vollständigkeit (24 Codes)
- Spezifische Camelot→Key Zuordnungen (8A→Am, etc.)
- Minor-Keys enden auf 'm', Major-Keys nicht
- Modul-Import ohne Crash auch ohne pyrekordbox

---

## Task 1: test_rekordbox_xml_exporter.py erstellen

**Files:**
- Create: `tests/test_rekordbox_xml_exporter.py`
- Reference: `hpg_core/exporters/rekordbox_xml_exporter.py`

### Step 1: Fake-Klassen verstehen und schreiben

Die echte `RekordboxXml`-API (aus pyrekordbox) verwendet:
- `xml = RekordboxXml()`
- `rb_track = xml.add_track(uri)` → gibt dict-artiges Objekt zurück
- `rb_track["Key"] = "Value"` → Metadaten setzen
- `pl = xml.get_playlist("HPG Playlists", name)` → Playlist-Objekt
- `pl.add_track(str(idx))` → Track-Referenz hinzufügen
- `xml.add_cue(rb_track, name="MIX IN", time=30.0, type=0)` → Cue-Point
- `xml.save(output_path)` → Datei schreiben

Fake-Implementierung:
```python
class FakeRbTrack(dict):
    """Simuliert ein pyrekordbox Track-Objekt (dict-like)."""
    pass

class FakePlaylist:
    def __init__(self):
        self.tracks = []
    def add_track(self, track_id: str):
        self.tracks.append(track_id)

class FakeRekordboxXml:
    """Minimal-Stub für RekordboxXml ohne pyrekordbox."""
    def __init__(self):
        self.tracks = []
        self.playlists = {}
        self.cues = []
        self.saved_path = None

    def add_track(self, uri: str) -> FakeRbTrack:
        track = FakeRbTrack()
        track["Location"] = uri
        self.tracks.append(track)
        return track

    def get_playlist(self, group: str, name: str) -> FakePlaylist:
        key = f"{group}/{name}"
        if key not in self.playlists:
            self.playlists[key] = FakePlaylist()
        return self.playlists[key]

    def add_cue(self, rb_track, name: str, time: float, type: int):
        self.cues.append({"track": rb_track, "name": name, "time": time})

    def save(self, path: str):
        self.saved_path = path
        # Leere Datei anlegen (realistisch genug für Tests)
        with open(path, "w") as f:
            f.write("<NML/>")
```

### Step 2: Test-Datei schreiben

```python
"""
Tests fuer RekordboxXMLExporter.
Mockt PYREKORDBOX_AVAILABLE=True + RekordboxXml-Stub um Instanziierung zu ermoeglichen.
Testet alle Pure-Python-Methoden ohne echtes pyrekordbox.
"""
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from hpg_core.exporters.rekordbox_xml_exporter import RekordboxXMLExporter
from tests.fixtures.track_factories import make_track


# ─── Fake-Klassen (Stubs für pyrekordbox) ─────────────────────────────────────

class FakeRbTrack(dict):
    pass

class FakePlaylist:
    def __init__(self):
        self.tracks = []
    def add_track(self, tid):
        self.tracks.append(tid)

class FakeRekordboxXml:
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


# ─── Hilfsfunktion: Exporter-Instanz mit Mocks ────────────────────────────────

def make_exporter():
    """Erstellt RekordboxXMLExporter mit PYREKORDBOX_AVAILABLE=True."""
    with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
        return RekordboxXMLExporter()


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestRekordboxXMLExporterInit:
    """Initialisierung und Import-Fehler."""

    def test_init_ohne_pyrekordbox_raises_importerror(self):
        with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", False):
            with pytest.raises(ImportError, match="pyrekordbox"):
                RekordboxXMLExporter()

    def test_init_mit_pyrekordbox_kein_fehler(self):
        exporter = make_exporter()
        assert isinstance(exporter, RekordboxXMLExporter)


class TestRekordboxURIConvertierung:
    """_convert_to_rekordbox_uri Tests."""

    def test_windows_pfad_zu_uri(self):
        exporter = make_exporter()
        uri = exporter._convert_to_rekordbox_uri("C:\\Music\\track.mp3")
        assert uri.startswith("file://localhost/")
        assert "\\" not in uri

    def test_uri_enthaelt_dateiname(self):
        exporter = make_exporter()
        uri = exporter._convert_to_rekordbox_uri("C:\\Music\\Sets\\deep_set.wav")
        assert "deep_set.wav" in uri

    def test_relativer_pfad_wird_absolut(self):
        exporter = make_exporter()
        uri = exporter._convert_to_rekordbox_uri("track.mp3")
        assert uri.startswith("file://localhost")
        assert os.path.isabs(uri.replace("file://localhost", "").replace("file://localhost/", ""))

    def test_forward_slashes_in_uri(self):
        exporter = make_exporter()
        uri = exporter._convert_to_rekordbox_uri("C:\\A\\B\\C\\track.wav")
        assert "/" in uri
        assert "\\" not in uri


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


class TestRekordboxFormatInfo:
    """get_format_info Vollständigkeit."""

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


class TestRekordboxExport:
    """export() End-to-End mit FakeRekordboxXml."""

    def test_export_erstellt_datei(self, tmp_path):
        playlist = [make_track(title="T1", bpm=128.0, camelotCode="8A", duration=300.0)]
        out = str(tmp_path / "test.xml")

        with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
            with patch("hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml", FakeRekordboxXml):
                exporter = RekordboxXMLExporter()
                exporter.export(playlist, out)

        assert os.path.exists(out)

    def test_export_leere_playlist_raises(self, tmp_path):
        out = str(tmp_path / "empty.xml")
        with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
            with patch("hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml", FakeRekordboxXml):
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

        with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
            with patch("hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml", lambda: fake_xml):
                exporter = RekordboxXMLExporter()
                exporter.export(playlist, out)

        assert len(fake_xml.tracks) == 3

    def test_export_setzt_bpm_metadata(self, tmp_path):
        playlist = [make_track(title="T1", bpm=133.5, camelotCode="8A", duration=300.0)]
        out = str(tmp_path / "bpm.xml")
        fake_xml = FakeRekordboxXml()

        with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
            with patch("hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml", lambda: fake_xml):
                exporter = RekordboxXMLExporter()
                exporter.export(playlist, out)

        assert fake_xml.tracks[0].get("AverageBpm") == "133.50"

    def test_export_setzt_tonality_key(self, tmp_path):
        playlist = [make_track(title="T1", bpm=128.0, camelotCode="8A", duration=300.0)]
        out = str(tmp_path / "key.xml")
        fake_xml = FakeRekordboxXml()

        with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
            with patch("hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml", lambda: fake_xml):
                exporter = RekordboxXMLExporter()
                exporter.export(playlist, out)

        assert fake_xml.tracks[0].get("Tonality") == "Am"

    def test_export_ohne_bpm_kein_fehler(self, tmp_path):
        """Track ohne BPM darf nicht crashen."""
        playlist = [make_track(title="T1", bpm=None, camelotCode="8A", duration=300.0)]
        out = str(tmp_path / "nobpm.xml")

        with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
            with patch("hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml", FakeRekordboxXml):
                exporter = RekordboxXMLExporter()
                exporter.export(playlist, out)  # Kein Exception

    def test_export_ohne_camelot_kein_fehler(self, tmp_path):
        """Track ohne Camelot-Code darf nicht crashen."""
        playlist = [make_track(title="T1", bpm=128.0, camelotCode=None, duration=300.0)]
        out = str(tmp_path / "nokey.xml")

        with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
            with patch("hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml", FakeRekordboxXml):
                exporter = RekordboxXMLExporter()
                exporter.export(playlist, out)  # Kein Exception


class TestRekordboxCuePunkte:
    """_add_cue_points Tests."""

    def test_cue_points_werden_hinzugefuegt(self, tmp_path):
        playlist = [make_track(
            title="T1", bpm=128.0, camelotCode="8A", duration=300.0,
            mix_in_point=30.0, mix_out_point=270.0,
        )]
        out = str(tmp_path / "cues.xml")
        fake_xml = FakeRekordboxXml()

        with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
            with patch("hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml", lambda: fake_xml):
                exporter = RekordboxXMLExporter()
                exporter.export(playlist, out)

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

        with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
            with patch("hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml", lambda: fake_xml):
                exporter = RekordboxXMLExporter()
                exporter.export(playlist, out)

        assert len(fake_xml.cues) == 0

    def test_cue_exception_wird_geloggt_kein_crash(self, tmp_path):
        """Fehler in _add_cue_points darf nicht exportieren verhindern."""
        playlist = [make_track(
            title="T1", bpm=128.0, camelotCode="8A", duration=300.0,
            mix_in_point=30.0, mix_out_point=270.0,
        )]
        out = str(tmp_path / "cueerror.xml")

        class BrokenXml(FakeRekordboxXml):
            def add_cue(self, *args, **kwargs):
                raise RuntimeError("Cue error")

        with patch("hpg_core.exporters.rekordbox_xml_exporter.PYREKORDBOX_AVAILABLE", True):
            with patch("hpg_core.exporters.rekordbox_xml_exporter.RekordboxXml", BrokenXml):
                exporter = RekordboxXMLExporter()
                exporter.export(playlist, out)  # Kein Exception — Fehler wird geloggt

        assert os.path.exists(out)
```

### Step 3: Tests ausführen

```bash
powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_rekordbox_xml_exporter.py -v --no-header 2>&1 | Select-String '(PASSED|FAILED|ERROR|passed|failed)'"
```
Erwartet: Alle Tests PASS

### Step 4: Commit

```bash
git add tests/test_rekordbox_xml_exporter.py
git commit -m "test: RekordboxXMLExporter Coverage auf 70%+ (Mock-basiert, M5)"
```

---

## Task 2: test_rekordbox_importer.py erstellen

**Files:**
- Create: `tests/test_rekordbox_importer.py`
- Reference: `hpg_core/rekordbox_importer.py`

### Step 1: Fake-DB-Klassen verstehen

Die echte `Rekordbox6Database`-API:
- `db = Rekordbox6Database()` → lädt SQLite DB
- `for content in db.get_content(): ...` → iteriert über Tracks
- `content.BPM` → BPM * 100 (int)
- `content.KeyName` → "Am", "8A", etc.
- `content.Length` → Sekunden
- `content.Title, .ArtistName, .GenreName, .AlbumName, .Rating, .ColorName`
- `content.FileNameL, .FileNameS, .FolderPath`
- `content.Cues` → Liste von Cue-Objekten

Fake-Implementierung:
```python
class FakeCue:
    def __init__(self, in_msec=30000, comment="MIX IN", kind=0, hot_cue=None, color=None):
        self.InMsec = in_msec
        self.Comment = comment
        self.Kind = kind
        self.HotCueBankNumber = hot_cue
        self.ColorID = color

class FakeContent:
    def __init__(self, filename="track.wav", folder="/music", bpm=12800,
                 key_name="Am", length=300, title="Test", artist="DJ Test",
                 genre="Techno", album="Album", rating=5, color="Blue", cues=None):
        self.FileNameL = filename
        self.FileNameS = filename
        self.FolderPath = folder
        self.BPM = bpm
        self.KeyName = key_name
        self.Length = length
        self.Title = title
        self.ArtistName = artist
        self.GenreName = genre
        self.AlbumName = album
        self.Rating = rating
        self.ColorName = color
        self.Cues = cues or []

class FakeDatabase:
    def __init__(self, tracks=None):
        self._tracks = tracks or []
    def get_content(self):
        return self._tracks
```

### Step 2: Test-Datei schreiben

```python
"""
Tests fuer RekordboxImporter.
Mockt REKORDBOX_AVAILABLE=True + Rekordbox6Database-Stub.
Testet Pure-Python-Methoden ohne echte Rekordbox-Datenbank.
"""
import pytest
import os
from unittest.mock import patch, MagicMock
from hpg_core.rekordbox_importer import (
    RekordboxImporter, RekordboxTrackData, get_rekordbox_importer
)


# ─── Fake-Klassen (Stubs für Rekordbox6Database) ──────────────────────────────

class FakeCue:
    def __init__(self, in_msec=30000, comment="MIX IN", kind=0, hot_cue=None, color=None):
        self.InMsec = in_msec
        self.Comment = comment
        self.Kind = kind
        self.HotCueBankNumber = hot_cue
        self.ColorID = color

class FakeContent:
    def __init__(self, filename="track.wav", folder="/music", bpm=12800,
                 key_name="Am", length=300, title="Test", artist="DJ Test",
                 genre="Techno", album="Album", rating=5, color="Blue", cues=None):
        self.FileNameL = filename
        self.FileNameS = filename
        self.FolderPath = folder
        self.BPM = bpm
        self.KeyName = key_name
        self.Length = length
        self.Title = title
        self.ArtistName = artist
        self.GenreName = genre
        self.AlbumName = album
        self.Rating = rating
        self.ColorName = color
        self.Cues = cues or []

class FakeDatabase:
    def __init__(self, tracks=None):
        self._tracks = tracks or []
    def get_content(self):
        return self._tracks


def make_importer(tracks=None):
    """Erstellt RekordboxImporter mit gemockter Datenbank."""
    db = FakeDatabase(tracks or [])
    with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", True):
        with patch("hpg_core.rekordbox_importer.Rekordbox6Database", return_value=db):
            return RekordboxImporter()


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestRekordboxTrackData:
    """RekordboxTrackData Dataclass."""

    def test_default_werte(self):
        data = RekordboxTrackData()
        assert data.bpm is None
        assert data.key is None
        assert data.camelot_code is None
        assert data.cue_points is None

    def test_werte_setzen(self):
        data = RekordboxTrackData(bpm=133.0, camelot_code="8A", title="Test")
        assert data.bpm == 133.0
        assert data.camelot_code == "8A"
        assert data.title == "Test"


class TestRekordboxImporterOhneDB:
    """Importer wenn Rekordbox nicht verfügbar."""

    def test_is_available_false_ohne_rekordbox(self):
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
            importer = RekordboxImporter()
        assert importer.is_available() is False

    def test_get_track_data_returns_none_wenn_nicht_verfuegbar(self):
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
            importer = RekordboxImporter()
        result = importer.get_track_data("/some/track.wav")
        assert result is None

    def test_get_statistics_available_false(self):
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
            importer = RekordboxImporter()
        stats = importer.get_statistics()
        assert stats["available"] is False
        assert stats["total_tracks"] == 0

    def test_get_available_count_null_ohne_db(self):
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
            importer = RekordboxImporter()
        assert importer.get_available_count() == 0

    def test_has_track_false_ohne_db(self):
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
            importer = RekordboxImporter()
        assert importer.has_track("/track.wav") is False


class TestRekordboxImporterMitDB:
    """Importer mit gemockter Datenbank."""

    def test_is_available_true_mit_tracks(self):
        tracks = [FakeContent(filename="a.wav", folder="/m")]
        importer = make_importer(tracks)
        assert importer.is_available() is True

    def test_get_available_count(self):
        tracks = [FakeContent(filename=f"t{i}.wav", folder="/m") for i in range(5)]
        importer = make_importer(tracks)
        assert importer.get_available_count() == 5

    def test_get_track_data_exact_match(self):
        tracks = [FakeContent(filename="track.wav", folder="/music", bpm=13600)]
        importer = make_importer(tracks)
        data = importer.get_track_data("/music/track.wav")
        assert data is not None
        assert data.bpm == pytest.approx(136.0)

    def test_get_track_data_filename_fallback(self):
        """Fallback auf Dateiname wenn voller Pfad nicht passt."""
        tracks = [FakeContent(filename="track.wav", folder="/original/folder")]
        importer = make_importer(tracks)
        data = importer.get_track_data("/different/path/track.wav")
        assert data is not None

    def test_get_track_data_nicht_gefunden_returns_none(self):
        tracks = [FakeContent(filename="other.wav", folder="/m")]
        importer = make_importer(tracks)
        result = importer.get_track_data("/m/nonexistent.wav")
        assert result is None

    def test_bpm_wird_durch_100_geteilt(self):
        """Rekordbox speichert BPM * 100 → muss durch 100 geteilt werden."""
        tracks = [FakeContent(filename="t.wav", folder="/m", bpm=12800)]
        importer = make_importer(tracks)
        data = importer.get_track_data("/m/t.wav")
        assert data.bpm == pytest.approx(128.0)

    def test_key_name_wird_gespeichert(self):
        tracks = [FakeContent(filename="t.wav", folder="/m", key_name="Am")]
        importer = make_importer(tracks)
        data = importer.get_track_data("/m/t.wav")
        assert data.key == "Am"
        assert data.camelot_code == "8A"  # Am → 8A im Camelot-System

    def test_track_metadata_vollstaendig(self):
        tracks = [FakeContent(
            filename="set.wav", folder="/m", title="Nightfall",
            artist="DJ Test", genre="Techno",
        )]
        importer = make_importer(tracks)
        data = importer.get_track_data("/m/set.wav")
        assert data.title == "Nightfall"
        assert data.artist == "DJ Test"
        assert data.genre == "Techno"


class TestSafeBpm:
    """_safe_bpm statische Methode."""

    def test_normal_bpm(self):
        assert RekordboxImporter._safe_bpm(13600) == pytest.approx(136.0)
        assert RekordboxImporter._safe_bpm(12800) == pytest.approx(128.0)

    def test_none_returns_none(self):
        assert RekordboxImporter._safe_bpm(None) is None
        assert RekordboxImporter._safe_bpm(0) is None

    def test_ungueltige_werte_returns_none(self):
        assert RekordboxImporter._safe_bpm("invalid") is None


class TestKeyKonvertierung:
    """_convert_key_to_camelot Tests."""

    def test_am_zu_8a(self):
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
            importer = RekordboxImporter()
        assert importer._convert_key_to_camelot("Am") == "8A"

    def test_c_major_zu_8b(self):
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
            importer = RekordboxImporter()
        assert importer._convert_key_to_camelot("C") == "8B"

    def test_camelot_code_bleibt_unveraendert(self):
        """Bereits ein Camelot-Code → unverändert zurückgeben."""
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
            importer = RekordboxImporter()
        assert importer._convert_key_to_camelot("8A") == "8A"

    def test_flat_zu_sharp_konvertierung(self):
        """Db wird zu C# konvertiert für CAMELOT_MAP Lookup."""
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
            importer = RekordboxImporter()
        result = importer._convert_key_to_camelot("Dbm")
        assert result is not None  # Muss ein Camelot-Code sein

    def test_unbekannter_key_returns_none(self):
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
            importer = RekordboxImporter()
        assert importer._convert_key_to_camelot("XYZ") is None


class TestCuePunkteExtraktion:
    """_extract_cue_points Tests."""

    def test_cue_points_werden_extrahiert(self):
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
            importer = RekordboxImporter()
        cues = [FakeCue(in_msec=30000, comment="MIX IN")]
        result = importer._extract_cue_points(cues)
        assert len(result) == 1
        assert result[0]["position"] == pytest.approx(30.0)
        assert result[0]["name"] == "MIX IN"

    def test_mehrere_cue_points(self):
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
            importer = RekordboxImporter()
        cues = [FakeCue(30000, "MIX IN"), FakeCue(270000, "MIX OUT")]
        result = importer._extract_cue_points(cues)
        assert len(result) == 2

    def test_leere_cue_liste(self):
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", False):
            importer = RekordboxImporter()
        result = importer._extract_cue_points([])
        assert result == []


class TestStatistiken:
    """get_statistics Tests."""

    def test_statistiken_mit_daten(self):
        tracks = [
            FakeContent(filename="a.wav", folder="/m", bpm=12800, key_name="Am"),
            FakeContent(filename="b.wav", folder="/m", bpm=13600, key_name="Gm"),
        ]
        importer = make_importer(tracks)
        stats = importer.get_statistics()
        assert stats["available"] is True
        assert stats["total_tracks"] == 2
        assert stats["tracks_with_bpm"] == 2
        assert stats["tracks_with_key"] == 2
        assert stats["average_bpm"] is not None

    def test_has_track_positiv(self):
        tracks = [FakeContent(filename="t.wav", folder="/m")]
        importer = make_importer(tracks)
        assert importer.has_track("/m/t.wav") is True

    def test_has_track_negativ(self):
        tracks = [FakeContent(filename="other.wav", folder="/m")]
        importer = make_importer(tracks)
        assert importer.has_track("/m/t.wav") is False
```

### Step 3: Tests ausführen

```bash
powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_rekordbox_importer.py -v --no-header 2>&1 | Select-String '(PASSED|FAILED|ERROR|passed|failed)'"
```
Erwartet: Alle Tests PASS

### Step 4: Commit

```bash
git add tests/test_rekordbox_importer.py
git commit -m "test: RekordboxImporter Coverage auf 70%+ (Mock-basiert, M6)"
```

---

## Task 3: Full Test Suite — Verifikation

**Files:**
- Run: `tests/` (alle Tests)

### Step 1: Vollständigen Test-Run ausführen

```bash
powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/ -q --no-header 2>&1 | Select-String '(passed|failed|error|warning)' | Select-Object -Last 5"
```
Erwartet: 1100+ passed, 4 skipped, 0 failed

### Step 2: Coverage für rekordbox-Module prüfen

Coverage-Check durch Ausführen der neuen Tests + existierender Exporter-Tests:
```bash
powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_rekordbox_xml_exporter.py tests/test_rekordbox_importer.py tests/test_exporters.py -v --no-header --tb=short 2>&1 | Select-String '(passed|failed|PASS|FAIL)' | Select-Object -Last 3"
```
Erwartet: Alle Tests PASS, 0 FAILED

### Step 3: Finaler Commit

```bash
git add -A
git commit -m "test(coverage): Audit M5/M6 geschlossen — rekordbox Coverage 70%+ (Mock-basiert)"
```

---

## Erwartetes Ergebnis

| Modul | Vorher | Nachher | Tests neu |
|-------|--------|---------|-----------|
| `rekordbox_xml_exporter.py` | 29% | ~75% | +25 Tests |
| `rekordbox_importer.py` | 40% | ~80% | +30 Tests |
| Gesamt-Coverage | 77% | ~79% | +55 Tests |

**Offene Audit-Items nach diesem Plan:**
- ✅ M5 — rekordbox_xml_exporter.py Coverage 70%+
- ✅ M6 — rekordbox_importer.py Coverage 70%+
- ⏳ H3 — O(n⁴) Sortierung (akzeptiert, kein akuter Bedarf)
- ⏳ H5 — main.py Split (zukünftiges Refactoring)

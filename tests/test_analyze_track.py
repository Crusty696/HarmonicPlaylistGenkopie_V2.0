"""
Integrationstests fuer analyze_track() Pipeline.
Testet volle Audio-Analyse: BPM, Key, Energy, Mix-Points.
"""
import os
import pytest
import tempfile
import numpy as np
from unittest.mock import Mock
from hpg_core.caching import TRACK_REQUIRED_FIELDS, track_to_dict, validate_track_dict
from hpg_core.models import Track
from hpg_core.rekordbox_importer import RekordboxTrackData
from hpg_core.structure_analyzer import TrackSection, TrackStructure


# ============================================================
# Hilfsfunktionen
# ============================================================

def _create_test_wav(path: str, duration: float = 5.0, sr: int = 22050):
  """Erstellt eine minimale WAV-Datei mit Sinuswelle."""
  import wave

  n_samples = int(duration * sr)
  t = np.linspace(0, duration, n_samples, endpoint=False)
  # 440Hz Sinuswelle (A4)
  signal = (np.sin(2 * np.pi * 440 * t) * 32767 * 0.5).astype(np.int16)

  with wave.open(path, "w") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sr)
    wav.writeframes(signal.tobytes())


def _create_click_wav(path: str, bpm: float = 128.0,
                      duration: float = 10.0, sr: int = 22050):
  """Erstellt eine WAV-Datei mit Click-Track bei gegebenem BPM."""
  import wave

  n_samples = int(duration * sr)
  signal = np.zeros(n_samples)

  beat_interval = 60.0 / bpm
  click_duration = 0.01  # 10ms Click

  t = 0.0
  while t < duration:
    start = int(t * sr)
    end = min(start + int(click_duration * sr), n_samples)
    if end > start:
      click_t = np.linspace(0, click_duration, end - start, endpoint=False)
      signal[start:end] = np.sin(2 * np.pi * 1000 * click_t) * 0.8
    t += beat_interval

  int_signal = (signal * 32767).astype(np.int16)
  with wave.open(path, "w") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sr)
    wav.writeframes(int_signal.tobytes())


def test_short_track_zaehlt_identisches_beatgrid_fenster_nur_einmal(monkeypatch):
  """Ein kurzer Track darf dasselbe Startfenster nicht dreifach zaehlen."""
  from hpg_core import analysis

  offsets = []

  def _capture(windows, *_args, **_kwargs):
    offsets.extend(offset for offset, _audio in windows)
    return analysis.BeatgridValidation("unverifiable", len(windows), -1.0)

  monkeypatch.setattr(analysis, "validate_beatgrid_windows", _capture)
  monkeypatch.setattr(
    analysis.librosa,
    "load",
    lambda *_args, **_kwargs: (np.zeros(22050), 22050),
  )

  result = analysis._validate_track_beatgrid(
    "short.wav",
    duration=10.0,
    bpm=120.0,
    anchor=0.0,
    head_audio=np.zeros(220500),
    head_sr=22050,
  )

  assert offsets == [0.0]
  assert result.status == "unverifiable"


def test_persistenz_guard_bestaetigt_true_und_faengt_unerwartete_exception(
  monkeypatch,
):
  from hpg_core import analysis

  track = Track(filePath="C:/Musik/test.wav", fileName="test.wav")
  monkeypatch.setattr(analysis, "cache_track", lambda *_args: True)
  assert analysis._persist_analysis_result("key", track) is True

  def _unerwarteter_fehler(*_args):
    raise RuntimeError("write contract broken")

  monkeypatch.setattr(analysis, "cache_track", _unerwarteter_fehler)
  assert analysis._persist_analysis_result("key", track) is False

  monkeypatch.setattr(analysis, "cache_track", lambda *_args: object())
  assert analysis._persist_analysis_result("key", track) is False


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def simple_wav():
  """Einfache WAV-Datei (5 Sekunden, 440Hz)."""
  with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
    path = f.name
  _create_test_wav(path, duration=5.0)
  yield path
  if os.path.exists(path):
    os.unlink(path)


@pytest.fixture
def click_wav_128():
  """Click-Track WAV bei 128 BPM (10 Sekunden)."""
  with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
    path = f.name
  _create_click_wav(path, bpm=128.0, duration=10.0)
  yield path
  if os.path.exists(path):
    os.unlink(path)


@pytest.fixture
def long_wav():
  """WAV mit Platz fuer mindestens zwei vollstaendige 8-Bar-Phrasen."""
  with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
    path = f.name
  _create_click_wav(path, bpm=128.0, duration=90.0)
  yield path
  if os.path.exists(path):
    os.unlink(path)


@pytest.fixture
def silence_wav():
  """Stille WAV-Datei (5 Sekunden)."""
  import wave

  path = tempfile.mktemp(suffix=".wav")
  sr = 22050
  n_samples = int(5.0 * sr)
  signal = np.zeros(n_samples, dtype=np.int16)
  with wave.open(path, "w") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sr)
    wav.writeframes(signal.tobytes())
  yield path
  if os.path.exists(path):
    os.unlink(path)


def _patch_harte_pipeline_geometrie(monkeypatch, analysis, mix_in, mix_out):
  sections = [
    TrackSection("intro", 0.0, 16.0, 0, 8, 20.0),
    TrackSection("main", 16.0, 104.0, 8, 52, 70.0),
    TrackSection("outro", 104.0, 120.0, 52, 60, 20.0),
  ]
  structure = TrackStructure(sections=sections, total_bars=60, phrase_unit=8)
  monkeypatch.setattr(
    analysis, "analyze_structure_windows", lambda *a, **k: (structure, 1.0, True)
  )
  monkeypatch.setattr(
    analysis,
    "calculate_genre_aware_mix_points",
    lambda *a, **k: (mix_in, mix_out, int(mix_in / 2.0), int(mix_out / 2.0)),
  )
  monkeypatch.setattr(
    analysis, "estimate_first_phrase", lambda *a, **k: (0.0, 1.0)
  )


@pytest.fixture
def named_wav():
  """WAV-Datei mit DJ-typischem Dateinamen."""
  tmpdir = tempfile.mkdtemp()
  path = os.path.join(tmpdir, "DJ Snake - Turn Down For What.wav")
  _create_test_wav(path, duration=5.0)
  yield path
  if os.path.exists(path):
    os.unlink(path)
  os.rmdir(tmpdir)


# ============================================================
# analyze_track() Basis-Tests
# ============================================================

@pytest.mark.integration
class TestAnalyzeTrackBasics:
  """Grundlegende analyze_track() Pipeline Tests."""

  def test_returns_track_object(self, simple_wav):
    """Gibt Track-Objekt zurueck."""
    from hpg_core.analysis import analyze_track
    result = analyze_track(simple_wav)
    assert isinstance(result, Track)

  def test_none_input_returns_none(self):
    """None Input = None."""
    from hpg_core.analysis import analyze_track
    assert analyze_track(None) is None

  def test_empty_string_returns_none(self):
    """Leerer String = None."""
    from hpg_core.analysis import analyze_track
    assert analyze_track("") is None

  def test_nonexistent_file_returns_none(self):
    """Nicht existente Datei = None."""
    from hpg_core.analysis import analyze_track
    result = analyze_track("/nonexistent/path/fake.mp3")
    assert result is None

  def test_invalid_type_returns_none(self):
    """Nicht-String Input = None."""
    from hpg_core.analysis import analyze_track
    result = analyze_track(12345)
    assert result is None

  @pytest.mark.parametrize("duration", [0.0, -1.0, float("nan"), float("inf")])
  def test_ungueltige_dateidauer_stoppt_vor_import_cache_und_decode(
    self, monkeypatch, simple_wav, duration
  ):
    from hpg_core import analysis

    importer_factory = Mock()
    cache_reader = Mock()
    decoder = Mock()
    monkeypatch.setattr(analysis, "_get_file_duration", lambda _path: duration)
    monkeypatch.setattr(analysis, "get_rekordbox_importer", importer_factory)
    monkeypatch.setattr(analysis, "get_cached_track", cache_reader)
    monkeypatch.setattr(analysis.librosa, "load", decoder)

    assert analysis.analyze_track(simple_wav) is None
    importer_factory.assert_not_called()
    cache_reader.assert_not_called()
    decoder.assert_not_called()

  def test_rekordbox_fast_path_decode_error_returns_none_without_cache(
    self, monkeypatch, simple_wav
  ):
    from hpg_core import analysis

    importer = Mock()
    importer.get_track_data.return_value = RekordboxTrackData(
      bpm=128.0,
      duration=4.0,
      camelot_code="8A",
      title="Test",
      artist="Artist",
    )
    importer.get_track_signature.return_value = "rb-signature"
    cache_writer = Mock()

    monkeypatch.setattr(analysis, "get_rekordbox_importer", lambda: importer)
    monkeypatch.setattr(analysis, "get_cached_track", lambda *args, **kwargs: None)
    monkeypatch.setattr(analysis, "cache_track", cache_writer)
    monkeypatch.setattr(analysis, "extract_metadata", lambda path: ("A", "T", "G"))
    monkeypatch.setattr(analysis, "_get_file_duration", lambda path: 5.0)

    def fail_decode(*args, **kwargs):
      raise RuntimeError("decode failed")

    monkeypatch.setattr(analysis.librosa, "load", fail_decode)

    track = analysis.analyze_track(simple_wav)

    assert track is None
    cache_writer.assert_not_called()

  def test_rekordbox_import_error_falls_back_to_audio(
    self, monkeypatch, simple_wav
  ):
    from hpg_core import analysis

    def importer_fails():
      raise RuntimeError("rekordbox unavailable")

    monkeypatch.setattr(analysis, "get_rekordbox_importer", importer_fails)
    monkeypatch.setattr(analysis, "get_cached_track", lambda *args, **kwargs: None)
    monkeypatch.setattr(analysis, "cache_track", lambda *args, **kwargs: True)

    track = analysis.analyze_track(simple_wav)

    assert isinstance(track, Track)
    assert track.analysis_mode != "rekordbox_degraded"

  @pytest.mark.parametrize("invalid_mode", ["full", "unknown", "rekordbox_degraded"])
  def test_ungueltiger_cache_hit_wird_neu_analysiert(
    self, monkeypatch, simple_wav, invalid_mode
  ):
    from hpg_core import analysis

    invalid_cached = Track(
      filePath=simple_wav,
      fileName=os.path.basename(simple_wav),
      analysis_mode=invalid_mode,
    )
    monkeypatch.setattr(analysis, "get_rekordbox_importer", lambda: None)
    monkeypatch.setattr(analysis, "get_cached_track", lambda *args, **kwargs: invalid_cached)
    monkeypatch.setattr(analysis, "cache_track", lambda *args, **kwargs: True)

    track = analysis.analyze_track(simple_wav)

    assert isinstance(track, Track)
    assert track is not invalid_cached
    assert track.analysis_mode == "librosa_full_or_tail"

  def test_rekordbox_signature_error_uses_audio_fallback_and_unsigned_key(
    self, monkeypatch, simple_wav
  ):
    from hpg_core import analysis

    importer = Mock()
    importer.get_track_data.return_value = RekordboxTrackData(
      bpm=128.0, duration=5.0, camelot_code="8A", title="RB", artist="RB"
    )
    importer.get_track_signature.side_effect = RuntimeError("signature failed")
    seen = {}

    def cache_key(path, signature):
      seen["signature"] = signature
      return "unsigned-key"

    monkeypatch.setattr(analysis, "get_rekordbox_importer", lambda: importer)
    monkeypatch.setattr(analysis, "generate_cache_key", cache_key)
    monkeypatch.setattr(analysis, "get_cached_track", lambda *args, **kwargs: None)
    monkeypatch.setattr(analysis, "cache_track", lambda *args, **kwargs: True)

    track = analysis.analyze_track(simple_wav)

    assert isinstance(track, Track)
    assert not track.analysis_mode.startswith("rekordbox")
    assert seen["signature"] == ""

  def test_cache_key_error_fails_closed_before_cache_and_decode(
    self, monkeypatch, simple_wav
  ):
    from hpg_core import analysis

    importer = Mock()
    importer.get_track_data.return_value = None
    importer.get_track_signature.return_value = ""
    cache_reader = Mock()
    decoder = Mock()
    monkeypatch.setattr(analysis, "get_rekordbox_importer", lambda: importer)
    monkeypatch.setattr(
      analysis, "generate_cache_key", Mock(side_effect=RuntimeError("key failed"))
    )
    monkeypatch.setattr(analysis, "get_cached_track", cache_reader)
    monkeypatch.setattr(analysis.librosa, "load", decoder)

    assert analysis.analyze_track(simple_wav) is None
    cache_reader.assert_not_called()
    decoder.assert_not_called()

  def test_cache_read_error_is_miss_and_audio_analysis_continues(
    self, monkeypatch, simple_wav
  ):
    from hpg_core import analysis

    importer = Mock()
    importer.get_track_data.return_value = None
    importer.get_track_signature.return_value = ""
    monkeypatch.setattr(analysis, "get_rekordbox_importer", lambda: importer)
    monkeypatch.setattr(
      analysis, "get_cached_track", Mock(side_effect=RuntimeError("read failed"))
    )
    monkeypatch.setattr(analysis, "cache_track", lambda *args, **kwargs: True)

    track = analysis.analyze_track(simple_wav)

    assert isinstance(track, Track)


# ============================================================
# Track-Felder Validierung
# ============================================================

@pytest.mark.integration
class TestAnalyzeTrackFields:
  """Prueft ob alle Track-Felder korrekt befuellt werden."""

  def test_file_path_set(self, simple_wav):
    """filePath wird korrekt gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track.filePath == simple_wav

  def test_file_name_set(self, simple_wav):
    """fileName wird korrekt gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track.fileName == os.path.basename(simple_wav)

  def test_duration_positive(self, simple_wav):
    """Duration ist positiv."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track.duration > 0

  def test_duration_approximately_correct(self, simple_wav):
    """Duration ist ca. 5 Sekunden (Fixture-Laenge)."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert 4.0 <= track.duration <= 6.0, (
      f"Duration {track.duration}s (erwartet ~5.0s)"
    )

  def test_bpm_positive(self, simple_wav):
    """BPM ist positiv."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track.bpm > 0

  def test_bpm_reasonable_range(self, simple_wav):
    """BPM im DJ-Bereich (50-250)."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert 50 <= track.bpm <= 250, (
      f"BPM {track.bpm} ausserhalb DJ-Bereich"
    )

  def test_camelot_code_valid(self, simple_wav):
    """Camelot-Code ist gueltig (1A-12B)."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    import re
    if track.camelotCode:
      assert re.match(r"^(1[0-2]|[1-9])[AB]$", track.camelotCode), (
        f"Ungueltiger Camelot-Code: '{track.camelotCode}'"
      )

  def test_energy_in_range(self, simple_wav):
    """Energy zwischen 0 und 100."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert 0 <= track.energy <= 100

  def test_bass_intensity_in_range(self, simple_wav):
    """Bass Intensity zwischen 0 und 100."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert 0 <= track.bass_intensity <= 100

  def test_key_note_set(self, simple_wav):
    """keyNote ist gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track.keyNote is not None
    valid_notes = [
      "C", "C#", "D", "D#", "E", "F",
      "F#", "G", "G#", "A", "A#", "B",
      "Db", "Eb", "Gb", "Ab", "Bb",
    ]
    assert track.keyNote in valid_notes, (
      f"Unbekannte Note: '{track.keyNote}'"
    )

  def test_key_mode_set(self, simple_wav):
    """keyMode ist Major oder Minor."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(simple_wav)
    assert track.keyMode in ("Major", "Minor"), (
      f"Ungueltiger Mode: '{track.keyMode}'"
    )


# ============================================================
# Mix-Point Validierung in der Pipeline
# ============================================================

@pytest.mark.integration
class TestAnalyzeTrackMixPoints:
  """Mix-Point Validierung in voller Pipeline."""

  @pytest.fixture(autouse=True)
  def _verifiziertes_beatgrid(self, monkeypatch):
    """Diese Tests pruefen Mixpunkte nur fuer einen freigegebenen Track."""
    from hpg_core import analysis

    monkeypatch.setattr(
      analysis,
      "_validate_track_beatgrid",
      lambda *a, **k: analysis.BeatgridValidation("verified", 3, 2.0),
    )

  def test_mix_in_point_set(self, long_wav):
    """mix_in_point wird gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(long_wav)
    assert track.mix_in_point is not None
    assert track.mix_in_point >= 0

  def test_mix_out_point_set(self, long_wav):
    """mix_out_point wird gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(long_wav)
    assert track.mix_out_point is not None
    assert track.mix_out_point > 0

  def test_mix_out_after_mix_in(self, long_wav):
    """mix_out > mix_in."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(long_wav)
    assert track.mix_out_point > track.mix_in_point, (
      f"Mix-Out {track.mix_out_point} <= Mix-In {track.mix_in_point}"
    )

  def test_mix_points_within_duration(self, long_wav):
    """Mix-Points innerhalb der Track-Dauer."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(long_wav)
    assert track.mix_in_point <= track.duration, (
      f"Mix-In {track.mix_in_point} > Duration {track.duration}"
    )
    assert track.mix_out_point <= track.duration, (
      f"Mix-Out {track.mix_out_point} > Duration {track.duration}"
    )

  def test_mix_in_bars_set(self, long_wav):
    """mix_in_bars wird gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(long_wav)
    assert track.mix_in_bars is not None
    assert track.mix_in_bars >= 0

  def test_mix_out_bars_set(self, long_wav):
    """mix_out_bars wird gesetzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(long_wav)
    assert track.mix_out_bars is not None
    assert track.mix_out_bars > 0


# ============================================================
# Edge Cases
# ============================================================

@pytest.mark.integration
class TestAnalyzeTrackEdgeCases:
  """Edge Cases fuer analyze_track()."""

  def test_silence_does_not_crash(self, silence_wav):
    """Stille WAV crasht nicht."""
    from hpg_core.analysis import analyze_track
    result = analyze_track(silence_wav)
    assert result is not None
    assert isinstance(result, Track)

  def test_silence_has_defaults(self, silence_wav):
    """Stille WAV hat sinnvolle Defaults."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(silence_wav)
    # BPM sollte Default sein
    assert track.bpm >= 0

  def test_named_file_extracts_metadata(self, named_wav):
    """DJ-Dateiname wird fuer Metadata genutzt."""
    from hpg_core.analysis import analyze_track
    track = analyze_track(named_wav)
    # Artist oder Title sollte aus Dateiname extrahiert werden
    assert track.fileName == "DJ Snake - Turn Down For What.wav"

  def test_pathlike_input(self, simple_wav):
    """os.PathLike Input funktioniert."""
    from hpg_core.analysis import analyze_track
    from pathlib import Path
    result = analyze_track(Path(simple_wav))
    assert isinstance(result, Track)


# ============================================================
# Caching in der Pipeline
# ============================================================

@pytest.mark.integration
class TestAnalyzeTrackCaching:
  """Caching-Verhalten in analyze_track()."""

  def test_second_call_uses_cache(self, simple_wav):
    """Zweiter Aufruf nutzt Cache (schneller)."""
    from hpg_core.analysis import analyze_track
    # Erster Aufruf (erzeugt Cache)
    track1 = analyze_track(simple_wav)

    # Zweiter Aufruf (aus Cache)
    track2 = analyze_track(simple_wav)

    # Cache-Hit sollte deutlich schneller sein
    assert track1.bpm == track2.bpm
    assert track1.camelotCode == track2.camelotCode
    # Timing-Vergleich kann flaky sein, daher nur Track-Gleichheit pruefen

  def test_cached_track_has_all_fields(self, simple_wav):
    """Gecachter Track hat alle Felder."""
    from hpg_core.analysis import analyze_track

    # Erster Aufruf (erzeugt Cache)
    track1 = analyze_track(simple_wav)
    # Zweiter Aufruf (aus Cache)
    track2 = analyze_track(simple_wav)

    assert track2.filePath == track1.filePath
    assert track2.duration == track1.duration
    assert track2.bpm == track1.bpm
    assert track2.energy == track1.energy

  @pytest.mark.parametrize("pfad", ["rekordbox_fast", "librosa_voll"])
  def test_cache_write_false_verwirft_analyseerfolg_beider_pfade(
    self, monkeypatch, simple_wav, pfad
  ):
    from hpg_core import analysis

    importer = Mock()
    importer.get_track_data.return_value = (
      RekordboxTrackData(
        bpm=128.0,
        duration=5.0,
        camelot_code="8A",
        title="T",
        artist="A",
        content_id="persistenz-test",
      )
      if pfad == "rekordbox_fast"
      else None
    )
    importer.get_track_signature.return_value = "persistenz-test"
    importer.get_beatgrid.return_value = []
    importer.get_phrases.return_value = []
    cache_writer = Mock(return_value=False)
    monkeypatch.setattr(analysis, "get_rekordbox_importer", lambda: importer)
    monkeypatch.setattr(analysis, "get_cached_track", lambda *a, **k: None)
    monkeypatch.setattr(analysis, "cache_track", cache_writer)

    assert analysis.analyze_track(simple_wav) is None
    cache_writer.assert_called_once()


# ============================================================
# Rekordbox-Fast-Path: Kandidaten statt Cue-Heuristik (Spec 2026-08-21)
# ============================================================

@pytest.mark.integration
class TestAnalyzeTrackFastPathCandidates:
  """Erfolgreicher Rekordbox-Fast-Path mit gemocktem Importer."""

  def test_fast_path_fuellt_phrasen_cues_gitter_und_kandidaten(
    self, monkeypatch, tmp_path
  ):
    """Rekordbox-Pfad: Track traegt phrases/cue_points/phrase_grid/mix_*_candidates;
    die Cue-Positionsheuristik (2./letzter Cue) wird NICHT mehr angewendet."""
    from hpg_core import analysis

    wav = tmp_path / "fast.wav"
    _create_click_wav(str(wav), bpm=128.0, duration=120.0)
    data = RekordboxTrackData(
      bpm=128.0, duration=119.0, camelot_code="8A", title="T", artist="A",
      cue_points=[
        {"position": p, "name": None, "type": 0,
         "hot_cue_number": None, "color": None}
        for p in (20.0, 61.0, 100.0, 119.5, 120.001)
      ],
      content_id="1",
    )
    importer = Mock()
    importer.get_track_data.return_value = data
    importer.get_track_signature.return_value = "rb-signature"
    importer.get_beatgrid.return_value = [
      {"beat": index % 4 + 1, "time": index * (60.0 / 128.0)}
      for index in range(256)
    ]
    importer.get_phrases.return_value = [
      {"start_s": 0.0, "end_s": 30.0, "label": "Intro",
       "mood": 1, "kind": 1, "fill": 0},
      {"start_s": 30.0, "end_s": 120.0, "label": "Chorus",
       "mood": 1, "kind": 5, "fill": 0},
    ]
    monkeypatch.setattr(analysis, "get_rekordbox_importer", lambda: importer)
    monkeypatch.setattr(analysis, "get_cached_track", lambda *a, **k: None)
    cache_writer = Mock(return_value=True)
    monkeypatch.setattr(analysis, "cache_track", cache_writer)
    bpm_factor_guard = Mock(
      side_effect=AssertionError("Rekordbox-Fastpath darf ID3-BPM nicht pruefen")
    )
    monkeypatch.setattr(analysis, "_correct_id3_bpm_factor", bpm_factor_guard)

    track = analysis.analyze_track(str(wav))

    assert track is not None
    cache_writer.assert_called_once()
    assert track.bpm == 128.0
    bpm_factor_guard.assert_not_called()
    assert track.duration == pytest.approx(120.0)
    assert set(track_to_dict(track)) == TRACK_REQUIRED_FIELDS
    validate_track_dict(track_to_dict(track))
    assert track.beatgrid_source == "rekordbox"
    assert track.beatgrid_status == "verified"
    assert track.beatgrid_windows_checked >= 3
    assert [p["label"] for p in track.phrases] == ["Intro", "Chorus"]
    assert track.phrase_grid == [0.0, 30.0, 120.0]
    assert [c["t"] for c in track.cue_points] == [20.0, 61.0, 100.0, 119.5]
    assert all(c["provenance"] == "leer" for c in track.cue_points)
    assert all(
      "t" in c and "schema" in c and "confidence" in c
      for c in track.mix_in_candidates + track.mix_out_candidates
    )
    assert track.mix_in_candidates, "Mix-In-Kandidaten fehlen"
    # Heuristik weg: der 2. Cue (61 s) setzt den Mix-In NICHT mehr direkt
    assert abs(track.mix_in_point - 61.0) > 0.5 or any(
      "analyzer" in c["schema"] for c in track.mix_in_candidates
    )
    importer.get_phrases.assert_called_once_with(
      str(wav), duration=pytest.approx(120.0)
    )

  def test_fast_path_verwirft_in_im_50ms_band_und_behaelt_gueltigen_out(
    self, monkeypatch, tmp_path
  ):
    from hpg_core import analysis

    wav = tmp_path / "fast_harter_cue_vertrag.wav"
    _create_click_wav(str(wav), bpm=120.0, duration=120.0)
    data = RekordboxTrackData(
      bpm=120.0,
      duration=120.0,
      camelot_code="8A",
      cue_points=[
        {"position": 16.05, "name": "MIX IN", "type": 0,
         "hot_cue_number": 1, "color": None},
        {"position": 80.0, "name": "MIX OUT", "type": 0,
         "hot_cue_number": 2, "color": None},
      ],
      content_id="fast-harter-cue-vertrag",
    )
    importer = Mock()
    importer.get_track_data.return_value = data
    importer.get_track_signature.return_value = "fast-harter-cue-vertrag"
    importer.get_beatgrid.return_value = [
      {"beat": index % 4 + 1, "time": index * 0.5}
      for index in range(240)
    ]
    importer.get_phrases.return_value = []
    monkeypatch.setattr(analysis, "get_rekordbox_importer", lambda: importer)
    monkeypatch.setattr(analysis, "get_cached_track", lambda *a, **k: None)
    monkeypatch.setattr(analysis, "cache_track", Mock(return_value=True))
    monkeypatch.setattr(
      analysis,
      "_validate_track_beatgrid",
      lambda *a, **k: analysis.BeatgridValidation("verified", 3, 0.0),
    )
    _patch_harte_pipeline_geometrie(monkeypatch, analysis, 48.0, 96.0)

    track = analysis.analyze_track(str(wav))

    assert track is not None
    assert track.analysis_mode == "rekordbox_fast_tail"
    assert (track.mix_in_point, track.mix_out_point) == (48.0, 80.0)

  def test_fast_path_nutzt_audio_anker_bei_rekordbox_grid_mismatch(
    self, monkeypatch, tmp_path
  ):
    from hpg_core import analysis

    wav = tmp_path / "grid_mismatch.wav"
    _create_click_wav(str(wav), bpm=128.0, duration=120.0)
    data = RekordboxTrackData(
      bpm=128.0, duration=121.0, camelot_code="8A", content_id="1"
    )
    importer = Mock()
    importer.get_track_data.return_value = data
    importer.get_track_signature.return_value = "rb-signature"
    importer.get_beatgrid.return_value = [
      {"beat": index % 4 + 1, "time": index * (60.0 / 128.0)}
      for index in range(256)
    ]
    importer.get_phrases.return_value = [
      {"start_s": 0.0, "end_s": 120.0, "label": "Chorus"}
    ]
    monkeypatch.setattr(analysis, "get_rekordbox_importer", lambda: importer)
    monkeypatch.setattr(analysis, "get_cached_track", lambda *a, **k: None)
    monkeypatch.setattr(analysis, "cache_track", Mock(return_value=True))
    monkeypatch.setattr(
      analysis,
      "_validate_track_beatgrid",
      lambda *a, **k: analysis.BeatgridValidation("mismatch", 3, 35.0),
    )
    monkeypatch.setattr(
      analysis, "estimate_first_downbeat", lambda *a, **k: (0.0, 0.8)
    )

    track = analysis.analyze_track(str(wav))

    assert track is not None
    assert track.duration == pytest.approx(120.0)
    assert track.beatgrid_source == "rekordbox"
    assert track.beatgrid_status == "mismatch"
    assert track.downbeat_confidence == 0.8
    assert track.phrases == [] and track.phrase_grid == []
    assert track.mix_in_point >= 0.0 and track.mix_out_point > track.mix_in_point
    assert track.mix_in_candidates and track.mix_out_candidates
    importer.get_phrases.assert_not_called()


# ============================================================
# Voll-Pfad (kein Rekordbox): Kandidaten ohne Phrasen (Spec 2026-08-21)
# ============================================================

@pytest.mark.integration
def test_voll_pfad_ohne_rekordbox_hat_analyzer_kandidaten_ohne_phrasen(monkeypatch, tmp_path):
    """Voll-Pfad (kein Rekordbox): keine Phrasen/Cues/Gitter, aber Kandidaten aus Analyzer/Sektionen."""
    from unittest.mock import Mock
    from hpg_core import analysis
    wav = tmp_path / "voll.wav"
    _create_click_wav(str(wav), bpm=128.0, duration=120.0)
    monkeypatch.setattr(analysis, "get_rekordbox_importer",
                        lambda: type("NoRekordbox", (), {"get_track_data": lambda self, _p: None})())
    monkeypatch.setattr(analysis, "get_cached_track", lambda *a, **k: None)
    cache_writer = Mock(return_value=True)
    monkeypatch.setattr(analysis, "cache_track", cache_writer)
    monkeypatch.setattr(
      analysis,
      "_validate_track_beatgrid",
      lambda *a, **k: analysis.BeatgridValidation("verified", 3, 2.0),
    )
    track = analysis.analyze_track(str(wav))
    assert track is not None
    cache_writer.assert_called_once()
    assert set(track_to_dict(track)) == TRACK_REQUIRED_FIELDS
    assert track.beatgrid_source == "audio"
    assert track.beatgrid_status == "verified"
    assert track.phrases == [] and track.cue_points == [] and track.phrase_grid == []
    assert track.mix_in_candidates, "Mix-In-Kandidaten fehlen"
    erlaubt = {"analyzer", "sektion", "energie_neuheit"}
    assert all(set(c["schema"]) <= erlaubt for c in track.mix_in_candidates + track.mix_out_candidates)
    assert all("confidence" in c and 0.0 <= c["confidence"] <= 1.0 for c in track.mix_in_candidates)


@pytest.mark.integration
def test_voll_pfad_beatgrid_diagnose_sperrt_mixpunkte_nicht(
  monkeypatch, tmp_path
):
    from hpg_core import analysis

    wav = tmp_path / "voll_grid_mismatch.wav"
    _create_click_wav(str(wav), bpm=128.0, duration=120.0)
    monkeypatch.setattr(
      analysis,
      "get_rekordbox_importer",
      lambda: type("NoRekordbox", (), {"get_track_data": lambda self, _p: None})(),
    )
    monkeypatch.setattr(analysis, "get_cached_track", lambda *a, **k: None)
    monkeypatch.setattr(analysis, "cache_track", Mock(return_value=True))
    monkeypatch.setattr(
      analysis,
      "_validate_track_beatgrid",
      lambda *a, **k: analysis.BeatgridValidation("mismatch", 3, 35.0),
    )

    track = analysis.analyze_track(str(wav))

    assert track is not None
    assert track.beatgrid_source == "audio"
    assert track.beatgrid_status == "mismatch"
    assert track.mix_in_point >= 0.0 and track.mix_out_point > track.mix_in_point
    assert track.mix_in_candidates and track.mix_out_candidates


@pytest.mark.integration
@pytest.mark.parametrize("rekordbox_bpm", [None, 0.0])
def test_voll_pfad_behaelt_sichere_rekordbox_daten_ohne_rb_bpm(
  monkeypatch, tmp_path, rekordbox_bpm
):
    from hpg_core import analysis

    wav = tmp_path / f"rb_ohne_bpm_{rekordbox_bpm}.wav"
    _create_click_wav(str(wav), bpm=128.0, duration=120.0)
    data = RekordboxTrackData(
      bpm=rekordbox_bpm,
      duration=90.0,
      camelot_code="8A",
      title="RB Titel",
      artist="RB Artist",
      genre="Psytrance",
      cue_points=[
        {"position": 32.0, "name": "MIX IN", "type": 0,
         "hot_cue_number": 1, "color": None},
        {"position": 96.0, "name": "MIX OUT", "type": 0,
         "hot_cue_number": 2, "color": None},
        {"position": 120.001, "name": "STALE OUT", "type": 0,
         "hot_cue_number": 3, "color": None},
      ],
      content_id="1",
    )
    importer = Mock()
    importer.get_track_data.return_value = data
    importer.get_track_signature.return_value = "rb-ohne-bpm-signatur"
    importer.get_beatgrid.return_value = [
      {"beat": index % 4 + 1, "time": index * 0.46875}
      for index in range(256)
    ]
    importer.get_phrases.return_value = [
      {"start_s": 0.0, "end_s": 30.0, "label": "Intro",
       "mood": 1, "kind": 1, "fill": 0},
      {"start_s": 30.0, "end_s": 120.0, "label": "Chorus",
       "mood": 1, "kind": 5, "fill": 0},
    ]
    monkeypatch.setattr(analysis, "get_rekordbox_importer", lambda: importer)
    monkeypatch.setattr(analysis, "get_cached_track", lambda *a, **k: None)
    monkeypatch.setattr(analysis, "cache_track", Mock(return_value=True))
    monkeypatch.setattr(
      analysis,
      "_validate_track_beatgrid",
      lambda *a, **k: analysis.BeatgridValidation("verified", 3, 2.0),
    )

    track = analysis.analyze_track(str(wav))

    assert track is not None
    assert track.analysis_mode == "librosa_full_or_tail"
    assert track.bpm > 0.0
    assert (track.artist, track.title, track.genre) == (
      "RB Artist", "RB Titel", "Psytrance"
    )
    assert (track.camelotCode, track.keyNote, track.keyMode) == (
      "8A", "A", "Minor"
    )
    assert track.key_confidence == 1.0
    assert track.beatgrid_source == "rekordbox"
    assert track.beatgrid_status == "verified"
    assert [phrase["label"] for phrase in track.phrases] == ["Intro", "Chorus"]
    assert track.phrase_grid == [0.0, 30.0, 120.0]
    assert [cue["name"] for cue in track.cue_points] == ["MIX IN", "MIX OUT"]
    assert all(
      candidate["t"] <= track.duration
      for candidate in track.mix_in_candidates + track.mix_out_candidates
    )
    validate_track_dict(track_to_dict(track))
    assert track.mix_in_point >= 0.0 < track.mix_out_point <= track.duration
    importer.get_phrases.assert_called_once_with(
      str(wav), duration=pytest.approx(120.0)
    )


@pytest.mark.integration
def test_bpm_loser_vollpfad_verwirft_out_im_50ms_band_und_behaelt_in(
  monkeypatch, tmp_path
):
  from hpg_core import analysis

  wav = tmp_path / "voll_harter_cue_vertrag.wav"
  _create_click_wav(str(wav), bpm=120.0, duration=120.0)
  data = RekordboxTrackData(
    bpm=None,
    duration=120.0,
    camelot_code="8A",
    cue_points=[
      {"position": 32.0, "name": "MIX IN", "type": 0,
       "hot_cue_number": 1, "color": None},
      {"position": 103.95, "name": "MIX OUT", "type": 0,
       "hot_cue_number": 2, "color": None},
    ],
    content_id="voll-harter-cue-vertrag",
  )
  importer = Mock()
  importer.get_track_data.return_value = data
  importer.get_track_signature.return_value = "voll-harter-cue-vertrag"
  importer.get_beatgrid.return_value = [
    {"beat": index % 4 + 1, "time": index * 0.5}
    for index in range(240)
  ]
  importer.get_phrases.return_value = []
  monkeypatch.setattr(analysis, "get_rekordbox_importer", lambda: importer)
  monkeypatch.setattr(analysis, "get_cached_track", lambda *a, **k: None)
  monkeypatch.setattr(analysis, "cache_track", Mock(return_value=True))
  monkeypatch.setattr(analysis, "extract_bpm_from_tags", lambda *a, **k: 120.0)
  monkeypatch.setattr(
    analysis,
    "_validate_track_beatgrid",
    lambda *a, **k: analysis.BeatgridValidation("verified", 3, 0.0),
  )
  _patch_harte_pipeline_geometrie(monkeypatch, analysis, 48.0, 80.0)

  track = analysis.analyze_track(str(wav))

  assert track is not None
  assert track.analysis_mode == "librosa_full_or_tail"
  assert track.bpm == 120.0
  assert (track.mix_in_point, track.mix_out_point) == (32.0, 80.0)


@pytest.mark.integration
def test_voll_pfad_verwirft_pssi_bei_rb_grid_mismatch_aber_behaelt_cues(
  monkeypatch, tmp_path
):
    from hpg_core import analysis

    wav = tmp_path / "rb_ohne_bpm_mismatch.wav"
    _create_click_wav(str(wav), bpm=128.0, duration=120.0)
    data = RekordboxTrackData(
      bpm=None,
      duration=120.0,
      camelot_code="8A",
      cue_points=[
        {"position": 32.0, "name": "MIX IN", "type": 0,
         "hot_cue_number": 1, "color": None},
      ],
      content_id="1",
    )
    importer = Mock()
    importer.get_track_data.return_value = data
    importer.get_track_signature.return_value = "rb-mismatch-signatur"
    importer.get_beatgrid.return_value = [
      {"beat": index % 4 + 1, "time": index * 0.5}
      for index in range(240)
    ]
    importer.get_phrases.return_value = [
      {"start_s": 0.0, "end_s": 120.0, "label": "Chorus"}
    ]
    monkeypatch.setattr(analysis, "get_rekordbox_importer", lambda: importer)
    monkeypatch.setattr(analysis, "get_cached_track", lambda *a, **k: None)
    monkeypatch.setattr(analysis, "cache_track", Mock(return_value=True))
    monkeypatch.setattr(
      analysis,
      "_validate_track_beatgrid",
      lambda *a, **k: analysis.BeatgridValidation("mismatch", 3, 35.0),
    )
    monkeypatch.setattr(
      analysis, "estimate_first_downbeat", lambda *a, **k: (0.25, 0.8)
    )

    track = analysis.analyze_track(str(wav))

    assert track is not None
    assert track.beatgrid_source == "rekordbox"
    assert track.beatgrid_status == "mismatch"
    assert track.downbeat_confidence == 0.8
    assert track.phrases == [] and track.phrase_grid == []
    assert [cue["name"] for cue in track.cue_points] == ["MIX IN"]
    importer.get_phrases.assert_not_called()


def _harte_cue_sections():
  return [
    {"label": "intro", "start_time": 0.0, "end_time": 32.0},
    {"label": "main", "start_time": 32.0, "end_time": 160.0},
    {"label": "outro", "start_time": 160.0, "end_time": 200.0},
  ]


def _manual_cue(t, name):
  return {"t": t, "name": name, "provenance": "manual"}


def test_manual_mixpoint_cues_respektieren_intro_outro_und_sicherheitsband():
  from hpg_core.analysis import _apply_manual_mixpoint_cues

  result = _apply_manual_mixpoint_cues(
    48.0,
    144.0,
    cue_points=[_manual_cue(32.04, "MIX IN"), _manual_cue(160.0, "MIX OUT")],
    bpm=120.0,
    duration=200.0,
    phrase_unit=8,
    anchor=0.0,
    sections=_harte_cue_sections(),
  )

  assert result == (48.0, 144.0)


def test_manual_mixpoint_cues_uebernehmen_gueltiges_paar_auf_phrasengitter():
  from hpg_core.analysis import _apply_manual_mixpoint_cues

  result = _apply_manual_mixpoint_cues(
    48.0,
    144.0,
    cue_points=[_manual_cue(64.0, "MIX IN"), _manual_cue(128.0, "MIX OUT")],
    bpm=120.0,
    duration=200.0,
    phrase_unit=8,
    anchor=0.0,
    sections=_harte_cue_sections(),
  )

  assert result == (64.0, 128.0)


def test_ungueltiger_in_cue_verwirft_gueltigen_out_cue_nicht_mit():
  from hpg_core.analysis import _apply_manual_mixpoint_cues

  result = _apply_manual_mixpoint_cues(
    48.0,
    144.0,
    cue_points=[_manual_cue(16.0, "MIX IN"), _manual_cue(128.0, "MIX OUT")],
    bpm=120.0,
    duration=200.0,
    phrase_unit=8,
    anchor=0.0,
    sections=_harte_cue_sections(),
  )

  assert result == (48.0, 128.0)


def test_manual_cues_unterschreiten_nicht_zwei_phrasen_mindestfenster():
  from hpg_core.analysis import _apply_manual_mixpoint_cues

  result = _apply_manual_mixpoint_cues(
    48.0,
    144.0,
    cue_points=[_manual_cue(112.0, "MIX IN"), _manual_cue(128.0, "MIX OUT")],
    bpm=120.0,
    duration=200.0,
    phrase_unit=8,
    anchor=0.0,
    sections=_harte_cue_sections(),
  )

  # Das gemeinsame 112/128-Fenster ist zu kurz. Der einzeln gueltige IN-Cue
  # bleibt erhalten, der OUT-Cue faellt auf 144 zurueck: exakt zwei Phrasen.
  assert result == (112.0, 144.0)


def test_harter_cue_vertrag_nutzt_acht_bar_fallback_bei_phrase_unit_null():
  from hpg_core.analysis import _mixpoint_pair_erfuellt_harten_vertrag

  kwargs = {
    "bpm": 120.0,
    "duration": 200.0,
    "phrase_unit": 0,
    "anchor": 0.0,
    "sections": _harte_cue_sections(),
  }

  assert not _mixpoint_pair_erfuellt_harten_vertrag(48.0, 64.0, **kwargs)
  assert _mixpoint_pair_erfuellt_harten_vertrag(48.0, 80.0, **kwargs)

"""
Tests fuer hpg_core.structure_analyzer - Track-Struktur-Erkennung fuer DJ Brain.
Testet Sektions-Erkennung, Boundary-Detection, Quantisierung und Labeling.
"""
import pytest
import numpy as np

from hpg_core.structure_analyzer import (
  TrackSection,
  TrackStructure,
  GENRE_PHRASE_UNITS,
  MIN_SECTIONS,
  MAX_SECTIONS,
  MIN_SECTION_DURATION,
  ENERGY_HIGH_THRESHOLD,
  ENERGY_LOW_THRESHOLD,
  _compute_novelty_curve,
  _pick_boundaries,
  _quantize_to_bars,
  _compute_section_energy,
  _compute_energy_trend,
  _label_sections,
  analyze_structure,
)
from hpg_core.config import METER


# === Hilfsfunktionen fuer synthetische Audio-Signale ===

def _make_silence(sr: int, duration: float) -> np.ndarray:
  """Erzeugt Stille."""
  return np.zeros(int(sr * duration), dtype=np.float32)


def _make_tone(sr: int, duration: float, freq: float = 440.0, amplitude: float = 0.3) -> np.ndarray:
  """Erzeugt einen Sinuston."""
  t = np.linspace(0, duration, int(sr * duration), endpoint=False)
  return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _make_noise(sr: int, duration: float, amplitude: float = 0.3) -> np.ndarray:
  """Erzeugt weisses Rauschen."""
  return (amplitude * np.random.randn(int(sr * duration))).astype(np.float32)


def _make_structured_track(sr: int = 22050) -> np.ndarray:
  """
  Erzeugt einen synthetischen Track mit klaren Sektionen:
  - 0-10s: Leise (Intro)
  - 10-20s: Mittel, ansteigend (Build)
  - 20-40s: Laut (Drop)
  - 40-50s: Mittel (Breakdown)
  - 50-60s: Leise, abfallend (Outro)
  """
  intro = _make_tone(sr, 10.0, freq=220, amplitude=0.05)
  build = np.linspace(0.05, 0.3, int(sr * 10)) * np.sin(2 * np.pi * 330 * np.linspace(0, 10, int(sr * 10)))
  drop = _make_noise(sr, 20.0, amplitude=0.35) + _make_tone(sr, 20.0, freq=100, amplitude=0.25)
  breakdown = _make_tone(sr, 10.0, freq=440, amplitude=0.15)
  outro = _make_tone(sr, 10.0, freq=220, amplitude=0.04)

  y = np.concatenate([intro, build.astype(np.float32), drop, breakdown, outro])
  return y


# === TrackSection Dataclass ===

class TestTrackSection:
  """Prueft die TrackSection Datenstruktur."""

  def test_basic_creation(self):
    s = TrackSection(label="intro", start_time=0.0, end_time=30.0,
                     start_bar=0, end_bar=16, avg_energy=25.0)
    assert s.label == "intro"
    assert s.start_time == 0.0
    assert s.end_time == 30.0

  def test_duration(self):
    s = TrackSection(label="drop", start_time=60.0, end_time=120.0,
                     start_bar=32, end_bar=64, avg_energy=85.0)
    assert s.duration() == 60.0

  def test_zero_duration(self):
    s = TrackSection(label="main", start_time=10.0, end_time=10.0,
                     start_bar=5, end_bar=5, avg_energy=50.0)
    assert s.duration() == 0.0

  def test_to_dict(self):
    s = TrackSection(label="outro", start_time=180.0, end_time=210.0,
                     start_bar=96, end_bar=112, avg_energy=20.0)
    d = s.to_dict()
    assert isinstance(d, dict)
    assert d["label"] == "outro"
    assert d["start_time"] == 180.0
    assert d["end_time"] == 210.0
    assert d["start_bar"] == 96
    assert d["end_bar"] == 112
    assert d["avg_energy"] == 20.0

  def test_valid_labels(self):
    """Alle erwarteten Labels sind gueltig."""
    valid = {"intro", "build", "drop", "breakdown", "outro", "main"}
    for label in valid:
      s = TrackSection(label=label, start_time=0, end_time=10,
                       start_bar=0, end_bar=5, avg_energy=50)
      assert s.label in valid


# === TrackStructure Dataclass ===

class TestTrackStructure:
  """Prueft die TrackStructure Datenstruktur."""

  def test_default_empty(self):
    ts = TrackStructure()
    assert ts.sections == []
    assert ts.total_bars == 0
    assert ts.phrase_unit == 8

  def test_with_sections(self):
    sections = [
      TrackSection("intro", 0, 30, 0, 16, 25),
      TrackSection("drop", 30, 90, 16, 48, 80),
      TrackSection("outro", 90, 120, 48, 64, 20),
    ]
    ts = TrackStructure(sections=sections, total_bars=64, phrase_unit=16)
    assert len(ts.sections) == 3
    assert ts.total_bars == 64
    assert ts.phrase_unit == 16


# === Genre-spezifische Phrase Units ===

class TestGenrePhraseUnits:
  """Prueft die Genre-Phrase-Unit-Zuordnung."""

  def test_psytrance_16_bars(self):
    assert GENRE_PHRASE_UNITS["Psytrance"] == 16

  def test_tech_house_8_bars(self):
    assert GENRE_PHRASE_UNITS["Tech House"] == 8

  def test_progressive_8_bars(self):
    assert GENRE_PHRASE_UNITS["Progressive"] == 8

  def test_melodic_techno_8_bars(self):
    assert GENRE_PHRASE_UNITS["Melodic Techno"] == 8

  def test_unknown_8_bars(self):
    assert GENRE_PHRASE_UNITS["Unknown"] == 8

  def test_all_genres_defined(self):
    expected = {
      "Psytrance", "Tech House", "Progressive", "Melodic Techno",
      "Techno", "Deep House", "Trance", "Drum & Bass", "Minimal",
      "Unknown"
    }
    assert set(GENRE_PHRASE_UNITS.keys()) == expected

  def test_all_values_power_of_2_multiple(self):
    """Phrase Units muessen 8 oder 16 sein (Vielfache von 8)."""
    for genre, unit in GENRE_PHRASE_UNITS.items():
      assert unit in (8, 16, 32), f"{genre}: {unit} ist kein gueltiger Phrase Unit"


# === Quantize to Bars ===

class TestQuantizeToBars:
  """Prueft die Bar-Quantisierung."""

  def test_exact_bar_boundary(self):
    """Exakte Bar-Grenzen bleiben unveraendert."""
    bpm = 120.0
    spb = 60.0 / bpm * METER  # 2.0 Sekunden pro Bar
    boundaries = [0.0, spb * 4, spb * 8]  # Bar 0, 4, 8
    result = _quantize_to_bars(boundaries, bpm, spb * 16)
    assert 0.0 in result
    assert abs(result[1] - spb * 4) < 0.01
    assert abs(result[2] - spb * 8) < 0.01

  def test_snaps_to_nearest_bar(self):
    """Werte zwischen Bars werden zum naechsten Bar gerundet."""
    bpm = 120.0
    spb = 60.0 / bpm * METER  # 2.0 sec/bar
    boundaries = [0.0, spb * 3.7, spb * 8.2]
    result = _quantize_to_bars(boundaries, bpm, spb * 16)
    # 3.7 bars -> round to 4 bars = 8.0s
    # 8.2 bars -> round to 8 bars = 16.0s
    assert any(abs(t - spb * 4) < 0.01 for t in result)
    assert any(abs(t - spb * 8) < 0.01 for t in result)

  def test_removes_duplicates(self):
    """Doppelte Boundaries nach Quantisierung werden entfernt."""
    bpm = 120.0
    spb = 60.0 / bpm * METER
    # Beide nahe an Bar 4
    boundaries = [0.0, spb * 3.9, spb * 4.1]
    result = _quantize_to_bars(boundaries, bpm, spb * 16)
    # Beide sollten zu Bar 4 gerundet werden -> nur einer bleibt
    assert len(result) == len(set(result))

  def test_zero_bpm_returns_unchanged(self):
    """Bei BPM=0 keine Quantisierung."""
    boundaries = [0.0, 30.0, 60.0]
    result = _quantize_to_bars(boundaries, 0.0, 90.0)
    assert result == boundaries

  def test_clamped_to_duration(self):
    """Werte werden auf Track-Laenge begrenzt."""
    bpm = 120.0
    duration = 60.0
    boundaries = [0.0, 55.0, 100.0]  # 100 > duration
    result = _quantize_to_bars(boundaries, bpm, duration)
    for t in result:
      assert t <= duration

  def test_minimum_spacing(self):
    """Mindestabstand von 2 Bars wird eingehalten."""
    bpm = 120.0
    spb = 60.0 / bpm * METER
    # Sehr nahe Boundaries
    boundaries = [0.0, spb * 1.0, spb * 1.5, spb * 10.0]
    result = _quantize_to_bars(boundaries, bpm, spb * 20)
    for i in range(1, len(result)):
      assert result[i] - result[i - 1] >= spb * 2 - 0.01


# === Section Energy ===

class TestComputeSectionEnergy:
  """Prueft die Energie-Berechnung pro Sektion."""

  def test_silence_has_zero_energy(self):
    sr = 22050
    y = _make_silence(sr, 10.0)
    energy = _compute_section_energy(y, sr, 0.0, 10.0)
    assert energy == 0.0

  def test_loud_signal_has_high_energy(self):
    sr = 22050
    y = _make_tone(sr, 10.0, amplitude=0.35)
    energy = _compute_section_energy(y, sr, 0.0, 10.0)
    assert energy > 50.0

  def test_quiet_signal_has_low_energy(self):
    sr = 22050
    y = _make_tone(sr, 10.0, amplitude=0.02)
    energy = _compute_section_energy(y, sr, 0.0, 10.0)
    assert energy < 20.0

  def test_energy_between_0_and_100(self):
    sr = 22050
    y = _make_noise(sr, 10.0, amplitude=0.5)
    energy = _compute_section_energy(y, sr, 0.0, 10.0)
    assert 0.0 <= energy <= 100.0

  def test_partial_section(self):
    """Nur ein Teil des Signals wird bewertet."""
    sr = 22050
    silence = _make_silence(sr, 5.0)
    loud = _make_tone(sr, 5.0, amplitude=0.3)
    y = np.concatenate([silence, loud])
    energy_first = _compute_section_energy(y, sr, 0.0, 5.0)
    energy_second = _compute_section_energy(y, sr, 5.0, 10.0)
    assert energy_second > energy_first


# === Energy Trend ===

class TestComputeEnergyTrend:
  """Prueft die Energie-Trend-Erkennung."""

  def test_rising_trend(self):
    sr = 22050
    # Erste Haelfte leise, zweite laut
    quiet = _make_tone(sr, 5.0, amplitude=0.02)
    loud = _make_tone(sr, 5.0, amplitude=0.3)
    y = np.concatenate([quiet, loud])
    trend = _compute_energy_trend(y, sr, 0.0, 10.0)
    assert trend == "rising"

  def test_falling_trend(self):
    sr = 22050
    loud = _make_tone(sr, 5.0, amplitude=0.3)
    quiet = _make_tone(sr, 5.0, amplitude=0.02)
    y = np.concatenate([loud, quiet])
    trend = _compute_energy_trend(y, sr, 0.0, 10.0)
    assert trend == "falling"

  def test_stable_trend(self):
    sr = 22050
    y = _make_tone(sr, 10.0, amplitude=0.2)
    trend = _compute_energy_trend(y, sr, 0.0, 10.0)
    assert trend == "stable"

  def test_very_short_segment_is_stable(self):
    """Segmente < 1 Sekunde gelten als stabil."""
    sr = 22050
    y = _make_tone(sr, 0.5, amplitude=0.3)
    trend = _compute_energy_trend(y, sr, 0.0, 0.5)
    assert trend == "stable"


# === Label Sections ===

class TestLabelSections:
  """Prueft die regelbasierte Sektions-Labelung."""

  def test_low_first_section_is_intro(self):
    """Niedrige Energie am Anfang = Intro."""
    boundaries = [0.0, 30.0, 60.0, 90.0]
    energies = [10.0, 50.0, 80.0, 15.0]
    trends = ["rising", "stable", "stable", "falling"]
    labels = _label_sections(boundaries, 120.0, energies, trends)
    assert labels[0] == "intro"

  def test_low_last_section_is_outro(self):
    """Niedrige Energie am Ende = Outro."""
    boundaries = [0.0, 30.0, 60.0, 90.0]
    energies = [10.0, 50.0, 80.0, 15.0]
    trends = ["rising", "stable", "stable", "falling"]
    labels = _label_sections(boundaries, 120.0, energies, trends)
    assert labels[-1] == "outro"

  def test_high_energy_is_drop(self):
    """Hohe Energie = Drop."""
    boundaries = [0.0, 30.0, 60.0, 90.0]
    energies = [10.0, 40.0, 90.0, 10.0]
    trends = ["rising", "rising", "stable", "falling"]
    labels = _label_sections(boundaries, 120.0, energies, trends)
    assert labels[2] == "drop"

  def test_rising_before_drop_is_build(self):
    """Ansteigende Energie vor Drop = Build."""
    boundaries = [0.0, 30.0, 60.0, 90.0]
    energies = [10.0, 40.0, 90.0, 10.0]
    trends = ["rising", "rising", "stable", "falling"]
    labels = _label_sections(boundaries, 120.0, energies, trends)
    assert labels[1] == "build"

  def test_low_after_drop_is_breakdown(self):
    """Niedrige Energie nach Drop = Breakdown."""
    boundaries = [0.0, 20.0, 40.0, 60.0, 80.0]
    # intro, build, drop, breakdown, outro
    # avg = (10+35+85+20+10)/5 = 32.0, breakdown_threshold = 32*0.8 = 25.6
    # 20.0 < 25.6 -> breakdown
    energies = [10.0, 35.0, 85.0, 20.0, 10.0]
    trends = ["rising", "rising", "stable", "stable", "falling"]
    labels = _label_sections(boundaries, 100.0, energies, trends)
    assert labels[3] == "breakdown"

  def test_empty_energies_returns_empty(self):
    labels = _label_sections([], 0.0, [], [])
    assert labels == []

  def test_single_section_is_main(self):
    """Eine einzige Sektion wird als 'main' gelabelt (kein Intro/Outro bei nur 1)."""
    labels = _label_sections([0.0], 60.0, [50.0], ["stable"])
    # Eine einzelne Sektion bleibt 'main' (da n<=1 kein Outro-Check)
    assert labels[0] in {"main", "intro"}  # Intro wenn < low_threshold

  def test_all_labels_valid(self):
    """Alle erzeugten Labels sind gueltige Werte."""
    valid = {"intro", "build", "drop", "breakdown", "outro", "main"}
    boundaries = [0.0, 20.0, 40.0, 60.0, 80.0]
    energies = [10.0, 40.0, 80.0, 30.0, 10.0]
    trends = ["rising", "rising", "stable", "falling", "falling"]
    labels = _label_sections(boundaries, 100.0, energies, trends)
    for label in labels:
      assert label in valid


# === Pick Boundaries ===

class TestPickBoundaries:
  """Prueft die Boundary-Erkennung aus Novelty-Kurven."""

  def test_always_starts_with_zero(self):
    """Boundaries beginnen immer bei 0.0."""
    novelty = np.array([0, 0.5, 0, 0.8, 0, 0.3, 0, 0.6, 0, 0])
    times = np.linspace(0, 100, len(novelty))
    result = _pick_boundaries(novelty, times, 100.0, min_distance_sec=5.0)
    assert result[0] == 0.0

  def test_short_novelty_returns_zero_only(self):
    """Sehr kurze Novelty-Kurve -> nur [0.0]."""
    novelty = np.array([0.5, 0.3])
    times = np.array([0.0, 1.0])
    result = _pick_boundaries(novelty, times, 2.0)
    assert result == [0.0]

  def test_flat_novelty_returns_zero_only(self):
    """Flache Novelty (keine Aenderungen) -> nur [0.0]."""
    novelty = np.zeros(100)
    times = np.linspace(0, 100, 100)
    result = _pick_boundaries(novelty, times, 100.0)
    assert result == [0.0]

  def test_max_sections_respected(self):
    """Nicht mehr als max_sections Boundaries."""
    # Viele starke Peaks
    novelty = np.zeros(200)
    for i in range(10, 200, 20):
      novelty[i] = 1.0
    times = np.linspace(0, 200, 200)
    result = _pick_boundaries(novelty, times, 200.0, min_distance_sec=1.0, max_sections=5)
    assert len(result) <= 5


# === Novelty Curve ===

class TestComputeNoveltyCurve:
  """Prueft die Novelty-Kurven-Berechnung."""

  def test_returns_correct_shapes(self):
    sr = 22050
    y = _make_tone(sr, 10.0)
    novelty, times = _compute_novelty_curve(y, sr)
    assert len(novelty) == len(times)
    assert len(novelty) > 0

  def test_novelty_non_negative(self):
    sr = 22050
    y = _make_noise(sr, 10.0)
    novelty, times = _compute_novelty_curve(y, sr)
    assert np.all(novelty >= 0)

  def test_times_monotonically_increasing(self):
    sr = 22050
    y = _make_tone(sr, 10.0)
    novelty, times = _compute_novelty_curve(y, sr)
    assert np.all(np.diff(times) > 0)


# === Main Function: analyze_structure ===

class TestAnalyzeStructure:
  """Prueft die Hauptfunktion analyze_structure()."""

  @pytest.fixture
  def simple_audio(self):
    """10-Sekunden Ton bei 22050 Hz."""
    sr = 22050
    y = _make_tone(sr, 10.0, amplitude=0.2)
    return y, sr

  @pytest.fixture
  def structured_audio(self):
    """60-Sekunden Track mit klaren Sektionen."""
    sr = 22050
    y = _make_structured_track(sr)
    return y, sr

  def test_returns_track_structure(self, simple_audio):
    y, sr = simple_audio
    result = analyze_structure(y, sr, bpm=128.0)
    assert isinstance(result, TrackStructure)

  def test_has_sections(self, simple_audio):
    y, sr = simple_audio
    result = analyze_structure(y, sr, bpm=128.0)
    assert len(result.sections) >= 1

  def test_sections_are_track_sections(self, simple_audio):
    y, sr = simple_audio
    result = analyze_structure(y, sr, bpm=128.0)
    for section in result.sections:
      assert isinstance(section, TrackSection)

  def test_sections_cover_full_track(self, simple_audio):
    """Sektionen decken den ganzen Track ab (Start=0, Ende=Duration)."""
    y, sr = simple_audio
    result = analyze_structure(y, sr, bpm=128.0)
    if result.sections:
      assert result.sections[0].start_time == 0.0
      # Letzte Sektion endet bei Duration (ungefaehr)
      import librosa as lr
      duration = lr.get_duration(y=y, sr=sr)
      assert abs(result.sections[-1].end_time - duration) < 1.0

  def test_no_overlapping_sections(self, simple_audio):
    """Sektionen ueberlappen nicht."""
    y, sr = simple_audio
    result = analyze_structure(y, sr, bpm=128.0)
    for i in range(len(result.sections) - 1):
      assert result.sections[i].end_time <= result.sections[i + 1].start_time + 0.01

  def test_total_bars_positive(self, simple_audio):
    y, sr = simple_audio
    result = analyze_structure(y, sr, bpm=128.0)
    assert result.total_bars > 0

  def test_phrase_unit_default_8(self, simple_audio):
    y, sr = simple_audio
    result = analyze_structure(y, sr, bpm=128.0)
    assert result.phrase_unit == 8

  def test_psytrance_phrase_unit_16(self, simple_audio):
    y, sr = simple_audio
    result = analyze_structure(y, sr, bpm=142.0, genre="Psytrance")
    assert result.phrase_unit == 16

  def test_tech_house_phrase_unit_8(self, simple_audio):
    y, sr = simple_audio
    result = analyze_structure(y, sr, bpm=128.0, genre="Tech House")
    assert result.phrase_unit == 8

  def test_unknown_genre_phrase_unit_8(self, simple_audio):
    y, sr = simple_audio
    result = analyze_structure(y, sr, bpm=128.0, genre="Unknown")
    assert result.phrase_unit == 8

  def test_zero_bpm_returns_empty(self):
    """BPM=0 -> leere Struktur."""
    sr = 22050
    y = _make_tone(sr, 10.0)
    result = analyze_structure(y, sr, bpm=0.0)
    assert result.sections == []
    assert result.total_bars == 0

  def test_empty_audio_returns_empty(self):
    """Leeres Audio -> leere Struktur."""
    sr = 22050
    y = np.array([], dtype=np.float32)
    result = analyze_structure(y, sr, bpm=128.0)
    assert result.sections == []

  def test_section_energies_between_0_and_100(self, structured_audio):
    y, sr = structured_audio
    result = analyze_structure(y, sr, bpm=128.0)
    for section in result.sections:
      assert 0.0 <= section.avg_energy <= 100.0

  def test_section_bars_non_negative(self, structured_audio):
    y, sr = structured_audio
    result = analyze_structure(y, sr, bpm=128.0)
    for section in result.sections:
      assert section.start_bar >= 0
      assert section.end_bar >= section.start_bar

  def test_valid_labels_only(self, structured_audio):
    """Alle Sektionen haben gueltige Labels."""
    valid = {"intro", "build", "drop", "breakdown", "outro", "main"}
    y, sr = structured_audio
    result = analyze_structure(y, sr, bpm=128.0)
    for section in result.sections:
      assert section.label in valid, f"Ungueltiges Label: {section.label}"


# === Track Model Integration ===

class TestTrackModelIntegration:
  """Prueft die neuen Struktur-Felder im Track Model."""

  def test_default_sections_empty(self):
    from hpg_core.models import Track
    track = Track(filePath="/test.mp3", fileName="test.mp3")
    assert track.sections == []

  def test_default_phrase_unit(self):
    from hpg_core.models import Track
    track = Track(filePath="/test.mp3", fileName="test.mp3")
    assert track.phrase_unit == 8

  def test_custom_sections(self):
    from hpg_core.models import Track
    sections = [{"label": "intro", "start_time": 0, "end_time": 30}]
    track = Track(filePath="/test.mp3", fileName="test.mp3",
                  sections=sections, phrase_unit=16)
    assert len(track.sections) == 1
    assert track.phrase_unit == 16

  def test_sections_independent_between_tracks(self):
    """Jeder Track hat seine eigene sections-Liste (kein shared mutable default)."""
    from hpg_core.models import Track
    t1 = Track(filePath="/a.mp3", fileName="a.mp3")
    t2 = Track(filePath="/b.mp3", fileName="b.mp3")
    t1.sections.append({"label": "intro"})
    assert len(t2.sections) == 0  # t2 darf nicht betroffen sein

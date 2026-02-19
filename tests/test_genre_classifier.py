"""
Tests fuer hpg_core.genre_classifier - Genre-Erkennung fuer DJ Brain.
Testet ID3-Matching, Audio-Feature-Scoring und Klassifikations-Logik.
"""
import pytest
import numpy as np

from hpg_core.genre_classifier import (
  GenreClassification,
  GenreFeatures,
  GenreProfile,
  GENRE_PROFILES,
  ID3_GENRE_MAP,
  match_id3_genre,
  classify_genre,
  extract_genre_features,
  _score_range,
  _score_genre,
  MIN_CONFIDENCE,
)


# === ID3 Genre Tag Matching ===

class TestMatchId3Genre:
  """Prueft die ID3-Tag-basierte Genre-Erkennung."""

  def test_direct_match_psytrance(self):
    assert match_id3_genre("psytrance") == "Psytrance"

  def test_direct_match_tech_house(self):
    assert match_id3_genre("tech house") == "Tech House"

  def test_direct_match_progressive(self):
    assert match_id3_genre("progressive house") == "Progressive"

  def test_direct_match_melodic_techno(self):
    assert match_id3_genre("melodic techno") == "Melodic Techno"

  def test_case_insensitive(self):
    assert match_id3_genre("PSYTRANCE") == "Psytrance"
    assert match_id3_genre("Tech House") == "Tech House"
    assert match_id3_genre("PROGRESSIVE") == "Progressive"

  def test_whitespace_handling(self):
    assert match_id3_genre("  psytrance  ") == "Psytrance"
    assert match_id3_genre(" tech house ") == "Tech House"

  def test_substring_match(self):
    """ID3-Tags wie 'Psytrance / Full On' sollen matchen."""
    assert match_id3_genre("Psytrance / Full On") == "Psytrance"
    assert match_id3_genre("Progressive House (Deep)") == "Progressive"

  def test_goa_trance_maps_to_psytrance(self):
    assert match_id3_genre("goa trance") == "Psytrance"
    assert match_id3_genre("goa") == "Psytrance"

  def test_unknown_returns_none(self):
    assert match_id3_genre("Unknown") is None

  def test_empty_returns_none(self):
    assert match_id3_genre("") is None
    assert match_id3_genre(None) is None

  def test_unrecognized_genre_returns_none(self):
    assert match_id3_genre("Reggae") is None
    assert match_id3_genre("Hip Hop") is None
    assert match_id3_genre("Classical") is None

  def test_all_psytrance_variants(self):
    variants = [
      "psytrance", "psy trance", "psy-trance", "psychedelic trance",
      "goa trance", "goa", "full on", "full-on", "dark psy",
      "dark psytrance", "forest", "hi-tech", "hitech",
    ]
    for v in variants:
      assert match_id3_genre(v) == "Psytrance", f"'{v}' sollte Psytrance sein"

  def test_all_tech_house_variants(self):
    variants = ["tech house", "tech-house", "techhouse", "minimal tech house", "bass house"]
    for v in variants:
      assert match_id3_genre(v) == "Tech House", f"'{v}' sollte Tech House sein"

  def test_all_progressive_variants(self):
    variants = [
      "progressive", "progressive house", "progressive trance",
      "prog house", "prog trance", "prog", "deep progressive",
    ]
    for v in variants:
      assert match_id3_genre(v) == "Progressive", f"'{v}' sollte Progressive sein"

  def test_all_melodic_techno_variants(self):
    variants = [
      "melodic techno", "melodic house & techno", "melodic house",
      "melodic house/techno", "indie dance", "organic house", "afro house",
    ]
    for v in variants:
      assert match_id3_genre(v) == "Melodic Techno", f"'{v}' sollte Melodic Techno sein"

  def test_all_techno_variants(self):
    variants = [
      "techno", "hard techno", "industrial techno", "acid techno",
      "detroit techno", "peak time techno", "peak time / driving",
      "raw techno", "warehouse techno",
    ]
    for v in variants:
      assert match_id3_genre(v) == "Techno", f"'{v}' sollte Techno sein"

  def test_all_deep_house_variants(self):
    variants = [
      "deep house", "deep-house", "deephouse", "soulful house",
      "lounge house", "deep tech",
    ]
    for v in variants:
      assert match_id3_genre(v) == "Deep House", f"'{v}' sollte Deep House sein"

  def test_all_trance_variants(self):
    variants = [
      "trance", "uplifting trance", "vocal trance", "epic trance",
      "dream trance", "hard trance", "eurotrance",
    ]
    for v in variants:
      assert match_id3_genre(v) == "Trance", f"'{v}' sollte Trance sein"

  def test_all_dnb_variants(self):
    variants = [
      "drum & bass", "drum and bass", "dnb", "d&b",
      "jungle", "liquid dnb", "liquid funk", "neurofunk",
      "jump up", "breakbeat",
    ]
    for v in variants:
      assert match_id3_genre(v) == "Drum & Bass", f"'{v}' sollte Drum & Bass sein"

  def test_all_minimal_variants(self):
    variants = [
      "minimal", "minimal techno", "micro house", "clicks & cuts",
      "glitch", "minimal house",
    ]
    for v in variants:
      assert match_id3_genre(v) == "Minimal", f"'{v}' sollte Minimal sein"

  def test_direct_match_techno(self):
    assert match_id3_genre("techno") == "Techno"

  def test_direct_match_deep_house(self):
    assert match_id3_genre("deep house") == "Deep House"

  def test_direct_match_trance(self):
    assert match_id3_genre("trance") == "Trance"

  def test_direct_match_dnb(self):
    assert match_id3_genre("drum & bass") == "Drum & Bass"

  def test_direct_match_minimal(self):
    assert match_id3_genre("minimal") == "Minimal"


# === Genre Profiles ===

class TestGenreProfiles:
  """Prueft die Genre-Profile auf Konsistenz."""

  def test_all_nine_genres_defined(self):
    expected = {
      "Psytrance", "Tech House", "Progressive", "Melodic Techno",
      "Techno", "Deep House", "Trance", "Drum & Bass", "Minimal",
    }
    assert set(GENRE_PROFILES.keys()) == expected

  def test_bpm_ranges_valid(self):
    for name, profile in GENRE_PROFILES.items():
      assert profile.bpm_range[0] < profile.bpm_range[1], (
        f"{name}: BPM min >= max"
      )
      assert profile.bpm_range[0] >= 100, f"{name}: BPM min zu niedrig"
      assert profile.bpm_range[1] <= 200, f"{name}: BPM max zu hoch"

  def test_bpm_center_within_range(self):
    for name, profile in GENRE_PROFILES.items():
      assert profile.bpm_range[0] <= profile.bpm_center <= profile.bpm_range[1], (
        f"{name}: BPM center {profile.bpm_center} ausserhalb Range {profile.bpm_range}"
      )

  def test_dnb_fastest(self):
    """Drum & Bass hat den hoechsten BPM-Bereich."""
    dnb = GENRE_PROFILES["Drum & Bass"]
    for name, profile in GENRE_PROFILES.items():
      if name != "Drum & Bass":
        assert dnb.bpm_center > profile.bpm_center, (
          f"DnB BPM center ({dnb.bpm_center}) sollte hoeher als {name} ({profile.bpm_center}) sein"
        )

  def test_spectral_ranges_positive(self):
    for name, profile in GENRE_PROFILES.items():
      assert profile.spectral_centroid_range[0] > 0, f"{name}: centroid min <= 0"
      assert profile.spectral_centroid_range[1] > profile.spectral_centroid_range[0]


# === Scoring Functions ===

class TestScoreRange:
  """Prueft die Range-Scoring-Funktion."""

  def test_center_value_scores_high(self):
    score = _score_range(142.0, 135.0, 150.0, center=142.0)
    assert score >= 0.95

  def test_edge_value_scores_moderate(self):
    score = _score_range(135.0, 135.0, 150.0)
    assert 0.5 < score < 1.0

  def test_outside_value_scores_low(self):
    score = _score_range(100.0, 135.0, 150.0)
    assert score < 0.5

  def test_far_outside_value_near_zero(self):
    score = _score_range(50.0, 135.0, 150.0)
    assert score < 0.2

  def test_exact_center_without_explicit_center(self):
    """Ohne explizites center wird Mittelpunkt genommen."""
    score = _score_range(142.5, 135.0, 150.0)
    assert score >= 0.95

  def test_returns_between_0_and_1(self):
    for value in [0, 50, 100, 142, 200, 500]:
      score = _score_range(value, 135.0, 150.0)
      assert 0.0 <= score <= 1.0


# === Genre Scoring ===

class TestScoreGenre:
  """Prueft die gewichtete Genre-Scoring-Funktion."""

  def _make_features(self, bpm=142, centroid=3000, onset=3.5, flatness=0.04,
                     rms_var=0.3, bass=70):
    """Erzeugt GenreFeatures mit gegebenen Werten."""
    return GenreFeatures(
      bpm=bpm,
      spectral_centroid_mean=centroid,
      spectral_centroid_std=500.0,
      spectral_rolloff_mean=6000.0,
      spectral_flatness_mean=flatness,
      onset_rate=onset,
      rms_variance=rms_var,
      bass_ratio=bass,
      mfcc_means=np.zeros(13),
    )

  def test_psytrance_features_score_highest_for_psytrance(self):
    """Typische Psytrance-Features sollten am besten zu Psytrance passen."""
    features = self._make_features(bpm=142, centroid=3200, onset=3.5, flatness=0.04, rms_var=0.3, bass=70)
    scores = {name: _score_genre(features, profile) for name, profile in GENRE_PROFILES.items()}
    best = max(scores, key=scores.get)
    assert best == "Psytrance", f"Erwartet Psytrance, bekommen {best}. Scores: {scores}"

  def test_tech_house_features_score_highest_for_tech_house(self):
    """Typische Tech House-Features sollten am besten zu Tech House passen."""
    features = self._make_features(bpm=128, centroid=2500, onset=5.5, flatness=0.10, rms_var=0.12, bass=50)
    scores = {name: _score_genre(features, profile) for name, profile in GENRE_PROFILES.items()}
    best = max(scores, key=scores.get)
    assert best == "Tech House", f"Erwartet Tech House, bekommen {best}. Scores: {scores}"

  def test_progressive_features_score_highest_for_progressive(self):
    """Typische Progressive-Features sollten am besten zu Progressive passen."""
    features = self._make_features(bpm=126, centroid=2000, onset=2.5, flatness=0.07, rms_var=0.10, bass=45)
    scores = {name: _score_genre(features, profile) for name, profile in GENRE_PROFILES.items()}
    best = max(scores, key=scores.get)
    assert best == "Progressive", f"Erwartet Progressive, bekommen {best}. Scores: {scores}"

  def test_melodic_techno_features_score_highest_for_melodic_techno(self):
    """Typische Melodic Techno-Features sollten am besten zu Melodic Techno passen."""
    features = self._make_features(bpm=125, centroid=2600, onset=4.0, flatness=0.05, rms_var=0.20, bass=50)
    scores = {name: _score_genre(features, profile) for name, profile in GENRE_PROFILES.items()}
    best = max(scores, key=scores.get)
    assert best == "Melodic Techno", f"Erwartet Melodic Techno, bekommen {best}. Scores: {scores}"

  def test_techno_features_score_highest_for_techno(self):
    """Typische Techno-Features sollten am besten zu Techno passen."""
    features = self._make_features(bpm=138, centroid=2800, onset=6.0, flatness=0.12, rms_var=0.15, bass=75)
    scores = {name: _score_genre(features, profile) for name, profile in GENRE_PROFILES.items()}
    best = max(scores, key=scores.get)
    assert best == "Techno", f"Erwartet Techno, bekommen {best}. Scores: {scores}"

  def test_deep_house_features_score_highest_for_deep_house(self):
    """Typische Deep House-Features sollten am besten zu Deep House passen."""
    features = self._make_features(bpm=123, centroid=1800, onset=3.0, flatness=0.06, rms_var=0.08, bass=45)
    scores = {name: _score_genre(features, profile) for name, profile in GENRE_PROFILES.items()}
    best = max(scores, key=scores.get)
    assert best == "Deep House", f"Erwartet Deep House, bekommen {best}. Scores: {scores}"

  def test_trance_features_score_highest_for_trance(self):
    """Typische Trance-Features sollten am besten zu Trance passen."""
    features = self._make_features(bpm=138, centroid=3500, onset=3.0, flatness=0.03, rms_var=0.35, bass=60)
    scores = {name: _score_genre(features, profile) for name, profile in GENRE_PROFILES.items()}
    best = max(scores, key=scores.get)
    assert best == "Trance", f"Erwartet Trance, bekommen {best}. Scores: {scores}"

  def test_dnb_features_score_highest_for_dnb(self):
    """Typische DnB-Features sollten am besten zu Drum & Bass passen."""
    features = self._make_features(bpm=174, centroid=3000, onset=8.0, flatness=0.08, rms_var=0.30, bass=80)
    scores = {name: _score_genre(features, profile) for name, profile in GENRE_PROFILES.items()}
    best = max(scores, key=scores.get)
    assert best == "Drum & Bass", f"Erwartet Drum & Bass, bekommen {best}. Scores: {scores}"

  def test_minimal_features_score_highest_for_minimal(self):
    """Typische Minimal-Features sollten am besten zu Minimal passen."""
    features = self._make_features(bpm=126, centroid=1500, onset=2.5, flatness=0.07, rms_var=0.05, bass=40)
    scores = {name: _score_genre(features, profile) for name, profile in GENRE_PROFILES.items()}
    best = max(scores, key=scores.get)
    assert best == "Minimal", f"Erwartet Minimal, bekommen {best}. Scores: {scores}"

  def test_scores_between_0_and_1(self):
    features = self._make_features()
    for name, profile in GENRE_PROFILES.items():
      score = _score_genre(features, profile)
      assert 0.0 <= score <= 1.0, f"{name}: Score {score} ausserhalb 0-1"


# === Main Classification Function ===

class TestClassifyGenre:
  """Prueft die Hauptfunktion classify_genre()."""

  @pytest.fixture
  def audio_signal(self):
    """Erzeugt ein einfaches 10-Sekunden Mono-Signal."""
    sr = 22050
    duration = 10.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Einfacher Ton mit etwas Rauschen
    y = 0.3 * np.sin(2 * np.pi * 440 * t) + 0.05 * np.random.randn(len(t))
    return y.astype(np.float32), sr

  def test_id3_override_psytrance(self, audio_signal):
    """ID3-Tag 'psytrance' wird direkt uebernommen."""
    y, sr = audio_signal
    result = classify_genre(y, sr, bpm=142.0, bass_intensity=70, id3_genre="psytrance")
    assert result.genre == "Psytrance"
    assert result.confidence == 1.0
    assert result.source == "id3_tag"

  def test_id3_override_tech_house(self, audio_signal):
    y, sr = audio_signal
    result = classify_genre(y, sr, bpm=128.0, bass_intensity=50, id3_genre="Tech House")
    assert result.genre == "Tech House"
    assert result.confidence == 1.0
    assert result.source == "id3_tag"

  def test_id3_override_progressive(self, audio_signal):
    y, sr = audio_signal
    result = classify_genre(y, sr, bpm=126.0, bass_intensity=45, id3_genre="Progressive House")
    assert result.genre == "Progressive"
    assert result.confidence == 1.0

  def test_id3_override_melodic_techno(self, audio_signal):
    y, sr = audio_signal
    result = classify_genre(y, sr, bpm=125.0, bass_intensity=50, id3_genre="Melodic Techno")
    assert result.genre == "Melodic Techno"
    assert result.confidence == 1.0

  def test_id3_override_techno(self, audio_signal):
    y, sr = audio_signal
    result = classify_genre(y, sr, bpm=138.0, bass_intensity=75, id3_genre="techno")
    assert result.genre == "Techno"
    assert result.confidence == 1.0
    assert result.source == "id3_tag"

  def test_id3_override_deep_house(self, audio_signal):
    y, sr = audio_signal
    result = classify_genre(y, sr, bpm=123.0, bass_intensity=45, id3_genre="deep house")
    assert result.genre == "Deep House"
    assert result.confidence == 1.0
    assert result.source == "id3_tag"

  def test_id3_override_trance(self, audio_signal):
    y, sr = audio_signal
    result = classify_genre(y, sr, bpm=138.0, bass_intensity=60, id3_genre="trance")
    assert result.genre == "Trance"
    assert result.confidence == 1.0
    assert result.source == "id3_tag"

  def test_id3_override_dnb(self, audio_signal):
    y, sr = audio_signal
    result = classify_genre(y, sr, bpm=174.0, bass_intensity=80, id3_genre="drum & bass")
    assert result.genre == "Drum & Bass"
    assert result.confidence == 1.0
    assert result.source == "id3_tag"

  def test_id3_override_minimal(self, audio_signal):
    y, sr = audio_signal
    result = classify_genre(y, sr, bpm=126.0, bass_intensity=40, id3_genre="minimal")
    assert result.genre == "Minimal"
    assert result.confidence == 1.0
    assert result.source == "id3_tag"

  def test_unknown_id3_triggers_audio_analysis(self, audio_signal):
    """Bei 'Unknown' ID3-Tag wird Audio-Analyse gemacht."""
    y, sr = audio_signal
    result = classify_genre(y, sr, bpm=142.0, bass_intensity=70, id3_genre="Unknown")
    assert result.source == "audio_analysis"
    assert result.genre in {
      "Psytrance", "Tech House", "Progressive", "Melodic Techno",
      "Techno", "Deep House", "Trance", "Drum & Bass", "Minimal", "Unknown",
    }

  def test_no_id3_triggers_audio_analysis(self, audio_signal):
    y, sr = audio_signal
    result = classify_genre(y, sr, bpm=128.0, bass_intensity=50)
    assert result.source == "audio_analysis"

  def test_result_has_scores_dict(self, audio_signal):
    """Audio-Analyse liefert Scores fuer alle Genres."""
    y, sr = audio_signal
    result = classify_genre(y, sr, bpm=128.0, bass_intensity=50, id3_genre="Unknown")
    if result.source == "audio_analysis" and result.genre != "Unknown":
      assert len(result.scores) == 9
      for genre_name in [
        "Psytrance", "Tech House", "Progressive", "Melodic Techno",
        "Techno", "Deep House", "Trance", "Drum & Bass", "Minimal",
      ]:
        assert genre_name in result.scores

  def test_confidence_between_0_and_1(self, audio_signal):
    y, sr = audio_signal
    result = classify_genre(y, sr, bpm=128.0, bass_intensity=50)
    assert 0.0 <= result.confidence <= 1.0

  def test_unrecognized_id3_falls_to_audio(self, audio_signal):
    """Unbekanntes Genre-Tag fuehrt zu Audio-Analyse."""
    y, sr = audio_signal
    result = classify_genre(y, sr, bpm=142.0, bass_intensity=70, id3_genre="Reggae")
    assert result.source == "audio_analysis"


# === GenreClassification Dataclass ===

class TestGenreClassification:
  """Prueft die GenreClassification Datenstruktur."""

  def test_default_scores_empty(self):
    gc = GenreClassification(genre="Psytrance", confidence=0.9, source="audio_analysis")
    assert gc.scores == {}

  def test_with_scores(self):
    scores = {"Psytrance": 0.8, "Tech House": 0.3}
    gc = GenreClassification(genre="Psytrance", confidence=0.8, source="audio_analysis", scores=scores)
    assert gc.scores["Psytrance"] == 0.8

  def test_id3_source(self):
    gc = GenreClassification(genre="Tech House", confidence=1.0, source="id3_tag")
    assert gc.source == "id3_tag"
    assert gc.confidence == 1.0


# === Track Model Integration ===

class TestTrackGenreFields:
  """Prueft die neuen Genre-Felder im Track Model."""

  def test_default_genre_fields(self):
    from hpg_core.models import Track
    track = Track(filePath="/test.mp3", fileName="test.mp3")
    assert track.detected_genre == "Unknown"
    assert track.genre_confidence == 0.0
    assert track.genre_source == ""

  def test_custom_genre_fields(self):
    from hpg_core.models import Track
    track = Track(
      filePath="/test.mp3", fileName="test.mp3",
      detected_genre="Psytrance",
      genre_confidence=0.85,
      genre_source="audio_analysis",
    )
    assert track.detected_genre == "Psytrance"
    assert track.genre_confidence == 0.85
    assert track.genre_source == "audio_analysis"

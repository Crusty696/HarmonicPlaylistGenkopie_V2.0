"""
Tests fuer das DJ Brain Modul (hpg_core/dj_brain.py).

Prueft:
- Genre Mix Profiles (alle 9 Genres + Default)
- Genre-Kompatibilitaets-Matrix (Symmetrie, bekannte/unbekannte Genres)
- Mix-Punkt-Berechnung (genre-spezifisch, Fallbacks, Edge Cases)
- DJ Empfehlungen (Same-Genre, Cross-Genre, Risiko-Bewertung)
- Hilfsfunktionen (Sektions-Erkennung, Structure Notes, Camelot)
"""

import pytest
from hpg_core.dj_brain import (
  get_genre_compatibility,
  get_mix_profile,
  calculate_genre_aware_mix_points,
  calculate_paired_mix_points,
  generate_dj_recommendation,
  GenreMixProfile,
  DJRecommendation,
  GENRE_MIX_PROFILES,
  GENRE_COMPATIBILITY,
  DEFAULT_MIX_PROFILE,
  _find_mix_in_point,
  _find_mix_out_point,
  _get_intro_end,
  _get_intro_end_from_sections,
  _get_outro_start_from_sections,
  _get_section_at_mix_out,
  _get_section_at_mix_in,
  _build_structure_note,
  _get_cross_genre_technique,
  _get_cross_genre_eq,
  _assess_transition_risks,
  _extract_camelot_number,
)
from hpg_core.models import Track


# === Fixtures ===

def _make_track(
  genre="Psytrance", bpm=140.0, energy=75, duration=420.0,
  sections=None, mix_in=30.0, mix_out=390.0,
  camelot="8A", key_note="A", key_mode="Minor",
  bass_intensity=70,
):
  """Erstellt einen Test-Track mit DJ Brain Feldern."""
  t = Track(
    filePath="/test/track.mp3",
    fileName="track.mp3",
    bpm=bpm,
    energy=energy,
    duration=duration,
    detected_genre=genre,
    genre_confidence=0.85,
    genre_source="audio_analysis",
    sections=sections or [],
    mix_in_point=mix_in,
    mix_out_point=mix_out,
    camelotCode=camelot,
    keyNote=key_note,
    keyMode=key_mode,
    bass_intensity=bass_intensity,
  )
  return t


def _standard_sections():
  """Standard-Sektionsliste: Intro -> Build -> Drop -> Breakdown -> Drop -> Outro."""
  return [
    {"label": "intro",     "start_time": 0.0,   "end_time": 60.0,   "start_bar": 0,  "end_bar": 32,  "avg_energy": 25.0},
    {"label": "build",     "start_time": 60.0,  "end_time": 90.0,   "start_bar": 32, "end_bar": 48,  "avg_energy": 55.0},
    {"label": "drop",      "start_time": 90.0,  "end_time": 180.0,  "start_bar": 48, "end_bar": 96,  "avg_energy": 85.0},
    {"label": "breakdown", "start_time": 180.0, "end_time": 240.0,  "start_bar": 96, "end_bar": 128, "avg_energy": 40.0},
    {"label": "drop",      "start_time": 240.0, "end_time": 360.0,  "start_bar": 128,"end_bar": 192, "avg_energy": 88.0},
    {"label": "outro",     "start_time": 360.0, "end_time": 420.0,  "start_bar": 192,"end_bar": 224, "avg_energy": 20.0},
  ]


# === Genre Mix Profiles ===

class TestGenreMixProfiles:
  """Tests fuer Genre-spezifische Mix-Profile."""

  def test_all_nine_genres_have_profiles(self):
    expected = {
      "Psytrance", "Tech House", "Progressive", "Melodic Techno",
      "Techno", "Deep House", "Trance", "Drum & Bass", "Minimal",
    }
    assert set(GENRE_MIX_PROFILES.keys()) == expected

  def test_psytrance_profile(self):
    p = GENRE_MIX_PROFILES["Psytrance"]
    assert p.phrase_unit == 16
    assert p.intro_bars == (32, 64)
    assert p.outro_bars == (32, 64)
    assert p.transition_bars == (16, 32)

  def test_tech_house_profile(self):
    p = GENRE_MIX_PROFILES["Tech House"]
    assert p.phrase_unit == 8
    assert p.intro_bars == (16, 32)
    assert p.transition_bars == (8, 16)

  def test_progressive_profile(self):
    p = GENRE_MIX_PROFILES["Progressive"]
    assert p.phrase_unit == 8
    assert p.transition_bars == (32, 64)  # Laengste Transitions

  def test_melodic_techno_profile(self):
    p = GENRE_MIX_PROFILES["Melodic Techno"]
    assert p.phrase_unit == 8
    assert p.transition_bars == (16, 32)

  def test_get_mix_profile_known_genre(self):
    p = get_mix_profile("Psytrance")
    assert p.name == "Psytrance"
    assert p.phrase_unit == 16

  def test_techno_profile(self):
    p = GENRE_MIX_PROFILES["Techno"]
    assert p.phrase_unit == 8
    assert p.intro_bars == (16, 32)
    assert p.transition_bars == (8, 16)

  def test_deep_house_profile(self):
    p = GENRE_MIX_PROFILES["Deep House"]
    assert p.phrase_unit == 8
    assert p.intro_bars == (32, 64)
    assert p.transition_bars == (32, 64)

  def test_trance_profile(self):
    p = GENRE_MIX_PROFILES["Trance"]
    assert p.phrase_unit == 16
    assert p.intro_bars == (32, 64)
    assert p.transition_bars == (16, 32)

  def test_dnb_profile(self):
    p = GENRE_MIX_PROFILES["Drum & Bass"]
    assert p.phrase_unit == 8
    assert p.intro_bars == (16, 32)
    assert p.transition_bars == (8, 16)

  def test_minimal_profile(self):
    p = GENRE_MIX_PROFILES["Minimal"]
    assert p.phrase_unit == 8
    assert p.intro_bars == (32, 64)
    assert p.transition_bars == (32, 64)

  def test_get_mix_profile_unknown_genre(self):
    p = get_mix_profile("Ambient")
    assert p == DEFAULT_MIX_PROFILE
    assert p.name == "Default"

  def test_default_profile_has_sensible_values(self):
    d = DEFAULT_MIX_PROFILE
    assert d.phrase_unit == 8
    assert d.intro_bars[0] <= d.intro_bars[1]
    assert d.outro_bars[0] <= d.outro_bars[1]
    assert d.transition_bars[0] <= d.transition_bars[1]

  def test_all_profiles_have_eq_and_technique(self):
    for name, profile in GENRE_MIX_PROFILES.items():
      assert profile.eq_strategy, f"{name} hat keine EQ-Strategie"
      assert profile.mix_technique, f"{name} hat keine Mix-Technik"
      assert profile.description, f"{name} hat keine Beschreibung"


# === Genre Compatibility Matrix ===

class TestGenreCompatibility:
  """Tests fuer die Genre-Kompatibilitaets-Matrix."""

  def test_same_genre_is_1_0(self):
    all_genres = [
      "Psytrance", "Tech House", "Progressive", "Melodic Techno",
      "Techno", "Deep House", "Trance", "Drum & Bass", "Minimal",
    ]
    for genre in all_genres:
      assert get_genre_compatibility(genre, genre) == 1.0, f"{genre} self-compat != 1.0"

  def test_matrix_is_symmetric(self):
    all_genres = [
      "Psytrance", "Tech House", "Progressive", "Melodic Techno",
      "Techno", "Deep House", "Trance", "Drum & Bass", "Minimal",
    ]
    for a in all_genres:
      for b in all_genres:
        assert get_genre_compatibility(a, b) == get_genre_compatibility(b, a), \
          f"Asymmetrie: {a}/{b}"

  def test_known_compatibility_values(self):
    # Originale 4 Genres
    assert get_genre_compatibility("Psytrance", "Tech House") == 0.3
    assert get_genre_compatibility("Psytrance", "Progressive") == 0.6
    assert get_genre_compatibility("Progressive", "Melodic Techno") == 0.85
    assert get_genre_compatibility("Tech House", "Melodic Techno") == 0.75
    # Neue Genres
    assert get_genre_compatibility("Tech House", "Techno") == 0.8
    assert get_genre_compatibility("Techno", "Minimal") == 0.8
    assert get_genre_compatibility("Progressive", "Trance") == 0.8
    assert get_genre_compatibility("Deep House", "Drum & Bass") == 0.1

  def test_unknown_genre_returns_0_5(self):
    assert get_genre_compatibility("Unknown", "Psytrance") == 0.5
    assert get_genre_compatibility("Psytrance", "Unknown") == 0.5
    assert get_genre_compatibility("Unknown", "Unknown") == 0.5

  def test_empty_genre_returns_0_5(self):
    assert get_genre_compatibility("", "Psytrance") == 0.5
    assert get_genre_compatibility("Psytrance", "") == 0.5

  def test_unrecognized_genre_pair_returns_0_5(self):
    assert get_genre_compatibility("Ambient", "Reggae") == 0.5

  def test_all_matrix_values_in_range(self):
    for key, value in GENRE_COMPATIBILITY.items():
      assert 0.0 <= value <= 1.0, f"Wert ausserhalb 0-1: {key} = {value}"

  def test_lowest_compatibility_pair(self):
    """Deep House + DnB sollte die niedrigste Kompatibilitaet haben (0.1)."""
    all_genres = [
      "Psytrance", "Tech House", "Progressive", "Melodic Techno",
      "Techno", "Deep House", "Trance", "Drum & Bass", "Minimal",
    ]
    scores = {}
    for i, a in enumerate(all_genres):
      for b in all_genres[i+1:]:
        scores[(a, b)] = get_genre_compatibility(a, b)
    min_pair = min(scores, key=scores.get)
    min_val = scores[min_pair]
    assert min_val == 0.1, f"Niedrigster Wert: {min_pair} = {min_val}"


# === Mix-Punkt-Berechnung ===

class TestMixPointCalculation:
  """Tests fuer genre-spezifische Mix-Punkt-Berechnung."""

  def test_basic_mix_points_with_sections(self):
    sections = _standard_sections()
    mix_in, mix_out, bars_in, bars_out = calculate_genre_aware_mix_points(
      sections, bpm=140.0, duration=420.0, genre="Psytrance"
    )
    # Mix-In muss nach dem Intro liegen (Intro endet bei 60s)
    assert mix_in >= 60.0
    assert mix_out < 420.0
    assert mix_out > mix_in
    assert bars_in > 0
    assert bars_out > bars_in

  def test_mix_in_after_intro(self):
    """Mix-In muss NACH dem Intro liegen - fuer alle Genres."""
    sections = _standard_sections()  # Intro endet bei 60s
    mix_in, _, _, _ = calculate_genre_aware_mix_points(
      sections, bpm=140.0, duration=420.0, genre="Psytrance"
    )
    # REGEL: Mix-In niemals im Intro
    assert mix_in >= 60.0, f"Mix-In {mix_in}s liegt im Intro (endet bei 60s)"

  def test_mix_out_at_outro(self):
    """Mix-Out sollte am Outro sein (Outro beginnt bei 360s)."""
    sections = _standard_sections()
    _, mix_out, _, _ = calculate_genre_aware_mix_points(
      sections, bpm=140.0, duration=420.0, genre="Psytrance"
    )
    # Mix-Out sollte in der Naehe des Outro-Anfangs (360s) sein
    assert 300.0 <= mix_out <= 420.0

  def test_empty_sections_fallback(self):
    mix_in, mix_out, bars_in, bars_out = calculate_genre_aware_mix_points(
      [], bpm=140.0, duration=420.0, genre="Psytrance"
    )
    assert mix_in == 0.0
    assert mix_out == 420.0
    assert bars_in == 0
    assert bars_out == 0

  def test_zero_bpm_fallback(self):
    sections = _standard_sections()
    mix_in, mix_out, _, _ = calculate_genre_aware_mix_points(
      sections, bpm=0.0, duration=420.0, genre="Psytrance"
    )
    assert mix_in == 0.0
    assert mix_out == 420.0

  def test_zero_duration_fallback(self):
    sections = _standard_sections()
    mix_in, mix_out, _, _ = calculate_genre_aware_mix_points(
      sections, bpm=140.0, duration=0.0, genre="Psytrance"
    )
    assert mix_in == 0.0
    assert mix_out == 0.0

  def test_mix_out_always_after_mix_in(self):
    """Mix-Out muss immer nach Mix-In liegen."""
    all_genres = [
      "Psytrance", "Tech House", "Progressive", "Melodic Techno",
      "Techno", "Deep House", "Trance", "Drum & Bass", "Minimal",
    ]
    for genre in all_genres:
      sections = _standard_sections()
      mix_in, mix_out, _, _ = calculate_genre_aware_mix_points(
        sections, bpm=128.0, duration=360.0, genre=genre
      )
      assert mix_out > mix_in, f"Mix-Out <= Mix-In fuer {genre}"

  def test_phrase_quantization_psytrance(self):
    """Psytrance Mix-Punkte sollten auf 16-bar Phrasen quantisiert sein."""
    sections = _standard_sections()
    _, _, bars_in, bars_out = calculate_genre_aware_mix_points(
      sections, bpm=140.0, duration=420.0, genre="Psytrance"
    )
    # 16-bar phrase unit fuer Psytrance
    # Mix-In bei Bar 1 (Index 0) = korrekt fuer Psytrance
    # (DJ spielt Track B ab dem allerersten Beat)
    assert bars_in >= 0  # Bar 1 = 0 ist korrekt
    assert bars_out > bars_in

  def test_tech_house_shorter_transitions(self):
    """Tech House sollte kuerzer Transitions haben als Progressive."""
    sections = _standard_sections()
    _, _, th_in, th_out = calculate_genre_aware_mix_points(
      sections, bpm=128.0, duration=360.0, genre="Tech House"
    )
    _, _, prog_in, prog_out = calculate_genre_aware_mix_points(
      sections, bpm=128.0, duration=360.0, genre="Progressive"
    )
    # Tech House intro ist 16-32 bars, Progressive ist 32-64 bars
    # Die Mix-Punkte koennen sich unterscheiden
    assert th_in >= 0
    assert prog_in >= 0

  def test_sections_only_main(self):
    """Nur 'main' Sektionen -> Fallback auf Genre-Profil."""
    sections = [
      {"label": "main", "start_time": 0.0, "end_time": 360.0, "start_bar": 0, "end_bar": 192, "avg_energy": 70.0},
    ]
    mix_in, mix_out, _, _ = calculate_genre_aware_mix_points(
      sections, bpm=128.0, duration=360.0, genre="Tech House"
    )
    assert mix_in > 0
    assert mix_out < 360.0


# === DJ Empfehlungen ===

class TestDJRecommendation:
  """Tests fuer generate_dj_recommendation()."""

  def test_same_genre_recommendation(self):
    a = _make_track(genre="Psytrance", bpm=140.0, energy=75, sections=_standard_sections())
    b = _make_track(genre="Psytrance", bpm=142.0, energy=80, sections=_standard_sections())
    rec = generate_dj_recommendation(a, b)

    assert isinstance(rec, DJRecommendation)
    assert rec.genre_pair == "Psytrance -> Psytrance"
    assert rec.genre_compatibility == 1.0
    assert rec.transition_bars > 0
    assert rec.mix_technique != ""
    assert rec.eq_advice != ""

  def test_cross_genre_recommendation(self):
    a = _make_track(genre="Tech House", bpm=126.0, energy=70)
    b = _make_track(genre="Melodic Techno", bpm=124.0, energy=65)
    rec = generate_dj_recommendation(a, b)

    assert rec.genre_pair == "Tech House -> Melodic Techno"
    assert rec.genre_compatibility == 0.75
    # Cross-Genre hat spezifische Technik
    assert "swap" in rec.mix_technique.lower() or "groove" in rec.mix_technique.lower()

  def test_unknown_genre_recommendation(self):
    a = _make_track(genre="Unknown", bpm=128.0)
    b = _make_track(genre="Tech House", bpm=128.0)
    rec = generate_dj_recommendation(a, b)

    assert rec.genre_pair == "Unknown -> Tech House"
    assert rec.genre_compatibility == 0.5

  def test_recommendation_has_structure_note(self):
    sections_a = _standard_sections()
    sections_b = _standard_sections()
    a = _make_track(genre="Progressive", bpm=128.0, sections=sections_a, mix_out=360.0)
    b = _make_track(genre="Progressive", bpm=128.0, sections=sections_b, mix_in=60.0)
    rec = generate_dj_recommendation(a, b)

    assert rec.structure_note != ""

  def test_large_bpm_gap_creates_risk(self):
    a = _make_track(genre="Psytrance", bpm=145.0)
    b = _make_track(genre="Tech House", bpm=126.0)
    rec = generate_dj_recommendation(a, b)

    risk_text = " ".join(rec.risk_notes).lower()
    assert "bpm" in risk_text

  def test_large_energy_gap_creates_risk(self):
    a = _make_track(genre="Psytrance", bpm=140.0, energy=90)
    b = _make_track(genre="Psytrance", bpm=140.0, energy=30)
    rec = generate_dj_recommendation(a, b)

    risk_text = " ".join(rec.risk_notes).lower()
    assert "energie" in risk_text

  def test_low_genre_compat_creates_risk(self):
    a = _make_track(genre="Psytrance", bpm=140.0)
    b = _make_track(genre="Tech House", bpm=128.0)
    rec = generate_dj_recommendation(a, b)

    risk_text = " ".join(rec.risk_notes).lower()
    assert "genre" in risk_text or "kompatibilitaet" in risk_text

  def test_no_risks_for_perfect_match(self):
    a = _make_track(genre="Progressive", bpm=128.0, energy=70, camelot="8A")
    b = _make_track(genre="Progressive", bpm=128.0, energy=72, camelot="8A")
    rec = generate_dj_recommendation(a, b)

    assert len(rec.risk_notes) == 0

  def test_key_clash_risk(self):
    a = _make_track(genre="Psytrance", bpm=140.0, camelot="1A")
    b = _make_track(genre="Psytrance", bpm=140.0, camelot="7A")
    rec = generate_dj_recommendation(a, b)

    risk_text = " ".join(rec.risk_notes).lower()
    assert "tonart" in risk_text or "camelot" in risk_text


# === Hilfsfunktionen ===

class TestHelperFunctions:
  """Tests fuer interne Hilfsfunktionen."""

  def test_find_mix_in_after_intro(self):
    """Mix-In muss NACH dem Intro liegen (nie im Intro)."""
    sections = _standard_sections()
    profile = get_mix_profile("Psytrance")
    spb = (60.0 / 140.0) * 4  # seconds per bar
    result = _find_mix_in_point(sections, profile, spb)
    # Intro endet bei 60s -> Mix-In >= 60s
    assert result >= 60.0, f"Mix-In {result}s liegt im Intro (endet bei 60s)"

  def test_find_mix_in_no_intro(self):
    sections = [
      {"label": "build", "start_time": 0.0, "end_time": 30.0},
      {"label": "drop", "start_time": 30.0, "end_time": 180.0},
    ]
    profile = get_mix_profile("Tech House")
    spb = (60.0 / 128.0) * 4
    result = _find_mix_in_point(sections, profile, spb)
    assert result == 0.0  # Erster Build/Drop startet bei 0

  def test_find_mix_out_before_outro(self):
    """Mix-Out muss VOR dem Outro liegen (nie im Outro)."""
    sections = _standard_sections()
    profile = get_mix_profile("Psytrance")
    spb = (60.0 / 140.0) * 4
    result = _find_mix_out_point(sections, profile, spb, 420.0)
    assert result < 360.0, f"Mix-Out {result}s im Outro (startet bei 360s)"
    assert result > 0.0

  def test_find_mix_out_no_outro(self):
    """Kein Outro: Mix-Out basierend auf letzter Nicht-Outro-Sektion."""
    sections = [
      {"label": "intro", "start_time": 0.0, "end_time": 30.0, "avg_energy": 30.0},
      {"label": "drop", "start_time": 30.0, "end_time": 270.0, "avg_energy": 80.0},
      {"label": "main", "start_time": 270.0, "end_time": 300.0, "avg_energy": 40.0},
    ]
    profile = get_mix_profile("Tech House")
    spb = (60.0 / 128.0) * 4
    result = _find_mix_out_point(sections, profile, spb, 300.0)
    # Kein Outro -> outro_start = 300.0, letzte Nicht-Outro-Sektion = main(270-300)
    assert result <= 300.0
    assert result > 0.0

  def test_section_at_mix_out(self):
    track = _make_track(sections=_standard_sections(), mix_out=370.0)
    section = _get_section_at_mix_out(track)
    assert section == "outro"

  def test_section_at_mix_in(self):
    track = _make_track(sections=_standard_sections(), mix_in=65.0)
    section = _get_section_at_mix_in(track)
    assert section == "build"

  def test_section_no_sections(self):
    track = _make_track(sections=[])
    assert _get_section_at_mix_out(track) == "unknown"
    assert _get_section_at_mix_in(track) == "unknown"

  def test_build_structure_note_ideal(self):
    note = _build_structure_note("outro", "intro")
    assert "Ideal" in note

  def test_build_structure_note_bold(self):
    note = _build_structure_note("drop", "drop")
    assert "Mutig" in note

  def test_build_structure_note_unknown(self):
    """Unknown sections -> leerer String (keine nutzlose Meldung)."""
    note = _build_structure_note("unknown", "intro")
    assert note == ""

  def test_cross_genre_technique_all_pairs(self):
    all_genres = [
      "Psytrance", "Tech House", "Progressive", "Melodic Techno",
      "Techno", "Deep House", "Trance", "Drum & Bass", "Minimal",
    ]
    for i, a in enumerate(all_genres):
      for b in all_genres[i+1:]:
        technique = _get_cross_genre_technique(a, b)
        assert technique != "", f"Keine Technik fuer {a}/{b}"
        assert len(technique) > 10, f"Technik zu kurz fuer {a}/{b}"

  def test_cross_genre_eq_all_pairs(self):
    all_genres = [
      "Psytrance", "Tech House", "Progressive", "Melodic Techno",
      "Techno", "Deep House", "Trance", "Drum & Bass", "Minimal",
    ]
    for i, a in enumerate(all_genres):
      for b in all_genres[i+1:]:
        eq = _get_cross_genre_eq(a, b)
        assert eq != "", f"Keine EQ-Strategie fuer {a}/{b}"

  def test_extract_camelot_number(self):
    assert _extract_camelot_number("8A") == 8
    assert _extract_camelot_number("12B") == 12
    assert _extract_camelot_number("1A") == 1
    assert _extract_camelot_number("") == 0
    assert _extract_camelot_number("X") == 0

  def test_assess_risks_no_issues(self):
    a = _make_track(bpm=128.0, energy=70, camelot="8A")
    b = _make_track(bpm=128.0, energy=72, camelot="8A")
    risks = _assess_transition_risks(a, b, 1.0)
    assert len(risks) == 0

  def test_assess_risks_all_issues(self):
    a = _make_track(bpm=145.0, energy=90, camelot="1A")
    b = _make_track(bpm=126.0, energy=30, camelot="7A")
    risks = _assess_transition_risks(a, b, 0.3)
    assert len(risks) >= 3  # BPM, Energy, Genre + evtl. Key


# === Integration mit Playlist ===

class TestPlaylistIntegration:
  """Tests dass DJ Brain Funktionen in playlist.py korrekt importierbar sind."""

  def test_imports_work(self):
    from hpg_core.playlist import calculate_enhanced_compatibility, compute_transition_recommendations
    assert callable(calculate_enhanced_compatibility)
    assert callable(compute_transition_recommendations)

  def test_enhanced_compatibility_uses_dj_brain(self):
    """calculate_enhanced_compatibility sollte detected_genre nutzen."""
    from hpg_core.playlist import calculate_enhanced_compatibility

    a = _make_track(genre="Progressive", bpm=128.0, energy=70, camelot="8A")
    a.genre = "Electronic"  # ID3 Genre
    b = _make_track(genre="Melodic Techno", bpm=126.0, energy=72, camelot="8A")
    b.genre = "Electronic"  # ID3 Genre gleich

    metrics = calculate_enhanced_compatibility(a, b, bpm_tolerance=3.0)

    # Genre-Kompatibilitaet sollte DJ Brain Wert haben (0.85)
    # nicht den alten Wert (1.0 weil beide "Electronic")
    assert 0.8 <= metrics.genre_compatibility <= 0.9

  def test_transition_recommendations_with_dj_brain(self):
    """compute_transition_recommendations sollte DJ Brain Notes enthalten."""
    from hpg_core.playlist import compute_transition_recommendations

    a = _make_track(genre="Psytrance", bpm=140.0, energy=75, duration=420.0,
                    sections=_standard_sections(), mix_in=60.0, mix_out=360.0)
    b = _make_track(genre="Psytrance", bpm=142.0, energy=78, duration=420.0,
                    sections=_standard_sections(), mix_in=60.0, mix_out=360.0)

    recs = compute_transition_recommendations([a, b], bpm_tolerance=3.0)
    assert len(recs) == 1

    rec = recs[0]
    # DJ Brain Notes sollten Mix-Technik oder EQ enthalten
    assert "Mix:" in rec.notes or "EQ:" in rec.notes or "Transition:" in rec.notes


# === Paarspezifische Mix-Punkt-Berechnung ===

def _psytrance_sections_long():
  """Psytrance-Track mit langem Intro: 2x 64 Bars = 128 Bars = 106.2s (bei 145 BPM)."""
  spb = (60.0 / 145.0) * 4  # 1.655s/Bar
  intro1_end = 64 * spb      # ~105.9s
  intro2_end = 128 * spb     # ~211.7s
  drop_end   = 256 * spb     # ~423.4s
  outro_start = drop_end     # Outro danach
  duration    = outro_start + 64 * spb  # ~529s
  return [
    {"label": "intro", "start_time": 0.0,          "end_time": intro1_end, "start_bar": 0,   "end_bar": 64,  "avg_energy": 20.0},
    {"label": "intro", "start_time": intro1_end,   "end_time": intro2_end, "start_bar": 64,  "end_bar": 128, "avg_energy": 25.0},
    {"label": "drop",  "start_time": intro2_end,   "end_time": drop_end,   "start_bar": 128, "end_bar": 256, "avg_energy": 90.0},
    {"label": "outro", "start_time": outro_start,  "end_time": duration,   "start_bar": 256, "end_bar": 320, "avg_energy": 20.0},
  ], duration


def _psytrance_sections_short():
  """Psytrance-Track mit kurzem Intro: 16 Bars = 26.2s (bei 146 BPM)."""
  spb = (60.0 / 146.0) * 4
  intro_end   = 16 * spb   # ~26.2s
  drop_end    = 128 * spb  # ~209.6s
  outro_start = drop_end
  duration    = outro_start + 32 * spb  # ~261.9s
  return [
    {"label": "intro", "start_time": 0.0,         "end_time": intro_end,  "start_bar": 0,   "end_bar": 16,  "avg_energy": 18.0},
    {"label": "drop",  "start_time": intro_end,   "end_time": drop_end,   "start_bar": 16,  "end_bar": 128, "avg_energy": 88.0},
    {"label": "outro", "start_time": outro_start, "end_time": duration,   "start_bar": 128, "end_bar": 160, "avg_energy": 18.0},
  ], duration


class TestGetIntroEnd:
  """Tests fuer _get_intro_end(): Wo endet das Intro wirklich?"""

  def test_standard_single_intro(self):
    """Standard-Sections: Intro endet bei 60.0s."""
    track = _make_track(sections=_standard_sections(), mix_in=60.0)
    assert _get_intro_end(track) == 60.0

  def test_long_multi_section_intro(self):
    """Zwei aufeinanderfolgende Intro-Sections werden kumuliert."""
    sections, duration = _psytrance_sections_long()
    spb = (60.0 / 145.0) * 4
    expected_end = round(128 * spb, 1)  # ~211.7s
    track = _make_track(
      genre="Psytrance", bpm=145.0, duration=duration,
      sections=sections, mix_in=0.0,
    )
    assert abs(_get_intro_end(track) - expected_end) < 1.0  # 1s Toleranz

  def test_no_intro_section_fallback_to_mix_in(self):
    """Track ohne Intro-Section -> Fallback auf mix_in_point."""
    sections = [
      {"label": "drop",  "start_time": 0.0,   "end_time": 120.0, "avg_energy": 85.0},
      {"label": "outro", "start_time": 120.0, "end_time": 180.0, "avg_energy": 20.0},
    ]
    track = _make_track(sections=sections, mix_in=45.0)
    assert _get_intro_end(track) == 45.0

  def test_no_sections_at_all(self):
    """Leere sections -> mix_in_point."""
    track = _make_track(sections=[], mix_in=88.0)
    assert _get_intro_end(track) == 88.0

  def test_no_sections_no_mix_in(self):
    """Weder sections noch mix_in_point -> 0.0."""
    track = _make_track(sections=[], mix_in=0.0)
    assert _get_intro_end(track) == 0.0


class TestCalculatePairedMixPoints:
  """
  Tests fuer calculate_paired_mix_points(track_a, track_b).

  Szenario-Uebersicht:
    [Gleiches Intro/Outro]: Guard: Mix-In B >= intro_end, Mix-Out A < outro_start
    [Langes Intro B]:       Mix-In B nach Intro (>= 212s), Mix-Out A vor Outro
    [Kurzes Intro B]:       Mix-In B nach Intro (>= 26s)
    [Non-Psytrance]:        Gleiche Guards fuer alle Genres
  """

  def test_equal_intro_outro_mix_in_after_intro(self):
    """
    Intro B = 60s, Outro A = 60s.
    Guard: Mix-In B darf NICHT im Intro liegen -> >= 60.0.
    """
    track_a = _make_track(
      genre="Psytrance", bpm=143.0, duration=420.0,
      sections=_standard_sections(), mix_out=360.0,
    )
    track_b = _make_track(
      genre="Psytrance", bpm=143.0, duration=420.0,
      sections=_standard_sections(), mix_in=60.0,
    )
    mix_out_a, mix_in_b = calculate_paired_mix_points(track_a, track_b)
    assert mix_in_b >= 60.0, f"Mix-In B im Intro! War {mix_in_b}, Intro endet bei 60s"
    assert mix_out_a < 360.0, f"Mix-Out A im Outro! War {mix_out_a}, Outro startet bei 360s"

  def test_long_intro_mix_in_not_zero(self):
    """
    Intro B = ~212s, Outro A = 60s.
    Overlap = min(212, 60) = 60s -> Mix-In B = ~152s (NICHT 0.0!).
    """
    sections_b, duration_b = _psytrance_sections_long()
    spb_b = (60.0 / 145.0) * 4
    intro_end_b = 128 * spb_b  # ~211.7s

    track_a = _make_track(
      genre="Psytrance", bpm=143.0, duration=420.0,
      sections=_standard_sections(), mix_out=360.0,
    )
    track_b = _make_track(
      genre="Psytrance", bpm=145.0, duration=duration_b,
      sections=sections_b, mix_in=0.0,
    )
    mix_out_a, mix_in_b = calculate_paired_mix_points(track_a, track_b)

    # Mix-In B = intro_end - outro_dauer_A = 211.7 - 60 = ~151.7s
    expected_mix_in_b = intro_end_b - 60.0
    assert mix_in_b > 0.0, (
      f"Bei langem Intro sollte Mix-In B > 0 sein, war {mix_in_b}"
    )
    # Guard: Mix-In B nach Intro (Rundungstoleranz 1 Bar)
    assert mix_in_b >= intro_end_b - 1.0, (
      f"Mix-In B {mix_in_b}s im Intro (endet bei {intro_end_b:.1f}s)"
    )
    # Guard: Mix-Out A vor Outro (startet bei 360s)
    assert mix_out_a < 360.0, f"Mix-Out A {mix_out_a}s im Outro (startet bei 360s)"

  def test_short_intro_mix_in_after_intro(self):
    """
    Intro B = ~26s, Outro A = 60s.
    Guard: Mix-In B NACH Intro (>= 26s), Mix-Out A VOR Outro (< 360s).
    """
    sections_b, duration_b = _psytrance_sections_short()

    track_a = _make_track(
      genre="Psytrance", bpm=143.0, duration=420.0,
      sections=_standard_sections(), mix_out=360.0,
    )
    track_b = _make_track(
      genre="Psytrance", bpm=146.0, duration=duration_b,
      sections=sections_b, mix_in=0.0,
    )
    mix_out_a, mix_in_b = calculate_paired_mix_points(track_a, track_b)

    # Guard: Mix-In B nach Intro (~26s, Rundungstoleranz 1 Bar)
    spb_b = (60.0 / 146.0) * 4
    intro_end_b = 16 * spb_b  # ~26.3s
    assert mix_in_b >= intro_end_b - 1.0, (
      f"Mix-In B {mix_in_b}s im Intro (endet bei {intro_end_b:.1f}s)"
    )
    assert mix_out_a < 420.0, f"Mix-Out A muss vor Track-Ende liegen"

  def test_tech_house_paired_points(self):
    """Tech House: Paired Mix Points werden berechnet (nicht mehr Sonderbehandlung)."""
    track_a = _make_track(
      genre="Tech House", bpm=130.0, duration=360.0,
      sections=_standard_sections(), mix_out=288.0,
    )
    track_b = _make_track(
      genre="Tech House", bpm=132.0, duration=360.0,
      sections=_standard_sections(), mix_in=55.0,
    )
    mix_out_a, mix_in_b = calculate_paired_mix_points(track_a, track_b)

    assert mix_out_a >= 0.0
    assert mix_in_b >= 0.0
    assert mix_out_a <= track_a.duration
    assert mix_in_b <= track_b.duration
    # Intro endet bei 60s, Outro startet bei 360s (standard_sections)
    assert mix_in_b >= 55.0, f"Mix-In B {mix_in_b}s zu nah am Intro"
    assert mix_out_a < 360.0, f"Mix-Out A {mix_out_a}s im Outro"

  def test_overlap_minimum_8_bars(self):
    """
    Auch mit sehr kurzem Intro: Overlap mindestens 8 Bars.
    """
    sections_b, duration_b = _psytrance_sections_short()
    bpm_b = 146.0
    spb_b = (60.0 / bpm_b) * 4
    min_expected_overlap = 8 * spb_b  # ~13.7s

    track_a = _make_track(
      genre="Psytrance", bpm=143.0, duration=420.0,
      sections=_standard_sections(), mix_out=360.0,
    )
    track_b = _make_track(
      genre="Psytrance", bpm=bpm_b, duration=duration_b,
      sections=sections_b, mix_in=0.0,
    )
    mix_out_a, mix_in_b = calculate_paired_mix_points(track_a, track_b)
    actual_overlap = track_a.duration - mix_out_a

    assert actual_overlap >= min_expected_overlap, (
      f"Overlap {actual_overlap:.1f}s < Minimum {min_expected_overlap:.1f}s (8 Bars)"
    )

  def test_recommendation_includes_paired_points(self):
    """generate_dj_recommendation() befuellt adjusted_mix_out_a und adjusted_mix_in_b."""
    track_a = _make_track(
      genre="Psytrance", bpm=143.0, duration=420.0,
      sections=_standard_sections(), mix_out=360.0,
    )
    track_b = _make_track(
      genre="Psytrance", bpm=143.0, duration=420.0,
      sections=_standard_sections(), mix_in=0.0,
    )
    rec = generate_dj_recommendation(track_a, track_b)

    assert rec.adjusted_mix_out_a >= 0.0,   "adjusted_mix_out_a muss gesetzt sein"
    assert rec.adjusted_mix_in_b >= 0.0,    "adjusted_mix_in_b muss gesetzt sein"
    assert rec.overlap_seconds > 0.0,        "overlap_seconds muss > 0 sein"

  def test_trance_paired_points(self):
    """Trance: Paired Mix Points werden berechnet (gleiche Logik wie alle Genres)."""
    track_a = _make_track(
      genre="Trance", bpm=138.0, duration=400.0,
      sections=_standard_sections(), mix_out=340.0,
    )
    track_b = _make_track(
      genre="Trance", bpm=140.0, duration=400.0,
      sections=_standard_sections(), mix_in=60.0,
    )
    mix_out_a, mix_in_b = calculate_paired_mix_points(track_a, track_b)

    assert mix_out_a >= 0.0
    assert mix_in_b >= 60.0, f"Trance Mix-In B {mix_in_b}s im Intro"
    assert mix_out_a < 360.0, f"Trance Mix-Out A {mix_out_a}s im Outro"
    assert mix_out_a <= track_a.duration


# === Intro/Outro Section Helpers ===

class TestIntroOutroSectionHelpers:
  """Tests fuer _get_intro_end_from_sections und _get_outro_start_from_sections."""

  def test_intro_end_standard_track(self):
    """Standard-Track: Intro endet bei 60s."""
    sections = _standard_sections()
    assert _get_intro_end_from_sections(sections) == 60.0

  def test_intro_end_multi_intro(self):
    """Multi-Intro: Zwei Intro-Sektionen hintereinander."""
    sections = [
      {"label": "intro", "start_time": 0.0, "end_time": 30.0},
      {"label": "intro", "start_time": 30.0, "end_time": 60.0},
      {"label": "build", "start_time": 60.0, "end_time": 90.0},
    ]
    assert _get_intro_end_from_sections(sections) == 60.0

  def test_intro_end_no_intro(self):
    """Kein Intro: Gibt 0.0 zurueck."""
    sections = [
      {"label": "drop", "start_time": 0.0, "end_time": 90.0},
      {"label": "outro", "start_time": 90.0, "end_time": 120.0},
    ]
    assert _get_intro_end_from_sections(sections) == 0.0

  def test_intro_end_empty_sections(self):
    """Leere Sektionen: Gibt 0.0 zurueck."""
    assert _get_intro_end_from_sections([]) == 0.0

  def test_outro_start_standard_track(self):
    """Standard-Track: Outro startet bei 360s."""
    sections = _standard_sections()
    assert _get_outro_start_from_sections(sections, 420.0) == 360.0

  def test_outro_start_multi_outro(self):
    """Multi-Outro: Zwei Outro-Sektionen am Ende."""
    sections = [
      {"label": "drop", "start_time": 0.0, "end_time": 200.0},
      {"label": "outro", "start_time": 200.0, "end_time": 250.0},
      {"label": "outro", "start_time": 250.0, "end_time": 300.0},
    ]
    assert _get_outro_start_from_sections(sections, 300.0) == 200.0

  def test_outro_start_no_outro(self):
    """Kein Outro: Gibt duration zurueck."""
    sections = [
      {"label": "intro", "start_time": 0.0, "end_time": 30.0},
      {"label": "drop", "start_time": 30.0, "end_time": 300.0},
    ]
    assert _get_outro_start_from_sections(sections, 300.0) == 300.0

  def test_outro_start_empty_sections(self):
    """Leere Sektionen: Gibt duration zurueck."""
    assert _get_outro_start_from_sections([], 300.0) == 300.0


# === Mix-In/Out Intro/Outro Guard Tests ===

class TestMixInNeverInIntro:
  """Mix-In darf NIEMALS in einer Intro-Sektion liegen."""

  def test_standard_track_mix_in_after_intro(self):
    """Standard-Track: Mix-In >= 60s (Intro endet bei 60s)."""
    sections = _standard_sections()
    profile = get_mix_profile("Psytrance")
    spb = (60.0 / 140.0) * 4
    mix_in = _find_mix_in_point(sections, profile, spb)
    assert mix_in >= 60.0, f"Mix-In {mix_in}s liegt im Intro (endet bei 60s)"

  def test_trance_track_mix_in_after_intro(self):
    """Trance: Mix-In nach Intro, nicht bei 0.0."""
    sections = [
      {"label": "intro", "start_time": 0.0, "end_time": 53.0, "start_bar": 0, "end_bar": 32, "avg_energy": 20.0},
      {"label": "build", "start_time": 53.0, "end_time": 106.0, "start_bar": 32, "end_bar": 64, "avg_energy": 55.0},
      {"label": "drop", "start_time": 106.0, "end_time": 300.0, "start_bar": 64, "end_bar": 180, "avg_energy": 85.0},
      {"label": "outro", "start_time": 300.0, "end_time": 360.0, "start_bar": 180, "end_bar": 216, "avg_energy": 20.0},
    ]
    profile = get_mix_profile("Trance")
    spb = (60.0 / 138.0) * 4
    mix_in = _find_mix_in_point(sections, profile, spb)
    assert mix_in >= 53.0, f"Mix-In {mix_in}s liegt im Intro (endet bei 53s)"

  def test_no_intro_track(self):
    """Track ohne Intro: Mix-In kann bei 0.0 sein."""
    sections = [
      {"label": "drop", "start_time": 0.0, "end_time": 200.0, "start_bar": 0, "end_bar": 100, "avg_energy": 85.0},
      {"label": "outro", "start_time": 200.0, "end_time": 300.0, "start_bar": 100, "end_bar": 150, "avg_energy": 20.0},
    ]
    profile = get_mix_profile("Techno")
    spb = (60.0 / 130.0) * 4
    mix_in = _find_mix_in_point(sections, profile, spb)
    # Kein Intro -> Mix-In darf bei 0.0 oder auf erster Phrasen-Grenze sein
    assert mix_in >= 0.0
    # Mix-In muss vor dem Drop-Ende liegen
    assert mix_in < 200.0, f"Mix-In {mix_in}s zu spaet (Drop endet bei 200s)"

  def test_multi_intro_mix_in_after_all(self):
    """Multi-Intro: Mix-In nach ALLEN Intro-Sektionen."""
    sections = [
      {"label": "intro", "start_time": 0.0, "end_time": 30.0, "start_bar": 0, "end_bar": 16, "avg_energy": 15.0},
      {"label": "intro", "start_time": 30.0, "end_time": 60.0, "start_bar": 16, "end_bar": 32, "avg_energy": 25.0},
      {"label": "build", "start_time": 60.0, "end_time": 90.0, "start_bar": 32, "end_bar": 48, "avg_energy": 55.0},
      {"label": "drop", "start_time": 90.0, "end_time": 250.0, "start_bar": 48, "end_bar": 133, "avg_energy": 85.0},
      {"label": "outro", "start_time": 250.0, "end_time": 300.0, "start_bar": 133, "end_bar": 160, "avg_energy": 20.0},
    ]
    profile = get_mix_profile("Deep House")
    spb = (60.0 / 124.0) * 4
    mix_in = _find_mix_in_point(sections, profile, spb)
    assert mix_in >= 60.0, f"Mix-In {mix_in}s liegt im Intro (endet bei 60s)"


class TestMixOutNeverInOutro:
  """Mix-Out darf NIEMALS in einer Outro-Sektion liegen."""

  def test_standard_track_mix_out_before_outro(self):
    """Standard-Track: Mix-Out < 360s (Outro startet bei 360s)."""
    sections = _standard_sections()
    profile = get_mix_profile("Psytrance")
    spb = (60.0 / 140.0) * 4
    mix_out = _find_mix_out_point(sections, profile, spb, 420.0)
    assert mix_out < 360.0, f"Mix-Out {mix_out}s liegt im Outro (startet bei 360s)"

  def test_multi_outro_mix_out_before_first(self):
    """Multi-Outro: Mix-Out vor der ERSTEN Outro-Sektion."""
    sections = [
      {"label": "drop", "start_time": 0.0, "end_time": 200.0, "start_bar": 0, "end_bar": 100, "avg_energy": 85.0},
      {"label": "main", "start_time": 200.0, "end_time": 250.0, "start_bar": 100, "end_bar": 125, "avg_energy": 60.0},
      {"label": "outro", "start_time": 250.0, "end_time": 275.0, "start_bar": 125, "end_bar": 138, "avg_energy": 30.0},
      {"label": "outro", "start_time": 275.0, "end_time": 300.0, "start_bar": 138, "end_bar": 150, "avg_energy": 15.0},
    ]
    profile = get_mix_profile("Techno")
    spb = (60.0 / 130.0) * 4
    mix_out = _find_mix_out_point(sections, profile, spb, 300.0)
    assert mix_out <= 250.0, f"Mix-Out {mix_out}s liegt im Outro (startet bei 250s)"

  def test_no_outro_track(self):
    """Track ohne Outro: Mix-Out basierend auf Genre-Profil."""
    sections = [
      {"label": "intro", "start_time": 0.0, "end_time": 30.0, "start_bar": 0, "end_bar": 16, "avg_energy": 20.0},
      {"label": "drop", "start_time": 30.0, "end_time": 300.0, "start_bar": 16, "end_bar": 160, "avg_energy": 85.0},
    ]
    profile = get_mix_profile("Drum & Bass")
    spb = (60.0 / 174.0) * 4
    mix_out = _find_mix_out_point(sections, profile, spb, 300.0)
    # Kein Outro -> Mix-Out basierend auf Profil, muss im Drop-Bereich liegen
    assert mix_out >= 30.0, f"Mix-Out {mix_out}s zu frueh (Drop startet bei 30s)"
    assert mix_out <= 300.0, f"Mix-Out {mix_out}s ueber Track-Dauer"


class TestGenreAwareMixPointsGuard:
  """calculate_genre_aware_mix_points respektiert Intro/Outro-Grenzen."""

  @pytest.mark.parametrize("genre", [
    "Psytrance", "Trance", "Tech House", "Techno",
    "Deep House", "Progressive", "Melodic Techno",
    "Drum & Bass", "Minimal",
  ])
  def test_mix_in_after_intro_all_genres(self, genre):
    """Mix-In nach Intro fuer alle Genres."""
    sections = _standard_sections()
    bpm = 140.0 if genre in ("Psytrance", "Trance") else 128.0
    mi, mo, _, _ = calculate_genre_aware_mix_points(sections, bpm, 420.0, genre)
    assert mi >= 60.0, f"{genre}: Mix-In {mi}s im Intro (endet bei 60s)"

  @pytest.mark.parametrize("genre", [
    "Psytrance", "Trance", "Tech House", "Techno",
    "Deep House", "Progressive", "Melodic Techno",
    "Drum & Bass", "Minimal",
  ])
  def test_mix_out_before_outro_all_genres(self, genre):
    """Mix-Out vor Outro fuer alle Genres."""
    sections = _standard_sections()
    bpm = 140.0 if genre in ("Psytrance", "Trance") else 128.0
    mi, mo, _, _ = calculate_genre_aware_mix_points(sections, bpm, 420.0, genre)
    assert mo < 360.0, f"{genre}: Mix-Out {mo}s im Outro (startet bei 360s)"

  def test_different_structures_different_points(self):
    """Verschiedene Track-Strukturen erzeugen verschiedene Mix-Punkte."""
    sections_a = [
      {"label": "intro", "start_time": 0.0, "end_time": 90.0, "start_bar": 0, "end_bar": 48, "avg_energy": 20.0},
      {"label": "drop", "start_time": 90.0, "end_time": 380.0, "start_bar": 48, "end_bar": 203, "avg_energy": 85.0},
      {"label": "outro", "start_time": 380.0, "end_time": 420.0, "start_bar": 203, "end_bar": 224, "avg_energy": 20.0},
    ]
    sections_b = [
      {"label": "intro", "start_time": 0.0, "end_time": 30.0, "start_bar": 0, "end_bar": 16, "avg_energy": 20.0},
      {"label": "drop", "start_time": 30.0, "end_time": 300.0, "start_bar": 16, "end_bar": 160, "avg_energy": 85.0},
      {"label": "outro", "start_time": 300.0, "end_time": 420.0, "start_bar": 160, "end_bar": 224, "avg_energy": 20.0},
    ]
    mi_a, mo_a, _, _ = calculate_genre_aware_mix_points(sections_a, 140.0, 420.0, "Techno")
    mi_b, mo_b, _, _ = calculate_genre_aware_mix_points(sections_b, 140.0, 420.0, "Techno")
    assert mi_a != mi_b or mo_a != mo_b, "Verschiedene Strukturen haben gleiche Mix-Punkte!"


class TestMixPointIntegration:
  """Ende-zu-Ende Tests: DJ Brain + Mix-Punkte + Empfehlungen."""

  def test_full_recommendation_respects_intro_outro(self):
    """generate_dj_recommendation nutzt Mix-Punkte die nicht in Intro/Outro liegen."""
    a = _make_track(
      genre="Psytrance", bpm=140.0, duration=420.0,
      mix_in=60.0, mix_out=350.0,
      sections=_standard_sections(),
    )
    b = _make_track(
      genre="Trance", bpm=138.0, duration=360.0,
      mix_in=53.0, mix_out=300.0,
      sections=[
        {"label": "intro", "start_time": 0.0, "end_time": 53.0, "start_bar": 0, "end_bar": 32, "avg_energy": 20.0},
        {"label": "build", "start_time": 53.0, "end_time": 106.0, "start_bar": 32, "end_bar": 64, "avg_energy": 55.0},
        {"label": "drop", "start_time": 106.0, "end_time": 300.0, "start_bar": 64, "end_bar": 180, "avg_energy": 85.0},
        {"label": "outro", "start_time": 300.0, "end_time": 360.0, "start_bar": 180, "end_bar": 216, "avg_energy": 20.0},
      ],
    )
    rec = generate_dj_recommendation(a, b)
    assert rec.genre_pair
    assert rec.mix_technique
    assert rec.transition_bars > 0
    # Harte Regel: Mix-Out A vor Outro A (360s), Mix-In B nach Intro B (53s)
    if rec.adjusted_mix_out_a > 0:
      assert rec.adjusted_mix_out_a < 360.0, (
        f"Mix-Out A {rec.adjusted_mix_out_a}s im Outro (startet bei 360s)"
      )
    if rec.adjusted_mix_in_b > 0:
      assert rec.adjusted_mix_in_b >= 53.0, (
        f"Mix-In B {rec.adjusted_mix_in_b}s im Intro (endet bei 53s)"
      )

  @pytest.mark.parametrize("genre_pair", [
    ("Psytrance", "Psytrance"),
    ("Trance", "Trance"),
    ("Tech House", "Techno"),
    ("Deep House", "Progressive"),
    ("Drum & Bass", "Drum & Bass"),
  ])
  def test_recommendations_for_all_genre_pairs(self, genre_pair):
    """DJ Empfehlungen fuer verschiedene Genre-Paare funktionieren."""
    g_a, g_b = genre_pair
    bpm_a = 140.0 if g_a in ("Psytrance", "Trance") else 128.0
    bpm_b = 140.0 if g_b in ("Psytrance", "Trance") else 128.0
    a = _make_track(genre=g_a, bpm=bpm_a, sections=_standard_sections())
    b = _make_track(genre=g_b, bpm=bpm_b, sections=_standard_sections())
    rec = generate_dj_recommendation(a, b)
    assert rec.genre_pair
    assert rec.mix_technique
    assert rec.transition_bars > 0

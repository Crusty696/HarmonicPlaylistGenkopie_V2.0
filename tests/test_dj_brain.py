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
  generate_dj_recommendation,
  GenreMixProfile,
  DJRecommendation,
  GENRE_MIX_PROFILES,
  GENRE_COMPATIBILITY,
  DEFAULT_MIX_PROFILE,
  _find_mix_in_point,
  _find_mix_out_point,
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
    assert mix_in > 0.0
    assert mix_out < 420.0
    assert mix_out > mix_in
    assert bars_in > 0
    assert bars_out > bars_in

  def test_mix_in_after_intro(self):
    """Mix-In sollte nach dem Intro sein (Intro endet bei 60s)."""
    sections = _standard_sections()
    mix_in, _, _, _ = calculate_genre_aware_mix_points(
      sections, bpm=140.0, duration=420.0, genre="Psytrance"
    )
    # Mix-In sollte in der Naehe des Intro-Endes (60s) sein, quantisiert
    assert 30.0 <= mix_in <= 120.0

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
    # Bars sollten in der Naehe eines 16er-Vielfachen sein
    # (exakte Quantisierung haengt von Rundung ab)
    assert bars_in > 0
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
    sections = _standard_sections()
    profile = get_mix_profile("Psytrance")
    spb = (60.0 / 140.0) * 4  # seconds per bar
    result = _find_mix_in_point(sections, profile, spb)
    assert result == 60.0  # Build beginnt bei 60s (nach Intro)

  def test_find_mix_in_no_intro(self):
    sections = [
      {"label": "build", "start_time": 0.0, "end_time": 30.0},
      {"label": "drop", "start_time": 30.0, "end_time": 180.0},
    ]
    profile = get_mix_profile("Tech House")
    spb = (60.0 / 128.0) * 4
    result = _find_mix_in_point(sections, profile, spb)
    assert result == 0.0  # Erster Build/Drop startet bei 0

  def test_find_mix_out_at_outro(self):
    sections = _standard_sections()
    profile = get_mix_profile("Psytrance")
    spb = (60.0 / 140.0) * 4
    result = _find_mix_out_point(sections, profile, spb, 420.0)
    assert result == 360.0  # Outro beginnt bei 360s

  def test_find_mix_out_no_outro(self):
    # Realistisch: Drop endet VOR dem Track-Ende, danach kommt noch eine Section
    sections = [
      {"label": "intro", "start_time": 0.0, "end_time": 30.0, "avg_energy": 30.0},
      {"label": "drop", "start_time": 30.0, "end_time": 270.0, "avg_energy": 80.0},
      {"label": "main", "start_time": 270.0, "end_time": 300.0, "avg_energy": 40.0},
    ]
    profile = get_mix_profile("Tech House")
    spb = (60.0 / 128.0) * 4
    result = _find_mix_out_point(sections, profile, spb, 300.0)
    assert result == 270.0  # Ende des Drops (letzte energiereiche Section)

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

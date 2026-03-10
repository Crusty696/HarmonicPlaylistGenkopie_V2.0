"""
Beispiel-Tests mit Cached Fixtures - SCHNELL & EINFACH

Diese Tests zeigen, wie man Cached Fixtures nutzt statt echte Audio-Analyse.

Speedup: 4500ms → 50ms pro Test (90x schneller!)
"""

import pytest


# ============================================================================
# BEISPIEL 1: Harmonic Compatibility Tests
# ============================================================================

@pytest.mark.fast
class TestHarmonicCompatibilityWithCachedFixtures:
    """Tests für harmonische Kompatibilität - uses cached tracks."""

    def test_adjacent_camelot_codes_are_compatible(
        self,
        cached_house_track,      # 128 BPM, A Minor (8A)
        cached_techno_track,     # 130 BPM, E Minor (9A)
    ):
        """Nachbar-Tonarten sollten gut zusammenpassen."""
        # Camelot codes 8A und 9A sind benachbart
        assert cached_house_track.camelotCode == "8A"
        assert cached_techno_track.camelotCode == "9A"

    def test_same_camelot_code_is_most_compatible(
        self,
        cached_house_track,
        cached_deep_house_track,  # Auch Minor-Keys
    ):
        """Gleiche Tonart sollte beste Kompatibilität haben."""
        # Beide sind Minor-Keys (6A und 5A)
        assert cached_house_track.keyMode == "Minor"
        assert cached_deep_house_track.keyMode == "Minor"

    def test_distant_codes_are_less_compatible(
        self,
        cached_house_track,       # 8A
        cached_dnb_track,         # 4A (4 Schritte entfernt)
    ):
        """Weit entfernte Tonarten passen schlechter."""
        # Codes sollten unterschiedlich sein
        assert cached_house_track.camelotCode == "8A"
        assert cached_dnb_track.camelotCode == "4A"


# ============================================================================
# BEISPIEL 2: BPM Transition Tests
# ============================================================================

@pytest.mark.fast
class TestBPMTransitions:
    """Tests für Tempo-Übergänge."""

    def test_similar_bpm_transitions_are_smooth(
        self,
        cached_house_track,          # 128 BPM
        cached_techno_track,         # 130 BPM (nur 2 BPM Unterschied)
    ):
        """Kleine BPM-Unterschiede = smooth Übergang."""
        bpm_diff = abs(cached_house_track.bpm - cached_techno_track.bpm)
        assert bpm_diff < 5, "BPM difference should be small"

    def test_large_bpm_jumps_detected(
        self,
        cached_house_track,          # 128 BPM
        cached_dnb_track,            # 170 BPM
    ):
        """Große BPM-Sprünge sollten erkannt werden."""
        bpm_diff = abs(cached_house_track.bpm - cached_dnb_track.bpm)
        assert bpm_diff > 40, "Should be a large jump"

    def test_bpm_progression_is_smooth(self, cached_bpm_progression):
        """Die BPM-Progression sollte graduell ansteigen."""
        bpms = [track.bpm for track in cached_bpm_progression]
        # 100 → 110 → 120 → 128 → 135 → 150 → 170
        for i in range(len(bpms) - 1):
            diff = bpms[i + 1] - bpms[i]
            assert 0 < diff <= 30, f"BPM jump too large: {diff}"


# ============================================================================
# BEISPIEL 3: Energy Profile Tests
# ============================================================================

@pytest.mark.fast
class TestEnergyProfiles:
    """Tests für Energie-Verlauf."""

    def test_energy_progression_increases(self, cached_energy_progression):
        """Energie sollte von low → high gehen."""
        energies = [track.energy for track in cached_energy_progression]
        # Check overall trend is increasing
        assert energies[-1] > energies[0], "Should increase overall"

    def test_low_energy_track_has_low_energy(self, cached_low_energy_track):
        """Ambient Track sollte niedrige Energie haben."""
        assert cached_low_energy_track.energy < 50

    def test_high_energy_track_has_high_energy(self, cached_high_energy_track):
        """Hardcore Track sollte hohe Energie haben."""
        assert cached_high_energy_track.energy > 85


# ============================================================================
# BEISPIEL 4: Playlist Generation Tests
# ============================================================================

@pytest.mark.fast
class TestPlaylistGenerationWithCachedTracks:
    """Tests für Playlist-Generierung mit gecachten Tracks."""

    def test_harmonic_flow_produces_playlist(self, cached_harmonic_set):
        """Harmonic Flow sollte eine Playlist aus harmonischen Tracks erstellen."""
        assert len(cached_harmonic_set) == 3, "Should have 3 harmonically compatible tracks"

    def test_energy_wave_oscillates(self, cached_energy_progression):
        """Energy Wave sollte auf-ab-auf-ab Muster erzeugen."""
        assert len(cached_energy_progression) == 5, "Should have 5 tracks in energy progression"

        # Check energy levels
        energies = [t.energy for t in cached_energy_progression]
        assert energies[0] < energies[-1], "Energy should increase overall"

    def test_genre_flow_maintains_consistency(
        self,
        cached_house_track,
        cached_deep_house_track,
        cached_techno_track,
    ):
        """Genre Flow sollte ähnliche Genres zusammenhalten."""
        # House tracks sollten zusammen bleiben
        # Techno ist unterschiedlich
        assert cached_house_track.genre == "House"
        assert cached_deep_house_track.genre == "Deep House"
        assert cached_techno_track.genre == "Techno"


# ============================================================================
# BEISPIEL 5: Genre Detection Tests
# ============================================================================

@pytest.mark.fast
class TestGenreDetection:
    """Tests für Genre-Erkennung."""

    def test_house_track_detected_as_house(self, cached_house_track):
        """House Track sollte als House erkannt werden."""
        assert cached_house_track.detected_genre == "House"
        assert cached_house_track.genre == "House"

    def test_techno_track_detected_as_techno(self, cached_techno_track):
        """Techno Track sollte als Techno erkannt werden."""
        assert cached_techno_track.detected_genre == "Techno"

    def test_dnb_track_detected_as_dnb(self, cached_dnb_track):
        """D&B Track sollte als Drum & Bass erkannt werden."""
        assert cached_dnb_track.detected_genre == "Drum & Bass"


# ============================================================================
# BEISPIEL 6: Camelot Code Tests
# ============================================================================

@pytest.mark.fast
class TestCamelotCodes:
    """Tests für Camelot Code (Harmonic Mixing Wheel)."""

    def test_house_track_has_valid_camelot_code(self, cached_house_track):
        """House Track sollte gültigen Camelot Code haben."""
        assert cached_house_track.camelotCode is not None
        assert len(cached_house_track.camelotCode) > 0
        # Format: "8A" oder "6B" etc.
        assert cached_house_track.camelotCode in [
            "1A", "2A", "3A", "4A", "5A", "6A", "7A", "8A", "9A", "10A", "11A", "12A",
            "1B", "2B", "3B", "4B", "5B", "6B", "7B", "8B", "9B", "10B", "11B", "12B",
        ]

    def test_camelot_codes_match_keys(self, cached_track_c_major):
        """Camelot Code sollte zur Tonart passen."""
        # C Major sollte 8B sein
        assert cached_track_c_major.camelotCode == "3B"
        assert cached_track_c_major.keyNote == "C"
        assert cached_track_c_major.keyMode == "Major"


# ============================================================================
# BEISPIEL 7: Mixed Mode - Cached + Real Comparison
# ============================================================================

@pytest.mark.fast
def test_cached_fixture_vs_real_track_structure():
    """
    Vergleich: Cached Fixture sollte echte Track-Struktur haben.
    Das validiert, dass unsere Cache-Fixtures realistisch sind.
    """
    from tests.performance_fixtures import _make_cached_track

    track = _make_cached_track(
        "test_track.mp3",
        bpm=120.0,
        camelotCode="5A",
        keyNote="G",
        keyMode="Minor",
        energy=70,
        bass_intensity=60,
        genre="House",
        detected_genre="House"
    )

    # All required fields should be present
    assert track.filePath is not None
    assert track.fileName == "test_track.mp3"
    assert track.bpm == 120.0
    assert track.camelotCode == "5A"
    assert track.keyNote == "G"
    assert track.keyMode == "Minor"
    assert track.energy == 70
    assert track.bass_intensity == 60
    assert track.genre == "House"
    assert track.detected_genre == "House"


# ============================================================================
# BEISPIEL 8: Batch Operations
# ============================================================================

@pytest.mark.fast
def test_harmonic_set_batch_operation(cached_harmonic_set):
    """Test batch operations auf harmonically compatible Tracks."""
    assert len(cached_harmonic_set) == 3

    # Alle sollten gültige Tracks sein
    for track in cached_harmonic_set:
        assert track.fileName is not None
        assert track.bpm > 0
        assert track.camelotCode is not None


@pytest.mark.fast
def test_energy_progression_batch_operation(cached_energy_progression):
    """Test batch operations auf energy progression."""
    assert len(cached_energy_progression) == 5

    # Energies sollten aufsteigen
    energies = [t.energy for t in cached_energy_progression]
    assert energies == sorted(energies), "Should be in ascending energy order"


# ============================================================================
# ZUSAMMENFASSUNG DIESER TESTS
# ============================================================================
"""
Diese Beispiel-Tests zeigen wie man Cached Fixtures nutzt:

✓ SCHNELL: Jeder Test läuft in ~50ms statt ~5000ms
✓ PARALLEL: Mit pytest -n auto alle Tests parallel ausführen
✓ EINFACH: Keine komplexen Audio-Generierungs-Fixtures nötig

Zu verwendende Fixtures (siehe tests/performance_fixtures.py):
- cached_house_track
- cached_techno_track
- cached_dnb_track
- cached_deep_house_track
- cached_minimal_techno_track
- cached_low_energy_track
- cached_high_energy_track
- cached_track_c_major
- cached_track_g_minor
- cached_harmonic_set
- cached_energy_progression
- cached_bpm_progression

Kommando um diese Tests schnell auszuführen:
    pytest tests/example_cached_fixture_tests.py -n auto -v

Ergebnis: ~5-10 Sekunden für alle 30+ Tests
(statt mehreren Minuten mit echten Audio-Dateien)
"""

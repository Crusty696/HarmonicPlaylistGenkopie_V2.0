import pytest
import logging
from hpg_core.genre_compatibility import GenreCompatibilityMatrix

class TestExactMatch:
    """Perfect compatibility when genres are exactly the same."""
    @pytest.mark.parametrize("genre", [
        "House",
        "Techno",
        "Trance",
        "Rock",
        "Jazz",
        "Unknown Genre"
    ])
    def test_same_genre_is_1_0(self, genre):
        assert GenreCompatibilityMatrix.get_compatibility(genre, genre) == 1.0

    def test_case_insensitive_match(self):
        """Case should be ignored when comparing exact matches."""
        assert GenreCompatibilityMatrix.get_compatibility("House", "house") == 1.0
        assert GenreCompatibilityMatrix.get_compatibility("TECHNO", "techno") == 1.0

class TestMissingGenres:
    """Neutral compatibility (0.5) when one or both genres are missing."""
    @pytest.mark.parametrize("g1, g2", [
        ("", "House"),
        ("Techno", ""),
        (None, "Trance"),
        ("Dubstep", None),
        ("", ""),
        (None, None)
    ])
    def test_missing_genre_is_0_5(self, g1, g2):
        assert GenreCompatibilityMatrix.get_compatibility(g1, g2) == 0.5

class TestDictionaryLookup:
    """Testing combinations defined in GenreCompatibilityMatrix.COMPATIBILITY."""
    @pytest.mark.parametrize("g1, g2, expected_score", [
        ("House", "Tech House", 0.90),
        ("Tech House", "House", 0.90),  # Reverse
        ("Techno", "Tech House", 0.75),
        ("Tech House", "Techno", 0.75), # Reverse
        ("Drum and Bass", "Liquid Drum and Bass", 0.85),
        ("Hip-Hop", "Trap", 0.90),
        ("Jazz", "R&B", 0.65),
    ])
    def test_known_combinations(self, g1, g2, expected_score):
        assert GenreCompatibilityMatrix.get_compatibility(g1, g2) == expected_score

    def test_case_insensitive_lookup(self):
        """Dictionary lookup should ignore case."""
        assert GenreCompatibilityMatrix.get_compatibility("hOuSe", "DeEp HouSe") == 0.95
        assert GenreCompatibilityMatrix.get_compatibility("techno", "tech HOUSE") == 0.75

class TestHeuristicFallbacks:
    """Testing fallbacks based on electronic/acoustic classifications."""

    @pytest.mark.parametrize("g1, g2", [
        ("Synthwave", "Electronic Dance Music"), # Both electronic but unknown to dict
        ("electro-swing", "ambient dub"),
    ])
    def test_electronic_to_electronic(self, g1, g2):
        # Expected: 0.65 for electronic/electronic fallback
        assert GenreCompatibilityMatrix.get_compatibility(g1, g2) == 0.65

    @pytest.mark.parametrize("g1, g2", [
        ("Acoustic Pop", "Classical Guitar"),
        ("Folk Rock", "Blues"),
    ])
    def test_acoustic_to_acoustic(self, g1, g2):
        # Expected: 0.70 for acoustic/acoustic fallback
        assert GenreCompatibilityMatrix.get_compatibility(g1, g2) == 0.70

    @pytest.mark.parametrize("g1, g2", [
        ("Electronic Dance", "Acoustic Pop"),
        ("Synthwave", "Classical Guitar"),
        ("House", "Blues"), # Known electronic, unknown acoustic
    ])
    def test_electronic_to_acoustic(self, g1, g2):
        # Expected: 0.35 for electronic/acoustic fallback
        assert GenreCompatibilityMatrix.get_compatibility(g1, g2) == 0.35

    @pytest.mark.parametrize("g1, g2", [
        ("Acoustic Pop", "Electronic Dance"),
    ])
    def test_acoustic_to_electronic_reverse(self, g1, g2):
        # Acoustic first, electronic second does not hit the `electronic(g1) & acoustic(g2)` check
        # So it falls through to the 0.5 fallback
        assert GenreCompatibilityMatrix.get_compatibility(g1, g2) == 0.5

class TestGeneralFallback:
    """Testing fallback for completely unknown combinations."""
    def test_unknown_to_unknown(self):
        # Neither electronic nor acoustic
        assert GenreCompatibilityMatrix.get_compatibility("Polka", "Salsa") == 0.5

    def test_unknown_to_known_electronic(self):
        # One unknown, one electronic (g1 unknown, g2 electronic)
        assert GenreCompatibilityMatrix.get_compatibility("Salsa", "House") == 0.5

    def test_known_electronic_to_unknown(self):
        # One electronic, one unknown (g1 electronic, g2 unknown)
        assert GenreCompatibilityMatrix.get_compatibility("House", "Salsa") == 0.5

class TestLogCompatibility:
    """Testing logging method."""
    def test_log_compatibility(self, caplog):
        # Set caplog to capture DEBUG level messages
        with caplog.at_level(logging.DEBUG):
            GenreCompatibilityMatrix.log_compatibility("House", "Techno")
        assert "Genre compatibility House → Techno: 0.70" in caplog.text

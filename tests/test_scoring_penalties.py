import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock
#sys.modules['numpy'] = MagicMock()

from hpg_core.models import Track
from hpg_core.scoring_context import PlaylistContext
from hpg_core.scoring_bonuses import EnhancedPenaltyCalculator


@pytest.fixture
def base_track():
    return Track(
        filePath="/test.mp3",
        fileName="test.mp3",
        artist="DJ Base",
        title="Base",
        genre="House",
        detected_genre="House",
        bpm=120,
        keyNote="A",
        keyMode="Minor",
        camelotCode="8A",
        energy=50,
        duration=300,
        brightness=50,
        danceability=80,
        vocal_instrumental="instrumental"
    )

class TestEnhancedPenaltyCalculator:

    def test_no_penalties(self, base_track):
        # Perfect match, no penalties
        candidate = Track("/cand.mp3", "cand.mp3", artist="DJ Cand", title="Cand", genre="House",
                          bpm=120, camelotCode="8A", energy=50, brightness=50, danceability=80)
        # Avoid repetition penalty by not having history or having slight diff
        candidate.bpm = 125
        context = PlaylistContext([base_track], 10)

        penalty = EnhancedPenaltyCalculator.calculate_all_penalties(base_track, candidate, context)
        assert penalty == 0.0

    @pytest.mark.parametrize("bpm,energy,camelot,expected_penalty", [
        (165, 50, "8A", -0.15),  # Jarring BPM at stable energy
        (155, 50, "3A", -0.10), # Camelot > 4 and BPM diff > 30
        (120, 95, "12A", -0.12), # Energy diff > 40 and camelot > 3
    ])
    def test_jarring_penalty(self, base_track, bpm, energy, camelot, expected_penalty):
        # Stable energy playlist context
        playlist = [
            Track("/t1", "t1", energy=50, bpm=120, camelotCode="8A"),
            Track("/t2", "t2", energy=50, bpm=120, camelotCode="8A"),
            base_track
        ]
        context = PlaylistContext(playlist, 10)

        candidate = Track("/cand.mp3", "cand.mp3", bpm=bpm, energy=energy, camelotCode=camelot)
        penalty = EnhancedPenaltyCalculator._jarring_penalty(base_track, candidate, context)
        assert penalty == expected_penalty

    def test_repetition_penalty(self, base_track):
        # Exact same attributes -> -0.20
        playlist = [base_track]
        context = PlaylistContext(playlist, 10)
        candidate = Track("/cand.mp3", "cand.mp3", bpm=120, energy=50, camelotCode="8A", brightness=50, genre="House", detected_genre="House")
        penalty = EnhancedPenaltyCalculator._repetition_penalty(base_track, candidate, context)
        assert penalty == -0.20

        # 3 out of 4 same -> -0.10
        candidate.brightness = 90 # different
        candidate.bpm = 120 # restore
        penalty = EnhancedPenaltyCalculator._repetition_penalty(base_track, candidate, context)
        assert penalty == -0.10

        # 2 out of 4 same -> 0.0
        candidate.bpm = 150 # different
        penalty = EnhancedPenaltyCalculator._repetition_penalty(base_track, candidate, context)
        assert penalty == 0.0

    def test_energy_cliff_penalty(self, base_track):
        # Phase = PEAK (position 6 of 10)
        playlist = [base_track] * 6
        context = PlaylistContext(playlist, 10)
        candidate = Track("/c", "c", energy=10) # Diff = 40
        penalty = EnhancedPenaltyCalculator._energy_cliff_penalty(base_track, candidate, context)
        assert penalty == -0.08

        # Phase = INTRO (position 1 of 10)
        playlist = [base_track] * 1
        context = PlaylistContext(playlist, 10)
        candidate = Track("/c", "c", energy=80) # Diff = 30
        penalty = EnhancedPenaltyCalculator._energy_cliff_penalty(base_track, candidate, context)
        assert penalty == -0.05

    def test_spectral_monotony_penalty(self, base_track):
        playlist = [
            Track("/1", "1", brightness=50),
            Track("/2", "2", brightness=52),
            Track("/3", "3", brightness=51)
        ]
        context = PlaylistContext(playlist, 10)
        candidate = Track("/c", "c", brightness=53)
        penalty = EnhancedPenaltyCalculator._spectral_monotony_penalty(base_track, candidate, context)
        assert penalty == -0.05

        # No penalty if recent diff >= 10
        playlist[0].brightness = 40
        context = PlaylistContext(playlist, 10)
        penalty = EnhancedPenaltyCalculator._spectral_monotony_penalty(base_track, candidate, context)
        assert penalty == 0.0

    def test_tonal_drift_penalty(self, base_track):
        # camelot dist <= 1 but energy diff > 30
        context = PlaylistContext([base_track], 10)
        candidate = Track("/c", "c", camelotCode="8A", energy=90)
        penalty = EnhancedPenaltyCalculator._tonal_drift_penalty(base_track, candidate, context)
        assert penalty == -0.08

        # No penalty if camelot > 1
        candidate = Track("/c", "c", camelotCode="10A", energy=90)
        penalty = EnhancedPenaltyCalculator._tonal_drift_penalty(base_track, candidate, context)
        assert penalty == 0.0

    def test_calculate_all_penalties_clamping(self, base_track):
        # Triggering multiple penalties to hit the -0.3 limit
        # JARRING: BPM 165 at stable energy (-0.15)
        # REPETITION: same everything but BPM (-0.10) (Wait, repetition needs 3/4 same. same energy, brightness, genre. different bpm)
        # ENERGY CLIFF in PEAK: energy diff > 30 (-0.08)

        # To get all these, let's craft carefully
        playlist = [
            Track("/1", "1", energy=50, bpm=120, brightness=50, genre="House", camelotCode="8A"),
            Track("/2", "2", energy=50, bpm=120, brightness=50, genre="House", camelotCode="8A"),
            Track("/3", "3", energy=50, bpm=120, brightness=50, genre="House", camelotCode="8A"),
            Track("/4", "4", energy=50, bpm=120, brightness=50, genre="House", camelotCode="8A"),
            Track("/5", "5", energy=50, bpm=120, brightness=50, genre="House", camelotCode="8A"),
            Track("/6", "6", energy=50, bpm=120, brightness=50, genre="House", camelotCode="8A")
        ]
        context = PlaylistContext(playlist, 10) # 6/10 -> PEAK phase
        base_track = playlist[-1]

        # Candidate:
        # BPM 165 -> Jarring -0.15 (bpm diff > 40 at stable energy)
        # Energy 90 -> Cliff -0.08 (energy diff > 30 in PEAK)
        # Brightness 52 -> Spectral monotony -0.05
        # Genre House -> Repetition: same genre, same brightness -> 2/4. Wait.
        # Let's just make it have repetition penalty too. If energy is 90, it's not same energy.
        # So we might not get repetition. But -0.15 - 0.08 - 0.05 = -0.28.
        # Add Tonal drift: camelot <= 1 and energy diff > 30 (-0.08)
        # So total = -0.15 (jarring) - 0.08 (cliff) - 0.05 (spectral) - 0.08 (tonal drift) = -0.36
        candidate = Track("/c", "c", bpm=165, energy=90, brightness=52, genre="House", camelotCode="8A")

        penalty = EnhancedPenaltyCalculator.calculate_all_penalties(base_track, candidate, context)
        assert penalty == -0.3  # Bounded at -0.3

        # Verify without bounding
        raw_penalty = (
            EnhancedPenaltyCalculator._jarring_penalty(base_track, candidate, context) +
            EnhancedPenaltyCalculator._repetition_penalty(base_track, candidate, context) +
            EnhancedPenaltyCalculator._energy_cliff_penalty(base_track, candidate, context) +
            EnhancedPenaltyCalculator._spectral_monotony_penalty(base_track, candidate, context) +
            EnhancedPenaltyCalculator._tonal_drift_penalty(base_track, candidate, context)
        )
        assert raw_penalty < -0.3

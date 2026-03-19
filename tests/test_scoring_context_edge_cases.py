
import pytest
from hpg_core.scoring_context import PlaylistContext
from hpg_core.models import Track

@pytest.fixture
def base_track():
    return Track(
        filePath="<test:track>",
        fileName="track.mp3",
        artist="Test Artist",
        title="Test Track",
        genre="House",
        duration=240.0,
        bpm=128.0,
        keyNote="A",
        keyMode="Minor",
        camelotCode="8A",
        energy=50,
        detected_genre="House"
    )

def create_track(energy=50, bpm=128.0, genre="House"):
    return Track(
        filePath=f"<test:{energy}_{bpm}_{genre}>",
        fileName="track.mp3",
        artist="Test Artist",
        title="Test Track",
        genre=genre,
        duration=240.0,
        bpm=bpm,
        keyNote="A",
        keyMode="Minor",
        camelotCode="8A",
        energy=energy,
        detected_genre=genre
    )

class TestPlaylistContextEdgeCases:

    def test_energy_trend_empty_playlist(self):
        context = PlaylistContext([], 10)
        assert context.get_energy_trend() == "UNDEFINED"

    def test_energy_trend_too_few_tracks(self):
        t1 = create_track(energy=50)
        t2 = create_track(energy=70)

        context = PlaylistContext([t1], 10)
        assert context.get_energy_trend() == "UNDEFINED"

        context = PlaylistContext([t1, t2], 10)
        assert context.get_energy_trend() == "UNDEFINED"

    def test_energy_trend_rising(self):
        playlist = [
            create_track(energy=40),
            create_track(energy=50),
            create_track(energy=55) # 55 - 40 = 15 (> 10)
        ]
        context = PlaylistContext(playlist, 10)
        assert context.get_energy_trend() == "RISING"

    def test_energy_trend_falling(self):
        playlist = [
            create_track(energy=60),
            create_track(energy=50),
            create_track(energy=45) # 45 - 60 = -15 (< -10)
        ]
        context = PlaylistContext(playlist, 10)
        assert context.get_energy_trend() == "FALLING"

    def test_energy_trend_stable_positive_delta(self):
        playlist = [
            create_track(energy=50),
            create_track(energy=55),
            create_track(energy=60) # 60 - 50 = 10 (not > 10)
        ]
        context = PlaylistContext(playlist, 10)
        assert context.get_energy_trend() == "STABLE"

    def test_energy_trend_stable_negative_delta(self):
        playlist = [
            create_track(energy=60),
            create_track(energy=55),
            create_track(energy=50) # 50 - 60 = -10 (not < -10)
        ]
        context = PlaylistContext(playlist, 10)
        assert context.get_energy_trend() == "STABLE"

    def test_energy_trend_only_last_three_considered(self):
        playlist = [
            create_track(energy=10), # Should be ignored
            create_track(energy=100), # Should be ignored
            create_track(energy=50), # Start of window
            create_track(energy=55),
            create_track(energy=52) # 52 - 50 = 2 (STABLE)
        ]
        context = PlaylistContext(playlist, 10)
        assert context.get_energy_trend() == "STABLE"

    def test_bpm_trend_empty_playlist(self):
        context = PlaylistContext([], 10)
        assert context.get_bpm_trend() == "UNDEFINED"

    def test_bpm_trend_accelerating(self):
        playlist = [
            create_track(bpm=120),
            create_track(bpm=124),
            create_track(bpm=126) # 126 - 120 = 6 (> 5)
        ]
        context = PlaylistContext(playlist, 10)
        assert context.get_bpm_trend() == "ACCELERATING"

    def test_bpm_trend_decelerating(self):
        playlist = [
            create_track(bpm=130),
            create_track(bpm=126),
            create_track(bpm=124) # 124 - 130 = -6 (< -5)
        ]
        context = PlaylistContext(playlist, 10)
        assert context.get_bpm_trend() == "DECELERATING"

    def test_bpm_trend_stable(self):
        playlist = [
            create_track(bpm=120),
            create_track(bpm=123),
            create_track(bpm=125) # 125 - 120 = 5 (not > 5)
        ]
        context = PlaylistContext(playlist, 10)
        assert context.get_bpm_trend() == "STABLE"

    def test_genre_streak_empty(self):
        context = PlaylistContext([], 10)
        assert context.get_genre_streak() == 0

    def test_genre_streak_single(self):
        context = PlaylistContext([create_track(genre="House")], 10)
        assert context.get_genre_streak() == 1

    def test_genre_streak_multiple(self):
        playlist = [
            create_track(genre="Techno"),
            create_track(genre="House"),
            create_track(genre="House"),
            create_track(genre="House")
        ]
        context = PlaylistContext(playlist, 10)
        assert context.get_genre_streak() == 3

    def test_camelot_stability_undefined(self):
        context = PlaylistContext([create_track()], 10)
        assert context.get_camelot_stability() == "UNDEFINED"

    def test_camelot_stability_tight(self):
        t1 = create_track()
        t1.camelotCode = "8A"
        t2 = create_track()
        t2.camelotCode = "9A" # dist = 1
        context = PlaylistContext([t1, t2], 10)
        assert context.get_camelot_stability() == "TIGHT" # 1 < 2

    def test_playlist_phase_undefined(self):
        # total_tracks = 0 should return "UNDEFINED"
        context = PlaylistContext([], 0)
        # Note: the constructor sets self.total_tracks = 1 if total_tracks <= 0
        # But get_playlist_phase checks if self.total_tracks <= 0 (which it never will be)
        # However, let's test current behavior.
        # Actually, let's see what happens if we pass 0.
        assert context.total_tracks == 1
        assert context.get_playlist_phase() == "INTRO" # 0/1 = 0 < 0.2

    def test_get_last_track_feature(self):
        t1 = create_track(energy=77)
        context = PlaylistContext([t1], 10)
        assert context.get_last_track_feature("energy") == 77
        assert context.get_last_track_feature("non_existent") is None

        context_empty = PlaylistContext([], 10)
        assert context_empty.get_last_track_feature("energy") is None

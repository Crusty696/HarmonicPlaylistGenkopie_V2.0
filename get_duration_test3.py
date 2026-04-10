import sys

# Create a mock librosa
class MockLibrosa:
    def get_duration(self, y=None, sr=None, path=None):
        if path:
            return 800.0 # Return real length
        if y is not None and sr is not None:
            return len(y) / sr
        return 0.0

sys.modules['librosa'] = MockLibrosa()
import librosa

# Simulate finding out if the track is too long
file_path = "dummy.mp3"
LIBROSA_MAX_DURATION = 600

# BEFORE (Current behavior):
y = [0.0] * int(44100 * 600)  # y is truncated
sr = 44100
duration_before = librosa.get_duration(y=y, sr=sr)
print("Before logic:", duration_before, "(Misses the real duration which is > 10 mins!)")

# AFTER (Proposed behavior):
duration_after = librosa.get_duration(path=file_path)
print("After logic:", duration_after)

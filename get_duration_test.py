import sys
import os

class LibrosaMock:
    def get_duration(self, path=None, y=None, sr=None):
        if path:
            return 800.0
        return 600.0

    def load(self, path, duration=None, sr=None):
        return [0.0] * int(44100 * min(duration or 600.0, 800.0)), 44100

librosa = LibrosaMock()
sys.modules['librosa'] = librosa

# Simulate analysis.py snippet
file_path = "dummy.mp3"
LIBROSA_MAX_DURATION = 600

y, sr = librosa.load(file_path, duration=LIBROSA_MAX_DURATION)
duration = librosa.get_duration(path=file_path) # changed from y=y, sr=sr
print(f"y duration: {len(y)/sr}, file duration: {duration}")
if duration > LIBROSA_MAX_DURATION:
    print(f"Track is too long: {duration}s > {LIBROSA_MAX_DURATION}s. Truncated or skip.")

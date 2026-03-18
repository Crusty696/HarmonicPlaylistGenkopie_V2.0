
import sys
from unittest.mock import MagicMock

# Mock all dependencies that prevent importing hpg_core
sys.modules["numpy"] = MagicMock()
sys.modules["librosa"] = MagicMock()
sys.modules["librosa.feature"] = MagicMock()
sys.modules["librosa.beat"] = MagicMock()
sys.modules["librosa.effects"] = MagicMock()
sys.modules["librosa.onset"] = MagicMock()
sys.modules["mutagen"] = MagicMock()
sys.modules["mutagen.easyid3"] = MagicMock()
sys.modules["PyQt6"] = MagicMock()
sys.modules["PyQt6.QtCore"] = MagicMock()
sys.modules["PyQt6.QtWidgets"] = MagicMock()
sys.modules["PyQt6.QtGui"] = MagicMock()

import os
# Ensure hpg_core is in path
sys.path.append(os.getcwd())

from hpg_core.models import Track
from hpg_core.exporters.m3u8_exporter import M3U8Exporter

def test_m3u8_sanitization():
    # Malicious track with newline injection and path traversal
    malicious_path = "normal/path.mp3\n/etc/passwd\n#EXTINF:100,Injected\n../../../secret.txt"
    malicious_artist = "Artist\nInjected"
    malicious_title = "Title\rInjected"

    track = Track(filePath=malicious_path, fileName="path.mp3", artist=malicious_artist, title=malicious_title)

    exporter = M3U8Exporter()
    output_path = "test_sanitized.m3u8"

    try:
        exporter.export([track], output_path)
        with open(output_path, "r") as f:
            content = f.read()

        # Verify sanitization
        assert "\n/etc/passwd" not in content, "Path newline injection failed"
        assert "\n#EXTINF:100" not in content, "Metadata EXTINF injection failed"
        assert "Artist Injected" in content, "Artist newline should be replaced by space"
        assert "TitleInjected" in content, "Title carriage return should be removed"

        # Verify that the malicious part is now part of a single line
        lines = content.splitlines()
        # Find the line that should contain the path
        path_line = next(l for l in lines if "normal/path.mp3" in l)
        assert "/etc/passwd#EXTINF:100,Injected" in path_line, "Injected content should be on the same line"

        # Ensure that every line starting with #EXTINF: is legitimate
        extinf_lines = [l for l in lines if l.startswith("#EXTINF:")]
        assert len(extinf_lines) == 1, f"Expected 1 line starting with #EXTINF:, found {len(extinf_lines)}"

    finally:
        if os.path.exists(output_path):
            os.remove(output_path)

if __name__ == "__main__":
    try:
        test_m3u8_sanitization()
        print("M3U8Exporter sanitization verified successfully!")
    except Exception as e:
        print(f"Verification failed: {e}")
        sys.exit(1)

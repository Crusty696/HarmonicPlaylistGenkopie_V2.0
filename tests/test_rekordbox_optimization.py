
import os
import unittest
from unittest.mock import patch, MagicMock
import sys

# Mock everything needed to avoid imports of numpy, librosa, etc.
sys.modules["numpy"] = MagicMock()
sys.modules["librosa"] = MagicMock()
sys.modules["mutagen"] = MagicMock()
sys.modules["sqlalchemy"] = MagicMock()
sys.modules["sqlalchemy.orm"] = MagicMock()
sys.modules["pyrekordbox"] = MagicMock()
sys.modules["pyrekordbox.db6"] = MagicMock()

import hpg_core.rekordbox_importer as rb_module
from hpg_core.rekordbox_importer import RekordboxImporter, RekordboxTrackData

class FakeContent:
    def __init__(self, folder_path="C:/Music", filename="track.mp3"):
        self.FolderPath = folder_path
        self.FileNameL = filename
        self.FileNameS = filename
        self.BPM = 12800
        self.KeyName = "8A"
        self.Length = 240
        self.Title = "Test Track"
        self.ArtistName = "Test Artist"
        self.GenreName = "Techno"
        self.AlbumName = "Test Album"
        self.Rating = 3
        self.ColorName = None
        self.Cues = []

class FakeDatabase:
    def __init__(self, contents=None):
        self._contents = contents or []
    def get_content(self):
        return self._contents

class TestRekordboxImporterOptimization(unittest.TestCase):
    def test_basename_cache_population(self):
        content = FakeContent(folder_path="C:/Music", filename="track.mp3")
        db = FakeDatabase([content])
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", True):
            with patch("hpg_core.rekordbox_importer.Rekordbox6Database", return_value=db):
                imp = RekordboxImporter()

        self.assertEqual(len(imp.track_cache), 1)
        self.assertEqual(len(imp.basename_cache), 1)
        self.assertIn("track.mp3", imp.basename_cache)

    def test_get_track_data_fallback(self):
        content = FakeContent(folder_path="C:/Music", filename="track.mp3")
        db = FakeDatabase([content])
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", True):
            with patch("hpg_core.rekordbox_importer.Rekordbox6Database", return_value=db):
                imp = RekordboxImporter()

        # Test exact match
        data = imp.get_track_data("C:/Music/track.mp3")
        self.assertIsNotNone(data)

        # Test fallback match
        data_fallback = imp.get_track_data("D:/Other/track.mp3")
        self.assertIsNotNone(data_fallback)
        self.assertEqual(data, data_fallback)

    def test_basename_cache_first_found_behavior(self):
        contents = [
            FakeContent(folder_path="C:/Folder1", filename="dup.mp3"),
            FakeContent(folder_path="C:/Folder2", filename="dup.mp3")
        ]
        db = FakeDatabase(contents)
        with patch("hpg_core.rekordbox_importer.REKORDBOX_AVAILABLE", True):
            with patch("hpg_core.rekordbox_importer.Rekordbox6Database", return_value=db):
                imp = RekordboxImporter()

        data_fallback = imp.get_track_data("D:/Other/dup.mp3")
        expected_path = os.path.normpath("C:/Folder1/dup.mp3").lower()
        self.assertEqual(imp.track_cache[expected_path], data_fallback)

if __name__ == "__main__":
    unittest.main()

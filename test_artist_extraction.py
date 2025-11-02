"""
Quick test for artist extraction from filenames
"""
import os
import sys
from hpg_core.analysis import parse_filename_for_metadata, extract_metadata

def test_filename_parsing():
    """Test filename parsing patterns"""
    print("=" * 60)
    print("FILENAME PARSING TESTS")
    print("=" * 60)

    test_cases = [
        "Artist Name - Track Title.wav",
        "01 - Artist Name - Track Title.mp3",
        "ArtistName-TrackTitle.flac",
        "Track_Number_Artist_Track.wav",
        "SomeArtist_SomeTrack.mp3",
    ]

    for filename in test_cases:
        # Create fake path
        fake_path = os.path.join("test", filename)
        artist, title = parse_filename_for_metadata(fake_path)

        print(f"\nFilename: {filename}")
        print(f"  Artist: {artist}")
        print(f"  Title:  {title}")
        print(f"  Status: {'[OK] PARSED' if artist and title else '[FAIL] NOT PARSED'}")

def test_real_files():
    """Test with real audio files from test directory"""
    print("\n" + "=" * 60)
    print("REAL FILE TESTS")
    print("=" * 60)

    test_dir = r"C:\CLAUDE_PROJEKTE\HarmonicPlaylistGenkopie_V2.0\tests\test audio files"

    if not os.path.exists(test_dir):
        print(f"[ERROR] Test directory not found: {test_dir}")
        return

    # Get first 5 audio files
    audio_files = []
    for file in os.listdir(test_dir):
        if file.lower().endswith(('.wav', '.mp3', '.flac', '.aiff')):
            audio_files.append(os.path.join(test_dir, file))
            if len(audio_files) >= 5:
                break

    if not audio_files:
        print("[ERROR] No audio files found in test directory")
        return

    for file_path in audio_files:
        artist, title, genre = extract_metadata(file_path)

        print(f"\nFile: {os.path.basename(file_path)}")
        print(f"  Artist: {artist}")
        print(f"  Title:  {title}")
        print(f"  Genre:  {genre}")

        if artist == "Unknown":
            print("  [WARNING] Artist still 'Unknown'")
        else:
            print("  [OK] Artist extracted successfully")

if __name__ == '__main__':
    test_filename_parsing()
    test_real_files()

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

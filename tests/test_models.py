"""
Tests fuer hpg_core.models - Track Dataclass und Camelot-Mapping.
Validiert alle 24 Camelot-Codes und Track-Defaults.
"""
import pytest
from hpg_core.models import Track, CAMELOT_MAP, key_to_camelot
from tests.fixtures.camelot_test_data import EXPECTED_CAMELOT_MAP


class TestCamelotMap:
  """Prueft die korrekte Zuordnung aller 24 Camelot-Codes."""

  def test_camelot_map_has_24_entries(self):
    """Genau 24 Eintraege: 12 Notes x 2 Modes."""
    assert len(CAMELOT_MAP) == 24

  def test_all_12_minor_keys_present(self):
    """Alle 12 Minor-Keys muessen vorhanden sein."""
    notes = ['A', 'A#', 'B', 'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#']
    for note in notes:
      assert (note, 'Minor') in CAMELOT_MAP, f"Minor-Key {note} fehlt"

  def test_all_12_major_keys_present(self):
    """Alle 12 Major-Keys muessen vorhanden sein."""
    notes = ['A', 'A#', 'B', 'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#']
    for note in notes:
      assert (note, 'Major') in CAMELOT_MAP, f"Major-Key {note} fehlt"

  def test_camelot_codes_are_unique(self):
    """Kein Camelot-Code darf doppelt vergeben sein."""
    codes = list(CAMELOT_MAP.values())
    assert len(codes) == len(set(codes)), "Doppelte Camelot-Codes gefunden"

  def test_all_codes_1_to_12(self):
    """Codes gehen von 1A bis 12A und 1B bis 12B."""
    codes = set(CAMELOT_MAP.values())
    expected_codes = set()
    for num in range(1, 13):
      expected_codes.add(f"{num}A")
      expected_codes.add(f"{num}B")
    assert codes == expected_codes

  def test_minor_keys_map_to_a_suffix(self):
    """Alle Minor-Keys muessen auf A-Suffix enden."""
    for (note, mode), code in CAMELOT_MAP.items():
      if mode == 'Minor':
        assert code.endswith('A'), f"{note} Minor -> {code} (erwartet A-Suffix)"

  def test_major_keys_map_to_b_suffix(self):
    """Alle Major-Keys muessen auf B-Suffix enden."""
    for (note, mode), code in CAMELOT_MAP.items():
      if mode == 'Major':
        assert code.endswith('B'), f"{note} Major -> {code} (erwartet B-Suffix)"

  @pytest.mark.parametrize("key,expected", list(EXPECTED_CAMELOT_MAP.items()))
  def test_specific_camelot_mapping(self, key, expected):
    """Prueft jede einzelne Zuordnung gegen Erwartungswerte."""
    assert CAMELOT_MAP[key] == expected, (
      f"{key[0]} {key[1]}: erwartet {expected}, bekommen {CAMELOT_MAP[key]}"
    )

  def test_a_minor_is_8a(self):
    """Klassiker: A Minor = 8A (Standard DJ-Referenz)."""
    assert CAMELOT_MAP[('A', 'Minor')] == '8A'

  def test_c_major_is_8b(self):
    """Relative Major von A Minor: C Major = 8B."""
    assert CAMELOT_MAP[('C', 'Major')] == '8B'

  def test_relative_keys_share_number(self):
    """Relative Major/Minor-Paare haben die gleiche Nummer."""
    relative_pairs = [
      ('A', 'Minor', 'C', 'Major'),
      ('E', 'Minor', 'G', 'Major'),
      ('D', 'Minor', 'F', 'Major'),
      ('B', 'Minor', 'D', 'Major'),
    ]
    for minor_note, minor_mode, major_note, major_mode in relative_pairs:
      minor_code = CAMELOT_MAP[(minor_note, minor_mode)]
      major_code = CAMELOT_MAP[(major_note, major_mode)]
      minor_num = minor_code[:-1]
      major_num = major_code[:-1]
      assert minor_num == major_num, (
        f"Relative Pair: {minor_note}m={minor_code}, {major_note}M={major_code}"
      )


class TestKeyToCamelot:
  """Prueft die key_to_camelot() Funktion."""

  def test_assigns_correct_code(self):
    """Korrekte Zuweisung bei gueltiger Note+Mode."""
    track = Track(filePath="/test.mp3", fileName="test.mp3",
                  keyNote="A", keyMode="Minor")
    key_to_camelot(track)
    assert track.camelotCode == "8A"

  def test_empty_key_no_assignment(self):
    """Leere Note = keine Zuweisung."""
    track = Track(filePath="/test.mp3", fileName="test.mp3",
                  keyNote="", keyMode="Minor")
    key_to_camelot(track)
    assert track.camelotCode == ""

  def test_empty_mode_no_assignment(self):
    """Leere Mode = keine Zuweisung."""
    track = Track(filePath="/test.mp3", fileName="test.mp3",
                  keyNote="A", keyMode="")
    key_to_camelot(track)
    assert track.camelotCode == ""

  def test_invalid_combination(self):
    """Ungueltige Note/Mode = leerer Code."""
    track = Track(filePath="/test.mp3", fileName="test.mp3",
                  keyNote="X", keyMode="Minor")
    key_to_camelot(track)
    assert track.camelotCode == ""

  def test_all_valid_combinations(self):
    """Alle 24 gueltigen Kombinationen werden zugewiesen."""
    for (note, mode), expected_code in CAMELOT_MAP.items():
      track = Track(filePath="/test.mp3", fileName="test.mp3",
                    keyNote=note, keyMode=mode)
      key_to_camelot(track)
      assert track.camelotCode == expected_code


class TestTrackDataclass:
  """Prueft Track-Defaults und Datenstruktur."""

  def test_required_fields(self):
    """filePath und fileName sind Pflichtfelder."""
    track = Track(filePath="/test/song.mp3", fileName="song.mp3")
    assert track.filePath == "/test/song.mp3"
    assert track.fileName == "song.mp3"

  def test_default_values(self):
    """Alle optionalen Felder haben sinnvolle Defaults."""
    track = Track(filePath="/t.mp3", fileName="t.mp3")
    assert track.artist == "Unknown"
    assert track.title == "Unknown"
    assert track.genre == "Unknown"
    assert track.duration == 0.0
    assert track.bpm == 0.0
    assert track.keyNote == ""
    assert track.keyMode == ""
    assert track.camelotCode == ""
    assert track.energy == 0
    assert track.bass_intensity == 0
    assert track.mix_in_point == 0.0
    assert track.mix_out_point == 0.0
    assert track.mix_in_bars == 0
    assert track.mix_out_bars == 0

  def test_custom_values(self):
    """Benutzerdefinierte Werte werden korrekt gesetzt."""
    track = Track(
      filePath="/music/track.mp3",
      fileName="Artist - Title.mp3",
      artist="Test DJ",
      title="Club Banger",
      genre="Techno",
      duration=360.0,
      bpm=135.0,
      keyNote="D",
      keyMode="Minor",
      camelotCode="7A",
      energy=85,
      bass_intensity=80,
      mix_in_point=30.0,
      mix_out_point=330.0,
      mix_in_bars=16,
      mix_out_bars=176,
    )
    assert track.bpm == 135.0
    assert track.camelotCode == "7A"
    assert track.energy == 85
    assert track.mix_in_bars == 16

  def test_track_is_dataclass(self):
    """Track ist ein Dataclass mit allen Feldern."""
    from dataclasses import fields
    track_fields = {f.name for f in fields(Track)}
    required = {
      'filePath', 'fileName', 'artist', 'title', 'genre',
      'duration', 'bpm', 'keyNote', 'keyMode', 'camelotCode',
      'energy', 'bass_intensity',
      'mix_in_point', 'mix_out_point', 'mix_in_bars', 'mix_out_bars',
    }
    assert required.issubset(track_fields), (
      f"Fehlende Felder: {required - track_fields}"
    )

  def test_mix_points_numeric_types(self):
    """Mix-Punkte sind float (Sekunden) bzw int (Bars)."""
    track = Track(filePath="/t.mp3", fileName="t.mp3",
                  mix_in_point=30.5, mix_out_point=270.3,
                  mix_in_bars=16, mix_out_bars=144)
    assert isinstance(track.mix_in_point, float)
    assert isinstance(track.mix_out_point, float)
    assert isinstance(track.mix_in_bars, int)
    assert isinstance(track.mix_out_bars, int)

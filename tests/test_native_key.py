"""Belegte native Tonartreihenfolge, enharmonische Eingaben und Unknown."""
import pytest

from hpg_core.ai_models.native_key import native_key_index


@pytest.mark.parametrize('mode,offset', [('Major', 0), ('Minor', 12)])
@pytest.mark.parametrize('note,index', [
    ('A', 0), ('Bb', 1), ('B', 2), ('C', 3), ('Db', 4), ('D', 5),
    ('Eb', 6), ('E', 7), ('F', 8), ('F#', 9), ('G', 10), ('Ab', 11),
    ('A#', 1), ('C#', 4), ('D#', 6), ('G#', 11), ('Gb', 9),
])
def test_native_key_table(note, index, mode, offset):
    assert native_key_index(note, mode) == index + offset


@pytest.mark.parametrize('note,mode', [
    ('', ''), (None, 'Major'), ('A', None), ('H', 'Major'),
    ('A', 'Dorian'), (True, 'Minor'), ([], 'Minor'), ('A', []),
])
def test_unknown_is_not_reported_as_a_major(note, mode):
    assert native_key_index(note, mode) is None

import json
import os
import random
from types import SimpleNamespace

import pytest

from hpg_core.playlist_selection import (
    empty_history,
    load_history,
    retain_membership,
    record_successful_export,
    select_tracks,
    validate_history,
    validate_playlist_length,
)


def _track(name, bpm=120):
    return SimpleNamespace(filePath=f"C:/music/{name}.mp3", bpm=bpm)


def _identity(track):
    return os.path.normcase(os.path.abspath(os.path.normpath(track.filePath)))


@pytest.mark.parametrize("value,expected", [(None, None), (0, None), (1, 1), (1000, 1000)])
def test_playlist_length_accepts_all_and_inclusive_range(value, expected):
    assert validate_playlist_length(value) == expected


@pytest.mark.parametrize("value", [True, False, -1, 1001, 2.0, "2"])
def test_playlist_length_rejects_non_integer_and_out_of_range(value):
    with pytest.raises(ValueError):
        validate_playlist_length(value)


def test_all_preserves_existing_track_input_exactly():
    first = _track("first")
    duplicate = _track("first")
    invalid = _track("invalid", float("nan"))

    selected, report = select_tracks([first, duplicate, invalid], 0)

    assert selected == [first, duplicate, invalid]
    assert report.requested is None
    assert report.selected == 3


def test_bounded_selection_uses_valid_unique_tracks_without_replacement():
    first = _track("first")
    selected, report = select_tracks(
        [first, _track("first"), _track("invalid", 0), _track("second")],
        8,
        empty_history(),
        rng=random.Random(1),
    )

    assert selected == [first, _track("second")]
    assert report.requested == 8
    assert report.eligible == 2
    assert report.selected == 2


def test_tracks_exported_longer_ago_receive_greater_selection_weight():
    tracks = [_track("old"), _track("middle"), _track("recent")]
    history = {
        "version": 1,
        "last_exported": {
            _identity(tracks[0]): 100,
            _identity(tracks[1]): 200,
            _identity(tracks[2]): 300,
        },
        "last_set": [],
    }

    class ChooseHighestWeight:
        def choices(self, population, weights, k):
            assert k == 1
            assert weights == [3, 2, 1]
            return [max(range(len(population)), key=weights.__getitem__)]

    selected, _report = select_tracks(tracks, 1, history, rng=ChooseHighestWeight())

    assert selected == [tracks[0]]


def test_same_last_track_set_is_avoided_when_an_alternative_exists():
    tracks = [_track("a"), _track("b"), _track("c")]
    history = {
        "version": 1,
        "last_exported": {
            _identity(tracks[0]): 10,
            _identity(tracks[1]): 20,
            _identity(tracks[2]): 0,
        },
        "last_set": [_identity(tracks[0]), _identity(tracks[1])],
    }

    class FirstChoice:
        def choices(self, population, weights, k):
            return [0]

    selected, report = select_tracks(tracks, 2, history, rng=FirstChoice())

    assert {_identity(track) for track in selected} != set(history["last_set"])
    assert report.avoided_previous_set is True


def test_ranking_refresh_reuses_current_membership_with_fresh_track_objects():
    current = [_track("b"), _track("d")]
    source = [_track(name, bpm=120 + index) for index, name in enumerate("abcd")]

    retained = retain_membership(source, current)

    assert [track.filePath for track in retained] == ["C:/music/b.mp3", "C:/music/d.mp3"]
    assert retained == [source[1], source[3]]
    assert retained[0] is source[1]


def test_ranking_refresh_fails_closed_when_a_current_track_is_missing():
    with pytest.raises(ValueError, match="fehlt im aktuellen Analyselauf"):
        retain_membership([_track("a")], [_track("missing")])


def test_successful_export_updates_history_atomically(tmp_path):
    path = tmp_path / "rotation.json"
    tracks = [_track("a"), _track("b")]

    history = record_successful_export(path, tracks, timestamp=1234)

    assert history["last_set"] == [_identity(track) for track in tracks]
    assert history["last_exported"] == {_identity(track): 1234 for track in tracks}
    assert load_history(path) == history
    assert json.loads(path.read_text(encoding="utf-8")) == history


def test_invalid_history_is_not_overwritten_by_export(tmp_path):
    path = tmp_path / "rotation.json"
    original = b"{invalid"
    path.write_bytes(original)

    with pytest.raises(ValueError):
        record_successful_export(path, [_track("a")], timestamp=1234)

    assert path.read_bytes() == original


def test_history_schema_rejects_duplicate_last_set_identity():
    with pytest.raises(ValueError):
        validate_history({
            "version": 1,
            "last_exported": {},
            "last_set": ["a", "a"],
        })

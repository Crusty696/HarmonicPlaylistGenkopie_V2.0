"""Tests fuer den PSSI-Phrasenleser (Rekordbox ANLZ0000.EXT)."""
from types import SimpleNamespace

import numpy as np
import pytest

from hpg_core.rekordbox_phrases import (
    PHRASE_LABELS_HIGH, PHRASE_LABELS_MIDLOW, phrases_from_anlz,
    phrase_grid_from_phrases,
)


class _Tag:
    def __init__(self, content):
        self.content = content


class _Pqtz:
    def __init__(self, times):
        self._times = np.asarray(times, dtype=float)

    def get(self):
        n = len(self._times)
        beats = np.array([(i % 4) + 1 for i in range(n)], dtype=np.int8)
        return beats, np.full(n, 128.0), self._times


class _Anlz:
    def __init__(self, tags):
        self._tags = tags

    def get_tag(self, key):
        if key not in self._tags:
            raise KeyError(key)
        return self._tags[key]


def _entry(index, beat, kind, fill=0, beat_fill=0):
    return SimpleNamespace(index=index, beat=beat, kind=kind, k1=0, k2=0, k3=0,
                           fill=fill, beat_fill=beat_fill)


def _beatgrid(n_beats, spb=0.46875):  # 128 BPM
    return [i * spb for i in range(n_beats)]


def test_mood_high_labels():
    assert PHRASE_LABELS_HIGH == {1: "Intro", 2: "Up", 3: "Down", 5: "Chorus", 6: "Outro"}
    assert PHRASE_LABELS_MIDLOW[1] == "Intro" and PHRASE_LABELS_MIDLOW[9] == "Chorus"
    assert PHRASE_LABELS_MIDLOW[8] == "Bridge" and PHRASE_LABELS_MIDLOW[10] == "Outro"


def test_phrasen_aus_high_mood_mit_zeiten_aus_pqtz():
    times = _beatgrid(129)
    pssi = _Tag(SimpleNamespace(mood=1, end_beat=129, entries=[
        _entry(1, 1, 1), _entry(2, 33, 2), _entry(3, 65, 5), _entry(4, 97, 6)]))
    phrases = phrases_from_anlz(_Anlz({"PSSI": pssi}), _Anlz({"PQTZ": _Pqtz(times)}), duration=60.0)
    assert [p["label"] for p in phrases] == ["Intro", "Up", "Chorus", "Outro"]
    assert phrases[0]["start_s"] == pytest.approx(0.0)
    assert phrases[1]["start_s"] == pytest.approx(times[32])
    assert phrases[0]["end_s"] == pytest.approx(phrases[1]["start_s"])
    assert phrases[-1]["end_s"] == pytest.approx(times[128])  # end_beat → Zeit
    assert all(p["mood"] == 1 for p in phrases)
    assert phrases[2]["kind"] == 5


def test_unbekannter_kind_wird_als_unbekannt_beschriftet_nicht_verworfen():
    times = _beatgrid(65)
    pssi = _Tag(SimpleNamespace(mood=2, end_beat=65, entries=[_entry(1, 1, 1), _entry(2, 17, 11), _entry(3, 33, 10)]))
    phrases = phrases_from_anlz(_Anlz({"PSSI": pssi}), _Anlz({"PQTZ": _Pqtz(times)}), duration=40.0)
    assert phrases[1]["label"] == "Unbekannt(11)" and phrases[2]["label"] == "Outro"


def test_beat_ausserhalb_des_beatgrids_wird_verworfen():
    times = _beatgrid(10)
    pssi = _Tag(SimpleNamespace(mood=1, end_beat=50, entries=[_entry(1, 1, 1), _entry(2, 40, 6)]))
    phrases = phrases_from_anlz(_Anlz({"PSSI": pssi}), _Anlz({"PQTZ": _Pqtz(times)}), duration=30.0)
    assert len(phrases) == 1
    assert phrases[0]["start_s"] == pytest.approx(0.0)
    assert phrases[0]["end_s"] == pytest.approx(30.0)


def test_ohne_pssi_oder_pqtz_leere_liste():
    assert phrases_from_anlz(_Anlz({}), _Anlz({}), duration=30.0) == []
    assert phrases_from_anlz(None, None, duration=30.0) == []


@pytest.mark.parametrize("duration", [None, True, 0.0, -1.0, float("nan"), float("inf")])
def test_ungueltige_dauer_liefert_keine_phrasen(duration):
    times = _beatgrid(33)
    pssi = _Tag(SimpleNamespace(
        mood=1, end_beat=33, entries=[_entry(1, 1, 1)],
    ))

    assert phrases_from_anlz(
        _Anlz({"PSSI": pssi}), _Anlz({"PQTZ": _Pqtz(times)}), duration
    ) == []


@pytest.mark.parametrize("bad_time", [-1.0, float("nan"), float("inf")])
def test_ungueltige_pqtz_zeiten_werden_verworfen(bad_time):
    times = [0.0, bad_time, 2.0]
    pssi = _Tag(SimpleNamespace(mood=1, end_beat=3, entries=[
        _entry(1, 1, 1), _entry(2, 2, 2), _entry(3, 3, 6),
    ]))

    phrases = phrases_from_anlz(
        _Anlz({"PSSI": pssi}), _Anlz({"PQTZ": _Pqtz(times)}), duration=3.0
    )

    assert [phrase["start_s"] for phrase in phrases] == [0.0, 2.0]
    assert all(
        np.isfinite(phrase["start_s"]) and np.isfinite(phrase["end_s"])
        for phrase in phrases
    )


def test_defekter_mittlerer_pssi_eintrag_verwirft_spaetere_nicht():
    times = _beatgrid(65)
    broken = SimpleNamespace(beat="kaputt", kind=2, fill=0)
    pssi = _Tag(SimpleNamespace(mood=1, end_beat=65, entries=[
        _entry(1, 1, 1), broken, _entry(3, 33, 6),
    ]))

    phrases = phrases_from_anlz(
        _Anlz({"PSSI": pssi}), _Anlz({"PQTZ": _Pqtz(times)}), duration=40.0
    )

    assert [phrase["label"] for phrase in phrases] == ["Intro", "Outro"]


def test_doppelte_geklemmte_startzeiten_werden_dedupliziert():
    times = _beatgrid(10)
    pssi = _Tag(SimpleNamespace(mood=1, end_beat=50, entries=[
        _entry(1, 1, 1), _entry(2, 40, 2), _entry(3, 50, 6),
    ]))

    phrases = phrases_from_anlz(
        _Anlz({"PSSI": pssi}), _Anlz({"PQTZ": _Pqtz(times)}), duration=30.0
    )

    grid = phrase_grid_from_phrases(phrases)
    assert grid == sorted(set(grid))
    assert all(left < right for left, right in zip(grid, grid[1:]))


def test_phrase_grid_sind_die_phrasenstarts_plus_ende():
    phrases = [
        {"start_s": 0.0, "end_s": 15.0, "label": "Intro", "mood": 1, "kind": 1, "fill": 0},
        {"start_s": 15.0, "end_s": 30.0, "label": "Up", "mood": 1, "kind": 2, "fill": 0},
    ]
    assert phrase_grid_from_phrases(phrases) == [0.0, 15.0, 30.0]
    assert phrase_grid_from_phrases([]) == []


def test_phrase_grid_verwirft_nicht_endliche_und_negative_punkte():
    phrases = [
        {"start_s": -1.0, "end_s": 2.0},
        {"start_s": float("nan"), "end_s": float("inf")},
    ]

    assert phrase_grid_from_phrases(phrases) == []

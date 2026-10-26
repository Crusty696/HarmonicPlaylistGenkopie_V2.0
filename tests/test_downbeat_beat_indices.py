"""Die musikalische Eins darf nicht von fehlenden Trackerpunkten abhaengen."""

import numpy as np
import pytest

from hpg_core import downbeat
from tests.test_downbeat import SR, _make_four_on_floor


@pytest.fixture(scope="module")
def known_one():
    audio = _make_four_on_floor(128.0, 120.0, 0.3)
    _, frames = downbeat.librosa.beat.beat_track(
        y=audio, sr=SR, hop_length=downbeat.HOP_LENGTH,
        start_bpm=128.0, bpm=128.0, trim=False,
    )
    return audio, frames


def _estimate(monkeypatch, audio, frames):
    monkeypatch.setattr(
        downbeat.librosa.beat, "beat_track", lambda **kwargs: (128.0, frames),
    )
    diagnostics = {}
    result = downbeat.estimate_first_downbeat(audio, SR, 128.0, diagnostics=diagnostics)
    return result, diagnostics


@pytest.mark.parametrize("change", [
    "full", "missing_one", "missing_two", "extra", "duplicate", "duplicate_all", "jitter",
])
def test_bekannte_eins_bleibt_bei_trackerfehlern_erhalten(monkeypatch, known_one, change):
    audio, baseline = known_one
    frames = baseline.copy()
    middle = len(frames) // 2
    if change == "missing_one":
        frames = np.delete(frames, middle)
    elif change == "missing_two":
        frames = np.delete(frames, [len(frames) // 3, 2 * len(frames) // 3])
    elif change == "extra":
        frames = np.sort(np.r_[frames, int((frames[middle] + frames[middle + 1]) / 2)])
    elif change == "duplicate":
        frames = np.sort(np.r_[frames, np.repeat(frames[middle], 5)])
    elif change == "duplicate_all":
        frames = np.repeat(frames, 2)
    elif change == "jitter":
        frames[0] += 4

    (anchor, confidence), diagnostics = _estimate(monkeypatch, audio, frames)

    assert confidence >= downbeat.DOWNBEAT_RELIABLE_MIN
    # Bekannte Takt-Eins, nicht nur die modulo eines Beats gleiche Kickphase.
    assert anchor == pytest.approx(0.3, abs=downbeat.EXACT_BEAT_SYNC_TOLERANCE_SECONDS)
    assert diagnostics["reason"] == "ok"


@pytest.mark.parametrize("change", ["half", "double", "reversed"])
def test_fremde_metrik_und_rueckwaertszeit_bleiben_gesperrt(monkeypatch, known_one, change):
    audio, frames = known_one
    if change == "half":
        frames = frames[::2]
    elif change == "double":
        frames = np.sort(np.r_[frames, ((frames[:-1] + frames[1:]) / 2).astype(int)])
    else:
        frames = frames[::-1]

    result, diagnostics = _estimate(monkeypatch, audio, frames)

    assert result == (0.0, 0.0)
    assert diagnostics["reason"] == ("invalidinput" if change == "reversed" else "incommensurate")


@pytest.mark.parametrize("duration", [40, 120])
def test_lokaler_metrik_retry_prueft_drei_echte_disjunkte_fenster(
    monkeypatch, known_one, duration,
):
    audio, frames = known_one
    audio = audio[:duration * SR]
    frames = frames[frames * downbeat.HOP_LENGTH < len(audio)]
    original_tracker = downbeat.librosa.beat.beat_track
    original_validator = downbeat.validate_beatgrid_windows
    calls, windows_seen = [], []

    def tracker(**kwargs):
        calls.append(kwargs)
        return original_tracker(**kwargs) if "bpm" in kwargs else (64.0, frames[::2])

    def validator(windows, *args, **kwargs):
        windows_seen.extend(windows)
        return original_validator(windows, *args, **kwargs)

    monkeypatch.setattr(downbeat.librosa.beat, "beat_track", tracker)
    monkeypatch.setattr(downbeat, "validate_beatgrid_windows", validator)
    anchor, confidence = downbeat.estimate_first_downbeat(audio, np.int64(SR), 128.0)

    assert anchor == pytest.approx(0.3, abs=downbeat.EXACT_BEAT_SYNC_TOLERANCE_SECONDS)
    assert confidence >= downbeat.DOWNBEAT_RELIABLE_MIN
    assert len(calls) == 2
    assert calls[1]["bpm"] == 128.0
    assert len(windows_seen) == downbeat.BEATGRID_MIN_WINDOWS
    previous_end = 0
    for offset, segment in windows_seen:
        start = round(offset * SR)
        assert start >= previous_end
        assert len(segment) <= 16 * SR
        assert np.shares_memory(segment, audio)
        np.testing.assert_array_equal(segment, audio[start:start + len(segment)])
        previous_end = start + len(segment)


def test_dateipipeline_kann_lokalen_retry_deaktivieren(monkeypatch, known_one):
    audio, frames = known_one
    calls = []

    def tracker(**kwargs):
        calls.append(kwargs)
        return 64.0, frames[::2]

    monkeypatch.setattr(downbeat.librosa.beat, "beat_track", tracker)
    result = downbeat.estimate_first_downbeat(audio, SR, 128.0, _allow_metric_retry=False)
    assert result == (0.0, 0.0)
    assert len(calls) == 1


@pytest.mark.parametrize("status", ["mismatch", "unverifiable", "unsupported"])
def test_lokaler_retry_ohne_audiofreigabe_bleibt_null(monkeypatch, known_one, status):
    audio, frames = known_one
    original_tracker = downbeat.librosa.beat.beat_track
    checks = []

    def tracker(**kwargs):
        return original_tracker(**kwargs) if "bpm" in kwargs else (64.0, frames[::2])

    def validator(*args, **kwargs):
        checks.append(True)
        return downbeat.BeatgridValidation(status, 3, 20.0)

    monkeypatch.setattr(downbeat.librosa.beat, "beat_track", tracker)
    monkeypatch.setattr(downbeat, "validate_beatgrid_windows", validator)
    diagnostics = {}
    assert downbeat.estimate_first_downbeat(audio, SR, 128.0, diagnostics=diagnostics) == (0.0, 0.0)
    assert diagnostics["reason"] == "incommensurate"
    assert checks == [True]


def test_lokaler_retry_mit_schwachem_voting_prueft_keine_freigabe(monkeypatch, known_one):
    audio, frames = known_one
    original_tracker = downbeat.librosa.beat.beat_track

    def tracker(**kwargs):
        return original_tracker(**kwargs) if "bpm" in kwargs else (64.0, frames[::2])

    def unexpected_validation(*args, **kwargs):
        pytest.fail("Schwache Konfidenz darf keine Freigabe anfordern")

    monkeypatch.setattr(downbeat.librosa.beat, "beat_track", tracker)
    monkeypatch.setattr(downbeat, "_bar_phase_confidence", lambda votes: 0.299)
    monkeypatch.setattr(downbeat, "validate_beatgrid_windows", unexpected_validation)
    assert downbeat.estimate_first_downbeat(audio, SR, 128.0) == (0.0, 0.0)


def test_echtes_stilles_endfenster_verhindert_lokale_freigabe(monkeypatch, known_one):
    original_audio, frames = known_one
    audio = original_audio.copy()
    audio[80 * SR:] = 0.0
    original_tracker = downbeat.librosa.beat.beat_track
    original_validator = downbeat.validate_beatgrid_windows
    checks = []

    def tracker(**kwargs):
        return original_tracker(**kwargs) if "bpm" in kwargs else (64.0, frames[::2])

    def validator(*args, **kwargs):
        result = original_validator(*args, **kwargs)
        checks.append(result)
        return result

    monkeypatch.setattr(downbeat.librosa.beat, "beat_track", tracker)
    monkeypatch.setattr(downbeat, "validate_beatgrid_windows", validator)
    assert downbeat.estimate_first_downbeat(audio, SR, 128.0) == (0.0, 0.0)
    assert len(checks) == 1
    assert checks[0].status == "unverifiable"
    assert checks[0].windows_checked == 2


@pytest.mark.parametrize("disturbance", ["none", "missing", "extra49", "extra51", "combined"])
def test_wandernder_lag_veraendert_keine_physischen_beatnummern(disturbance):
    labels = np.arange(128)
    # Ueberschreitet globale Rundungsgrenzen, waehrend jeder lokale Abstand
    # weiterhin auf genau einen Beat rundet. Kein Audioqualitaets-Grenzwert.
    times = 0.3 + labels * 0.5 + 0.3 * np.sin(np.linspace(0, 4 * np.pi, 128))
    assert np.all(np.rint(np.diff(times) / 0.5) == 1)
    if disturbance in ("missing", "combined"):
        times, labels = np.delete(times, [30, 80]), np.delete(labels, [30, 80])
    if disturbance in ("extra49", "extra51", "combined"):
        fraction = 0.49 if disturbance == "extra49" else 0.51
        extra = times[49] + fraction * 0.5
        times, labels = np.insert(times, 50, extra), np.insert(labels, 50, -1)

    keep, numbers = downbeat._number_tracker_beats(times, 0.5)

    assert np.all(labels[keep] >= 0)
    np.testing.assert_array_equal(numbers, labels[keep])
    np.testing.assert_array_equal(np.sort(labels[keep]), labels[labels >= 0])


@pytest.mark.parametrize("times,expected_keep,expected_numbers", [
    ([0, .2, .49, .51, .75, 1, 2, 3, 4], [0, 5, 6, 7, 8], [0, 1, 2, 3, 4]),
    ([0, .51, 1, 3, 4, 5], [0, 2, 3, 4, 5], [0, 1, 3, 4, 5]),
    ([0, .75, 1.25, 2, 3, 4], [0, 1, 3, 4, 5], [0, 1, 2, 3, 4]),
    ([0, .51, 1.49, 2.49, 3.49], [0, 1, 2, 3, 4], [0, 1, 2, 3, 4]),
    ([0, .6, 1, 1.4, 1.6, 2, 3, 4], [0, 2, 5, 6, 7], [0, 1, 2, 3, 4]),
    # Ein Extra ohne folgenden echten Beat bleibt zeitlich unentscheidbar;
    # die spaeteren echten Beats werden trotzdem nicht umnummeriert.
    ([0, .51, 2, 3, 4], [0, 1, 2, 3, 4], [0, 1, 2, 3, 4]),
])
def test_lokale_auswahl_behaelt_luecken_und_prueft_nach_neuem_anker(
    times, expected_keep, expected_numbers,
):
    keep, numbers = downbeat._number_tracker_beats(np.asarray(times), 1.0)
    np.testing.assert_array_equal(keep, expected_keep)
    np.testing.assert_array_equal(numbers, expected_numbers)


def test_fuehrendes_extra_aendert_nur_den_relativursprung():
    times = np.asarray([0.49, 1, 2, 3, 4, 5])
    keep, numbers = downbeat._number_tracker_beats(times, 1.0)
    # Der erste Trackerpunkt definiert Beat null, nicht die musikalische Eins.
    real = keep > 0
    np.testing.assert_array_equal(numbers[real] - keep[real], np.zeros(np.sum(real)))
    np.testing.assert_array_equal(keep, np.arange(len(times)))


@pytest.mark.parametrize("extra", [None, 0.49, 0.51])
def test_bekannte_eins_mit_wanderndem_trackerlag_und_luecken(
    monkeypatch, known_one, extra,
):
    audio, frames = known_one
    frames = frames + np.rint(
        0.2 * np.sin(np.linspace(0, 4 * np.pi, len(frames))) * SR / downbeat.HOP_LENGTH
    ).astype(int)
    if extra is not None:
        frames = np.delete(frames, [len(frames) // 3, 2 * len(frames) // 3])
        inserted = round(frames[len(frames) // 2] + extra * (60 / 128) * SR / downbeat.HOP_LENGTH)
        frames = np.sort(np.r_[frames, inserted])
    (anchor, confidence), _ = _estimate(monkeypatch, audio, frames)
    assert anchor == pytest.approx(0.3, abs=downbeat.EXACT_BEAT_SYNC_TOLERANCE_SECONDS)
    assert confidence >= downbeat.DOWNBEAT_RELIABLE_MIN

"""Getrennte numerische Vorproben, realer Replay-Pilot und native Bruecke.

Keine Gates, Bootstrap-Verfahren, Fitresultate oder Seeds werden ersetzt.
Synthetische Labels sind keine Musik-Ground-Truth. Eine rote GUI-Bruecke
bleibt rot; bestandene Teilstufen sind kein Fullchain-Nachweis.
"""
import json

import pytest

from tools import rate_transitions as rate
from tests.hearing_e2e_fixtures import FIT_SEED, numeric_gate_rows, starting_weights


@pytest.mark.gui
@pytest.mark.regression
def test_hearing_refresh_actual_gui_settings_start_real_worker(tmp_path, qtbot, monkeypatch):
    """Schnelle Reproduktion ohne Audit-/Fit-Wiederholung oder Settings-Filter."""
    from tests.hearing_e2e_fixtures import producer_fixture, managed_hearing_jobs
    from tests.test_main_window import _window
    config, tracks, _inventory = producer_fixture(tmp_path, count=1)
    window = _window(qtbot, monkeypatch)
    window.analyzed_raw_tracks = tracks
    window._refresh_hearing_ranking()
    worker = window.playlist_worker
    try:
        assert worker is not None, window.analytics_panel.hearing_status.text()
        assert window._hearing_refresh_worker is worker
        qtbot.waitUntil(lambda: window.playlist_worker is None, timeout=30000)
        assert window.current_generation_result is not None
    finally:
        if window.playlist_worker is not None:
            window.playlist_worker.request_cancel()
            qtbot.waitUntil(lambda: window.playlist_worker is None, timeout=30000)
    finished = []
    with pytest.raises(AssertionError, match="Eigener Testabbruch"):
        with managed_hearing_jobs(qtbot) as owned:
            owned.append(window)
            window._refresh_hearing_ranking()
            assert window.playlist_worker is not None
            window.playlist_worker.finished.connect(lambda: finished.append(True))
            raise AssertionError("Eigener Testabbruch")
    assert finished and window.playlist_worker is None and window._hearing_worker is None
    from hpg_core.hearing_workflow import create_set
    from hpg_core.hearing_jobs import HearingLoadWorker
    prepared = create_set(config)
    loader_window = _window(qtbot, monkeypatch)
    load_finished = []
    with pytest.raises(AssertionError, match="Eigener Ladeabbruch"):
        with managed_hearing_jobs(qtbot) as owned:
            owned.append(loader_window)
            loader = HearingLoadWorker(prepared.output_dir, loader_window)
            loader.finished.connect(lambda: load_finished.append(True))
            assert loader_window._start_hearing_worker(loader, "open")
            raise AssertionError("Eigener Ladeabbruch")
    assert load_finished and loader_window._hearing_worker is None and loader_window.playlist_worker is None


def test_actual_producer_replay_resource_pilot(tmp_path):
    """Ein reales Paar vor Skalierung; kein erfundenes Audit-Ergebnis."""
    from tests.hearing_e2e_fixtures import producer_fixture, replay_proposal
    config, tracks, inventory = producer_fixture(tmp_path, count=1)
    proposal, elapsed = replay_proposal(config, fit=False)
    assert proposal["audit_passed"] is True
    assert proposal["audit"]["ok"] is True
    import hashlib
    assert inventory == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in inventory}
    print(json.dumps({"scope": "actual_producer_replay_pilot", "seconds": elapsed,
                      "sources": len(tracks), "physical_audio_bytes": (config.source_roots[0] / "shared.wav").stat().st_size,
                      "audit": proposal["audit"]}, default=str))


@pytest.mark.gui
@pytest.mark.integration
def test_real_producer_audit_native_fit_confirm_apply_actual_ranking(tmp_path, qtbot, monkeypatch):
    """Die numerische Vorprobe darf diese reale Bruecke nicht ersetzen."""
    from tests.hearing_e2e_fixtures import run_native_bridge
    evidence = run_native_bridge(tmp_path, qtbot, monkeypatch)
    assert evidence["producer_pairs"] == 64
    assert evidence["audit"]["pairs"] == 64 and evidence["audit"]["clips"] == 128
    assert evidence["proposal"]["audit_passed"]
    assert evidence["proposal"]["fit_status"] == "passed"
    assert set(evidence["proposal"]["gate_updates"]) == {"Psytrance"}
    assert evidence["rejected_without_write"]
    assert evidence["applied"] == {"persisted": True, "effective_reload": True, "error": "",
                                    "path": str(tmp_path / "active-preferences.json")}
    assert evidence["rank_before"] != evidence["rank_after"]
    # Diese reale Fixture aendert Scores, nicht die Reihenfolge. Kein Rangwechsel-Beleg.
    assert evidence["ordered_keys_before"] == evidence["ordered_keys_after"]
    assert set(evidence["ordered_keys_before"]) == set(evidence["ordered_keys_after"])
    assert evidence["rank_one_before"] == evidence["ordered_keys_before"][0]
    assert evidence["rank_one_after"] == evidence["ordered_keys_after"][0]
    assert evidence["rank_one_before"] == evidence["rank_one_after"]
    assert evidence["selected_after"] == evidence["rank_one_after"]
    assert evidence["cleanup_warnings"] == []
    assert evidence["ranking_published"]
    assert evidence["sources_unchanged"] and evidence["cache_unchanged"]
    print(json.dumps({key: value for key, value in evidence.items() if key not in {"proposal", "audit"}}, default=str))


@pytest.mark.parametrize("three_notes", [False, True])
def test_numeric_fixture_real_gates_positive_without_seed_search(tmp_path, three_notes):
    rows = numeric_gate_rows(tmp_path, three_notes=three_notes)
    if three_notes:
        weights, diagnose = rate.fit_dreinoten_genre(rows, FIT_SEED, starting_weights())
        assert diagnose["unabhaengige_trackpaare"] == 400
        assert diagnose["zusammenhangskomponenten"] == 400
        assert diagnose["folds"] == 5
        assert all(target["mindestklasse_train"] >= 100 for target in diagnose["ziele"].values())
        assert all(target["auc_unten_95"] > .5 for target in diagnose["ziele"].values())
    else:
        weights, _rank, diagnose = rate._fit_kandidaten_genre("Psytrance", rows, FIT_SEED, starting_weights())
        train, hold, _pairs, _clips = rate.holdout_nach_tracks_mit_diagnose(rows, seed=FIT_SEED)
        assert not {t for row in train for t in row["tracks"]} & {t for row in hold for t in row["tracks"]}
        assert diagnose["belastbar_note"]
        assert len(diagnose["identifizierbar"]) == 1
        assert diagnose["paare_mit_wahl_train"] >= 10
        assert all(low > 0 for low, high in diagnose["intervalle_paarvergleich"].values())
    print(json.dumps({"scope": "numeric_fixture_only", "seed": FIT_SEED,
                      "observations": len(rows), "independent_components": 400 if three_notes else 64,
                      "three_notes": three_notes, "diagnose": diagnose}, ensure_ascii=False))
    assert weights is not None, diagnose
    assert diagnose["uebernommen"] is True


@pytest.mark.parametrize("three_notes", [False, True])
def test_numeric_fixture_constant_signal_keeps_real_gates_closed(tmp_path, three_notes):
    rows = numeric_gate_rows(tmp_path, three_notes=three_notes, null_effect=True)
    if three_notes:
        weights, diagnose = rate.fit_dreinoten_genre(rows, FIT_SEED, starting_weights())
    else:
        weights, _rank, diagnose = rate._fit_kandidaten_genre("Psytrance", rows, FIT_SEED, starting_weights())
    assert weights is None and diagnose["uebernommen"] is False

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


@pytest.mark.gui
@pytest.mark.integration
def test_three_note_native_fit_worker_returns_bound_draft_from_real_producer(
    tmp_path, qtbot, monkeypatch,
):
    """Dreinoten-Satz durchläuft Producer, Rating, GUI-Worker, Audit und Fit."""
    from dataclasses import replace
    from PyQt6.QtWidgets import QDialog

    from hpg_core import hearing_panel
    from hpg_core.hearing_ratings import save_rating
    from hpg_core.hearing_workflow import create_set
    from tests.hearing_e2e_fixtures import FIT_SEED, managed_hearing_jobs, producer_fixture
    from tests.test_main_window import _window
    from tools import rate_transitions as rate
    import main

    config, _tracks, _inventory = producer_fixture(tmp_path, count=1)
    config = replace(config, three_notes=True)
    prepared = create_set(config)
    metrics = rate.lies_csv(prepared.output_dir / "merkmale.csv")
    best = None
    for row in metrics:
        note = 5 if float(row["loudness"]) > .5 else 2
        for dimension in ("track_note", "technik_note", "gesamt_note"):
            save_rating(prepared.output_dir, "/note", {
                "pair_id": row["pair_id"], "clip_id": row["clip_id"],
                "dimension": dimension, "note": note if dimension != "technik_note" else 4,
            })
        if best is None or float(row["loudness"]) > float(best["loudness"]):
            best = row
    assert best is not None
    save_rating(prepared.output_dir, "/bester", {
        "pair_id": best["pair_id"], "clip_id": best["clip_id"],
    })

    preference_path = tmp_path / "active-preferences.json"
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(preference_path))
    window = _window(qtbot, monkeypatch)
    window._hearing_set_path = str(prepared.output_dir)
    window._hearing_cache_path = str(config.cache)

    class AcceptedFitDialog:
        def __init__(self, cache, *, audit_only, single, three_note, parent):
            assert cache == str(config.cache)
            assert not audit_only and not single and three_note
            self.cache = cache
            self.seed, self.genres = FIT_SEED, ()

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(hearing_panel, "HearingFitDialog", AcceptedFitDialog)
    proposals, warnings = [], []

    def capture_result(dialog):
        qtbot.addWidget(dialog)
        proposals.append(dialog.proposal)
        assert not dialog.apply_button.isEnabled()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(hearing_panel.HearingCalibrationResultDialog, "exec", capture_result)
    monkeypatch.setattr(main.QMessageBox, "warning", lambda *args: warnings.append(str(args[-1])))

    with managed_hearing_jobs(qtbot) as owned:
        owned.append(window)
        window._fit_hearing_set()
        assert window._hearing_worker is not None and window._hearing_action == "fit"
        qtbot.waitUntil(
            lambda: window._hearing_worker is None and bool(proposals or warnings),
            timeout=120000,
        )

    assert not warnings
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["audit_passed"] and proposal["fit_status"] == "passed"
    assert proposal["candidate_report"]["dreinoten"] is True
    assert proposal["candidate_report"]["diagnose"]["rating_schema"] == "three_notes_v1"
    assert proposal["gate_updates"] == {}
    assert not preference_path.exists()


@pytest.mark.gui
@pytest.mark.integration
def test_applied_preferences_reorder_visible_mixpoint_ranking(
    tmp_path, qtbot, monkeypatch, request
):
    """Persistierte Gewichte muessen die sichtbare Mixpunktreihenfolge neu berechnen."""
    from tests.hearing_e2e_fixtures import managed_hearing_jobs, producer_fixture
    from tests.test_main_window import _window
    from hpg_core import candidate_preferences as cp, playlist

    preference_path = tmp_path / "candidate-preferences.json"
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(preference_path))
    cp.reset_cache()
    request.addfinalizer(cp.reset_cache)

    fixture_root = tmp_path / "synthetic"
    fixture_root.mkdir()
    config, tracks, _inventory = producer_fixture(fixture_root, count=1)
    window = _window(qtbot, monkeypatch)
    with managed_hearing_jobs(qtbot) as owned:
        owned.append(window)
        window.analyzed_raw_tracks = tracks

        def persist_one_hot_weight(factor):
            weights = {
                key: 1.0 if key == f"kandidaten_{factor}_weight" else 0.0
                for key in cp.GEWICHT_SCHLUESSEL
            }
            cp.merge_user_preferences_atomically({
                "Psytrance": {**weights, "schema_rang": ["sektion"]}
            })
            cp.reset_cache()
            playlist.reset_pair_candidate_cache()

        def refresh_and_wait():
            window._refresh_hearing_ranking()
            qtbot.waitUntil(
                lambda: window.playlist_worker is None
                and window.current_generation_result is not None,
                timeout=30000,
            )
            result = window.current_generation_result
            assert len(result.boundaries) == 1
            assert len(result.boundaries[0].snapshots) == 2
            return result

        persist_one_hot_weight("bpm")
        before = refresh_and_wait()
        before_order = [item.t_in for item in before.boundaries[0].snapshots]
        assert before_order == [16.0, 32.0]
        assert before.boundaries[0].snapshots[0].rang == 1

        persist_one_hot_weight("harmonic")
        after = refresh_and_wait()
        after_order = [item.t_in for item in after.boundaries[0].snapshots]
        assert after is not before
        assert after_order == [32.0, 16.0]
        assert after.boundaries[0].snapshots[0].rang == 1
        assert after.scoring_context_dict()["candidate_tolerances_by_genre"]["Psytrance"][
            "kandidaten_harmonic_weight"
        ] == 1.0
        assert json.loads(preference_path.read_text(encoding="utf-8"))["Psytrance"][
            "kandidaten_harmonic_weight"
        ] == 1.0


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

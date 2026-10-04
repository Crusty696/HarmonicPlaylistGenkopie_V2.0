"""Numerische Vorproben und separater realer synthetischer Producer-Satz.

Labels enthalten absichtlich einen starken Effekt. Keine Nutzerpraeferenz,
keine Musikqualitaet und kein positiver GUI-End-to-End-Nachweis.
Seed und Stichprobe sind vor dem ersten numerischen Lauf festgelegt.
"""
from tools import rate_transitions as rate
from contextlib import contextmanager


FIT_SEED = 20260820


def numeric_gate_rows(root, *, three_notes=False, null_effect=False):
    """Disjunkte Trackpaare statt mehrfach gezaehlter Varianten erzeugen."""
    count = 400 if three_notes else 64
    factor = rate.KANDIDATEN_TEILWERTE[0]
    rows = []
    for index in range(count):
        tracks = tuple(str(root / f"pair-{index:04d}-{side}.wav") for side in ("a", "b"))
        for version in range(2):
            if three_notes:
                good = index % 2 == 0
                value = (.75 if good else .25) + (.01 if version else -.01)
            else:
                good = version == 1
                distance = .12 + (index % 8) * .045
                value = .5 + (distance if good else -distance)
            features = {name: .5 for name in rate.KANDIDATEN_TEILWERTE}
            features[factor] = .5 if null_effect else value
            note = 5 if good else 2
            row = {"pair_id": f"{index + 1:03d}", "clip_id": f"{index + 1:03d}_k{version + 1}",
                   "tracks": tracks, "genre": "Psytrance", "genre_a": "Psytrance", "genre_b": "Psytrance",
                   "merkmale": features, "note": note, "bewertung": note,
                   "gewaehlt": version == 1, "schemata_out": ["analyzer"], "schemata_in": ["analyzer"]}
            if three_notes:
                row.update(track_note=note, technik_note=note, gesamt_note=note)
            rows.append(row)
    return rows


def starting_weights():
    return {f"kandidaten_{name}_weight": .1 for name in rate.KANDIDATEN_TEILWERTE}


def producer_fixture(root, *, count=64):
    """Eine eigene 120-s-Aufnahme mit Hardlinks; keine 64 unabhaengigen Musikaufnahmen.

    Getrennte synthetische Metadaten-/Pfadkomponenten, kein DSP-Mock.
    """
    import os
    import hashlib
    import sqlite3
    import json
    import numpy as np
    import soundfile as sf
    from hpg_core.models import Track
    from hpg_core.mix_candidates import MixCandidate
    from hpg_core.caching import CACHE_VERSION, track_to_dict
    from hpg_core.hearing_workflow import PrepareConfig

    sources = root / "sources"
    sources.mkdir()
    sr, duration = 8000, 120
    seconds = np.arange(sr * duration, dtype=np.float64) / sr
    phase = seconds % .5
    # Deterministischer Viertelpuls plus leiser Sinus, keinerlei Benutzermedien.
    audio = .2 * np.exp(-phase * 80) * np.sin(2 * np.pi * 100 * seconds)
    audio += .025 * np.sin(2 * np.pi * 220 * seconds)
    shared = sources / "shared.wav"
    sf.write(shared, audio, sr, subtype="PCM_16")
    tracks = []
    for index in range(count):
        for side in ("a", "b"):
            path = sources / f"pair-{index:04d}-{side}.wav"
            os.link(shared, path)
            track = Track(filePath=str(path), fileName=path.name)
            track.bpm, track.duration, track.camelotCode = 120., float(duration), "8A"
            track.detected_genre, track.phrase_unit = "Psytrance", 8
            track.first_downbeat, track.downbeat_confidence = 0., 1.
            track.beatgrid_source, track.beatgrid_status = "rekordbox", "verified"
            track.beatgrid_windows_checked, track.beatgrid_max_phase_error_ms = 3, 0.
            track.analysis_mode, track.outro_covered = "librosa_full_or_tail", True
            track.energy = 70
            track.sections = [
                {"label": "intro", "start_time": 0., "end_time": 8., "avg_energy": 30},
                {"label": "main", "start_time": 8., "end_time": 48., "avg_energy": 70},
                {"label": "outro", "start_time": 48., "end_time": 120., "avg_energy": 30},
            ]
            for section in track.sections:
                section.update(start_bar=int(section["start_time"] / 2),
                               end_bar=int(section["end_time"] / 2), analysis_status="analyzed")
            track.analysis_coverage = [{"start": 0., "end": 120.}]
            def candidate(t, lufs, alone, camelot="8A"):
                return MixCandidate(t=t, schema=["pssi_phrase"], provenance="synthetic_fixture", confidence=.9,
                    section_label="main", phrase_label="Chorus",
                    neuheit=.6, traegt_allein=alone,
                    groove_pattern_lokal=[.25 if s % 4 == 0 else 0. for s in range(16)],
                    bass_pattern_lokal=[.25 if s % 4 == 0 else 0. for s in range(16)],
                    syncopation_lokal=.2, percussive_ratio_lokal=.5, sub_energy=.5,
                    bass_punch=2., bass_rms_dbfs=-20., kick_aktiv=True, camelot_lokal=camelot,
                    key_confidence_lokal=.9, timbre_fingerprint_lokal=[1. / (n + 1) for n in range(13)],
                    brightness_lokal=50, flatness_lokal=.1, avg_mids_lokal=40., avg_highs_lokal=20.,
                    energy_lokal=70, energy_trend="rising", lufs_lokal=lufs,
                    mood={"pssi_mood": 1, "brightness": 50., "flatness": .1, "key_mode": "Minor"},
                    vocal_aktiv_lokal=False)
            distance = .12 + (index % 8) * .045
            track.mix_out_candidates = [candidate(32., -10., False)] if side == "a" else []
            # Zweiter, alternierender Faktor: identifizierbar, aber kein Labelsignal.
            # Erlaubt einen echten Gewichts-/Rankingwechsel statt Ein-Faktor-No-op.
            track.mix_in_candidates = ([candidate(16., -10. + 3 * (.5 - distance), True,
                                                   "9A" if index % 2 == 0 else "8A"),
                                        candidate(32., -10. + 3 * (.5 + distance), True,
                                                   "8A" if index % 2 == 0 else "9A")] if side == "b" else [])
            tracks.append(track)
    cache = root / "fixture-cache.db"
    with sqlite3.connect(cache) as connection:
        connection.execute("CREATE TABLE cache (key TEXT PRIMARY KEY, filepath TEXT, version INTEGER, data TEXT)")
        connection.execute("INSERT INTO cache VALUES ('version','system',?,'metadata')", (CACHE_VERSION,))
        connection.executemany("INSERT INTO cache VALUES (?,?,?,?)", [
            (str(index), track.filePath, CACHE_VERSION, json.dumps(track_to_dict(track)))
            for index, track in enumerate(tracks)])
    # Nur Inhalt sichern: Hardlinks bleiben eigene temporaere Testressourcen.
    inventory = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources.iterdir()}
    config = PrepareConfig(mode="kandidaten", output_dir=root / "hearing-set", cache=cache,
                           count=count, seed=FIT_SEED, only_genre="Psytrance", tracks_once=True,
                           max_versions_per_pair=4, energy_direction="maintain", workers=1,
                           source_roots=(sources,))
    return config, tracks, inventory


def replay_proposal(config, *, fit=True):
    """Tatsaechlicher Producer und nativer Spawn-Worker, keine Gate-Ersatzwerte."""
    import time
    from hpg_core.hearing_workflow import create_set
    from hpg_core.hearing_jobs import HearingCalibrationWorker
    started = time.perf_counter()
    result = create_set(config)
    worker = HearingCalibrationWorker(result.output_dir, config.cache, fit=fit, seed=FIT_SEED,
                                      genres=("Psytrance",), timeout=600)
    results = []
    worker.completed.connect(results.append)
    worker.run()
    assert len(results) == 1 and results[0]["ok"], results
    assert not results[0].get("cleanup_warning"), results
    return results[0]["proposal"], time.perf_counter() - started


@contextmanager
def managed_hearing_jobs(qtbot):
    """Auch bei Assertion-Abbruch nur eigene GUI-Worker beenden und aufraeumen."""
    owned = []
    try:
        yield owned
    finally:
        for window in owned:
            if window._hearing_worker is not None or window.playlist_worker is not None:
                # Keine Folgeaktion/kein Modal waehrend eigener Fehler-Aufraeumung.
                window._close_pending = True
            for name in ("_hearing_worker", "playlist_worker"):
                worker = getattr(window, name)
                if worker is not None:
                    worker.request_cancel()
                    qtbot.waitUntil(lambda owner=window, attr=name: getattr(owner, attr) is None, timeout=30000)


def run_native_bridge(root, qtbot, monkeypatch):
    with managed_hearing_jobs(qtbot) as owned:
        return _run_native_bridge(root, qtbot, monkeypatch, owned)


def _run_native_bridge(root, qtbot, monkeypatch, owned):
    """Realer Producer -> CSV-Ratings -> nativer Fit -> bestaetigtes Apply -> GUI-Ranking.

    Ersetzt nur Benutzerklicks und die Startup-Abhaengigkeitswarnung. Kein
    Scorer, Producer, Auditor, Fit, Bootstrap oder Worker wird ersetzt.
    Synthetische Labels folgen der lokalen Lautheit, nicht Musik-Ground-Truth.
    """
    import hashlib
    import json
    import time
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QDialogButtonBox, QMessageBox
    from hpg_core import candidate_preferences as cp, hearing_panel
    from hpg_core.hearing_workflow import create_set
    from hpg_core.hearing_ratings import save_rating
    from hpg_core.pair_candidates import score_pair
    from tools import audit_candidate_set as audit
    from tests.test_main_window import _window
    import pytest
    import main

    def fingerprint(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    started = time.perf_counter()
    config, tracks, inventory = producer_fixture(root)
    cache_before = fingerprint(config.cache)
    prepared = create_set(config)
    features = rate.lies_csv(prepared.output_dir / "merkmale.csv")
    manifest = json.loads((prepared.output_dir / rate.KANDIDATEN_MANIFEST_NAME).read_text(encoding="utf-8"))
    by_path = {track.filePath: track for track in tracks}
    by_id = {row["clip_id"]: row for row in features}
    selected_paths = set()
    for pair in manifest["pairs"]:
        a, b = by_path[pair["track_a"]], by_path[pair["track_b"]]
        assert not selected_paths & {a.filePath, b.filePath}
        selected_paths.update((a.filePath, b.filePath))
        ranked = audit._rank_pair_from_manifest(a, b, manifest)
        assert len(ranked) == len(pair["clips"]) == 2
        tolerances = manifest["scoring_snapshot"]["candidate_tolerances_by_genre"]["Psytrance"]
        for clip, pc in zip(pair["clips"], ranked):
            row = by_id[clip["clip_id"]]
            score, factors, _flags = score_pair(a, b, pc.out_a, pc.in_b, pc.blend_bars,
                energy_direction="maintain", harmonic_strictness=7,
                allow_experimental=True, tolerances=tolerances, bass_swap_geplant=True)
            assert float(row["score"]) == pytest.approx(score, abs=1e-6)
            assert {name: float(row[name]) for name in rate.KANDIDATEN_TEILWERTE} == pytest.approx(factors, abs=1e-6)
            save_rating(prepared.output_dir, "/note", {"pair_id": pair["pair_id"],
                        "clip_id": row["clip_id"], "note": 5 if factors["loudness"] > .5 else 2})
        winner = max(pair["clips"], key=lambda clip: float(by_id[clip["clip_id"]]["loudness"]))
        save_rating(prepared.output_dir, "/bester", {"pair_id": pair["pair_id"], "clip_id": winner["clip_id"]})
    assert len(selected_paths) == 128
    assert not list(prepared.output_dir.rglob("*.wav"))

    override = root / "active-preferences.json"
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(override))
    cp.reset_cache()
    window = _window(qtbot, monkeypatch)
    owned.append(window)
    warnings, results, starts, modals = [], [], [], []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(str(args[-1])))
    real_start = window._start_hearing_worker
    def start(worker, action):
        starts.append(action)
        worker.completed.connect(lambda result: results.append((action, result)))
        return real_start(worker, action)
    monkeypatch.setattr(window, "_start_hearing_worker", start)

    real_fit_exec = hearing_panel.HearingFitDialog.exec
    def fit_exec(dialog):
        assert window._hearing_native_active
        QTimer.singleShot(0, lambda: dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click())
        return real_fit_exec(dialog)
    monkeypatch.setattr(hearing_panel.HearingFitDialog, "exec", fit_exec)
    real_result_exec = hearing_panel.HearingCalibrationResultDialog.exec
    accept = False
    def result_exec(dialog):
        modals.append(dialog.proposal)
        assert window._hearing_worker is None and window._hearing_native_active
        assert not override.exists()
        QTimer.singleShot(0, dialog.apply_button.click if accept and dialog.apply_button.isEnabled() else dialog.reject)
        return real_result_exec(dialog)
    monkeypatch.setattr(hearing_panel.HearingCalibrationResultDialog, "exec", result_exec)

    # Nur zwei synthetische Tracks fuer die sichtbare Playlist, nicht 128!
    a, b = tracks[2:4]
    a.energy, b.energy = 60, 70
    window.analyzed_raw_tracks = [a, b]
    window._hearing_set_path, window._hearing_cache_path = str(prepared.output_dir), str(config.cache)
    before = window.current_generation_result
    def ranking(result):
        return [(snapshot.t_in, snapshot.score) for snapshot in result.boundaries[0].snapshots]
    window._fit_hearing_set()
    qtbot.waitUntil(lambda: window._hearing_worker is None and bool(modals or warnings), timeout=600000)
    assert not warnings, warnings
    assert all(not result.get("cleanup_warning") for _action, result in results), results
    proposal = modals[0]
    assert proposal["audit_passed"] and proposal["fit_status"] == "passed", proposal
    assert proposal["gate_updates"], proposal["diagnose"]
    assert starts == ["fit"] and not override.exists()
    assert window.current_generation_result is before
    assert inventory == {path: fingerprint(path) for path in inventory}
    assert cache_before == fingerprint(config.cache)
    rejected_without_write = True
    print(json.dumps({"scope": "actual_native_proposal_before_confirmation", "seed": FIT_SEED,
                      "observations": len(features), "independent_path_components": len(manifest["pairs"]),
                      "audit_pairs": proposal["audit"]["pairs"], "audit_clips": proposal["audit"]["clips"],
                      "diagnose": proposal["diagnose"], "gate_updates": proposal["gate_updates"]}))
    # Ungefilterte echte GUI-Settings: ein Produktfehler muss hier sichtbar bleiben.
    window._refresh_hearing_ranking()
    qtbot.waitUntil(lambda: window.playlist_worker is None, timeout=30000)
    before = window.current_generation_result
    assert before is not None and before.graph_stats.boundaries_with_candidates == 1, (
        window.run_state, window.analytics_panel.hearing_status.text(),
        None if before is None else (before.graph_stats, [t.fileName for t in before.tracks]))
    rank_before = ranking(before)
    # key[-1] ist die positionsabhaengige Original-Ordinalzahl, keine Identitaet.
    def ordered_keys(result):
        return [snapshot.key[:-1] for snapshot in result.boundaries[0].snapshots]
    keys_before = ordered_keys(before)
    assert before.boundaries[0].snapshots[0].rang == 1
    rank_one_before = keys_before[0]
    # Derselbe echte Vorschlag; erst dieser Nutzerklick bestaetigt die Uebernahme.
    accept = True
    window._show_hearing_proposal(proposal)
    qtbot.waitUntil(lambda: window._hearing_worker is None and window.playlist_worker is None, timeout=30000)
    assert not warnings, warnings
    assert all(not result.get("cleanup_warning") for _action, result in results), results
    assert starts == ["fit", "apply"]
    applied = next(result["apply_state"] for action, result in results if action == "apply")
    after = window.current_generation_result
    assert window.run_state == main.RunState.SUCCESS
    assert after is not before and after.graph_stats.boundaries_with_candidates == 1
    assert "Ranking" in window.analytics_panel.hearing_status.text()
    disk = json.loads(override.read_text(encoding="utf-8"))
    expected = cp._normalisiere_updates(proposal["gate_updates"])["Psytrance"]
    assert {key: disk["Psytrance"][key] for key in expected} == expected
    expected_weights = {key: expected[key] for key in cp.GEWICHT_SCHLUESSEL}
    cp.reset_cache()
    assert cp.kandidaten_gewichte("Psytrance") == expected_weights
    assert cp.schema_rangfolge("Psytrance") == expected["schema_rang"]
    keys_after = ordered_keys(after)
    assert after.boundaries[0].snapshots[0].rang == 1
    assert after.scoring_context_dict()["candidate_tolerances_by_genre"]["Psytrance"] != before.scoring_context_dict()["candidate_tolerances_by_genre"]["Psytrance"]
    return {"scope": "synthetic_native_producer_audit_fit_apply_ranking_not_music_quality",
            "seed": FIT_SEED, "observations": len(features), "independent_path_components": len(manifest["pairs"]),
            "producer_pairs": len(manifest["pairs"]), "audit": proposal["audit"], "proposal": proposal,
            "rejected_without_write": rejected_without_write, "applied": applied,
            "rank_before": rank_before, "rank_after": ranking(after),
            "ordered_keys_before": keys_before, "ordered_keys_after": keys_after,
            "rank_one_before": rank_one_before, "rank_one_after": keys_after[0],
            "selected_after": after.boundaries[0].selected.key[:-1],
            "cleanup_warnings": [result["cleanup_warning"] for _action, result in results if result.get("cleanup_warning")],
            "ranking_published": window.current_generation_result is after,
            "sources_unchanged": inventory == {path: fingerprint(path) for path in inventory},
            "cache_unchanged": cache_before == fingerprint(config.cache),
            "seconds": time.perf_counter() - started, "diagnose": proposal["diagnose"]}

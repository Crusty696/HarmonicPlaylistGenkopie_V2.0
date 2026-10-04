"""Kohortenanalyse mit injiziertem Analyzer; keine erzeugten Audioclips."""
from dataclasses import replace
import json
import os
from pathlib import Path

import pytest

from hpg_core.collection_index import CollectionEntry, CollectionIndex
from hpg_core.hearing_cohorts import CohortContext, select_cohort
from hpg_core.hearing_collection import analyze_cohort
from hpg_core.models import Track


@pytest.fixture
def request_data(tmp_path, monkeypatch):
    roots = (tmp_path / "a", tmp_path / "b")
    entries = []
    for root in roots:
        root.mkdir()
        # Nur Metadatenfixture. Der .mp3-Pfad existiert nicht und wird nie geschrieben.
        path = root / "track.mp3"
        fixture = root / "source.fixture"
        fixture.touch()
        info = fixture.stat()
        entries.append(CollectionEntry(str(path), info.st_size, info.st_mtime_ns, "new"))
    real_stat, real_lstat = os.stat, os.lstat
    mapping = {entry.path: Path(entry.path).with_name("source.fixture") for entry in entries}
    def guarded(function):
        def call(path, *args, **kwargs):
            return function(mapping.get(os.fspath(path), path), *args, **kwargs)
        return call
    monkeypatch.setattr(os, "stat", guarded(real_stat))
    monkeypatch.setattr(os, "lstat", guarded(real_lstat))
    # Windows benutzt fuer isfile einen nativen Schnellpfad statt os.stat.
    monkeypatch.setattr(os.path, "isfile", guarded(os.path.isfile))
    index = CollectionIndex(tuple(map(str, roots)), tuple(entries))
    context = CohortContext("cache", "build")
    selection = select_cohort(index, count=2, seed=3, context=context)
    return index, context, selection


class Analyzer:
    def __init__(self, transform=None):
        self.paths = None
        self.transform = transform

    def analyze_files(self, paths, progress_callback, cancel_callback):
        self.paths = tuple(paths)
        tracks = [Track(p, Path(p).name, duration=120., bpm=120.,
                        analysis_mode="librosa_full_or_tail") for p in paths]
        return self.transform(tracks) if self.transform else tracks


def test_native_cohort_worker_uses_bound_selection_and_existing_analyzer(request_data,
                                                                          monkeypatch):
    from hpg_core import parallel_analyzer
    from hpg_core.hearing_jobs import HearingCohortWorker

    index, _, _ = request_data
    analyzer = Analyzer()
    monkeypatch.setattr(parallel_analyzer, "ParallelAnalyzer", lambda: analyzer)
    worker = HearingCohortWorker(index, 2, 1, 3, "kandidaten")
    results = []
    worker.completed.connect(results.append)
    worker.run()
    assert len(results) == 1 and results[0]["ok"]
    assert tuple(analyzer.paths) == results[0]["analysis"].requested_paths
    assert len(results[0]["analysis"].track_snapshots) == 2
    assert results[0]["analysis"].complete


def test_native_cohort_worker_cancel_before_analyzer(request_data, monkeypatch):
    from hpg_core import parallel_analyzer
    from hpg_core.hearing_jobs import HearingCohortWorker

    index, _, _ = request_data
    monkeypatch.setattr(parallel_analyzer, "ParallelAnalyzer",
                        lambda: pytest.fail("cancelled cohort started analyzer"))
    worker = HearingCohortWorker(index, 2, 1, 3, "kandidaten")
    results = []
    worker.completed.connect(results.append)
    worker.request_cancel()
    worker.run()
    assert len(results) == 1 and results[0]["cancelled"] and not results[0]["ok"]


def test_native_cohort_worker_detaches_mutable_index_lists(request_data):
    from hpg_core.hearing_jobs import HearingCohortWorker

    index, _, _ = request_data
    roots = list(index.roots)
    entries = list(index.entries)
    mutable = CollectionIndex(roots, entries)
    worker = HearingCohortWorker(mutable, 2, 1, 3, "kandidaten")
    roots.clear()
    entries.clear()
    assert worker.index.roots == index.roots
    assert worker.index.entries == index.entries
    assert isinstance(worker.index.roots, tuple)
    assert isinstance(worker.index.entries, tuple)


def test_exact_selected_paths_multiroot_snapshots(request_data):
    index, context, selection = request_data
    analyzer = Analyzer(lambda tracks: tracks[::-1])
    result = analyze_cohort(index, selection, context=context, analyzer=analyzer)
    assert analyzer.paths == selection.paths
    assert result.complete
    assert tuple(json.loads(raw)["filePath"] for raw in result.track_snapshots) == selection.paths
    assert result.selected_roots == index.roots
    assert result.source_proof == "stat_checked_before_after"


def test_bad_binding_before_source_access(request_data, monkeypatch):
    from hpg_core import hearing_collection as service
    index, context, selection = request_data
    def forbidden(*args):
        raise AssertionError("Quellenzugriff vor Bindungsvalidierung")
    monkeypatch.setattr(service, "_checked_source", forbidden)
    with pytest.raises(ValueError):
        analyze_cohort(index, replace(selection, seed=True), context=context, analyzer=Analyzer())


@pytest.mark.parametrize("kind", ["missing", "mode", "duration", "snapshot"])
def test_failures_are_explicit_not_complete(request_data, kind):
    index, context, selection = request_data
    def transform(tracks):
        if kind == "missing":
            return tracks[1:]
        if kind == "mode":
            tracks[0].analysis_mode = "rekordbox_degraded"
        elif kind == "duration":
            tracks[0].duration = float("nan")
        else:
            tracks[0].measurement_diagnostics = {"guessed": True}
        return tracks
    result = analyze_cohort(index, selection, context=context, analyzer=Analyzer(transform))
    assert not result.complete
    assert len(result.track_snapshots) == 1
    expected = {"missing": "analysis_result_missing", "mode": "invalid_analysis_mode",
                "duration": "resource_limit_excluded", "snapshot": "snapshot_invalid"}[kind]
    assert result.issues[0].path == selection.paths[0]
    assert result.issues[0].code == expected


@pytest.mark.parametrize("kind", ["duplicate", "outside", "unknown", "not_list"])
def test_result_contract_rejects_foreign_or_duplicate_tracks(request_data, kind):
    index, context, selection = request_data
    def transform(tracks):
        if kind == "duplicate":
            return tracks + tracks[:1]
        if kind == "not_list":
            return iter(tracks)
        tracks[0].filePath = "" if kind == "unknown" else str(Path(selection.paths[0]).parent / "extra.mp3")
        return tracks
    with pytest.raises(ValueError):
        analyze_cohort(index, selection, context=context, analyzer=Analyzer(transform))


@pytest.mark.parametrize("stage", ["before", "after"])
def test_changed_source_aborts_whole_snapshot(request_data, stage):
    index, context, selection = request_data
    def change():
        # Groessenaenderung explizit; keine echten Samples schreiben.
        Path(selection.paths[0]).with_name("source.fixture").write_bytes(b"stat-fixture")
    analyzer = Analyzer()
    if stage == "before":
        change()
    else:
        analyzer = Analyzer(lambda tracks: (change(), tracks)[1])
    with pytest.raises(ValueError):
        analyze_cohort(index, selection, context=context, analyzer=analyzer)
    if stage == "before":
        assert analyzer.paths is None


@pytest.mark.parametrize("stage", ["before", "during", "after", "last"])
def test_cancel_never_returns_partial_snapshot(request_data, monkeypatch, stage):
    from hpg_core import hearing_collection as service
    index, context, selection = request_data
    cancelled = stage == "before"
    class CancellingAnalyzer(Analyzer):
        def analyze_files(self, paths, progress_callback, cancel_callback):
            nonlocal cancelled
            if stage == "during":
                cancelled = True
                cancel_callback()
            tracks = super().analyze_files(paths, progress_callback, cancel_callback)
            if stage == "after":
                cancelled = True
            return tracks
    if stage == "last":
        real_check = service._checked_source
        checks = 0
        def checked(entry):
            nonlocal cancelled, checks
            real_check(entry)
            checks += 1
            if checks == 4:
                cancelled = True
        monkeypatch.setattr(service, "_checked_source", checked)
    with pytest.raises(InterruptedError):
        analyze_cohort(index, selection, context=context, analyzer=CancellingAnalyzer(),
                       cancel=lambda: cancelled)


def test_callback_error_aborts_without_recovery(request_data):
    index, context, selection = request_data
    class ReportingAnalyzer(Analyzer):
        def analyze_files(self, paths, progress_callback, cancel_callback):
            progress_callback(0, len(paths), "start")
            pytest.fail("Nach Callbackfehler darf keine Analyse starten")
    def failed(*args):
        raise RuntimeError("private detail")
    with pytest.raises(InterruptedError, match="Fortschrittsmeldung") as error:
        analyze_cohort(index, selection, context=context, analyzer=ReportingAnalyzer(), progress=failed)
    assert "private detail" not in str(error.value)


def test_reparse_source_rejected_before_dispatch(request_data, monkeypatch):
    from hpg_core import hearing_collection as service
    index, context, selection = request_data
    def reject(path):
        raise ValueError("Verlinkter Vorfahr")
    monkeypatch.setattr(service, "_unlinked", reject)
    analyzer = Analyzer()
    with pytest.raises(ValueError):
        analyze_cohort(index, selection, context=context, analyzer=analyzer)
    assert analyzer.paths is None


def test_snapshots_detached_and_no_audio_decoder_or_own_writer(request_data, monkeypatch):
    import builtins
    import io
    index, context, selection = request_data
    retained = []
    def retain(tracks):
        retained.extend(tracks)
        return tracks
    def forbidden(*args, **kwargs):
        raise AssertionError("Dienst darf keine Audio-/DB-Dateien oeffnen")
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(io, "open", forbidden)
    result = analyze_cohort(index, selection, context=context, analyzer=Analyzer(retain))
    retained[0].fileName = "changed"
    assert json.loads(result.track_snapshots[0])["fileName"] == "track.mp3"

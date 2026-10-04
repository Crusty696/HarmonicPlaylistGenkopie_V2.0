"""Quellreferenz-Adapter: nur synthetische Daten in temporaeren Verzeichnissen."""
from types import SimpleNamespace
from dataclasses import asdict
from pathlib import Path
import hashlib
import json

import pytest

from tools import rate_transitions as rt
from tests.test_rate_transitions import (
    _FakeTrack, _plan_empfehlung, _pc, _ns_track, _dramaturgie_mocklauf,
)


def _paar(monkeypatch):
    a = _FakeTrack("A.wav", 140.0, 400.0, 0.0, 1.0)
    b = _FakeTrack("B.wav", 140.0, 400.0, 0.0, 1.0)
    emp = _plan_empfehlung(a, b)
    monkeypatch.setattr(rt, "compute_transition_recommendations", lambda *a, **k: [emp])
    return a, b, emp


@pytest.mark.parametrize("mode", ["paar", "kandidat"])
def test_sink_erhaelt_exakten_spec_ohne_wav(monkeypatch, tmp_path, mode):
    a, b, emp = _paar(monkeypatch)
    specs = []
    original = rt.TransitionClipSpec

    def capture(*a, **k):
        spec = original(*a, **k)
        specs.append(spec)
        return spec

    if mode == "paar":
        original_replace = rt.replace
        def capture_replace(*a, **k):
            spec = original_replace(*a, **k)
            specs.append(spec)
            return spec
        monkeypatch.setattr(rt, "replace", capture_replace)
    else:
        monkeypatch.setattr(rt, "TransitionClipSpec", capture)
    seen = []
    monkeypatch.setattr(rt, "_rendere_atomar", lambda *a: pytest.fail("WAV-Pfad"))
    sink = lambda spec, target: seen.append((spec, target))
    if mode == "paar":
        result = rt.rendere_paar({"track_a": a, "track_b": b}, "001", tmp_path, render_sink=sink)
        assert result[1] is emp.plan
        name = "001.wav"
    else:
        result = rt.rendere_kandidat(a, b, _pc(160, 80, 16, .8), "001", 1, tmp_path, render_sink=sink)
        name = "001_k1.wav"
    assert seen[0][0] is specs[-1]
    assert seen[0][1] == tmp_path / name
    assert result[0] == f"clips/{name}"
    assert not list(tmp_path.rglob("*.wav"))


@pytest.mark.parametrize("mode", ["paar", "kandidat"])
def test_validation_vor_sink(monkeypatch, tmp_path, mode):
    a, b, emp = _paar(monkeypatch)
    sink = lambda *a: pytest.fail("Sink vor Validierung")
    with pytest.raises(ValueError):
        if mode == "paar":
            emp.plan = None
            rt.rendere_paar({"track_a": a, "track_b": b}, "001", tmp_path, render_sink=sink)
        else:
            pc = _pc(160, 80, 16, .8)
            pc.overlap_sec = 65.0
            rt.rendere_kandidat(a, b, pc, "001", 1, tmp_path, render_sink=sink)


def _single(monkeypatch, tmp_path):
    a, b, emp = _paar(monkeypatch)
    candidate = {"track_a": a, "track_b": b, "merkmale": {n: .5 for n in rt.NEUE_FAKTOREN}}
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda *_args: [a, b])
    monkeypatch.setattr(rt, "sammle_kandidaten", lambda *a: [candidate, candidate])
    monkeypatch.setattr(rt, "maximin_auswahl", lambda *a, **k: [0, 1])
    monkeypatch.setattr(rt.PairCandidate, "from_dict", lambda d: SimpleNamespace(rang=1))
    monkeypatch.setattr(rt, "_faktoren_vollstaendig", lambda pc: {n: .5 for n in rt.ALLE_FAKTOREN})
    monkeypatch.setattr(rt, "transition_metrics_from_candidate", lambda pc: SimpleNamespace(overall_score=.8, lufs_delta=0))
    return SimpleNamespace(out=tmp_path / "single", cache=None, bpm_toleranz=2., anzahl=1, seed=1)


def test_single_sink_progress(monkeypatch, tmp_path):
    args = _single(monkeypatch, tmp_path)
    seen, progress = [], []
    args.hpg_render_sink = lambda spec, target: seen.append((spec, target))
    args.hpg_progress = lambda *event: progress.append(event)
    assert rt._befehl_prepare_intern(args) == 0
    assert seen[0][1] == args.out / "clips/001.wav"
    assert ("einzel", 1, 1) in progress
    assert not list(args.out.rglob("*.wav"))


def test_single_faktorfehler_nach_sink_abbruch_ohne_reserve(monkeypatch, tmp_path):
    args = _single(monkeypatch, tmp_path)
    emitted = []
    args.hpg_render_sink = lambda spec, target: emitted.append(target)
    monkeypatch.setattr(rt, "_faktoren_vollstaendig", lambda pc: None)
    with pytest.raises(ValueError, match="unvollstaendige Faktoren"):
        rt._befehl_prepare_intern(args)
    assert len(emitted) == 1
    assert not (args.out / "bewertung.csv").exists()


def _candidates(monkeypatch, tmp_path):
    a, b = _ns_track("a"), _ns_track("b")
    pcs = [_pc(160, 80, 16, .8), _pc(170, 90, 16, .7)]
    for n, pc in enumerate(pcs, 1):
        pc.rang = n
    candidate = {"track_a": a, "track_b": b, "pair_candidates": pcs,
                 "merkmale": {n: .5 for n in rt.NEUE_FAKTOREN}}
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"synthetic")
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda *_args: [a, b])
    monkeypatch.setattr(rt, "sammle_kandidaten_parallel", lambda *a, **k: [candidate, candidate])
    monkeypatch.setattr(rt, "maximin_auswahl", lambda *a, **k: [0, 1])
    return SimpleNamespace(out=tmp_path / "candidates", cache=str(cache), bpm_toleranz=2., anzahl=1, seed=1)


def test_candidates_final_paths_ohne_wav_move(monkeypatch, tmp_path):
    args = _candidates(monkeypatch, tmp_path)
    seen, progress = [], []
    args.hpg_render_sink = lambda spec, target: seen.append((spec, target))
    args.hpg_progress = lambda *event: progress.append(event)
    assert rt._befehl_prepare_kandidaten_intern(args) == 0
    assert [p for s, p in seen] == [args.out / f"clips/001_k{n}.wav" for n in (1, 2)]
    assert ("kandidaten", 1, 1) in progress
    assert not list(args.out.rglob("*.wav"))


@pytest.mark.parametrize("error", [ValueError("sink failure"), InterruptedError("cancelled")])
def test_candidates_sink_failure_abort(monkeypatch, tmp_path, error):
    args = _candidates(monkeypatch, tmp_path)
    seen = []
    def sink(spec, target):
        seen.append(target)
        if len(seen) == 2:
            raise error
    args.hpg_render_sink = sink
    with pytest.raises(type(error), match=str(error)):
        rt._befehl_prepare_kandidaten_intern(args)
    assert len(seen) == 2
    assert not (args.out / "bewertung.csv").exists()


@pytest.mark.parametrize("producer", ["_befehl_prepare_intern", "_befehl_prepare_kandidaten_intern", "_befehl_prepare_dramaturgie_intern"])
def test_cancel_checkpoint_vor_arbeit(monkeypatch, tmp_path, producer):
    def checkpoint():
        raise InterruptedError("cancelled")
    args = SimpleNamespace(out=tmp_path / "cancel", hpg_cancel=SimpleNamespace(checkpoint=checkpoint))
    with pytest.raises(InterruptedError, match="cancelled"):
        getattr(rt, producer)(args)
    assert not args.out.exists()


def test_dramaturgie_source_metadata_ohne_wav_validator(monkeypatch, tmp_path):
    _, args, observed = _dramaturgie_mocklauf(monkeypatch, tmp_path)
    seen, progress = [], []
    args.hpg_render_sink = lambda spec, target: seen.append((spec, target))
    args.hpg_progress = lambda *event: progress.append(event)
    monkeypatch.setattr(rt, "_validiere_dramaturgie_satz", lambda *a: pytest.fail("WAV-Validator"))
    monkeypatch.setattr(rt, "_datei_metadaten", lambda *a: pytest.fail("WAV-Metadaten"))
    assert rt._befehl_prepare_dramaturgie_intern(args) == 0
    manifest = json.loads((args.out / rt.DRAMATURGIE_MANIFEST_NAME).read_text(encoding="utf-8"))
    clips = [t["clip"] for v in manifest["variants"] for t in v["transitions"]]
    assert all(set(c) == {"path", "representation"} and c["representation"] == "source_reference_v1" for c in clips)
    assert [spec for spec, target in seen] == observed.from_plan_aufrufe
    assert progress[-1] == ("dramaturgie", len(manifest["variants"]), len(manifest["variants"]))
    assert not list(args.out.rglob("*.wav"))


@pytest.mark.parametrize("wrapper", ["befehl_prepare", "befehl_prepare_kandidaten", "befehl_prepare_dramaturgie"])
def test_source_wrapper_ohne_service_publiziert_nicht(monkeypatch, tmp_path, wrapper):
    args = SimpleNamespace(out=tmp_path / "published", hpg_render_sink=lambda *a: None)
    monkeypatch.setattr(rt, "_publiziere_staging", lambda *a: pytest.fail("Publikation ohne Quellvalidierung"))
    with pytest.raises(ValueError, match="Service"):
        getattr(rt, wrapper)(args)
    assert not args.out.exists()


@pytest.mark.parametrize("mode", ["single", "candidates", "dramaturgie"])
@pytest.mark.parametrize("error_type", [InterruptedError, ValueError])
def test_sink_fehler_aller_produzenten_propagiert(monkeypatch, tmp_path, mode, error_type):
    if mode == "single":
        args = _single(monkeypatch, tmp_path)
        producer = rt._befehl_prepare_intern
    elif mode == "candidates":
        args = _candidates(monkeypatch, tmp_path)
        producer = rt._befehl_prepare_kandidaten_intern
    else:
        _, args, _ = _dramaturgie_mocklauf(monkeypatch, tmp_path)
        producer = rt._befehl_prepare_dramaturgie_intern
    seen = []
    def sink(spec, target):
        seen.append(target)
        raise error_type("sink abort")
    args.hpg_render_sink = sink
    with pytest.raises(error_type, match="sink abort"):
        producer(args)
    assert len(seen) == 1
    assert not (args.out / "bewertung.csv").exists()


def test_dramaturgie_beatsyncfehler_source_keine_reserve(monkeypatch, tmp_path):
    _, args, _ = _dramaturgie_mocklauf(monkeypatch, tmp_path)
    def sink(*a):
        raise rt.BeatSyncError("beat abort")
    args.hpg_render_sink = sink
    with pytest.raises(rt.BeatSyncError, match="beat abort"):
        rt._befehl_prepare_dramaturgie_intern(args)


@pytest.mark.parametrize("mode", ["single", "candidates"])
def test_legacy_interruptederror_nicht_verschluckt(monkeypatch, tmp_path, mode):
    if mode == "single":
        args = _single(monkeypatch, tmp_path)
        producer = rt.befehl_prepare
    else:
        args = _candidates(monkeypatch, tmp_path)
        producer = rt.befehl_prepare_kandidaten
    def render(*a):
        raise InterruptedError("legacy abort")
    monkeypatch.setattr(rt, "_rendere_atomar", render)
    with pytest.raises(InterruptedError, match="legacy abort"):
        producer(args)
    assert not args.out.exists()
    assert not list(tmp_path.glob(f".{args.out.name}.staging-*"))


@pytest.mark.parametrize("mode", ["single", "candidates", "dramaturgie"])
def test_cancel_nach_sink_propagiert(monkeypatch, tmp_path, mode):
    if mode == "single":
        args = _single(monkeypatch, tmp_path)
        producer = rt._befehl_prepare_intern
    elif mode == "candidates":
        args = _candidates(monkeypatch, tmp_path)
        producer = rt._befehl_prepare_kandidaten_intern
    else:
        _, args, _ = _dramaturgie_mocklauf(monkeypatch, tmp_path)
        producer = rt._befehl_prepare_dramaturgie_intern
    seen = []
    args.hpg_render_sink = lambda spec, target: seen.append(target)
    def checkpoint():
        if seen:
            raise InterruptedError("after sink")
    args.hpg_cancel = SimpleNamespace(checkpoint=checkpoint)
    with pytest.raises(InterruptedError, match="after sink"):
        producer(args)
    assert len(seen) == 1


def test_single_cancel_beim_schreiben_verhindert_erfolg(monkeypatch, tmp_path):
    args = _single(monkeypatch, tmp_path)
    args.hpg_render_sink = lambda *a: None
    written = []
    original = rt.schreibe_csv
    def write(*a):
        original(*a)
        written.append(a[0])
    monkeypatch.setattr(rt, "schreibe_csv", write)
    def checkpoint():
        if written:
            raise InterruptedError("during write")
    args.hpg_cancel = SimpleNamespace(checkpoint=checkpoint)
    with pytest.raises(InterruptedError, match="during write"):
        rt._befehl_prepare_intern(args)


def _source_service_config(monkeypatch, tmp_path, mode):
    """Echte Produzenten/Dienst/Validatoren; nur Cache- und Planinputs synthetisch."""
    from hpg_core.hearing_workflow import PrepareConfig
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    if mode == "einzel":
        args = _single(monkeypatch, fixture_dir)
        cache = fixture_dir / "cache.db"
        cache.write_bytes(b"synthetic cache")
        options = {"count": 1}
    elif mode == "kandidaten":
        args = _candidates(monkeypatch, fixture_dir)
        cache = Path(args.cache)
        # Der Quellvalidator bekommt vollstaendige synthetische Teilwerte.
        for pair in rt.sammle_kandidaten_parallel([], 2.):
            for pc in pair["pair_candidates"]:
                pc.teilwerte = {key: .5 for key in rt.KANDIDATEN_TEILWERTE}
        options = {"count": 1}
    else:
        from hpg_core.playlist import resolve_run_scoring_context
        from_plan = rt.TransitionClipSpec.from_plan
        _, args, _ = _dramaturgie_mocklauf(monkeypatch, fixture_dir)
        # Der bestehende CLI-Testhelfer mockt dies; hier echte Spec und echten Kontext nutzen.
        monkeypatch.setattr(rt.TransitionClipSpec, "from_plan", from_plan)
        monkeypatch.setattr(rt, "resolve_run_scoring_context", resolve_run_scoring_context)
        cache = Path(args.cache)
        options = {"sequence_tracks": 12, "transitions_per_variant": 5}
    tracks = rt.lade_tracks_aus_cache(str(cache))
    for index, track in enumerate(tracks):
        source = fixture_dir / f"source-{index:02d}.wav"
        source.write_bytes(f"synthetic source {index}".encode())
        track.filePath = str(source)
        track.bpm = 140.
    monkeypatch.setattr(rt, "_rendere_atomar", lambda *a: pytest.fail("Permanenter WAV-Render"))
    return PrepareConfig(mode, tmp_path / "result", cache, source_roots=(fixture_dir,), **options)


@pytest.mark.parametrize("mode", ["einzel", "kandidaten", "dramaturgie"])
@pytest.mark.parametrize("outcome", ["success", "sink_failure", "cancel_after_emit", "invalid_metadata"])
def test_source_producer_service_allmode_e2e(monkeypatch, tmp_path, mode, outcome):
    from hpg_core.hearing_sources import SourceRenderSink, load_source_session
    from hpg_core.hearing_workflow import (
        CancellationToken, HearingCancelledError, HearingOperationError,
        HearingValidationError, create_set,
    )
    config = _source_service_config(monkeypatch, tmp_path, mode)
    def fingerprints():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in config.source_roots[0].iterdir() if p.is_file()}
    before = fingerprints()
    emitted, published, updates = {}, [], []
    token = CancellationToken()
    real_emit = SourceRenderSink.emit
    def emit(sink, spec, target):
        real_emit(sink, spec, target)
        emitted[target.relative_to(sink.staging_root).as_posix()] = asdict(spec)
        if outcome == "sink_failure":
            raise ValueError("after real emit")
        if outcome == "cancel_after_emit":
            token.request_cancel()
    monkeypatch.setattr(SourceRenderSink, "emit", emit)
    real_publish = rt._publiziere_staging
    def publish(stage, target):
        # Ein echter Quellvalidator muss den ganzen Satz schon akzeptieren.
        assert load_source_session(stage).specs == emitted
        published.append(target)
        real_publish(stage, target)
    monkeypatch.setattr(rt, "_publiziere_staging", publish)
    if outcome == "invalid_metadata":
        real_write = rt.schreibe_csv
        def corrupt(path, columns, rows):
            real_write(path, columns, rows)
            if path.name == "bewertung.csv":
                path.write_text("invalid,header\nbad,row\n", encoding="utf-8")
        monkeypatch.setattr(rt, "schreibe_csv", corrupt)
    if outcome == "success":
        result = create_set(config, progress=updates.append, cancel=token)
        session = load_source_session(result.output_dir)
        expected_clips = {"einzel": 1, "kandidaten": 2,
                          "dramaturgie": len(rt.dramaturgie_varianten()) * 5}[mode]
        assert result.clip_count == session.clip_count == expected_clips
        assert session.specs == emitted
        assert session.manifest["format_version"] == 1
        assert session.status == result.status == "prepared"
        assert published == [config.output_dir]
        assert token.state == token.COMPLETE
        assert updates[-1].phase == "prepared"
        assert any(p.phase == mode and p.completed == p.total for p in updates)
        assert not list(result.output_dir.rglob("*.wav"))
        assert not list(result.output_dir.rglob("*.mp3"))
    else:
        expected_error = {"sink_failure": HearingOperationError,
                          "cancel_after_emit": HearingCancelledError,
                          "invalid_metadata": HearingValidationError}[outcome]
        with pytest.raises(expected_error):
            create_set(config, progress=updates.append, cancel=token)
        assert emitted
        assert not published
        assert not config.output_dir.exists()
    assert not list(tmp_path.glob(".result.staging-*"))
    assert fingerprints() == before


def test_source_service_single_postfaktorfehler_raeumt_staging(monkeypatch, tmp_path):
    from hpg_core.hearing_sources import SourceRenderSink
    from hpg_core.hearing_workflow import HearingOperationError, create_set
    config = _source_service_config(monkeypatch, tmp_path, "einzel")
    emitted = []
    original = SourceRenderSink.emit
    def emit(sink, spec, target):
        original(sink, spec, target)
        emitted.append(target)
    monkeypatch.setattr(SourceRenderSink, "emit", emit)
    monkeypatch.setattr(rt, "_faktoren_vollstaendig", lambda pc: None)
    monkeypatch.setattr(rt, "_publiziere_staging", lambda *a: pytest.fail("Postfaktorfehler publiziert"))
    with pytest.raises(HearingOperationError, match="unvollstaendige Faktoren"):
        create_set(config)
    assert len(emitted) == 1
    assert not config.output_dir.exists()
    assert not list(tmp_path.glob(".result.staging-*"))

"""Lokale Forschung: reine Bindungen und synthetische Fenster, keine Musikdateien."""
from dataclasses import FrozenInstanceError, replace
import importlib
import importlib.util

import pytest


def api():
    assert importlib.util.find_spec("hpg_core.anchor_research") is not None, "Forschungskern fehlt"
    return importlib.import_module("hpg_core.anchor_research")


def context(**changes):
    a = api()
    source = a.SourceBinding("C:/music/track.wav", "C:/music", 1, "inventory-1", 100, 12, "a" * 64)
    return replace(a.MeasurementBinding(source, "b" * 64, "c" * 64, "d" * 64,
                                        8000, 120.0, 4, 60.0), **changes)


def item(**changes):
    a = api()
    return replace(a.AnchorResearchInput(
        context(), (a.ResearchCandidate("out-1", "out", 24.0, "existing_candidate"),),
        0.1, 0.0, None, None, ("coverage",), (), None), **changes)


def plan(value=None, **policy):
    a = api()
    return a.plan_anchor_research((value or item(),), policy=a.AnchorResearchPolicy(**policy))


def measured(p, phase=0.1):
    a = api()
    return tuple(a.WindowObservation(w, (phase - w.offset_seconds) % 0.5, 0.8, "measured")
                 for w in p.requests)


def test_plan_budget_and_no_source_access():
    p = plan()
    assert [(r.offset_seconds, r.duration_seconds) for r in p.requests] == [(12, 8), (20, 8), (28, 8)]
    assert p.new_window_count == 3
    assert p.new_audio_seconds == 24
    assert p.max_window_samples == 64000


@pytest.mark.parametrize("field,value", [
    ("bpm", True), ("bpm", 0), ("bpm", float("nan")), ("bpm", float("inf")),
    ("duration", False), ("duration", -1), ("meter", True), ("meter", 0), ("meter", 4.5),
    ("sample_rate", True), ("sample_rate", 0), ("schema", True), ("schema", 2),
    ("build_sha256", "bad"), ("parameters_sha256", []),
])
def test_binding_rejects_invalid_public_values(field, value):
    with pytest.raises(ValueError):
        context(**{field: value})


@pytest.mark.parametrize("field,value", [
    ("window_seconds", True), ("window_seconds", 0), ("max_windows", False),
    ("max_windows", -1), ("max_audio_seconds", float("inf")),
])
def test_policy_rejects_invalid_numbers(field, value):
    with pytest.raises(ValueError):
        api().AnchorResearchPolicy(**{field: value})


def test_strict_nested_types_and_immutability():
    a = api()
    x = item()
    with pytest.raises(ValueError):
        replace(x, candidates=list(x.candidates))
    with pytest.raises(ValueError):
        replace(x, production_blockers=(["coverage"],))
    with pytest.raises(ValueError):
        replace(x, bar_confidence=True)
    with pytest.raises(FrozenInstanceError):
        x.binding.source.path = "elsewhere"
    with pytest.raises(ValueError):
        a.plan_anchor_research([x], policy=a.AnchorResearchPolicy())


@pytest.mark.parametrize("path", ["C:/music2/a.wav", "C:/music/../outside.wav", "relative.wav"])
def test_source_root_lexical_containment(path):
    with pytest.raises(ValueError):
        replace(context().source, path=path)


def test_actual_zero_bar_and_unknown_phrase_never_promoted():
    a = api()
    p = plan()
    result = a.evaluate_anchor_hypotheses(p, measured(p))
    baseline = result.results[0]
    assert baseline.beat_status == "consistent"
    assert baseline.max_phase_error_ms == pytest.approx(0)
    assert baseline.bar_confidence == 0
    assert baseline.bar_status == "unverified"
    assert baseline.phrase_confidence is None
    assert baseline.phrase_status == "unverified"
    assert baseline.production_blockers == ("coverage",)
    assert result.contract == "research_only"
    assert result.reader_calls == result.dsp_calls == 0
    assert result.proof_source == "caller_provided_observations"


def test_whole_beat_hypotheses_do_not_establish_bar_identity():
    a = api()
    p = plan()
    result = a.evaluate_anchor_hypotheses(p, measured(p, 0.2))
    derived = [r for r in result.results if r.hypothesis.origin == "local_phase"]
    assert [r.hypothesis.anchor_seconds for r in derived] == pytest.approx([.2, .7, 1.2, 1.7])
    assert all(r.bar_status == r.phrase_status == "unverified" for r in derived)
    assert all(r.beat_status == "consistent" for r in derived)
    assert all(r.independent_windows == 2 for r in derived)


def test_phase_wrap_and_mismatch_are_not_rounded_away():
    a = api()
    p = plan(item(beat_anchor=.499))
    result = a.evaluate_anchor_hypotheses(p, measured(p, .001))
    assert result.results[0].max_phase_error_ms == pytest.approx(2)
    assert result.results[0].beat_status == "consistent"
    result = a.evaluate_anchor_hypotheses(p, measured(p, .007))
    assert result.results[0].beat_status == "mismatch"


def test_duplicate_and_overlapping_windows_not_independent():
    a = api()
    p = plan(item(candidates=(a.ResearchCandidate("edge", "in", 0, "cue"),)))
    assert len(p.requests) < 3
    report = a.evaluate_anchor_hypotheses(p, measured(p))
    assert all(r.beat_status == "unverified" for r in report.results)
    with pytest.raises(ValueError):
        a.evaluate_anchor_hypotheses(p, measured(p) + measured(p))


def test_reuse_exact_binding_skips_all_work():
    a = api()
    p = plan()
    observations = measured(p)
    p = plan(item(observations=observations))
    assert p.new_window_count == p.new_audio_seconds == 0
    def forbidden(request):
        pytest.fail("Wiederverwendung darf keinen Leser aufrufen")
    result = a.run_anchor_research(p, window_reader=forbidden)
    assert result.reader_calls == result.dsp_calls == 0
    assert result.reused_windows == 3


@pytest.mark.parametrize("field,value", [
    ("build_sha256", "e" * 64), ("algorithm_sha256", "e" * 64),
    ("parameters_sha256", "e" * 64), ("bpm", 121), ("sample_rate", 16000), ("duration", 61),
])
def test_context_change_invalidates_reuse(field, value):
    old = measured(plan())
    p = plan(item(binding=context(**{field: value}), observations=old))
    assert p.new_window_count == 3
    assert p.reused == ()


def test_source_change_invalidates_reuse():
    b = context()
    p = plan(item(binding=replace(b, source=replace(b.source, mtime_ns=13)), observations=measured(plan())))
    assert p.new_window_count == 3


def test_missing_provenance_blocks_measurement_not_guesses():
    a = api()
    p = plan(item(binding=context(build_sha256=None)))
    assert p.requests == ()
    assert p.issues == ("missing_binding",)
    result = a.run_anchor_research(p, window_reader=lambda w: pytest.fail("Kein Kontext"))
    assert result.results[0].beat_status == "unverified"


@pytest.mark.parametrize("identity", ["unverified", "different", "unavailable", "byte_identical"])
def test_identity_claim_never_becomes_core_proof(identity):
    a = api()
    claim = a.ReferenceClaim("basename", identity, "D:/old/track.wav", "42", "signature", "main-manifest")
    p = plan(item(reference=claim))
    result = a.evaluate_anchor_hypotheses(p, measured(p))
    assert result.results[0].reference == claim
    assert result.results[0].identity_proof_source == "caller_provided"
    assert result.results[0].bar_status == "unverified"


def test_over_budget_fails_before_reader():
    with pytest.raises(ValueError):
        plan(max_windows=2)


def test_actual_reader_dsp_calls_and_inputs_unchanged():
    import numpy as np
    a = api()
    x = item()
    p = plan(x)
    calls = []
    def reader(w):
        calls.append(w)
        return w.binding, np.zeros(round(w.duration_seconds * w.binding.sample_rate))
    result = a.run_anchor_research(p, window_reader=reader)
    assert result.reader_calls == result.dsp_calls == len(calls) == 3
    assert result.decoded_seconds == 24
    assert result.proof_source == "core_dsp_on_injected_audio"
    assert all(r.beat_status == "unverified" for r in result.results)
    assert x == item()


def test_decode_failure_is_opaque_and_counts_attempts():
    a = api()
    def reader(w):
        raise OSError("opaque-sensitive-token")
    result = a.run_anchor_research(plan(), window_reader=reader)
    assert result.reader_calls == 3 and result.dsp_calls == 0
    assert result.errors == ("decode_error",) * 3
    assert "opaque-sensitive-token" not in repr(result)


def test_reader_binding_mismatch_is_fatal():
    import numpy as np
    a = api()
    with pytest.raises(a.AnchorResearchError):
        a.run_anchor_research(plan(), window_reader=lambda w: (context(bpm=121), np.zeros(64000)))


@pytest.mark.parametrize("stage", ["progress", "cancel", "final_cancel"])
def test_callback_failure_or_final_cancel_never_completes(stage):
    a = api()
    p = plan(item(observations=measured(plan())))
    count = 0
    def cancel():
        nonlocal count
        count += 1
        if stage == "cancel":
            raise RuntimeError("opaque-sensitive-token")
        return stage == "final_cancel" and count >= 2
    def progress(event):
        if stage == "progress":
            raise RuntimeError("opaque-sensitive-token")
    with pytest.raises(a.AnchorResearchError) as exc:
        a.run_anchor_research(p, window_reader=lambda w: None, cancel=cancel, progress=progress)
    assert "opaque-sensitive-token" not in str(exc.value)


def test_forged_plan_cost_or_requests_rejected():
    a = api()
    p = plan()
    with pytest.raises(ValueError):
        a.evaluate_anchor_hypotheses(replace(p, requests=()), ())


def test_synthetic_pulses_use_real_fold_not_confidence_override():
    import numpy as np
    a = api()
    p = plan()
    def reader(w):
        sr = w.binding.sample_rate
        t = np.arange(round(w.duration_seconds * sr)) / sr
        # Tieffrequente Attacken mit bekanntem halben Sekundenabstand.
        phase = (t + w.offset_seconds - .1) % .5
        y = np.exp(-phase * 70) * np.cos(2 * np.pi * 70 * phase)
        return w.binding, y
    report = a.run_anchor_research(p, window_reader=reader)
    assert report.dsp_calls == 3
    assert all(o.phase_seconds is not None and o.fold_lock > .1 for o in report.observations)
    assert all(min(abs(o.phase_seconds - .1), .5 - abs(o.phase_seconds - .1)) < .03
               for o in report.observations)
    assert all(r.bar_status == r.phrase_status == "unverified" for r in report.results)


def test_each_observation_has_its_actual_proof_source():
    import numpy as np
    a = api()
    old = measured(plan())[:1]
    p = plan(item(observations=old))
    report = a.run_anchor_research(p, window_reader=lambda w: (w.binding, np.zeros(64000)))
    assert report.observation_proof_sources == (
        "caller_provided", "core_dsp_on_injected_audio", "core_dsp_on_injected_audio")
    assert report.reader_calls == report.dsp_calls == 2
    assert report.reused_windows == 1
    assert report.decoded_seconds == 16


@pytest.mark.parametrize("which", ["plan", "hypothesis", "report"])
def test_public_records_cannot_retain_mutable_nested_values(which):
    a = api()
    p = plan()
    report = a.evaluate_anchor_hypotheses(p, ())
    with pytest.raises(ValueError):
        if which == "plan":
            replace(p, issues=[])
        elif which == "hypothesis":
            a.AnchorHypothesis("existing_anchor", [])
        else:
            replace(report, observations=[])


@pytest.mark.parametrize("kind", ["short", "stereo", "nan", "bool", "list"])
def test_reader_invalid_audio_contract_is_fatal(kind):
    import numpy as np
    a = api()
    samples = {
        "short": np.zeros(1), "stereo": np.zeros((64000, 2)),
        "nan": np.full(64000, np.nan), "bool": np.zeros(64000, dtype=bool),
        "list": [0.] * 64000,
    }[kind]
    with pytest.raises(a.AnchorResearchError):
        a.run_anchor_research(plan(), window_reader=lambda w: (w.binding, samples))


def test_subsample_duration_not_claimed_as_exact_window():
    with pytest.raises(ValueError):
        api().WindowRequest(context(), 0, .00018)


def test_reader_safety_error_aborts_instead_of_decode_failure():
    a = api()
    def reader(w):
        raise a.AnchorResearchError("opaque-sensitive-token")
    with pytest.raises(a.AnchorResearchError) as exc:
        a.run_anchor_research(plan(), window_reader=reader)
    assert "opaque-sensitive-token" not in str(exc.value)


def test_overlapping_candidate_windows_deduplicated_without_mutation():
    a = api()
    x = item()
    candidates = x.candidates + (a.ResearchCandidate("in-2", "in", 24, "section"),)
    p = plan(replace(x, candidates=candidates))
    assert len(p.requests) == 3
    report = a.evaluate_anchor_hypotheses(p, measured(p))
    assert len(report.results) == 10
    assert all(r.independent_windows <= 3 for r in report.results)


def test_unknown_meter_and_zero_window_budget_fail_closed():
    a = api()
    p = plan(item(binding=context(meter=3)))
    assert p.requests == () and p.issues == ("unsupported_meter",)
    report = a.evaluate_anchor_hypotheses(p, ())
    assert report.results[0].beat_status == "unverified"
    with pytest.raises(ValueError):
        plan(max_windows=0)


def test_current_anchor_change_reuses_phase_but_not_old_error():
    a = api()
    p = plan(item(beat_anchor=.2, observations=measured(plan(), .1)))
    report = a.evaluate_anchor_hypotheses(p, ())
    assert p.new_window_count == 0
    assert report.results[0].max_phase_error_ms == pytest.approx(100)
    assert report.results[0].beat_status == "mismatch"


@pytest.mark.parametrize("field,value", [("phase_seconds", True), ("phase_seconds", .5),
                                         ("fold_lock", float("nan")), ("fold_lock", 1.1),
                                         ("reason", []), ("phase_seconds", None)])
def test_malformed_observation_cannot_be_reused(field, value):
    observation = measured(plan())[0]
    with pytest.raises(ValueError):
        replace(observation, **{field: value})


def test_unmatched_observation_is_not_silently_used():
    a = api()
    p = plan()
    old = measured(p)[0]
    other = replace(old, request=replace(old.request, binding=context(bpm=121)))
    with pytest.raises(ValueError):
        a.evaluate_anchor_hypotheses(p, (other,))


def test_old_bar_and_phrase_confidence_not_transplanted_to_alternative():
    a = api()
    p = plan(item(bar_confidence=.9, phrase_anchor=8.1, phrase_confidence=.8))
    report = a.evaluate_anchor_hypotheses(p, measured(p, .2))
    baseline, *alternatives = report.results
    assert baseline.bar_confidence == .9 and baseline.phrase_confidence == .8
    assert all(r.bar_confidence is None and r.phrase_confidence is None and r.phrase_anchor is None
               for r in alternatives)


def test_windows_path_alias_cannot_create_two_source_contexts():
    a = api()
    first = item()
    second = replace(first, binding=replace(first.binding, source=replace(
        first.binding.source, path="c:\\MUSIC\\TRACK.wav")))
    with pytest.raises(ValueError):
        a.plan_anchor_research((first, second), policy=a.AnchorResearchPolicy())

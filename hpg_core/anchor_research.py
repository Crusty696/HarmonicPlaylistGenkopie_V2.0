"""Lokale Ankerhypothesen, niemals Produktionsfreigaben.

Keine eigenen Datei-/DB-Zugriffe. Alle Bindungen und Identitaetsangaben sind
Caller-Angaben, auch bei vorhandenen Hashes. Nur die DSP-Auswertung injizierter
RAM-Samples entsteht hier. Der Reader muss Quellenzugriff und Laufbindung selbst
absichern. Takt-/Phrasenkonfidenzen bleiben unverifizierte Eingangsevidenz.
"""
from dataclasses import dataclass, replace
import math
import ntpath
import re
from typing import Protocol


class AnchorResearchError(RuntimeError):
    """Opaker Laufabbruch; kein abgeschlossener Teilbericht."""


def _require(condition):
    if not condition:
        raise ValueError("Ungueltiger Ankerforschungsvertrag")


def _number(value, *, positive=False, integer=False):
    _require(type(value) in ((int,) if integer else (int, float)))
    try:
        valid = math.isfinite(value) and (value > 0 if positive else value >= 0)
    except (OverflowError, ValueError):
        valid = False
    _require(valid)


def _text(value):
    _require(type(value) is str and bool(value.strip()) and "\x00" not in value)


def _choice(value, choices):
    _require(type(value) is str and value in choices)


def _optional_number(value, *, confidence=False):
    if value is not None:
        _number(value)
        if confidence:
            _require(value <= 1)


def _hash(value):
    _require(value is None or (type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None))


def _path(value):
    _text(value)
    drive, tail = ntpath.splitdrive(value)
    _require(bool(drive) and tail.startswith(("/", "\\")))
    _require(not any(part in (".", "..") for part in value.replace("\\", "/").split("/")))
    _require(not value.startswith(("\\\\?", "\\\\.")))
    _require(":" not in tail)


def _tuple(value, cls):
    _require(type(value) is tuple)
    for entry in value:
        _require(type(entry) is cls)
        if cls is str:
            _text(entry)
        else:
            entry.__post_init__()


@dataclass(frozen=True, slots=True)
class SourceBinding:
    path: str
    root: str
    index_version: int
    index_id: str
    size: int
    mtime_ns: int
    sha256: str | None

    def __post_init__(self):
        _path(self.path)
        _path(self.root)
        _number(self.index_version, positive=True, integer=True)
        _text(self.index_id)
        _number(self.size, integer=True)
        _number(self.mtime_ns, integer=True)
        _hash(self.sha256)
        path, root = ntpath.normcase(self.path), ntpath.normcase(self.root)
        try:
            contained = ntpath.commonpath((path, root)) == ntpath.normpath(root) and path != root
        except ValueError:
            contained = False
        _require(contained)


@dataclass(frozen=True, slots=True)
class MeasurementBinding:
    source: SourceBinding
    build_sha256: str | None
    algorithm_sha256: str | None
    parameters_sha256: str | None
    sample_rate: int
    bpm: float
    meter: int
    duration: float
    schema: int = 1

    def __post_init__(self):
        _require(type(self.source) is SourceBinding)
        self.source.__post_init__()
        for value in (self.build_sha256, self.algorithm_sha256, self.parameters_sha256):
            _hash(value)
        _number(self.sample_rate, positive=True, integer=True)
        _number(self.bpm, positive=True)
        _number(self.meter, positive=True, integer=True)
        _number(self.duration, positive=True)
        _require(type(self.schema) is int and self.schema == 1)
        _require(math.isfinite(60 / self.bpm) and 60 / self.bpm > 0)
        _require(math.isfinite(self.duration * self.sample_rate))

    @property
    def complete(self):
        return all(v is not None for v in (self.source.sha256, self.build_sha256,
                                           self.algorithm_sha256, self.parameters_sha256))


@dataclass(frozen=True, slots=True)
class ReferenceClaim:
    match_kind: str
    identity: str
    record_path: str | None
    content_id: str
    signature: str
    evidence_id: str

    def __post_init__(self):
        _choice(self.match_kind, ("exact", "basename", "ambiguous", "missing", "unavailable"))
        _choice(self.identity, ("unverified", "byte_identical", "different", "unavailable"))
        if self.record_path is not None:
            _path(self.record_path)
        for value in (self.content_id, self.signature, self.evidence_id):
            _text(value)
        _require(self.identity != "byte_identical" or self.record_path is not None)


@dataclass(frozen=True, slots=True)
class ResearchCandidate:
    id: str
    side: str
    time_seconds: float
    origin: str

    def __post_init__(self):
        _text(self.id)
        _choice(self.side, ("in", "out"))
        _number(self.time_seconds)
        _choice(self.origin, ("existing_candidate", "cue", "section"))


@dataclass(frozen=True, slots=True)
class WindowRequest:
    binding: MeasurementBinding
    offset_seconds: float
    duration_seconds: float

    def __post_init__(self):
        _require(type(self.binding) is MeasurementBinding)
        self.binding.__post_init__()
        _number(self.offset_seconds)
        _number(self.duration_seconds, positive=True)
        _require(self.offset_seconds + self.duration_seconds <= self.binding.duration)
        samples = self.duration_seconds * self.binding.sample_rate
        _require(samples >= 1 and float(samples).is_integer())


@dataclass(frozen=True, slots=True)
class WindowObservation:
    request: WindowRequest
    phase_seconds: float | None
    fold_lock: float | None
    reason: str

    def __post_init__(self):
        _require(type(self.request) is WindowRequest)
        self.request.__post_init__()
        _optional_number(self.phase_seconds)
        _optional_number(self.fold_lock, confidence=True)
        _choice(self.reason, ("measured", "weakfold", "invalidinput", "estimationerror", "decode_error"))
        if self.phase_seconds is not None:
            _require(self.phase_seconds < 60 / self.request.binding.bpm)
        if self.reason == "measured":
            _require(self.phase_seconds is not None and self.fold_lock is not None)


@dataclass(frozen=True, slots=True)
class AnchorResearchInput:
    binding: MeasurementBinding
    candidates: tuple[ResearchCandidate, ...]
    beat_anchor: float | None = None
    bar_confidence: float | None = None
    phrase_anchor: float | None = None
    phrase_confidence: float | None = None
    production_blockers: tuple[str, ...] = ()
    observations: tuple[WindowObservation, ...] = ()
    reference: ReferenceClaim | None = None

    def __post_init__(self):
        _require(type(self.binding) is MeasurementBinding)
        self.binding.__post_init__()
        _tuple(self.candidates, ResearchCandidate)
        _require(len({c.id for c in self.candidates}) == len(self.candidates))
        _require(all(c.time_seconds <= self.binding.duration for c in self.candidates))
        for value in (self.beat_anchor, self.phrase_anchor):
            _optional_number(value)
            _require(value is None or value <= self.binding.duration)
        for value in (self.bar_confidence, self.phrase_confidence):
            _optional_number(value, confidence=True)
        _tuple(self.production_blockers, str)
        _tuple(self.observations, WindowObservation)
        if self.reference is not None:
            _require(type(self.reference) is ReferenceClaim)
            self.reference.__post_init__()


@dataclass(frozen=True, slots=True)
class AnchorResearchPolicy:
    window_seconds: float = 8.0
    max_windows: int = 6
    max_audio_seconds: float = 48.0
    max_window_samples: int = 2_000_000

    def __post_init__(self):
        _number(self.window_seconds, positive=True)
        _number(self.max_windows, integer=True)
        _number(self.max_audio_seconds)
        _number(self.max_window_samples, positive=True, integer=True)


@dataclass(frozen=True, slots=True)
class AnchorResearchPlan:
    inputs: tuple[AnchorResearchInput, ...]
    policy: AnchorResearchPolicy
    requests: tuple[WindowRequest, ...]
    reused: tuple[WindowObservation, ...]
    issues: tuple[str, ...]

    def __post_init__(self):
        _tuple(self.inputs, AnchorResearchInput)
        _require(type(self.policy) is AnchorResearchPolicy)
        self.policy.__post_init__()
        _tuple(self.requests, WindowRequest)
        _tuple(self.reused, WindowObservation)
        _tuple(self.issues, str)

    @property
    def new_window_count(self):
        return len(self.requests) - len(self.reused)

    @property
    def new_audio_seconds(self):
        reused = {o.request for o in self.reused}
        return sum(w.duration_seconds for w in self.requests if w not in reused)

    @property
    def max_window_samples(self):
        reused = {o.request for o in self.reused}
        return max((round(w.duration_seconds * w.binding.sample_rate)
                    for w in self.requests if w not in reused), default=0)


@dataclass(frozen=True, slots=True)
class AnchorHypothesis:
    origin: str
    anchor_seconds: float | None
    derivation_window: WindowRequest | None = None

    def __post_init__(self):
        _choice(self.origin, ("existing_anchor", "local_phase"))
        _optional_number(self.anchor_seconds)
        if self.derivation_window is not None:
            _require(type(self.derivation_window) is WindowRequest)
            self.derivation_window.__post_init__()
        _require(self.origin != "local_phase" or (
            self.anchor_seconds is not None and self.derivation_window is not None))


@dataclass(frozen=True, slots=True)
class AnchorEvidence:
    binding: MeasurementBinding
    candidate: ResearchCandidate
    hypothesis: AnchorHypothesis
    beat_status: str
    max_phase_error_ms: float | None
    beat_strength: float | None
    independent_windows: int
    bar_confidence: float | None
    phrase_confidence: float | None
    phrase_anchor: float | None
    production_blockers: tuple[str, ...]
    reference: ReferenceClaim | None
    identity_proof_source: str
    bar_status: str = "unverified"
    phrase_status: str = "unverified"

    def __post_init__(self):
        for value, cls in ((self.binding, MeasurementBinding), (self.candidate, ResearchCandidate),
                           (self.hypothesis, AnchorHypothesis)):
            _require(type(value) is cls)
            value.__post_init__()
        _choice(self.beat_status, ("unverified", "consistent", "mismatch"))
        _choice(self.bar_status, ("unverified",))
        _choice(self.phrase_status, ("unverified",))
        _optional_number(self.max_phase_error_ms)
        _number(self.independent_windows, integer=True)
        for value in (self.beat_strength, self.bar_confidence, self.phrase_confidence):
            _optional_number(value, confidence=True)
        _optional_number(self.phrase_anchor)
        _tuple(self.production_blockers, str)
        if self.reference is not None:
            _require(type(self.reference) is ReferenceClaim)
            self.reference.__post_init__()
        _require(self.identity_proof_source == ("caller_provided" if self.reference is not None else "none"))


@dataclass(frozen=True, slots=True)
class AnchorResearchReport:
    plan: AnchorResearchPlan
    results: tuple[AnchorEvidence, ...]
    observations: tuple[WindowObservation, ...]
    research_coverage: tuple[WindowRequest, ...]
    errors: tuple[str, ...]
    proof_source: str
    observation_proof_sources: tuple[str, ...]
    reused_windows: int = 0
    reader_calls: int = 0
    dsp_calls: int = 0
    decoded_seconds: float = 0.0
    binding_proof_source: str = "caller_provided"
    contract: str = "research_only"

    def __post_init__(self):
        _require(type(self.plan) is AnchorResearchPlan)
        self.plan.__post_init__()
        _tuple(self.results, AnchorEvidence)
        _tuple(self.observations, WindowObservation)
        _tuple(self.research_coverage, WindowRequest)
        _tuple(self.errors, str)
        _tuple(self.observation_proof_sources, str)
        _require(len(self.observation_proof_sources) == len(self.observations))
        for value in self.observation_proof_sources:
            _choice(value, ("caller_provided", "core_dsp_on_injected_audio", "reader_failure"))
        _choice(self.proof_source, ("caller_provided_observations", "core_dsp_on_injected_audio"))
        for value in (self.reused_windows, self.reader_calls, self.dsp_calls):
            _number(value, integer=True)
        _number(self.decoded_seconds)
        _choice(self.binding_proof_source, ("caller_provided",))
        _choice(self.contract, ("research_only",))


class ResearchWindowReader(Protocol):
    def __call__(self, request: WindowRequest) -> tuple[MeasurementBinding, object]:
        """Liefert exakte Bindung und mono-ndarray; keine Besitzuebernahme."""
        ...


def _windows(binding, candidate, policy):
    width = policy.window_seconds
    result = []
    for shift in (-1.5, -.5, .5):
        start = candidate.time_seconds + shift * width
        if start >= 0 and start + width <= binding.duration:
            result.append(WindowRequest(binding, start, width))
    return tuple(result)


def plan_anchor_research(inputs, *, policy):
    """Reiner Plan: keine Sourcepruefung und kein nachtraegliches Budgetwachstum."""
    _tuple(inputs, AnchorResearchInput)
    _require(type(policy) is AnchorResearchPolicy)
    policy.__post_init__()
    _require(len({ntpath.normcase(ntpath.normpath(i.binding.source.path)) for i in inputs}) == len(inputs))
    requests, reused, issues = [], [], []
    for item in inputs:
        if not item.binding.complete:
            issues.append("missing_binding")
            continue
        # Vier Taktlagen sind hier nur Hypothesen fuer den bestehenden 4/4-Vertrag.
        if item.binding.meter != 4:
            issues.append("unsupported_meter")
            continue
        cached = {}
        for observation in item.observations:
            if observation.request in cached:
                _require(cached[observation.request] == observation)
            cached[observation.request] = observation
        for candidate in item.candidates:
            for request in _windows(item.binding, candidate, policy):
                if request not in requests:
                    requests.append(request)
                    observation = cached.get(request)
                    if observation is not None and observation.reason in ("measured", "weakfold"):
                        reused.append(observation)
    result = AnchorResearchPlan(inputs, policy, tuple(requests), tuple(reused), tuple(issues))
    _require(result.new_window_count <= policy.max_windows)
    _require(result.new_audio_seconds <= policy.max_audio_seconds)
    _require(result.max_window_samples <= policy.max_window_samples)
    return result


def _validate_plan(plan):
    _require(type(plan) is AnchorResearchPlan)
    _require(plan == plan_anchor_research(plan.inputs, policy=plan.policy))


def _independent(observations):
    selected = []
    end = -1.0
    for observation in sorted(observations, key=lambda o: o.request.offset_seconds):
        if observation.request.offset_seconds >= end:
            selected.append(observation)
            end = observation.request.offset_seconds + observation.request.duration_seconds
    return selected


def evaluate_anchor_hypotheses(plan, observations):
    """Caller-Messungen auswerten; ein Treffer ist keine musikalische Groundtruth."""
    _validate_plan(plan)
    _tuple(observations, WindowObservation)
    _require(len({o.request for o in observations}) == len(observations))
    _require(all(o.request in plan.requests for o in observations))
    by_request = {o.request: o for o in plan.reused}
    for observation in observations:
        _require(observation.request not in by_request or by_request[observation.request] == observation)
        by_request[observation.request] = observation
    # Bestehende Schwellen importieren, niemals eine Forschungsabsenkung erfinden.
    from .downbeat import BEATGRID_MIN_FOLD_LOCK, BEATGRID_MIN_WINDOWS, BEATGRID_MAX_PHASE_ERROR_SECONDS

    results = []
    for item in plan.inputs:
        interval = 60 / item.binding.bpm
        for candidate in item.candidates:
            windows = _windows(item.binding, candidate, plan.policy)
            usable = _independent([by_request[w] for w in windows if w in by_request
                                   and by_request[w].reason == "measured"
                                   and by_request[w].fold_lock >= BEATGRID_MIN_FOLD_LOCK])
            hypotheses = [AnchorHypothesis("existing_anchor", item.beat_anchor)]
            if usable:
                seed = usable[0]
                phase = (seed.request.offset_seconds + seed.phase_seconds) % interval
                hypotheses.extend(AnchorHypothesis("local_phase", phase + k * interval, seed.request)
                                  for k in range(item.binding.meter))
            for hypothesis in hypotheses:
                existing = hypothesis.origin == "existing_anchor"
                errors = []
                if hypothesis.anchor_seconds is not None:
                    for o in usable:
                        expected = (hypothesis.anchor_seconds - o.request.offset_seconds) % interval
                        delta = abs(o.phase_seconds - expected) % interval
                        errors.append(min(delta, interval - delta))
                independent = sum(o.request != hypothesis.derivation_window for o in usable)
                status = "unverified"
                if len(errors) >= BEATGRID_MIN_WINDOWS and independent > 0:
                    status = ("consistent" if max(errors) <= BEATGRID_MAX_PHASE_ERROR_SECONDS + 1e-12
                              else "mismatch")
                results.append(AnchorEvidence(
                    item.binding, candidate, hypothesis, status,
                    max(errors) * 1000 if errors else None,
                    min(o.fold_lock for o in usable) if usable else None,
                    independent, item.bar_confidence if existing else None,
                    item.phrase_confidence if existing else None, item.phrase_anchor if existing else None,
                    item.production_blockers, item.reference,
                    "caller_provided" if item.reference is not None else "none"))
    ordered = tuple(by_request[w] for w in plan.requests if w in by_request)
    return AnchorResearchReport(
        plan, tuple(results), ordered,
        tuple(o.request for o in ordered if o.reason in ("measured", "weakfold")),
        tuple(o.reason for o in ordered if o.reason in ("decode_error", "invalidinput", "estimationerror")),
        "caller_provided_observations", ("caller_provided",) * len(ordered), len(plan.reused))


def _checkpoint(cancel):
    if cancel is not None:
        try:
            value = cancel()
            if type(value) is not bool:
                raise ValueError
        except Exception:
            raise AnchorResearchError("Abbruchpruefung fehlgeschlagen") from None
        if value:
            raise AnchorResearchError("Ankerforschung abgebrochen")


def _progress(progress, completed, total):
    if progress is not None:
        try:
            progress((completed, total))
        except Exception:
            raise AnchorResearchError("Fortschrittsmeldung fehlgeschlagen") from None


def run_anchor_research(plan, *, window_reader, cancel=None, progress=None):
    """Nur geplante RAM-Fenster messen. Fremde Fehlertexte niemals weitergeben."""
    _validate_plan(plan)
    _require(callable(window_reader))
    _require(cancel is None or callable(cancel))
    _require(progress is None or callable(progress))
    _checkpoint(cancel)
    _progress(progress, 0, plan.new_window_count)
    observations = []
    reused = {o.request for o in plan.reused}
    reader_calls = dsp_calls = 0
    decoded_seconds = 0.0
    for request in plan.requests:
        if request in reused:
            continue
        _checkpoint(cancel)
        reader_calls += 1
        try:
            returned = window_reader(request)
        except AnchorResearchError:
            raise AnchorResearchError("Quellzugriff abgebrochen") from None
        except Exception:
            observations.append(WindowObservation(request, None, None, "decode_error"))
        else:
            _checkpoint(cancel)
            import numpy as np
            try:
                _require(type(returned) is tuple and len(returned) == 2)
                binding, audio = returned
                _require(type(binding) is MeasurementBinding and binding == request.binding)
                _require(type(audio) is np.ndarray and audio.ndim == 1 and audio.dtype.kind in "fi")
                _require(len(audio) == round(request.duration_seconds * binding.sample_rate))
                _require(np.all(np.isfinite(audio)))
            except Exception:
                raise AnchorResearchError("Fenstervertrag verletzt") from None
            decoded_seconds += len(audio) / binding.sample_rate
            from .downbeat import validate_beatgrid_windows
            dsp_calls += 1
            try:
                measured = validate_beatgrid_windows(
                    [(request.offset_seconds, audio)], binding.sample_rate, binding.bpm,
                    anchor=0.0, collect_diagnostics=True)
                detail, = measured.window_diagnostics
                observation = WindowObservation(request, detail.phase_seconds, detail.fold_lock, detail.reason)
            except Exception:
                observation = WindowObservation(request, None, None, "estimationerror")
            observations.append(observation)
            # Keine Sample-Referenzen im Ergebnis halten.
            del audio, returned
        _checkpoint(cancel)
        _progress(progress, reader_calls, plan.new_window_count)
    report = evaluate_anchor_hypotheses(plan, tuple(observations))
    _checkpoint(cancel)
    return replace(report, reader_calls=reader_calls, dsp_calls=dsp_calls,
                   decoded_seconds=decoded_seconds,
                   observation_proof_sources=tuple(
                       "caller_provided" if o.request in reused else
                       "reader_failure" if o.reason == "decode_error" else "core_dsp_on_injected_audio"
                       for o in report.observations),
                   proof_source="core_dsp_on_injected_audio" if dsp_calls else "caller_provided_observations")

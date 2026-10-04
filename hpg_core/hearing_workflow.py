"""Qt-freie, quellbasierte Hoertest-Vorbereitung mit einer Publikationsgrenze."""
from __future__ import annotations

import argparse
import importlib
import math
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from .hearing_sources import (
    SourceRenderSink, SourceValidationError, load_source_session,
    normalize_source_roots, write_source_manifest,
)


class HearingError(RuntimeError):
    """Kontrollierter Fehler des nativen Workflows."""


class HearingValidationError(HearingError, ValueError):
    """Unzulaessige Konfiguration oder Quellreferenz."""


class HearingTargetExistsError(HearingError, FileExistsError):
    """Vorhandene Nutzerdaten werden nicht ueberschrieben."""


class HearingCancelledError(HearingError):
    """Abbruch vor der Publikationsgrenze."""


class HearingOperationError(HearingError):
    """Produzent oder Publikation ist fehlgeschlagen."""


@dataclass(frozen=True)
class PrepareConfig:
    mode: Literal["einzel", "kandidaten", "dramaturgie"]
    output_dir: Path
    cache: Path
    count: int = 100
    bpm_tolerance: float = 2.0
    energy_direction: Literal["auto", "up", "down", "maintain"] = "auto"
    harmonic_strictness: int = 7
    allow_experimental: bool = True
    seed: int = 20260820
    only_genre: str | None = None
    sequence_tracks: int = 16
    transitions_per_variant: int = 5
    max_versions_per_pair: int = 5
    three_notes: bool = False
    tracks_once: bool = False
    selection_profile: Path | None = None
    workers: int = 1
    transition_type_mode: Literal["kontrolliert", "produktion"] = "kontrolliert"
    storage: Literal["source_refs"] = "source_refs"
    source_roots: tuple[Path, ...] = ()


@dataclass(frozen=True)
class Progress:
    completed: int
    total: int
    message: str = ""
    phase: str = "prepare"

    @property
    def percent(self) -> int:
        return min(100, max(0, round(100 * self.completed / self.total))) if self.total else 0


@dataclass(frozen=True)
class PrepareResult:
    mode: str
    output_dir: Path
    clip_count: int
    pair_count: int
    manifest_path: Path
    status: Literal["prepared"] = "prepared"
    source_roots: tuple[Path, ...] = ()
    warnings: tuple[str, ...] = ()


class CancellationToken:
    RUNNING = "running"
    CANCELLED = "cancelled"
    PUBLISHING = "publishing"
    COMPLETE = "complete"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = self.RUNNING

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def request_cancel(self) -> bool:
        with self._lock:
            if self._state != self.RUNNING:
                return False
            self._state = self.CANCELLED
            return True

    def checkpoint(self) -> None:
        with self._lock:
            if self._state == self.CANCELLED:
                # Produzenten muessen dies vor ihren Reservepaar-Fallbacks weiterwerfen.
                raise InterruptedError("Hoertest-Vorbereitung abgebrochen")

    def begin_publish(self) -> bool:
        with self._lock:
            if self._state != self.RUNNING:
                return False
            self._state = self.PUBLISHING
            return True

    def mark_complete(self) -> None:
        with self._lock:
            if self._state != self.PUBLISHING:
                raise HearingOperationError("Publikationszustand ist ungueltig")
            self._state = self.COMPLETE


_PRODUCERS = {
    "einzel": "_befehl_prepare_intern",
    "kandidaten": "_befehl_prepare_kandidaten_intern",
    "dramaturgie": "_befehl_prepare_dramaturgie_intern",
}


def _validate_config(config: PrepareConfig, rate) -> None:
    if not isinstance(config, PrepareConfig):
        raise HearingValidationError("PrepareConfig wird erwartet")
    if type(config.mode) is not str or config.mode not in _PRODUCERS or config.storage != "source_refs":
        raise HearingValidationError("Unbekannter Modus oder Speichervertrag")
    for name, minimum, maximum in (
        ("count", 1, rate.MAX_ANZAHL), ("sequence_tracks", rate.MIN_SEQUENZ_TRACKS, rate.MAX_ANZAHL),
        ("transitions_per_variant", rate.MIN_DRAMATURGIE_UEBERGAENGE, rate.MAX_ANZAHL),
        ("max_versions_per_pair", 1, 5), ("workers", 1, 4), ("harmonic_strictness", 1, 10),
    ):
        value = getattr(config, name)
        if type(value) is not int or not minimum <= value <= maximum:
            raise HearingValidationError(f"{name}: ganze Zahl {minimum}..{maximum} erforderlich")
    if type(config.seed) is not int:
        raise HearingValidationError("seed muss eine ganze Zahl sein")
    if (type(config.bpm_tolerance) not in (int, float) or not math.isfinite(config.bpm_tolerance)
            or not 0 < config.bpm_tolerance <= rate.PAAR_BPM_MAX):
        raise HearingValidationError("bpm_tolerance liegt ausserhalb des Parser-Vertrags")
    for name in ("allow_experimental", "three_notes", "tracks_once"):
        if type(getattr(config, name)) is not bool:
            raise HearingValidationError(f"{name} muss boolesch sein")
    if config.energy_direction not in ("auto", "up", "down", "maintain"):
        raise HearingValidationError("energy_direction ist ungueltig")
    if config.transition_type_mode not in ("kontrolliert", "produktion"):
        raise HearingValidationError("transition_type_mode ist ungueltig")
    if config.only_genre is not None and config.only_genre not in rate.CANONICAL_GENRES:
        raise HearingValidationError("only_genre ist nicht kanonisch")
    if any(not isinstance(getattr(config, name), Path) for name in ("output_dir", "cache")):
        raise HearingValidationError("output_dir und cache muessen Path sein")
    if not config.cache.is_file():
        raise HearingValidationError("Cache-Datei fehlt")
    if type(config.source_roots) is not tuple or any(not isinstance(p, Path) for p in config.source_roots):
        raise HearingValidationError("source_roots muss ein Path-Tupel sein")
    if not config.source_roots:
        raise HearingValidationError("source_roots: explizit gewaehlte Quellordner erforderlich")
    if config.selection_profile is not None and (
        not isinstance(config.selection_profile, Path) or not config.selection_profile.is_file()
    ):
        raise HearingValidationError("selection_profile muss eine vorhandene Datei sein")
    if config.mode != "kandidaten" and (
        config.three_notes or config.tracks_once or config.selection_profile is not None
        or config.max_versions_per_pair != 5 or config.workers != 1
        or config.harmonic_strictness != 7 or config.allow_experimental is not True
        or config.transition_type_mode != "kontrolliert"
    ):
        raise HearingValidationError("Kandidatenparameter sind fuer diesen Modus nicht anwendbar")
    if config.mode != "dramaturgie" and (config.sequence_tracks != 16 or config.transitions_per_variant != 5):
        raise HearingValidationError("Dramaturgieparameter sind fuer diesen Modus nicht anwendbar")
    if config.mode == "dramaturgie" and (
        config.count != 100 or config.only_genre is not None or config.energy_direction != "auto"
    ):
        raise HearingValidationError("Parameter werden vom Dramaturgieproduzenten nicht verwendet")


def _producer_namespace(config, staging, target, sink, token, progress):
    def report(phase: str, completed: int, total: int) -> None:
        token.checkpoint()
        if (type(phase) is not str or type(completed) is not int or type(total) is not int
                or not 0 <= completed <= total):
            raise HearingOperationError("Ungueltiger Produzentenfortschritt")
        if progress is not None:
            progress(Progress(completed, total, phase, phase))
    return argparse.Namespace(
        modus=config.mode, out=staging, anzeige_out=target, cache=str(config.cache),
        anzahl=config.count, bpm_toleranz=config.bpm_tolerance,
        energy_direction=None if config.energy_direction == "auto" else config.energy_direction,
        harmonic_strictness=config.harmonic_strictness, allow_experimental=config.allow_experimental,
        seed=config.seed, nur_genre=config.only_genre, sequenz_tracks=config.sequence_tracks,
        uebergaenge_pro_variante=config.transitions_per_variant,
        max_versionen_pro_paar=config.max_versions_per_pair, dreinoten_pilot=config.three_notes,
        tracks_einmalig=config.tracks_once, auswahlprofil=config.selection_profile,
        workers=config.workers, transition_type_mode=config.transition_type_mode,
        storage=config.storage, source_roots=sink.source_roots,
        hpg_render_sink=sink.emit, hpg_cancel=token, hpg_progress=report,
    )


def create_set(
    config: PrepareConfig,
    progress: Callable[[Progress], None] | None = None,
    cancel: CancellationToken | None = None,
) -> PrepareResult:
    """Publiziert vorbereitete Referenzen; behauptet keinen Render-/Audit-Erfolg."""
    rate = importlib.import_module("tools.rate_transitions")
    _validate_config(config, rate)
    target = config.output_dir.absolute()
    if target.exists() or target.is_symlink():
        raise HearingTargetExistsError(f"Ausgabeziel existiert bereits: {target}")
    token = cancel or CancellationToken()
    staging = None
    try:
        token.checkpoint()
        rate._reject_pending_wal(config.cache)
        cache_fingerprint = rate._fingerprint_cache(config.cache)
        roots = normalize_source_roots(config.source_roots)
        token.checkpoint()
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent))
        sink = SourceRenderSink(staging, roots, checkpoint=token.checkpoint)
        args = _producer_namespace(config, staging, target, sink, token, progress)
        status = getattr(rate, _PRODUCERS[config.mode])(args)
        if type(status) is not int or status != 0:
            raise HearingOperationError(f"Produzent meldete Status {status!r}; nichts publiziert")
        token.checkpoint()
        manifest_path = write_source_manifest(staging, config.mode, sink)
        session = load_source_session(staging, verify_source_contents=False)
        if config.mode != "dramaturgie" and session.pair_count != config.count:
            raise HearingValidationError("Produzent lieferte nicht die verlangte Paarzahl")
        if config.mode == "dramaturgie" and any(
            len(v["transitions"]) != config.transitions_per_variant
            for v in session.producer_manifest["variants"]
        ):
            raise HearingValidationError("Dramaturgie-Uebergangszahl stimmt nicht")
        token.checkpoint()
        # Vor der Grenze stehen alle falliblen Beobachter und Validatoren.
        if progress is not None:
            progress(Progress(session.clip_count, session.clip_count, "prepared", "prepared"))
        token.checkpoint()
        final_session = load_source_session(staging)
        if final_session.manifest != session.manifest:
            raise HearingValidationError("Quellmanifest wurde vor Publikation veraendert")
        rate._reject_pending_wal(config.cache)
        if rate._fingerprint_cache(config.cache) != cache_fingerprint:
            raise HearingValidationError("Cache wurde waehrend Vorbereitung veraendert")
        if session.producer_manifest and session.producer_manifest["cache"] != {
            "version": rate.CACHE_VERSION, **cache_fingerprint
        }:
            raise HearingValidationError("Produzentenmanifest ist nicht an ausgewaehlten Cache gebunden")
        token.checkpoint()
        if not token.begin_publish():
            raise InterruptedError("Abbruch vor Publikation")
        rate._publiziere_staging(staging, target)
        token.mark_complete()
        return PrepareResult(config.mode, target, session.clip_count, session.pair_count,
                             target / manifest_path.name, source_roots=roots)
    except InterruptedError as exc:
        raise HearingCancelledError(str(exc)) from exc
    except SourceValidationError as exc:
        raise HearingValidationError(str(exc)) from exc
    except HearingError:
        raise
    except (OSError, ValueError, RuntimeError) as exc:
        raise HearingOperationError(str(exc)) from exc
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)

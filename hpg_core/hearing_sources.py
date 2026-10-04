"""Versionierte Quellreferenzen ohne permanente Hoertest-Audiodateien."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Callable, Mapping

from .transition_renderer import TransitionClipSpec, SUPPORTED_TRANSITION_TYPES

SOURCE_MANIFEST_NAME = "hearing_source_manifest.json"
SOURCE_FORMAT = "hpg_hearing_source_refs"
SOURCE_VERSION = 1
# Explizites v1-Schema: neue Rendererfelder duerfen alte Referenzen nicht umdeuten.
_STRING_FIELDS = frozenset({
    "track_a_path", "track_b_path", "transition_type", "beatgrid_status_a", "beatgrid_status_b",
    "analysis_mode_a", "analysis_mode_b",
})
_BOOL_FIELDS = frozenset({
    "downbeat_reliable_a", "downbeat_reliable_b", "bar_phase_reliable_a", "bar_phase_reliable_b",
    "strict_beat_sync", "normalize_rms", "use_compressor",
})
_NUMBER_FIELDS = frozenset({
    "mix_out_sec", "mix_in_sec", "crossfade_sec", "pre_roll_sec", "post_roll_sec",
    "bass_cutoff_hz", "bpm_a", "bpm_b", "first_downbeat_a", "first_downbeat_b",
    "normalize_target_db", "lufs_a", "lufs_b",
})
SPEC_V1_FIELDS = _STRING_FIELDS | _BOOL_FIELDS | _NUMBER_FIELDS | {"target_sr", "tempo_ratio"}
_MANIFEST_KEYS = {
    "format", "format_version", "mode", "status", "source_roots", "specs", "sources", "immutable_metadata",
}
_MODE_FILES = {
    "einzel": {"merkmale.csv", "bewertung.csv"},
    "kandidaten": {"merkmale.csv", "bewertung.csv", "reihenfolge.json", "kandidaten_manifest.json",
                   "LIESMICH-kandidaten.txt"},
    "dramaturgie": {"dramaturgie_manifest.json", "bewertung.csv", "dramaturgie_bewertung.csv", "README.md"},
}
_MUTABLE_FILES = {"bewertung.csv", "dramaturgie_bewertung.csv"}


class SourceValidationError(ValueError):
    """Quell-/Metadatenvertrag ist ungueltig; kein Renderbeleg."""


def _exact(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise SourceValidationError(f"{label}: kein exaktes Schema")
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SourceValidationError(f"Doppelter JSON-Schluessel: {key}")
        result[key] = value
    return result


def strict_json_bytes(raw: bytes):
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise SourceValidationError("Nicht-endliche JSON-Zahl")
        return number
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs,
                          parse_float=finite_float,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              SourceValidationError(f"Nicht-endliche JSON-Konstante: {value}")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SourceValidationError("JSON ist unlesbar") from exc


def _json_file(path: Path):
    return strict_json_bytes(path.read_bytes())


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value):
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def normalize_source_roots(roots: tuple[Path, ...]) -> tuple[Path, ...]:
    if not roots:
        raise SourceValidationError("Mindestens ein konkreter Quellordner ist erforderlich")
    normalized = []
    for root in roots:
        root = Path(root).resolve(strict=True)
        if not root.is_dir() or root == Path(root.anchor):
            raise SourceValidationError("Quellwurzel muss konkreter Ordner unterhalb der Laufwerkswurzel sein")
        if root not in normalized:
            normalized.append(root)
    return tuple(normalized)


def _fingerprint(path: Path) -> dict:
    before = path.stat()
    if not path.is_file():
        raise SourceValidationError(f"Quelle ist keine Datei: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    signature = lambda s: (s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_ino, s.st_dev)
    if signature(before) != signature(after):
        raise SourceValidationError(f"Datei waehrend Fingerprint veraendert: {path}")
    return {"size": after.st_size, "sha256": digest.hexdigest()}


def _fingerprint_schema(value, label):
    _exact(value, {"size", "sha256"}, label)
    if (type(value["size"]) is not int or value["size"] < 0
            or type(value["sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])):
        raise SourceValidationError(f"{label}: ungueltiger Fingerprint")


def validate_spec_v1(spec: dict) -> dict:
    _exact(spec, SPEC_V1_FIELDS, "TransitionClipSpec v1")
    if {field.name for field in fields(TransitionClipSpec)} != SPEC_V1_FIELDS:
        raise SourceValidationError("Renderer-Feldschema passt nicht mehr zu source_refs v1")
    for name in _STRING_FIELDS:
        if type(spec[name]) is not str or not spec[name]:
            raise SourceValidationError(f"{name}: nichtleerer Text erforderlich")
    for name in _BOOL_FIELDS:
        if type(spec[name]) is not bool:
            raise SourceValidationError(f"{name}: bool erforderlich")
    for name in _NUMBER_FIELDS | {"tempo_ratio"}:
        value = spec[name]
        if name == "tempo_ratio" and value is None:
            continue
        if type(value) not in (int, float) or not math.isfinite(value):
            raise SourceValidationError(f"{name}: endliche Zahl erforderlich")
    for name in ("mix_out_sec", "mix_in_sec", "pre_roll_sec", "post_roll_sec", "first_downbeat_a", "first_downbeat_b"):
        if spec[name] < 0:
            raise SourceValidationError(f"{name}: negativer Wert")
    for name in ("crossfade_sec", "bass_cutoff_hz", "bpm_a", "bpm_b"):
        if spec[name] <= 0:
            raise SourceValidationError(f"{name}: positiver Wert erforderlich")
    if spec["tempo_ratio"] is not None and spec["tempo_ratio"] <= 0:
        raise SourceValidationError("tempo_ratio muss positiv oder null sein")
    if type(spec["target_sr"]) is not int or spec["target_sr"] <= 0:
        raise SourceValidationError("target_sr: positive ganze Zahl erforderlich")
    if spec["transition_type"] not in SUPPORTED_TRANSITION_TYPES:
        raise SourceValidationError("Unbekannter Transition-Type")
    for name in ("track_a_path", "track_b_path"):
        if not Path(spec[name]).is_absolute():
            raise SourceValidationError("Quellpfade muessen absolut sein")
    return spec


def _virtual_path(value: str) -> str:
    if (type(value) is not str or "\\" in value or ":" in value or "\0" in value
            or value != value.strip()):
        raise SourceValidationError("Ungueltiger virtueller Clip-Pfad")
    path = PurePosixPath(value)
    if (path.is_absolute() or len(path.parts) < 2 or path.parts[0] != "clips"
            or path.suffix != ".wav" or any(part in ("", ".", "..") for part in value.split("/"))
            or path.as_posix() != value):
        raise SourceValidationError("Virtueller Clip-Pfad muss kanonisch unter clips/ liegen")
    return value


class SourceRenderSink:
    """Erfasst exakte Specs; Originalquellen werden nur gelesen."""
    def __init__(self, staging_root: Path, source_roots: tuple[Path, ...], *,
                 checkpoint: Callable[[], None] | None = None):
        self.staging_root = Path(staging_root).resolve(strict=True)
        self.source_roots = normalize_source_roots(source_roots)
        self.checkpoint = checkpoint or (lambda: None)
        self._specs: dict[str, dict] = {}
        self._sources: dict[str, dict] = {}
        self.failure: Exception | None = None

    @property
    def specs(self) -> dict:
        return strict_json_bytes(json.dumps(self._specs, allow_nan=False).encode())

    @property
    def sources(self) -> dict:
        return strict_json_bytes(json.dumps(self._sources, allow_nan=False).encode())

    def emit(self, spec: TransitionClipSpec, target: Path) -> None:
        try:
            self.checkpoint()
            if self.failure is not None:
                raise SourceValidationError("Vorheriger Quellfehler; gesamter Satz wird abgebrochen")
            if not isinstance(spec, TransitionClipSpec):
                raise SourceValidationError("TransitionClipSpec erforderlich")
            payload = validate_spec_v1(asdict(spec))
            target = Path(target)
            if ".." in target.parts:
                raise SourceValidationError("Clip-Ziel enthaelt Traversal")
            target = target.resolve()
            try:
                logical = _virtual_path(target.relative_to(self.staging_root).as_posix())
            except ValueError as exc:
                raise SourceValidationError("Clip-Ziel verlaesst eigenen Staging-Ordner") from exc
            if logical in self._specs:
                raise SourceValidationError(f"Doppelter Clip-Pfad: {logical}")
            additions = {}
            for name in ("track_a_path", "track_b_path"):
                path_text = payload[name]
                source = Path(path_text).resolve(strict=True)
                root = next((r for r in self.source_roots if _inside(source, r)), None)
                if root is None:
                    raise SourceValidationError(f"Quelle ausserhalb gewaehlter Quellordner: {path_text}")
                if _inside(source, self.staging_root):
                    raise SourceValidationError("Originalquelle darf nicht im Staging liegen")
                entry = {"path": path_text, **_fingerprint(source), "root": str(root)}
                previous = self._sources.get(path_text)
                if previous is not None and previous != entry:
                    raise SourceValidationError(f"Quelle seit erster Referenz veraendert: {path_text}")
                additions[path_text] = entry
            self.checkpoint()
            self._sources.update(additions)
            self._specs[logical] = payload
        except Exception as exc:
            # Auch verschluckte Reservepaarfehler verhindern die Publikation.
            self.failure = exc
            raise


def _inventory(root: Path, mode: str, *, with_manifest: bool) -> dict[str, Path]:
    if _link(root):
        raise SourceValidationError("Satzwurzel darf kein Link sein")
    allowed = _MODE_FILES[mode] | ({SOURCE_MANIFEST_NAME} if with_manifest else set())
    files = {}
    for path in root.rglob("*"):
        if _link(path):
            raise SourceValidationError("Links sind im Quellsatz verboten")
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            if relative != "clips" and not relative.startswith("clips/"):
                raise SourceValidationError("Unerwarteter Metadaten-Unterordner")
            continue
        if not path.is_file() or relative not in allowed:
            raise SourceValidationError(f"Unerwartete Satzdatei; Audio ist verboten: {relative}")
        files[relative] = path
    if set(files) != allowed:
        raise SourceValidationError("Pflichtmetadaten fehlen oder Satzwurzel ist nicht exakt")
    return files


def _read_csv(path: Path, columns) -> list[dict]:
    try:
        reader = csv.DictReader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline=""))
        if tuple(reader.fieldnames or ()) != tuple(columns):
            raise SourceValidationError(f"{path.name}: falsche Spalten")
        rows = list(reader)
        if not rows or any(None in row or any(v is None for v in row.values()) for row in rows):
            raise SourceValidationError(f"{path.name}: leere oder fehlerhafte CSV")
        return rows
    except (UnicodeError, csv.Error) as exc:
        raise SourceValidationError(f"{path.name}: unlesbare CSV") from exc


def _number(row, key):
    try:
        value = float(row[key])
    except (ValueError, KeyError, TypeError) as exc:
        raise SourceValidationError(f"CSV-Feld {key} ist ungueltig") from exc
    if not math.isfinite(value):
        raise SourceValidationError(f"CSV-Feld {key} ist nicht endlich")
    return value


def _matches_spec(spec, a, b, timing, transition_type, target_sr=None, overlap_tolerance=1e-6):
    if spec["track_a_path"] != a or spec["track_b_path"] != b:
        raise SourceValidationError("Spec-Quellen stimmen nicht mit Produzentenmetadaten")
    for key, value in zip(("mix_out_sec", "mix_in_sec", "crossfade_sec"), timing):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise SourceValidationError("Produzentenplan hat ungueltige Zeitwerte")
        tolerance = overlap_tolerance if key == "crossfade_sec" else 1e-6
        if abs(spec[key] - value) > tolerance:
            raise SourceValidationError(f"Spec-{key} widerspricht Produzentenplan")
    if spec["transition_type"] != transition_type or (target_sr is not None and spec["target_sr"] != target_sr):
        raise SourceValidationError("Spec-Technik/Samplerate widerspricht Produzentenplan")


def _single_metadata(root, specs, rt):
    columns = ("pair_id", *rt.ALLE_FAKTOREN, "crossfade_sek", *rt.ZUSATZ_SPALTEN,
               *rt.PLAN_AUDIT_SPALTEN, "track_a", "track_b")
    rows = _read_csv(root / "merkmale.csv", columns)
    ratings = _read_csv(root / "bewertung.csv", ("pair_id", "clip", "bewertung"))
    ids = [f"{i:03d}" for i in range(1, len(rows) + 1)]
    if [r["pair_id"] for r in rows] != ids or [r["pair_id"] for r in ratings] != ids:
        raise SourceValidationError("Einzel-Paar-IDs sind nicht eindeutig und kanonisch geordnet")
    refs = [f"clips/{pid}.wav" for pid in ids]
    if [r["clip"] for r in ratings] != refs or set(refs) != set(specs):
        raise SourceValidationError("Einzel-Referenzen sind nicht exakt 1:1")
    for row, rating, ref in zip(rows, ratings, refs):
        if rating["bewertung"] not in ("", "1", "2", "3", "4", "5"):
            raise SourceValidationError("Einzel-Bewertung liegt nicht in 1..5")
        for key in rt.ALLE_FAKTOREN:
            if not 0 <= _number(row, key) <= 1:
                raise SourceValidationError("Einzel-Faktor liegt nicht in 0..1")
        sample_rate = _number(row, "plan_target_sr")
        if not sample_rate.is_integer():
            raise SourceValidationError("Plan-Samplerate muss ganzzahlig sein")
        _matches_spec(specs[ref], row["track_a"], row["track_b"],
                      [_number(row, key) for key in ("plan_mix_out_sec", "plan_mix_in_sec", "plan_overlap_sec")],
                      row["plan_transition_type"], int(sample_rate))
    return len(rows), {}


def _candidate_metadata(root, specs, rt):
    # Wiederverwendung des strikten Manifestvertrags ohne WAV-Pruefungen.
    from tools.audit_candidate_set import _load_manifest
    producer = _json_file(root / rt.KANDIDATEN_MANIFEST_NAME)
    try:
        producer = _load_manifest(root / rt.KANDIDATEN_MANIFEST_NAME)
    except ValueError as exc:
        raise SourceValidationError(str(exc)) from exc
    rows = _read_csv(root / "merkmale.csv", rt.MERKMALE_KANDIDATEN_SPALTEN)
    columns = rt.BEWERTUNG_DREINOTEN_SPALTEN if producer.get("rating_schema") == "three_notes_v1" else rt.BEWERTUNG_KANDIDATEN_SPALTEN
    ratings = _read_csv(root / "bewertung.csv", columns)
    expected = [(p["pair_id"], c["clip_id"]) for p in producer["pairs"] for c in p["clips"]]
    if ([(r["pair_id"], r["clip_id"]) for r in rows] != expected
            or [(r["pair_id"], r["clip_id"]) for r in ratings] != expected):
        raise SourceValidationError("Kandidaten-IDs sind nicht exakt geordnet 1:1")
    refs = [f"clips/{cid}.wav" for _, cid in expected]
    if [r["clip"] for r in rows] != refs or set(refs) != set(specs):
        raise SourceValidationError("Kandidaten-Referenzen sind nicht exakt 1:1")
    try:
        rt.validiere_kandidaten_csvs(rows, ratings)
    except ValueError as exc:
        raise SourceValidationError(str(exc)) from exc
    order = _json_file(root / "reihenfolge.json")
    expected_order = {p["pair_id"]: rt.reihenfolge_fuer_paar(
        p["pair_id"], [c["clip_id"] for c in p["clips"]], producer["render_args"]["seed"])
        for p in producer["pairs"]}
    if order != expected_order:
        raise SourceValidationError("Kandidaten-Reihenfolge stimmt nicht mit eingefrorenem Seed")
    flat = [(p, c) for p in producer["pairs"] for c in p["clips"]]
    for row, ref, (pair, clip) in zip(rows, refs, flat):
        _matches_spec(specs[ref], pair["track_a"], pair["track_b"],
                      [clip[k] for k in ("t_out", "t_in", "overlap_sec")], clip["rendered_transition_type"])
        for key, expected_value in (("t_out", clip["t_out"]), ("t_in", clip["t_in"]),
                                    ("blend_bars", clip["blend_bars"]), ("crossfade_sek", clip["overlap_sec"])):
            if abs(_number(row, key) - expected_value) > (0.011 if key == "crossfade_sek" else 1e-12):
                raise SourceValidationError("Kandidaten-CSV widerspricht Manifest")
        if (row["track_a"] != pair["track_a"] or row["track_b"] != pair["track_b"]
                or row["rendered_transition_type"] != clip["rendered_transition_type"]
                or row["transition_type_mode"] != producer["render_args"]["transition_type_mode"]
                or _number(row, "bpm_toleranz") != producer["scoring_snapshot"]["rank_args"]["bpm_tolerance"]
                or row["energy_direction"] != producer["scoring_snapshot"]["rank_args"]["energy_direction"]):
            raise SourceValidationError("Kandidaten-CSV-Kontext widerspricht Manifest")
    return len(producer["pairs"]), producer


def _validate_frozen_dramaturgy_context(variant):
    """Prueft den gespeicherten Laufvertrag, niemals heutige Praeferenzen.

    Vollstaendigkeit ist vor dem Produktionsvalidator zwingend: dessen
    Kompatibilitaetspfad fuer partielle Snapshots wuerde live nachladen.
    Dies ist Schema-/Strategiepruefung, kein Algorithmus-Replay-/Auditbeleg.
    """
    from .playlist import (
        _has_complete_run_profile_snapshot, _complete_run_scoring_context,
        resolve_scoring_context,
    )
    context = variant["scoring_context"]
    if type(context) is not dict or not _has_complete_run_profile_snapshot(context):
        raise SourceValidationError("Dramaturgie-Kontext ist kein vollstaendiger eingefrorener Snapshot")
    strategy = variant["canonical_strategy"]
    parameters = variant["requested_parameters"]
    profile_keys = {"track_tolerances_by_genre", "candidate_tolerances_by_genre", "candidate_schema_ranks_by_genre"}
    try:
        scalars = resolve_scoring_context(strategy, parameters)
        if set(context) != set(scalars) | profile_keys:
            raise ValueError("Kontext hat nicht exakt die Strategie-/Snapshotfelder")
        # Typ-/Bereichspruefung, kanonische Genres, vollstaendige Profile,
        # Gewichtssummen und eindeutige bekannte Schema-Raenge ohne Live-I/O.
        validated = _complete_run_scoring_context(strategy, parameters, context)
        if validated != context or {k: context[k] for k in scalars} != scalars:
            raise ValueError("Gespeicherte Strategieparameter stimmen nicht")
        if context["candidate_schema_ranks_by_genre"]["Unknown"] != []:
            raise ValueError("Unknown-Schemafallback muss leer sein")
    except (ValueError, TypeError, KeyError) as exc:
        raise SourceValidationError(f"Dramaturgie-Kontext ist ungueltig: {exc}") from exc


def _dramaturgy_metadata(root, specs, rt):
    producer = _json_file(root / rt.DRAMATURGIE_MANIFEST_NAME)
    _exact(producer, {"format_version", "contract", "app_version", "algorithm_build", "cache", "pool_hash",
                      "ordered_pool_track_ids", "candidate_choice_hash", "variants"}, "Dramaturgiemanifest")
    if (type(producer["format_version"]) is not int or producer["format_version"] != rt.DRAMATURGIE_MANIFEST_VERSION
            or producer["contract"] != rt.DRAMATURGIE_CONTRACT):
        raise SourceValidationError("Dramaturgie-Produzentenvertrag stimmt nicht")
    expected_variants = rt.dramaturgie_varianten()
    variants = producer["variants"]
    if type(variants) is not list or [v.get("variant_id") for v in variants if type(v) is dict] != [v["variant_id"] for v in expected_variants]:
        raise SourceValidationError("Dramaturgiematrix ist nicht exakt vollstaendig")
    pool = producer["ordered_pool_track_ids"]
    if (type(pool) is not list or any(type(p) is not str for p in pool) or len(pool) != len(set(pool))
            or len(pool) < rt.MIN_SEQUENZ_TRACKS
            or any(re.fullmatch(r"[0-9a-f]{64}", p) is None for p in pool)
            or producer["pool_hash"] != rt._kanonischer_json_hash(pool)
            or producer["candidate_choice_hash"] != rt._kanonischer_json_hash({})):
        raise SourceValidationError("Dramaturgiepool oder Kandidatenwahl-Bindung stimmt nicht")
    from .playlist import TransitionPlan
    plan_keys = {f.name for f in fields(TransitionPlan)}
    transition_ids, refs = [], []
    for variant, expected in zip(variants, expected_variants):
        _exact(variant, set(expected) | {"scoring_context", "pool_hash", "ordered_track_ids", "transitions"}, "Variante")
        if any(variant[k] != v for k, v in expected.items()):
            raise SourceValidationError("Dramaturgieparameter stimmen nicht mit Matrix")
        _validate_frozen_dramaturgy_context(variant)
        if variant["pool_hash"] != producer["pool_hash"]:
            raise SourceValidationError("Dramaturgie-Poolhash stimmt nicht")
        ordered = variant["ordered_track_ids"]
        if type(ordered) is not list or sorted(ordered) != sorted(pool):
            raise SourceValidationError("Variantenplaylist ist keine Pool-Permutation")
        transitions = variant["transitions"]
        if type(transitions) is not list or not transitions:
            raise SourceValidationError("Dramaturgie-Uebergaenge fehlen")
        previous = -1
        for transition in transitions:
            _exact(transition, {"transition_id", "index", "from_track_id", "to_track_id", "plan", "clip"}, "Transition")
            index = transition["index"]
            if type(index) is not int or not previous < index < len(ordered) - 1:
                raise SourceValidationError("Dramaturgie-Indizes sind ungueltig")
            previous = index
            if transition["from_track_id"] != ordered[index] or transition["to_track_id"] != ordered[index + 1]:
                raise SourceValidationError("Dramaturgie-Trackreferenz stimmt nicht")
            _exact(transition["plan"], plan_keys, "TransitionPlan")
            _exact(transition["clip"], {"path", "representation"}, "Source-Clip")
            clip = transition["clip"]
            ref = _virtual_path(clip["path"])
            if clip["representation"] != "source_reference_v1" or ref not in specs:
                raise SourceValidationError("Dramaturgie-Clip ist keine gebundene Quellreferenz")
            expected_id = f"{variant['variant_id']}__t{index + 1:03d}"
            if transition["transition_id"] != expected_id or ref != f"clips/{variant['variant_id']}/{expected_id}.wav":
                raise SourceValidationError("Dramaturgie-Clip-ID/Pfad stimmt nicht")
            plan = transition["plan"]
            spec = specs[ref]
            source_ids = [hashlib.sha256(rt._windows_pfadschluessel(spec[key]).encode("utf-8")).hexdigest()
                          for key in ("track_a_path", "track_b_path")]
            if source_ids != [transition["from_track_id"], transition["to_track_id"]]:
                raise SourceValidationError("Spec-Quellen stimmen nicht mit Dramaturgie-Track-IDs")
            _matches_spec(specs[ref], specs[ref]["track_a_path"], specs[ref]["track_b_path"],
                          [plan[k] for k in ("mix_out_a", "mix_in_b", "overlap")],
                          plan["transition_type"], plan["target_sr"])
            transition_ids.append(expected_id)
            refs.append(ref)
    if len(refs) != len(set(refs)) or set(refs) != set(specs):
        raise SourceValidationError("Dramaturgie-Referenzen sind nicht eindeutig 1:1")
    ratings = _read_csv(root / "bewertung.csv", rt.BEWERTUNG_DREINOTEN_SPALTEN)
    variant_ratings = _read_csv(root / "dramaturgie_bewertung.csv", rt.DRAMATURGIE_BEWERTUNG_SPALTEN)
    if ([(r["pair_id"], r["clip_id"]) for r in ratings] != [(cid, cid) for cid in transition_ids]
            or [r["variant_id"] for r in variant_ratings] != [v["variant_id"] for v in variants]):
        raise SourceValidationError("Dramaturgie-Bewertungsreferenzen stimmen nicht")
    for row in ratings:
        if any(row[key] not in ("", "1", "2", "3", "4", "5") for key in ("track_note", "technik_note", "gesamt_note")) or row["gewaehlt"] not in ("", "0", "1"):
            raise SourceValidationError("Dramaturgie-Transitionbewertung ist ungueltig")
    for row in variant_ratings:
        if any(row[key] not in ("", "1", "2", "3", "4", "5") for key in (
            "dramaturgie_gesamt", "energieverlauf", "peak_platzierung", "kohaerenz"
        )):
            raise SourceValidationError("Dramaturgie-Variantenbewertung ist ungueltig")
    return len(refs), producer


@dataclass(frozen=True)
class SourceSession:
    directory: Path
    mode: str
    manifest: Mapping
    clip_count: int
    pair_count: int
    producer_manifest: Mapping
    status: str = "prepared"
    source_contents_verified: bool = True

    @property
    def verification_scope(self) -> str:
        return "source contents verified" if self.source_contents_verified else (
            "structural only, no original content integrity proof")

    @property
    def specs(self) -> dict:
        return _thaw(self.manifest["specs"])

    @property
    def sources(self) -> dict:
        return _thaw(self.manifest["sources"])

    @property
    def manifest_path(self) -> Path:
        return self.directory / SOURCE_MANIFEST_NAME

    @property
    def playback_paths(self) -> tuple[str, ...]:
        """Virtuelle POSIX-Referenzen; keine existierenden WAV-Pfade."""
        return tuple(self.manifest["specs"])


def _validate_manifest(root: Path, manifest: dict, *, with_manifest: bool,
                       verify_source_contents: bool = True) -> SourceSession:
    _exact(manifest, _MANIFEST_KEYS, "Quellmanifest")
    if (manifest["format"] != SOURCE_FORMAT or type(manifest["format_version"]) is not int
            or manifest["format_version"] != SOURCE_VERSION or manifest["status"] != "prepared"
            or type(manifest["mode"]) is not str or manifest["mode"] not in _MODE_FILES):
        raise SourceValidationError("Unbekannter Quellmanifestvertrag oder Status")
    mode = manifest["mode"]
    raw_roots = manifest["source_roots"]
    if type(raw_roots) is not list or any(type(p) is not str for p in raw_roots):
        raise SourceValidationError("Quellwurzel-Liste ist ungueltig")
    roots = normalize_source_roots(tuple(Path(p) for p in raw_roots))
    if [str(r) for r in roots] != raw_roots:
        raise SourceValidationError("Quellwurzeln sind nicht kanonisch/eindeutig")
    files = _inventory(root, mode, with_manifest=with_manifest)
    immutable = manifest["immutable_metadata"]
    if type(immutable) is not dict or set(immutable) != _MODE_FILES[mode] - _MUTABLE_FILES:
        raise SourceValidationError("Immutable Metadatenliste ist nicht exakt")
    for name, expected in immutable.items():
        _fingerprint_schema(expected, name)
        if _fingerprint(files[name]) != expected:
            raise SourceValidationError(f"Metadaten wurden veraendert: {name}")
    specs, sources = manifest["specs"], manifest["sources"]
    if type(specs) is not dict or not specs or type(sources) is not dict or not sources:
        raise SourceValidationError("Specs/Quellen fehlen")
    referenced = set()
    for ref, spec in specs.items():
        _virtual_path(ref)
        validate_spec_v1(spec)
        referenced.update((spec["track_a_path"], spec["track_b_path"]))
    if referenced != set(sources):
        raise SourceValidationError("Spec-Pfade und Quellen sind nicht exakt 1:1")
    for key, source in sources.items():
        _exact(source, {"path", "size", "sha256", "root"}, "Quelle")
        _fingerprint_schema({k: source[k] for k in ("size", "sha256")}, "Quelle")
        if source["path"] != key or type(source["root"]) is not str or Path(source["root"]) not in roots:
            raise SourceValidationError("Quellpfad/Quellwurzel ist nicht exakt gebunden")
        path = Path(key).resolve(strict=True)
        if Path(key) != path:
            raise SourceValidationError("Quellpfad ist nicht kanonisch an seine Identitaet gebunden")
        if not _inside(path, Path(source["root"])) or _inside(path, root):
            raise SourceValidationError("Quelle verlaesst gewaehlten Quellordner oder liegt im Satz")
        if not path.is_file() or path.stat().st_size != source["size"]:
            raise SourceValidationError(f"Originalquelle hat falschen Typ oder Groesse: {key}")
        if verify_source_contents and _fingerprint(path) != {k: source[k] for k in ("size", "sha256")}:
            raise SourceValidationError(f"Originalquelle wurde veraendert: {key}")
    from tools import rate_transitions as rt
    validators = {"einzel": _single_metadata, "kandidaten": _candidate_metadata, "dramaturgie": _dramaturgy_metadata}
    pair_count, producer = validators[mode](root, specs, rt)
    # Nochmals nach dem Parsen binden; keine stille Metadatenmutation akzeptieren.
    for name, expected in immutable.items():
        if _fingerprint(files[name]) != expected:
            raise SourceValidationError(f"Metadaten waehrend Validierung veraendert: {name}")
    return SourceSession(root, mode, _freeze(manifest), len(specs), pair_count,
                         _freeze(producer), source_contents_verified=verify_source_contents)


def write_source_manifest(root: Path, mode: str, sink: SourceRenderSink) -> Path:
    """Validiert vorbereitete Metadaten und schreibt nur das separate Manifest."""
    root = Path(root).resolve(strict=True)
    if root != sink.staging_root or mode not in _MODE_FILES:
        raise SourceValidationError("Staging-/Modusvertrag stimmt nicht")
    if sink.failure is not None:
        if isinstance(sink.failure, InterruptedError):
            raise sink.failure
        raise SourceValidationError("Quell-Sink meldete Fehler; gesamter Satz wird verworfen") from sink.failure
    files = _inventory(root, mode, with_manifest=False)
    manifest = {
        "format": SOURCE_FORMAT, "format_version": SOURCE_VERSION, "mode": mode, "status": "prepared",
        "source_roots": [str(r) for r in sink.source_roots], "specs": sink.specs, "sources": sink.sources,
        "immutable_metadata": {name: _fingerprint(path) for name, path in files.items() if name not in _MUTABLE_FILES},
    }
    _validate_manifest(root, manifest, with_manifest=False)
    path = root / SOURCE_MANIFEST_NAME
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return path


def load_source_session(directory: Path, *, verify_source_contents: bool = True) -> SourceSession:
    """Prueft vorbereitete Quellreferenzen; kein Replay-/Render-Audit.

    False: structural only, no original content integrity proof. Dabei bleiben
    Metadatenbindung, Quellpfadidentitaet, Containment und Dateigroessen geprueft.
    Die strikte Standardeinstellung liest und verifiziert Originalinhalte.
    """
    if type(verify_source_contents) is not bool:
        raise SourceValidationError("verify_source_contents muss boolesch sein")
    directory = Path(directory)
    if _link(directory):
        raise SourceValidationError("Satzwurzel darf kein Link sein")
    root = directory.resolve(strict=True)
    return _validate_manifest(root, _json_file(root / SOURCE_MANIFEST_NAME), with_manifest=True,
                              verify_source_contents=verify_source_contents)

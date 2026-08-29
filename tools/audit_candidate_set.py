"""Strenger, schreibgeschuetzter Post-Render-Audit fuer Kandidaten-Hoertests."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import soundfile as sf

from hpg_core import candidate_choices
from hpg_core.app_metadata import APP_VERSION
from hpg_core.caching import CACHE_VERSION
from hpg_core.config import PAAR_BPM_MAX
from hpg_core.genres import CANONICAL_GENRES
from hpg_core.mix_candidates import SCHEMA_PRIORITAET
from hpg_core.pair_candidates import FAKTOREN, rank_pair_candidates
from hpg_core.tolerances import KANDIDATEN_GEWICHT_SCHLUESSEL, NICHT_GEWICHT_SCHLUESSEL
from hpg_core import transition_renderer
from tools.rate_transitions import (
    BEWERTUNG_KANDIDATEN_SPALTEN,
    KANDIDATEN_MANIFEST_NAME,
    ALGORITHM_BUILD_SCHEME,
    HARMONIC_GATE_SCOPE,
    MAX_ANZAHL,
    MIN_GROOVE,
    MIN_HARMONIC_SCORE,
    MIN_OVERALL_SCORE,
    MERKMALE_KANDIDATEN_SPALTEN,
    _hauptschema,
    _algorithm_build_fingerprint,
    _fingerprint_kandidatensatz,
    _transition_type_fuer,
    lade_tracks_aus_cache,
    loese_genre_auf,
    reihenfolge_fuer_paar,
    rendere_kandidat,
    transition_metrics_from_candidate,
)

NUMERIC_FIELDS = (
    *FAKTOREN, "score", "blend_bars", "t_out", "t_in", "confidence_out",
    "confidence_in", "crossfade_sek", "bpm_a", "bpm_b",
    "bpm_toleranz",
)
ENERGY_DIRECTIONS = {"auto", "up", "down", "maintain"}
ROOT_KEYS = {
    "format_version", "app_version", "algorithm_build", "hearing_test_contract",
    "cache", "render_args", "scoring_snapshot", "pairs",
}
SCORING_KEYS = {
    "rank_args", "candidate_tolerances_by_genre", "candidate_tolerances_fallback",
    "candidate_schema_ranks_by_genre", "candidate_schema_rank_fallback", "candidate_choices",
}
RANK_KEYS = {"bpm_tolerance", "energy_direction", "harmonic_strictness", "allow_experimental"}
RENDER_KEYS = {"anzahl", "max_versionen_pro_paar", "nur_genre", "transition_type_mode", "seed"}
PROFILE_KEYS = set(KANDIDATEN_GEWICHT_SCHLUESSEL) | set(NICHT_GEWICHT_SCHLUESSEL)
PAIR_KEYS = {"pair_id", "track_a", "track_b", "clips"}
CLIP_KEYS = {
    "clip_id", "rank", "t_out", "t_in", "blend_bars", "overlap_sec",
    "rendered_transition_type",
}
SET_ROOT_NAMES = frozenset({
    "merkmale.csv", "bewertung.csv", "reihenfolge.json",
    KANDIDATEN_MANIFEST_NAME, "LIESMICH-kandidaten.txt", "clips",
})


class AuditError(ValueError):
    pass


def _inside(path: Path, root: Path) -> bool:
    try:
        path_s, root_s = os.path.normcase(str(path)), os.path.normcase(str(root))
        return os.path.commonpath((path_s, root_s)) == root_s
    except ValueError:
        return False


def _resolved_existing(path: Path, kind: str) -> Path:
    resolved = path.resolve(strict=True)
    if kind == "dir" and not resolved.is_dir():
        raise AuditError(f"Kein Verzeichnis: {resolved}")
    if kind == "file" and not resolved.is_file():
        raise AuditError(f"Keine Datei: {resolved}")
    return resolved


def validate_paths(set_dir: Path, cache: Path, report: Path) -> tuple[Path, Path, Path]:
    set_real = _resolved_existing(set_dir, "dir")
    cache_real = _resolved_existing(cache, "file")
    report_parent = report.parent.resolve(strict=True)
    if not report_parent.is_dir():
        raise AuditError(f"Report-Elternpfad ist kein Verzeichnis: {report_parent}")
    report_real = report_parent / report.name
    protected_cache_paths = {
        os.path.normcase(str(Path(f"{cache_real}{suffix}")))
        for suffix in ("", "-wal", "-shm", "-journal", ".lock", "-lock")
    }
    protected_cache_paths.add(os.path.normcase(
        str(Path(os.path.splitext(str(cache_real))[0] + ".lock"))
    ))
    if os.path.normcase(str(report_real)) in protected_cache_paths or _inside(report_real, set_real):
        raise AuditError("--report muss separat ausserhalb von --set-dir und --cache liegen")
    if report_real.exists():
        raise AuditError(f"--report existiert bereits und wird nicht ueberschrieben: {report_real}")
    return set_real, cache_real, report_real


def _fingerprint_tree(root: Path) -> dict[str, tuple[int, str]]:
    result = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result[str(path.relative_to(root))] = (path.stat().st_size, digest)
    return result


def _fingerprint_file(path: Path) -> tuple[int, str]:
    return path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()


def _fingerprint_cache_family(cache: Path) -> dict[str, tuple[int, str] | None]:
    paths = {
        suffix: Path(f"{cache}{suffix}")
        for suffix in ("", "-wal", "-shm", "-journal", ".lock", "-lock")
    }
    paths["stem.lock"] = Path(os.path.splitext(str(cache))[0] + ".lock")
    return {
        label: _fingerprint_file(path) if path.exists() else None
        for label, path in paths.items()
    }


def _read_csv(path: Path, expected: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != expected:
            raise AuditError(f"Falsche Spalten in {path.name}")
        return list(reader)


def _finite(row: dict[str, str], field: str, clip_id: str) -> float:
    raw = str(row.get(field, "")).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise AuditError(f"{clip_id}: Pflichtwert {field} ist keine Zahl") from exc
    if not math.isfinite(value):
        raise AuditError(f"{clip_id}: Pflichtwert {field} ist nicht endlich")
    return value


def _reject_pending_wal(cache: Path) -> None:
    wal = Path(f"{cache}-wal")
    if wal.exists() and wal.stat().st_size:
        raise AuditError(f"Cache hat ausstehendes WAL und wird nicht angefasst: {wal}")


def _load_tracks_immutable(cache: Path) -> list:
    try:
        return lade_tracks_aus_cache(str(cache))
    except Exception as exc:
        raise AuditError(f"Cache verletzt den strikten Producer-Vertrag: {exc}") from exc


def _track_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.normpath(path)))


def _exact_dict(value, keys: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise AuditError(f"{label}: Schluessel muessen exakt {sorted(keys)!r} sein")
    return value


def _strict_int(value, label: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if type(value) is not int:
        raise AuditError(f"{label}: ganze Zahl erforderlich")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise AuditError(f"{label}: Wert ausserhalb des erlaubten Bereichs")
    return value


def _strict_number(value, label: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuditError(f"{label}: echte Zahl erforderlich")
    number = float(value)
    if not math.isfinite(number):
        raise AuditError(f"{label}: Zahl ist nicht endlich")
    if minimum is not None and number < minimum or maximum is not None and number > maximum:
        raise AuditError(f"{label}: Wert ausserhalb des erlaubten Bereichs")
    return number


def _profile(value, label: str) -> dict:
    profile = _exact_dict(value, PROFILE_KEYS, label)
    weights = [
        _strict_number(profile[key], f"{label}.{key}", minimum=0.0)
        for key in KANDIDATEN_GEWICHT_SCHLUESSEL
    ]
    if not math.isclose(sum(weights), 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise AuditError(f"{label}: Kandidatengewichte ergeben nicht 1")
    _strict_number(profile["groove_sim_floor"], f"{label}.groove_sim_floor", minimum=0.0, maximum=1.0)
    for key in ("bass_delta_max", "brightness_delta_max"):
        if _strict_number(profile[key], f"{label}.{key}") <= 0.0:
            raise AuditError(f"{label}.{key}: muss positiv sein")
    return profile


def _schema_rank(value, label: str) -> list[str]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise AuditError(f"{label}: Schema-Rang muss eine Zeichenkettenliste sein")
    if len(value) != len(set(value)) or any(item not in SCHEMA_PRIORITAET for item in value):
        raise AuditError(f"{label}: unbekanntes oder doppeltes Schema")
    return value


def _choice_snapshot(value) -> dict:
    if type(value) is not dict or any(type(key) is not str or not key for key in value):
        raise AuditError("scoring_snapshot.candidate_choices: ungueltiges Objekt")
    result = {}
    for key, choice in value.items():
        try:
            result[key] = candidate_choices._validiere_wahl(choice)
        except (TypeError, ValueError) as exc:
            raise AuditError(f"candidate_choices[{key!r}]: {exc}") from exc
    return result


def _load_manifest(path: Path, cache: Path | None = None) -> dict:
    try:
        manifest = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda raw: (_ for _ in ()).throw(
                AuditError(f"Manifest enthaelt nicht-endliche JSON-Konstante {raw}")
            ),
        )
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        raise AuditError(f"{KANDIDATEN_MANIFEST_NAME} ist unlesbar: {exc}") from exc
    _exact_dict(manifest, ROOT_KEYS, "Manifest")
    if _strict_int(manifest["format_version"], "format_version") != 1:
        raise AuditError("format_version ist nicht 1")
    if manifest["app_version"] != APP_VERSION:
        raise AuditError("app_version stimmt nicht mit dem lokalen Build")
    algorithm_build = _exact_dict(
        manifest["algorithm_build"], {"scheme", "files", "sha256"},
        "algorithm_build",
    )
    if algorithm_build.get("scheme") != ALGORITHM_BUILD_SCHEME:
        raise AuditError("algorithm_build.scheme ist unbekannt")
    _strict_int(algorithm_build.get("files"), "algorithm_build.files", minimum=1)
    build_digest = algorithm_build.get("sha256")
    if type(build_digest) is not str or re.fullmatch(r"[0-9a-f]{64}", build_digest) is None:
        raise AuditError("algorithm_build.sha256 ist kein kanonischer SHA-256")
    if algorithm_build != _algorithm_build_fingerprint():
        raise AuditError("Algorithmus-/Build-Digest stimmt nicht mit lokalem Code")
    hearing_contract = _exact_dict(
        manifest["hearing_test_contract"],
        {"harmonic_gate_scope", "minimum_harmonic_score"},
        "hearing_test_contract",
    )
    if hearing_contract.get("harmonic_gate_scope") != HARMONIC_GATE_SCOPE:
        raise AuditError("Harmonie-Gate ist nicht als Hoertest-spezifisch deklariert")
    if _strict_number(
        hearing_contract.get("minimum_harmonic_score"),
        "hearing_test_contract.minimum_harmonic_score",
    ) != MIN_HARMONIC_SCORE:
        raise AuditError("Hoertest-Harmonie-Gate stimmt nicht mit lokalem Vertrag")

    cache_info = _exact_dict(manifest["cache"], {"version", "size", "sha256"}, "cache")
    if _strict_int(cache_info["version"], "cache.version") != CACHE_VERSION:
        raise AuditError("cache.version stimmt nicht")
    _strict_int(cache_info["size"], "cache.size", minimum=0)
    digest = cache_info["sha256"]
    if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise AuditError("cache.sha256 ist kein kanonischer SHA-256")
    if cache is not None:
        size, actual_digest = _fingerprint_file(cache)
        if cache_info != {"version": CACHE_VERSION, "size": size, "sha256": actual_digest}:
            raise AuditError("Manifest-Cache-Fingerprint stimmt nicht mit --cache")

    render_args = _exact_dict(manifest["render_args"], RENDER_KEYS, "render_args")
    anzahl = _strict_int(
        render_args["anzahl"], "render_args.anzahl", minimum=1, maximum=MAX_ANZAHL
    )
    pair_ids = tuple(f"{n:03d}" for n in range(1, anzahl + 1))
    _strict_int(render_args["max_versionen_pro_paar"], "render_args.max_versionen_pro_paar", minimum=1, maximum=5)
    genre = render_args["nur_genre"]
    if genre is not None and (type(genre) is not str or genre not in CANONICAL_GENRES):
        raise AuditError("render_args.nur_genre ist ungueltig")
    _strict_int(render_args["seed"], "render_args.seed")
    if render_args["transition_type_mode"] not in {"kontrolliert", "produktion"}:
        raise AuditError("render_args.transition_type_mode ist ungueltig")

    scoring = _exact_dict(manifest["scoring_snapshot"], SCORING_KEYS, "scoring_snapshot")
    rank_args = _exact_dict(scoring["rank_args"], RANK_KEYS, "rank_args")
    _strict_number(rank_args["bpm_tolerance"], "rank_args.bpm_tolerance", minimum=0.0, maximum=PAAR_BPM_MAX)
    if float(rank_args["bpm_tolerance"]) <= 0.0:
        raise AuditError("rank_args.bpm_tolerance muss positiv sein")
    if rank_args["energy_direction"] not in ENERGY_DIRECTIONS:
        raise AuditError("rank_args.energy_direction ist ungueltig")
    _strict_int(
        rank_args["harmonic_strictness"], "rank_args.harmonic_strictness",
        minimum=1, maximum=10,
    )
    if type(rank_args["allow_experimental"]) is not bool:
        raise AuditError("rank_args.allow_experimental muss boolesch sein")

    profiles = _exact_dict(
        scoring["candidate_tolerances_by_genre"], set(CANONICAL_GENRES),
        "candidate_tolerances_by_genre",
    )
    for name in CANONICAL_GENRES:
        _profile(profiles[name], f"candidate_tolerances_by_genre.{name}")
    _profile(scoring["candidate_tolerances_fallback"], "candidate_tolerances_fallback")
    schemas = _exact_dict(
        scoring["candidate_schema_ranks_by_genre"], set(CANONICAL_GENRES),
        "candidate_schema_ranks_by_genre",
    )
    for name in CANONICAL_GENRES:
        _schema_rank(schemas[name], f"candidate_schema_ranks_by_genre.{name}")
    if _schema_rank(scoring["candidate_schema_rank_fallback"], "candidate_schema_rank_fallback") != []:
        raise AuditError("candidate_schema_rank_fallback muss exakt leer sein")
    _choice_snapshot(scoring["candidate_choices"])

    if type(manifest["pairs"]) is not list or len(manifest["pairs"]) != len(pair_ids):
        raise AuditError(f"Manifest-Paare muessen exakt {anzahl} Eintraege sein")
    for expected_pair, pair in zip(pair_ids, manifest["pairs"]):
        _exact_dict(pair, PAIR_KEYS, f"Paar {expected_pair}")
        if pair["pair_id"] != expected_pair:
            raise AuditError("Manifest-Paare folgen nicht render_args.anzahl")
        if any(type(pair[key]) is not str or not pair[key] for key in ("track_a", "track_b")):
            raise AuditError(f"{expected_pair}: Trackpfade sind ungueltig")
        clips = pair["clips"]
        maximum = render_args["max_versionen_pro_paar"]
        if type(clips) is not list or not 1 <= len(clips) <= maximum:
            raise AuditError(f"{expected_pair}: ungueltige Manifest-Clipanzahl")
        for rank, clip in enumerate(clips, 1):
            _exact_dict(clip, CLIP_KEYS, f"{expected_pair}_k{rank}")
            if clip["clip_id"] != f"{expected_pair}_k{rank}" or _strict_int(clip["rank"], "clip.rank") != rank:
                raise AuditError(f"{expected_pair}: Clip-Rang/ID ist nicht kanonisch")
            for key in ("t_out", "t_in"):
                _strict_number(clip[key], f"{clip['clip_id']}.{key}", minimum=0.0)
            _strict_int(clip["blend_bars"], f"{clip['clip_id']}.blend_bars", minimum=1)
            if _strict_number(clip["overlap_sec"], f"{clip['clip_id']}.overlap_sec") <= 0.0:
                raise AuditError(f"{clip['clip_id']}.overlap_sec muss positiv sein")
            transition_type = clip["rendered_transition_type"]
            if type(transition_type) is not str or transition_type not in transition_renderer.SUPPORTED_TRANSITION_TYPES:
                raise AuditError(f"{clip['clip_id']}: unbekannter Transition-Type")
            if render_args["transition_type_mode"] == "kontrolliert" and transition_type != "pro_eq_swap":
                raise AuditError(f"{clip['clip_id']}: kontrollierter Satz verlangt pro_eq_swap")
    return manifest


def _parse_set(set_dir: Path, cache: Path | None = None) -> tuple[list[dict], dict[str, dict], dict, dict]:
    root_names = {path.name for path in set_dir.iterdir()}
    if root_names != SET_ROOT_NAMES:
        raise AuditError(
            f"Satzwurzel muss exakt {sorted(SET_ROOT_NAMES)!r} enthalten"
        )
    required = {
        name: (set_dir / name).resolve(strict=True)
        for name in SET_ROOT_NAMES
    }
    if any(not _inside(path, set_dir) for path in required.values()):
        raise AuditError("Eine Satzdatei verlaesst --set-dir ueber einen Symlink")
    if not required["clips"].is_dir():
        raise AuditError("clips ist kein Verzeichnis")
    if any(not path.is_file() for name, path in required.items() if name != "clips"):
        raise AuditError("Satzwurzel enthaelt einen ungueltigen Pflichtdateityp")
    merkmale = _read_csv(required["merkmale.csv"], MERKMALE_KANDIDATEN_SPALTEN)
    bewertung = _read_csv(required["bewertung.csv"], BEWERTUNG_KANDIDATEN_SPALTEN)
    try:
        order = json.loads(required["reihenfolge.json"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"reihenfolge.json ist unlesbar: {exc}") from exc
    manifest = _load_manifest(required[KANDIDATEN_MANIFEST_NAME], cache)
    pair_ids = tuple(
        f"{n:03d}" for n in range(1, manifest["render_args"]["anzahl"] + 1)
    )

    by_id: dict[str, dict] = {}
    per_pair: dict[str, list[int]] = {}
    pair_tracks: dict[str, tuple[str, str]] = {}
    scoring_contract: tuple[float, str] | None = None
    for row in merkmale:
        pair_id, clip_id = row["pair_id"], row["clip_id"]
        if pair_id != pair_id.strip() or clip_id != clip_id.strip():
            raise AuditError(f"IDs duerfen keinen Rand-Leerraum enthalten: {pair_id!r}/{clip_id!r}")
        if pair_id not in pair_ids:
            raise AuditError(f"Ungueltige ID-Kombination: {pair_id!r}/{clip_id!r}")
        try:
            index = int(clip_id.rsplit("_k", 1)[1])
        except ValueError as exc:
            raise AuditError(f"Ungueltige clip_id: {clip_id}") from exc
        if clip_id != f"{pair_id}_k{index}":
            raise AuditError(f"Nichtkanonische ID-Kombination: {pair_id!r}/{clip_id!r}")
        if clip_id in by_id:
            raise AuditError(f"Doppelte clip_id in merkmale.csv: {clip_id}")
        tracks = (_track_key(row["track_a"]), _track_key(row["track_b"]))
        if pair_id in pair_tracks and pair_tracks[pair_id] != tracks:
            raise AuditError(f"{pair_id}: Kandidaten verweisen auf verschiedene Track-Paare")
        pair_tracks[pair_id] = tracks
        values = {field: _finite(row, field, clip_id) for field in NUMERIC_FIELDS}
        direction = str(row.get("energy_direction", "")).strip().casefold()
        if direction not in ENERGY_DIRECTIONS:
            raise AuditError(f"{clip_id}: energy_direction ist ungueltig")
        if not 0.0 < values["bpm_toleranz"] <= PAAR_BPM_MAX:
            raise AuditError(
                f"{clip_id}: bpm_toleranz muss groesser 0 und hoechstens {PAAR_BPM_MAX:g} sein"
            )
        row_contract = (values["bpm_toleranz"], direction)
        if scoring_contract is None:
            scoring_contract = row_contract
        elif scoring_contract != row_contract:
            raise AuditError("bpm_toleranz/energy_direction sind im Satz nicht einheitlich")
        for field in (*FAKTOREN, "score", "confidence_out", "confidence_in"):
            if not 0.0 <= values[field] <= 1.0:
                raise AuditError(f"{clip_id}: {field} liegt nicht in 0..1")
        if values["blend_bars"] <= 0 or not values["blend_bars"].is_integer():
            raise AuditError(f"{clip_id}: blend_bars muss eine positive Ganzzahl sein")
        if values["bpm_a"] <= 0 or values["bpm_b"] <= 0 or values["crossfade_sek"] <= 0:
            raise AuditError(f"{clip_id}: BPM und crossfade_sek muessen positiv sein")
        if values["t_out"] < 0 or values["t_in"] < 0:
            raise AuditError(f"{clip_id}: Mixzeiten muessen >= 0 sein")
        rel = Path(row["clip"])
        if rel.is_absolute() or rel.as_posix() != f"clips/{clip_id}.wav":
            raise AuditError(f"{clip_id}: ungueltiger Clip-Pfad {row['clip']!r}")
        clip_real = (set_dir / rel).resolve(strict=True)
        clips_root = required["clips"]
        if not _inside(clip_real, clips_root) or not clip_real.is_file():
            raise AuditError(f"{clip_id}: Clip verlaesst clips-Verzeichnis")
        by_id[clip_id] = row
        per_pair.setdefault(pair_id, []).append(index)

    if set(per_pair) != set(pair_ids):
        raise AuditError("Paar-IDs folgen nicht render_args.anzahl")
    for pair_id, indices in per_pair.items():
        expected = list(range(1, len(indices) + 1))
        if sorted(indices) != expected or not 1 <= len(indices) <= 5:
            raise AuditError(f"{pair_id}: Kandidaten muessen zusammenhaengend k1..kN, N=1..5 sein")

    rating_ids: set[str] = set()
    for row in bewertung:
        cid = row["clip_id"]
        if cid != cid.strip() or row["pair_id"] != row["pair_id"].strip():
            raise AuditError("bewertung.csv enthaelt Rand-Leerraum in einer ID")
        if cid in rating_ids:
            raise AuditError(f"Doppelte clip_id in bewertung.csv: {cid}")
        if cid not in by_id or row["pair_id"] != by_id[cid]["pair_id"]:
            raise AuditError(f"bewertung.csv verweist inkonsistent auf {cid!r}")
        rating_ids.add(cid)
    if rating_ids != set(by_id):
        raise AuditError("bewertung.csv und merkmale.csv sind nicht 1:1")

    clip_files = {
        path.relative_to(required["clips"]).as_posix()
        for path in required["clips"].rglob("*") if path.is_file()
    }
    expected_wavs = {f"{cid}.wav" for cid in by_id}
    if clip_files != expected_wavs:
        raise AuditError("clips/ und CSV sind nicht exakt 1:1")
    if type(order) is not dict or list(order) != list(pair_ids):
        raise AuditError("reihenfolge.json folgt nicht render_args.anzahl")
    manifest_by_pair = {pair["pair_id"]: pair for pair in manifest["pairs"]}
    expected_flat_ids = [
        clip["clip_id"] for pair in manifest["pairs"] for clip in pair["clips"]
    ]
    if [row["clip_id"] for row in merkmale] != expected_flat_ids:
        raise AuditError(
            f"merkmale.csv ist nicht exakt {pair_ids[0]}..{pair_ids[-1]}/k1..kN geordnet"
        )
    if [row["clip_id"] for row in bewertung] != expected_flat_ids:
        raise AuditError("bewertung.csv folgt nicht exakt derselben Clip-Reihenfolge")
    seed_satz = manifest["render_args"]["seed"]
    for pair_id in pair_ids:
        entry = order[pair_id]
        expected_ids = [f"{pair_id}_k{n}" for n in range(1, len(manifest_by_pair[pair_id]["clips"]) + 1)]
        if type(entry) is not dict or set(entry) != {"seed", "clips"} or type(entry.get("seed")) is not int:
            raise AuditError(f"{pair_id}: ungueltiger Reihenfolge-Eintrag")
        clips = entry.get("clips")
        expected_order = reihenfolge_fuer_paar(pair_id, expected_ids, seed_satz)
        if entry != expected_order:
            raise AuditError(f"{pair_id}: Seed oder Shuffle stimmt nicht exakt")

        pair = manifest_by_pair[pair_id]
        csv_rows = [by_id[cid] for cid in expected_ids if cid in by_id]
        if len(csv_rows) != len(expected_ids):
            raise AuditError(f"{pair_id}: Manifest und CSV sind nicht 1:1")
        for clip, row in zip(pair["clips"], csv_rows):
            if (_track_key(pair["track_a"]), _track_key(pair["track_b"])) != (
                _track_key(row["track_a"]), _track_key(row["track_b"])
            ):
                raise AuditError(f"{clip['clip_id']}: Manifest-Trackpaar stimmt nicht")
            comparisons = {
                "t_out": _finite(row, "t_out", clip["clip_id"]),
                "t_in": _finite(row, "t_in", clip["clip_id"]),
                "blend_bars": int(_finite(row, "blend_bars", clip["clip_id"])),
                "overlap_sec": _finite(row, "crossfade_sek", clip["clip_id"]),
            }
            for key, actual in comparisons.items():
                if abs(float(clip[key]) - float(actual)) > (0.011 if key == "overlap_sec" else 1e-12):
                    raise AuditError(f"{clip['clip_id']}: Manifest-{key} stimmt nicht mit CSV")
            if row.get("rendered_transition_type") != clip["rendered_transition_type"]:
                raise AuditError(f"{clip['clip_id']}: Transition-Type stimmt nicht mit CSV")
            if row.get("transition_type_mode") != manifest["render_args"]["transition_type_mode"]:
                raise AuditError(f"{clip['clip_id']}: Transition-Type-Modus stimmt nicht mit Manifest")
            rank_args = manifest["scoring_snapshot"]["rank_args"]
            if _finite(row, "bpm_toleranz", clip["clip_id"]) != float(rank_args["bpm_tolerance"]):
                raise AuditError(f"{clip['clip_id']}: BPM-Toleranz stimmt nicht mit Manifest")
            if row["energy_direction"] != rank_args["energy_direction"]:
                raise AuditError(f"{clip['clip_id']}: Energierichtung stimmt nicht mit Manifest")
    return merkmale, by_id, order, manifest


def _rank_pair_from_manifest(track_a, track_b, manifest: dict) -> list:
    scoring = manifest["scoring_snapshot"]
    rank_args = scoring["rank_args"]
    genre = loese_genre_auf(track_a)
    tolerances = scoring["candidate_tolerances_by_genre"].get(
        genre, scoring["candidate_tolerances_fallback"]
    )
    schema_rank = scoring["candidate_schema_ranks_by_genre"].get(
        genre, scoring["candidate_schema_rank_fallback"]
    )
    choice_key = candidate_choices.schluessel(track_a.filePath, track_b.filePath)
    return rank_pair_candidates(
        track_a,
        track_b,
        bpm_tolerance=float(rank_args["bpm_tolerance"]),
        energy_direction=None if rank_args["energy_direction"] == "auto" else rank_args["energy_direction"],
        harmonic_strictness=rank_args["harmonic_strictness"],
        allow_experimental=rank_args["allow_experimental"],
        tolerances=dict(tolerances),
        schema_rang=list(schema_rank),
        wahl=dict(scoring["candidate_choices"].get(choice_key, {})),
    )


def _candidate_for(row: dict, track_a, track_b, manifest: dict | None = None):
    """Kompatibilitaetshelfer; der strenge Audit ruft Ranking paarweise auf."""
    if manifest is None:
        raise AuditError("Kandidaten-Replay verlangt ein Manifest-Snapshot")
    candidates = _rank_pair_from_manifest(track_a, track_b, manifest)
    rank = int(row["clip_id"].rsplit("_k", 1)[1])
    if rank > len(candidates):
        raise AuditError(f"{row['clip_id']}: Kandidatenrang fehlt im Replay")
    candidate = candidates[rank - 1]
    _validate_candidate_row(row, track_a, track_b, candidate)
    return candidate


def _number_matches(row: dict, field: str, expected: float, tolerance: float) -> None:
    actual = _finite(row, field, row["clip_id"])
    if abs(actual - float(expected)) > tolerance:
        raise AuditError(f"{row['clip_id']}: {field} stimmt nicht mit dem Cache-Kandidaten")


def _text_matches(row: dict, field: str, expected: str) -> None:
    if str(row.get(field, "")) != str(expected):
        raise AuditError(f"{row['clip_id']}: {field} stimmt nicht mit dem Cache-Kandidaten")


def _validate_candidate_row(row: dict, track_a, track_b, pc) -> None:
    for field in FAKTOREN:
        value = pc.teilwerte.get(field)
        if value is None or not math.isfinite(float(value)):
            raise AuditError(f"{row['clip_id']}: Kandidat hat keinen endlichen Teilwert {field}")
        _number_matches(row, field, round(float(value), 6), 1e-12)
    _number_matches(row, "score", round(float(pc.score), 6), 1e-12)
    _number_matches(row, "t_out", float(pc.t_out), 1e-12)
    _number_matches(row, "t_in", float(pc.t_in), 1e-12)
    _number_matches(row, "crossfade_sek", round(float(pc.overlap_sec), 2), 1e-12)
    _number_matches(row, "blend_bars", int(pc.blend_bars), 0.0)
    _number_matches(row, "confidence_out", float(pc.out_a.confidence), 1e-12)
    _number_matches(row, "confidence_in", float(pc.in_b.confidence), 1e-12)
    _number_matches(row, "bpm_a", round(float(track_a.bpm), 1), 1e-12)
    _number_matches(row, "bpm_b", round(float(track_b.bpm), 1), 1e-12)
    expected_text = {
        "schema_out": _hauptschema(pc.out_a),
        "schema_in": _hauptschema(pc.in_b),
        "schemata_out": "|".join(pc.out_a.schema or []),
        "schemata_in": "|".join(pc.in_b.schema or []),
        "provenance_out": pc.out_a.provenance,
        "provenance_in": pc.in_b.provenance,
        "bpm_relation": pc.bpm_relation,
        "genre_a": loese_genre_auf(track_a),
        "genre_b": loese_genre_auf(track_b),
        "key_a": str(getattr(track_a, "camelotCode", "") or ""),
        "key_b": str(getattr(track_b, "camelotCode", "") or ""),
    }
    for field, expected in expected_text.items():
        _text_matches(row, field, expected)


def _compare_wav(actual: Path, fresh: Path, clip_id: str) -> dict:
    try:
        a_info, f_info = sf.info(actual), sf.info(fresh)
        a_pcm, _ = sf.read(actual, dtype="int16", always_2d=True)
        f_pcm, _ = sf.read(fresh, dtype="int16", always_2d=True)
    except Exception as exc:
        raise AuditError(f"{clip_id}: WAV unlesbar: {exc}") from exc
    shape_ok = a_pcm.shape == f_pcm.shape
    meta_ok = (
        a_info.samplerate == f_info.samplerate
        and a_info.channels == f_info.channels
        and a_info.format == f_info.format
        and a_info.subtype == f_info.subtype
    )
    pcm_ok = shape_ok and np.array_equal(a_pcm, f_pcm)
    if not (shape_ok and meta_ok and pcm_ok):
        raise AuditError(f"{clip_id}: PCM/Samplerate/Form weicht vom strikten Neurender ab")
    return {
        "samplerate": a_info.samplerate,
        "channels": a_info.channels,
        "frames": len(a_pcm),
        "format": a_info.format,
        "subtype": a_info.subtype,
    }


def _render_with_diagnostics(
    a, b, pc, pair_id: str, n: int, out_dir: Path, *,
    rendered_transition_type: str, transition_type_mode: str,
    bpm_toleranz: float, energy_direction: str | None,
) -> tuple[Path, list]:
    captured: list[float | None] = []
    original = transition_renderer._synchronize_and_verify_kicks

    def wrapped(ref_segment, segment_b, sr, bpm, cf_frames):
        corrected = original(ref_segment, segment_b, sr, bpm, cf_frames)
        captured[:] = transition_renderer._kick_lags_across_overlap(
            ref_segment, corrected, sr, bpm, cf_frames
        )
        return corrected

    transition_renderer._synchronize_and_verify_kicks = wrapped
    try:
        rendere_kandidat(
            a, b, pc, pair_id, n, out_dir,
            transition_type_mode=transition_type_mode,
            bpm_toleranz=bpm_toleranz,
            energy_direction=energy_direction,
            transition_type_override=rendered_transition_type,
        )
    finally:
        transition_renderer._synchronize_and_verify_kicks = original
    return out_dir / f"{pair_id}_k{n}.wav", [None if x is None else float(x) for x in captured]


def _validate_lags(clip_id: str, lags: list) -> list[float]:
    if len(lags) != 3:
        raise AuditError(f"{clip_id}: Kick-Diagnose muss exakt drei Regionen liefern")
    result = []
    for value in lags:
        if value is None:
            raise AuditError(f"{clip_id}: Kick-Lag ist nicht messbar")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise AuditError(f"{clip_id}: Kick-Lag ist ungueltig") from exc
        if not math.isfinite(number):
            raise AuditError(f"{clip_id}: Kick-Lag ist nicht endlich")
        if abs(number) > transition_renderer.KICK_SYNC_MAX_ERROR_SECONDS:
            raise AuditError(f"{clip_id}: Kick-Lag ueberschreitet die Renderer-Toleranz")
        result.append(number)
    return result


def audit_set(
    set_dir: Path,
    cache: Path,
    *,
    render: Callable = _render_with_diagnostics,
) -> dict:
    before_set = _fingerprint_tree(set_dir)
    before_set_digest = _fingerprint_kandidatensatz(set_dir)
    _reject_pending_wal(cache)
    before_cache = _fingerprint_cache_family(cache)
    merkmale, by_id, _, manifest = _parse_set(set_dir, cache)
    tracks = _load_tracks_immutable(cache)
    track_map = {_track_key(track.filePath): track for track in tracks}
    if len(track_map) != len(tracks):
        raise AuditError("Cache enthaelt doppelte Track-Pfade")

    results = []
    with tempfile.TemporaryDirectory(prefix="hpg-candidate-audit-") as tmp:
        temp_dir = Path(tmp)
        for pair in manifest["pairs"]:
            pair_id = pair["pair_id"]
            try:
                a = track_map[_track_key(pair["track_a"])]
                b = track_map[_track_key(pair["track_b"])]
            except KeyError as exc:
                raise AuditError(f"{pair_id}: Track nicht exakt im Cache gefunden") from exc
            if _track_key(a.filePath) != _track_key(pair["track_a"]) or _track_key(b.filePath) != _track_key(pair["track_b"]):
                raise AuditError(f"{pair_id}: Track-Pfad stimmt nicht exakt")
            if not Path(a.filePath).is_file() or not Path(b.filePath).is_file():
                raise AuditError(f"{pair_id}: Track-Audiodatei fehlt")
            required_genre = manifest["render_args"]["nur_genre"]
            if required_genre is not None and (
                loese_genre_auf(a) != required_genre
                or loese_genre_auf(b) != required_genre
            ):
                raise AuditError(
                    f"{pair_id}: Tracks verletzen render_args.nur_genre"
                )
            ranked = _rank_pair_from_manifest(a, b, manifest)
            if not ranked:
                raise AuditError(f"{pair_id}: kein gueltiger PairCandidate im Replay")
            producer_metrics = transition_metrics_from_candidate(ranked[0])
            if producer_metrics.harmonic_score < MIN_HARMONIC_SCORE:
                raise AuditError(f"{pair_id}: Producer-Harmonie-Gate verletzt")
            if float(producer_metrics.overall_score) < MIN_OVERALL_SCORE:
                raise AuditError(f"{pair_id}: Producer-Gesamtscore-Gate verletzt")
            groove = ranked[0].teilwerte.get("groove")
            if groove is None or float(groove) < MIN_GROOVE:
                raise AuditError(f"{pair_id}: Producer-Groove-Gate verletzt")
            expected_count = min(
                len(ranked), manifest["render_args"]["max_versionen_pro_paar"]
            )
            if len(pair["clips"]) != expected_count:
                raise AuditError(f"{pair_id}: Manifest enthaelt nicht exakt die Top-N-Kandidaten")
            for n, (clip, pc) in enumerate(zip(pair["clips"], ranked), 1):
                cid = clip["clip_id"]
                row = by_id[cid]
                _validate_candidate_row(row, a, b, pc)
                rank_args = manifest["scoring_snapshot"]["rank_args"]
                direction = rank_args["energy_direction"]
                mode = manifest["render_args"]["transition_type_mode"]
                expected_transition_type = _transition_type_fuer(
                    a,
                    b,
                    pc,
                    modus=mode,
                    bpm_toleranz=float(rank_args["bpm_tolerance"]),
                    energy_direction=None if direction == "auto" else direction,
                )
                if clip["rendered_transition_type"] != expected_transition_type:
                    raise AuditError(
                        f"{cid}: Transition-Type entspricht nicht der App-Entscheidung"
                    )
                fresh, lags = render(
                    a, b, pc, pair_id, n, temp_dir,
                    rendered_transition_type=clip["rendered_transition_type"],
                    transition_type_mode=mode,
                    bpm_toleranz=float(rank_args["bpm_tolerance"]),
                    energy_direction=None if direction == "auto" else direction,
                )
                lags = _validate_lags(cid, lags)
                wav = _compare_wav(set_dir / row["clip"], fresh, cid)
                results.append({"clip_id": cid, "wav": wav, "kick_lag_seconds": lags})

    if before_set != _fingerprint_tree(set_dir):
        raise AuditError("Kandidatensatz wurde waehrend des Audits veraendert")
    _reject_pending_wal(cache)
    if before_cache != _fingerprint_cache_family(cache):
        raise AuditError("Cache oder Begleitdatei wurde waehrend des Audits veraendert")
    return {
        "format_version": 1,
        "status": "passed",
        "ok": True,
        "set": {
            "path": str(set_dir),
            "manifest_sha256": hashlib.sha256(
                (set_dir / KANDIDATEN_MANIFEST_NAME).read_bytes()
            ).hexdigest(),
            **before_set_digest,
        },
        "cache": dict(manifest["cache"]),
        "algorithm_build": dict(manifest["algorithm_build"]),
        "pairs": manifest["render_args"]["anzahl"],
        "clips": len(results),
        "candidates": results,
    }


def _atomic_report(path: Path, payload: dict) -> None:
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # Hard-Link-Publikation ist atomar und scheitert, falls ein Ziel
        # zwischen validate_paths und diesem Punkt entstanden ist.
        os.link(name, path)
        os.unlink(name)
    except Exception:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set-dir", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        set_dir, cache, report = validate_paths(args.set_dir, args.cache, args.report)
        payload = audit_set(set_dir, cache)
    except Exception as exc:  # CLI muss jeden Auditfehler kontrolliert melden
        payload = {"ok": False, "error": str(exc), "error_type": type(exc).__name__}
        try:
            if "report" in locals():
                _atomic_report(report, payload)
        except Exception as report_exc:
            print(f"Audit fehlgeschlagen; Report konnte nicht geschrieben werden: {report_exc}", file=sys.stderr)
        print(f"Audit fehlgeschlagen: {exc}", file=sys.stderr)
        return 1
    try:
        _atomic_report(report, payload)
    except Exception as exc:
        print(f"Audit bestanden; Report konnte nicht geschrieben werden: {exc}", file=sys.stderr)
        return 1
    print(f"Audit bestanden: {payload['pairs']} Paare, {payload['clips']} Clips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

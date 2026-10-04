"""Gebundene Audit-/Fit-Vorschlaege ohne ungefragte aktive Uebernahme."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import tempfile
from pathlib import Path


def _encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def snapshot(directory, cache, *, seed, genres):
    """Bindet auch veraenderliche Ratings und Originalquellen, nicht nur Metadaten."""
    from .hearing_sources import SOURCE_MANIFEST_NAME, _fingerprint, load_source_session
    from tools import rate_transitions as rate
    from tools import audit_candidate_set as audit

    root = Path(directory).resolve(strict=True)
    has_source_manifest = (root / SOURCE_MANIFEST_NAME).exists()
    if has_source_manifest:
        session = load_source_session(root)
        mode = session.mode
        sources = session.sources
    else:
        from tools.hoertest_server import BEWERTUNG_SPALTEN, bewertungsschema
        from .hearing_ratings import load_session
        if bewertungsschema(root / "bewertung.csv") == BEWERTUNG_SPALTEN:
            # Der bestehende Einzel-Fit braucht nur CSV, keine Wiedergabequellen.
            mode, sources = "einzel", {}
        else:
            loaded = load_session(root)
            mode = "kandidaten" if loaded["mode"] in {"kandidaten", "dreinoten"} else loaded["mode"]
            rows = rate.lies_csv(root / "merkmale.csv")
            paths = sorted({str(Path(row[key]).resolve(strict=True)) for row in rows for key in ("track_a", "track_b")})
            sources = {path: {"path": path, "root": str(Path(path).parent), **_fingerprint(Path(path))} for path in paths}
    if mode not in {"einzel", "kandidaten"}:
        raise ValueError("Dramaturgie besitzt keinen bestehenden Fit oder Kandidaten-Replay-Audit")
    if cache is None:
        if mode != "einzel":
            raise ValueError("Kandidaten benoetigen einen Cache")
        cache_family = None
    else:
        cache = Path(cache).resolve(strict=True)
        if not cache.is_file():
            raise ValueError("Angegebener Cache ist keine Datei")
        audit._reject_pending_wal(cache)
        cache_family = audit._fingerprint_cache_family(cache)
    files = {}
    legacy_csv_single = mode == "einzel" and not has_source_manifest
    inventory = root.iterdir() if legacy_csv_single else root.rglob("*")
    for path in sorted(inventory):
        # Legacy-CSV-Fit betrachtet clips als opak, ohne Traversierung oder I/O.
        if legacy_csv_single and path.name == "clips":
            continue
        if path.is_symlink() or path.is_junction():
            raise ValueError("Satz enthaelt Link; kein gebundener Snapshot")
        if legacy_csv_single and (path.name not in {"merkmale.csv", "bewertung.csv", "gewichte.json"} or not path.is_file()):
            raise ValueError("Unbekannte Metadaten im Legacy-CSV-Einzel-Fit")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = _fingerprint(path)
    allowed_metadata = ({"merkmale.csv", "bewertung.csv"} if mode == "einzel"
                        else set(audit.SET_ROOT_NAMES) - {"clips"})
    if (root / SOURCE_MANIFEST_NAME).exists():
        allowed_metadata.add(SOURCE_MANIFEST_NAME)
    metadata = {name for name in files if Path(name).parts[0] != "clips"}
    if mode == "einzel":
        metadata.discard("gewichte.json")
    if metadata != allowed_metadata:
        raise ValueError("Satz enthaelt fehlende oder unbekannte Metadaten; keine Dateien kopiert")
    return {"set_path": str(root), "cache_path": str(cache) if cache is not None else None, "mode": mode,
            "files": files, "sources": sources,
            "cache": cache_family,
            "build": rate._algorithm_build_fingerprint(), "seed": seed, "genres": list(genres)}


def verify_binding(binding):
    current = snapshot(binding["set_path"], binding["cache_path"], seed=binding["seed"], genres=binding["genres"])
    if current != binding:
        raise ValueError("Satz, Bewertungen, Originalquellen, Cache oder Build wurden verändert; Vorschlag verworfen")


class _BoundedText(io.TextIOBase):
    def __init__(self):
        self.parts = []
        self.count = 0

    def write(self, text):
        remaining = max(0, 64000 - self.count)
        if remaining and text:
            self.parts.append(text[:remaining])
        self.count += min(len(text), remaining)
        return len(text)

    def getvalue(self):
        return "".join(self.parts)


def _materialize(binding, operation_root):
    """Kopiert nur Metadaten; Audio wird aus Originalquellen neu berechnet."""
    from .hearing_sources import SOURCE_MANIFEST_NAME, load_source_session
    from .transition_renderer import TransitionClipSpec, render_transition_clip
    from tools import rate_transitions as rate
    from tools import audit_candidate_set as audit

    original = Path(binding["set_path"])
    target = Path(operation_root) / "snapshot"
    target.mkdir()
    for name, expected in binding["files"].items():
        if name == SOURCE_MANIFEST_NAME or Path(name).parts[0] == "clips" or (binding["mode"] == "einzel" and name == "gewichte.json"):
            continue
        data = (original / name).read_bytes()
        if len(data) != expected["size"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise ValueError("Metadaten während Snapshot-Kopie verändert")
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_bytes(data)
    clips = target / "clips"
    clips.mkdir()
    if binding["mode"] == "kandidaten" and (original / SOURCE_MANIFEST_NAME).exists():
        source_session = load_source_session(original)
        for relative, spec in source_session.specs.items():
            render_transition_clip(TransitionClipSpec(**spec), target / relative)
    elif binding["mode"] == "kandidaten":
        manifest = audit._load_manifest(target / rate.KANDIDATEN_MANIFEST_NAME, Path(binding["cache_path"]))
        tracks = {_key(t.filePath): t for t in audit._load_tracks_immutable(Path(binding["cache_path"]))}
        rows = rate.lies_csv(target / "merkmale.csv")
        for row in rows:
            a, b = (tracks[_key(row[k])] for k in ("track_a", "track_b"))
            pc = audit._candidate_for(row, a, b, manifest)
            transition = next(c for p in manifest["pairs"] for c in p["clips"] if c["clip_id"] == row["clip_id"])
            fresh, _transition_type = rate.rendere_kandidat(
                a, b, pc, row["pair_id"], int(row["clip_id"].rsplit("_k", 1)[1]), clips,
                transition_type_override=transition["rendered_transition_type"],
                transition_type_mode=manifest["render_args"]["transition_type_mode"],
            )
            audit._compare_wav(original / row["clip"], target / fresh, row["clip_id"])
    # Einzel-Fit liest nur CSV; vorhandene Audioclips werden nicht kopiert.
    verify_binding(binding)
    return target


def _key(path):
    return os.path.normcase(os.path.abspath(path))


def compute_proposal(directory, cache, *, operation_root, operation_id, fit=True, seed=20260820, genres=()):
    """Nur im isolierten Child ausfuehren; Ergebnis ist nie produktiv aktiviert."""
    from tools import rate_transitions as rate
    from tools import audit_candidate_set as audit
    from . import candidate_preferences as cp
    from .hearing_sources import strict_json_bytes

    if type(seed) is not int or any(g not in rate.CANONICAL_GENRES for g in genres):
        raise ValueError("Ungueltiger Seed oder Genrefilter")
    operation_root = Path(operation_root).resolve(strict=True)
    preference_path = Path(os.environ.get("HPG_CANDIDATE_PREFERENCES_FILE", "")).resolve()
    if preference_path != operation_root / "child_preferences.json" or preference_path.exists():
        raise ValueError("Frische Child-Praeferenzisolation fehlt")
    cp.reset_cache()
    binding = snapshot(directory, cache, seed=seed, genres=genres)
    staged = _materialize(binding, operation_root)
    result = {"format": "hpg_calibration_proposal", "version": 1, "operation_id": operation_id,
              "binding": binding, "audit_passed": False, "audit": None, "fit_status": "not_requested",
              "gate_updates": {}, "diagnose": {}, "single_proposal": None, "live_applied": False, "output": ""}
    if binding["mode"] == "kandidaten":
        payload = audit.audit_set(staged, Path(cache))
        report = operation_root / "replay_audit.json"
        audit._atomic_report(report, payload)
        result.update(audit_passed=True, audit=payload)
    elif not fit:
        raise ValueError("Einzel besitzt keinen Kandidaten-Replay-Audit")
    if fit:
        text = _BoundedText()
        args = argparse.Namespace(dir=staged, cache=binding["cache_path"], audit_report=operation_root / "replay_audit.json",
                                  seed=seed, genre=list(genres) or None)
        with contextlib.redirect_stdout(text), contextlib.redirect_stderr(text):
            status = (rate.befehl_fit_kandidaten(args) if binding["mode"] == "kandidaten" else rate.befehl_fit(args))
        result.update(fit_status="passed" if status == 0 else "rejected", output=text.getvalue())
        if status == 0 and binding["mode"] == "kandidaten":
            if preference_path.is_file():
                data = strict_json_bytes(preference_path.read_bytes())
                updates = {key: value for key, value in data.items() if not key.startswith("_")}
                result["gate_updates"] = cp._normalisiere_updates(updates) if updates else {}
                result["diagnose"] = data.get("_diagnose", {}).get("fit_kandidaten", {})
            else:
                for name in ("candidate_preferences_entwurf.json", "dreinoten_fit_bericht.json"):
                    path = staged / name
                    if path.is_file():
                        result["diagnose"] = strict_json_bytes(path.read_bytes())
        elif status == 0 and binding["mode"] == "einzel":
            result["single_proposal"] = strict_json_bytes((staged / "gewichte.json").read_bytes())
    verify_binding(binding)
    result["proposal_sha256"] = _digest(result)
    if len(_encoded(result)) > 8 * 1024 * 1024:
        raise ValueError("Kalibrierungsergebnis ueberschreitet IPC-Limit")
    return result


def calibration_child(connection, directory, cache, operation_root, operation_id, fit, seed, genres):
    """Setzt ausschliesslich die Umgebung des eigenen Spawn-Kindprozesses."""
    root = Path(operation_root).resolve(strict=True)
    os.environ["TMP"] = os.environ["TEMP"] = str(root)
    os.environ["HPG_CANDIDATE_PREFERENCES_FILE"] = str(root / "child_preferences.json")
    tempfile.tempdir = str(root)
    try:
        result = compute_proposal(directory, cache, operation_root=root, operation_id=operation_id, fit=fit, seed=seed, genres=genres)
        connection.send((True, result))
    except Exception as exc:
        connection.send((False, f"{type(exc).__name__}: {exc}"[:64000]))
    finally:
        connection.close()


def validate_proposal(proposal, expected_operation_id=None):
    expected = {"format", "version", "operation_id", "binding", "audit_passed", "audit", "fit_status",
                "gate_updates", "diagnose", "single_proposal", "live_applied", "output", "proposal_sha256"}
    if type(proposal) is not dict or set(proposal) != expected or proposal["format"] != "hpg_calibration_proposal" or type(proposal["version"]) is not int or proposal["version"] != 1:
        raise ValueError("Unbekannter Kalibrierungsvorschlag")
    unsigned = {key: value for key, value in proposal.items() if key != "proposal_sha256"}
    if _digest(unsigned) != proposal["proposal_sha256"] or proposal["live_applied"] is not False:
        raise ValueError("Kalibrierungsvorschlag veraendert oder bereits aktiviert")
    from . import candidate_preferences as cp
    from .genres import CANONICAL_GENRES
    from .hearing_sources import _fingerprint_schema
    if (type(proposal["operation_id"]) is not str or not re.fullmatch(r"[0-9a-f]{32}", proposal["operation_id"])
            or expected_operation_id is not None and proposal["operation_id"] != expected_operation_id):
        raise ValueError("Operations-ID stimmt nicht")
    if (type(proposal["audit_passed"]) is not bool or type(proposal["fit_status"]) is not str or proposal["fit_status"] not in {"not_requested", "passed", "rejected"}
            or type(proposal["diagnose"]) is not dict or type(proposal["output"]) is not str or len(proposal["output"]) > 64000
            or type(proposal["gate_updates"]) is not dict):
        raise ValueError("Vorschlagszustand oder Typ ungueltig")
    binding = proposal["binding"]
    binding_keys = {"set_path", "cache_path", "mode", "files", "sources", "cache", "build", "seed", "genres"}
    if type(binding) is not dict or set(binding) != binding_keys:
        raise ValueError("Binding-Schema ungueltig")
    if (type(binding["mode"]) is not str or binding["mode"] not in {"einzel", "kandidaten"} or type(binding["seed"]) is not int
            or type(binding["genres"]) is not list or any(type(g) is not str or g not in CANONICAL_GENRES for g in binding["genres"])
            or len(binding["genres"]) != len(set(binding["genres"]))):
        raise ValueError("Binding-Modus/Parameter ungueltig")
    cache_absent = binding["cache_path"] is None and binding["cache"] is None
    if (binding["cache_path"] is None) != (binding["cache"] is None) or cache_absent and binding["mode"] != "einzel":
        raise ValueError("Cache darf nur beim Einzel-Fit gemeinsam fehlen")
    for key in (("set_path",) if cache_absent else ("set_path", "cache_path")):
        if type(binding[key]) is not str or not Path(binding[key]).is_absolute():
            raise ValueError("Binding-Pfad ungueltig")
    if type(binding["files"]) is not dict or not binding["files"] or type(binding["sources"]) is not dict:
        raise ValueError("Binding-Inventar fehlt")
    for name, value in binding["files"].items():
        if type(name) is not str or not Path(name).parts or Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Binding-Dateipfad ungueltig")
        _fingerprint_schema(value, name)
    if not binding["sources"]:
        from .hearing_sources import SOURCE_MANIFEST_NAME
        metadata = set(binding["files"])
        metadata.discard("gewichte.json")
        if binding["mode"] != "einzel" or SOURCE_MANIFEST_NAME in binding["files"] or metadata != {"merkmale.csv", "bewertung.csv"}:
            raise ValueError("Leere Quellen nur fuer den Legacy-CSV-Einzel-Fit")
    for name, value in binding["sources"].items():
        if (type(name) is not str or type(value) is not dict or set(value) != {"path", "root", "size", "sha256"}
                or value["path"] != name or type(value["root"]) is not str
                or not Path(name).is_absolute() or not Path(value["root"]).is_absolute()
                or Path(value["root"]) not in Path(name).parents):
            raise ValueError("Binding-Quellpfad ungueltig")
        _fingerprint_schema({k: value[k] for k in ("size", "sha256")}, name)
    cache = binding["cache"]
    if not cache_absent and (type(cache) is not dict or set(cache) != {"", "-wal", "-shm", "-journal", ".lock", "-lock", "stem.lock"}):
        raise ValueError("Cachefamilie ungueltig")
    for value in (() if cache_absent else cache.values()):
        if value is not None:
            if type(value) not in (tuple, list) or len(value) != 2:
                raise ValueError("Cachefingerprint ungueltig")
            _fingerprint_schema({"size": value[0], "sha256": value[1]}, "Cache")
    build = binding["build"]
    if type(build) is not dict or set(build) != {"scheme", "files", "sha256"} or build["scheme"] != "sha256-path-bytes-v1" or type(build["files"]) is not int or build["files"] <= 0:
        raise ValueError("Buildfingerprint ungueltig")
    _fingerprint_schema({"size": build["files"], "sha256": build["sha256"]}, "Build")
    if binding["mode"] == "kandidaten" and not proposal["audit_passed"]:
        raise ValueError("Kandidatenvorschlag benoetigt bestandenen Replay-Audit")
    if binding["mode"] == "einzel" and (proposal["fit_status"] == "not_requested"
            or proposal["fit_status"] == "passed" and type(proposal["single_proposal"]) is not dict):
        raise ValueError("Einzelvorschlag benoetigt angeforderten Fit und bei Erfolg einen Vorschlag")
    if proposal["gate_updates"]:
        cp._normalisiere_updates(proposal["gate_updates"])
        if binding["mode"] != "kandidaten" or proposal["fit_status"] != "passed" or not proposal["audit_passed"]:
            raise ValueError("Gate-Updates ohne bestandenen Kandidaten-Fit")
    if proposal["audit_passed"]:
        audit = proposal["audit"]
        if type(audit) is not dict or audit.get("ok") is not True or audit.get("status") != "passed" or audit.get("algorithm_build") != build or binding["mode"] != "kandidaten":
            raise ValueError("Audit-Zustand ungueltig")
    elif proposal["audit"] is not None:
        raise ValueError("Auditbericht ohne bestandenen Audit")
    if proposal["single_proposal"] is not None and (type(proposal["single_proposal"]) is not dict or binding["mode"] != "einzel" or proposal["fit_status"] != "passed"):
        raise ValueError("Einzelvorschlag ungueltig")
    return unsigned


def export_proposal(proposal, target):
    """Nur neuer JSON-Bericht ausserhalb aller Original- und Systempfade."""
    validate_proposal(proposal)
    from . import candidate_preferences, candidate_choices, tolerances
    target = Path(target)
    if target.is_symlink() or target.exists() or target.suffix.lower() != ".json":
        raise ValueError("Bericht muss eine neue JSON-Datei sein; vorhandene Dateien bleiben unveraendert")
    target = target.parent.resolve(strict=True) / target.name
    roots = [Path(proposal["binding"]["set_path"]), *[Path(v["root"]) for v in proposal["binding"]["sources"].values()]]
    if any(target == root or root in target.parents for root in roots):
        raise ValueError("Bericht darf nicht im Satz oder in Original-Musikordnern liegen")
    protected = {candidate_preferences.override_path().resolve(), tolerances._override_pfad().resolve(),
                 candidate_choices._pfad().resolve()}
    if proposal["binding"]["cache_path"] is not None:
        protected.add(Path(proposal["binding"]["cache_path"]))
    if any(str(target).startswith(str(path)) for path in protected):
        raise ValueError("Geschuetzte Praeferenz-/Cache-Datei ist kein Berichtsziel")
    fd, temporary = tempfile.mkstemp(prefix=".hpg-report-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_encoded(proposal) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, target)
    finally:
        os.unlink(temporary)
    return target


def apply_proposal(proposal, cancel=None):
    """Nur nach expliziter Bestaetigung des exakt angezeigten Vorschlags."""
    from . import candidate_preferences as cp
    from .hearing_sources import strict_json_bytes

    validate_proposal(proposal)
    if cancel is not None:
        cancel.checkpoint()
    if proposal["binding"]["mode"] != "kandidaten" or proposal["fit_status"] != "passed" or not proposal["audit_passed"] or not proposal["gate_updates"]:
        raise ValueError("Kein gatebestandener Kandidatenvorschlag zur Uebernahme")
    updates = cp._normalisiere_updates(proposal["gate_updates"])
    verify_binding(proposal["binding"])
    if cancel is not None and not cancel.begin_publish():
        raise InterruptedError("Uebernahme vor Publikation abgebrochen")
    path = cp.override_path()
    error = ""
    try:
        cp.merge_user_preferences_atomically(updates, diagnose=proposal["diagnose"])
    except Exception as exc:
        error = str(exc)
    finally:
        if cancel is not None:
            cancel.mark_complete()
    persisted = False
    try:
        actual = strict_json_bytes(path.read_bytes())
        persisted = all(all(actual.get(genre, {}).get(key) == value for key, value in block.items()) for genre, block in updates.items())
    except (OSError, ValueError, TypeError):
        pass
    return {"persisted": persisted, "effective_reload": persisted and not error, "error": error, "path": str(path)}

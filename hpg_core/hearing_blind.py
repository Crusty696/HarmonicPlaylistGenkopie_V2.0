"""LOCAL UI BLIND v1: Referenzen, keine Audiokopien und keine Renderings.

Neutral sind nur die UI-IDs. Playback-Metadaten enthalten Originalpfade und
koennen das System verraten; dieser Satz ist weder metadatenblind noch portabel.
Schluessel und Session haben getrennte Publikationsgrenzen, keine gemeinsame
Atomizitaet ueber Laufwerke. Ein Prozessabsturz nach der Schluesselpublikation
kann einen verwaisten privaten Schluessel hinterlassen.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import random
import shutil
import tempfile
import uuid
from pathlib import Path

import soundfile as sf

from .hearing_sources import strict_json_bytes
from .hearing_workflow import CancellationToken, HearingCancelledError

PUBLIC_NAME = "blind_session.json"
FORMAT = "hpg_local_ui_blind_refs"
VERSION = 1
_NOTICE = "LOCAL UI BLIND: Originalpfade sind sichtbar; nicht metadatenblind oder portabel."
_PUBLIC_KEYS = {"format", "format_version", "scope", "metadata_blinded", "notice",
                "session_id", "manifest", "source_root", "pairs"}
_PRIVATE_KEYS = {"format", "format_version", "session_id", "public_sha256", "manifest", "pairs"}


class OrphanBlindKeyError(OSError):
    """Rollback verlor Pfadbesitz; fremde Dateien werden nicht geloescht."""
    def __init__(self, key_path: Path):
        self.orphan_key_path = key_path
        super().__init__(f"orphan key: Besitz von {key_path} verloren; fremde Datei bleibt unangetastet")


def _exact(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(f"{label}: kein exaktes Schema")


def _signature(stat):
    return (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, stat.st_dev)


def _handle_signature(stat):
    # Windows: fstat.ctime und stat.ctime koennen unterschiedliche Zeitarten liefern.
    return (stat.st_size, stat.st_mtime_ns, stat.st_ino, stat.st_dev)


def _fingerprint(path: Path, checkpoint) -> dict:
    """Wie der Quell-Fingerprint, zusaetzlich Abbruchpruefung je 1-MiB-Block."""
    checkpoint()
    before = path.stat()
    if not path.is_file():
        raise ValueError(f"Quelle ist keine Datei: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        if _handle_signature(os.fstat(handle.fileno())) != _handle_signature(before):
            raise ValueError(f"Quelle vor Lesen veraendert: {path}")
        while True:
            checkpoint()
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after_handle = os.fstat(handle.fileno())
    after = path.stat()
    if (_signature(before) != _signature(after)
            or _handle_signature(before) != _handle_signature(after_handle)):
        raise ValueError(f"Quelle waehrend Lesen veraendert: {path}")
    checkpoint()
    return {"size": after.st_size, "sha256": digest.hexdigest(),
            "identity": list(_signature(after))}


def _bytes(path, checkpoint):
    chunks = []
    with path.open("rb") as handle:
        while True:
            checkpoint()
            chunk = handle.read(1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)


def _manifest_binding(raw):
    return {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _root(path):
    root = Path(path).resolve(strict=True)
    if not root.is_dir() or root == Path(root.anchor):
        raise ValueError("source_root muss ein konkreter Ordner sein")
    return root


def _source(path, root, checkpoint):
    try:
        path = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"Clip fehlt: {path}") from exc
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Clip ausserhalb des erlaubten Source-Roots oder fehlt: {path}")
    fingerprint = _fingerprint(path, checkpoint)
    checkpoint()
    info = sf.info(path)
    if _fingerprint(path, checkpoint) != fingerprint:
        raise ValueError(f"Quelle waehrend sf.info veraendert: {path}")
    return {"path": str(path), "root": str(root), **fingerprint,
            "samplerate": info.samplerate, "channels": info.channels,
            "frames": info.frames, "duration": info.duration}


def _validate_manifest(raw, manifest_parent, root, checkpoint):
    """Gleiche Pflichtfelder/Paargates wie prepare_dj_blind_test.prepare, ohne Kopierpfad."""
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    required = {"pair_id", "hpg_clip", "baseline_clip"}
    if not required.issubset(reader.fieldnames or ()) or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError(f"Manifest braucht eindeutige Spalten: {sorted(required)}")
    rows = list(reader)
    if not rows:
        raise ValueError("Manifest ist leer")
    validated, seen_ids, seen_pairs = [], set(), set()
    for row in rows:
        checkpoint()
        if None in row or any(type(row.get(k)) is not str for k in required):
            raise ValueError("Manifestzeile ist unvollstaendig")
        pair_id = row["pair_id"].strip()
        if not pair_id or pair_id in seen_ids:
            raise ValueError("Leere oder doppelte pair_id")
        seen_ids.add(pair_id)
        sources = []
        for field in ("hpg_clip", "baseline_clip"):
            if not row[field].strip():
                raise ValueError("Leerer Clip-Pfad")
            path = Path(row[field])
            sources.append(_source(path if path.is_absolute() else manifest_parent / path, root, checkpoint))
        a, b = sources
        if a["sha256"] == b["sha256"]:
            raise ValueError("A/B-Clips sind byte-identisch")
        signature = tuple(sorted((a["sha256"], b["sha256"])))
        if signature in seen_pairs:
            raise ValueError("Doppeltes Clip-Paar")
        seen_pairs.add(signature)
        if a["samplerate"] != b["samplerate"] or a["channels"] != b["channels"]:
            raise ValueError("Samplerate/Kanalzahl unterscheiden sich")
        if abs(a["duration"] - b["duration"]) > .01:
            raise ValueError("Clipdauer unterscheidet sich um mehr als 10 ms")
        validated.append((pair_id, sources))
    return validated


def _serialize(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def load_blind_references(public_path: Path, key_path: Path,
                          cancel: CancellationToken | None = None) -> dict:
    """Validiert eingefrorene Zuordnung/Quellen beim Resume; kein Manifest-Refresh."""
    token = cancel or CancellationToken()
    try:
        public_path, key_path = Path(public_path), Path(key_path)
        if key_path.resolve().is_relative_to(public_path.parent.resolve()):
            raise ValueError("Privater Schluessel liegt im Session-Ordner")
        public_raw = _bytes(Path(public_path), token.checkpoint)
        public = strict_json_bytes(public_raw)
        private = strict_json_bytes(_bytes(Path(key_path), token.checkpoint))
        _exact(public, _PUBLIC_KEYS, "Blindsatz")
        _exact(private, _PRIVATE_KEYS, "Privater Schluessel")
        if (public["format"] != FORMAT or type(public["format_version"]) is not int
                or public["format_version"] != VERSION or public["scope"] != "local_ui_blind"
                or public["metadata_blinded"] is not False or public["notice"] != _NOTICE
                or private["format"] != FORMAT + "_key" or type(private["format_version"]) is not int
                or private["format_version"] != VERSION):
            raise ValueError("Unbekannter Blind-Referenzvertrag")
        if (type(public["session_id"]) is not str or len(public["session_id"]) != 32
                or any(c not in "0123456789abcdef" for c in public["session_id"])
                or private["session_id"] != public["session_id"]
                or private["public_sha256"] != hashlib.sha256(public_raw).hexdigest()):
            raise ValueError("Session-/Public-Bindung stimmt nicht")
        bound = private["manifest"]
        _exact(bound, {"path", "size", "sha256", "bytes_base64"}, "Manifestbindung")
        if (type(bound["size"]) is not int or type(bound["sha256"]) is not str
                or type(bound["path"]) is not str or type(bound["bytes_base64"]) is not str):
            raise ValueError("Manifestbindung hat ungueltige Typen")
        raw = base64.b64decode(bound["bytes_base64"], validate=True)
        binding = _manifest_binding(raw)
        if (public["manifest"] != binding or {k: bound[k] for k in binding} != binding
                or not Path(bound["path"]).is_absolute()):
            raise ValueError("Eingefrorene Manifestbytes stimmen nicht")
        root = _root(public["source_root"])
        if str(root) != public["source_root"]:
            raise ValueError("Quellwurzel ist nicht kanonisch")
        validated = dict(_validate_manifest(raw, Path(bound["path"]).parent, root, token.checkpoint))
        pairs, keys = public["pairs"], private["pairs"]
        if type(pairs) is not list or type(keys) is not list or len(pairs) != len(keys) or len(keys) != len(validated):
            raise ValueError("Paarzuordnung ist unvollstaendig")
        seen, hpg_a = set(), 0
        for index, (pair, key) in enumerate(zip(pairs, keys), 1):
            _exact(pair, {"pair_id", "candidate_a", "candidate_b"}, "Paar")
            _exact(key, {"pair_id", "original_pair_id", "candidate_a_system", "candidate_b_system"}, "Paar-Schluessel")
            neutral = f"pair_{index:03d}"
            original = key["original_pair_id"]
            if (pair["pair_id"] != neutral or key["pair_id"] != neutral
                    or type(original) is not str or original not in validated or original in seen
                    or {key["candidate_a_system"], key["candidate_b_system"]} != {"HPG", "baseline"}):
                raise ValueError("Private Paarzuordnung stimmt nicht")
            seen.add(original)
            hpg_a += key["candidate_a_system"] == "HPG"
            for side in ("a", "b"):
                candidate = pair[f"candidate_{side}"]
                _exact(candidate, {"candidate_id", "source"}, "Kandidat")
                expected = validated[original][0 if key[f"candidate_{side}_system"] == "HPG" else 1]
                if candidate["candidate_id"] != f"{neutral}_{side.upper()}" or candidate["source"] != expected:
                    raise ValueError("Quelle veraendert oder Kandidatenreferenz stimmt nicht")
        if hpg_a != len(pairs) // 2:
            raise ValueError("A/B-Zuordnung ist nicht balanciert")
        token.checkpoint()
        return public
    except InterruptedError as exc:
        raise HearingCancelledError(str(exc)) from exc
    except (TypeError, KeyError) as exc:
        raise ValueError("Blindreferenz-Metadaten haben ungueltige Typen") from exc


def _owned(path, temporary, identity):
    try:
        current = path.lstat()
        return ((current.st_ino, current.st_dev) == identity
                and not path.is_symlink() and os.path.samefile(path, temporary))
    except FileNotFoundError:
        return False


def prepare_blind_references(manifest: Path, output_dir: Path, key_path: Path,
                             source_root: Path, seed=None,
                             cancel: CancellationToken | None = None) -> tuple[Path, Path]:
    """Publiziert privaten No-Clobber-Schluessel vor lokalem Referenzsatz."""
    from tools import rate_transitions as rate
    token = cancel or CancellationToken()
    staging = temporary = identity = None
    key_published = False
    manifest, output_dir, key_path = Path(manifest), Path(output_dir), Path(key_path)
    try:
        token.checkpoint()
        if output_dir.exists() or output_dir.is_symlink():
            raise FileExistsError(f"Ausgabeordner existiert bereits: {output_dir}")
        if key_path.exists() or key_path.is_symlink():
            raise FileExistsError(f"Schluesseldatei existiert bereits: {key_path}")
        output_dir, key_path = output_dir.resolve(), key_path.resolve()
        if key_path == output_dir or key_path.is_relative_to(output_dir):
            raise ValueError("Schluesseldatei muss ausserhalb des Session-Ordners liegen")
        manifest = manifest.resolve(strict=True)
        root = _root(source_root)
        manifest_before = _fingerprint(manifest, token.checkpoint)
        raw = _bytes(manifest, token.checkpoint)
        if _manifest_binding(raw) != {k: manifest_before[k] for k in ("size", "sha256")}:
            raise ValueError("Manifest waehrend Lesen veraendert")
        validated = _validate_manifest(raw, manifest.parent, root, token.checkpoint)
        rng = random.Random(seed) if seed is not None else random.SystemRandom()
        rng.shuffle(validated)
        sides = [True] * (len(validated) // 2) + [False] * (len(validated) - len(validated) // 2)
        rng.shuffle(sides)
        session_id = uuid.uuid4().hex
        public_pairs, key_pairs = [], []
        for index, ((original, sources), hpg_a) in enumerate(zip(validated, sides), 1):
            token.checkpoint()
            neutral = f"pair_{index:03d}"
            a, b = sources if hpg_a else reversed(sources)
            public_pairs.append({"pair_id": neutral,
                "candidate_a": {"candidate_id": neutral + "_A", "source": a},
                "candidate_b": {"candidate_id": neutral + "_B", "source": b}})
            key_pairs.append({"pair_id": neutral, "original_pair_id": original,
                "candidate_a_system": "HPG" if hpg_a else "baseline",
                "candidate_b_system": "baseline" if hpg_a else "HPG"})
        public = {"format": FORMAT, "format_version": VERSION, "scope": "local_ui_blind",
            "metadata_blinded": False, "notice": _NOTICE, "session_id": session_id,
            "manifest": _manifest_binding(raw), "source_root": str(root), "pairs": public_pairs}
        public_raw = _serialize(public)
        private = {"format": FORMAT + "_key", "format_version": VERSION, "session_id": session_id,
            "public_sha256": hashlib.sha256(public_raw).hexdigest(),
            "manifest": {"path": str(manifest), **_manifest_binding(raw),
                         "bytes_base64": base64.b64encode(raw).decode("ascii")}, "pairs": key_pairs}
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
        (staging / PUBLIC_NAME).write_bytes(public_raw)
        key_path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{key_path.name}.", suffix=".tmp", dir=key_path.parent)
        temporary = Path(name)
        with os.fdopen(fd, "wb") as handle:
            identity = (os.fstat(handle.fileno()).st_ino, os.fstat(handle.fileno()).st_dev)
            handle.write(_serialize(private))
            handle.flush()
            os.fsync(handle.fileno())
        # Resume-Validator liest Quellen und sf.info erneut gegen eingefrorene Bytes.
        load_blind_references(staging / PUBLIC_NAME, temporary, token)
        if (_fingerprint(manifest, token.checkpoint) != manifest_before
                or _bytes(manifest, token.checkpoint) != raw):
            raise ValueError("Manifest vor Publikation veraendert")
        token.checkpoint()
        if not token.begin_publish():
            raise InterruptedError("Abbruch vor Schluesselpublikation")
        os.link(temporary, key_path)
        key_published = True
        rate._publiziere_staging(staging, output_dir)
        token.mark_complete()
        return output_dir / PUBLIC_NAME, key_path
    except Exception as exc:
        if key_published:
            if _owned(key_path, temporary, identity):
                key_path.unlink()
            elif key_path.exists() or key_path.is_symlink():
                raise OrphanBlindKeyError(key_path) from exc
        if isinstance(exc, InterruptedError):
            raise HearingCancelledError(str(exc)) from exc
        raise
    finally:
        if temporary is not None and _owned(temporary, temporary, identity):
            temporary.unlink()
        if staging is not None and staging.exists():
            shutil.rmtree(staging)

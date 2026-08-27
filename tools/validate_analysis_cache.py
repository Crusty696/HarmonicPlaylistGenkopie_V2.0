"""Validiert einen fertigen HPG-Analysecache strikt und ohne Schreibzugriff."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hpg_core.caching import generate_cache_key, validate_track_dict
from tools.analyze_library import entdecke_audio


KANONISCHES_CACHE_SCHEMA = (
    ("key", "TEXT", 1),
    ("filepath", "TEXT", 0),
    ("version", "INTEGER", 0),
    ("data", "TEXT", 0),
)


class Validierungsfehler(RuntimeError):
    """Ein kontrolliert gemeldeter Vertrags- oder I/O-Fehler."""


def _positive_int(name: str):
    def parse(value: str) -> int:
        try:
            result = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{name} muss eine Ganzzahl sein") from exc
        if result < 1:
            raise argparse.ArgumentTypeError(f"{name} muss mindestens 1 sein")
        return result

    return parse


def _nonnegative_int(name: str):
    def parse(value: str) -> int:
        try:
            result = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{name} muss eine Ganzzahl sein") from exc
        if result < 0:
            raise argparse.ArgumentTypeError(f"{name} darf nicht negativ sein")
        return result

    return parse


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, help="Existierender Analysecache")
    parser.add_argument(
        "--expected-version",
        required=True,
        type=_positive_int("expected-version"),
        help=(
            "Erwartete DB_VERSION; Summary meldet DB_VERSION=<expected> und "
            "VALIDATOR_CONTRACT=CURRENT_CODE"
        ),
    )
    parser.add_argument("--root", required=True, help="Existierende Musik-Wurzel")
    parser.add_argument(
        "--expected-files", required=True, type=_positive_int("expected-files")
    )
    parser.add_argument(
        "--min-success", required=True, type=_nonnegative_int("min-success")
    )
    return parser


def _ist_link_oder_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction and isjunction(path))


def _innerhalb(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _cachefamilie(cache: Path) -> tuple[Path, ...]:
    kandidaten = (
        cache,
        Path(f"{cache}-wal"),
        Path(f"{cache}-shm"),
        Path(f"{cache}-journal"),
        cache.with_suffix(".lock"),
        Path(f"{cache}.lock"),
        Path(f"{cache}-lock"),
    )
    # Bei suffixlosen Namen koennen Varianten identisch sein.
    return tuple(dict.fromkeys(kandidaten))


def _sha256_stabil(path: Path, stat_vor: os.stat_result) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    stat_nach = path.stat()
    if (
        stat_vor.st_size != stat_nach.st_size
        or stat_vor.st_mtime_ns != stat_nach.st_mtime_ns
    ):
        raise Validierungsfehler(f"Datei waehrend Fingerprint veraendert: {path}")
    return digest.hexdigest()


def _familienfingerprint(cache: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in _cachefamilie(cache):
        name = str(path)
        if not os.path.lexists(path):
            result[name] = {"exists": False}
            continue
        if _ist_link_oder_junction(path) or not path.is_file():
            raise Validierungsfehler(
                f"Cachefamilien-Eintrag ist keine regulaere Nicht-Link-Datei: {path}"
            )
        stat = path.stat()
        result[name] = {
            "exists": True,
            "size": stat.st_size,
            "sha256": _sha256_stabil(path, stat),
            "mtime_ns": stat.st_mtime_ns,
        }
    return result


def _sqlite_uri(cache: Path) -> str:
    return f"{cache.as_uri()}?mode=ro&immutable=1"


def _json_strikt(text: Any) -> Any:
    if not isinstance(text, str):
        raise Validierungsfehler("Cache-Daten sind kein JSON-String")

    def reject_constant(value: str) -> None:
        raise ValueError(f"nichtendliche JSON-Konstante {value}")

    return json.loads(text, parse_constant=reject_constant)


def _schema_pruefen(conn: sqlite3.Connection) -> None:
    rows = list(conn.execute("PRAGMA table_info(cache)"))
    actual = tuple((str(row[1]), str(row[2]).upper(), int(row[5])) for row in rows)
    if actual != KANONISCHES_CACHE_SCHEMA:
        raise Validierungsfehler("Cache-Schema ist nicht exakt kanonisch")


def _pfade_pruefen(args: argparse.Namespace) -> tuple[Path, Path]:
    cache_roh = Path(args.cache).expanduser()
    root_roh = Path(args.root).expanduser()
    try:
        cache = cache_roh.resolve(strict=True)
        root = root_roh.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise Validierungsfehler(f"Cache oder Musik-Wurzel existiert nicht: {exc}") from exc
    if _ist_link_oder_junction(cache_roh) or not cache.is_file():
        raise Validierungsfehler("Cache ist keine regulaere Nicht-Link-Datei")
    if not root.is_dir():
        raise Validierungsfehler("Musik-Wurzel ist kein Verzeichnis")
    return cache, root


def _snapshot_transaktion_verweigern(
    cache: Path, fingerprint: dict[str, dict[str, Any]]
) -> None:
    """Verweigert jede durch einen Familien-Snapshot belegte offene Transaktion."""
    for path in (Path(f"{cache}-wal"), Path(f"{cache}-journal")):
        state = fingerprint[str(path)]
        if state["exists"] and int(state["size"]) > 0:
            raise Validierungsfehler(
                f"Nichtleere Transaktionsdatei verhindert immutable Pruefung: {path}"
            )


def _cache_pruefen(
    cache: Path,
    root: Path,
    discovered: list[str],
    expected_version: int,
) -> tuple[set[str], int]:
    discovered_norm = {
        os.path.normcase(os.path.realpath(path)): path for path in discovered
    }
    valide_pfade: set[str] = set()
    keys: set[str] = set()
    marker_count = 0

    # Zweiter Familien-Snapshot unmittelbar vor dem Open: Entsteht zwischen
    # Discovery und hier eine WAL/ein Journal, darf immutable=1 nie oeffnen.
    fingerprint_vor_open = _familienfingerprint(cache)
    _snapshot_transaktion_verweigern(cache, fingerprint_vor_open)
    conn = sqlite3.connect(_sqlite_uri(cache), uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        _schema_pruefen(conn)
        rows = conn.execute("SELECT key, filepath, version, data FROM cache").fetchall()
        for key, filepath, version, data in rows:
            if key == "version":
                marker_count += 1
                if (filepath, version, data) != ("system", expected_version, "metadata"):
                    raise Validierungsfehler("Versionsmarker ist nicht exakt kanonisch")
                continue
            if not isinstance(key, str) or not key:
                raise Validierungsfehler("Track-Schluessel ist leer oder ungueltig")
            if key in keys:
                raise Validierungsfehler(f"Track-Schluessel ist doppelt: {key}")
            keys.add(key)
            if version != expected_version:
                raise Validierungsfehler(f"Track-Zeile hat falsche Version: {key}")
            try:
                validated = validate_track_dict(_json_strikt(data))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise Validierungsfehler(f"Track-JSON ist ungueltig ({key}): {exc}") from exc
            json_path = validated["filePath"]
            if not isinstance(filepath, str) or filepath != json_path:
                raise Validierungsfehler(f"filepath stimmt nicht exakt mit JSON ueberein: {key}")

            track_roh = Path(filepath).expanduser()
            if _ist_link_oder_junction(track_roh):
                raise Validierungsfehler(f"Trackpfad ist ein Link oder Junction: {filepath}")
            try:
                track = track_roh.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise Validierungsfehler(f"Trackpfad existiert nicht ({filepath}): {exc}") from exc
            if not track.is_file() or not _innerhalb(track, root):
                raise Validierungsfehler(f"Trackpfad liegt ausserhalb der Wurzel: {filepath}")
            normalized = os.path.normcase(os.path.realpath(filepath))
            if normalized in valide_pfade:
                raise Validierungsfehler(f"Trackpfad ist normalisiert doppelt: {filepath}")
            if normalized not in discovered_norm:
                raise Validierungsfehler(f"Cachepfad wurde nicht als Audio entdeckt: {filepath}")
            expected_key = generate_cache_key(filepath, validated["rekordbox_signature"])
            if not expected_key or expected_key != key:
                raise Validierungsfehler(f"Cache-Schluessel passt nicht zum aktuellen Track: {filepath}")
            valide_pfade.add(normalized)
    finally:
        conn.close()

    if marker_count != 1:
        raise Validierungsfehler(
            f"Cache braucht genau einen kanonischen Versionsmarker, gefunden: {marker_count}"
        )
    return valide_pfade, len(keys)


def _summary(
    *, status: str, version: int, valid: int, expected: int, missing: int,
    db_size: int, db_sha256: str,
) -> str:
    return (
        f"STATUS={status} DB_VERSION={version} "
        "VALIDATOR_CONTRACT=CURRENT_CODE "
        f"TRACKS_VALID={valid} "
        f"TRACKS_EXPECTED={expected} TRACKS_MISSING={missing} "
        f"DB_SIZE={db_size} DB_SHA256={db_sha256}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.min_success > args.expected_files:
        parser.error("min-success darf expected-files nicht uebersteigen")

    valid = 0
    missing_paths: list[str] = []
    db_size = -1
    db_sha256 = "-"
    errors: list[str] = []

    try:
        cache, root = _pfade_pruefen(args)
        fingerprint_vor = _familienfingerprint(cache)
        _snapshot_transaktion_verweigern(cache, fingerprint_vor)
        db_before = fingerprint_vor[str(cache)]
        db_size = int(db_before["size"])
        db_sha256 = str(db_before["sha256"])

        discovered, discovery_errors = entdecke_audio(root)
        if discovery_errors:
            raise Validierungsfehler(
                "Audio-Discovery meldet Fehler: " + " | ".join(discovery_errors)
            )
        if len(discovered) != args.expected_files:
            raise Validierungsfehler(
                f"Audio-Discovery: {len(discovered)} statt {args.expected_files} Dateien"
            )

        valide_pfade, row_count = _cache_pruefen(
            cache, root, discovered, args.expected_version
        )
        valid = len(valide_pfade)
        if row_count != valid:
            raise Validierungsfehler("Nicht jede Track-Zeile ist eindeutig gueltig")
        if valid > args.expected_files:
            raise Validierungsfehler("Cache enthaelt mehr Tracks als erwartet")
        discovered_by_norm = {
            os.path.normcase(os.path.realpath(path)): path for path in discovered
        }
        missing_paths = sorted(
            discovered_by_norm[path]
            for path in discovered_by_norm.keys() - valide_pfade
        )
        if valid < args.min_success:
            raise Validierungsfehler(
                f"Nur {valid} gueltige Tracks; mindestens {args.min_success} verlangt"
            )
    except Exception as exc:
        # CLI-Vertrag: Daten-, SQLite- und Race-Fehler kontrolliert ohne Traceback.
        errors.append(str(exc))

    # Kein positives oder negatives Endergebnis vor dem zweiten Fingerprint.
    try:
        if "cache" in locals():
            fingerprint_nach = _familienfingerprint(cache)
            if "fingerprint_vor" in locals() and fingerprint_nach != fingerprint_vor:
                errors.append("Cachefamilie wurde waehrend der Validierung veraendert")
    except Exception as exc:
        errors.append(str(exc))

    for error in errors:
        print(f"FEHLER: {error}", file=sys.stderr)
    for path in missing_paths:
        print(f"FEHLENDER_TRACK: {path}")
    status = "OK" if not errors else "FEHLER"
    print(
        _summary(
            status=status,
            version=args.expected_version,
            valid=valid,
            expected=args.expected_files,
            missing=len(missing_paths),
            db_size=db_size,
            db_sha256=db_sha256,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

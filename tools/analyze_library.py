"""Analysiert eine vollstaendige Audio-Library wiederaufnehmbar in einen isolierten Cache."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import sys
from datetime import datetime
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a"}


def _integer_in_range(name: str, minimum: int, maximum: int | None = None):
    def parse(value: str) -> int:
        try:
            result = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{name} muss eine Ganzzahl sein") from exc
        if result < minimum or (maximum is not None and result > maximum):
            grenze = f"{minimum}..{maximum}" if maximum is not None else f">= {minimum}"
            raise argparse.ArgumentTypeError(f"{name} muss im Bereich {grenze} liegen")
        return result

    return parse


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Exakte Musik-Wurzel")
    parser.add_argument("--cache", required=True, help="Isolierter HPG-Cache")
    parser.add_argument("--expected-files", required=True, type=_integer_in_range("expected-files", 1))
    parser.add_argument("--min-success", required=True, type=_integer_in_range("min-success", 0))
    parser.add_argument("--workers", type=_integer_in_range("workers", 1, 4), default=4)
    parser.add_argument(
        "--task-timeout",
        type=_integer_in_range("task-timeout", 60, 900),
        default=60,
        help="Timeout je Track in Sekunden (nur fuer diesen CLI-Prozess)",
    )
    parser.add_argument("--progress-log", help="Append-only Fortschrittslog ausserhalb der Musik-Wurzel")
    return parser


def _innerhalb(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _ist_link_oder_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction and isjunction(path))


def entdecke_audio(root: Path) -> tuple[list[str], list[str]]:
    """Liefert deterministische echte Dateien sowie Scandir-/Pfadfehler."""
    gefunden: list[str] = []
    fehler: list[str] = []

    def onerror(exc: OSError) -> None:
        fehler.append(str(exc))

    for aktueller_ordner, dirs, files in os.walk(
        root, topdown=True, followlinks=False, onerror=onerror
    ):
        dirs.sort()
        files.sort()
        basis = Path(aktueller_ordner)
        erlaubte_dirs = []
        for name in dirs:
            kandidat = basis / name
            try:
                if _ist_link_oder_junction(kandidat):
                    continue
                aufgeloest = kandidat.resolve(strict=True)
                if aufgeloest.is_dir() and _innerhalb(aufgeloest, root):
                    erlaubte_dirs.append(name)
            except (OSError, RuntimeError) as exc:
                fehler.append(f"{kandidat}: {exc}")
        dirs[:] = erlaubte_dirs

        for name in files:
            kandidat = basis / name
            if kandidat.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            try:
                if _ist_link_oder_junction(kandidat):
                    continue
                aufgeloest = kandidat.resolve(strict=True)
                if aufgeloest.is_file() and _innerhalb(aufgeloest, root):
                    gefunden.append(str(aufgeloest))
            except (OSError, RuntimeError) as exc:
                fehler.append(f"{kandidat}: {exc}")

    return gefunden, fehler


def _pfade_pruefen(args) -> tuple[Path, Path, Path] | None:
    try:
        root = Path(args.root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        print(f"FEHLER: Musik-Wurzel ungueltig: {exc}", file=sys.stderr)
        return None
    if not root.is_dir():
        print("FEHLER: Musik-Wurzel ist kein Verzeichnis", file=sys.stderr)
        return None

    try:
        cache = Path(args.cache).resolve(strict=False)
        progress = (
            Path(args.progress_log).resolve(strict=False)
            if args.progress_log
            else cache.with_suffix(cache.suffix + ".progress.log")
        )
    except (OSError, RuntimeError) as exc:
        print(f"FEHLER: Cache-/Progresslog-Pfad ungueltig: {exc}", file=sys.stderr)
        return None
    if cache.exists() and cache.is_dir():
        print("FEHLER: Cache-Pfad ist ein Verzeichnis", file=sys.stderr)
        return None
    if progress.exists() and progress.is_dir():
        print("FEHLER: Progresslog-Pfad ist ein Verzeichnis", file=sys.stderr)
        return None
    if _innerhalb(cache, root) or _innerhalb(progress, root):
        print("FEHLER: Cache und Progresslog muessen ausserhalb der Musik-Wurzel liegen", file=sys.stderr)
        return None
    if cache == progress:
        print("FEHLER: Cache und Progresslog duerfen nicht identisch sein", file=sys.stderr)
        return None
    return root, cache, progress


def _produktcache_pfad(version: int) -> Path:
    configured_dir = os.environ.get("HPG_CACHE_DIR", "").strip()
    if configured_dir:
        basis = Path(configured_dir).expanduser().resolve()
    else:
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        basis = (
            Path(local_app_data).expanduser().resolve() / "HPG"
            if local_app_data else (Path.home() / ".hpg").resolve()
        )
    return (basis / f"hpg_cache_v{version}.db").resolve()


def _sqlite_ro_uri(path: Path) -> str:
    """Erzeugt eine URI-sichere read-only SQLite-Adresse fuer absolute Pfade."""
    return f"{path.resolve().as_uri()}?mode=ro"


def _pruefe_bestehenden_cache(cache: Path, version: int) -> str | None:
    """Akzeptiert zum Fortsetzen nur einen echten Cache derselben Version."""
    if not cache.exists():
        return None
    try:
        conn = sqlite3.connect(_sqlite_ro_uri(cache), uri=True)
        try:
            spalten = [
                str(row[1]) for row in conn.execute("PRAGMA table_info(cache)")
            ]
            if spalten != ["key", "filepath", "version", "data"]:
                return "Cache-Schema ist nicht exakt kanonisch"
            marker = conn.execute(
                "SELECT filepath, version, data FROM cache "
                "WHERE key = 'version' LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return f"keine gueltige SQLite-Cachedatei ({exc})"
    if marker is None:
        return "Cache-Versionsmarker fehlt"
    if marker != ("system", version, "metadata"):
        return "Cache-Versionsmarker ist nicht exakt kanonisch"
    return None


def _persistierte_track_pfade(
    cache: Path,
    tracks: list,
    input_pfade: list[str],
    version: int,
    cache_key_builder: Callable,
    track_validator: Callable,
) -> tuple[set[str], list[str]]:
    """Belegt Analyseerfolge durch exakte aktuelle Cache-Schluessel."""
    input_lookup = {os.path.normcase(os.path.realpath(path)) for path in input_pfade}
    erwartet: dict[tuple[str, str], str] = {}
    for track in tracks:
        file_path = getattr(track, "filePath", "")
        normalized = os.path.normcase(os.path.realpath(file_path)) if file_path else ""
        if normalized not in input_lookup:
            continue
        signature = getattr(track, "rekordbox_signature", "")
        cache_key = cache_key_builder(file_path, signature)
        if cache_key:
            erwartet[(cache_key, normalized)] = file_path

    conn = sqlite3.connect(_sqlite_ro_uri(cache), uri=True)
    try:
        marker = conn.execute(
            "SELECT filepath, version, data FROM cache "
            "WHERE key = 'version' LIMIT 1"
        ).fetchone()
        if marker != ("system", version, "metadata"):
            raise RuntimeError("Cache-Versionsmarker ist nicht exakt kanonisch")
        vorhanden = set()
        for key, filepath, data in conn.execute(
                "SELECT key, filepath, data FROM cache "
                "WHERE key <> 'version' AND version = ?",
                (version,),
            ):
            try:
                validated = track_validator(json.loads(data))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            normalized_row = os.path.normcase(os.path.realpath(str(filepath)))
            normalized_data = os.path.normcase(
                os.path.realpath(str(validated["filePath"]))
            )
            if normalized_row == normalized_data:
                vorhanden.add((str(key), normalized_row))
    finally:
        conn.close()

    persistiert = {
        normalized for key, normalized in erwartet if (key, normalized) in vorhanden
    }
    fehlend = sorted(
        file_path
        for (key, normalized), file_path in erwartet.items()
        if (key, normalized) not in vorhanden
    )
    return persistiert, fehlend


def main(argv: list[str] | None = None, analyzer_factory: Callable | None = None) -> int:
    args = _parser().parse_args(argv)
    fehlender_env_wert = object()
    geerbter_cache_roh = os.environ.get("HPG_CACHE_FILE", fehlender_env_wert)
    geerbter_cache = (
        geerbter_cache_roh.strip()
        if isinstance(geerbter_cache_roh, str)
        else ""
    )
    if args.min_success > args.expected_files:
        print("FEHLER: min-success darf expected-files nicht uebersteigen", file=sys.stderr)
        return 2

    pfade = _pfade_pruefen(args)
    if pfade is None:
        return 2
    root, cache, progress = pfade
    if geerbter_cache:
        try:
            if Path(geerbter_cache).expanduser().resolve() == cache:
                print(
                    "FEHLER: --cache entspricht dem geerbten HPG_CACHE_FILE; "
                    "ein konfigurierter Produktcache ist als Arbeitscache gesperrt",
                    file=sys.stderr,
                )
                return 2
        except (OSError, RuntimeError) as exc:
            print(f"FEHLER: Geerbter Cachepfad ungueltig: {exc}", file=sys.stderr)
            return 2
    audio_dateien, discovery_fehler = entdecke_audio(root)
    if discovery_fehler:
        print("FEHLER: Library-Discovery war nicht vollstaendig:", file=sys.stderr)
        for fehler in discovery_fehler:
            print(f"  - {fehler}", file=sys.stderr)
        return 2
    if len(audio_dateien) != args.expected_files:
        print(
            f"FEHLER: {len(audio_dateien)} Audiodateien gefunden, "
            f"aber {args.expected_files} erwartet",
            file=sys.stderr,
        )
        return 2

    def cache_umgebung_wiederherstellen() -> None:
        if geerbter_cache_roh is not fehlender_env_wert:
            os.environ["HPG_CACHE_FILE"] = geerbter_cache_roh
        else:
            os.environ.pop("HPG_CACHE_FILE", None)

    os.environ["HPG_CACHE_FILE"] = str(cache)
    try:
        from hpg_core import caching as hpg_caching

        if analyzer_factory is None and Path(hpg_caching.CACHE_FILE).resolve() != cache:
            print(
                "FEHLER: hpg_core.caching wurde bereits mit einem anderen Cachepfad geladen; "
                "analyze_library muss in einem frischen Prozess laufen",
                file=sys.stderr,
            )
            cache_umgebung_wiederherstellen()
            return 2
        if cache == _produktcache_pfad(hpg_caching.CACHE_VERSION):
            print(
                "FEHLER: Der produktive HPG-Benutzercache ist als Arbeitscache gesperrt",
                file=sys.stderr,
            )
            cache_umgebung_wiederherstellen()
            return 2
        cache_fehler = _pruefe_bestehenden_cache(cache, hpg_caching.CACHE_VERSION)
        if cache_fehler:
            print(
                f"FEHLER: Bestehender Arbeitscache ungueltig: {cache_fehler}",
                file=sys.stderr,
            )
            cache_umgebung_wiederherstellen()
            return 2
    except Exception as exc:  # noqa: BLE001 - kontrollierte CLI-Grenze
        print(f"FEHLER: Cache-Vorbereitung fehlgeschlagen: {exc}", file=sys.stderr)
        cache_umgebung_wiederherstellen()
        return 1

    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        progress.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"FEHLER: Arbeitsverzeichnis kann nicht angelegt werden: {exc}", file=sys.stderr)
        cache_umgebung_wiederherstellen()
        return 1
    try:
        log_handle = progress.open("a", encoding="utf-8", buffering=1)
    except OSError as exc:
        print(f"FEHLER: Progresslog kann nicht geoeffnet werden: {exc}", file=sys.stderr)
        cache_umgebung_wiederherstellen()
        return 1

    log_fehler = False
    log_fehler_gemeldet = False

    def fortschritt(current: int, total: int, status: str) -> None:
        nonlocal log_fehler, log_fehler_gemeldet
        if status.startswith("Analyzed (Safe Mode):"):
            status = status.replace(
                "Analyzed (Safe Mode):",
                "Analysiert (Safe Mode; Persistenz ungeprueft):",
                1,
            )
        elif status.startswith("Analyzed:"):
            status = status.replace(
                "Analyzed:", "Analysiert (Persistenz ungeprueft):", 1,
            )
        zeile = f"{datetime.now().isoformat(timespec='seconds')} {current}/{total} {status}"
        print(zeile, flush=True)
        try:
            log_handle.write(zeile + "\n")
            log_handle.flush()
        except OSError as exc:
            log_fehler = True
            if not log_fehler_gemeldet:
                print(f"FEHLER: Progresslog-Schreiben fehlgeschlagen: {exc}", file=sys.stderr)
                log_fehler_gemeldet = True

    hpg_config = None
    alter_timeout = None
    try:
        from hpg_core import config as hpg_config

        alter_timeout = hpg_config.PARALLEL_ANALYSIS_TIMEOUT
        hpg_config.PARALLEL_ANALYSIS_TIMEOUT = args.task_timeout
        if analyzer_factory is None:
            from hpg_core.parallel_analyzer import ParallelAnalyzer

            analyzer_factory = ParallelAnalyzer
        analyzer = analyzer_factory(max_workers=args.workers)
        tracks = analyzer.analyze_files(audio_dateien, progress_callback=fortschritt)
        try:
            persistierte_pfade, nicht_persistiert = _persistierte_track_pfade(
                cache,
                tracks,
                audio_dateien,
                hpg_caching.CACHE_VERSION,
                hpg_caching.generate_cache_key,
                hpg_caching.validate_track_dict,
            )
        except Exception as exc:
            fortschritt(
                len(audio_dateien),
                len(audio_dateien),
                f"[FAILED] Persistenznachweis: {exc}",
            )
            raise
        fortschritt(
            len(audio_dateien),
            len(audio_dateien),
            f"Persistiert: {len(persistierte_pfade)}/{len(tracks)} Analyseerfolge",
        )
        for file_path in nicht_persistiert:
            print(f"FEHLER: Analyse nicht im Cache persistiert: {file_path}", file=sys.stderr)
    except KeyboardInterrupt:
        print("ABGEBROCHEN: Analyse durch Benutzer beendet", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI-Grenze muss kontrolliert enden
        print(f"FEHLER: Library-Analyse fehlgeschlagen: {exc}", file=sys.stderr)
        return 1
    finally:
        if hpg_config is not None and alter_timeout is not None:
            hpg_config.PARALLEL_ANALYSIS_TIMEOUT = alter_timeout
        try:
            log_handle.close()
        except OSError as exc:
            log_fehler = True
            print(f"FEHLER: Progresslog-Abschluss fehlgeschlagen: {exc}", file=sys.stderr)
        cache_umgebung_wiederherstellen()

    erfolgreich = len(persistierte_pfade)
    print(
        f"ERGEBNIS: {erfolgreich}/{len(audio_dateien)} Tracks erfolgreich persistiert",
        flush=True,
    )
    if log_fehler:
        return 1
    return 0 if erfolgreich >= args.min_success else 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())

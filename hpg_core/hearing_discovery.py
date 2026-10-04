"""Explizite, flache Satzsuche; Fortschritt ist kein Integritaets-/Auditbeleg.

Quellreferenzen werden nur als Metadaten erkannt. Originaldateien, Cache und
Audio werden weder geoeffnet noch gehasht oder auf Verfuegbarkeit geprueft.
Eine vollstaendige SourceSession-Pruefung bleibt Aufgabe des Lade-Workers.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from tools import hoertest_launcher as launcher
from . import hearing_sources as sources


@dataclass(frozen=True)
class SetSummary:
    """``type`` ist der Launcher-Schemaname; Status beschreibt nur Bewertungen."""

    path: Path
    type: str
    rated: int
    total: int
    status: Literal["new", "in_progress", "complete", "empty", "error"]
    errors: tuple[str, ...] = ()


_MARKERS = ("bewertung.csv", sources.SOURCE_MANIFEST_NAME,
            "kandidaten_manifest.json", "dramaturgie_manifest.json", "merkmale.csv")
_METADATA = frozenset(_MARKERS) | {
    "dramaturgie_bewertung.csv", "reihenfolge.json", "LIESMICH-kandidaten.txt", "README.md",
}


def _linked(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _present(path: Path) -> bool:
    # Auch defekte Links sind sichtbare, fehlerhafte Metadaten.
    return _linked(path) or path.exists()


def _metadata_boundary(directory: Path) -> None:
    for name in _METADATA:
        path = directory / name
        if _linked(path):
            raise ValueError(f"Metadata link/junction rejected: {name}")
        if path.exists() and (not path.is_file() or path.resolve().parent != directory):
            raise ValueError(f"Metadata leaves set or is not a file: {name}")


def _source_metadata(directory: Path) -> dict:
    """Nur Schema-/Referenzpruefung; keine Inhalts-, Original- oder Auditpruefung."""
    manifest = sources.strict_json_bytes((directory / sources.SOURCE_MANIFEST_NAME).read_bytes())
    sources._exact(manifest, sources._MANIFEST_KEYS, "Source discovery manifest")
    mode = manifest["mode"]
    if (manifest["format"] != sources.SOURCE_FORMAT
            or type(manifest["format_version"]) is not int
            or manifest["format_version"] != sources.SOURCE_VERSION
            or manifest["status"] != "prepared"
            or type(mode) is not str or mode not in sources._MODE_FILES):
        raise ValueError("Unsupported source format/version/mode/status")
    roots = manifest["source_roots"]
    if (type(roots) is not list or not roots or any(type(r) is not str or not Path(r).is_absolute() for r in roots)
            or len(set(roots)) != len(roots)):
        raise ValueError("Invalid explicit source roots")
    specs, originals = manifest["specs"], manifest["sources"]
    if type(specs) is not dict or not specs or type(originals) is not dict or not originals:
        raise ValueError("Missing source specs/references")
    referenced = set()
    for ref, spec in specs.items():
        sources._virtual_path(ref)
        sources.validate_spec_v1(spec)
        referenced.update((spec["track_a_path"], spec["track_b_path"]))
    if referenced != set(originals):
        raise ValueError("Specs and sources differ")
    for key, original in originals.items():
        sources._exact(original, {"path", "size", "sha256", "root"}, "Source reference")
        sources._fingerprint_schema({k: original[k] for k in ("size", "sha256")}, "Source fingerprint")
        if (original["path"] != key or type(original["root"]) is not str or original["root"] not in roots
                or not sources._inside(Path(key), Path(original["root"]))
                or ".." in Path(key).parts):
            raise ValueError("Invalid source path/root reference")
    required = sources._MODE_FILES[mode]
    immutable = manifest["immutable_metadata"]
    sources._exact(immutable, required - sources._MUTABLE_FILES, "Immutable metadata inventory")
    for name, fingerprint in immutable.items():
        sources._fingerprint_schema(fingerprint, name)
    if any(not (directory / name).is_file() for name in required):
        raise ValueError("Source metadata files missing")
    if mode != "dramaturgie" and (directory / "dramaturgie_manifest.json").exists():
        raise ValueError("Source mode conflicts with dramaturgy manifest")
    return manifest


def _source_dramaturgy_progress(directory: Path, manifest: dict) -> tuple[int, int, str]:
    # Der alte Launcher fordert WAV-Hashes im Clipobjekt. Der getrennte
    # Source-Metadatenvertrag prueft stattdessen die explizite Representation.
    from tools import rate_transitions as rt
    sources._dramaturgy_metadata(directory, manifest["specs"], rt)
    rated = total = 0
    for name, columns in (
        ("bewertung.csv", ("track_note", "technik_note", "gesamt_note")),
        ("dramaturgie_bewertung.csv", launcher.DRAMATURGIE_SCHEMA[1:-1]),
    ):
        with (directory / name).open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                total += 1
                rated += all((row[key] or "").strip() for key in columns)
    return rated, total, "Dramaturgie"


def _summary(directory: Path) -> SetSummary:
    try:
        _metadata_boundary(directory)
        manifest = None
        if _present(directory / sources.SOURCE_MANIFEST_NAME):
            manifest = _source_metadata(directory)
        if manifest is not None and manifest["mode"] == "dramaturgie":
            rated, total, schema = _source_dramaturgy_progress(directory, manifest)
        else:
            rated, total, schema = launcher.lese_fortschritt(directory)
        if schema in {"fehler", "unbekannt"}:
            return SetSummary(directory, schema, rated, total, "error",
                              (f"Launcher progress returned {schema}; no detailed cause exposed.",))
        if manifest is not None:
            mode = manifest["mode"]
            if total == 0 or (mode == "einzel") != (schema == "Standard"):
                raise ValueError("Source mode/rating schema or empty source set mismatch")
            with (directory / "bewertung.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            refs = [r["clip"] if mode == "einzel" else f"clips/{r['clip_id']}.wav" for r in rows]
            # Dramaturgiepfade enthalten die Varianten-Unterordner und wurden oben gebunden.
            if mode != "dramaturgie" and (len(refs) != len(set(refs)) or set(refs) != set(manifest["specs"])):
                raise ValueError("Source rating references differ from specs")
        status = "empty" if total == 0 else "complete" if rated == total else "new" if rated == 0 else "in_progress"
        return SetSummary(directory, schema, rated, total, status)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        return SetSummary(directory, "fehler", 0, 0, "error", (f"{type(exc).__name__}: {exc}",))


def _sort_key(path: Path) -> tuple[int, str]:
    # Bestehende Launcher-Prioritaet, ohne dessen implizite Suchwurzeln.
    name = path.name.lower()
    priority = 0 if "techno-prog-melodic" in name else 1 if "psytrance-90-v3" in name else 2 if "psytrance" in name else 3
    return priority, name


def discover_sets(root: Path, cancelcheck: Callable[[], None] | None = None) -> tuple[SetSummary, ...]:
    """Nur ausgewaehlte Wurzel und direkte Kinder; keine automatische Laufwerkssuche.

    Ungueltige Wurzeln werfen ValueError/OSError. Fehlerhafte/unsichere Kinder
    bleiben als Fehlerzeilen sichtbar. ``cancelcheck()`` darf InterruptedError
    werfen; Abbruch liefert niemals einen partiellen Ergebnissatz.
    """
    def checkpoint():
        if cancelcheck is not None:
            cancelcheck()

    checkpoint()
    selected = Path(root).absolute()
    if any(_linked(p) for p in (selected, *selected.parents)):
        raise ValueError("Selected root contains a symlink/junction")
    selected = selected.resolve(strict=True)
    if not selected.is_dir():
        raise ValueError("Selected root is not a directory")
    result = []
    if any(_present(selected / name) for name in _MARKERS):
        checkpoint()
        result.append(_summary(selected))
    for child in sorted(selected.iterdir(), key=_sort_key):
        checkpoint()
        if _linked(child):
            result.append(SetSummary(child, "unbekannt", 0, 0, "error", ("Child symlink/junction rejected; target not inspected.",)))
            continue
        try:
            if not child.is_dir():
                continue
            if child.resolve(strict=True).parent != selected:
                raise ValueError("Child escapes selected root")
            if any(_present(child / name) for name in _MARKERS):
                result.append(_summary(child))
        except (OSError, ValueError) as exc:
            result.append(SetSummary(child, "unbekannt", 0, 0, "error", (f"{type(exc).__name__}: {exc}",)))
    checkpoint()
    return tuple(result)

"""Gemeinsame Bewertungen vorhandener Hoertests, ohne Qt oder Audio-Kopien.

Die Sperre gilt nur innerhalb eines Prozesses. Native und entfernte Bewertung
muessen deshalb durch den Aufrufer gegenseitig ausgeschlossen werden.
Quellreferenzen benutzen den separaten, validierten SourceSession-Vertrag.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


class RatingError(ValueError):
    """Kontrollierter Eingabefehler mit HTTP-kompatiblem Status."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _server():
    # Beim Skriptstart nicht einen zweiten Server samt zweiter Sperre laden.
    main = sys.modules.get("__main__")
    if main is not None and Path(getattr(main, "__file__", "")).resolve() == Path(__file__).resolve().parents[1] / "tools" / "hoertest_server.py":
        return main
    from tools import hoertest_server
    return hoertest_server


def __getattr__(name):
    if name == "CSV_SCHREIB_LOCK":
        return _server().CSV_SCHREIB_LOCK
    raise AttributeError(name)


def _metadata(folder):
    root = Path(folder).resolve(strict=True)
    for name in ("bewertung.csv", "merkmale.csv", "reihenfolge.json",
                 "dramaturgie_manifest.json", "dramaturgie_bewertung.csv",
                 "hearing_source_manifest.json", "kandidaten_manifest.json"):
        path = root / name
        if path.exists() or path.is_symlink():
            if path.resolve().parent != root:
                raise RatingError("Metadaten-Datei liegt ausserhalb des Satzes")
    return root


def _rows(root):
    hs = _server()
    path = root / "bewertung.csv"
    schema = hs.bewertungsschema(path)
    modes = {hs.BEWERTUNG_SPALTEN: "einzel",
             hs.BEWERTUNG_KANDIDATEN_SPALTEN: "kandidaten",
             hs.BEWERTUNG_DREINOTEN_SPALTEN: "dreinoten"}
    if schema not in modes:
        raise RatingError("Bewertungsschema ist ungueltig")
    rows = hs.lies_csv(path)
    if not rows:
        raise RatingError("Bewertungssatz ist leer")
    mode = modes[schema]
    dimensions = ("bewertung",) if mode == "einzel" else (("note",) if mode == "kandidaten" else ("track_note", "technik_note", "gesamt_note"))
    ids = set()
    for row in rows:
        if set(row) != set(schema) or any(v is None for v in row.values()):
            raise RatingError("Bewertungszeile hat falsche Spalten")
        pid = row["pair_id"]
        cid = pid if mode == "einzel" else row["clip_id"]
        if not pid or pid != pid.strip() or not cid or cid != cid.strip() or cid in ids:
            raise RatingError("Paar- oder Clip-ID fehlt oder ist doppelt")
        ids.add(cid)
        if any(row[d] not in ("", "1", "2", "3", "4", "5") for d in dimensions):
            raise RatingError("Bestehende Note ungueltig")
        if mode != "einzel" and row["gewaehlt"] not in ("", "0", "1"):
            raise RatingError("Gewinnerwert ungueltig")
    return mode, schema, rows, dimensions


def _source_session(root, *, verify_source_contents=True):
    from .hearing_sources import SOURCE_MANIFEST_NAME, SourceValidationError, load_source_session
    root = Path(root)
    if not (root / SOURCE_MANIFEST_NAME).exists():
        return None
    try:
        return load_source_session(root, verify_source_contents=verify_source_contents)
    except SourceValidationError as exc:
        raise RatingError(str(exc)) from exc


def _manifest(root, source_session=None):
    hs = _server()
    try:
        # Der Quellvertrag hat keine WAV-Metadaten des alten Produzenten.
        manifest = (source_session.producer_manifest if source_session is not None
                    else hs.validiere_dramaturgie_satz(root, pruefe_dateien=False))
        rows = hs.lies_csv(root / "dramaturgie_bewertung.csv")
        for row in rows:
            if set(row) != set(hs.DRAMATURGIE_BEWERTUNG_SPALTEN) or any(v is None for v in row.values()):
                raise RatingError("Dramaturgie-Bewertungszeile hat falsche Spalten")
            if any(row[d] not in ("", "1", "2", "3", "4", "5") for d in hs.DRAMATURGIE_BEWERTUNG_SPALTEN[1:-1]):
                raise RatingError("Bestehende Dramaturgienote ungueltig")
        return manifest
    except (ValueError, TypeError, KeyError) as exc:
        if isinstance(exc.__cause__, (OSError, UnicodeError)):
            raise exc.__cause__
        raise RatingError(str(exc)) from exc


def _id(payload, name, *, optional=False):
    value = payload.get(name, "")
    if not isinstance(value, str) or (not value and not optional):
        raise RatingError("ungueltige ID")
    return value.strip()


def save_rating(folder, route, payload) -> dict[str, bool]:
    """Liest, validiert, vereinigt und schreibt unter derselben Serversperre.

    RatingError meldet 400/404; Datei-/CSV-Lesefehler bleiben unveraendert,
    damit der HTTP-Transport seine bisherigen 500-Antworten liefern kann.
    Kleiner Adapter zum urspruenglichen None-Vertrag: Erfolg liefert
    {"ok": True}. Native Aufrufer duerfen diesen Rueckgabewert ignorieren.
    Quellsaetze: strukturelle Validierung ohne erneute Original-Hashes.
    Das beweist keine Inhaltsintegritaet; Laden und Playback pruefen Inhalte.
    """
    hs = _server()
    with hs.CSV_SCHREIB_LOCK:
        if not isinstance(payload, dict):
            raise RatingError("ungueltige Eingabe")
        if route not in ("/note", "/bester", "/transition-note", "/dramaturgie-note"):
            raise RatingError("nicht gefunden", 404)
        if route != "/bester":
            if "note" not in payload:
                raise RatingError("note fehlt")
            note = payload["note"]
            if note is not None and (type(note) is not int or note not in hs.NOTEN):
                raise RatingError("Note muss 1 bis 5 sein")
        root = _metadata(folder)
        mode, schema, rows, dimensions = _rows(root)
        source_session = _source_session(folder, verify_source_contents=False)
        dramaturgie = (root / hs.DRAMATURGIE_MANIFEST_NAME).exists()
        manifest = _manifest(root, source_session) if dramaturgie else None
        path = root / "bewertung.csv"
        if route in ("/transition-note", "/dramaturgie-note"):
            if manifest is None:
                raise RatingError("nicht gefunden", 404)
            id_field = "transition_id" if route == "/transition-note" else "variant_id"
            if set(payload) != {id_field, "dimension", "note"}:
                raise RatingError("ungueltige Schluessel")
            target = _id(payload, id_field)
            row_id = "pair_id" if route == "/transition-note" else "variant_id"
            if route == "/dramaturgie-note":
                path = root / "dramaturgie_bewertung.csv"
                schema = hs.DRAMATURGIE_BEWERTUNG_SPALTEN
                rows = hs.lies_csv(path)
                dimensions = schema[1:-1]
            dimension = payload["dimension"]
            if not isinstance(dimension, str) or dimension not in dimensions:
                raise RatingError("ungueltige Dimension")
            if not any(row[row_id] == target for row in rows):
                raise RatingError("ID unbekannt", 404)
            now = hs.datetime.datetime.now().isoformat(timespec="seconds")
            merged = [dict(row, **{dimension: "" if note is None else str(note), "zeit": now}) if row[row_id] == target else dict(row) for row in rows]
        else:
            pid = _id(payload, "pair_id")
            if mode == "einzel":
                if route != "/note":
                    raise RatingError("nicht gefunden", 404)
                if payload.get("dimension", "note") != "note":
                    raise RatingError("ungueltige Dimension")
                if not any(row["pair_id"] == pid for row in rows):
                    raise RatingError("Paar unbekannt", 404)
                merged = hs.merge_bewertungen(rows, {pid: note})
            else:
                cid = _id(payload, "clip_id", optional=route == "/bester")
                dimension = payload.get("dimension", "note")
                if route == "/note" and (not isinstance(dimension, str) or dimension not in dimensions):
                    raise RatingError("ungueltige Dimension")
                pair = [row for row in rows if row["pair_id"] == pid]
                target = next((row for row in pair if row["clip_id"] == cid), None)
                if not pair or (cid and target is None):
                    raise RatingError("Paar oder Clip unbekannt", 404)
                now = hs.datetime.datetime.now().isoformat(timespec="seconds")
                if route == "/bester":
                    if cid and mode == "kandidaten" and int(target["note"] or 0) < 2:
                        raise RatingError("Note 1 kann nicht bester sein")
                    merged = hs.merge_kandidaten_bewertung(rows, pair_id=pid, clip_id=cid, bester=bool(cid), kein_bester=not bool(cid), zeit=now)
                else:
                    merged = hs.merge_kandidaten_bewertung(rows, pair_id=pid, clip_id=cid, note=note, dimension=dimension, zeit=now)
        hs.schreibe_csv(path, schema, merged)
        return {"ok": True}


def _clip(root, relative):
    if not isinstance(relative, str):
        raise RatingError("Clip-Pfad fehlt")
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts or rel.parts[0] != "clips" or ".." in rel.parts or rel.suffix.lower() != ".wav":
        raise RatingError("Clip-Pfad ist unsicher")
    clips_root = root / "clips"
    if clips_root.resolve().parent != root:
        raise RatingError("Clip-Ordner liegt ausserhalb des Satzes")
    path = (root / rel).resolve()
    if clips_root.resolve() not in path.parents or not path.is_file():
        raise RatingError("Clip fehlt oder liegt ausserhalb des Satzes")
    return path


def _unique_json_object(items):
    # json.loads darf doppelte Schluessel nicht still durch den letzten ersetzen.
    result = {}
    for key, value in items:
        if key in result:
            raise RatingError(f"Doppelter JSON-Schluessel: {key}")
        result[key] = value
    return result


def load_session(folder):
    """Liefert Legacy-Pfade oder Quell-Specs mit path=None.

    Legacy-Audio wird nicht gelesen. Quellsitzungen werden einschliesslich
    Original-Hashes validiert; native Aufrufer laden sie im Worker-Thread.
    """
    hs = _server()
    with hs.CSV_SCHREIB_LOCK:
        root = _metadata(folder)
        mode, _, rows, dimensions = _rows(root)
        source_session = _source_session(folder)
        specs = source_session.specs if source_session is not None else {}
        sources = source_session.sources if source_session is not None else {}
        def clip(row, relative):
            result = {"pair_id": row["pair_id"], "clip_id": row.get("clip_id", row["pair_id"]),
                      "path": None if source_session is not None else _clip(root, relative),
                      "ratings": {d: row[d] for d in dimensions}, "gewaehlt": row.get("gewaehlt", "")}
            if source_session is not None:
                spec = specs[relative]
                result["spec"] = spec
                # Playback bindet nur die Quellen dieses Clips, nicht den Satz.
                result["sources"] = [dict(sources[p], size_bytes=sources[p]["size"])
                                     for p in dict.fromkeys((spec["track_a_path"], spec["track_b_path"]))]
            return result
        if (root / hs.DRAMATURGIE_MANIFEST_NAME).exists():
            manifest = _manifest(root, source_session)
            by_id = {r["pair_id"]: r for r in rows}
            variant_rows = {r["variant_id"]: r for r in hs.lies_csv(root / "dramaturgie_bewertung.csv")}
            groups = [{"id": v["variant_id"], "clips": [clip(by_id[t["transition_id"]], t["clip"]["path"]) for t in v["transitions"]],
                       "ratings": {d: variant_rows[v["variant_id"]][d] for d in hs.DRAMATURGIE_BEWERTUNG_SPALTEN[1:-1]}} for v in manifest["variants"]]
            return {"mode": "dramaturgie", "groups": groups}
        if mode == "einzel":
            return {"mode": mode, "groups": [{"id": r["pair_id"], "clips": [clip(r, r["clip"])], "ratings": {}} for r in rows]}
        feature_schema = hs.bewertungsschema(root / "merkmale.csv")
        if len(feature_schema) != len(set(feature_schema)) or not {"pair_id", "clip_id", "clip"} <= set(feature_schema):
            raise RatingError("Merkmale-Schema ist ungueltig")
        features = hs.lies_csv(root / "merkmale.csv")
        paths = {}
        by_id = {r["clip_id"]: r for r in rows}
        for feature in features:
            cid = feature.get("clip_id")
            if None in feature or any(v is None for v in feature.values()) or cid not in by_id or cid in paths or feature.get("pair_id") != by_id[cid]["pair_id"] or feature.get("clip") != f"clips/{cid}.wav":
                raise RatingError("Merkmale passen nicht zur Bewertung")
            paths[cid] = feature["clip"]
        if set(paths) != set(by_id):
            raise RatingError("Merkmale fehlen")
        try:
            order = json.loads(
                (root / "reihenfolge.json").read_text(encoding="utf-8"),
                object_pairs_hook=_unique_json_object,
            )
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RatingError("Blinde Reihenfolge ist ungueltig") from exc
        pairs = {}
        for row in rows:
            pairs.setdefault(row["pair_id"], []).append(row["clip_id"])
        if not isinstance(order, dict) or set(order) != set(pairs):
            raise RatingError("Blinde Reihenfolge passt nicht zu den Paaren")
        groups = []
        for pid, ids in pairs.items():
            item = order[pid]
            ordered = item.get("clips") if isinstance(item, dict) else None
            if not isinstance(ordered, list) or any(not isinstance(cid, str) for cid in ordered) or len(ordered) != len(ids) or set(ordered) != set(ids):
                raise RatingError("Blinde Clip-Reihenfolge ist unvollstaendig")
            groups.append({"id": pid, "clips": [clip(by_id[cid], paths[cid]) for cid in ordered], "ratings": {}})
        return {"mode": mode, "groups": groups}

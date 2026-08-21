"""Kandidaten-Regressionsmessung: analysiert eine Trackliste (oder liest den
Cache) und berichtet Kandidatenzahl je Seite, Schemaverteilung, PSSI-Anteil,
Intro/Outro-Verletzungen und Analysezeit je Track. Aufruf:
  python tools/kandidaten_messen.py --liste tracks.txt [--json out.json]
  python tools/kandidaten_messen.py --cache
"""
import argparse, json, os, statistics, sys, time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def zusammenfassung(tracks: list[dict]) -> dict:
    n = len(tracks)
    sch_in, sch_out = Counter(), Counter()
    for t in tracks:
        for c in t.get("mix_in_candidates", []):
            sch_in.update(c.get("schema", []))
        for c in t.get("mix_out_candidates", []):
            sch_out.update(c.get("schema", []))
    med = lambda xs: statistics.median(xs) if xs else 0
    return {
        "tracks": n,
        "ohne_in": sum(1 for t in tracks if not t.get("mix_in_candidates")),
        "ohne_out": sum(1 for t in tracks if not t.get("mix_out_candidates")),
        "mit_pssi": sum(1 for t in tracks if t.get("phrases")),
        "kandidaten_in_median": med([len(t.get("mix_in_candidates", [])) for t in tracks]),
        "kandidaten_out_median": med([len(t.get("mix_out_candidates", [])) for t in tracks]),
        "schemata_in": dict(sch_in), "schemata_out": dict(sch_out),
        "analyse_sekunden_median": med([t["analyse_sekunden"] for t in tracks if "analyse_sekunden" in t]),
    }


def _verletzungen(track: dict) -> int:
    from hpg_core.dj_brain import _get_intro_end_from_sections, _get_outro_start_from_sections
    secs = track.get("sections", [])
    ie = _get_intro_end_from_sections(secs)
    os_ = _get_outro_start_from_sections(secs, float(track.get("duration", 0.0)))
    v = sum(1 for c in track.get("mix_in_candidates", []) if c["t"] < ie - 0.05)
    v += sum(1 for c in track.get("mix_out_candidates", []) if c["t"] > os_ + 0.05)
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--liste", help="Textdatei, ein Audiopfad je Zeile")
    ap.add_argument("--cache", action="store_true", help="alle Tracks aus dem Cache lesen")
    ap.add_argument("--json", help="Ergebnis als JSON schreiben")
    a = ap.parse_args()
    from hpg_core.caching import track_to_dict
    tracks: list[dict] = []
    if a.liste:
        from hpg_core.analysis import analyze_track
        with open(a.liste, encoding="utf-8") as fh:
            pfade = [line.strip() for line in fh]
        for p in pfade:
            if not p:
                continue
            t0 = time.perf_counter()
            tr = analyze_track(p)
            dt = time.perf_counter() - t0
            if tr is None:
                continue
            d = track_to_dict(tr); d["analyse_sekunden"] = round(dt, 2); tracks.append(d)
    elif a.cache:
        from hpg_core import caching
        import sqlite3
        conn = sqlite3.connect(caching.CACHE_FILE)
        for (row,) in conn.execute("SELECT data FROM cache WHERE key <> 'version'"):
            tracks.append(json.loads(row))
    z = zusammenfassung(tracks)
    z["intro_outro_verletzungen"] = sum(_verletzungen(t) for t in tracks)
    print(json.dumps(z, indent=2, ensure_ascii=False))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"zusammenfassung": z, "tracks": tracks}, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

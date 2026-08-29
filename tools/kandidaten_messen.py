"""Kandidaten-Regressionsmessung: analysiert eine Trackliste (oder liest den
Cache) und berichtet Kandidatenzahl je Seite, Schemaverteilung, PSSI-Anteil,
Intro/Outro-Verletzungen, Analysezeit je Track sowie Kandidaten-Sekunden und
Analysepfad (fast/voll) aus der Logzeile von _kandidaten_berechnen. Aufruf:
  python tools/kandidaten_messen.py --liste tracks.txt [--json out.json]
  python tools/kandidaten_messen.py --cache
"""
import argparse, json, logging, os, re, statistics, sys, time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hpg_core.models import QUANTIZE_TOLERANCE_SEC

_KANDIDATEN_LOG_RE = re.compile(r"Kandidaten \[(fast|voll)\]: \d+ in / \d+ out in ([0-9.]+)s")


def parse_kandidaten_log(zeile: str) -> tuple[str, float] | None:
    """Liest Pfad und Sekunden aus der Erfolgszeile von _kandidaten_berechnen."""
    m = _KANDIDATEN_LOG_RE.search(zeile)
    if m is None:
        return None
    return m.group(1), float(m.group(2))


class _KandidatenLogFaenger(logging.Handler):
    """Merkt sich das letzte geparste Kandidaten-Logergebnis."""

    def __init__(self) -> None:
        super().__init__()
        self.letzte: tuple[str, float] | None = None

    def emit(self, record: logging.LogRecord) -> None:
        tref = parse_kandidaten_log(record.getMessage())
        if tref is not None:
            self.letzte = tref

    def abholen(self) -> tuple[str, float] | None:
        tref, self.letzte = self.letzte, None
        return tref


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
        "kandidaten_sekunden_median": med([t["kandidaten_sekunden"] for t in tracks if "kandidaten_sekunden" in t]),
        "pfade": dict(Counter(t["pfad"] for t in tracks if "pfad" in t)),
    }


def _verletzungen(track: dict) -> int:
    from hpg_core.dj_brain import _get_intro_end_from_sections, _get_outro_start_from_sections
    secs = track.get("sections", [])
    ie = _get_intro_end_from_sections(secs)
    os_ = _get_outro_start_from_sections(secs, float(track.get("duration", 0.0)))
    v = sum(1 for c in track.get("mix_in_candidates", []) if c["t"] < ie - QUANTIZE_TOLERANCE_SEC)
    v += sum(1 for c in track.get("mix_out_candidates", []) if c["t"] > os_ + QUANTIZE_TOLERANCE_SEC)
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
        faenger = _KandidatenLogFaenger()
        analyse_logger = logging.getLogger("hpg_core.analysis")
        analyse_logger.addHandler(faenger)
        analyse_logger.setLevel(logging.INFO)
        try:
            for p in pfade:
                if not p:
                    continue
                t0 = time.perf_counter()
                tr = analyze_track(p)
                dt = time.perf_counter() - t0
                tref = faenger.abholen()
                if tr is None:
                    continue
                d = track_to_dict(tr); d["analyse_sekunden"] = round(dt, 2)
                if tref is not None:
                    d["pfad"], d["kandidaten_sekunden"] = tref[0], tref[1]
                tracks.append(d)
        finally:
            analyse_logger.removeHandler(faenger)
    elif a.cache:
        from hpg_core import caching
        import sqlite3
        pfad = caching.CACHE_FILE
        if not os.path.exists(pfad):
            print(f"Cache-Datei nicht gefunden: {pfad}", file=sys.stderr)
            return 1
        # Context-Manager schliesst die Verbindung NICHT, daher explizit close().
        lesefehler = False
        with sqlite3.connect(pfad) as conn:
            try:
                for (row,) in conn.execute("SELECT data FROM cache WHERE key <> 'version'"):
                    tracks.append(json.loads(row))
            except sqlite3.OperationalError:
                lesefehler = True
        conn.close()
        if lesefehler:
            print(f"Cache-Datei nicht lesbar oder leer: {pfad}", file=sys.stderr)
            return 1
    z = zusammenfassung(tracks)
    z["intro_outro_verletzungen"] = sum(_verletzungen(t) for t in tracks)
    print(json.dumps(z, indent=2, ensure_ascii=False))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"zusammenfassung": z, "tracks": tracks}, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

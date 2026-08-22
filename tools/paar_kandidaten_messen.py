"""Paar-Kandidaten-Regressionsmessung: liest alle Tracks aus dem Cache, bildet
alle Paare innerhalb des BPM-Gates (PAAR_BPM_MAX) und berichtet je Paar die
Zahl der PairCandidates, Gate-Ausfaelle je Grund, Rang-1-Schemata und Scores.
Aufruf:
  python tools/paar_kandidaten_messen.py --cache [--json out.json] [--max-paare N]
"""
import argparse, itertools, json, os, sqlite3, statistics, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hpg_core.config import PAAR_BPM_MAX
from hpg_core.models import effective_bpm_diff


def zusammenfassung(ergebnisse: list[dict]) -> dict:
    med = lambda xs: statistics.median(xs) if xs else 0
    gruende = Counter()
    for e in ergebnisse:
        gruende.update(e.get("gate_gruende", {}))
    mit = [e for e in ergebnisse if e.get("anzahl", 0) > 0]
    return {
        "paare": len(ergebnisse),
        "paare_mit_kandidaten": len(mit),
        "kandidaten_median": med([e["anzahl"] for e in mit]),
        "gate_gruende": dict(gruende),
        "rang1_schemata_out": dict(Counter(e["rang1_schema_out"] for e in mit if e.get("rang1_schema_out"))),
        "rang1_schemata_in": dict(Counter(e["rang1_schema_in"] for e in mit if e.get("rang1_schema_in"))),
        "rang1_score_median": med([e["rang1_score"] for e in mit if e.get("rang1_score") is not None]),
        "blenden": dict(Counter(b for e in mit for b in e.get("blenden", []))),
    }


def _lade_tracks() -> list:
    from hpg_core import caching
    pfad = caching.CACHE_FILE
    if not os.path.exists(pfad):
        print(f"Cache-Datei nicht gefunden: {pfad}", file=sys.stderr)
        return []
    tracks = []
    conn = sqlite3.connect(pfad)
    try:
        for (row,) in conn.execute("SELECT data FROM cache WHERE key <> 'version'"):
            tracks.append(caching.dict_to_track(json.loads(row)))
    except sqlite3.OperationalError as exc:
        print(f"Cache nicht lesbar: {exc}", file=sys.stderr)
    finally:
        conn.close()
    return tracks


def _hauptschema(cand) -> str:
    from hpg_core.mix_candidates import SCHEMA_PRIORITAET
    s = [x for x in cand.schema if x in SCHEMA_PRIORITAET]
    return min(s, key=SCHEMA_PRIORITAET.index) if s else ""


def messe(tracks: list, max_paare: int | None = None) -> list[dict]:
    from hpg_core.mix_candidates import MixCandidate
    from hpg_core.pair_candidates import blend_bars_options, build_pair_candidates, pair_gate_reasons
    ergebnisse = []
    for a, b in itertools.permutations(tracks, 2):
        diff, rel = effective_bpm_diff(a.bpm, b.bpm)
        if diff > PAAR_BPM_MAX:
            continue
        gruende = Counter()
        outs = [MixCandidate.from_dict(d) for d in a.mix_out_candidates]
        ins = [MixCandidate.from_dict(d) for d in b.mix_in_candidates]
        for o in outs:
            for i in ins:
                for bars in blend_bars_options(a, o, rel):
                    for g in pair_gate_reasons(a, b, o, i, bars):
                        gruende[g] += 1
        res = build_pair_candidates(a, b)
        ergebnisse.append({
            "paar": (a.filePath, b.filePath), "anzahl": len(res), "gate_gruende": dict(gruende),
            "rang1_schema_out": _hauptschema(res[0].out_a) if res else "",
            "rang1_schema_in": _hauptschema(res[0].in_b) if res else "",
            "rang1_score": res[0].score if res else None,
            "blenden": [p.blend_bars for p in res],
        })
        if max_paare is not None and len(ergebnisse) >= max_paare:
            break
    return ergebnisse


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", action="store_true", help="Tracks aus dem Cache lesen (Pflicht)")
    ap.add_argument("--json", help="Ergebnis als JSON schreiben")
    ap.add_argument("--max-paare", type=int, default=None)
    a = ap.parse_args()
    if not a.cache:
        ap.error("--cache angeben")
    tracks = _lade_tracks()
    if not tracks:
        return 1
    ergebnisse = messe(tracks, a.max_paare)
    z = zusammenfassung(ergebnisse)
    print(json.dumps(z, indent=2, ensure_ascii=False))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"zusammenfassung": z, "paare": ergebnisse}, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""App-Regressionsmessung fuer die Mixpunkt-Kandidaten (Spec 2026-08-21 Abschnitt 4):
generiert auf allen gecachten Tracks eine Playlist, berechnet Metriken und
Empfehlungen und berichtet Dauer, Paare mit Kandidat, Rang-1-Schemata,
bass_swap-Anteil, Intro/Outro-Verletzungen der Plan-Punkte (Ziel 0), Abweichungen
Plan-Overlap vs. Kandidaten-Blende (Ziel 0), Cue-Gate-Verletzungen und den
Score-Median. Mit --ohne-kandidaten wird der Kandidatenpfad abgeschaltet
(Vergleich). Aufruf:
  python tools/playlist_kandidaten_messen.py --cache [--strategie "Harmonic Flow"] [--bpm 2.0]
                                             [--json out.json] [--ohne-kandidaten]
"""
import argparse
import json
import os
import sqlite3
import statistics
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hpg_core.models import QUANTIZE_TOLERANCE_SEC


def _med(xs):
    return statistics.median(xs) if xs else 0


def zusammenfassung(recs: list, tracks: list, dauer: dict) -> dict:
    """Reine Auswertung der Empfehlungen (recs) zur Playlist (tracks)."""
    from hpg_core.dj_brain import _get_intro_end_from_sections, _get_outro_start_from_sections
    mit = [r for r in recs if int(getattr(r, "kandidat_aktiv", 0) or 0) > 0]
    schemata_out, schemata_in = Counter(), Counter()
    verletzungen = overlap_abweichungen = bass_swap = 0
    inkonsistent = 0
    for r in mit:
        # aktiver Kandidat (Kettenwahl) — nicht zwingend Rang 1
        rang = int(getattr(r, "kandidat_aktiv", 1) or 1)
        k = r.kandidaten[rang - 1] if 0 < rang <= len(r.kandidaten) else r.kandidaten[0]
        if not bool(getattr(r, "kandidat_konsistent", True)):
            inkonsistent += 1
        schemata_out[(k.get("out_a", {}).get("schema") or [""])[0]] += 1
        schemata_in[(k.get("in_b", {}).get("schema") or [""])[0]] += 1
        if r.transition_type == "bass_swap":
            bass_swap += 1
        a, b = r.from_track, r.to_track
        if "benannter_cue" not in (k.get("out_a", {}).get("schema") or []):
            outro = _get_outro_start_from_sections(a.sections or [], float(a.duration or 0.0))
            if r.plan.mix_out_a + r.plan.overlap > outro + QUANTIZE_TOLERANCE_SEC:
                verletzungen += 1
        if "benannter_cue" not in (k.get("in_b", {}).get("schema") or []):
            intro = _get_intro_end_from_sections(b.sections or [])
            if r.plan.mix_in_b < intro - QUANTIZE_TOLERANCE_SEC:
                verletzungen += 1
        if abs(float(r.plan.overlap) - float(k.get("overlap_sec", r.plan.overlap))) > QUANTIZE_TOLERANCE_SEC:
            overlap_abweichungen += 1
    # Cue-Gate: Mix-In (Paar i-1) muss vor Mix-Out (Paar i) desselben Tracks liegen
    cue_gate = 0
    for i in range(1, len(tracks) - 1):
        vor, nach = recs[i - 1] if i - 1 < len(recs) else None, recs[i] if i < len(recs) else None
        if vor is None or nach is None:
            continue
        if int(getattr(vor, "kandidat_aktiv", 0) or 0) > 0 and int(getattr(nach, "kandidat_aktiv", 0) or 0) > 0:
            if not (0.0 <= vor.plan.mix_in_b < nach.plan.mix_out_a):
                cue_gate += 1
    return {
        "tracks": len(tracks), "paare": len(recs), "paare_mit_kandidat": len(mit),
        "rang1_schemata_out": dict(schemata_out), "rang1_schemata_in": dict(schemata_in),
        "bass_swap_anteil": round(bass_swap / len(mit), 4) if mit else None,
        "intro_outro_verletzungen": verletzungen, "overlap_abweichungen": overlap_abweichungen,
        "cue_gate_verletzungen": cue_gate, "kette_neustarts": inkonsistent,
        "score_median": _med([r.compatibility_score for r in recs]),
        "dauer": dict(dauer),
    }


def _lade_tracks():
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


def messe(tracks: list, strategie: str, bpm: float, ohne_kandidaten: bool = False) -> dict:
    from hpg_core import playlist as pl
    if ohne_kandidaten:
        pl._kandidaten_fuer_paar = lambda *a, **k: []   # Vergleichslauf ohne Kandidatenpfad
    pl.reset_pair_candidate_cache()
    t0 = time.perf_counter()
    liste = pl.generate_playlist(tracks, mode=strategie, bpm_tolerance=bpm)
    t1 = time.perf_counter()
    metrics = pl.compute_adjacent_transition_metrics(liste, bpm, {})
    recs = pl.compute_transition_recommendations(liste, bpm, scoring_context={}, transition_metrics=metrics)
    t2 = time.perf_counter()
    return zusammenfassung(recs, liste, {"generierung_s": round(t1 - t0, 2), "empfehlungen_s": round(t2 - t1, 2)})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", action="store_true", help="Tracks aus dem Cache lesen (Pflicht)")
    ap.add_argument("--strategie", default="Harmonic Flow")
    ap.add_argument("--bpm", type=float, default=2.0)
    ap.add_argument("--json", help="Ergebnis als JSON schreiben")
    ap.add_argument("--ohne-kandidaten", dest="ohne_kandidaten", action="store_true")
    a = ap.parse_args()
    if not a.cache:
        ap.error("--cache angeben")
    tracks = _lade_tracks()
    if not tracks:
        return 1
    z = messe(tracks, a.strategie, a.bpm, a.ohne_kandidaten)
    print(json.dumps(z, indent=2, ensure_ascii=False))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(z, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

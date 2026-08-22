"""Objektive Ende-zu-Ende-Pruefung der Kandidaten in der App (Checkliste Handoff
Teil 4, Punkte 2-6) auf echten Daten aus dem Cache: Playlist generieren,
Preview-Render aus dem Plan (Dauer, Pegel, Plan = aktiver Kandidat), Wahl eines
anderen Kandidaten (persistiert, Plan folgt, Preview aendert sich, Vergessen
stellt zurueck), Ketten-Neustarts, Regler Lautheit (Rang 1 aendert sich, Reset
stellt zurueck), Rekordbox-XML (MIX IN/OUT = Plan, HPG-K-Cues). Ersetzt NICHT
das Hoeren — es prueft, dass das Gehoerte dem Plan entspricht. Wahl und Regler
werden in Dateien unter --out geschrieben (Env HPG_CANDIDATE_CHOICES_FILE /
HPG_TOLERANCES_FILE), die Nutzerdaten bleiben unberuehrt. Aufruf:
  python tools/e2e_kandidaten_app.py --out <Ordner> [--strategie "Harmonic Flow"] [--bpm 2.0]
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ap = argparse.ArgumentParser()
_ap.add_argument("--out", required=True, help="Ausgabeordner (Clips, XML, Ergebnis-JSON, Wahl-/Regler-Dateien)")
_ap.add_argument("--strategie", default="Harmonic Flow")
_ap.add_argument("--bpm", type=float, default=2.0)
_args = _ap.parse_args()
OUT = _args.out
STRATEGIE, BPM = _args.strategie, _args.bpm
os.makedirs(OUT, exist_ok=True)
os.environ["HPG_CANDIDATE_CHOICES_FILE"] = os.path.join(OUT, "choices.json")
os.environ["HPG_TOLERANCES_FILE"] = os.path.join(OUT, "tolerances_override.json")
import numpy as np  # noqa: E402 - Env-Variablen muessen vor dem Import stehen
import soundfile as sf  # noqa: E402 - Env-Variablen muessen vor dem Import stehen
from hpg_core import caching, candidate_choices as cc, tolerances  # noqa: E402 - Env-Variablen muessen vor dem Import stehen
from hpg_core import playlist as pl  # noqa: E402 - Env-Variablen muessen vor dem Import stehen
from hpg_core.transition_renderer import TransitionClipSpec, render_transition_clip  # noqa: E402 - Env-Variablen muessen vor dem Import stehen
from hpg_core.exporters.rekordbox_xml_exporter import RekordboxXMLExporter  # noqa: E402 - Env-Variablen muessen vor dem Import stehen
from hpg_core.models import QUANTIZE_TOLERANCE_SEC  # noqa: E402 - Env-Variablen muessen vor dem Import stehen

E = {}
conn = sqlite3.connect(caching.CACHE_FILE)
tracks = [caching.dict_to_track(json.loads(r)) for (r,) in conn.execute("SELECT data FROM cache WHERE key <> 'version'")]
tracks = [t for t in tracks if t.filePath and os.path.exists(t.filePath)]
E["tracks_mit_datei"] = len(tracks)
pl.reset_pair_candidate_cache()
cc.reset_cache()
tolerances.reset_cache()
t0 = time.perf_counter()
liste = pl.generate_playlist(tracks, mode=STRATEGIE, bpm_tolerance=BPM)
E["generierung_s"] = round(time.perf_counter() - t0, 1)
def recs_fuer(liste):
    metrics = pl.compute_adjacent_transition_metrics(liste, BPM, {})
    return pl.compute_transition_recommendations(liste, BPM, scoring_context={}, transition_metrics=metrics)
recs = recs_fuer(liste)
mit = [r for r in recs if r.kandidat_aktiv > 0]
E["paare"] = len(recs)
E["paare_mit_kandidat"] = len(mit)

# 3) Ketten-Neustarts
neustarts = [r.index for r in recs if r.kandidat_aktiv > 0 and not r.kandidat_konsistent]
E["kette_neustarts"] = neustarts

# 2) Preview-Render aus dem Plan (erstes Paar mit Kandidat)
def render(rec, name):
    spec = TransitionClipSpec.from_plan(rec.plan, rec.from_track, rec.to_track)
    pfad = render_transition_clip(spec, os.path.join(OUT, name))
    y, sr = sf.read(pfad, always_2d=True)
    mono = y.mean(axis=1)
    dauer = len(mono) / sr
    a0 = int(spec.pre_roll_sec * sr)
    a1 = int((spec.pre_roll_sec + spec.crossfade_sec) * sr)
    xf = mono[a0:min(a1, len(mono))]
    rms_db = 20 * np.log10(max(float(np.sqrt(np.mean(xf ** 2))), 1e-9))
    return {"datei": os.path.basename(pfad), "dauer_s": round(dauer, 2),
            "erwartet_s": round(spec.pre_roll_sec + spec.crossfade_sec + spec.post_roll_sec, 2),
            "peak": round(float(np.max(np.abs(mono))), 3), "rms_crossfade_db": round(rms_db, 1),
            "mix_out_a": rec.plan.mix_out_a, "mix_in_b": rec.plan.mix_in_b, "overlap": rec.plan.overlap,
            "typ": rec.plan.transition_type, "kandidat_aktiv": rec.kandidat_aktiv}
r0 = next(r for r in mit if len(r.kandidaten) >= 2 and r.plan.overlap > 0)
E["preview_rang_aktiv"] = render(r0, "preview_aktiv.wav")
k_aktiv = r0.kandidaten[r0.kandidat_aktiv - 1]
E["preview_rang_aktiv"]["plan_gleich_kandidat"] = (abs(k_aktiv["t_out"] - r0.plan.mix_out_a) <= QUANTIZE_TOLERANCE_SEC
    and abs(k_aktiv["t_in"] - r0.plan.mix_in_b) <= QUANTIZE_TOLERANCE_SEC)

# 5) Wahl eines anderen Kandidaten -> gespeichert -> Plan folgt -> Preview aendert sich
anderer = next(k for k in r0.kandidaten if abs(k["t_out"] - k_aktiv["t_out"]) > QUANTIZE_TOLERANCE_SEC
               or abs(k["t_in"] - k_aktiv["t_in"]) > QUANTIZE_TOLERANCE_SEC)
cc.merke(r0.from_track.filePath, r0.to_track.filePath, t_out=anderer["t_out"], t_in=anderer["t_in"], blend_bars=anderer["blend_bars"])
recs2 = recs_fuer(liste)
r0b = recs2[r0.index]
E["wahl"] = {"gewaehlt": {"t_out": anderer["t_out"], "t_in": anderer["t_in"], "blend_bars": anderer["blend_bars"]},
             "plan_danach": {"mix_out_a": r0b.plan.mix_out_a, "mix_in_b": r0b.plan.mix_in_b, "overlap": r0b.plan.overlap},
             "kandidat_aktiv": r0b.kandidat_aktiv, "flag_gespeicherte_wahl": bool(r0b.kandidaten[0]["flags"].get("gespeicherte_wahl")),
             "konsistent": r0b.kandidat_konsistent,
             "plan_folgt_wahl": abs(r0b.plan.mix_out_a - anderer["t_out"]) <= QUANTIZE_TOLERANCE_SEC and abs(r0b.plan.mix_in_b - anderer["t_in"]) <= QUANTIZE_TOLERANCE_SEC,
             "datei_persistiert": cc.hole(r0.from_track.filePath, r0.to_track.filePath) is not None}
E["preview_nach_wahl"] = render(r0b, "preview_wahl.wav")
E["wahl"]["preview_unterschiedlich"] = (E["preview_nach_wahl"]["mix_out_a"], E["preview_nach_wahl"]["mix_in_b"]) != (E["preview_rang_aktiv"]["mix_out_a"], E["preview_rang_aktiv"]["mix_in_b"])
cc.vergiss(r0.from_track.filePath, r0.to_track.filePath)
recs3 = recs_fuer(liste)
E["wahl"]["nach_vergessen_wieder_wie_vorher"] = abs(recs3[r0.index].plan.mix_out_a - r0.plan.mix_out_a) <= QUANTIZE_TOLERANCE_SEC

# 6) Regler Lautheit: Rangfolge aendert sich messbar
vorher = [(r.index, r.kandidaten[0]["t_out"], r.kandidaten[0]["t_in"], r.kandidaten[0]["blend_bars"]) for r in recs3 if r.kandidat_aktiv > 0]
tolerances.write_override_kandidaten({"kandidaten_loudness_weight": 0.40})
tolerances.reset_cache()   # wie main._on_transition_weight_changed nach dem Schreiben
recs4 = recs_fuer(liste)
nachher = {r.index: (r.kandidaten[0]["t_out"], r.kandidaten[0]["t_in"], r.kandidaten[0]["blend_bars"]) for r in recs4 if r.kandidat_aktiv > 0}
geaendert = sum(1 for (i, a, b, c) in vorher if nachher.get(i) != (a, b, c))
E["regler"] = {"loudness_weight": 0.40, "rang1_geaendert": geaendert, "von": len(vorher),
               "override_summe": round(sum(v for k, v in tolerances.get_tolerances("Psytrance").items() if k.startswith("kandidaten_") and k.endswith("_weight")), 4)}
os.remove(os.environ["HPG_TOLERANCES_FILE"])
tolerances.reset_cache()
recs5 = recs_fuer(liste)
danach = {r.index: (r.kandidaten[0]["t_out"], r.kandidaten[0]["t_in"], r.kandidaten[0]["blend_bars"]) for r in recs5 if r.kandidat_aktiv > 0}
E["regler"]["nach_reset_rang1_wie_vorher"] = all(danach.get(i) == (a, b, c) for (i, a, b, c) in vorher)

# 7) Rekordbox-XML mit Empfehlungen
xml_pfad = os.path.join(OUT, "export.xml")
rep = RekordboxXMLExporter().export(liste, xml_pfad, "E2E", transitions=recs5)
root = ET.parse(xml_pfad).getroot()
marks = [m for m in root.iter("POSITION_MARK")]
hpg = [m for m in marks if (m.get("Name") or "").startswith("HPG K")]
out_ok = in_ok = gepr = gepr_in = 0
by_loc = {}
for tr in root.iter("TRACK"):
    if not tr.get("Location"):        # Playlist-Knoten <TRACK Key=...> ohne Location ueberspringen
        continue
    by_loc[os.path.normcase(os.path.basename(urllib.parse.unquote(tr.get("Location"))))] = tr
def loc(p):
    return os.path.normcase(os.path.basename(p))
for r in recs5:
    if r.kandidat_aktiv <= 0:
        continue
    tr = by_loc.get(loc(r.from_track.filePath))
    if tr is None:
        continue
    outs = [float(m.get("Start")) for m in tr.iter("POSITION_MARK") if m.get("Name") == "MIX OUT"]
    if outs:
        gepr += 1
        out_ok += int(abs(outs[0] - r.plan.mix_out_a) <= QUANTIZE_TOLERANCE_SEC)
    tb = by_loc.get(loc(r.to_track.filePath))
    if tb is not None:
        ins = [float(m.get("Start")) for m in tb.iter("POSITION_MARK") if m.get("Name") == "MIX IN"]
        if ins:
            gepr_in += 1
            in_ok += int(abs(ins[0] - r.plan.mix_in_b) <= QUANTIZE_TOLERANCE_SEC)
E["export"] = {"tracks_im_xml": len(by_loc), "position_marks": len(marks), "hpg_k_cues": len(hpg),
               "mix_out_gleich_plan": f"{out_ok}/{gepr}", "mix_in_gleich_plan": f"{in_ok}/{gepr_in}",
               "report": {"status": rep.status, "tracks_written": rep.tracks_written, "cues_written": rep.cues_written,
                          "cue_gate_meldungen": sum(1 for e in rep.errors if "Cues ausgelassen" in e),
                          "errors": list(rep.errors)[:5]},
               "beispiel_cues": [m.get("Name") for m in hpg[:6]]}
print(json.dumps(E, indent=2, ensure_ascii=False, default=str))
json.dump(E, open(os.path.join(OUT, "e2e_ergebnis.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)

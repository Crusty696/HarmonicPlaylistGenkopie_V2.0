"""Objektive Ende-zu-Ende-Pruefung der Kandidaten in der App (Checkliste Handoff
Teil 4, Punkte 2-6) auf echten Daten aus dem Cache: Playlist generieren,
Preview-Render aus dem Plan (Dauer, Pegel, Plan = aktiver Kandidat), Wahl eines
anderen Kandidaten (persistiert, Plan folgt, Preview aendert sich, Vergessen
stellt zurueck), Ketten-Neustarts, Regler Lautheit (Rang 1 aendert sich, Reset
stellt zurueck), Rekordbox-XML (MIX IN/OUT = Plan, HPG-K-Cues). Ersetzt NICHT
das Hoeren — es prueft, dass das Gehoerte dem Plan entspricht. Wahl und Regler
werden in Dateien unter --out geschrieben (Env HPG_CANDIDATE_CHOICES_FILE /
HPG_TOLERANCES_FILE), die Nutzerdaten bleiben unberuehrt. Aufruf:
  python tools/e2e_kandidaten_app.py --cache <cache-v42.db> --out <frischer-Ordner>
      [--strategie "Harmonic Flow"] [--bpm 2.0]
"""
import argparse
import atexit
import hashlib
import json
import math
import os
import shutil
import sys
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class E2EValidationError(RuntimeError):
    """Kontrollierter, nutzerverstaendlicher Abbruch des E2E-Laufs."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise E2EValidationError(message)


def _mit_phase(name: str, action):
    try:
        return action()
    except E2EValidationError:
        raise
    except Exception as exc:
        raise E2EValidationError(
            f"{name} fehlgeschlagen ({type(exc).__name__}): {exc}"
        ) from exc


def _finite_number(value, *, name: str, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise E2EValidationError(f"{name} muss eine endliche Zahl sein")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise E2EValidationError(f"{name} muss eine endliche Zahl sein") from exc
    if not math.isfinite(number) or (positive and number <= 0.0):
        qualifier = "positive " if positive else ""
        raise E2EValidationError(f"{name} muss eine endliche {qualifier}Zahl sein")
    return number


def _aktiver_kandidatenrang(rec) -> int:
    rang = getattr(rec, "kandidat_aktiv", None)
    kandidaten = getattr(rec, "kandidaten", None)
    if not isinstance(kandidaten, list):
        raise E2EValidationError(
            f"Paar {getattr(rec, 'index', '?')}: Kandidatenliste fehlt oder ist ungueltig"
        )
    if isinstance(rang, bool) or not isinstance(rang, int):
        raise E2EValidationError(
            f"Paar {getattr(rec, 'index', '?')}: aktiver Kandidatenrang muss ganzzahlig sein"
        )
    if kandidaten and not 1 <= rang <= len(kandidaten):
        raise E2EValidationError(
            f"Paar {getattr(rec, 'index', '?')}: aktiver Kandidatenrang {rang} "
            f"liegt ausserhalb 1..{len(kandidaten)}"
        )
    if not kandidaten and rang != 0:
        raise E2EValidationError(
            f"Paar {getattr(rec, 'index', '?')}: aktiver Kandidatenrang muss ohne Varianten 0 sein"
        )
    return rang


def _controlled_excepthook(exc_type, exc, _traceback) -> None:
    """CLI-Fehler ohne unkontrollierten Python-Traceback ausgeben."""
    print(f"E2E abgebrochen ({exc_type.__name__}): {exc}", file=sys.stderr)


sys.excepthook = _controlled_excepthook
_ap = argparse.ArgumentParser()
_ap.add_argument("--out", required=True, help="Ausgabeordner (Clips, XML, Ergebnis-JSON, Wahl-/Regler-Dateien)")
_ap.add_argument("--cache", required=True, help="Explizite Cache-v42-Datenbank (strikt read-only)")
_ap.add_argument("--strategie", default="Harmonic Flow")
_ap.add_argument("--bpm", type=float, default=2.0)
_args = _ap.parse_args()
ZIEL = Path(_args.out).absolute()
if os.path.lexists(ZIEL):
    _ap.error(f"--out muss frisch und nicht vorhanden sein: {ZIEL}")
STAGING = ZIEL.parent / f".{ZIEL.name}.staging-{uuid.uuid4().hex}"
OUT = str(STAGING)
STRATEGIE, BPM = _args.strategie, _args.bpm
os.environ["HPG_CANDIDATE_CHOICES_FILE"] = os.path.join(OUT, "choices.json")
os.environ["HPG_TOLERANCES_FILE"] = os.path.join(OUT, "tolerances_override.json")

from tools.rate_transitions import (  # noqa: E402 - gemeinsamer Cache-/Build-Vertrag
    _algorithm_build_fingerprint,
    _cache_pfad,
    _fingerprint_cache,
    _reject_pending_wal,
    lade_tracks_aus_cache,
)


def _cache_family_fingerprint(cache_path: Path) -> dict:
    """Bindet DB und jede relevante SQLite-/HPG-Begleitdatei bytegenau."""
    stem_lock = Path(os.path.splitext(str(cache_path))[0] + ".lock")
    pfade = {
        "db": cache_path,
        "wal": Path(f"{cache_path}-wal"),
        "shm": Path(f"{cache_path}-shm"),
        "journal": Path(f"{cache_path}-journal"),
        "db_lock": Path(f"{cache_path}.lock"),
        "dash_lock": Path(f"{cache_path}-lock"),
        "stem_lock": stem_lock,
    }
    result = {}
    for name, path in pfade.items():
        if not os.path.lexists(path):
            result[name] = None
            continue
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"Cache-Begleitpfad ist keine regulaere Datei: {path}")
        result[name] = _fingerprint_cache(path)
    return result


cache = _cache_pfad(_args.cache)
_reject_pending_wal(cache)
cache_family_digest = _cache_family_fingerprint(cache)
build_digest = _algorithm_build_fingerprint()
tracks = lade_tracks_aus_cache(str(cache))
_reject_pending_wal(cache)
if _cache_family_fingerprint(cache) != cache_family_digest:
    raise RuntimeError("Cache-Familie wurde waehrend der Vorpruefung veraendert")
if _algorithm_build_fingerprint() != build_digest:
    raise RuntimeError("Build-Digest wurde waehrend der Vorpruefung veraendert")

def _raeume_staging() -> None:
    if not os.path.lexists(STAGING):
        return
    for versuch in (1, 2):
        try:
            if STAGING.is_symlink() or not STAGING.is_dir():
                STAGING.unlink()
            else:
                shutil.rmtree(STAGING)
            return
        except Exception as exc:
            print(
                f"E2E-Aufraeumen fehlgeschlagen, Versuch {versuch}/2 "
                f"({type(exc).__name__}): {exc}",
                file=sys.stderr,
            )


atexit.register(_raeume_staging)
import numpy as np  # noqa: E402 - Env-Variablen muessen vor dem Import stehen
import soundfile as sf  # noqa: E402 - Env-Variablen muessen vor dem Import stehen
from hpg_core import candidate_choices as cc, tolerances  # noqa: E402 - Env-Variablen muessen vor dem Import stehen
from hpg_core import playlist as pl  # noqa: E402 - Env-Variablen muessen vor dem Import stehen
from hpg_core.transition_renderer import TransitionClipSpec, render_transition_clip  # noqa: E402 - Env-Variablen muessen vor dem Import stehen
from hpg_core.exporters.rekordbox_xml_exporter import RekordboxXMLExporter  # noqa: E402 - Env-Variablen muessen vor dem Import stehen
from hpg_core.models import QUANTIZE_TOLERANCE_SEC  # noqa: E402 - Env-Variablen muessen vor dem Import stehen

E = {}
tracks = [t for t in tracks if t.filePath and os.path.exists(t.filePath)]
E["tracks_mit_datei"] = len(tracks)
_require(
    len(tracks) >= 2,
    f"Mindestens zwei Tracks mit existierender Datei erforderlich; gefunden: {len(tracks)}",
)
pl.reset_pair_candidate_cache()
cc.reset_cache()
tolerances.reset_cache()
t0 = time.perf_counter()
liste = _mit_phase(
    "Playlist-Generierung",
    lambda: pl.generate_playlist(tracks, mode=STRATEGIE, bpm_tolerance=BPM),
)
E["generierung_s"] = round(time.perf_counter() - t0, 1)
def recs_fuer(liste):
    metrics = pl.compute_adjacent_transition_metrics(liste, BPM, {})
    return pl.compute_transition_recommendations(liste, BPM, scoring_context={}, transition_metrics=metrics)


def rec_nach_index(empfehlungen, index, phase):
    treffer = [r for r in empfehlungen if getattr(r, "index", None) == index]
    _require(
        len(treffer) == 1,
        f"{phase}: Empfehlung fuer Paar {index} fehlt oder ist doppelt",
    )
    return treffer[0]


recs = _mit_phase("Uebergangsempfehlungen", lambda: recs_fuer(liste))
raenge = {id(r): _aktiver_kandidatenrang(r) for r in recs}
mit = [r for r in recs if raenge[id(r)] > 0]
E["paare"] = len(recs)
E["paare_mit_kandidat"] = len(mit)
_require(bool(recs), "Keine Uebergangsempfehlung vorhanden")
_require(bool(mit), "Keine Empfehlung mit aktivem Kandidaten vorhanden")

# 3) Ketten-Neustarts
neustarts = [r.index for r in recs if raenge[id(r)] > 0 and not r.kandidat_konsistent]
E["kette_neustarts"] = neustarts

# 2) Preview-Render aus dem Plan (erstes geeignetes Paar mit Kandidat)
mit_varianten = [r for r in mit if len(getattr(r, "kandidaten", ()) or ()) >= 2]
_require(
    bool(mit_varianten),
    "Kein aktiver Kandidat mit mindestens zwei Varianten vorhanden",
)
mit_plan = [r for r in mit_varianten if getattr(r, "plan", None) is not None]
_require(bool(mit_plan), "Kein geeigneter Kandidat besitzt einen TransitionPlan")
mit_overlap = []
for rec in mit_plan:
    try:
        overlap = _finite_number(
            getattr(rec.plan, "overlap", None),
            name=f"Paar {getattr(rec, 'index', '?')}: Plan-Overlap",
            positive=True,
        )
    except E2EValidationError:
        continue
    if overlap > 0.0:
        mit_overlap.append(rec)
_require(
    bool(mit_overlap),
    "Kein TransitionPlan mit endlichem positivem Overlap vorhanden",
)
mit_rang = mit_overlap


def _kandidatenpunkt(kandidat, name):
    _require(isinstance(kandidat, dict), "Kandidat muss ein Mapping sein")
    _require(name in kandidat, f"Kandidat enthaelt {name!r} nicht")
    return _finite_number(kandidat[name], name=f"Kandidat.{name}")


r0 = None
k_aktiv = None
anderer = None
for rec in mit_rang:
    aktiv = rec.kandidaten[rec.kandidat_aktiv - 1]
    aktiv_out = _kandidatenpunkt(aktiv, "t_out")
    aktiv_in = _kandidatenpunkt(aktiv, "t_in")
    for kandidat in rec.kandidaten:
        kandidat_out = _kandidatenpunkt(kandidat, "t_out")
        kandidat_in = _kandidatenpunkt(kandidat, "t_in")
        if (
            abs(kandidat_out - aktiv_out) > QUANTIZE_TOLERANCE_SEC
            or abs(kandidat_in - aktiv_in) > QUANTIZE_TOLERANCE_SEC
        ):
            r0, k_aktiv, anderer = rec, aktiv, kandidat
            break
    if r0 is not None:
        break
_require(r0 is not None, "Kein zeitlich alternativer Kandidat vorhanden")
_require(
    abs(_kandidatenpunkt(k_aktiv, "t_out") - r0.plan.mix_out_a) <= QUANTIZE_TOLERANCE_SEC
    and abs(_kandidatenpunkt(k_aktiv, "t_in") - r0.plan.mix_in_b) <= QUANTIZE_TOLERANCE_SEC,
    f"Paar {r0.index}: aktiver Kandidat stimmt nicht mit TransitionPlan ueberein",
)

# Erst nach vollstaendiger Eignungspruefung entstehen private Artefakte.
ZIEL.parent.mkdir(parents=True, exist_ok=True)
STAGING.mkdir()


def render(rec, name):
    try:
        spec = TransitionClipSpec.from_plan(rec.plan, rec.from_track, rec.to_track)
        pfad = render_transition_clip(spec, os.path.join(OUT, name))
        y, sr = sf.read(pfad, always_2d=True)
    except Exception as exc:
        raise E2EValidationError(
            f"Preview Paar {rec.index} fehlgeschlagen ({type(exc).__name__}): {exc}"
        ) from exc
    _require(sr > 0 and len(y) > 0, f"Paar {rec.index}: Preview ist leer")
    mono = y.mean(axis=1)
    dauer = len(mono) / sr
    a0 = int(spec.pre_roll_sec * sr)
    a1 = int((spec.pre_roll_sec + spec.crossfade_sec) * sr)
    xf = mono[a0:min(a1, len(mono))]
    _require(len(xf) > 0, f"Paar {rec.index}: Crossfade-Ausschnitt ist leer")
    rms_db = 20 * np.log10(max(float(np.sqrt(np.mean(xf ** 2))), 1e-9))
    erwartet = spec.pre_roll_sec + spec.crossfade_sec + spec.post_roll_sec
    peak = float(np.max(np.abs(mono)))
    _require(
        math.isfinite(dauer) and abs(dauer - erwartet) <= max(0.05, 2 / sr),
        f"Paar {rec.index}: Preview-Dauer stimmt nicht mit Spezifikation ueberein",
    )
    _require(
        math.isfinite(peak) and 0.0 < peak <= 1.000001 and math.isfinite(rms_db),
        f"Paar {rec.index}: Preview-Pegel ist leer, nicht endlich oder uebersteuert",
    )
    pcm_digest = hashlib.sha256()
    pcm_digest.update(str(sr).encode("ascii"))
    pcm_digest.update(str(y.shape).encode("ascii"))
    pcm_digest.update(np.ascontiguousarray(y).tobytes())
    return {"datei": os.path.basename(pfad), "dauer_s": round(dauer, 2),
            "erwartet_s": round(erwartet, 2),
            "peak": round(peak, 3), "rms_crossfade_db": round(rms_db, 1),
            "mix_out_a": rec.plan.mix_out_a, "mix_in_b": rec.plan.mix_in_b, "overlap": rec.plan.overlap,
            "typ": rec.plan.transition_type, "kandidat_aktiv": rec.kandidat_aktiv,
            "pcm_sha256": pcm_digest.hexdigest()}
E["preview_rang_aktiv"] = render(r0, "preview_aktiv.wav")
E["preview_rang_aktiv"]["plan_gleich_kandidat"] = (abs(k_aktiv["t_out"] - r0.plan.mix_out_a) <= QUANTIZE_TOLERANCE_SEC
    and abs(k_aktiv["t_in"] - r0.plan.mix_in_b) <= QUANTIZE_TOLERANCE_SEC)

# 5) Wahl eines anderen Kandidaten -> gespeichert -> Plan folgt -> Preview aendert sich
_require("blend_bars" in anderer, "Alternativer Kandidat enthaelt 'blend_bars' nicht")
_mit_phase(
    f"Kandidatenwahl Paar {r0.index}",
    lambda: cc.merke(r0.from_track.filePath, r0.to_track.filePath, t_out=anderer["t_out"], t_in=anderer["t_in"], blend_bars=anderer["blend_bars"]),
)
recs2 = _mit_phase("Empfehlungen nach Wahl", lambda: recs_fuer(liste))
for rec in recs2:
    _aktiver_kandidatenrang(rec)
r0b = rec_nach_index(recs2, r0.index, "Nach Kandidatenwahl")
_require(r0b.plan is not None, f"Paar {r0.index}: TransitionPlan fehlt nach Wahl")
flags = (
    r0b.kandidaten[0].get("flags", {})
    if r0b.kandidaten and isinstance(r0b.kandidaten[0], dict)
    else {}
)
wahl_persistiert = cc.hole(r0.from_track.filePath, r0.to_track.filePath) is not None
plan_folgt_wahl = abs(r0b.plan.mix_out_a - anderer["t_out"]) <= QUANTIZE_TOLERANCE_SEC and abs(r0b.plan.mix_in_b - anderer["t_in"]) <= QUANTIZE_TOLERANCE_SEC
_require(wahl_persistiert, f"Paar {r0.index}: Wahl wurde nicht persistiert")
_require(bool(flags.get("gespeicherte_wahl")), f"Paar {r0.index}: gespeicherte Wahl ist nicht markiert")
_require(plan_folgt_wahl, f"Paar {r0.index}: TransitionPlan folgt der Wahl nicht")
E["wahl"] = {"gewaehlt": {"t_out": anderer["t_out"], "t_in": anderer["t_in"], "blend_bars": anderer["blend_bars"]},
             "plan_danach": {"mix_out_a": r0b.plan.mix_out_a, "mix_in_b": r0b.plan.mix_in_b, "overlap": r0b.plan.overlap},
             "kandidat_aktiv": r0b.kandidat_aktiv, "flag_gespeicherte_wahl": True,
             "konsistent": r0b.kandidat_konsistent,
             "plan_folgt_wahl": True,
             "datei_persistiert": True}
E["preview_nach_wahl"] = render(r0b, "preview_wahl.wav")
E["wahl"]["preview_unterschiedlich"] = (
    E["preview_nach_wahl"]["pcm_sha256"]
    != E["preview_rang_aktiv"]["pcm_sha256"]
)
_require(E["wahl"]["preview_unterschiedlich"], f"Paar {r0.index}: Preview folgt der anderen Wahl nicht")
_mit_phase(
    f"Kandidatenwahl vergessen Paar {r0.index}",
    lambda: cc.vergiss(r0.from_track.filePath, r0.to_track.filePath),
)
recs3 = _mit_phase("Empfehlungen nach Vergessen", lambda: recs_fuer(liste))
for rec in recs3:
    _aktiver_kandidatenrang(rec)
r0c = rec_nach_index(recs3, r0.index, "Nach Vergessen")
_require(r0c.plan is not None, f"Paar {r0.index}: TransitionPlan fehlt nach Vergessen")
_require(
    cc.hole(r0.from_track.filePath, r0.to_track.filePath) is None,
    f"Paar {r0.index}: vergessene Wahl ist weiterhin persistiert",
)
rang_nach_reset = _aktiver_kandidatenrang(r0c)
_require(
    rang_nach_reset == r0.kandidat_aktiv,
    f"Paar {r0.index}: Vergessen stellte aktiven Rang nicht wieder her",
)
_require(
    not any(
        isinstance(kandidat, dict)
        and bool(kandidat.get("flags", {}).get("gespeicherte_wahl"))
        for kandidat in r0c.kandidaten
    ),
    f"Paar {r0.index}: Flag gespeicherte_wahl blieb nach Vergessen gesetzt",
)
zurueckgesetzt = (
    abs(r0c.plan.mix_out_a - r0.plan.mix_out_a) <= QUANTIZE_TOLERANCE_SEC
    and abs(r0c.plan.mix_in_b - r0.plan.mix_in_b) <= QUANTIZE_TOLERANCE_SEC
    and abs(r0c.plan.overlap - r0.plan.overlap) <= QUANTIZE_TOLERANCE_SEC
)
_require(zurueckgesetzt, f"Paar {r0.index}: Vergessen stellt Plan nicht zurueck")
E["wahl"]["nach_vergessen_wieder_wie_vorher"] = True

# 6) Regler Lautheit: Rangfolge aendert sich messbar
vorher = [(r.index, r.kandidaten[0]["t_out"], r.kandidaten[0]["t_in"], r.kandidaten[0]["blend_bars"]) for r in recs3 if r.kandidat_aktiv > 0 and r.kandidaten]
_require(bool(vorher), "Keine Kandidatenrangfolge fuer Reglerpruefung vorhanden")
_mit_phase(
    "Lautheits-Regler schreiben",
    lambda: tolerances.write_override_kandidaten({"kandidaten_loudness_weight": 0.40}),
)
tolerances.reset_cache()   # wie main._on_transition_weight_changed nach dem Schreiben
recs4 = _mit_phase("Empfehlungen mit Lautheits-Regler", lambda: recs_fuer(liste))
for rec in recs4:
    _aktiver_kandidatenrang(rec)
nachher = {r.index: (r.kandidaten[0]["t_out"], r.kandidaten[0]["t_in"], r.kandidaten[0]["blend_bars"]) for r in recs4 if r.kandidat_aktiv > 0 and r.kandidaten}
_require(
    set(nachher) == {i for i, _a, _b, _c in vorher},
    "Reglerlauf verlor oder vervielfachte Kandidatenpaare",
)
geaendert = sum(1 for (i, a, b, c) in vorher if nachher.get(i) != (a, b, c))
_require(
    geaendert > 0,
    "Lautheits-Regler aenderte keinen Rang 1; Datensatz fuer E2E ungeeignet",
)
E["regler"] = {"loudness_weight": 0.40, "rang1_geaendert": geaendert, "von": len(vorher),
               "override_summe": round(sum(v for k, v in tolerances.get_tolerances("Psytrance").items() if k.startswith("kandidaten_") and k.endswith("_weight")), 4)}
_mit_phase(
    "Lautheits-Regler zuruecksetzen",
    lambda: os.remove(os.environ["HPG_TOLERANCES_FILE"]),
)
tolerances.reset_cache()
recs5 = _mit_phase("Empfehlungen nach Regler-Reset", lambda: recs_fuer(liste))
for rec in recs5:
    _aktiver_kandidatenrang(rec)
danach = {r.index: (r.kandidaten[0]["t_out"], r.kandidaten[0]["t_in"], r.kandidaten[0]["blend_bars"]) for r in recs5 if r.kandidat_aktiv > 0 and r.kandidaten}
E["regler"]["nach_reset_rang1_wie_vorher"] = all(danach.get(i) == (a, b, c) for (i, a, b, c) in vorher)
_require(
    set(danach) == {i for i, _a, _b, _c in vorher}
    and E["regler"]["nach_reset_rang1_wie_vorher"],
    "Regler-Reset stellte Rangfolge nicht vollstaendig wieder her",
)

# 7) Rekordbox-XML mit Empfehlungen
xml_pfad = os.path.join(OUT, "export.xml")
rep = _mit_phase(
    "Rekordbox-Export",
    lambda: RekordboxXMLExporter().export(liste, xml_pfad, "E2E", transitions=recs5),
)
root = _mit_phase("Rekordbox-XML lesen", lambda: ET.parse(xml_pfad).getroot())
marks = [m for m in root.iter("POSITION_MARK")]
hpg = [m for m in marks if (m.get("Name") or "").startswith("HPG K")]
out_ok = in_ok = gepr = gepr_in = 0
aktive_export_paare = 0
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
    aktive_export_paare += 1
    _require(r.plan is not None, f"Export Paar {r.index}: TransitionPlan fehlt")
    tr = by_loc.get(loc(r.from_track.filePath))
    if tr is None:
        continue
    outs = _mit_phase(
        "Rekordbox-Cue-Pruefung MIX OUT",
        lambda: [float(m.get("Start")) for m in tr.iter("POSITION_MARK") if m.get("Name") == "MIX OUT"],
    )
    _require(
        len(outs) == 1,
        f"Export Paar {r.index}: genau ein MIX OUT erwartet, gefunden: {len(outs)}",
    )
    gepr += 1
    out_ok += int(abs(outs[0] - r.plan.mix_out_a) <= QUANTIZE_TOLERANCE_SEC)
    tb = by_loc.get(loc(r.to_track.filePath))
    if tb is not None:
        ins = _mit_phase(
            "Rekordbox-Cue-Pruefung MIX IN",
            lambda: [float(m.get("Start")) for m in tb.iter("POSITION_MARK") if m.get("Name") == "MIX IN"],
        )
        _require(
            len(ins) == 1,
            f"Export Paar {r.index}: genau ein MIX IN erwartet, gefunden: {len(ins)}",
        )
        gepr_in += 1
        in_ok += int(abs(ins[0] - r.plan.mix_in_b) <= QUANTIZE_TOLERANCE_SEC)
rep_status, rep_errors, rep_tracks, rep_cues = _mit_phase(
    "Rekordbox-Report-Pruefung",
    lambda: (rep.status, list(rep.errors), rep.tracks_written, rep.cues_written),
)
_require(rep_status == "success", f"Rekordbox-Exportstatus ist {rep_status!r} statt 'success'")
_require(not rep_errors, "Rekordbox-Export meldete Fehler: " + "; ".join(rep_errors[:3]))
_require(aktive_export_paare > 0, "Keine aktiven Kandidatenpaare im Exportlauf")
_require(
    gepr == aktive_export_paare and out_ok == gepr,
    f"MIX OUT entspricht nicht fuer alle Paare dem Plan ({out_ok}/{gepr}, erwartet {aktive_export_paare})",
)
_require(
    gepr_in == aktive_export_paare and in_ok == gepr_in,
    f"MIX IN entspricht nicht fuer alle Paare dem Plan ({in_ok}/{gepr_in}, erwartet {aktive_export_paare})",
)
_require(bool(hpg), "Rekordbox-Export enthaelt keine HPG-K-Cues")
E["export"] = {"tracks_im_xml": len(by_loc), "position_marks": len(marks), "hpg_k_cues": len(hpg),
               "mix_out_gleich_plan": f"{out_ok}/{gepr}", "mix_in_gleich_plan": f"{in_ok}/{gepr_in}",
               "report": {"status": rep_status, "tracks_written": rep_tracks, "cues_written": rep_cues,
                          "cue_gate_meldungen": sum(1 for e in rep.errors if "Cues ausgelassen" in e),
                           "errors": rep_errors[:5]},
               "beispiel_cues": [m.get("Name") for m in hpg[:6]]}
Path(OUT, "e2e_ergebnis.json").write_text(
    json.dumps(E, ensure_ascii=False, indent=2, default=str) + "\n",
    encoding="utf-8",
)
_reject_pending_wal(cache)
if _cache_family_fingerprint(cache) != cache_family_digest:
    raise RuntimeError("Cache-Familie wurde waehrend des E2E-Laufs veraendert")
if _algorithm_build_fingerprint() != build_digest:
    raise RuntimeError("Build-Digest wurde waehrend des E2E-Laufs veraendert")
if os.path.lexists(ZIEL):
    raise FileExistsError(f"--out entstand waehrend des E2E-Laufs: {ZIEL}")
_mit_phase("Ergebnis publizieren", lambda: os.rename(STAGING, ZIEL))
atexit.unregister(_raeume_staging)
try:
    print(json.dumps(E, indent=2, ensure_ascii=False, default=str))
except BrokenPipeError:
    pass

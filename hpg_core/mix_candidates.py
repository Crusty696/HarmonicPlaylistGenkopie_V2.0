"""Mixpunkt-Kandidaten je Track (Spec 2026-08-21, Abschnitt 1).

Ein Kandidat ist ein Zeitpunkt auf dem Gitter plus lokale Messwerte im
Fenster +-1 Phrase. Quellen ("schema"): benannter Cue, Auto-Cue,
PSSI-Phrasengrenze, Sektionsgrenze, Energie-Neuheit, Analyzer-Mixpunkt.
Harte Gates (Intro/Outro-Guard, Coverage, Gitter, 2 Phrasen) entscheiden,
ob ein Kandidat ueberhaupt entsteht. Bewertung und Paarung: Teil 2.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict, dataclass, field, fields

from .config import (
    CUE_DEDUPE_SEC, ENERGIE_NEUHEIT_MIN, KANDIDATEN_MAX_JE_SEITE, KANDIDATEN_MIN_JE_SEITE,
)
from .models import QUANTIZE_TOLERANCE_SEC, quantize_to_grid

logger = logging.getLogger(__name__)

# Identisch zu den bisherigen Mustern in analysis.py (Wortgrenzen; "INTRO"
# markiert den Intro-START und ist KEIN Mix-In).
CUE_IN_PATTERN = re.compile(r"\b(MIX[- ]?IN|IN|START)\b")
CUE_OUT_PATTERN = re.compile(r"\b(MIX[- ]?OUT|OUT|OUTRO|END)\b")

SCHEMA_PRIORITAET = (
    "benannter_cue", "pssi_phrase", "auto_cue", "analyzer", "sektion", "energie_neuheit",
)

PROVENANCE_JE_SCHEMA = {
    "benannter_cue": "rekordbox_manual", "auto_cue": "rekordbox_auto",
    "pssi_phrase": "rekordbox_pssi", "analyzer": "hpg_analyzer",
    "sektion": "hpg_analyzer", "energie_neuheit": "hpg_analyzer",
}


@dataclass
class MixCandidate:
    """Ein Kandidat mit lokalen Messwerten. Alle Messwerte optional (None =
    nicht gemessen), damit fehlende Werte spaeter umverteilt und nie mit 0
    bestraft werden."""
    t: float
    schema: list = field(default_factory=list)
    provenance: str = ""
    confidence: float = 0.0
    # Struktur
    section_label: str = ""
    phrase_label: str = ""
    neuheit: float | None = None
    traegt_allein: bool | None = None
    # Rhythmus
    groove_pattern_lokal: list = field(default_factory=list)
    bass_pattern_lokal: list = field(default_factory=list)
    syncopation_lokal: float | None = None
    percussive_ratio_lokal: float | None = None
    # Bass
    sub_energy: float | None = None
    bass_punch: float | None = None
    bass_rms_dbfs: float | None = None
    kick_aktiv: bool | None = None
    # Harmonie
    camelot_lokal: str = ""
    key_confidence_lokal: float | None = None
    # Klangfarbe
    timbre_fingerprint_lokal: list = field(default_factory=list)
    brightness_lokal: int | None = None
    flatness_lokal: float | None = None
    avg_mids_lokal: float | None = None
    avg_highs_lokal: float | None = None
    # Energie / Lautheit
    energy_lokal: int | None = None
    energy_trend: str = ""
    lufs_lokal: float | None = None
    # Stimmung / Vocals
    mood: dict = field(default_factory=dict)
    vocal_aktiv_lokal: bool | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MixCandidate":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


def normalize_cues(cues: list | None) -> list[dict]:
    """Rekordbox-Cues → [{t, name, typ, hot_cue, provenance}], sortiert, dedupliziert
    (< CUE_DEDUPE_SEC), Provenienz: manual (benannt, nicht 'CUE(Auto)'),
    auto ('CUE(Auto)'), leer (kein Name)."""
    out: list[dict] = []
    for cue in cues or []:
        pos = cue.get("position")
        if pos is None:
            continue
        try:
            t = float(pos)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(t) or t < 0.0:
            continue
        name = (cue.get("name") or "").strip()
        if not name:
            prov = "leer"
        elif name.upper().startswith("CUE(AUTO)"):
            prov = "auto"
        else:
            prov = "manual"
        out.append({
            "t": round(t, 3), "name": name, "typ": cue.get("type"),
            "hot_cue": cue.get("hot_cue_number"), "provenance": prov,
        })
    out.sort(key=lambda c: c["t"])
    dedup: list[dict] = []
    for c in out:
        if dedup and c["t"] - dedup[-1]["t"] < CUE_DEDUPE_SEC:
            # benannter Cue gewinnt gegen unbenannten Zwilling
            if dedup[-1]["provenance"] != "manual" and c["provenance"] == "manual":
                dedup[-1] = c
            continue
        dedup.append(c)
    return dedup


def quantize_to_points(t: float, points: list[float], mode: str) -> float | None:
    """Auf eine Liste von Gitterpunkten quantisieren (PSSI-Gitter).

    ceil: kleinster Punkt >= t - Toleranz; floor: groesster Punkt <= t + Toleranz.
    None, wenn kein Punkt in der Richtung liegt. `points` muss aufsteigend
    sortiert und dedupliziert sein (das PSSI-Gitter aus
    `phrase_grid_from_phrases` erfuellt das); unsortierte Listen liefern
    stillschweigend falsche Ergebnisse."""
    if not points:
        return None
    tol = QUANTIZE_TOLERANCE_SEC
    if mode == "ceil":
        for p in points:
            if p >= t - tol:
                return float(p)
        return None
    for p in reversed(points):
        if p <= t + tol:
            return float(p)
    return None


def passes_track_gates(t: float, seite: str, *, intro_end: float, outro_start: float,
                       duration: float, grid: float) -> bool:
    """Track-seitige harte Gates (Spec Abschnitt 1): Intro/Outro-Guard und
    Platz fuer das Mindestfenster von 2 Phrasen zur jeweils anderen Seite.
    Ungueltige Geometrie (grid/duration <= 0, t ausserhalb) → False;
    ungueltige `seite` → ValueError (Programmierfehler)."""
    if grid <= 0 or duration <= 0 or t < 0 or t > duration:
        return False
    eps = QUANTIZE_TOLERANCE_SEC
    if seite == "in":
        return t + eps >= intro_end and t <= duration - 2 * grid + eps
    if seite == "out":
        return t - eps <= outro_start and t >= 2 * grid - eps
    raise ValueError(f"seite muss 'in' oder 'out' sein, nicht {seite!r}")


def _quantize(t: float, seite: str, seite_grid: list[float], grid_sec: float, anchor: float) -> float | None:
    mode = "ceil" if seite == "in" else "floor"
    if seite_grid:
        return quantize_to_points(t, seite_grid, mode)
    return quantize_to_grid(t, grid_sec, anchor, mode)


def _section_at(sections: list[dict], t: float) -> dict | None:
    for i, s in enumerate(sections):
        start, end = s.get("start_time", 0.0), s.get("end_time", 0.0)
        last = i == len(sections) - 1
        if start <= t < end or (last and t == end):
            return s
    return None


def _phrase_at(phrases: list[dict], t: float) -> dict | None:
    for i, p in enumerate(phrases):
        last = i == len(phrases) - 1
        if p["start_s"] <= t < p["end_s"] or (last and t == p["end_s"]):
            return p
    return None


def _rohe_zeitpunkte(sections, phrases, cues, analyzer_in, analyzer_out) -> dict[str, list[tuple[float, str, bool]]]:
    """Je Seite: [(t_roh, schema, guard_frei)]. Benannte Cues mit IN/OUT-Muster
    gehen nur auf ihre Seite und sind guard_frei (Spec-Ausnahme); andere
    benannte Cues ("Drop 2") sind Schema benannter_cue auf beiden Seiten MIT
    Guard; Auto-/leere Cues Schema auto_cue. Uebrige Quellen auf beide Seiten."""
    beide: list[tuple[float, str, bool]] = []
    rohe = {"in": [], "out": []}
    for c in cues:
        name = (c.get("name") or "").upper()
        if c["provenance"] == "manual" and CUE_IN_PATTERN.search(name):
            rohe["in"].append((c["t"], "benannter_cue", True))
        elif c["provenance"] == "manual" and CUE_OUT_PATTERN.search(name):
            rohe["out"].append((c["t"], "benannter_cue", True))
        elif c["provenance"] == "manual":
            beide.append((c["t"], "benannter_cue", False))
        else:
            beide.append((c["t"], "auto_cue", False))
    for p in phrases:
        beide.append((float(p["start_s"]), "pssi_phrase", False))
    vorher = None
    for s in sections:
        if s.get("label") in ("intro", "outro", "unanalysed"):
            vorher = s
            continue
        beide.append((float(s.get("start_time", 0.0)), "sektion", False))
        if vorher is not None and abs(float(s.get("avg_energy", 0.0)) - float(vorher.get("avg_energy", 0.0))) >= ENERGIE_NEUHEIT_MIN:
            beide.append((float(s.get("start_time", 0.0)), "energie_neuheit", False))
        vorher = s
    if analyzer_in is not None and analyzer_in >= 0:
        rohe["in"].append((float(analyzer_in), "analyzer", False))
    if analyzer_out is not None and analyzer_out >= 0:
        rohe["out"].append((float(analyzer_out), "analyzer", False))
    rohe["in"].extend(beide)
    rohe["out"].extend(beide)
    return rohe


def collect_candidate_times(*, seite_grid: list[float], sections: list[dict], phrases: list[dict],
                            cues: list[dict], analyzer_in: float | None, analyzer_out: float | None,
                            duration: float, grid_sec: float, intro_end: float, outro_start: float,
                            outro_covered: bool, anchor: float = 0.0,
                            ) -> tuple[list[MixCandidate], list[MixCandidate]]:
    """Kandidaten-Zeitpunkte je Seite: quantisieren, Gates, Dedupe (gleicher
    Gitterpunkt → Schemata vereinigen), Kappung auf KANDIDATEN_MAX_JE_SEITE
    nach SCHEMA_PRIORITAET, dann zeitlich sortiert. Noch OHNE Messwerte."""
    rohe = _rohe_zeitpunkte(sections, phrases, cues, analyzer_in, analyzer_out)
    ergebnis: dict[str, list[MixCandidate]] = {}
    for seite in ("in", "out"):
        if seite == "out" and not outro_covered:
            ergebnis[seite] = []
            continue
        je_t: dict[float, MixCandidate] = {}
        for t_roh, schema, guard_frei in rohe[seite]:
            tq = _quantize(t_roh, seite, seite_grid, grid_sec, anchor)
            if tq is None:
                continue
            tq = round(float(tq), 3)
            # Spec-Ausnahme: ein benannter Cue mit MIX IN/IN/START bzw. OUT-
            # Muster ist eine bewusste Nutzerentscheidung und schlaegt den
            # Intro/Outro-Guard; nur Trackgrenzen gelten. Alle anderen: Gates.
            if guard_frei:
                gate_ok = 0.0 <= tq <= duration
            else:
                gate_ok = passes_track_gates(tq, seite, intro_end=intro_end, outro_start=outro_start,
                                             duration=duration, grid=grid_sec)
            if not gate_ok:
                continue
            sek = _section_at(sections, tq)
            if sek is not None and sek.get("label") == "unanalysed":
                continue
            if tq not in je_t:
                je_t[tq] = MixCandidate(t=tq)
            if schema not in je_t[tq].schema:
                je_t[tq].schema.append(schema)
        kandidaten = list(je_t.values())
        for k in kandidaten:
            k.schema.sort(key=SCHEMA_PRIORITAET.index)
            k.provenance = PROVENANCE_JE_SCHEMA[k.schema[0]]
            sek = _section_at(sections, k.t)
            k.section_label = sek.get("label", "") if sek else ""
            ph = _phrase_at(phrases, k.t)
            k.phrase_label = ph["label"] if ph else ""
        if len(kandidaten) > KANDIDATEN_MAX_JE_SEITE:
            kandidaten.sort(key=lambda k: (SCHEMA_PRIORITAET.index(k.schema[0]), -len(k.schema)))
            kandidaten = kandidaten[:KANDIDATEN_MAX_JE_SEITE]
        kandidaten.sort(key=lambda k: k.t)
        if 0 < len(kandidaten) < KANDIDATEN_MIN_JE_SEITE:
            logger.info("Nur %d %s-Kandidaten (Minimum %d) — Quellen reichen nicht",
                        len(kandidaten), seite, KANDIDATEN_MIN_JE_SEITE)
        ergebnis[seite] = kandidaten
    return ergebnis["in"], ergebnis["out"]

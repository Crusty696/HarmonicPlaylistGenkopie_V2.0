"""Mixpunkt-Kandidaten je Track (Spec 2026-08-21, Abschnitt 1).

Ein Kandidat ist ein Zeitpunkt auf dem Gitter plus lokale Messwerte im
Fenster +-1 Phrase. Quellen ("schema"): benannter Cue, Auto-Cue,
PSSI-Phrasengrenze, Sektionsgrenze, Energie-Neuheit, Analyzer-Mixpunkt.
Harte Gates (Intro/Outro-Guard, Coverage, Gitter, 2 Phrasen) entscheiden,
ob ein Kandidat ueberhaupt entsteht. Bewertung und Paarung: Teil 2.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field, fields

from .config import (
    CUE_DEDUPE_SEC, KANDIDATEN_MAX_JE_SEITE, KANDIDATEN_MIN_JE_SEITE,
)
from .models import QUANTIZE_TOLERANCE_SEC

logger = logging.getLogger(__name__)

# Identisch zu den bisherigen Mustern in analysis.py (Wortgrenzen; "INTRO"
# markiert den Intro-START und ist KEIN Mix-In).
CUE_IN_PATTERN = re.compile(r"\b(MIX[- ]?IN|IN|START)\b")
CUE_OUT_PATTERN = re.compile(r"\b(MIX[- ]?OUT|OUT|OUTRO|END)\b")

SCHEMA_PRIORITAET = (
    "benannter_cue", "pssi_phrase", "auto_cue", "analyzer", "sektion", "energie_neuheit",
)


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
        if t < 0.0:
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
    None, wenn kein Punkt in der Richtung liegt."""
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
    Platz fuer das Mindestfenster von 2 Phrasen zur jeweils anderen Seite."""
    if grid <= 0 or duration <= 0 or t < 0 or t > duration:
        return False
    eps = QUANTIZE_TOLERANCE_SEC
    if seite == "in":
        return t + eps >= intro_end and t <= duration - 2 * grid + eps
    if seite == "out":
        return t - eps <= outro_start and t >= 2 * grid - eps
    raise ValueError(f"seite muss 'in' oder 'out' sein, nicht {seite!r}")

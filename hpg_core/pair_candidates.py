"""Paarung und Bewertung von Mixpunkt-Kandidaten (Spec 2026-08-21, Abschnitt 2).

Eingabe: Track A (`mix_out_candidates`), Track B (`mix_in_candidates`).
Ausgabe: sortierte `PairCandidate`s (Zeitpunkt-Kombination x Blendenlaenge)
mit Gates, Score aus allen Faktoren lokal an der Naht, Teilwerten, Flags und
Begruendung. Reine Funktionen, kein Audio. Teil 4 bindet das Ergebnis an
Scoring, GUI und Export an; hier wird nichts am Track veraendert.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields

from .config import (
    BASS_RMS_DELTA_MAX_DB, BPM_HALF_DOUBLE_PENALTY, ENERGIE_TREND_WIDERSPRUCH,
    KICK_KONFLIKT_ABZUG, LUFS_DELTA_MAX_DB, MIDS_HIGHS_DELTA_MAX, MIN_TRANSITION_BARS,
    PAAR_BPM_MAX, PAAR_BPM_SKALA, PAAR_HALF_DOUBLE_MAX_BARS, PAAR_MAX_KOMBINATIONEN,
    PAAR_PITCH_MAX, PERCUSSIVE_ABZUG, PERCUSSIVE_HOCH, PERCUSSIVE_NIEDRIG, PSSI_MOOD_ABZUG,
    STRUKTUR_LABEL_BONUS, SYNCOPATION_DELTA_MAX,
)
from .dj_brain import (
    _get_intro_end_from_sections, _get_outro_start_from_sections,
    get_genre_compatibility, get_mix_profile,
)
from .mix_candidates import (
    CUE_IN_PATTERN, CUE_OUT_PATTERN, SCHEMA_PRIORITAET, MixCandidate, _quantize,
    quantize_to_points,
)
from .models import (
    QUANTIZE_TOLERANCE_SEC, Track, camelot_relation_score, effective_bpm_diff,
    quantize_to_grid, seconds_per_bar,
)
from .tolerances import get_tolerances
from .transition_features import (
    BASS_PATTERN_SHARE, DEFAULT_BRIGHTNESS_DELTA_MAX, DEFAULT_FLATNESS_DELTA_MAX,
    DEFAULT_GROOVE_SIM_FLOOR, DEFAULT_PUNCH_DELTA_MAX, DEFAULT_SUB_DELTA_MAX,
    MODE_SWITCH_PENALTY, _normiert, _spreize, cosine_similarity,
)

# Reihenfolge der Faktoren = Reihenfolge in Teilwerten/Begruendung.
FAKTOREN = ("harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre",
            "mood", "loudness", "structure")
SCHEMA_RANG = {s: i for i, s in enumerate(SCHEMA_PRIORITAET)}


@dataclass
class PairCandidate:
    """Eine Kombination aus Mix-Out-Kandidat (A) und Mix-In-Kandidat (B) mit
    Blendenlaenge. Teilwerte je Faktor in [0,1] oder None (nicht messbar)."""
    out_a: MixCandidate
    in_b: MixCandidate
    blend_bars: int
    overlap_sec: float
    score: float = 0.0
    teilwerte: dict = field(default_factory=dict)
    flags: dict = field(default_factory=dict)
    begruendung: str = ""
    rang: int = 0
    bpm_relation: str = "direct"

    @property
    def t_out(self) -> float:
        return self.out_a.t

    @property
    def t_in(self) -> float:
        return self.in_b.t

    def to_dict(self) -> dict:
        d = asdict(self)
        d["t_out"], d["t_in"] = self.t_out, self.t_in
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PairCandidate":
        names = {f.name for f in fields(cls)}
        kw = {k: v for k, v in d.items() if k in names}
        kw["out_a"] = MixCandidate.from_dict(kw["out_a"])
        kw["in_b"] = MixCandidate.from_dict(kw["in_b"])
        return cls(**kw)


def _genre(track: Track) -> str:
    # Lazy: playlist importiert (ab Teil 4) dieses Modul — kein Importzyklus.
    from .playlist import _resolve_track_genre
    return _resolve_track_genre(track)


def _grid_sec(track: Track) -> float:
    unit = int(track.phrase_unit) if track.phrase_unit else get_mix_profile(_genre(track)).phrase_unit
    return seconds_per_bar(track.bpm) * unit


def _guard_frei(track: Track, cand: MixCandidate, seite: str) -> bool:
    """Spec-Ausnahme (Abschnitt 1): nur ein MANUELLER Cue mit IN- bzw. OUT-Muster
    schlaegt den Guard. MixCandidate traegt das Muster nicht; deshalb wird ueber
    track.cue_points geprueft, ob ein solcher Cue — mit derselben Quantisierung
    wie in Teil 1 (mix_candidates._quantize) — auf cand.t faellt."""
    if "benannter_cue" not in (cand.schema or []):
        return False
    muster = CUE_IN_PATTERN if seite == "in" else CUE_OUT_PATTERN
    grid = _grid_sec(track)
    for cue in track.cue_points or []:
        if cue.get("provenance") != "manual":
            continue
        if not muster.search((cue.get("name") or "").upper()):
            continue
        q = _quantize(float(cue["t"]), seite, list(track.phrase_grid or []), grid, track.phrase_anchor)
        if q is not None and abs(round(float(q), 3) - cand.t) <= QUANTIZE_TOLERANCE_SEC:
            return True
    return False


def _auf_gitter(track: Track, t: float, seite: str) -> bool:
    """Punkt liegt (mit QUANTIZE_TOLERANCE_SEC) auf dem PSSI-Gitter bzw. dem
    Phrasenraster des Tracks."""
    if track.phrase_grid:
        q = quantize_to_points(t, list(track.phrase_grid), "floor" if seite == "out" else "ceil")
    else:
        grid = _grid_sec(track)
        if grid <= 0.0:
            return False
        q = quantize_to_grid(t, grid, track.phrase_anchor, "round")
    return q is not None and abs(q - t) <= QUANTIZE_TOLERANCE_SEC


def _outro_deckel(track_a: Track, out_a: MixCandidate) -> float:
    """Spaetestes Ende der Blende: Outro-Start; bei guard-freiem OUT-Cue das Trackende."""
    if _guard_frei(track_a, out_a, "out"):
        return float(track_a.duration)
    return _get_outro_start_from_sections(track_a.sections, float(track_a.duration))


def pair_gate_reasons(track_a: Track, track_b: Track, out_a: MixCandidate,
                      in_b: MixCandidate, blend_bars: int) -> list[str]:
    """Harte Gates auf Paar-Ebene (Spec Abschnitt 2, Schritt 1). Leere Liste =
    Kombination erlaubt; sonst die Gruende (stabil benannt, fuer Messung)."""
    reasons: list[str] = []
    diff, rel = effective_bpm_diff(track_a.bpm, track_b.bpm)
    if diff > PAAR_BPM_MAX:
        reasons.append("bpm")
    if track_a.bpm > 0 and diff / track_a.bpm > PAAR_PITCH_MAX:
        reasons.append("pitch")
    if out_a.section_label == "unanalysed" or in_b.section_label == "unanalysed":
        reasons.append("coverage")
    if not track_a.outro_covered:
        reasons.append("outro_covered")
    spb = seconds_per_bar(track_a.bpm)
    overlap = blend_bars * spb
    if out_a.t + overlap > _outro_deckel(track_a, out_a) + QUANTIZE_TOLERANCE_SEC:
        reasons.append("blende_im_outro")
    intro_end = _get_intro_end_from_sections(track_b.sections)
    if not _guard_frei(track_b, in_b, "in") and in_b.t < intro_end - QUANTIZE_TOLERANCE_SEC:
        reasons.append("in_im_intro")
    if in_b.t < 0.0 or in_b.t > float(track_b.duration):
        reasons.append("in_ausserhalb")
    if not _auf_gitter(track_a, out_a.t, "out"):
        reasons.append("gitter_out")
    if not _auf_gitter(track_b, in_b.t, "in"):
        reasons.append("gitter_in")
    return reasons


def blend_bars_options(track_a: Track, out_a: MixCandidate, bpm_relation: str) -> list[int]:
    """Beide Genre-Blendenlaengen (transition_bars), je durch den Outro-Deckel
    auf ganze Takte geklemmt; Half/Double hoechstens PAAR_HALF_DOUBLE_MAX_BARS;
    unter MIN_TRANSITION_BARS (Projekt-Untergrenze, wie playlist._outro_overlap_limit)
    entfaellt die Laenge. Doppelte Werte nach dem Deckel werden zusammengelegt."""
    kurz, lang = get_mix_profile(_genre(track_a)).transition_bars
    spb = seconds_per_bar(track_a.bpm)
    if spb <= 0.0:
        return []
    max_bars = int(math.floor((_outro_deckel(track_a, out_a) - out_a.t + QUANTIZE_TOLERANCE_SEC) / spb))
    out: list[int] = []
    for bars in (int(kurz), int(lang)):
        b = min(bars, max_bars)
        if bpm_relation != "direct":
            b = min(b, PAAR_HALF_DOUBLE_MAX_BARS)
        if b >= MIN_TRANSITION_BARS and b not in out:
            out.append(b)
    return out

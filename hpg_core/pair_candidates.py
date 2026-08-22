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

from . import candidate_choices, candidate_preferences
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


def _beide(a, b) -> bool:
    return a is not None and b is not None


def _teil_harmonie(out_a: MixCandidate, in_b: MixCandidate, *, harmonic_strictness: int,
                   allow_experimental: bool) -> float | None:
    if not out_a.camelot_lokal or not in_b.camelot_lokal:
        return None
    return camelot_relation_score(
        out_a.camelot_lokal, in_b.camelot_lokal, harmonic_strictness=harmonic_strictness,
        allow_experimental=allow_experimental, penalty=1.0) / 100.0


def _teil_bpm(diff: float) -> float:
    return math.exp(-diff / PAAR_BPM_SKALA)


def _teil_energie(out_a: MixCandidate, in_b: MixCandidate, richtung: str | None) -> float | None:
    if not _beide(out_a.energy_lokal, in_b.energy_lokal):
        return None
    diff = float(in_b.energy_lokal) - float(out_a.energy_lokal)
    # Formeln wie playlist.calculate_enhanced_compatibility (Energie-Block).
    if richtung == "up":
        wert = min(1.0, max(0.0, diff) / 50.0)
    elif richtung == "down":
        wert = min(1.0, max(0.0, -diff) / 50.0)
    elif richtung == "maintain":
        wert = max(0.0, 1.0 - abs(diff) / 50.0)
    else:
        wert = max(0.0, 1.0 - abs(diff) / 100.0)
    trend = in_b.energy_trend or ""
    if (richtung == "up" and trend == "falling") or (richtung == "down" and trend == "rising"):
        wert *= ENERGIE_TREND_WIDERSPRUCH
    return wert


def _teil_groove(out_a: MixCandidate, in_b: MixCandidate, tol: dict, flags: dict) -> float | None:
    bass_sim = cosine_similarity(out_a.bass_pattern_lokal, in_b.bass_pattern_lokal)
    onset_sim = cosine_similarity(out_a.groove_pattern_lokal, in_b.groove_pattern_lokal)
    if bass_sim is None and onset_sim is None:
        return None
    if bass_sim is None:
        roh = onset_sim
    elif onset_sim is None:
        roh = bass_sim
    else:
        roh = BASS_PATTERN_SHARE * bass_sim + (1.0 - BASS_PATTERN_SHARE) * onset_sim
    wert = _spreize(roh, tol.get("groove_sim_floor", DEFAULT_GROOVE_SIM_FLOOR))
    if _beide(out_a.syncopation_lokal, in_b.syncopation_lokal):
        wert *= _normiert(in_b.syncopation_lokal - out_a.syncopation_lokal, SYNCOPATION_DELTA_MAX)
    pa, pb = out_a.percussive_ratio_lokal, in_b.percussive_ratio_lokal
    if _beide(pa, pb):
        if pa > PERCUSSIVE_HOCH and pb > PERCUSSIVE_HOCH:
            wert -= PERCUSSIVE_ABZUG
        flags["lange_blende_erlaubt"] = bool(pa < PERCUSSIVE_NIEDRIG and pb < PERCUSSIVE_NIEDRIG)
    return max(0.0, min(1.0, wert))


def _teil_bass(out_a: MixCandidate, in_b: MixCandidate, tol: dict, flags: dict,
               bass_swap_geplant: bool = False) -> float | None:
    sub = (_normiert(in_b.sub_energy - out_a.sub_energy, tol.get("bass_delta_max", DEFAULT_SUB_DELTA_MAX))
           if _beide(out_a.sub_energy, in_b.sub_energy) else None)
    punch = (_normiert(in_b.bass_punch - out_a.bass_punch, DEFAULT_PUNCH_DELTA_MAX)
             if _beide(out_a.bass_punch, in_b.bass_punch) else None)
    if sub is None and punch is None:
        return None
    if sub is None:
        wert = punch
    elif punch is None:
        wert = sub
    else:
        wert = 0.6 * sub + 0.4 * punch
    if _beide(out_a.bass_rms_dbfs, in_b.bass_rms_dbfs):
        wert *= _normiert(in_b.bass_rms_dbfs - out_a.bass_rms_dbfs, BASS_RMS_DELTA_MAX_DB)
    konflikt = bool(out_a.kick_aktiv and in_b.kick_aktiv)
    flags["bass_swap_pflicht"] = konflikt
    # Plant der Aufrufer einen Bass-/EQ-Swap (App bei bass_swap_pflicht, Hoertest
    # mit pro_eq_swap), ist der Kick-Konflikt geloest — kein Abzug, Flag bleibt.
    if konflikt and not bass_swap_geplant:
        wert -= KICK_KONFLIKT_ABZUG
    return max(0.0, min(1.0, wert))


def _teil_timbre(out_a: MixCandidate, in_b: MixCandidate) -> float | None:
    wert = cosine_similarity(out_a.timbre_fingerprint_lokal, in_b.timbre_fingerprint_lokal)
    if wert is None:
        return None
    deltas = []
    if _beide(out_a.avg_mids_lokal, in_b.avg_mids_lokal):
        deltas.append(abs(in_b.avg_mids_lokal - out_a.avg_mids_lokal))
    if _beide(out_a.avg_highs_lokal, in_b.avg_highs_lokal):
        deltas.append(abs(in_b.avg_highs_lokal - out_a.avg_highs_lokal))
    if deltas:
        wert *= _normiert(sum(deltas) / len(deltas), MIDS_HIGHS_DELTA_MAX)
    return max(0.0, min(1.0, wert))


def _teil_mood(out_a: MixCandidate, in_b: MixCandidate, tol: dict) -> float | None:
    ma, mb = out_a.mood or {}, in_b.mood or {}
    ha = ma.get("brightness", out_a.brightness_lokal)
    hb = mb.get("brightness", in_b.brightness_lokal)
    fa = ma.get("flatness", out_a.flatness_lokal)
    fb = mb.get("flatness", in_b.flatness_lokal)
    hell = (_normiert(float(hb) - float(ha), tol.get("brightness_delta_max", DEFAULT_BRIGHTNESS_DELTA_MAX))
            if _beide(ha, hb) else None)
    flach = _normiert(float(fb) - float(fa), DEFAULT_FLATNESS_DELTA_MAX) if _beide(fa, fb) else None
    if hell is None and flach is None:
        return None
    if hell is None:
        wert = flach
    elif flach is None:
        wert = hell
    else:
        wert = 0.7 * hell + 0.3 * flach
    if ma.get("key_mode") and mb.get("key_mode") and ma["key_mode"] != mb["key_mode"]:
        wert -= MODE_SWITCH_PENALTY
    if (ma.get("pssi_mood") is not None and mb.get("pssi_mood") is not None
            and ma["pssi_mood"] != mb["pssi_mood"]):
        wert -= PSSI_MOOD_ABZUG
    return max(0.0, min(1.0, wert))


def _teil_lautheit(out_a: MixCandidate, in_b: MixCandidate) -> float | None:
    if not _beide(out_a.lufs_lokal, in_b.lufs_lokal):
        return None
    return _normiert(in_b.lufs_lokal - out_a.lufs_lokal, LUFS_DELTA_MAX_DB)


_OUT_LABELS = {"outro", "breakdown", "Outro", "Down"}
_IN_LABELS = {"drop", "Chorus"}


def _teil_struktur(out_a: MixCandidate, in_b: MixCandidate) -> float | None:
    teile = []
    if in_b.neuheit is not None:
        teile.append(float(in_b.neuheit))
    if in_b.traegt_allein is not None:
        teile.append(1.0 if in_b.traegt_allein else 0.0)
    if not teile:
        return None
    wert = sum(teile) / len(teile)
    aus_out = out_a.section_label in _OUT_LABELS or out_a.phrase_label in _OUT_LABELS
    in_in = in_b.section_label in _IN_LABELS or in_b.phrase_label in _IN_LABELS
    if aus_out and in_in:
        wert += STRUKTUR_LABEL_BONUS
    return max(0.0, min(1.0, wert))


def _gewichte(tol: dict, genre: str, explizit: bool) -> dict[str, float]:
    """Gewichtsquelle: ein explizit uebergebenes `tolerances` gewinnt immer;
    sonst schlagen Praeferenzen aus dem Hoertest (candidate_preferences.json)
    die geladenen Toleranzen; ohne Eintrag fuer das Genre gelten die
    kandidaten_*_weight der Toleranzen."""
    pref = None if explizit else candidate_preferences.kandidaten_gewichte(genre)
    quelle = pref if pref is not None else tol
    return {f: float(quelle.get(f"kandidaten_{f}_weight", 0.0)) for f in FAKTOREN}


def score_pair(track_a: Track, track_b: Track, out_a: MixCandidate, in_b: MixCandidate,
               blend_bars: int, *, energy_direction=None, harmonic_strictness: int = 7,
               allow_experimental: bool = True, tolerances: dict | None = None,
               bass_swap_geplant: bool = False) -> tuple[float, dict, dict]:
    """Score einer Kombination aus allen Faktoren lokal an der Naht (Spec
    Abschnitt 2, Schritt 2). Liefert (score, teilwerte, flags). Fehlende
    Teilwerte (None) werden per combine_weighted umverteilt, nie mit 0 bewertet.
    Half/Double: Gesamtscore x BPM_HALF_DOUBLE_PENALTY. Vocals beidseitig: -0.06.
    `blend_bars` ist bewusst KEIN Score-Merkmal (Spec Abschnitt 1: Blendenlaenge
    als Qualitaetsmerkmal widerlegt, rho -0.08); es dient nur den Gates/Flags.
    `bass_swap_geplant`: der Aufrufer rendert/plant einen Bass-/EQ-Swap — der
    Kick-Konflikt ist damit geloest, KICK_KONFLIKT_ABZUG entfaellt, das Flag
    `bass_swap_pflicht` bleibt gesetzt."""
    from .playlist import VOCAL_CLASH_PENALTY, combine_weighted   # lazy, s. _genre
    richtung = getattr(energy_direction, "value", energy_direction)
    genre_a, genre_b = _genre(track_a), _genre(track_b)
    tol = tolerances if tolerances is not None else get_tolerances(genre_a)
    diff, rel = effective_bpm_diff(track_a.bpm, track_b.bpm)
    flags = {"half_double": rel != "direct", "bass_swap_pflicht": False,
             "lange_blende_erlaubt": False,
             "benannter_cue": _guard_frei(track_a, out_a, "out") or _guard_frei(track_b, in_b, "in")}
    teil = {
        "harmonic": _teil_harmonie(out_a, in_b, harmonic_strictness=harmonic_strictness,
                                   allow_experimental=allow_experimental),
        "bpm": _teil_bpm(diff),
        "energy": _teil_energie(out_a, in_b, richtung),
        "genre": get_genre_compatibility(genre_a, genre_b),
        "groove": _teil_groove(out_a, in_b, tol, flags),
        "bass": _teil_bass(out_a, in_b, tol, flags, bass_swap_geplant),
        "timbre": _teil_timbre(out_a, in_b),
        "mood": _teil_mood(out_a, in_b, tol),
        "loudness": _teil_lautheit(out_a, in_b),
        "structure": _teil_struktur(out_a, in_b),
    }
    gew = _gewichte(tol, genre_a, explizit=tolerances is not None)
    if teil["harmonic"] is not None and _beide(out_a.key_confidence_lokal, in_b.key_confidence_lokal):
        gew["harmonic"] *= max(0.0, min(1.0, min(out_a.key_confidence_lokal, in_b.key_confidence_lokal)))
    score = combine_weighted(teil, gew)
    if flags["half_double"]:
        score *= BPM_HALF_DOUBLE_PENALTY
    if out_a.vocal_aktiv_lokal and in_b.vocal_aktiv_lokal:
        score -= VOCAL_CLASH_PENALTY
    return max(0.0, min(1.0, score)), teil, flags


_FAKTOR_NAMEN = {
    "harmonic": "Harmonie", "bpm": "Tempo", "energy": "Energie", "genre": "Genre",
    "groove": "Groove", "bass": "Bass", "timbre": "Klangfarbe", "mood": "Stimmung",
    "loudness": "Lautheit", "structure": "Struktur",
}


def _stufe(wert: float | None) -> str:
    if wert is None:
        return "nicht messbar"
    if wert >= 0.8:
        return "stark"
    if wert >= 0.5:
        return "mittel"
    return "schwach"


def begruendung_aus_teilwerten(teilwerte: dict, flags: dict, blend_bars: int) -> str:
    """Begruendung ausschliesslich aus Teilwerten und Flags (kein freier Text)."""
    teile = [f"{_FAKTOR_NAMEN.get(k, k)} {_stufe(teilwerte.get(k))}" for k in FAKTOREN if k in teilwerte]
    if flags.get("bass_swap_pflicht"):
        teile.append("Bass-Swap noetig")
    if flags.get("half_double"):
        teile.append(f"Half/Double, Cut <= {PAAR_HALF_DOUBLE_MAX_BARS} Takte")
    if flags.get("lange_blende_erlaubt"):
        teile.append("lange Blende erlaubt")
    if flags.get("benannter_cue"):
        teile.append("benannter Cue")
    teile.append(f"Blende {blend_bars} Takte")
    return "; ".join(teile)


def _hauptschema(cand: MixCandidate, rang_map: dict | None = None) -> str:
    """Schema mit dem besten Rang — dieselbe Map wie _sortschluessel (Hoertest-
    Rangfolge je Genre, sonst SCHEMA_PRIORITAET); unbekannte Schemata zaehlen
    nicht als Hauptschema."""
    rm = rang_map if rang_map is not None else SCHEMA_RANG
    schemata = [s for s in (cand.schema or []) if s in rm]
    if not schemata:
        schemata = [s for s in (cand.schema or []) if s in SCHEMA_RANG]
        return min(schemata, key=SCHEMA_RANG.get) if schemata else ""
    return min(schemata, key=rm.get)


def _gleiche_kombination(p: PairCandidate, q: PairCandidate, grid_a: float, grid_b: float,
                         rang_map: dict | None = None) -> bool:
    """Spec Schritt 4: |dt| < 1 Phrase und gleiches Schema. Toleranz abgezogen,
    weil Teil 1 t auf 3 Dezimalen rundet — sonst verschmelzen Gitterpunkte, die
    genau eine Phrase auseinanderliegen. Gleiche Blende, sonst fiele die zweite
    Blendenlaenge (identischer Score) als Duplikat weg."""
    return (p.blend_bars == q.blend_bars
            and abs(p.t_out - q.t_out) < grid_a - QUANTIZE_TOLERANCE_SEC
            and abs(p.t_in - q.t_in) < grid_b - QUANTIZE_TOLERANCE_SEC
            and _hauptschema(p.out_a, rang_map) == _hauptschema(q.out_a, rang_map)
            and _hauptschema(p.in_b, rang_map) == _hauptschema(q.in_b, rang_map))


def _sortschluessel(p: PairCandidate, rang_map: dict | None = None):
    """Score, dann Schema-Rang (Hoertest-Rangfolge je Genre, sonst
    SCHEMA_PRIORITAET) fuer Out und In, dann kuerzere Blende."""
    rm = rang_map if rang_map is not None else SCHEMA_RANG
    unbekannt = len(rm)
    return (-p.score, rm.get(_hauptschema(p.out_a, rm), unbekannt),
            rm.get(_hauptschema(p.in_b, rm), unbekannt), p.blend_bars)


def dedupe_and_cap(paare: list[PairCandidate], grid_a: float, grid_b: float,
                   schemata_vorhanden: set[str], rang_map: dict | None = None) -> list[PairCandidate]:
    """Schritt 4: nahe Kombinationen gleichen Schemas zusammenlegen (bester Score
    bleibt, Schemata vereinigt), Kappung auf PAAR_MAX_KOMBINATIONEN Zeitpunkt-
    Kombinationen (je bis zu 2 Blenden), mindestens eine Kombination je
    vorhandenem Schema."""
    paare = sorted(paare, key=lambda p: _sortschluessel(p, rang_map))
    # Dedupe ueber Kombinationen (ohne Blende): Vertreter = bester Score.
    vertreter: list[PairCandidate] = []
    zuordnung: dict[int, PairCandidate] = {}
    for p in paare:
        ziel = next((v for v in vertreter if _gleiche_kombination(p, v, grid_a, grid_b, rang_map)), None)
        if ziel is None:
            vertreter.append(p)
            zuordnung[id(p)] = p
        else:
            for s in p.out_a.schema:
                if s not in ziel.out_a.schema:
                    ziel.out_a.schema.append(s)
            for s in p.in_b.schema:
                if s not in ziel.in_b.schema:
                    ziel.in_b.schema.append(s)
            zuordnung[id(p)] = ziel
    kombis: list[tuple[float, float]] = []
    for v in vertreter:
        key = (v.t_out, v.t_in)
        if key not in kombis:
            kombis.append(key)
    gewaehlt = kombis[:PAAR_MAX_KOMBINATIONEN]

    def schemata_in(auswahl):
        s = set()
        for p in vertreter:
            if (p.t_out, p.t_in) in auswahl:
                s.update(p.out_a.schema)
                s.update(p.in_b.schema)
        return s

    # Schema-Garantie: fehlt ein vorhandenes Schema, ersetzt die beste Kombination
    # mit diesem Schema die schlechteste gewaehlte, deren Schemata anderweitig
    # vertreten bleiben.
    for schema in SCHEMA_PRIORITAET:
        if schema not in schemata_vorhanden or schema in schemata_in(gewaehlt):
            continue
        ersatz = next(((p.t_out, p.t_in) for p in vertreter
                       if schema in p.out_a.schema or schema in p.in_b.schema), None)
        if ersatz is None or ersatz in gewaehlt:
            continue
        if len(gewaehlt) < PAAR_MAX_KOMBINATIONEN:
            gewaehlt.append(ersatz)
            continue
        for k in reversed(gewaehlt):
            rest = [x for x in gewaehlt if x != k]
            verloren = schemata_in(gewaehlt) - schemata_in(rest + [ersatz])
            if not verloren:
                gewaehlt = rest + [ersatz]
                break
    # Dedupe-Opfer (zuordnung != p) sind raus. Je (Kombination, Blende) bleibt
    # der beste Vertreter; liegen zwei Vertreter verschiedener Hauptschemata auf
    # demselben Punkt, werden ihre Schemata vereinigt (kein Kandidat geht verloren).
    ergebnis = [p for p in paare if zuordnung[id(p)] is p and (p.t_out, p.t_in) in gewaehlt]
    je_punkt: dict[tuple[float, float, int], PairCandidate] = {}
    for p in sorted(ergebnis, key=lambda p: _sortschluessel(p, rang_map)):
        k = (p.t_out, p.t_in, p.blend_bars)
        if k in je_punkt:
            ziel = je_punkt[k]
            for s in p.out_a.schema:
                if s not in ziel.out_a.schema:
                    ziel.out_a.schema.append(s)
            for s in p.in_b.schema:
                if s not in ziel.in_b.schema:
                    ziel.in_b.schema.append(s)
            continue
        je_punkt[k] = p
    return list(je_punkt.values())


def build_pair_candidates(track_a: Track, track_b: Track, *, energy_direction=None,
                          harmonic_strictness: int = 7, allow_experimental: bool = True,
                          tolerances: dict | None = None, bass_swap_geplant: bool = False,
                          schema_rang: list[str] | None = None) -> list[PairCandidate]:
    """Schritte 1–5 der Spec: Gates, Score, Blendenlaengen, Dedupe/Kappung,
    Rang + Begruendung. Liefert [] wenn keine Kombination die Gates besteht.
    `schema_rang`: Rangfolge der Schemata (Hoertest, Teil 3) als Tiebreak bei
    gleichem Score; None = SCHEMA_PRIORITAET."""
    rang_map = {s: i for i, s in enumerate(schema_rang)} if schema_rang else None
    outs = [MixCandidate.from_dict(d) if isinstance(d, dict) else d for d in (track_a.mix_out_candidates or [])]
    ins = [MixCandidate.from_dict(d) if isinstance(d, dict) else d for d in (track_b.mix_in_candidates or [])]
    if not outs or not ins:
        return []
    _, rel = effective_bpm_diff(track_a.bpm, track_b.bpm)
    spb = seconds_per_bar(track_a.bpm)
    schemata_vorhanden: set[str] = set()
    for c in outs + ins:
        schemata_vorhanden.update(c.schema or [])
    paare: list[PairCandidate] = []
    for o in outs:
        for i in ins:
            for bars in blend_bars_options(track_a, o, rel):
                if pair_gate_reasons(track_a, track_b, o, i, bars):
                    continue
                score, teil, flags = score_pair(
                    track_a, track_b, o, i, bars, energy_direction=energy_direction,
                    harmonic_strictness=harmonic_strictness,
                    allow_experimental=allow_experimental, tolerances=tolerances,
                    bass_swap_geplant=bass_swap_geplant)
                paare.append(PairCandidate(
                    out_a=MixCandidate.from_dict(o.to_dict()), in_b=MixCandidate.from_dict(i.to_dict()),
                    blend_bars=bars, overlap_sec=bars * spb, score=score, teilwerte=teil,
                    flags=flags, begruendung=begruendung_aus_teilwerten(teil, flags, bars),
                    bpm_relation=rel))
    if not paare:
        return []
    final = dedupe_and_cap(paare, _grid_sec(track_a), _grid_sec(track_b), schemata_vorhanden, rang_map)
    for rang, p in enumerate(final, start=1):
        p.rang = rang
    return final


def rank_pair_candidates(track_a: Track, track_b: Track, *, energy_direction=None,
                         harmonic_strictness: int = 7, allow_experimental: bool = True,
                         tolerances: dict | None = None, wahl: dict | None = None) -> list[PairCandidate]:
    """Kandidaten des Paars in App-Reihenfolge (Spec Abschnitt 4): eine
    gespeicherte Wahl (candidate_choices, oder `wahl`) kommt nach vorn, sonst
    Score; Tiebreak die Schema-Rangfolge aus dem Hoertest
    (candidate_preferences), sonst SCHEMA_PRIORITAET. Flag `gespeicherte_wahl`
    auf jedem Kandidaten. bass_swap_geplant=True: die App waehlt bei
    bass_swap_pflicht den Uebergangstyp bass_swap."""
    genre_a = _genre(track_a)
    paare = build_pair_candidates(
        track_a, track_b, energy_direction=energy_direction, harmonic_strictness=harmonic_strictness,
        allow_experimental=allow_experimental, tolerances=tolerances, bass_swap_geplant=True,
        schema_rang=candidate_preferences.schema_rangfolge(genre_a) or None)
    if not paare:
        return []
    w = wahl if wahl is not None else candidate_choices.hole(track_a.filePath, track_b.filePath)
    treffer = None
    if w:
        try:
            w_out, w_in, w_bars = float(w.get("t_out", -1)), float(w.get("t_in", -1)), int(w.get("blend_bars", -1))
        except (TypeError, ValueError):
            w_out, w_in, w_bars = -1.0, -1.0, -1
        for p in paare:
            if (abs(p.t_out - w_out) <= QUANTIZE_TOLERANCE_SEC and abs(p.t_in - w_in) <= QUANTIZE_TOLERANCE_SEC
                    and int(p.blend_bars) == w_bars):
                treffer = p
                break
    for p in paare:
        p.flags["gespeicherte_wahl"] = p is treffer
    if treffer is not None:
        paare = [treffer] + [p for p in paare if p is not treffer]
    for rang, p in enumerate(paare, start=1):
        p.rang = rang
    return paare


def select_pair_candidate(track_a: Track, track_b: Track, **kw) -> PairCandidate | None:
    """Rang 1 aus rank_pair_candidates oder None."""
    paare = rank_pair_candidates(track_a, track_b, **kw)
    return paare[0] if paare else None

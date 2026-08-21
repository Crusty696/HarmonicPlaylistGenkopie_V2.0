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

import numpy as np

from .config import (
    CUE_DEDUPE_SEC, ENERGIE_NEUHEIT_MIN, ENERGIE_TREND_SCHWELLE, KANDIDATEN_AUDIO_SR,
    KANDIDATEN_FENSTER_PHRASEN, KANDIDATEN_MAX_JE_SEITE, KANDIDATEN_MIN_JE_SEITE,
    KICK_AKTIV_MIN_DBFS, KICK_AKTIV_ONBEAT_MIN, METER,
)
from .downbeat import DOWNBEAT_RELIABLE_MIN
from .groove import ON_BEAT_SLOTS, bass_kennwerte, extract_groove, syncopation_from_pattern
from .models import CAMELOT_MAP, QUANTIZE_TOLERANCE_SEC, quantize_to_grid
from .rekordbox_phrases import phrase_grid_from_phrases

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
    # Zwilling von dj_brain.section_dict_at_time (dort auf Track, hier auf rohe
    # Sektions-Dicts vor der Track-Erzeugung); bei Aenderung der Randregel
    # beide anpassen.
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
            # Tiebreak explizit ueber die Zeit (frueher = zuerst), nicht ueber
            # die Einfuegereihenfolge
            kandidaten.sort(key=lambda k: (SCHEMA_PRIORITAET.index(k.schema[0]), -len(k.schema), k.t))
            kandidaten = kandidaten[:KANDIDATEN_MAX_JE_SEITE]
        kandidaten.sort(key=lambda k: k.t)
        if 0 < len(kandidaten) < KANDIDATEN_MIN_JE_SEITE:
            logger.info("Nur %d %s-Kandidaten (Minimum %d) — Quellen reichen nicht",
                        len(kandidaten), seite, KANDIDATEN_MIN_JE_SEITE)
        ergebnis[seite] = kandidaten
    return ergebnis["in"], ergebnis["out"]


# ---------------------------------------------------------------------------
# Lokale Messung je Kandidat (Spec Abschnitt 2): Fenster +-1 Phrase um t.
# Audio wird je Kandidat frisch geladen (unabhaengig vom Head-/Tail-Fenster
# der Strukturanalyse); LUFS getrennt in nativer Samplerate/Kanalzahl.
# ---------------------------------------------------------------------------

BASS_RMS_CUTOFF_HZ = 160.0   # wie die Downbeat-Low-Frequency-Onsets (<=160 Hz)
LUFS_SHORT_TERM_SEC = 3.0    # BS.1771 Short-Term-Fenster
NEUHEIT_LAUT_DB = 20.0       # RMS-Sprung (dB) fuer vollen Lautheitsbruch; Startwert, nicht gemessen


def _lade_fenster(file_path: str, start: float, ende: float, sr: int):
    import librosa
    y, _ = librosa.load(file_path, sr=sr, mono=True, offset=max(0.0, start),
                        duration=max(0.0, ende - max(0.0, start)))
    return y


def _lufs_short_term(file_path: str, t: float, duration: float) -> float | None:
    """Short-Term-Lautheit (3-s-Block um t) in nativer Samplerate/Kanalzahl."""
    try:
        import soundfile as sf
        import pyloudnorm as pyln
        info = sf.info(file_path)
        halb = LUFS_SHORT_TERM_SEC / 2.0
        start = max(0.0, t - halb)
        ende = min(float(duration), t + halb) if duration > 0 else t + halb
        a = int(start * info.samplerate)
        b = int(ende * info.samplerate)
        if b - a < info.samplerate:
            return None
        data, sr = sf.read(file_path, start=a, stop=b, dtype="float64", always_2d=True)
        meter = pyln.Meter(sr, filter_class="DeMan")
        v = float(meter.integrated_loudness(data))
        if not np.isfinite(v) or v >= 0.0 or v < -70.0:
            return None
        return round(v, 2)
    except Exception as exc:
        logger.warning("LUFS short-term nicht messbar (%s @ %.1f s): %s", file_path, t, exc)
        return None


def _bass_rms_dbfs(y: np.ndarray, sr: int) -> float | None:
    from scipy.signal import butter, sosfiltfilt
    if y is None or len(y) < sr // 4:
        return None
    sos = butter(4, BASS_RMS_CUTOFF_HZ, btype="low", fs=sr, output="sos")
    low = sosfiltfilt(sos, np.asarray(y, dtype=float))
    rms = float(np.sqrt(np.mean(low ** 2)))
    if rms <= 0.0:
        return -120.0
    return round(20.0 * np.log10(rms), 2)


def _kick_aktiv(bass_pattern: list[float], bass_rms_dbfs: float | None) -> bool | None:
    if not bass_pattern or bass_rms_dbfs is None:
        return None
    onbeat = sum(bass_pattern[i] for i in ON_BEAT_SLOTS)
    return bool(bass_rms_dbfs >= KICK_AKTIV_MIN_DBFS and onbeat >= KICK_AKTIV_ONBEAT_MIN)


def _trend(e_vor: int, e_nach: int) -> str:
    d = e_nach - e_vor
    if d >= ENERGIE_TREND_SCHWELLE:
        return "rising"
    if d <= -ENERGIE_TREND_SCHWELLE:
        return "falling"
    return "stable"


def _cos_dist(a, b) -> float:
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    if a.size == 0 or b.size == 0 or a.size != b.size:
        return 0.0
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.clip(1.0 - float(np.dot(a, b) / (na * nb)), 0.0, 1.0))


def _rms_db(x: np.ndarray) -> float:
    return float(20.0 * np.log10(max(float(np.sqrt(np.mean(np.asarray(x, dtype=float) ** 2))), 1e-9)))


def _neuheit(y_vor, y_nach, sr, fc_vor, fc_nach) -> float | None:
    """Mittel aus vier normierten Spruengen vor/nach t:
    rhythmus (Onset-Dichte je Sekunde, relativ), laut (RMS-Sprung in dB,
    NEUHEIT_LAUT_DB = voller Bruch), timbre (Kosinus-Distanz MFCC ohne
    Koeffizient 0 — der misst Lautheit und dominiert sonst, siehe
    dj_brain._calculate_texture_similarity), harm (Kosinus-Distanz Chroma).
    0 = nichts passiert, 1 = maximaler Bruch."""
    import librosa
    from .analysis import generate_timbre_fingerprint
    if y_vor is None or y_nach is None or len(y_vor) < sr or len(y_nach) < sr:
        return None
    d_v = len(librosa.onset.onset_detect(y=y_vor, sr=sr, units="frames")) / (len(y_vor) / sr)
    d_n = len(librosa.onset.onset_detect(y=y_nach, sr=sr, units="frames")) / (len(y_nach) / sr)
    rhythmus = abs(d_n - d_v) / max(d_n, d_v, 1e-9)
    laut = float(np.clip(abs(_rms_db(y_nach) - _rms_db(y_vor)) / NEUHEIT_LAUT_DB, 0.0, 1.0))
    fp_v = generate_timbre_fingerprint(y_vor, sr, fc_vor)
    fp_n = generate_timbre_fingerprint(y_nach, sr, fc_nach)
    timbre = _cos_dist(fp_v[1:], fp_n[1:]) if len(fp_v) > 1 and len(fp_n) > 1 else 0.0
    harm = _cos_dist(np.mean(fc_vor.get_chroma(), axis=1), np.mean(fc_nach.get_chroma(), axis=1))
    return round(float(np.clip(np.mean([rhythmus, laut, timbre, harm]), 0.0, 1.0)), 3)


def measure_candidate_window(file_path: str, cand: MixCandidate, *, bpm: float, first_downbeat: float,
                             downbeat_confidence: float, grid_sec: float, duration: float,
                             sections: list[dict], pssi_mood: int | None = None) -> MixCandidate:
    """Fuellt die lokalen Messwerte eines Kandidaten (Fenster +-1 Phrase).
    Fehler einzelner Messungen lassen das Feld auf None; die Analyse kippt nie."""
    # Lazy-Import: analysis importiert dieses Modul (Importzyklus vermeiden).
    from .analysis import (
        FeatureCache, analyze_frequency_bands, analyze_rhythm_complexity, calculate_brightness,
        calculate_energy, detect_vocal_instrumental, generate_timbre_fingerprint,
        get_key_with_confidence, key_confidence_score,
    )
    sr = KANDIDATEN_AUDIO_SR
    w = grid_sec * KANDIDATEN_FENSTER_PHRASEN
    start, ende = max(0.0, cand.t - w), min(duration, cand.t + w)
    try:
        y = _lade_fenster(file_path, start, ende, sr)
    except Exception as exc:
        logger.warning("Kandidatenfenster nicht ladbar (%s @ %.1f s): %s", file_path, cand.t, exc)
        return cand
    if y is None or len(y) < sr:
        return cand
    fc = FeatureCache(y, sr)
    split = int((cand.t - start) * sr)
    y_vor, y_nach = y[:split], y[split:]
    try:
        cand.energy_lokal = calculate_energy(y)
        e_vor = calculate_energy(y_vor) if len(y_vor) else cand.energy_lokal
        e_nach = calculate_energy(y_nach) if len(y_nach) else cand.energy_lokal
        cand.energy_trend = _trend(e_vor, e_nach)
    except Exception as exc:
        logger.warning("Energie lokal: %s", exc)
    try:
        b, m, h = analyze_frequency_bands(y, sr, fc)
        cand.avg_mids_lokal, cand.avg_highs_lokal = round(m, 3), round(h, 3)
        pr, flat = analyze_rhythm_complexity(y, sr, fc)
        cand.percussive_ratio_lokal, cand.flatness_lokal = round(pr, 4), round(flat, 4)
        cand.brightness_lokal = calculate_brightness(y, sr, fc)
        cand.timbre_fingerprint_lokal = generate_timbre_fingerprint(y, sr, fc)
        cand.vocal_aktiv_lokal = detect_vocal_instrumental(y, sr, fc) == "vocal"
    except Exception as exc:
        logger.warning("Klangfarbe lokal: %s", exc)
    cand.mood = {"pssi_mood": pssi_mood}   # bleibt auch bei Harmonie-Fehler erhalten
    try:
        chroma_vec = np.mean(fc.get_chroma(), axis=1)
        note, mode, strength, margin, n2, m2 = get_key_with_confidence(chroma_vec)
        cand.camelot_lokal = CAMELOT_MAP.get((note, mode), "")
        cand.key_confidence_lokal = round(key_confidence_score(strength, margin, note, mode, n2, m2), 3)
        cand.mood.update({"brightness": cand.brightness_lokal, "flatness": cand.flatness_lokal,
                          "key_mode": mode})
    except Exception as exc:
        logger.warning("Harmonie lokal: %s", exc)
    try:
        cand.bass_rms_dbfs = _bass_rms_dbfs(y, sr)
        sub, punch = bass_kennwerte(y, sr)
        cand.sub_energy, cand.bass_punch = round(sub, 4), round(punch, 4)
        if downbeat_confidence >= DOWNBEAT_RELIABLE_MIN and bpm > 0:
            g = extract_groove(y, sr, bpm, first_downbeat - start, feature_cache=fc)
            cand.groove_pattern_lokal = g.groove_pattern
            cand.bass_pattern_lokal = g.bass_pattern
            cand.syncopation_lokal = round(syncopation_from_pattern(g.bass_pattern or g.groove_pattern), 4)
            cand.kick_aktiv = _kick_aktiv(g.bass_pattern, cand.bass_rms_dbfs)
            # traegt_allein: Kick + Bass NACH t aktiv
            if len(y_nach) >= sr:
                g_n = extract_groove(y_nach, sr, bpm, first_downbeat - cand.t, feature_cache=None)
                cand.traegt_allein = _kick_aktiv(g_n.bass_pattern, _bass_rms_dbfs(y_nach, sr))
                if cand.traegt_allein is None:
                    cand.traegt_allein = False
    except Exception as exc:
        logger.warning("Bass/Groove lokal: %s", exc)
    try:
        fc_v = FeatureCache(y_vor, sr) if len(y_vor) >= sr else None
        fc_n = FeatureCache(y_nach, sr) if len(y_nach) >= sr else None
        if fc_v is not None and fc_n is not None:
            cand.neuheit = _neuheit(y_vor, y_nach, sr, fc_v, fc_n)
    except Exception as exc:
        logger.warning("Neuheit lokal: %s", exc)
    cand.lufs_lokal = _lufs_short_term(file_path, cand.t, duration)
    return cand


def candidate_confidence(*, downbeat_confidence: float, pssi_grid: bool, phrase_confidence: float,
                         key_confidence_lokal: float | None, covered: bool) -> float:
    """Mittel der verfuegbaren Teilkonfidenzen (Spec: downbeat, phrase, key,
    Coverage). Das gleichgewichtete Mittel ist ein STARTWERT, nicht gemessen."""
    teile = [float(downbeat_confidence), 1.0 if pssi_grid else float(phrase_confidence),
             1.0 if covered else 0.0]
    if key_confidence_lokal is not None:
        teile.append(float(key_confidence_lokal))
    return round(float(np.clip(np.mean(teile), 0.0, 1.0)), 3)


def build_track_candidates(file_path: str, *, bpm: float, duration: float, first_downbeat: float,
                           downbeat_confidence: float, phrase_confidence: float, phrase_anchor: float,
                           phrase_unit: int, sections: list[dict], phrases: list[dict], cues: list[dict],
                           analyzer_in: float | None, analyzer_out: float | None, outro_covered: bool,
                           ) -> tuple[list[dict], list[dict]]:
    """Vollstaendige Kandidaten beider Seiten als Dict-Listen (fuer Track/Cache)."""
    # Lazy nur aus Konsistenz mit dem analysis-Import; dj_brain importiert weder
    # analysis noch mix_candidates (kein Zyklus).
    from .dj_brain import _get_intro_end_from_sections, _get_outro_start_from_sections
    if bpm <= 0 or duration <= 0:
        return [], []
    grid_sec = (60.0 / bpm) * METER * (phrase_unit if phrase_unit > 0 else 8)
    seite_grid = phrase_grid_from_phrases(phrases)
    intro_end = _get_intro_end_from_sections(sections)
    outro_start = _get_outro_start_from_sections(sections, duration)
    ins, outs = collect_candidate_times(
        seite_grid=seite_grid, sections=sections, phrases=phrases, cues=cues,
        analyzer_in=analyzer_in, analyzer_out=analyzer_out, duration=duration, grid_sec=grid_sec,
        intro_end=intro_end, outro_start=outro_start, outro_covered=outro_covered, anchor=phrase_anchor,
    )
    for cand in ins + outs:
        measure_candidate_window(file_path, cand, bpm=bpm, first_downbeat=first_downbeat,
                                 downbeat_confidence=downbeat_confidence, grid_sec=grid_sec,
                                 duration=duration, sections=sections,
                                 pssi_mood=int(phrases[0]["mood"]) if phrases else None)
        sek = _section_at(sections, cand.t)
        # Coverage: die `unanalysed`-Sektionen SIND die Luecken aus
        # analyze_structure_windows (Head 360 s / Tail 180 s); Out-Kandidaten
        # ohne outro_covered entstehen in collect_candidate_times gar nicht erst.
        covered = sek is not None and sek.get("label") != "unanalysed"
        cand.confidence = candidate_confidence(
            downbeat_confidence=downbeat_confidence, pssi_grid=bool(seite_grid),
            phrase_confidence=phrase_confidence, key_confidence_lokal=cand.key_confidence_lokal, covered=covered)
    return [c.to_dict() for c in ins], [c.to_dict() for c in outs]

"""Paarung und Bewertung von Mixpunkt-Kandidaten (Spec 2026-08-21, Abschnitt 2).

Eingabe: Track A (`mix_out_candidates`), Track B (`mix_in_candidates`).
Ausgabe: sortierte `PairCandidate`s (Zeitpunkt-Kombination x Blendenlaenge)
mit Gates, Score aus allen Faktoren lokal an der Naht, Teilwerten, Flags und
Begruendung. Reine Funktionen, kein Audio. Teil 4 bindet das Ergebnis an
Scoring, GUI und Export an; hier wird nichts am Track veraendert.
"""
from __future__ import annotations

import copy
import logging
import math
import unicodedata
from dataclasses import asdict, dataclass, field, fields

from . import candidate_choices, candidate_preferences
from .config import (
    BASS_RMS_DELTA_MAX_DB, BPM_HALF_DOUBLE_PENALTY, ENERGIE_TREND_WIDERSPRUCH,
    KICK_KONFLIKT_ABZUG, LUFS_DELTA_MAX_DB, MIDS_HIGHS_DELTA_MAX, MIN_TRANSITION_BARS,
    MAX_TRANSITION_OVERLAP_SECONDS,
    PAAR_BPM_MAX, PAAR_BPM_SKALA, PAAR_HALF_DOUBLE_MAX_BARS, PAAR_MAX_KOMBINATIONEN,
    PAAR_MIN_LOCAL_GROOVE, PAAR_MIN_LOCAL_SCORE, PAAR_PITCH_MAX, PERCUSSIVE_ABZUG,
    PERCUSSIVE_HOCH, PERCUSSIVE_NIEDRIG, PSSI_MOOD_ABZUG,
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
from .genres import CANONICAL_GENRES
from .models import (
    QUANTIZE_TOLERANCE_SEC, Track,
    camelot_relation_score, effective_bpm_diff, get_camelot_components,
    quantize_to_grid, seconds_per_bar,
)
from .tolerances import get_tolerances
from .transition_features import (
    BASS_PATTERN_SHARE, DEFAULT_BRIGHTNESS_DELTA_MAX, DEFAULT_FLATNESS_DELTA_MAX,
    DEFAULT_GROOVE_SIM_FLOOR, DEFAULT_PUNCH_DELTA_MAX, DEFAULT_SUB_DELTA_MAX,
    MODE_SWITCH_PENALTY, _normiert, _spreize, cosine_similarity,
)

logger = logging.getLogger(__name__)

# Reihenfolge der Faktoren = Reihenfolge in Teilwerten/Begruendung.
FAKTOREN = ("harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre",
            "mood", "loudness", "structure")
SCHEMA_RANG = {s: i for i, s in enumerate(SCHEMA_PRIORITAET)}
WAHL_AUDIT_ABS_TOLERANCE = 1e-6


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


def _nfc(value: object) -> str:
    return unicodedata.normalize("NFC", str(value))


def _freeze_flag_value(value):
    """Friert Flag-Werte auf den kleinen, serialisierbaren Result-Vertrag ein."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("CandidateSnapshot-Flag muss endlich sein")
        return value
    if isinstance(value, str):
        return _nfc(value)
    if isinstance(value, dict):
        return tuple(
            (_nfc(key), _freeze_flag_value(item))
            for key, item in sorted(value.items(), key=lambda pair: _nfc(pair[0]))
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_flag_value(item) for item in value)
    raise ValueError(f"CandidateSnapshot-Flagtyp nicht unterstuetzt: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class CandidateSnapshot:
    """Tief unveraenderlicher, laufstabiler Blick auf einen PairCandidate."""

    original_ordinal: int
    key: tuple
    t_out: float
    t_in: float
    blend_bars: int
    overlap_sec: float
    score: float
    teilwerte: tuple[tuple[str, float | None], ...]
    flags: tuple[tuple[str, object], ...]
    begruendung: str
    rang: int
    bpm_relation: str
    out_schemas: tuple[str, ...]
    in_schemas: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.original_ordinal, bool)
            or not isinstance(self.original_ordinal, int)
            or self.original_ordinal < 0
        ):
            raise ValueError("original_ordinal muss eine nichtnegative ganze Zahl sein")
        for name, value in (("t_out", self.t_out), ("t_in", self.t_in)):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{name} muss eine echte Zahl sein")
            if not math.isfinite(float(value)) or float(value) < 0.0:
                raise ValueError(f"{name} muss endlich und nichtnegativ sein")
        if (
            not isinstance(self.overlap_sec, (int, float))
            or isinstance(self.overlap_sec, bool)
            or not math.isfinite(float(self.overlap_sec))
            or not 0.0 < float(self.overlap_sec) <= MAX_TRANSITION_OVERLAP_SECONDS
        ):
            raise ValueError("overlap_sec muss endlich, positiv und hoechstens 64 sein")
        if (
            not isinstance(self.score, (int, float))
            or isinstance(self.score, bool)
            or not math.isfinite(float(self.score))
        ):
            raise ValueError("score muss endlich sein")
        if isinstance(self.blend_bars, bool) or not isinstance(self.blend_bars, int):
            raise ValueError("blend_bars muss eine ganze Zahl sein")
        if not isinstance(self.teilwerte, tuple) or not isinstance(self.flags, tuple):
            raise ValueError("teilwerte und flags muessen unveraenderliche Tupel sein")
        for name, value in self.teilwerte:
            if not isinstance(name, str) or name != _nfc(name):
                raise ValueError("Teilwertnamen muessen NFC-Strings sein")
            if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
            ):
                raise ValueError(f"Teilwert {name} muss endlich oder None sein")
        if not all(
            isinstance(name, str) and name == _nfc(name)
            for name, _value in self.flags
        ):
            raise ValueError("Flagnamen muessen NFC-Strings sein")
        for name, value in self.flags:
            if _freeze_flag_value(value) != value:
                raise ValueError(f"Flag {name} ist nicht tief unveraenderlich")
        if (
            not isinstance(self.out_schemas, tuple)
            or not isinstance(self.in_schemas, tuple)
            or any(value != _nfc(value) for value in (*self.out_schemas, *self.in_schemas))
        ):
            raise ValueError("Schemata muessen NFC-Tupel sein")
        if self.bpm_relation != _nfc(self.bpm_relation) or self.begruendung != _nfc(self.begruendung):
            raise ValueError("Textfelder muessen NFC-normalisiert sein")

        def quantize(value: float) -> int:
            return int(math.floor(float(value) / QUANTIZE_TOLERANCE_SEC + 0.5))

        expected_key = (
            quantize(self.t_out),
            quantize(self.t_in),
            self.blend_bars,
            self.bpm_relation,
            self.out_schemas,
            self.in_schemas,
            self.original_ordinal,
        )
        if self.key != expected_key:
            raise ValueError("CandidateSnapshot.key ist nicht kanonisch")

    @classmethod
    def from_pair_candidate(
        cls, kandidat: PairCandidate, *, original_ordinal: int
    ) -> "CandidateSnapshot":
        if isinstance(original_ordinal, bool) or not isinstance(original_ordinal, int):
            raise ValueError("original_ordinal muss eine ganze Zahl sein")
        if original_ordinal < 0:
            raise ValueError("original_ordinal darf nicht negativ sein")
        try:
            t_out = float(kandidat.t_out)
            t_in = float(kandidat.t_in)
            overlap = float(kandidat.overlap_sec)
            score = float(kandidat.score)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("CandidateSnapshot-Zahlen sind ungueltig") from exc
        if not math.isfinite(t_out) or t_out < 0.0:
            raise ValueError("t_out muss endlich und nichtnegativ sein")
        if not math.isfinite(t_in) or t_in < 0.0:
            raise ValueError("t_in muss endlich und nichtnegativ sein")
        if not math.isfinite(overlap) or not 0.0 < overlap <= MAX_TRANSITION_OVERLAP_SECONDS:
            raise ValueError("overlap_sec muss endlich, positiv und hoechstens 64 sein")
        if not math.isfinite(score):
            raise ValueError("score muss endlich sein")
        blend_bars = kandidat.blend_bars
        if isinstance(blend_bars, bool) or not isinstance(blend_bars, int):
            raise ValueError("blend_bars muss eine ganze Zahl sein")

        teilwerte: list[tuple[str, float | None]] = []
        for name, value in sorted((kandidat.teilwerte or {}).items()):
            frozen_name = _nfc(name)
            if value is None:
                teilwerte.append((frozen_name, None))
                continue
            try:
                number = float(value)
            except (OverflowError, TypeError, ValueError) as exc:
                raise ValueError(f"Teilwert {frozen_name} ist ungueltig") from exc
            if not math.isfinite(number):
                raise ValueError(f"Teilwert {frozen_name} muss endlich sein")
            teilwerte.append((frozen_name, number))

        flags = tuple(
            (_nfc(name), _freeze_flag_value(value))
            for name, value in sorted((kandidat.flags or {}).items())
        )
        out_schemas = tuple(_nfc(value) for value in (kandidat.out_a.schema or ()))
        in_schemas = tuple(_nfc(value) for value in (kandidat.in_b.schema or ()))
        bpm_relation = _nfc(kandidat.bpm_relation)

        def quantize(value: float) -> int:
            return int(math.floor(value / QUANTIZE_TOLERANCE_SEC + 0.5))

        key = (
            quantize(t_out),
            quantize(t_in),
            blend_bars,
            bpm_relation,
            out_schemas,
            in_schemas,
            original_ordinal,
        )
        return cls(
            original_ordinal=original_ordinal,
            key=key,
            t_out=t_out,
            t_in=t_in,
            blend_bars=blend_bars,
            overlap_sec=overlap,
            score=score,
            teilwerte=tuple(teilwerte),
            flags=flags,
            begruendung=_nfc(kandidat.begruendung),
            rang=int(kandidat.rang),
            bpm_relation=bpm_relation,
            out_schemas=out_schemas,
            in_schemas=in_schemas,
        )

    @classmethod
    def from_candidate(
        cls, kandidat: PairCandidate, *, original_ordinal: int
    ) -> "CandidateSnapshot":
        """Kompatibilitaetsalias fuer fruehe V6-Prototyp-Aufrufer."""
        return cls.from_pair_candidate(
            kandidat, original_ordinal=original_ordinal
        )

    def teilwerte_dict(self) -> dict[str, float | None]:
        return dict(self.teilwerte)

    def flags_dict(self) -> dict[str, object]:
        return dict(self.flags)

    def to_dict(self) -> dict:
        """Defensive Legacy-Sicht; nie Teil des unveraenderlichen Results."""
        return {
            "candidate_key": self.key,
            "t_out": self.t_out,
            "t_in": self.t_in,
            "blend_bars": self.blend_bars,
            "overlap_sec": self.overlap_sec,
            "score": self.score,
            "teilwerte": dict(self.teilwerte),
            "flags": dict(self.flags),
            "begruendung": self.begruendung,
            "rang": self.rang,
            "bpm_relation": self.bpm_relation,
            "out_a": {"schema": list(self.out_schemas)},
            "in_b": {"schema": list(self.in_schemas)},
            "out_schemas": list(self.out_schemas),
            "in_schemas": list(self.in_schemas),
        }


def pair_quality_reasons(
    score: float, teilwerte: dict, kandidat: PairCandidate | None = None
) -> list[str]:
    """Gruende, warum ein lokales Paar nicht vollwertig bewertbar ist."""
    gruende: list[str] = []
    for faktor in FAKTOREN:
        wert = teilwerte.get(faktor)
        try:
            messbar = wert is not None and math.isfinite(float(wert))
        except (TypeError, ValueError):
            messbar = False
        if not messbar or not 0.0 <= float(wert) <= 1.0:
            gruende.append(f"faktor_fehlt:{faktor}")

    if kandidat is not None:
        a, b = kandidat.out_a, kandidat.in_b

        def endlich(*werte) -> bool:
            try:
                return all(v is not None and math.isfinite(float(v)) for v in werte)
            except (TypeError, ValueError):
                return False

        def normiert(*werte) -> bool:
            return endlich(*werte) and all(0.0 <= float(v) <= 1.0 for v in werte)

        raw_ok = {
            "harmonic": (
                get_camelot_components(a.camelot_lokal)[0] != 0
                and get_camelot_components(b.camelot_lokal)[0] != 0
                and normiert(a.key_confidence_lokal, b.key_confidence_lokal)
            ),
            "energy": endlich(a.energy_lokal, b.energy_lokal),
            "groove": (
                bool(a.groove_pattern_lokal and b.groove_pattern_lokal)
                or bool(a.bass_pattern_lokal and b.bass_pattern_lokal)
            ),
            "bass": (
                (endlich(a.sub_energy, b.sub_energy) or endlich(a.bass_punch, b.bass_punch))
                and isinstance(a.kick_aktiv, bool) and isinstance(b.kick_aktiv, bool)
            ),
            "timbre": (
                bool(a.timbre_fingerprint_lokal and b.timbre_fingerprint_lokal)
                and endlich(*(list(a.timbre_fingerprint_lokal) + list(b.timbre_fingerprint_lokal)))
            ),
            "mood": (
                endlich((a.mood or {}).get("brightness", a.brightness_lokal),
                        (b.mood or {}).get("brightness", b.brightness_lokal))
                or endlich((a.mood or {}).get("flatness", a.flatness_lokal),
                           (b.mood or {}).get("flatness", b.flatness_lokal))
            ),
            "loudness": endlich(a.lufs_lokal, b.lufs_lokal),
            "structure": (
                normiert(a.neuheit, b.neuheit)
                and isinstance(a.traegt_allein, bool)
                and isinstance(b.traegt_allein, bool)
            ),
            "vocals": isinstance(a.vocal_aktiv_lokal, bool)
                      and isinstance(b.vocal_aktiv_lokal, bool),
        }
        for faktor, gueltig in raw_ok.items():
            if not gueltig:
                gruende.append(f"quellmessung_fehlt:{faktor}")

        for name, werte in (
            ("groove_pattern", list(a.groove_pattern_lokal or []) + list(b.groove_pattern_lokal or [])),
            ("bass_pattern", list(a.bass_pattern_lokal or []) + list(b.bass_pattern_lokal or [])),
            ("syncopation", [v for v in (a.syncopation_lokal, b.syncopation_lokal) if v is not None]),
            ("percussive_ratio", [v for v in (a.percussive_ratio_lokal, b.percussive_ratio_lokal) if v is not None]),
            ("sub_energy", [v for v in (a.sub_energy, b.sub_energy) if v is not None]),
            ("flatness", [v for v in (a.flatness_lokal, b.flatness_lokal) if v is not None]),
        ):
            if werte and not normiert(*werte):
                gruende.append(f"quellmessung_ungueltig:{name}")

        # Optionale Enhancer werden nur dann geprueft, wenn die jeweilige
        # Teilfunktion sie tatsaechlich paarweise verwendet.
        for name, werte in (
            ("bass_punch", (a.bass_punch, b.bass_punch)),
            ("bass_rms_dbfs", (a.bass_rms_dbfs, b.bass_rms_dbfs)),
            ("avg_mids_lokal", (a.avg_mids_lokal, b.avg_mids_lokal)),
            ("avg_highs_lokal", (a.avg_highs_lokal, b.avg_highs_lokal)),
        ):
            if all(v is not None for v in werte) and not endlich(*werte):
                gruende.append(f"quellmessung_ungueltig:{name}")

        mood_hell = (
            (a.mood or {}).get("brightness", a.brightness_lokal),
            (b.mood or {}).get("brightness", b.brightness_lokal),
        )
        mood_flach = (
            (a.mood or {}).get("flatness", a.flatness_lokal),
            (b.mood or {}).get("flatness", b.flatness_lokal),
        )
        if all(v is not None for v in mood_hell) and not endlich(*mood_hell):
            gruende.append("quellmessung_ungueltig:brightness")
        if all(v is not None for v in mood_flach) and not normiert(*mood_flach):
            gruende.append("quellmessung_ungueltig:flatness")

    groove = teilwerte.get("groove")
    try:
        if groove is not None and math.isfinite(float(groove)) and float(groove) < PAAR_MIN_LOCAL_GROOVE:
            gruende.append("groove_zu_niedrig")
    except (TypeError, ValueError):
        pass

    try:
        score_gueltig = (
            math.isfinite(float(score))
            and PAAR_MIN_LOCAL_SCORE <= float(score) <= 1.0
        )
    except (TypeError, ValueError):
        score_gueltig = False
    if not score_gueltig:
        gruende.append("lokaler_score_zu_niedrig")
    return gruende


def _genre(track: Track) -> str:
    # Lazy: playlist importiert (ab Teil 4) dieses Modul — kein Importzyklus.
    from .playlist import _resolve_track_genre
    return _resolve_track_genre(track)


def _grid_sec(track: Track) -> float:
    unit = int(track.phrase_unit) if track.phrase_unit else get_mix_profile(_genre(track)).phrase_unit
    return seconds_per_bar(track.bpm) * unit


def _ist_benannter_cue(track: Track, cand: MixCandidate, seite: str) -> bool:
    """Erkennt einen gerichteten manuellen Cue nur fuer Herkunftsdiagnose."""
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


def _section_label_at(track: Track, t: float) -> str | None:
    """Autoritatives Section-Label am Zeitpunkt; unvollstaendige Daten sperren."""
    try:
        zeit = float(t)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(zeit):
        return None
    sections = track.sections or []
    for index, section in enumerate(sections):
        try:
            start = float(section["start_time"])
            end = float(section["end_time"])
        except (KeyError, TypeError, ValueError):
            return None
        if not math.isfinite(start) or not math.isfinite(end) or end < start:
            return None
        is_last = index == len(sections) - 1
        if start <= zeit < end or (is_last and zeit == end):
            label = section.get("label")
            return label if isinstance(label, str) and label else None
    return None


def _analysis_covers(track: Track, t: float) -> bool:
    """Nur explizite, gueltige Analysefenster decken einen Zeitpunkt ab."""
    try:
        zeit = float(t)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(zeit):
        return False
    covered = False
    for window in track.analysis_coverage or []:
        try:
            start = float(window["start"])
            end = float(window["end"])
        except (KeyError, TypeError, ValueError):
            return False
        if not math.isfinite(start) or not math.isfinite(end) or start > end:
            return False
        covered = covered or start <= zeit <= end
    return covered


def _candidate_context(track: Track, t: float) -> tuple[bool, str | None]:
    """Coverage und Section stammen immer vom Track, nie vom Kandidaten-Snapshot."""
    label = _section_label_at(track, t)
    covered = _analysis_covers(track, t) and label not in (None, "unanalysed")
    return covered, label


def _outro_deckel(track_a: Track, out_a: MixCandidate) -> float:
    """Spaetestes Blendenende ist immer der Beginn des Outros."""
    return _get_outro_start_from_sections(track_a.sections, float(track_a.duration))


def _gate_gruende_basis(track_a: Track, track_b: Track, out_a: MixCandidate,
                        in_b: MixCandidate) -> list[str]:
    """Blenden-unabhaengige Gate-Gruende einer Kombination (einmal je (out, in))."""
    reasons: list[str] = []
    diff, rel = effective_bpm_diff(track_a.bpm, track_b.bpm)
    if diff > PAAR_BPM_MAX:
        reasons.append("bpm")
    if track_a.bpm > 0 and diff / track_a.bpm > PAAR_PITCH_MAX:
        reasons.append("pitch")
    out_covered, _out_label = _candidate_context(track_a, out_a.t)
    in_covered, _in_label = _candidate_context(track_b, in_b.t)
    if not out_covered or not in_covered:
        reasons.append("coverage")
    if not track_a.outro_covered:
        reasons.append("outro_covered")
    outro_start = _get_outro_start_from_sections(track_a.sections, float(track_a.duration))
    if out_a.t >= outro_start - QUANTIZE_TOLERANCE_SEC:
        reasons.append("out_im_outro")
    intro_end = _get_intro_end_from_sections(track_b.sections)
    if in_b.t <= intro_end + QUANTIZE_TOLERANCE_SEC:
        reasons.append("in_im_intro")
    if in_b.t < 0.0 or in_b.t > float(track_b.duration):
        reasons.append("in_ausserhalb")
    if not _auf_gitter(track_a, out_a.t, "out"):
        reasons.append("gitter_out")
    if not _auf_gitter(track_b, in_b.t, "in"):
        reasons.append("gitter_in")
    return reasons


def _blenden_gate(track_a: Track, out_a: MixCandidate, blend_bars: int, deckel: float | None = None) -> bool:
    """True, wenn die Blende ueber den effektiven Outro-Deckel hinauslaeuft."""
    spb = seconds_per_bar(track_a.bpm)
    if deckel is None:
        deckel = _outro_deckel(track_a, out_a)
    return out_a.t + blend_bars * spb > deckel + QUANTIZE_TOLERANCE_SEC


def _blende_passt_in_b(track_b: Track, in_b: MixCandidate, blend_bars: int, spb_a: float) -> bool:
    """Die Blende laeuft ab in_b in Track B; sie muss vor dem Trackende von B
    enden (Renderer/Playlist-Clamp: Rest von B = duration_b - in_b). Ohne
    dieses Gate kuerzt der Playlist-Clamp die Blende still (gemessen 2026-08-22:
    27 von 220 Paaren)."""
    return in_b.t + blend_bars * spb_a <= float(track_b.duration) + QUANTIZE_TOLERANCE_SEC


def pair_gate_reasons(track_a: Track, track_b: Track, out_a: MixCandidate,
                      in_b: MixCandidate, blend_bars: int) -> list[str]:
    """Harte Gates auf Paar-Ebene (Spec Abschnitt 2, Schritt 1). Leere Liste =
    Kombination erlaubt; sonst die Gruende (stabil benannt, fuer Messung).
    Reihenfolge der Gruende: bpm, pitch, coverage, outro_covered, blende_im_outro,
    blende_ueber_b_ende, in_im_intro, in_ausserhalb, gitter_out, gitter_in."""
    basis = _gate_gruende_basis(track_a, track_b, out_a, in_b)
    reasons: list[str] = [
        g for g in basis
        if g in ("bpm", "pitch", "coverage", "outro_covered", "out_im_outro")
    ]
    if _blenden_gate(track_a, out_a, blend_bars):
        reasons.append("blende_im_outro")
    if not _blende_passt_in_b(track_b, in_b, blend_bars, seconds_per_bar(track_a.bpm)):
        reasons.append("blende_ueber_b_ende")
    reasons += [g for g in basis if g in ("in_im_intro", "in_ausserhalb", "gitter_out", "gitter_in")]
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


def _teil_genre(genre_a: str, genre_b: str) -> float | None:
    if genre_a not in CANONICAL_GENRES or genre_b not in CANONICAL_GENRES:
        return None
    return get_genre_compatibility(genre_a, genre_b)


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


def _teil_struktur(out_a: MixCandidate, in_b: MixCandidate,
                   out_section_label: str | None,
                   in_section_label: str | None) -> float | None:
    if (out_a.neuheit is None or in_b.neuheit is None
            or not isinstance(out_a.traegt_allein, bool)
            or not isinstance(in_b.traegt_allein, bool)):
        return None
    # Gerichteter Handoff: A soll an der Naht loslassen, B soll uebernehmen.
    wert = sum((
        float(out_a.neuheit),
        float(in_b.neuheit),
        1.0 if not out_a.traegt_allein else 0.0,
        1.0 if in_b.traegt_allein else 0.0,
    )) / 4.0
    aus_out = out_section_label in _OUT_LABELS or out_a.phrase_label in _OUT_LABELS
    in_in = in_section_label in _IN_LABELS or in_b.phrase_label in _IN_LABELS
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
    if explizit:
        erwartet = {f"kandidaten_{f}_weight" for f in FAKTOREN}
        vorhanden = {
            key for key in quelle
            if isinstance(key, str)
            and key.startswith("kandidaten_")
            and key.endswith("_weight")
        }
        if vorhanden != erwartet:
            raise ValueError("Explizite Kandidatengewichtsgruppe ist nicht exakt vollstaendig")
        rohwerte = {key: quelle[key] for key in erwartet}
        if any(
            type(wert) not in (int, float)
            or not math.isfinite(wert)
            or not 0.0 <= wert <= 1.0
            for wert in rohwerte.values()
        ):
            raise ValueError("Explizite Kandidatengewichte muessen endliche Zahlen in 0..1 sein")
        if not math.isclose(
            sum(rohwerte.values()), 1.0, rel_tol=0.0, abs_tol=1e-6
        ):
            raise ValueError("Explizite Kandidatengewichte muessen sich auf 1 summieren")
    return {f: float(quelle[f"kandidaten_{f}_weight"]) for f in FAKTOREN}


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
    _out_covered, out_section_label = _candidate_context(track_a, out_a.t)
    _in_covered, in_section_label = _candidate_context(track_b, in_b.t)
    flags = {"half_double": rel != "direct", "bass_swap_pflicht": False,
             "lange_blende_erlaubt": False,
             "benannter_cue": _ist_benannter_cue(track_a, out_a, "out") or _ist_benannter_cue(track_b, in_b, "in")}
    teil = {
        "harmonic": _teil_harmonie(out_a, in_b, harmonic_strictness=harmonic_strictness,
                                   allow_experimental=allow_experimental),
        "bpm": _teil_bpm(diff),
        "energy": _teil_energie(out_a, in_b, richtung),
        "genre": _teil_genre(genre_a, genre_b),
        "groove": _teil_groove(out_a, in_b, tol, flags),
        "bass": _teil_bass(out_a, in_b, tol, flags, bass_swap_geplant),
        "timbre": _teil_timbre(out_a, in_b),
        "mood": _teil_mood(out_a, in_b, tol),
        "loudness": _teil_lautheit(out_a, in_b),
        "structure": _teil_struktur(
            out_a, in_b, out_section_label, in_section_label
        ),
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
    try:
        bpm_gueltig = all(
            math.isfinite(float(track.bpm)) and float(track.bpm) > 0.0
            for track in (track_a, track_b)
        )
    except (TypeError, ValueError):
        bpm_gueltig = False
    if not bpm_gueltig:
        return []
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
    # Laufzeit (gemessen 2026-08-22: ~9 ms je Paar bei 128 Kombinationen): der
    # Score haengt nicht von der Blende ab (Docstring score_pair), die Gates nur
    # ueber blende_im_outro — deshalb je (out, in) EINMAL Gates + Score, dann die
    # Blendenlaengen; Gitter/Guard je Kandidat einmal. Ergebnis identisch.
    out_context = {id(o): _candidate_context(track_a, o.t) for o in outs}
    in_context = {id(i): _candidate_context(track_b, i.t) for i in ins}
    out_ok = {id(o): _auf_gitter(track_a, o.t, "out") for o in outs}
    in_ok = {id(i): _auf_gitter(track_b, i.t, "in") for i in ins}
    intro_end_b = _get_intro_end_from_sections(track_b.sections)
    diff, _rel = effective_bpm_diff(track_a.bpm, track_b.bpm)
    basis_global = (
        diff > PAAR_BPM_MAX
        or (track_a.bpm > 0 and diff / track_a.bpm > PAAR_PITCH_MAX)
        or not track_a.outro_covered
    )
    if basis_global:
        return []
    outro_start_a = _get_outro_start_from_sections(
        track_a.sections, float(track_a.duration)
    )
    for o in outs:
        out_covered, out_section_label = out_context[id(o)]
        if not out_covered or not out_ok[id(o)]:
            continue
        if o.t >= outro_start_a - QUANTIZE_TOLERANCE_SEC:
            continue
        deckel = _outro_deckel(track_a, o)
        bars_liste = blend_bars_options(track_a, o, rel)
        if not bars_liste:
            continue
        for i in ins:
            in_covered, in_section_label = in_context[id(i)]
            if not in_covered or not in_ok[id(i)]:
                continue
            if i.t < 0.0 or i.t > float(track_b.duration):
                continue
            if i.t <= intro_end_b + QUANTIZE_TOLERANCE_SEC:
                continue
            bars_ok = [
                b for b in bars_liste
                if math.isfinite(b * spb)
                and 0.0 < b * spb <= MAX_TRANSITION_OVERLAP_SECONDS
                and not _blenden_gate(track_a, o, b, deckel)
                and _blende_passt_in_b(track_b, i, b, spb)
            ]
            if not bars_ok:
                continue
            score, teil, flags = score_pair(
                track_a, track_b, o, i, bars_ok[0], energy_direction=energy_direction,
                harmonic_strictness=harmonic_strictness,
                allow_experimental=allow_experimental, tolerances=tolerances,
                bass_swap_geplant=bass_swap_geplant)
            for bars in bars_ok:
                # Flache Kopien statt to_dict()/from_dict() (asdict kostete die
                # Haelfte der Laufzeit); die Schema-Listen werden eigenstaendig,
                # weil dedupe_and_cap sie vereinigt.
                o_k, i_k = copy.copy(o), copy.copy(i)
                o_k.schema, i_k.schema = list(o.schema or []), list(i.schema or [])
                o_k.section_label, i_k.section_label = out_section_label, in_section_label
                paare.append(PairCandidate(
                    out_a=o_k, in_b=i_k,
                    blend_bars=bars, overlap_sec=bars * spb, score=score, teilwerte=dict(teil),
                    flags=dict(flags), begruendung=begruendung_aus_teilwerten(teil, flags, bars),
                    bpm_relation=rel))
    if not paare:
        return []
    final = dedupe_and_cap(paare, _grid_sec(track_a), _grid_sec(track_b), schemata_vorhanden, rang_map)
    for rang, p in enumerate(final, start=1):
        p.rang = rang
    return final


def rank_pair_candidates(track_a: Track, track_b: Track, *, bpm_tolerance: float = PAAR_BPM_MAX,
                         energy_direction=None,
                         harmonic_strictness: int = 7, allow_experimental: bool = True,
                         tolerances: dict | None = None, wahl: dict | None = None,
                         schema_rang: list[str] | None = None) -> list[PairCandidate]:
    """Kandidaten des Paars in App-Reihenfolge (Spec Abschnitt 4): eine
    gespeicherte Wahl (candidate_choices, oder `wahl`) kommt nach vorn, sonst
    Score; Tiebreak die Schema-Rangfolge aus dem Hoertest
    (candidate_preferences), sonst SCHEMA_PRIORITAET. Flag `gespeicherte_wahl`
    auf jedem Kandidaten. bass_swap_geplant=True: die App waehlt bei
    bass_swap_pflicht den Uebergangstyp bass_swap."""
    try:
        tolerance = float(bpm_tolerance)
        bpm_diff, _ = effective_bpm_diff(track_a.bpm, track_b.bpm)
    except (TypeError, ValueError):
        return []
    if not math.isfinite(tolerance) or tolerance < 0.0 or bpm_diff > tolerance:
        return []
    genre_a = _genre(track_a)
    effektiver_schema_rang = (
        candidate_preferences.schema_rangfolge(genre_a) or None
        if schema_rang is None
        else list(schema_rang)
    )
    paare = build_pair_candidates(
        track_a, track_b, energy_direction=energy_direction, harmonic_strictness=harmonic_strictness,
        allow_experimental=allow_experimental, tolerances=tolerances, bass_swap_geplant=True,
        schema_rang=effektiver_schema_rang)
    paare = [p for p in paare if not pair_quality_reasons(p.score, p.teilwerte, p)]
    if not paare:
        return []
    w = wahl if wahl is not None else candidate_choices.hole(track_a.filePath, track_b.filePath)
    treffer = None
    wahl_ungueltig_grund = ""
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
        if treffer is None:
            wahl_ungueltig_grund = "kandidat_nicht_mehr_vorhanden"
        elif w.get("version") == 2:
            try:
                auditwerte = (
                    ("bpm_a", float(track_a.bpm), float(w["bpm_a"])),
                    ("bpm_b", float(track_b.bpm), float(w["bpm_b"])),
                    (
                        "overlap_sec",
                        float(treffer.overlap_sec),
                        float(w["overlap_sec"]),
                    ),
                )
            except (KeyError, OverflowError, TypeError, ValueError):
                wahl_ungueltig_grund = "audit_snapshot_ungueltig"
            else:
                for feld, aktuell, gespeichert in auditwerte:
                    if (
                        not math.isfinite(aktuell)
                        or not math.isfinite(gespeichert)
                        or not math.isclose(
                            aktuell,
                            gespeichert,
                            rel_tol=0.0,
                            abs_tol=WAHL_AUDIT_ABS_TOLERANCE,
                        )
                    ):
                        wahl_ungueltig_grund = f"{feld}_abweichung"
                        break
            if wahl_ungueltig_grund:
                treffer = None
        if wahl_ungueltig_grund:
            logger.warning(
                "Gespeicherte Kandidatenwahl %s -> %s wird nicht priorisiert: %s",
                track_a.filePath,
                track_b.filePath,
                wahl_ungueltig_grund,
            )
    for p in paare:
        p.flags["gespeicherte_wahl"] = p is treffer
        p.flags["gespeicherte_wahl_ungueltig"] = bool(wahl_ungueltig_grund)
        if wahl_ungueltig_grund:
            p.flags["gespeicherte_wahl_grund"] = wahl_ungueltig_grund
    if treffer is not None:
        paare = [treffer] + [p for p in paare if p is not treffer]
    for rang, p in enumerate(paare, start=1):
        p.rang = rang
    return paare


def select_pair_candidate(track_a: Track, track_b: Track, **kw) -> PairCandidate | None:
    """Rang 1 aus rank_pair_candidates oder None."""
    paare = rank_pair_candidates(track_a, track_b, **kw)
    return paare[0] if paare else None

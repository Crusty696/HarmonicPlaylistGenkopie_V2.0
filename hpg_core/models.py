from __future__ import annotations
import os
import re
import math
from dataclasses import dataclass, field

from .config import METER, BPM_HALF_DOUBLE_ENABLED, MIX_POINT_UNSET

SUPPORTED_PHRASE_UNITS = (8, 16, 32)


def is_supported_phrase_unit(value: object) -> bool:
    """Prueft Phraseneinheit ohne bool-als-int oder implizite Umwandlung."""
    return type(value) is int and value in SUPPORTED_PHRASE_UNITS


def bar_position_usage_blocked(anchor_or_diagnostics) -> bool:
    """Sperrt unaufgeloeste Rotation; audio-bestaetigte Korrektur ist aktiv."""
    if not isinstance(anchor_or_diagnostics, dict):
        return False
    if "version" in anchor_or_diagnostics and anchor_or_diagnostics.get("version") not in {5, 6, 7, 8}:
        return False
    anchor = anchor_or_diagnostics.get("anchor", anchor_or_diagnostics)
    comparison = anchor.get("bar_position_comparison") if isinstance(anchor, dict) else None
    if not isinstance(comparison, dict):
        return False
    confirmation = comparison.get("audio_confirmation")
    if (
        comparison.get("status") == "candidate_rotation"
        and isinstance(anchor, dict)
        and anchor.get("method") == "model_audio_rotation"
        and anchor.get("source") == "audio"
        and isinstance(confirmation, dict)
        and anchor.get("anchor_s") == confirmation.get("expected_anchor_s")
        and confirmation.get("status") == "audio_confirmed"
        and confirmation.get("final_grid_status") == "verified"
    ):
        return False
    rotation = comparison.get("rotation_beats")
    windows = comparison.get("windows")
    if not isinstance(windows, list) or any(
        not isinstance(row, dict)
        or type(row.get("model_id")) is not str
        or row["model_id"] not in {"model7", "model8"}
        or type(row.get("start_s")) not in (int, float)
        or not math.isfinite(row["start_s"])
        for row in windows
    ):
        return False
    model_ids = {row.get("model_id") for row in windows}
    starts = {row.get("start_s") for row in windows}
    measured_pairs = {(row.get("model_id"), row.get("start_s")) for row in windows}
    expected_pairs = {
        (model_id, start_s)
        for model_id in ("model7", "model8")
        for start_s in starts
    }
    return (
        comparison.get("status") == "candidate_rotation"
        and comparison.get("reason") in {"measured", "offset_compensated"}
        and type(rotation) is int and rotation in {1, 2, 3}
        and isinstance(windows, list) and len(windows) == 6
        and model_ids == {"model7", "model8"} and len(starts) == 3
        and measured_pairs == expected_pairs
        and all(
            isinstance(row, dict)
            and row.get("status") == "measured"
            and row.get("rotation_beats") == rotation
            for row in windows
        )
    )

# Mapping from Key and Mode to Camelot Code
CAMELOT_MAP = {
    ('A', 'Minor'): '8A', ('A#', 'Minor'): '3A', ('B', 'Minor'): '10A',
    ('C', 'Minor'): '5A', ('C#', 'Minor'): '12A', ('D', 'Minor'): '7A',
    ('D#', 'Minor'): '2A', ('E', 'Minor'): '9A', ('F', 'Minor'): '4A',
    ('F#', 'Minor'): '11A', ('G', 'Minor'): '6A', ('G#', 'Minor'): '1A',
    ('C', 'Major'): '8B', ('C#', 'Major'): '3B', ('D', 'Major'): '10B',
    ('D#', 'Major'): '5B', ('E', 'Major'): '12B', ('F', 'Major'): '7B',
    ('F#', 'Major'): '2B', ('G', 'Major'): '9B', ('G#', 'Major'): '4B',
    ('A', 'Major'): '11B', ('A#', 'Major'): '6B', ('B', 'Major'): '1B',
}

# Hinweis: TrackSection lebt in structure_analyzer.py (einzige Definition).
# Das fruehere ungenutzte Duplikat hier wurde entfernt (Audit 2026-07-17);
# in Track.sections liegen serialisierte Section-Dicts.


# Toleranz, innerhalb derer ein Zeitpunkt als AUF dem Raster liegend gilt.
#
# WARUM: Sektionsgrenzen kommen gerundet aus der Analyse (zwei Nachkommastellen,
# also bis zu 5 ms Fehler) und sind zusaetzlich frame-quantisiert (bei Hop 512
# und 22050 Hz rund 23 ms). Liegt eine solche Grenze rechnerisch 3 ms HINTER
# einem Rasterpunkt, schiebt `ceil` den Mixpunkt um eine GANZE Phrase nach
# hinten — bei 16-Bar-Phrasen und 140 BPM sind das 27 Sekunden.
#
# Real gemessen (Paar 001 des Hoertests, 2026-08-20): Intro-Ende 82,29 s,
# Raster 27,4286 s, drei Raster = 82,2867 s. Ueberschuss 0,0033 s ->
# rel = 3,00012 -> ceil = 4 -> Mix-In 109,72 s statt 82,29 s, also mitten in
# den Drop statt ans Intro-Ende.
#
# 50 ms ist bewusst gewaehlt: groesser als die Rundungs- und Frame-Fehler
# oben, aber unter der hoerbaren Flam-Grenze von 1/8 Beat (54 ms bei 138 BPM,
# siehe downbeat.py) — die Toleranz kann also keine echte Rastergrenze
# ueberspringen, die ein Hoerer als Versatz wahrnaehme.
QUANTIZE_TOLERANCE_SEC = 0.05

BEATGRID_SOURCES = frozenset({"unknown", "none", "rekordbox", "audio"})
BEATGRID_STATUSES = frozenset(
    {"unknown", "verified", "mismatch", "unverifiable", "unsupported"}
)


def quantize_to_grid(
    t: float, grid: float, anchor: float = 0.0, mode: str = "round"
) -> float:
    """Quantisiert einen Zeitpunkt auf ein Raster mit optionalem Anker.

    Downbeat-Feature 2026-07-17: das Takt-/Phrasen-Raster ist am ersten
    Downbeat verankert statt an t=0. Formel: (t - anchor)/grid quantisieren,
    dann + anchor. Bei anchor=0.0 bit-identisch zum bisherigen Verhalten.

    `ceil` und `floor` arbeiten mit QUANTIZE_TOLERANCE_SEC Spielraum: ein
    Zeitpunkt, der nur durch Rundungsrauschen knapp neben einem Rasterpunkt
    liegt, wird als AUF dem Raster liegend behandelt statt eine volle Phrase
    weit verschoben zu werden.
    """
    if grid <= 0:
        return t
    rel = (t - anchor) / grid
    # Toleranz im Raster-Massstab: absolute Sekunden durch die Rasterbreite.
    eps = QUANTIZE_TOLERANCE_SEC / grid
    if mode == "ceil":
        from math import ceil as _ceil
        idx = _ceil(rel - eps)
    elif mode == "floor":
        from math import floor as _floor
        idx = _floor(rel + eps)
    else:
        idx = round(rel)
    return idx * grid + anchor


def seconds_per_bar(bpm: float, meter: int = METER) -> float:
    """Sekunden pro Takt — zentrale Definition statt 15+ Kopien im Code.

    Audit 2026-07-17: mehrere Stellen umgingen METER mit hartkodierter 4.
    """
    if bpm <= 0:
        return 0.0
    return (60.0 / bpm) * meter


def seconds_to_bars(
    seconds: float, bpm: float, meter: int = METER, rounding: str = "round"
) -> int:
    """Zentrale Seconds→Bars-Semantik mit expliziter Rundungsart."""
    width = seconds_per_bar(bpm, meter)
    if width <= 0:
        return 0
    value = float(seconds) / width
    if rounding == "floor":
        from math import floor
        return int(floor(value))
    if rounding == "ceil":
        from math import ceil
        return int(ceil(value))
    if rounding != "round":
        raise ValueError(f"Unbekannte Bar-Rundung: {rounding}")
    return int(round(value))


def bars_to_seconds(bars: int, bpm: float, meter: int = METER) -> float:
    """Zentrale Bars→Seconds-Umrechnung."""
    return float(bars) * seconds_per_bar(bpm, meter)


_CAMELOT_RE = re.compile(r"(1[0-2]|[1-9])([AB])")


def get_camelot_components(camelot_code: str) -> tuple[int, str]:
    """Parst einen Camelot-Code in (Nummer, Buchstabe); (0, "") bei ungueltig.

    Zentrale Definition — vorher identische Regexe in playlist und dj_brain.
    """
    match = _CAMELOT_RE.fullmatch(camelot_code or "")
    if match:
        return int(match.group(1)), match.group(2)
    return 0, ""


def camelot_relation_score(
    code_a: str, code_b: str, *, harmonic_strictness: int = 7,
    allow_experimental: bool = True, penalty: float = 1.0,
) -> int:
    """Camelot-Punktetabelle fuer zwei Codes (Reihenfolge der Zweige bindend).

    Herausgeloest aus playlist._calculate_compatibility_inner (2026-08-22),
    damit die Paar-Bewertung der Kandidaten (camelot_lokal) dieselbe Tabelle
    nutzt. `penalty` ist der Half/Double-Faktor des Aufrufers (1.0 = direct).
    Fehlende/ungueltige Codes -> 10 * penalty.
    """
    if not code_a or not code_b:
        return int(10 * penalty)
    num1, letter1 = get_camelot_components(code_a)
    num2, letter2 = get_camelot_components(code_b)
    if num1 == 0 or num2 == 0:
        return int(10 * penalty)
    if num1 == num2 and letter1 == letter2:
        return int(100 * penalty)
    if num1 == num2 and letter1 != letter2:
        if letter1 == "A" and letter2 == "B":
            return int(90 * penalty)
        return int(85 * penalty)
    next_num_cw = (num1 % 12) + 1
    next_num_ccw = (num1 - 2 + 12) % 12 + 1
    if letter1 == letter2 and (num2 == next_num_cw or num2 == next_num_ccw):
        return int(80 * penalty)
    # Obergrenze 1.0 (AUDIT-FIX F03): lockere Techniken ueberholen nie den +-1.
    loose_factor = max(0.4, min(1.0, 1.0 - (harmonic_strictness - 7) * 0.08))
    plus_two_num = (num1 + 2 - 1) % 12 + 1
    if num2 == plus_two_num and letter1 == letter2:
        return int(75 * penalty * loose_factor)
    if allow_experimental:
        plus_four_num = (num1 + 4 - 1) % 12 + 1
        if num2 == plus_four_num and letter1 == letter2:
            return int(70 * penalty * loose_factor)
        plus_seven_num = (num1 + 7 - 1) % 12 + 1
        if num2 == plus_seven_num and letter1 == letter2:
            return int(65 * penalty * loose_factor)
    if letter1 != letter2 and (num2 == next_num_cw or num2 == next_num_ccw):
        return int(60 * penalty * loose_factor)
    return max(5, int((15 - harmonic_strictness) * penalty))


def effective_bpm_diff(bpm1: float, bpm2: float) -> tuple[float, str]:
    """Effektive BPM-Differenz mit Half/Double-Time-Erkennung.

    Zentrale Definition (Audit 2026-07-17) — vorher zwei divergierende Kopien:
    playlist respektierte BPM_HALF_DOUBLE_ENABLED, dj_brain ignorierte das Flag.

    Returns:
        (effektive_differenz, relation) mit relation in "direct"/"half"/"double"
    """
    if bpm1 <= 0 or bpm2 <= 0:
        return abs(bpm1 - bpm2), "direct"

    # AUDIT-FIX F01 (2026-07-24): Die Differenz wird IMMER im Tempo-Raum von
    # bpm1 (Referenz = Track A, der laufen bleibt) gemessen. Vorher enthielt die
    # Liste fuer dieselbe Relation je einen Kandidaten im schnellen UND im
    # langsamen Tempo-Raum (z. B. |bpm1-bpm2*2| und |bpm1*2-bpm2| = das Doppelte
    # davon); min() waehlte systematisch die halbierte Variante, wodurch das
    # BPM-Hard-Gate bei Half/Double doppelt so lax war (140 vs 73 passierte mit
    # "diff 3", real muss der DJ 6 BPM = 4,3 % schieben). Track B wird an A
    # angepasst: half-time B -> *2, double-time B -> /2, jeweils gegen bpm1.
    candidates = [
        (abs(bpm1 - bpm2), "direct"),
        (abs(bpm1 - bpm2 * 2), "half"),    # bpm2 ist Half-Time -> auf *2 ziehen
        (abs(bpm1 - bpm2 / 2), "double"),  # bpm2 ist Double-Time -> auf /2 ziehen
    ]

    if not BPM_HALF_DOUBLE_ENABLED:
        return candidates[0]

    return min(candidates, key=lambda x: x[0])


@dataclass(eq=False)
class Track:
    # Core Info
    filePath: str
    fileName: str

    @property
    def track_id(self) -> str:
        """Stabile Windows-Identitaet; Basename ist ausdruecklich ungeeignet."""
        return os.path.normcase(os.path.abspath(os.path.normpath(self.filePath)))

    def __eq__(self, other: object) -> bool:
        """Vergleicht Tracks ueber stabile Datei-Identitaet statt Deep-Compare."""
        if not isinstance(other, Track):
            return NotImplemented
        return self.track_id == other.track_id

    def __hash__(self) -> int:
        """Ermoeglicht schnelle Sets/Dicts ueber stabile Track-Identitaet."""
        return hash(self.track_id)

    @property
    def reference_bar_position_verified(self) -> bool:
        """Prueft Bar-1-Freigabe samt persistierter, ausgerichteter Diagnose."""
        diagnostics = self.measurement_diagnostics
        anchor = diagnostics.get("anchor") if isinstance(diagnostics, dict) else None
        comparison = anchor.get("bar_position_comparison") if isinstance(anchor, dict) else None
        return bool(
            self.bar_position_status == "reference_verified"
            and self.beatgrid_source == "rekordbox"
            and self.beatgrid_status == "verified"
            and self.downbeat_confidence == 1.0
            and isinstance(comparison, dict)
            and comparison.get("status") == "aligned"
        )

    @property
    def verified_pssi_phrase_grid(self) -> bool:
        """PSSI-Punkte nur mit ausgerichtetem Referenzanker quantisieren."""
        return bool(
            self.phrases
            and self.phrase_grid
            and self.reference_bar_position_verified
            and not self.bar_position_usage_blocked
        )

    @property
    def phrase_anchor(self) -> float | None:
        """AUDIT-FEATURE A1: Anker fuers PHRASEN-Gitter.

        Gibt nur einen explizit nutzbaren Phrase-/Taktanker zurück. Ein
        unbestätigtes Raster liefert None statt eines stillen Nullzeitankers.

        AUDIT-FIX R4 (2026-07-26): Sentinel fuer "nicht geschaetzt" ist -1.0
        — eine Phase von exakt 0.0 ist GUELTIG und wurde vorher verworfen.
        Ein konsistentes Beatgrid belegt keine unabhaengige musikalische
        Takt-1-Genauigkeit. Es ist hier das technische Gate gegen
        unbestaetigte Raster, keine Ground-Truth-Aussage.
        Bei einer validierten nichtnulligen Modell-Taktrotation ist der Anker
        explizit nicht verfuegbar (None), damit kein Aufrufer auf 0.0 ausweicht.
        """
        from .config import PHRASE_CONFIDENCE_MIN
        from .downbeat import DOWNBEAT_RELIABLE_MIN
        if bar_position_usage_blocked(self.measurement_diagnostics):
            return None
        from .ai_models.native_track_beats import has_verified_grid
        native_phase = has_verified_grid(self)
        if (self.beatgrid_status != "verified"
                or (self.downbeat_confidence < DOWNBEAT_RELIABLE_MIN and not native_phase)):
            return None
        if (self.bar_position_status in {"reference_candidate", "native_candidate"}
                or (self.beatgrid_source == "rekordbox"
                    and not self.reference_bar_position_verified)):
            return None
        if (
            self.first_phrase >= 0.0
            and self.phrase_confidence >= PHRASE_CONFIDENCE_MIN
        ):
            return self.first_phrase
        return self.first_downbeat

    @property
    def bar_position_usage_blocked(self) -> bool:
        """Takt-/Phrasen-Nutzung bei validiertem Rotationshinweis sperren."""
        return bar_position_usage_blocked(self.measurement_diagnostics)

    # ID3 Tag Info
    artist: str = "Unknown"
    title: str = "Unknown"
    genre: str = "Unknown"

    # Analysis Info
    duration: float = 0.0
    bpm: float = 0.0
    keyNote: str = ""
    keyMode: str = ""
    stem_analysis: dict = field(default_factory=dict)
    embedding_analysis: dict = field(default_factory=dict)
    audio_embedding: list[float] = field(default_factory=list)
    camelotCode: str = ""
    energy: int = 0
    bass_intensity: int = 0

    # Advanced Frequency Bands
    avg_bass: float = 0.0
    avg_mids: float = 0.0
    avg_highs: float = 0.0

    # Structural Info
    # -1.0 = nicht gesetzt; 0.0 ist ein gueltiger Mixpunkt am Trackanfang.
    mix_in_point: float = MIX_POINT_UNSET
    mix_out_point: float = MIX_POINT_UNSET

    # Downbeat-Anker (2026-07-17): Zeitpunkt der ersten "1" in Sekunden.
    # Verankert das Phrasen-Raster der Mixpoint-Quantisierung; 0.0 = kein
    # Anker (Verhalten wie frueher, Raster ab t=0). Die Bar-Anzeige
    # (mix_in_bars/mix_out_bars) zaehlt weiterhin ab Track-Start.
    first_downbeat: float = 0.0
    downbeat_confidence: float = 0.0  # 0-1; 1.0 = aus Rekordbox-Beatgrid
    # Taktzählung ist getrennt von der technisch bestätigten Beatphase.
    # native_candidate darf fürs Debugging/Modell weitergereicht, aber nicht
    # als unabhängig bestätigte Bar-1-Referenz exportiert oder ausgerichtet werden.
    bar_position_status: str = "unknown"
    # -1.0 ist der Sentinel fuer "kein messbares Fenster".
    beatgrid_source: str = "unknown"
    beatgrid_status: str = "unknown"
    beatgrid_windows_checked: int = 0
    beatgrid_max_phase_error_ms: float = -1.0
    # Schema 2 trennt aktive Ankerquelle, RB-Versuch und neuronale Audio-Prüfung.
    # Leeres Objekt bedeutet unbekannt, niemals nachtraeglich erfundene Ursache.
    measurement_diagnostics: dict = field(default_factory=dict)
    # Versionierte Cue-/Beat-Kandidaten; leer bedeutet unbekannt, kein Scoringbonus.
    neural_analysis: dict = field(default_factory=dict)
    # Native Phrasenerzeugung getrennt von importiertem PSSI und Cue-Regressor.
    native_phrase_analysis: dict = field(default_factory=dict)
    # Vollständiges natives Beatgrid, getrennt von importiertem ANLZ/PSSI.
    native_beat_analysis: dict = field(default_factory=dict)

    # AUDIT-FEATURE A1 (2026-07-26): PHRASEN-Anker — Zeitpunkt der ersten
    # Phrasengrenze in Sekunden (liegt auf dem Bar-Raster: first_downbeat +
    # k*bar_len). Der Takt-Anker sagt nur, WO die "1" liegt; erst die
    # Phrasen-Phase sagt, welcher Takt Takt 1 einer 8/16-Bar-Phrase ist.
    # AUDIT-FIX R4 (2026-07-26): -1.0 = nicht geschaetzt (Fallback:
    # first_downbeat als Anker); 0.0 ist eine GUELTIGE Phase.
    first_phrase: float = -1.0
    phrase_confidence: float = 0.0  # 0-1 aus dem Bar-Voting

    # Key-Confidence (2026-07-17): 0-1 nach Essentia-Muster (strength+margin);
    # 0.0 = unbekannt (Alt-Cache), 1.0 = Key aus Rekordbox-DB
    key_confidence: float = 0.0

    # Integrated Loudness nach EBU R128 (2026-07-17); 0.0 = nicht gemessen
    lufs: float = 0.0

    # Mix Points in Bars (fuer DJ-Anzeige)
    mix_in_bars: int = 0
    mix_out_bars: int = 0

    # DJ Brain - Genre Detection (Phase 1)
    detected_genre: str = "Unknown"
    genre_confidence: float = 0.0
    genre_source: str = ""

    # DJ Brain - Track Structure (Phase 2)
    sections: list = field(default_factory=list)  # Liste von TrackSection-Dicts
    phrase_unit: int = 8
    phrase_unit_source: str = "genre_prior"  # genre_prior, audio_novelty, configured
    phrase_unit_candidate: int | None = None
    phrase_unit_score: float | None = None  # rohe Novelty-Korrelation, keine Wahrscheinlichkeit
    phrase_unit_margin: float | None = None  # Abstand im prior-adjustierten Ranking

    # Audio Feature Extensions (Phase 3)
    brightness: int = 0  # Spektrale Helligkeit 0-100 (dunkel?hell)
    vocal_instrumental: str = "unknown"  # "vocal", "instrumental", "unknown"
    danceability: int = 0  # Tanzbarkeit 0-100
    spectral_flatness: float = 0.0
    percussive_ratio: float = 0.0
    mfcc_fingerprint: list = field(default_factory=list)  # MFCC-Vektor fuer Similarity
    timbre_fingerprint: list = field(default_factory=list)  # Gemittelter MFCC-Fingerabdruck
    # Groove-Features (2026-08-19): beat-synchrone Rhythmusmuster, verankert
    # am first_downbeat. Leere Liste = nicht bestimmt (z. B. downbeat_confidence
    # 0.0); das Scoring verteilt das Gewicht dann um, statt zu bestrafen.
    groove_pattern: list = field(default_factory=list)  # 16 Slots, L1-normiert
    bass_pattern: list = field(default_factory=list)    # 16 Slots, nur <150 Hz
    syncopation: float = 0.0    # 0-1, Offbeat-Anteil im Achtel-Raster
    sub_energy: float = 0.0     # 20-60 Hz, Anteil an der Gesamtenergie
    bass_punch: float = 0.0     # Crest-Faktor des Bassbands
    ai_metadata: dict = field(default_factory=dict)  # LLM Analysis Results
    # Quellidentität: Rekordbox-Metadatensignatur plus Cue-/Beat-Modell-/Preprocess-
    # Fingerprint. Bestehende Cache-/KI-Merge-Konsumenten verwenden dieses Feld.
    rekordbox_signature: str = ""

    # Provenienz der Audioabdeckung. Luecken bleiben explizit sichtbar; ein
    # Mix-Out darf nur verwendet werden, wenn das Track-Ende analysiert wurde.
    analysis_mode: str = "unknown"
    analysis_coverage: list = field(default_factory=list)
    outro_covered: bool = False
    lufs_status: str = "unknown"
    lufs_coverage_seconds: float = 0.0
    lufs_channels: int = 0
    lufs_sample_rate: int = 0
    # Mixpunkt-Kandidaten (Spec 2026-08-21 Abschnitt 1). Alles Listen von
    # Dicts/Floats, damit der Cache sie ohne Sonderfall serialisiert.
    phrases: list = field(default_factory=list)             # Rekordbox-PSSI-Phrasen
    cue_points: list = field(default_factory=list)          # Cues mit Provenienz
    phrase_grid: list = field(default_factory=list)         # Gitterpunkte (Sekunden)
    mix_in_candidates: list = field(default_factory=list)   # MixCandidate.to_dict()
    mix_out_candidates: list = field(default_factory=list)

def key_to_camelot(track: Track):
    """Assigns a Camelot code to a track based on its key."""
    # camelotCode ist ein abgeleitetes Feld. Auch ein geloeschter oder
    # ungueltiger Key muss deshalb einen zuvor berechneten Wert invalidieren.
    track.camelotCode = CAMELOT_MAP.get((track.keyNote, track.keyMode), "")

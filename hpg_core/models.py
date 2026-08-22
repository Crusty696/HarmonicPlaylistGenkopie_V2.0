from __future__ import annotations
import os
import re
from dataclasses import dataclass, field

from .config import METER, BPM_HALF_DOUBLE_ENABLED, MIX_POINT_UNSET

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
    def phrase_anchor(self) -> float:
        """AUDIT-FEATURE A1: Anker fuers PHRASEN-Gitter.

        first_phrase, wenn die Schaetzung belastbar ist (Konfidenz-Gate aus
        config.PHRASE_CONFIDENCE_MIN), sonst first_downbeat (bisheriges
        Verhalten). Damit ist die Umstellung fuer Alt-Caches und schwache
        Schaetzungen ein No-Op.

        AUDIT-FIX R4 (2026-07-26): Sentinel fuer "nicht geschaetzt" ist -1.0
        — eine Phase von exakt 0.0 ist GUELTIG und wurde vorher verworfen.
        AUDIT-FIX R2 (2026-07-26): zusaetzliches Gate auf
        downbeat_confidence — ein first_phrase aus Alt-Caches, das auf einem
        gescheiterten (erfundenen) Downbeat-Raster abgestimmt wurde, wird
        nicht mehr als Anker verwendet.
        """
        from .config import PHRASE_CONFIDENCE_MIN
        if (
            self.first_phrase >= 0.0
            and self.downbeat_confidence > 0.0
            and self.phrase_confidence >= PHRASE_CONFIDENCE_MIN
        ):
            return self.first_phrase
        return self.first_downbeat

    # ID3 Tag Info
    artist: str = "Unknown"
    title: str = "Unknown"
    genre: str = "Unknown"

    # Analysis Info
    duration: float = 0.0
    bpm: float = 0.0
    keyNote: str = ""
    keyMode: str = ""
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
    # Signatur der verwendeten Rekordbox-Metadaten fuer Cache-Invalidierung.
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

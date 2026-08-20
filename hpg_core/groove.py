"""Beat-synchrone Mustererkennung fuer das Uebergangs-Scoring.

Reine Funktionen ohne Audio-Kontext-Abhaengigkeit: Huellkurve und Zeiten
rein, normiertes Muster raus. Damit bleiben die gelernten Toleranzen
ueberpruefbar (siehe Spec Abschnitt 4).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import librosa
import numpy as np

from .config import METER

logger = logging.getLogger(__name__)

# Ein 4/4-Takt hat 16 Sechzehntel — das ist die Aufloesung des Musters.
BAR_SLOTS = 16

# Mindest-Konzentration des gefalteten Musters, als Vielfaches der
# Gleichverteilung (1/slots). Darunter gilt das Muster als nicht bestimmbar
# und `fold_to_bar` liefert eine leere Liste.
#
# WARUM: ueber ein langes Fenster laeuft ein Tempofehler als Phase weg
# (Drift = Fensterlaenge * dBPM / BPM). Bei 360 s Analysefenster
# (LIBROSA_FAST_PATH_DURATION) und 0,5 BPM Fehler auf 128 BPM sind das 1,4 s
# — mehr als ein ganzer Takt. Das Muster wird dann flach, bleibt aber 16
# Zahlen und wuerde vom Scoring als gueltiges Signal gelesen. Genau das soll
# der Vertrag "leer = nicht bestimmt" verhindern.
#
# KALIBRIERUNG (2026-08-19, 50 Tracks der Sammlung, 360-s-Fenster, BPM aus
# Rekordbox, Spitze als Vielfaches der Gleichverteilung):
#   korrektes Tempo   Onset  min 1,133  Median 1,52  max 2,62
#                     Bass   min 1,137  Median 1,40  max 2,24
#   Tempo +0,5 BPM    Onset  max 1,187  Median 1,11
#                     Bass   max 1,225  Median 1,09
#   synthetisch: exakter Impulszug 4,00 / +0,5 BPM 1,02 / gleichverteilt 1,00
# Auf ECHTEM Audio ueberlappen die beiden Verteilungen — anders als beim
# synthetischen Impulszug gibt es keinen Schwellwert, der sauber trennt.
# 1,10 liegt unter dem Minimum aller 100 gemessenen Muster mit korrektem
# Tempo (1,133) und ueber der Gleichverteilung samt synthetischem
# Drift-Fall (1,02). Der Gate verwirft damit sicher das, was nachweislich
# Rauschen ist, ohne belastbare Muster zu verlieren. Ein hoeherer Wert
# (etwa 1,5) wuerde die Mehrheit der korrekt analysierten Tracks
# wegwerfen — siehe Median 1,40 bis 1,52.
GROOVE_MIN_PEAK_RATIO = 1.10


def fold_to_bar(
    envelope: np.ndarray,
    times: np.ndarray,
    bpm: float,
    first_downbeat: float,
) -> list[float]:
    """Faltet eine Huellkurve auf einen Takt und normiert auf Summe 1.

    Jeder Frame wird ueber seinen Zeitstempel einem der `slots` Sechzehntel
    zugeordnet, verankert am ersten Downbeat. Rueckgabe ist eine leere Liste,
    wenn kein belastbares Raster bestimmt werden kann.

    Die Slot-Zahl ist fest BAR_SLOTS (16). Ein frei waehlbarer Parameter waere
    eine Scheinfreiheit: ON_BEAT_SLOTS/OFF_BEAT_SLOTS beschreiben genau dieses
    Raster, und syncopation_from_pattern lieferte bei jeder anderen Zahl
    stillschweigend 0.0. Weggelassen statt hergeleitet, weil kein Aufrufer je
    eine andere Zahl brauchte.

    Die Slots sind auf dem Raster ZENTRIERT, nicht daran ausgerichtet: Slot 0
    umfasst [-halbe Slotbreite, +halbe Slotbreite) um den Downbeat. Laege der
    Downbeat am linken Rand von Slot 0, saesse jede Zaehlzeit exakt auf einer
    Bin-Grenze — der Punkt mit der groessten Streuung. Der geschaetzte
    Downbeat traegt laut Kalibrierung in downbeat.py auch bei guter Konfidenz
    einen Sub-Beat-Fehler (Median 16 ms, Max 43 ms); das reicht regelmaessig,
    um Energie ueber die Grenze in den Sechzehntel VOR der Zaehlzeit zu
    schieben (gemessen: 42 % der Bassenergie eines reinen On-Beat-Kicks
    landeten in 3/7/11/15).
    """
    if envelope is None or times is None:
        return []
    if len(envelope) == 0 or len(times) == 0 or len(envelope) != len(times):
        return []
    if bpm <= 0:
        return []

    slots = BAR_SLOTS

    bar_duration = (60.0 / bpm) * METER
    if bar_duration <= 0:
        return []
    slot_width = bar_duration / slots

    acc = np.zeros(slots, dtype=float)
    rel = np.mod(np.asarray(times, dtype=float) - float(first_downbeat), bar_duration)
    # +0.5 verschiebt die Bin-Grenze um eine halbe Slotbreite: der Downbeat
    # liegt damit in der Mitte von Slot 0 statt an dessen linkem Rand.
    idx = np.floor(rel / slot_width + 0.5).astype(int) % slots
    np.add.at(acc, idx, np.asarray(envelope, dtype=float))

    total = float(acc.sum())
    if total <= 0.0:
        return []
    muster = acc / total

    # Konzentrations-Gate: ein von der Gleichverteilung nicht unterscheidbares
    # Muster ist kein Muster, sondern ein auf falschem Tempo verschmiertes
    # Signal (siehe GROOVE_MIN_PEAK_RATIO).
    if float(muster.max()) < GROOVE_MIN_PEAK_RATIO / slots:
        return []
    return muster.tolist()


# Zaehlzeiten und die dazwischenliegenden Achtel im 16-Slot-Raster.
ON_BEAT_SLOTS = (0, 4, 8, 12)
OFF_BEAT_SLOTS = (2, 6, 10, 14)


def syncopation_from_pattern(pattern: list[float]) -> float:
    """Anteil der Offbeat-Energie an der Energie auf dem Achtel-Raster.

    0.0 = alles auf den Zaehlzeiten, 1.0 = alles dazwischen. Slots ausserhalb
    des Achtel-Rasters (Sechzehntel) bleiben unberuecksichtigt, weil sie die
    Frage "gerade oder offbeat" nicht beantworten.
    """
    if not pattern or len(pattern) < BAR_SLOTS:
        return 0.0
    on = sum(pattern[s] for s in ON_BEAT_SLOTS)
    off = sum(pattern[s] for s in OFF_BEAT_SLOTS)
    total = on + off
    if total <= 0.0:
        return 0.0
    return float(off / total)


def bass_punch_from_band(band_envelope: np.ndarray) -> float:
    """Crest-Faktor des Bassbands: Spitze durch Mittelwert.

    Ein durchgehender Sub-Teppich liefert Werte nahe 1.0, ein punchy
    Kick-Bass deutlich mehr. Die Spitze ist das 95. Perzentil, damit ein
    einzelner Frame — ein Klick, ein Clipping-Artefakt — den Wert nicht
    bestimmt.

    Messung an 18 Tracks der Sammlung (2026-08-19, 60-s-Ausschnitte):
    Wertebereich 1,26 bis 2,65, Median 1,95. Bass-Huellkurven aus dem STFT
    tragen in 98-100 % der Frames Energie; das Perzentil ist dort stabil.
    Das Maximum laege systematisch 10-33 % hoeher und haenge an einem
    einzigen Frame.
    """
    if band_envelope is None or len(band_envelope) == 0:
        return 0.0
    arr = np.asarray(band_envelope, dtype=float)
    mean = float(np.mean(np.abs(arr)))
    if mean <= 0.0:
        return 0.0
    peak = float(np.percentile(np.abs(arr), 95))
    return peak / mean


# Onset und STFT werden bei diesem Hop aus dem FeatureCache gelesen. 512 ist
# librosas Default und genau der Hop, den calculate_danceability unmittelbar
# vor dem Groove-Aufruf materialisiert (Onset ohne Argument -> Cache-Schluessel
# None, STFT unter (2048, 512)). Mit dem frueheren HOP_LENGTH (1024) wurden
# beide Groessen ein zweites Mal berechnet.
# Bei sr=22050 sind 512 Samples 23 ms je Frame gegen ein Sechzehntel von
# 117 ms bei 128 BPM — auch die bessere Abtastung.
GROOVE_HOP_LENGTH = 512

# librosas Default-Hop fuer onset_strength. Ein Aufruf OHNE hop_length landet
# im FeatureCache unter dem Schluessel None, rechnet aber mit genau diesem
# Wert. Deshalb wird bei Gleichheit None uebergeben, sonst entstuende ein
# zweiter Eintrag mit identischem Inhalt.
LIBROSA_DEFAULT_ONSET_HOP = 512

# Frequenzgrenzen der Baender in Hz.
SUB_LOW, SUB_HIGH = 20.0, 60.0
BASS_HIGH = 150.0


@dataclass
class GrooveFeatures:
    """Ergebnis der Groove-Extraktion eines Tracks oder Ausschnitts."""

    groove_pattern: list[float] = field(default_factory=list)
    bass_pattern: list[float] = field(default_factory=list)
    syncopation: float = 0.0
    sub_energy: float = 0.0
    bass_punch: float = 0.0


def _band_envelope(
    magnitude: np.ndarray, freqs: np.ndarray, low: float, high: float
) -> np.ndarray:
    """Summiert die STFT-Magnitude eines Frequenzbands je Frame."""
    maske = (freqs >= low) & (freqs < high)
    if not np.any(maske):
        return np.zeros(magnitude.shape[1], dtype=float)
    return magnitude[maske, :].sum(axis=0)


# Kuerzere Ausschnitte tragen bei 22050 Hz und Hop 512 unter 90 STFT-Frames;
# Perzentil und Energieanteil werden dann von einzelnen Frames bestimmt.
# Sektionen darunter bekommen die Kennwerte gar nicht erst (siehe
# analysis.py), damit der Nahtstellen-Fallback auf das Trackmittel greift.
BASS_KENNWERTE_MIN_SEC = 2.0


def _bass_kennwerte_aus_magnitude(
    magnitude: np.ndarray, freqs: np.ndarray
) -> tuple[float, float, np.ndarray]:
    """sub_energy, bass_punch und Bass-Huellkurve einer STFT-Magnitude.

    Einzige Quelle dieser Berechnung: `extract_groove` und `bass_kennwerte`
    rufen beide hierher, damit Trackmittel und Sektionswerte nie
    auseinanderlaufen koennen.

    sub_energy ist ein ENERGIE-Anteil, also aus der Leistung zu bilden:
    Leistung ist das Quadrat der Magnitude. Zaehler und Nenner stammen beide
    aus derselben quadrierten Matrix, damit bleibt der Wert
    verstaerkungsinvariant (geprueft bei 0 dB und -20 dB: identisch).
    Die Bass-Huellkurve bleibt bewusst auf der Magnitude — bass_punch ist ein
    Crest-Faktor und dort kalibriert (1,26 bis 2,65).
    """
    # Erst nach float64 wandeln, dann summieren: float32-Akkumulation ueber
    # tausende Frames weicht sonst je nach Aufrufweg in der 8. Stelle ab, und
    # Sektionswerte und Trackmittel liefen minimal auseinander.
    magnitude = np.asarray(magnitude, dtype=float)
    bass_env = _band_envelope(magnitude, freqs, SUB_LOW, BASS_HIGH)
    leistung = magnitude ** 2
    sub_leistung = _band_envelope(leistung, freqs, SUB_LOW, SUB_HIGH)
    gesamt = float(leistung.sum())
    sub_energy = float(sub_leistung.sum() / gesamt) if gesamt > 0.0 else 0.0
    return sub_energy, bass_punch_from_band(bass_env), bass_env


def bass_kennwerte(
    y: np.ndarray, sr: int, hop_length: int = GROOVE_HOP_LENGTH
) -> tuple[float, float]:
    """sub_energy und bass_punch eines Ausschnitts, ohne Musterfaltung.

    Fuer den Nahtstellen-Vergleich (Spec 5.3) werden diese Kennwerte je
    Sektion gebraucht. `extract_groove` komplett je Sektion zu rufen wuerde
    zusaetzlich Onset und Faltung rechnen — beides ist pro Sektion sinnlos,
    weil das Muster ueber den ganzen Track gebildet wird.
    """
    if y is None or len(y) == 0 or sr <= 0:
        return 0.0, 0.0
    magnitude = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop_length))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=(magnitude.shape[0] - 1) * 2)
    sub_energy, punch, _ = _bass_kennwerte_aus_magnitude(magnitude, freqs)
    return sub_energy, punch


# Mindestmaterial fuer eine belastbare Faltung, in Takten. Unter 8 Takten
# traegt jeder Slot nur eine Handvoll Ereignisse; ein einzelner Fill oder ein
# ausgelassener Kick verschiebt das Muster dann sichtbar. Bleibt nach der
# Maskierung weniger uebrig, wird ueber das GESAMTE Fenster gefaltet: ein
# Muster aus zu wenig Material ist schlechter als eines mit etwas Breakdown
# darin.
GROOVE_MIN_BARS = 8


def _sektions_maske(
    times: np.ndarray, bereiche: list[tuple[float, float]]
) -> np.ndarray:
    """Bool-Maske ueber die Frames, die in einen der Bereiche fallen."""
    maske = np.zeros(len(times), dtype=bool)
    for start_s, end_s in bereiche:
        if end_s <= start_s:
            continue
        maske |= (times >= float(start_s)) & (times < float(end_s))
    return maske


def _mindest_frames(bpm: float, sr: int, hop_length: int) -> int:
    """Frame-Zahl, die GROOVE_MIN_BARS Takten entspricht."""
    bar_duration = (60.0 / bpm) * METER
    return int(GROOVE_MIN_BARS * bar_duration * sr / hop_length)


def extract_groove(
    y: np.ndarray,
    sr: int,
    bpm: float,
    first_downbeat: float,
    feature_cache=None,
    hop_length: int = GROOVE_HOP_LENGTH,
    beat_sektionen: list[tuple[float, float]] | None = None,
) -> GrooveFeatures:
    """Extrahiert Rhythmusmuster und Bass-Kennwerte aus einem Signal.

    Nutzt den uebergebenen FeatureCache, wenn dessen Signal identisch ist —
    Onset und STFT sind die teuren Operationen und liegen dort meist schon
    vor (siehe Spec Abschnitt 5.4).

    beat_sektionen: Bereiche (start_s, end_s) mit Beat. Ist die Liste
    gesetzt, gehen nur Frames innerhalb dieser Bereiche in die FALTUNG ein
    (Spec 5.1: ein Breakdown ohne Drums wuerde das Muster verwaessern).
    Maskiert wird ueber die Frames, das Audio wird NICHT zusammengeschnitten:
    ein Schnitt wuerde die Taktphase zerstoeren, waehrend die Maske die
    Zeitachse absolut laesst und die Verankerung am first_downbeat erhaelt.
    """
    if y is None or len(y) == 0 or sr <= 0:
        return GrooveFeatures()

    passend = (
        feature_cache is not None
        and getattr(feature_cache, "y", None) is not None
        and len(feature_cache.y) == len(y)
    )

    if passend:
        onset_key = (
            None if hop_length == LIBROSA_DEFAULT_ONSET_HOP else hop_length
        )
        onset = feature_cache.get_onset_strength(onset_key)
        # n_fft bleibt bei 2048 — das ist die Groesse, die der Cache haelt.
        # Das Analysefenster von 93 ms steht damit einem Sechzehntel von
        # 117 ms (128 BPM) gegenueber; die Bassmuster koennen deshalb nicht
        # beliebig scharf werden. Bekannte, akzeptierte Grenze: ein kuerzeres
        # Fenster wuerde die Aufloesung im Sub-Bass (20-60 Hz) zerstoeren.
        magnitude = feature_cache.get_stft_magnitude(
            n_fft=2048, hop_length=hop_length
        )
    else:
        onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
        magnitude = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop_length))

    times = librosa.frames_to_time(
        np.arange(len(onset)), sr=sr, hop_length=hop_length
    )
    freqs = librosa.fft_frequencies(sr=sr, n_fft=(magnitude.shape[0] - 1) * 2)

    # Die STFT kann durch abweichende Frame-Zahl minimal laenger oder kuerzer
    # sein als die Onset-Huellkurve — auf die kuerzere kappen. Die Kappung
    # gilt fuer ALLE Kennwerte, nicht nur fuer die Muster: sonst beschriebe
    # sub_energy einen anderen Ausschnitt als bass_pattern.
    n = min(len(onset), magnitude.shape[1], len(times))
    magnitude = magnitude[:, :n]

    sub_energy, punch, bass_env = _bass_kennwerte_aus_magnitude(magnitude, freqs)

    onset_f = np.asarray(onset[:n], dtype=float)
    times_f = np.asarray(times[:n], dtype=float)
    falt_bass = bass_env

    if beat_sektionen:
        maske = _sektions_maske(times_f, beat_sektionen)
        genug = _mindest_frames(bpm, sr, hop_length)
        if int(maske.sum()) >= genug:
            onset_f = onset_f[maske]
            falt_bass = np.asarray(falt_bass)[maske]
            times_f = times_f[maske]
        else:
            logger.info(
                "Groove: nur %d von %d Frames in Beat-Sektionen (Minimum %d "
                "fuer %d Takte) — falte ueber das gesamte Fenster",
                int(maske.sum()), len(times_f), genug, GROOVE_MIN_BARS,
            )

    # sub_energy und bass_punch bleiben bewusst auf dem GESAMTEN Fenster:
    # sie sind das Trackmittel und dienen in transition_features als
    # Rueckfallebene fuer die Sektionswerte an der Nahtstelle. Auf die
    # Beat-Sektionen eingeschraenkt waeren sie kein Trackmittel mehr und
    # nicht mehr mit den Sektionswerten vergleichbar.
    groove_pattern = fold_to_bar(onset_f, times_f, bpm, first_downbeat)
    bass_pattern = fold_to_bar(falt_bass, times_f, bpm, first_downbeat)

    return GrooveFeatures(
        groove_pattern=groove_pattern,
        bass_pattern=bass_pattern,
        syncopation=syncopation_from_pattern(bass_pattern or groove_pattern),
        sub_energy=sub_energy,
        bass_punch=punch,
    )

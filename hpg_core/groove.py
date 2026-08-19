"""Beat-synchrone Mustererkennung fuer das Uebergangs-Scoring.

Reine Funktionen ohne Audio-Kontext-Abhaengigkeit: Huellkurve und Zeiten
rein, normiertes Muster raus. Damit bleiben die gelernten Toleranzen
ueberpruefbar (siehe Spec Abschnitt 4).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import librosa
import numpy as np

from .config import HOP_LENGTH, METER

# Ein 4/4-Takt hat 16 Sechzehntel — das ist die Aufloesung des Musters.
BAR_SLOTS = 16


def fold_to_bar(
    envelope: np.ndarray,
    times: np.ndarray,
    bpm: float,
    first_downbeat: float,
    slots: int = BAR_SLOTS,
) -> list[float]:
    """Faltet eine Huellkurve auf einen Takt und normiert auf Summe 1.

    Jeder Frame wird ueber seinen Zeitstempel einem der `slots` Sechzehntel
    zugeordnet, verankert am ersten Downbeat. Rueckgabe ist eine leere Liste,
    wenn kein belastbares Raster bestimmt werden kann.
    """
    if envelope is None or times is None:
        return []
    if len(envelope) == 0 or len(times) == 0 or len(envelope) != len(times):
        return []
    if bpm <= 0 or slots <= 0:
        return []

    bar_duration = (60.0 / bpm) * METER
    if bar_duration <= 0:
        return []
    slot_width = bar_duration / slots

    acc = np.zeros(slots, dtype=float)
    rel = np.mod(np.asarray(times, dtype=float) - float(first_downbeat), bar_duration)
    idx = np.floor(rel / slot_width).astype(int) % slots
    np.add.at(acc, idx, np.asarray(envelope, dtype=float))

    total = float(acc.sum())
    if total <= 0.0:
        return []
    return (acc / total).tolist()


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
    Kick-Bass mit kurzen, dominanten Impulsen deutlich mehr. Die Spitze
    ist das Maximum, weil ein Perzentil bei duennen Impulsmustern
    (wenige Prozent der Frames tragen den Kick) die Spitze selbst
    wegmitteln und keinen Unterschied zum Teppich mehr zeigen wuerde.
    """
    if band_envelope is None or len(band_envelope) == 0:
        return 0.0
    arr = np.asarray(band_envelope, dtype=float)
    mean = float(np.mean(np.abs(arr)))
    if mean <= 0.0:
        return 0.0
    peak = float(np.max(np.abs(arr)))
    return peak / mean


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


def extract_groove(
    y: np.ndarray,
    sr: int,
    bpm: float,
    first_downbeat: float,
    feature_cache=None,
    hop_length: int = HOP_LENGTH,
) -> GrooveFeatures:
    """Extrahiert Rhythmusmuster und Bass-Kennwerte aus einem Signal.

    Nutzt den uebergebenen FeatureCache, wenn dessen Signal identisch ist —
    Onset und STFT sind die teuren Operationen und liegen dort meist schon
    vor (siehe Spec Abschnitt 5.4).
    """
    if y is None or len(y) == 0 or sr <= 0:
        return GrooveFeatures()

    passend = (
        feature_cache is not None
        and getattr(feature_cache, "y", None) is not None
        and len(feature_cache.y) == len(y)
    )

    if passend:
        onset = feature_cache.get_onset_strength(hop_length)
        magnitude = feature_cache.get_stft_magnitude(hop_length=hop_length)
    else:
        onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
        magnitude = np.abs(librosa.stft(y, hop_length=hop_length))

    times = librosa.frames_to_time(
        np.arange(len(onset)), sr=sr, hop_length=hop_length
    )
    freqs = librosa.fft_frequencies(sr=sr, n_fft=(magnitude.shape[0] - 1) * 2)

    bass_env = _band_envelope(magnitude, freqs, SUB_LOW, BASS_HIGH)
    sub_env = _band_envelope(magnitude, freqs, SUB_LOW, SUB_HIGH)

    # Die Bass-Huellkurve kann durch abweichende Frame-Zahl minimal laenger
    # oder kuerzer sein als die Onset-Huellkurve — auf die kuerzere kappen.
    n = min(len(onset), len(bass_env), len(times))
    groove_pattern = fold_to_bar(onset[:n], times[:n], bpm, first_downbeat)
    bass_pattern = fold_to_bar(bass_env[:n], times[:n], bpm, first_downbeat)

    gesamt = float(magnitude.sum())
    sub_energy = float(sub_env.sum() / gesamt) if gesamt > 0.0 else 0.0

    return GrooveFeatures(
        groove_pattern=groove_pattern,
        bass_pattern=bass_pattern,
        syncopation=syncopation_from_pattern(bass_pattern or groove_pattern),
        sub_energy=sub_energy,
        bass_punch=bass_punch_from_band(bass_env),
    )

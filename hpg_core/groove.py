"""Beat-synchrone Mustererkennung fuer das Uebergangs-Scoring.

Reine Funktionen ohne Audio-Kontext-Abhaengigkeit: Huellkurve und Zeiten
rein, normiertes Muster raus. Damit bleiben die gelernten Toleranzen
ueberpruefbar (siehe Spec Abschnitt 4).
"""
from __future__ import annotations

import numpy as np

from .config import METER

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

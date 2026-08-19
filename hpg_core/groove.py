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

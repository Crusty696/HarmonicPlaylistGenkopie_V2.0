"""Mix-Analyse: Uebergaenge finden und Kennzahlen daraus gewinnen.

Reine Funktionen ohne Dateizugriff — die Beschaffung liegt spaeter in
tools/mix_mining.py. Grundlage der Kalibrierung.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import librosa

from .config import HOP_LENGTH
from .transition_features import cosine_similarity

# Ein DJ-Mix blendet ueber; die Blend-Zone selbst ist unbrauchbar, weil dort
# beide Tracks uebereinanderliegen und jede Messung ein Mischwert waere.
BLEND_HALBBREITE_S = 20.0
# Laenge des stabilen Fensters vor bzw. hinter der Blend-Zone.
FENSTER_S = 30.0
# Ein Track im Mix ist selten kuerzer als das.
MIN_ABSTAND_S = 60.0


def find_transitions(
    y: np.ndarray,
    sr: int,
    min_abstand_s: float = MIN_ABSTAND_S,
    schwelle: float = 2.5,
) -> list[float]:
    """Findet Uebergangsstellen ueber Neuheit in Timbre und Bassband.

    Rueckgabe sind Sekundenpositionen, aufsteigend, mit Mindestabstand.
    Leere Liste, wenn das Signal zu kurz ist oder keine Stelle die Schwelle
    erreicht (homogenes Material).
    """
    if y is None or sr <= 0:
        return []
    dauer = len(y) / float(sr)
    if dauer < 2 * min_abstand_s:
        return []

    # Grobe Aufloesung genuegt und haelt lange Mixe bezahlbar.
    hop = HOP_LENGTH * 8
    # center=False vermeidet Reflect-Padding an den Raendern: Mit Padding
    # erzeugen die ersten Frames eines reinen Sinus einen Kanten-Artefakt,
    # der jede echte Uebergangsstelle im Signal ueberstrahlt.
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop, center=False)
    mfcc = (mfcc - mfcc.mean(axis=1, keepdims=True)) / (
        mfcc.std(axis=1, keepdims=True) + 1e-9
    )

    diff = np.linalg.norm(np.diff(mfcc, axis=1), axis=0)
    fenster = max(3, int(5.0 * sr / hop))
    kern = np.ones(fenster) / fenster
    novelty = np.convolve(diff, kern, mode="same")

    if novelty.size == 0 or novelty.std() <= 0:
        return []
    z = (novelty - novelty.mean()) / novelty.std()

    zeiten = librosa.frames_to_time(np.arange(len(z)), sr=sr, hop_length=hop)
    kandidaten = [(float(z[i]), float(zeiten[i])) for i in range(len(z)) if z[i] >= schwelle]
    kandidaten.sort(reverse=True)

    gewaehlt: list[float] = []
    for _, t in kandidaten:
        if all(abs(t - g) >= min_abstand_s for g in gewaehlt):
            gewaehlt.append(t)
    return sorted(gewaehlt)


@dataclass
class TransitionSample:
    """Messwerte eines stabilen Fensters neben einer Uebergangsstelle."""

    groove_pattern: list[float] = field(default_factory=list)
    bass_pattern: list[float] = field(default_factory=list)
    sub_energy: float = 0.0
    bass_punch: float = 0.0
    brightness: float = 0.0
    timbre: list[float] = field(default_factory=list)


def window_bounds(
    stelle: float, dauer: float,
    blend: float = BLEND_HALBBREITE_S, fenster: float = FENSTER_S,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Grenzen der stabilen Fenster vor und hinter einer Uebergangsstelle.

    None, wenn eines der Fenster nicht vollstaendig ins Signal passt — ein
    angeschnittenes Fenster wuerde verzerrte Kennzahlen liefern.
    """
    vor_ende = stelle - blend
    vor_start = vor_ende - fenster
    nach_start = stelle + blend
    nach_ende = nach_start + fenster
    if vor_start < 0.0 or nach_ende > dauer:
        return None
    return (vor_start, vor_ende), (nach_start, nach_ende)


def deltas_between(a: TransitionSample, b: TransitionSample) -> dict[str, float]:
    """Die vier Kennzahlen eines Uebergangs."""
    groove_sim = cosine_similarity(a.bass_pattern, b.bass_pattern)
    if groove_sim is None:
        groove_sim = cosine_similarity(a.groove_pattern, b.groove_pattern)
    timbre_sim = cosine_similarity(a.timbre, b.timbre)
    return {
        "groove_sim": float(groove_sim) if groove_sim is not None else 0.0,
        "sub_delta": abs(a.sub_energy - b.sub_energy),
        "punch_delta": abs(a.bass_punch - b.bass_punch),
        "brightness_delta": abs(a.brightness - b.brightness),
        "timbre_sim": float(timbre_sim) if timbre_sim is not None else 0.0,
    }


# Ab dieser AUC gilt die Trennung als belastbar genug fuer den Einbau.
HOLDOUT_AUC_MIN = 0.65


def discrimination_auc(
    echte: list[float], zufaellige: list[float], hoeher_ist_besser: bool = True
) -> float:
    """Trennschaerfe als AUC: Anteil der Paare, die richtig geordnet sind.

    0.5 heisst "der Faktor unterscheidet echte Uebergaenge nicht von
    zufaelligen" und fuehrt spaeter zu geringem Gewicht.
    """
    if not echte or not zufaellige:
        return 0.5
    treffer = 0.0
    gesamt = 0
    for e in echte:
        for z in zufaellige:
            gesamt += 1
            if e == z:
                treffer += 0.5
            elif (e > z) == hoeher_ist_besser:
                treffer += 1.0
    return float(treffer / gesamt) if gesamt else 0.5


def tolerance_percentile(werte: list[float], perzentil: float = 90.0) -> float | None:
    """Grenze, die in `perzentil` Prozent der echten Uebergaenge gilt."""
    if not werte:
        return None
    return float(np.percentile(np.asarray(werte, dtype=float), perzentil))


def learn_weights(auc: dict[str, float], gesamt: float = 0.30) -> dict[str, float]:
    """Verteilt `gesamt` auf die Faktoren nach ihrer Trennschaerfe.

    Grundlage ist der Abstand zu 0.5 — ein Faktor, der nichts unterscheidet,
    bekommt nur den Gleichanteil.
    """
    if not auc:
        return {}
    ueberschuss = {k: max(0.0, v - 0.5) for k, v in auc.items()}
    summe = sum(ueberschuss.values())
    if summe <= 0.0:
        gleich = gesamt / len(auc)
        return {k: gleich for k in auc}
    return {k: gesamt * (v / summe) for k, v in ueberschuss.items()}


def holdout_passed(
    echte_scores: list[float], zufall_scores: list[float],
    schwelle: float = HOLDOUT_AUC_MIN,
) -> bool:
    """Prueft am zurueckgehaltenen Mix, ob echte Uebergaenge hoeher scoren.

    Faellt der Test durch, taugen die gelernten Werte fuer dieses Genre nicht
    und werden NICHT eingebaut.
    """
    return discrimination_auc(echte_scores, zufall_scores, True) >= schwelle

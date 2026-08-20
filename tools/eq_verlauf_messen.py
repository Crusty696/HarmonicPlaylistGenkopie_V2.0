"""CLI-Werkzeug: misst den Baenderverlauf um Uebergaenge in echten DJ-Mixen.

Beantwortet, was ein DJ waehrend eines Uebergangs mit den Frequenzbaendern
tut — laufen Bass und Sub durch, waehrend Mitten und Hoehen zurueckgenommen
werden?

Stand 2026-08-20: der Renderer zieht daraus KEINE Konsequenz. Eine
Mitten-Mulde im `pro_eq_swap` wurde auf Basis dieses Werkzeugs gebaut und
wieder zurueckgebaut — die Begruendung steht im Kommentar bei den
Mids-Envelopes in `_apply_eq_crossfade`.

Vorgehen je Mix:
  1. Uebergangsstellen ueber `find_transitions` (hpg_core/mix_analysis.py).
  2. Je Sekunde drei Bandpegel und die Onset-Dichte messen.
  3. Fenster um jede Stelle sammeln, ebenso um gleich viele Zufallsstellen
     aus demselben Mix — ohne Kontrollgruppe ist ein Verlauf nicht deutbar.
  4. Trennschaerfe als AUC, geclustert nach Mix ueber `cluster_bootstrap_auc`.
     Uebergaenge desselben Mixes teilen Mastering und Aufnahmekette; sie als
     unabhaengig zu behandeln macht das Intervall zu eng.

Die Blendenlaenge wird aus der Breite der Onset-Erhoehung GESCHAETZT (nicht
gemessen; Trennschaerfe gegen Zufallsstellen rund 0,64) und die Auswertung
danach stratifiziert.

Ergebnis der bisher groessten Messung (275 Uebergaenge aus 13 Mixen): das
Mittenband liegt waehrend eines Uebergangs tiefer als davor und danach
(AUC 0.655 [0.601, 0.715]), aber GLEICHMAESSIG — die Differenz zwischen
Blendenmitte und Blendenrand enthaelt in jeder Laengengruppe die Null.

Wichtig fuer jede Wiederholung: die Bandgrenzen muessen die Crossover des
Renderers treffen. Eine erste Fassung mass die Mitten als 250-2500 Hz und
lieferte scheinbar klare Werte — der Renderer trennt aber bei 120 Hz, und die
Oktave 120-250 Hz traegt keine Mulde.

Aufruf:
  python tools/eq_verlauf_messen.py --mix "D:/Sets/*.mp3" --out ergebnis.json

Trennung von reiner Logik und Aussenwelt (Testbarkeit):
- REIN: `band_am_punkt`, `blendenbreite`, `muldentiefe`, `sekundenprofil`
  (rechnet nur auf Arrays, aber teuer)
- AUSSENWELT: `sammle_fenster` (Datei), `main`
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import librosa
import numpy as np
from scipy.signal import butter, sosfiltfilt

from hpg_core.mix_analysis import cluster_bootstrap_auc, find_transitions

logger = logging.getLogger("eq_verlauf")

SR = 22050
FENSTER_S = 60          # halbe Fensterbreite um jede Stelle
ABSTAND_S = 100.0       # Mindestabstand zwischen erkannten Uebergaengen
SCHWELLE = 1.5          # Novelty-Schwelle; darunter wird die Auswahl beliebig
# Die Bandgrenzen sind die Crossover des Renderers (fc1=120, fc2=2500 in
# _apply_eq_crossfade), damit gemessenes und angefasstes Band deckungsgleich
# sind. Eine fruehere Fassung mass 250-2500 und haette die Oktave 120-250 Hz
# ungemessen mit abgesenkt.
BAENDER = ((20, 120, "sub"), (120, 2500, "mitten"), (2500, 10000, "hoehen"))
MITTEN_INDEX = 1        # Position der Mitten in BAENDER
MIN_GRUPPE = 30         # weniger Uebergaenge tragen keine Gruppenaussage


def sekundenprofil(y: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Je Sekunde: ein Bandpegel (RMS) je Band und die Onset-Dichte."""
    n = sr
    anzahl = len(y) // n
    baender = np.zeros((len(BAENDER), anzahl), dtype=np.float32)
    for k, (lo, hi, _name) in enumerate(BAENDER):
        sos = butter(4, [lo, hi], btype="band", fs=sr, output="sos")
        gefiltert = sosfiltfilt(sos, y)
        baender[k] = [
            np.sqrt(np.mean(gefiltert[i * n:(i + 1) * n] ** 2)) for i in range(anzahl)
        ]
    hop = 512
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    je_sekunde = int(sr / hop)
    dichte = np.array([
        onset[i * je_sekunde:(i + 1) * je_sekunde].mean()
        if (i + 1) * je_sekunde <= len(onset) else 0.0
        for i in range(anzahl)
    ])
    return baender, dichte


def sammle_fenster(pfad: str, seed: int) -> tuple[list[dict], list[dict]]:
    """Fenster um echte Uebergaenge und um ebenso viele Zufallsstellen."""
    y, sr = librosa.load(pfad, sr=SR, mono=True)
    baender, dichte = sekundenprofil(y, sr)
    bezug_b = np.median(baender, axis=1, keepdims=True) + 1e-9
    bezug_o = np.median(dichte) + 1e-9
    laenge = baender.shape[1]
    stellen = [int(t) for t in find_transitions(y, sr, min_abstand_s=ABSTAND_S,
                                                schwelle=SCHWELLE)]
    gueltig = [i for i in stellen if FENSTER_S <= i < laenge - FENSTER_S]

    def schnipsel(idx: int) -> dict:
        return {
            "b": (baender[:, idx - FENSTER_S:idx + FENSTER_S + 1] / bezug_b).tolist(),
            "o": (dichte[idx - FENSTER_S:idx + FENSTER_S + 1] / bezug_o).tolist(),
        }

    echte = [schnipsel(i) for i in gueltig]
    rng = np.random.default_rng(seed)
    zufaellige: list[dict] = []
    versuche = 0
    while len(zufaellige) < len(gueltig) and versuche < 1000:
        versuche += 1
        idx = int(rng.integers(FENSTER_S, laenge - FENSTER_S))
        if any(abs(idx - s) < FENSTER_S for s in stellen):
            continue
        zufaellige.append(schnipsel(idx))
    return echte, zufaellige


def band_am_punkt(fenster: list[dict], band: int) -> np.ndarray:
    """Bandpegel in der Uebergangsmitte, bezogen auf das eigene Umfeld.

    Der Bezug ist bewusst das Umfeld DESSELBEN Uebergangs (-45..-20 und
    +20..+45 s), nicht der Mix-Median: so faellt heraus, ob an der Stelle
    generell lautes oder leises Material laeuft.
    """
    A = np.array([m["b"][band] for m in fenster])
    mitte = A.shape[1] // 2
    umfeld = np.concatenate(
        [A[:, mitte - 45:mitte - 20], A[:, mitte + 20:mitte + 45]], axis=1
    )
    return A[:, mitte - 3:mitte + 4].mean(axis=1) / (np.median(umfeld, axis=1) + 1e-9)


def blendenbreite(fenster: dict) -> float:
    """Blendenlaenge aus der Breite der Onset-Erhoehung.

    Laufen zwei Tracks uebereinander, liegen mehr Schlaege je Sekunde an. Die
    Schaetzung ist grob (Trennschaerfe gegen Zufallsstellen 0,636, gemessen an
    76 echten gegen 82 zufaellige Stellen aus 6 Mixen) und taugt zur
    Gruppenbildung, nicht als Einzelwert.
    """
    o = np.array(fenster["o"])
    mitte = len(o) // 2
    basis = np.median(np.concatenate([o[:15], o[-15:]]))
    ueber = o > basis * 1.10
    if not ueber[mitte - 1:mitte + 2].any():
        return 0.0
    links = mitte
    while links > 0 and ueber[links - 1]:
        links -= 1
    rechts = mitte
    while rechts < len(ueber) - 1 and ueber[rechts + 1]:
        rechts += 1
    return float(rechts - links + 1)


def muldentiefe(fenster: list[dict], blende_s: float) -> float:
    """Wie tief liegen die Mitten in der Blendenmitte gegen den Blendenrand?

    Diese Groesse braeuchte der Renderer fuer einen Bandgain ueber der
    Blendkurve: ein solcher Gain waere an den Crossfade-Raendern auf 1.0
    verankert, entscheidend ist also die Differenz zwischen Mitte und Rand —
    nicht die absolute Absenkung. Gemessen wurde sie nicht signifikant.
    """
    A = np.array([m["b"][MITTEN_INDEX] for m in fenster])
    mitte = A.shape[1] // 2
    umfeld = np.concatenate(
        [A[:, mitte - 45:mitte - 20], A[:, mitte + 20:mitte + 45]], axis=1
    )
    kurve = np.median(A / (np.median(umfeld, axis=1, keepdims=True) + 1e-9), axis=0)
    radius = max(1, min(int(round(blende_s / 2)), mitte - 1))
    return float(1.0 - kurve[mitte] / kurve[mitte + radius])


def muldentiefe_mit_bereich(
    fenster: list[dict], blende_s: float, ziehungen: int = 1000, seed: int = 7
) -> tuple[float, float, float]:
    """Muldentiefe samt 95-%-Bereich, gebootstrappt ueber die Uebergaenge.

    Der Punktschaetzer allein sagt nichts darueber, ob eine Gruppe den Wert
    ueberhaupt traegt. In der Messung vom 2026-08-20 lag die Null in JEDER
    Laengengruppe im Bereich — deshalb faehrt der Renderer keine Mulde.
    Genau diese Unterscheidung ist der Zweck der Funktion.
    """
    punkt = muldentiefe(fenster, blende_s)
    if len(fenster) < 2:
        return punkt, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    verteilung = []
    for _ in range(ziehungen):
        auswahl = [fenster[i] for i in rng.integers(0, len(fenster), len(fenster))]
        verteilung.append(muldentiefe(auswahl, blende_s))
    return punkt, float(np.percentile(verteilung, 2.5)), float(np.percentile(verteilung, 97.5))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mix", action="append", required=True, dest="mixe",
                        help="Pfad oder Glob-Muster; mehrfach angebbar")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    pfade: list[str] = []
    for muster in args.mixe:
        pfade.extend(sorted(glob.glob(muster)))
    if not pfade:
        logger.error("Keine Dateien gefunden.")
        return 1

    echt_je_mix: list[list[dict]] = []
    zufall_je_mix: list[list[dict]] = []
    alle_echt: list[dict] = []
    for pfad in pfade:
        try:
            echte, zufaellige = sammle_fenster(pfad, args.seed)
        except Exception as fehler:  # noqa: BLE001 — ein defekter Mix darf nicht abbrechen
            logger.warning("%s uebersprungen: %s", Path(pfad).name, fehler)
            continue
        if not echte or not zufaellige:
            logger.warning("%s: keine verwertbaren Stellen", Path(pfad).name)
            continue
        echt_je_mix.append(echte)
        zufall_je_mix.append(zufaellige)
        alle_echt.extend(echte)
        logger.info("%-44s %3d Uebergaenge", Path(pfad).name[:44], len(echte))

    if len(echt_je_mix) < 2:
        logger.error("Mindestens zwei Mixe noetig — mit einem Cluster laesst sich "
                     "die Streuung zwischen Mixen nicht schaetzen.")
        return 1

    ergebnis: dict = {
        "mixe": len(echt_je_mix),
        "uebergaenge": len(alle_echt),
        "baender": {},
        "mulde": {},
    }
    logger.info("\n%d Mixe, %d Uebergaenge", len(echt_je_mix), len(alle_echt))
    logger.info("\nTrennschaerfe gegen Kontrollstellen (geclustert nach Mix):")
    for band, (_lo, _hi, name) in enumerate(BAENDER):
        echte = [list(band_am_punkt(f, band)) for f in echt_je_mix]
        zufall = [list(band_am_punkt(f, band)) for f in zufall_je_mix]
        punkt, unten, oben = cluster_bootstrap_auc(
            echte, zufall, hoeher_ist_besser=False, seed=args.seed
        )
        ergebnis["baender"][name] = {"auc": punkt, "unten": unten, "oben": oben}
        urteil = "trennt" if unten > 0.5 else "kein Beleg"
        logger.info("   %-7s AUC %.3f  95-%%-Bereich [%.3f, %.3f]   %s",
                    name, punkt, unten, oben, urteil)

    breiten = np.array([blendenbreite(f) for f in alle_echt])
    logger.info("\nMuldentiefe nach Blendenlaenge:")
    for name, maske in (("kurz", breiten <= 8),
                        ("mittel", (breiten > 8) & (breiten <= 25)),
                        ("lang", breiten > 25)):
        anzahl = int(maske.sum())
        if anzahl < MIN_GRUPPE:
            logger.info("   %-7s n=%d — zu wenige fuer eine Aussage", name, anzahl)
            continue
        gruppe = [f for f, m in zip(alle_echt, maske) if m]
        typisch = float(np.median(breiten[maske]))
        tiefe, unten, oben = muldentiefe_mit_bereich(gruppe, typisch, seed=args.seed)
        traegt = unten > 0.0
        ergebnis["mulde"][name] = {
            "n": anzahl, "blende_s": typisch, "faktor": tiefe,
            "unten": unten, "oben": oben, "traegt": traegt,
        }
        logger.info("   %-7s n=%3d  Blende %4.0f s  Faktor %+.3f "
                    "[%+.3f, %+.3f]  (%+.2f dB)  %s",
                    name, anzahl, typisch, tiefe, unten, oben,
                    20 * np.log10(max(1e-6, 1.0 - tiefe)),
                    "traegt" if traegt else "Null im Bereich")

    args.out.write_text(json.dumps(ergebnis, indent=2), encoding="utf-8")
    logger.info("\ngeschrieben: %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

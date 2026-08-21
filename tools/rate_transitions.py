"""CLI-Werkzeug: Uebergaenge selbst bewerten und daraus Scoring-Gewichte schaetzen.

Warum: die vier neuen Transition-Faktoren (Groove, Bassdruck, Klangfarbe,
Stimmung) haben ungemessene Gewichte. Der Versuch, sie aus fremden DJ-Mixen zu
lernen, scheiterte an der Zahl unabhaengiger Mixe (Gewichtsbudget 0,012 bzw.
0,000). Hundert selbst bewertete Uebergaenge tragen mehr Information, weil sie
den Geschmack des Nutzers abbilden statt einer Hilfsannahme darueber.

Aufruf:
    python tools/rate_transitions.py prepare --anzahl 100 --out D:\\hoertest
    python tools/hoertest_server.py --dir D:\\hoertest
    (Nutzer bewertet im Browser mit 1 bis 5, die Seite schreibt bewertung.csv)
    python tools/rate_transitions.py fit --dir D:\\hoertest

Trennung von reiner Logik und Aussenwelt (Testbarkeit):
- REIN (ohne Audio, ohne Dateisystem, ohne Cache): `maximin_auswahl`,
  `verbinde_bewertungen`, `zu_zielgroesse`, `negative_log_likelihood`,
  `fit_logistic`, `bootstrap_intervalle`, `waehle_merkmale`,
  `datenlage_urteil`,
  `leite_gewichte_ab`, `baue_genre_gewichte`, `streuung`, `filtere_nach_genre`,
  `crossfade_reserve`, `baue_ausgabe_json`.
- AUSSENWELT: `lade_tracks_aus_cache` (SQLite), `sammle_kandidaten` (Core-
  Scoring), `geplanter_overlap` (Core-Scoring), `rendere_paar` (Audio),
  `lies_csv` / `schreibe_csv`, `main`.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import sqlite3
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from scipy.optimize import minimize

from hpg_core.caching import CACHE_FILE, dict_to_track
from hpg_core.dj_brain import calculate_paired_mix_points
from hpg_core.downbeat import (
    DOWNBEAT_RELIABLE_MIN,
    REFERENCE_BEATGRID_CONFIDENCE,
)
from hpg_core.genres import CANONICAL_GENRES, GENRE_TRANSITION_TOLERANCES
from hpg_core.models import Track, effective_bpm_diff
from hpg_core.playlist import (
    calculate_enhanced_compatibility,
    compute_transition_recommendations,
)
from hpg_core.transition_features import (
    bass_continuity,
    groove_match,
    mood_match,
    timbre_match,
)
from hpg_core.transition_renderer import TransitionClipSpec, render_transition_clip

logger = logging.getLogger("rate_transitions")

# --- Faktoren -------------------------------------------------------------
# Die vier neuen Faktoren, deren Gewicht geschaetzt werden soll.
NEUE_FAKTOREN: tuple[str, ...] = ("groove", "bass", "timbre", "mood")
# Die vier klassischen Faktoren laufen als KONTROLLVARIABLEN mit: ohne sie
# wuerde ihr Beitrag zum Urteil faelschlich den neuen Faktoren zugeschlagen.
KLASSISCHE_FAKTOREN: tuple[str, ...] = ("harmonic", "bpm", "energy", "genre")
ALLE_FAKTOREN: tuple[str, ...] = NEUE_FAKTOREN + KLASSISCHE_FAKTOREN

# --- Auswahl / Rendern ----------------------------------------------------
STANDARD_BPM_TOLERANZ = 6.0
MIN_HARMONIC_SCORE = 60
# Feste Blende fuer ALLE Hoertest-Clips: reine 3-Band-EQ-Blende ohne Echo,
# Cut oder Filter-Sweep. Vorher lief je Paar predict_transition_type, damit
# variierte der Effekt von Clip zu Clip und ging als nicht erfasste
# Stoergroesse in die Note ein (Konfundierung). Umgestellt 2026-08-21, alle
# Noten aus der Zeit davor wurden verworfen.
HOERTEST_TRANSITION_TYPE = "pro_eq_swap"
# Fester Seed: eine Vorbereitung mit denselben Tracks liefert denselben Satz.
STANDARD_SEED = 20260820
# Rueckfall-Crossfade, wenn fuer ein Paar keine Uebergangs-Empfehlung
# vorliegt. Der Regelfall ist die INDIVIDUELLE Blendenlaenge des Paares
# (siehe rendere_paar): die App plant sie pro Uebergang aus transition_bars,
# gemessen an 148 Paaren Median 46,1 s bei einer Spanne von 17,3 bis 64,0 s.
# Eine feste Laenge fuer alle Clips waere zwar als Stoergroesse sauber
# kontrolliert, wuerde aber einen Uebergang bewerten lassen, den die App so
# nie baut. Preis dieser Entscheidung: die ungemessenen transition_bars-
# Intervalle aus genres.py gehen ins Urteil mit ein — eine schlechte Note
# kann "Faktoren passen nicht" ODER "Blende war zu lang" heissen. Deshalb
# wird die tatsaechlich benutzte Laenge je Clip in merkmale.csv mitgefuehrt.
CROSSFADE_SEK = 32.0
PRE_ROLL_SEK = 8.0
POST_ROLL_SEK = 8.0
# Wie viele Kandidaten ueber die gewuenschte Anzahl hinaus in die Warteschlange
# kommen, damit uebersprungene Paare ersetzt werden koennen.
RESERVE_FAKTOR = 4
# Standardumfang des Hoertests. 100 Bewertungen reichen bei den vier neuen
# Faktoren allein fuer die Faustregel (40 Ereignisse je Klasse), sofern das
# Urteil einigermassen ausgewogen ausfaellt.
STANDARD_ANZAHL = 100

# --- Schaetzung -----------------------------------------------------------
# L2-Staerke auf den standardisierten Steigungen (der Achsenabschnitt bleibt
# frei). Entspricht einem Normal-Prior mit Standardabweichung
# 1/sqrt(2*L2) ~ 0,71 je Koeffizient: ein Effekt groesser als Faktor e^1,4 in
# den Chancen pro Standardabweichung gilt a priori als unwahrscheinlich. Bei
# der hier ueblichen Zahl von Bewertungen und Merkmalen ist ohne diese Bremse
# jede Trennung perfekt und jeder Koeffizient beliebig gross.
L2_STAERKE = 1.0
BOOTSTRAP_ZIEHUNGEN = 500
BUDGET_MAX = 0.30
# Skala, ab der ein standardisierter Koeffizient als "voller" Effekt gilt und
# das Budget ausschoepft (Chancen-Faktor e^1 ~ 2,7 pro Standardabweichung).
KOEFFIZIENT_VOLLAUSSCHLAG = 1.0
# Faustregel fuer logistische Regression: mindestens 10 Ereignisse je Merkmal
# — und zwar in BEIDEN Klassen.
MIN_EREIGNISSE_JE_MERKMAL = 10

# Mindest-Standardabweichung, ab der ein klassischer Faktor als Kontroll-
# variable in die Regression kommt. Begruendung: `prepare` filtert bereits auf
# harmonic_score >= 60 und BPM innerhalb der Toleranz — die klassischen
# Faktoren streuen im bewerteten Satz deshalb kaum. Alle vier trotzdem
# mitzuschaetzen kostet vier Freiheitsgrade, ohne etwas zu erklaeren, und
# verschaerft die Faustregel "10 Ereignisse je Merkmal" von 40 auf 80
# Bewertungen je Klasse. Die Faktoren liegen in [0, 1]; 0,05 heisst "der
# Faktor variiert um weniger als 5 % seines Wertebereichs" — daraus laesst
# sich kein Beitrag schaetzen.
MIN_KONTROLL_STREUUNG = 0.05

BEWERTUNG_MIN = 1
BEWERTUNG_MAX = 5
# Ab dieser Note gilt ein Uebergang als "gut" (Zielgroesse der Regression).
GUT_AB = 4


# ===========================================================================
# Reine Logik — Auswahl
# ===========================================================================

def maximin_auswahl(
    vektoren,
    anzahl: int,
    seed: int = STANDARD_SEED,
    start: int | None = None,
) -> list[int]:
    """Maximin-Auswahl (farthest-point sampling) im Merkmalsraum.

    Zufaellig ziehen liefert hundert fast identische Uebergaenge, weil die
    Kandidatenmenge im Zentrum verklumpt — die spaetere Schaetzung haette dann
    keinen Kontrast. Hier wird der erste Kandidat gezogen und danach jeweils
    der aufgenommen, dessen kleinster Abstand zu den bereits Gewaehlten am
    groessten ist. Das deckt den Merkmalsraum ab.

    Gibt die Indizes der gewaehlten Kandidaten zurueck.
    """
    punkte = np.asarray(vektoren, dtype=float)
    if punkte.size == 0:
        return []
    gesamt = punkte.shape[0]
    anzahl = min(int(anzahl), gesamt)
    if anzahl <= 0:
        return []

    if start is None:
        start = random.Random(seed).randrange(gesamt)
    gewaehlt = [int(start)]
    # Kleinster Abstand jedes Kandidaten zu der bereits gewaehlten Menge.
    min_abstand = np.linalg.norm(punkte - punkte[start], axis=1)
    min_abstand[start] = -1.0

    while len(gewaehlt) < anzahl:
        naechster = int(np.argmax(min_abstand))
        if min_abstand[naechster] < 0.0:
            break  # alle Kandidaten bereits gewaehlt
        gewaehlt.append(naechster)
        min_abstand = np.minimum(
            min_abstand, np.linalg.norm(punkte - punkte[naechster], axis=1)
        )
        min_abstand[naechster] = -1.0
    return gewaehlt


def crossfade_reserve(
    mix_out_a: float, dauer_a: float, dauer_b: float, mix_in_b: float
) -> tuple[float, float]:
    """Wieviel Audio steht in beiden Tracks fuer den Crossfade zur Verfuegung.

    Beide Tracks laufen waehrend der Blende VORWAERTS ab ihrem Mixpunkt
    (Vertrag mit dem Renderer, siehe Ladefenster in render_transition_clip:
    `a_start = mix_out - pre_roll`, `a_dur = pre_roll + cf_sec`).
    Nutzbar ist damit die Restdauer HINTER dem jeweiligen Mixpunkt.

    Fix 2026-08-20: die A-Seite rechnete vorher ``mix_out_a - PRE_ROLL_SEK``,
    also das Audio VOR dem Mix-Out. Das ist die falsche Region — der Vorlauf
    wird vom Renderer ohnehin auf 0 geklemmt, wenn er nicht reicht (C1-Fix),
    waehrend fehlendes Audio hinter dem Mix-Out von ``_ensure_len`` still mit
    Nullen aufgefuellt wird.

    Reichweite des Fixes, damit sie nicht ueberschaetzt wird: BEI DER FESTEN
    32-s-BLENDE waeren 12 von 148 Paaren mitten in der Blende in Stille
    gelaufen, bis zu 14,7 s lang. Mit dem Plan-Overlap sind es 0 von 148,
    weil ``_clamp_transition_overlap`` in playlist.py den Overlap
    bereits auf ``duration_a - mix_out_a`` klemmt — die kleinste gemessene
    Blende von 17,3 s ist genau dieser Klemmfall. Der Fix sichert damit den
    Fallback-Pfad ab (CROSSFADE_SEK), nicht den Regelfall.

    Reicht es nicht, wird das Paar verworfen statt die Blende zu kuerzen.
    """
    return (
        float(dauer_a) - float(mix_out_a),
        float(dauer_b) - float(mix_in_b) - POST_ROLL_SEK,
    )


def streuung(werte) -> dict:
    """Min/Median/Max einer Werteliste — der Kontrast-Nachweis der Auswahl."""
    zahlen = [float(w) for w in werte]
    if not zahlen:
        return {"min": None, "median": None, "max": None}
    return {
        "min": min(zahlen),
        "median": statistics.median(zahlen),
        "max": max(zahlen),
    }


# ===========================================================================
# Reine Logik — CSV verbinden
# ===========================================================================

def verbinde_bewertungen(
    merkmale_zeilen, bewertung_zeilen
) -> tuple[list[dict], int, int]:
    """Verbindet Merkmals- und Bewertungszeilen ueber `pair_id`.

    Rueckgabe: (verbundene Zeilen, Anzahl ohne Bewertung, Anzahl ungueltig).
    "Ungueltig" heisst: eine Eintragung, die keine ganze Zahl von 1 bis 5 ist —
    die wird gemeldet und NICHT stillschweigend als "nicht bewertet" gezaehlt.
    """
    noten: dict[str, str] = {
        str(z.get("pair_id", "")).strip(): str(z.get("bewertung", "")).strip()
        for z in bewertung_zeilen
    }

    zeilen: list[dict] = []
    ohne = 0
    ungueltig = 0
    for roh in merkmale_zeilen:
        pair_id = str(roh.get("pair_id", "")).strip()
        eintrag = noten.get(pair_id, "")
        if not eintrag:
            ohne += 1
            continue
        try:
            note = int(round(float(eintrag)))
        except (TypeError, ValueError):
            ungueltig += 1
            continue
        if not BEWERTUNG_MIN <= note <= BEWERTUNG_MAX:
            ungueltig += 1
            continue
        try:
            merkmale = {name: float(roh[name]) for name in ALLE_FAKTOREN}
        except (KeyError, TypeError, ValueError):
            ungueltig += 1
            continue
        zeilen.append({"pair_id": pair_id, "bewertung": note, "merkmale": merkmale})
    return zeilen, ohne, ungueltig


def waehle_merkmale(
    zeilen, min_streuung: float = MIN_KONTROLL_STREUUNG
) -> tuple[list[str], dict[str, float]]:
    """Bestimmt, welche Merkmale in die Regression kommen.

    Die vier NEUEN Faktoren sind immer dabei — sie sind der Gegenstand der
    Schaetzung. Ein klassischer Faktor kommt nur als Kontrollvariable dazu,
    wenn er im bewerteten Satz ueberhaupt streut (siehe
    MIN_KONTROLL_STREUUNG). Rueckgabe: (aktive Merkmale, Streuung je Faktor).
    """
    streuungen: dict[str, float] = {}
    for name in ALLE_FAKTOREN:
        werte = [float(z["merkmale"][name]) for z in zeilen]
        streuungen[name] = float(np.std(werte)) if werte else 0.0

    aktiv = list(NEUE_FAKTOREN)
    aktiv += [
        name for name in KLASSISCHE_FAKTOREN
        if streuungen[name] >= min_streuung
    ]
    return aktiv, streuungen


def zu_zielgroesse(zeilen, merkmale=ALLE_FAKTOREN) -> tuple[np.ndarray, np.ndarray]:
    """Baut Merkmalsmatrix X und Zielvektor y (gut = Note >= 4)."""
    namen = list(merkmale)
    X = np.array(
        [[z["merkmale"][name] for name in namen] for z in zeilen],
        dtype=float,
    ).reshape(len(zeilen), len(namen))
    y = np.array([1.0 if z["bewertung"] >= GUT_AB else 0.0 for z in zeilen])
    return X, y


# ===========================================================================
# Reine Logik — logistische Regression
# ===========================================================================

def _standardisiere(X: np.ndarray) -> np.ndarray:
    """Z-Transformation je Spalte; konstante Spalten werden zu Null.

    Ohne sie waeren die Koeffizienten nicht vergleichbar (jeder Faktor haette
    seine eigene Skala) und das Gewichtsbudget nicht ableitbar.
    """
    X = np.asarray(X, dtype=float)
    mittel = X.mean(axis=0)
    streuungen = X.std(axis=0)
    sicher = np.where(streuungen > 1e-12, streuungen, 1.0)
    Xz = (X - mittel) / sicher
    Xz[:, streuungen <= 1e-12] = 0.0
    return Xz


def negative_log_likelihood(
    beta: np.ndarray, X: np.ndarray, y: np.ndarray, l2: float
) -> float:
    """Negative Log-Likelihood der Logit-Regression mit L2-Strafe.

    `beta[0]` ist der Achsenabschnitt und bleibt UNBESTRAFT — sonst wuerde die
    Strafe die Grundhaeufigkeit "gut" verzerren.
    """
    beta = np.asarray(beta, dtype=float)
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    z = beta[0] + X @ beta[1:]
    # Numerisch stabile Form von log(1 + exp(z)).
    log1pexp = np.logaddexp(0.0, z)
    nll = float(np.sum(log1pexp - y * z))
    return nll + l2 * float(np.dot(beta[1:], beta[1:]))


def _gradient(beta: np.ndarray, X: np.ndarray, y: np.ndarray, l2: float) -> np.ndarray:
    """Analytischer Gradient — spart Funktionsauswertungen im Bootstrap."""
    z = beta[0] + X @ beta[1:]
    p = 1.0 / (1.0 + np.exp(-np.clip(z, -500.0, 500.0)))
    rest = p - y
    grad = np.empty_like(beta)
    grad[0] = float(np.sum(rest))
    grad[1:] = X.T @ rest + 2.0 * l2 * beta[1:]
    return grad


def _fit_standardisiert(Xz: np.ndarray, y: np.ndarray, l2: float) -> np.ndarray:
    """Optimiert die regularisierte Log-Likelihood auf bereits skalierten Daten."""
    start = np.zeros(Xz.shape[1] + 1)
    ergebnis = minimize(
        negative_log_likelihood,
        start,
        args=(Xz, y, l2),
        jac=_gradient,
        method="L-BFGS-B",
    )
    return np.asarray(ergebnis.x, dtype=float)


def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = L2_STAERKE) -> np.ndarray:
    """Logistische Regression mit L2-Strafe; kein sklearn, nur scipy.

    Rueckgabe: [Achsenabschnitt, Steigung_1, ...] auf STANDARDISIERTER Skala,
    also "Veraenderung des Logits je Standardabweichung des Faktors".
    """
    return _fit_standardisiert(_standardisiere(X), np.asarray(y, dtype=float), l2)


def bootstrap_intervalle(
    X: np.ndarray,
    y: np.ndarray,
    l2: float = L2_STAERKE,
    ziehungen: int = BOOTSTRAP_ZIEHUNGEN,
    seed: int = STANDARD_SEED,
    namen=ALLE_FAKTOREN,
) -> dict[str, tuple[float, float]]:
    """95-%-Bootstrap-Bereich je Koeffizient (Ziehen mit Zuruecklegen).

    Standardisiert wird EINMAL mit den Kennzahlen der Gesamtstichprobe, damit
    alle Ziehungen dieselbe Skala haben und die Perzentile vergleichbar sind.
    Ziehungen mit nur einer Klasse werden verworfen — dort ist der Koeffizient
    nicht definiert.
    """
    Xz = _standardisiere(X)
    y = np.asarray(y, dtype=float)
    n = Xz.shape[0]
    rng = np.random.default_rng(seed)
    gesammelt: list[np.ndarray] = []
    for _ in range(int(ziehungen)):
        index = rng.integers(0, n, size=n)
        y_zug = y[index]
        if y_zug.min() == y_zug.max():
            continue
        gesammelt.append(_fit_standardisiert(Xz[index], y_zug, l2)[1:])

    namen = list(namen)
    if not gesammelt:
        return {name: (0.0, 0.0) for name in namen}
    stapel = np.vstack(gesammelt)
    unten = np.percentile(stapel, 2.5, axis=0)
    oben = np.percentile(stapel, 97.5, axis=0)
    return {
        name: (float(unten[i]), float(oben[i]))
        for i, name in enumerate(namen)
    }


# ===========================================================================
# Reine Logik — Datenlage und Gewichte
# ===========================================================================

def datenlage_urteil(
    n_gut: int, n_schlecht: int, n_merkmale: int
) -> tuple[bool, str]:
    """Prueft die Faustregel "10 Ereignisse je Merkmal" in BEIDEN Klassen."""
    noetig = MIN_EREIGNISSE_JE_MERKMAL * int(n_merkmale)
    if n_gut >= noetig and n_schlecht >= noetig:
        return True, (
            f"Datenlage tragfaehig: {n_gut} mal 'gut' und {n_schlecht} mal "
            f"'nicht gut', jeweils mindestens {noetig}."
        )
    return False, (
        f"Datenlage NICHT BELASTBAR: {n_gut} mal 'gut' und {n_schlecht} mal "
        f"'nicht gut'. Fuer {n_merkmale} Merkmale braucht die logistische "
        f"Regression mindestens {noetig} Faelle JE Klasse "
        f"(Faustregel {MIN_EREIGNISSE_JE_MERKMAL} Ereignisse je Merkmal). "
        f"Die Koeffizienten unten sind Zwischenstaende, keine Messung — es "
        f"werden deshalb KEINE Gewichte vergeben."
    )


def leite_gewichte_ab(
    koeffizienten: dict[str, float],
    intervalle: dict[str, tuple[float, float]],
    belastbar: bool,
    budget_max: float = BUDGET_MAX,
) -> dict[str, float]:
    """Verteilt Gewicht nach der UNTEREN Bootstrap-Grenze, nicht nach dem Punkt.

    Gleiches Prinzip wie `learn_weights_bounded` in hpg_core/mix_analysis.py:
    dort war die Nullhypothese AUC = 0,5, hier ist sie Koeffizient = 0. Ein
    Faktor, dessen Intervall die Null enthaelt, ist nicht von "wirkt nicht" zu
    unterscheiden und bekommt NICHTS. Ein Faktor mit gesichert NEGATIVEM
    Koeffizient bekommt ebenfalls nichts: das Scoring kennt nur "hoeher ist
    besser", ein negatives Gewicht liesse sich dort nicht abbilden — er wird
    stattdessen im Bericht ausgewiesen.

    Das Budget waechst mit der Staerke des besten gesicherten Faktors und ist
    bei `budget_max` gedeckelt. Ueberlebt keiner: Budget 0.
    """
    if not belastbar:
        return {name: 0.0 for name in NEUE_FAKTOREN}

    roh: dict[str, float] = {}
    for name in NEUE_FAKTOREN:
        unten, oben = intervalle.get(name, (0.0, 0.0))
        # Nur ein vollstaendig positives Intervall zaehlt als gesichert.
        gesichert = unten > 0.0 and oben > 0.0
        roh[name] = float(unten) if gesichert else 0.0

    summe = sum(roh.values())
    if summe <= 0.0:
        return {name: 0.0 for name in NEUE_FAKTOREN}
    budget = budget_max * min(1.0, max(roh.values()) / KOEFFIZIENT_VOLLAUSSCHLAG)
    return {name: budget * (wert / summe) for name, wert in roh.items()}


def baue_genre_gewichte(neue_gewichte: dict[str, float]) -> dict[str, float]:
    """Ergaenzt die vier neuen Gewichte zu einem vollstaendigen Satz von acht.

    Die vier klassischen Faktoren fuellen den Rest (1 - Budget) im Verhaeltnis
    ihrer Defaults auf. Das Scoring erwartet eine Summe von 1,0 je Genre
    (siehe `_validate_genre_tables` in hpg_core/genres.py).
    """
    budget = sum(max(0.0, float(w)) for w in neue_gewichte.values())
    budget = min(budget, 1.0)
    defaults = GENRE_TRANSITION_TOLERANCES[CANONICAL_GENRES[0]]
    klassisch_summe = sum(defaults[f"{name}_weight"] for name in KLASSISCHE_FAKTOREN)

    gewichte = {
        f"{name}_weight": round(max(0.0, float(neue_gewichte.get(name, 0.0))), 6)
        for name in NEUE_FAKTOREN
    }
    rest = 1.0 - sum(gewichte.values())
    for name in KLASSISCHE_FAKTOREN:
        anteil = defaults[f"{name}_weight"] / klassisch_summe
        gewichte[f"{name}_weight"] = round(rest * anteil, 6)

    # Rundungsrest auf den groessten klassischen Faktor legen, damit die Summe
    # exakt 1,0 ist — sonst schlaegt die Genre-Validierung fehl.
    differenz = 1.0 - sum(gewichte.values())
    groesster = max(KLASSISCHE_FAKTOREN, key=lambda n: defaults[f"{n}_weight"])
    gewichte[f"{groesster}_weight"] = round(
        gewichte[f"{groesster}_weight"] + differenz, 9
    )
    return gewichte


def baue_ausgabe_json(
    genres,
    neue_gewichte: dict[str, float],
    koeffizienten: dict[str, float],
    intervalle: dict[str, tuple[float, float]],
    n_bewertungen: int,
    n_gut: int,
    belastbar: bool,
    hinweis: str,
    aktive_merkmale=ALLE_FAKTOREN,
    streuungen: dict[str, float] | None = None,
) -> dict:
    """Baut das JSON im Format von hpg_core/data/transition_tolerances.json.

    Die Diagnose liegt unter `_diagnose`; `_merge` in hpg_core/tolerances.py
    uebernimmt nur kanonische Genre-Schluessel und ignoriert sie folgenlos.
    """
    genre_block = baue_genre_gewichte(neue_gewichte)
    ergebnis: dict = {genre: dict(genre_block) for genre in genres}
    ergebnis["_diagnose"] = {
        "quelle": "tools/rate_transitions.py fit",
        "anzahl_bewertungen": int(n_bewertungen),
        "anzahl_gut": int(n_gut),
        "anzahl_nicht_gut": int(n_bewertungen - n_gut),
        "belastbar": bool(belastbar),
        "hinweis": hinweis,
        "aktive_merkmale": list(aktive_merkmale),
        "merkmals_streuung": {
            k: round(float(v), 4) for k, v in (streuungen or {}).items()
        },
        "l2_staerke": L2_STAERKE,
        "bootstrap_ziehungen": BOOTSTRAP_ZIEHUNGEN,
        "koeffizienten": {k: round(float(v), 4) for k, v in koeffizienten.items()},
        "intervalle": {
            k: [round(float(v[0]), 4), round(float(v[1]), 4)]
            for k, v in intervalle.items()
        },
    }
    return ergebnis


# ===========================================================================
# Aussenwelt — Cache, Kandidaten, Rendern, Dateien
# ===========================================================================

def lade_tracks_aus_cache(db_pfad: str | None = None) -> list[Track]:
    """Liest alle analysierten Tracks aus der Cache-Datenbank."""
    pfad = Path(db_pfad or CACHE_FILE)
    if not pfad.is_file():
        raise FileNotFoundError(f"Cache-Datenbank nicht gefunden: {pfad}")

    tracks: list[Track] = []
    gesehen: set[str] = set()
    # Nur lesend oeffnen — die Datenbank des Nutzers wird nicht veraendert.
    conn = sqlite3.connect(f"file:{pfad.as_posix()}?mode=ro", uri=True)
    try:
        for key, roh in conn.execute("SELECT key, data FROM cache"):
            if key == "version":
                continue
            try:
                daten = json.loads(roh)
                track = dict_to_track(daten)
            except Exception as exc:  # noqa: BLE001 — eine defekte Zeile darf nicht abbrechen
                logger.debug("Cache-Zeile %s uebersprungen: %s", key, exc)
                continue
            if not track.filePath or track.filePath in gesehen:
                continue
            gesehen.add(track.filePath)
            tracks.append(track)
    finally:
        conn.close()
    return tracks


def loese_genre_auf(track: Track) -> str:
    """Genre wie im Scoring: erkanntes Genre schlaegt das Tag.

    Gleiche Regel wie `_resolve_genre` in hpg_core/playlist.py; "Unknown"
    faellt in `get_tolerances` auf das erste kanonische Genre zurueck.
    """
    erkannt = getattr(track, "detected_genre", "") or ""
    if erkannt and erkannt != "Unknown":
        return erkannt
    tag = getattr(track, "genre", "") or ""
    return tag if tag and tag != "Unknown" else "Unknown"


def _faktoren_vollstaendig(
    track_a: Track, track_b: Track, metrics
) -> dict[str, float] | None:
    """Sammelt die acht Faktorwerte; None, wenn einer nicht bestimmbar ist.

    Die vier NEUEN Faktoren werden direkt aus `hpg_core.transition_features`
    geholt und nicht aus `TransitionMetrics` gelesen: die Metrik-Felder werden
    nur bei TRANSITION_FEATURES_ENABLED befuellt. Der direkte Weg liefert
    dieselben Werte, unabhaengig vom Flag — der Hoertest darf nicht davon
    abhaengen, ob das Scoring die Faktoren gerade nutzt (Flag seit 2026-08-21
    an, mit Startgewichten; die Noten sollen genau diese ersetzen).
    """
    genre_a = loese_genre_auf(track_a)
    werte = {
        "groove": groove_match(track_a, track_b, genre_a),
        "bass": bass_continuity(track_a, track_b, genre_a),
        "timbre": timbre_match(track_a, track_b, genre_a),
        "mood": mood_match(track_a, track_b, genre_a),
        "harmonic": metrics.harmonic_score / 100.0,
        "bpm": metrics.bpm_smoothness,
        "energy": metrics.energy_flow,
        "genre": metrics.genre_compatibility,
    }
    if any(w is None for w in werte.values()):
        return None
    return {k: float(v) for k, v in werte.items()}


def sammle_kandidaten(
    tracks: list[Track], bpm_toleranz: float = STANDARD_BPM_TOLERANZ
) -> list[dict]:
    """Bildet mixbare Kandidatenpaare mit vollstaendigen Faktorwerten.

    Nur mixbare Paare: bewertet der Nutzer "unmixbar", sagt das nichts ueber
    die vier Faktoren aus, sondern nur ueber BPM und Tonart.
    """
    kandidaten: list[dict] = []
    for a in tracks:
        for b in tracks:
            if a.filePath == b.filePath:
                continue
            if not a.bpm or not b.bpm:
                continue
            diff, _relation = effective_bpm_diff(float(a.bpm), float(b.bpm))
            if diff > bpm_toleranz:
                continue
            metrics = calculate_enhanced_compatibility(a, b, bpm_toleranz)
            if metrics.harmonic_score < MIN_HARMONIC_SCORE:
                continue
            werte = _faktoren_vollstaendig(a, b, metrics)
            if werte is None:
                continue
            kandidaten.append({"track_a": a, "track_b": b, "merkmale": werte})
    return kandidaten


def filtere_nach_genre(kandidaten: list[dict], genre: str) -> list[dict]:
    """Behaelt nur Paare, bei denen BEIDE Tracks das genannte Genre tragen.

    Warum beide: der Hoertest soll ein Genre am Stueck vermessen. Ein
    Genrewechsel traegt zwei Toleranzprofile gleichzeitig, seine Note laesst
    sich keinem der beiden zuordnen. Gemessen am 160er-Satz sind die
    Wechsel-Uebergaenge ausserdem systematisch schlechter bewertet worden
    (Mittel 1.58 gegen 2.39) — ein Satz mit Wechseln haette kaum
    Positivfaelle, und ohne die schaetzt keine Logistik etwas.

    Genre wird wie im Scoring aufgeloest (`loese_genre_auf`), damit der Satz
    dieselbe Sicht hat wie die Bewertung, die er spaeter steuert.
    """
    return [
        k
        for k in kandidaten
        if loese_genre_auf(k["track_a"]) == genre
        and loese_genre_auf(k["track_b"]) == genre
    ]


def geplanter_overlap(a: Track, b: Track, mix_out_a: float, mix_in_b: float) -> float:
    """Die Blendenlaenge, die HPG fuer genau dieses Paar plant.

    Quelle ist ``compute_transition_recommendations`` — derselbe Weg, den die
    App und die Vorschau nehmen (playlist.py:1684-1695: transition_bars mal
    seconds_per_bar, geklemmt auf das real vorhandene Audio).

    Der Wert wird nur uebernommen, wenn ZWEI Bedingungen halten: es gibt eine
    DJ-Brain-Empfehlung, und sie steht auf DENSELBEN Mixpunkten wie der Clip.
    Fehlt die Empfehlung (kein erkanntes Genre, oder eine Ausnahme in
    generate_dj_recommendation), rechnet playlist.py mit eigenen
    Ersatz-Mixpunkten und dem Default-Overlap von 12 s; dieser Wert gehoert
    dann nicht zu diesem Clip. Die Mixpunkt-Pruefung allein genuegt nicht —
    fielen die Ersatzpunkte zufaellig mit den unseren zusammen, kaeme die
    fremde Laenge still durch. In beiden Faellen: Rueckfall auf CROSSFADE_SEK.
    """
    try:
        empfehlungen = compute_transition_recommendations([a, b])
    except Exception as exc:  # noqa: BLE001 — Empfehlung ist optional
        logger.warning("Overlap-Empfehlung fehlgeschlagen: %s", exc)
        return CROSSFADE_SEK
    if not empfehlungen:
        return CROSSFADE_SEK
    plan = getattr(empfehlungen[0], "plan", None)
    if plan is None:
        return CROSSFADE_SEK
    if getattr(empfehlungen[0], "dj_rec", None) is None:
        logger.warning(
            "Keine DJ-Brain-Empfehlung fuer das Paar — Rueckfall auf %.0f s",
            CROSSFADE_SEK,
        )
        return CROSSFADE_SEK
    passt = (
        abs(float(plan.mix_out_a) - float(mix_out_a)) < 0.05
        and abs(float(plan.mix_in_b) - float(mix_in_b)) < 0.05
    )
    if not passt:
        logger.warning(
            "Empfehlung steht auf anderen Mixpunkten (%.2f/%.2f statt "
            "%.2f/%.2f) — Rueckfall auf %.0f s",
            plan.mix_out_a, plan.mix_in_b, mix_out_a, mix_in_b, CROSSFADE_SEK,
        )
        return CROSSFADE_SEK
    overlap = float(empfehlungen[0].overlap)
    return overlap if overlap > 0 else CROSSFADE_SEK


def rendere_paar(
    kandidat: dict, pair_id: str, clips_dir: Path
) -> tuple[str, float]:
    """Rendert einen Uebergangs-Clip.

    Gibt den relativen Clip-Pfad und die tatsaechlich benutzte Blendenlaenge
    zurueck. Die Laenge wandert nach merkmale.csv, weil sie von Paar zu Paar
    verschieden ist und sonst als unkontrollierte Stoergroesse im Fit landet.
    """
    a: Track = kandidat["track_a"]
    b: Track = kandidat["track_b"]
    mix_out_a, mix_in_b = calculate_paired_mix_points(a, b)

    crossfade = geplanter_overlap(a, b, float(mix_out_a), float(mix_in_b))

    rest_a, rest_b = crossfade_reserve(
        float(mix_out_a),
        float(getattr(a, "duration", 0.0) or 0.0),
        float(getattr(b, "duration", 0.0) or 0.0),
        float(mix_in_b),
    )
    if min(rest_a, rest_b) < crossfade:
        raise ValueError(
            f"Crossfade von {crossfade:.0f} s passt nicht "
            f"(Rest A {rest_a:.1f} s, Rest B {rest_b:.1f} s)"
        )
    spec = TransitionClipSpec(
        track_a_path=a.filePath,
        track_b_path=b.filePath,
        mix_out_sec=float(mix_out_a),
        mix_in_sec=float(mix_in_b),
        crossfade_sec=float(crossfade),
        transition_type=HOERTEST_TRANSITION_TYPE,
        pre_roll_sec=PRE_ROLL_SEK,
        post_roll_sec=POST_ROLL_SEK,
        bpm_a=float(a.bpm or 120.0),
        bpm_b=float(b.bpm or 120.0),
        # Beatgrid-Anker weiterreichen — dieselben Felder und dieselben
        # Schwellen wie in TransitionClipSpec.from_plan, wo die Begruendung
        # steht (Feld-Kommentar zu downbeat_reliable_* in
        # TransitionClipSpec, AUDIT-FIX D-03). Ohne sie bleiben die
        # Dataclass-Defaults stehen, der Renderer schaetzt den ersten Beat aus
        # einem 8-s-Fenster und richtet nur auf BEAT-Ebene aus. Der Bestand
        # traegt das Rekordbox-Referenz-Beatgrid (gemessen: 199 von 200 Tracks
        # mit downbeat_confidence 1.0) — es wegzuwerfen und stattdessen zu
        # schaetzen ist der schlechtere Weg.
        # Wirkung mit bar_phase_reliable: das Alignment rastert auf TAKTE statt
        # auf Beats, Beat 1 von B landet auf Beat 1 von A. Das verschiebt den
        # Einsatz von B um bis zu einen Takt gegenueber der Beat-Ebene — so
        # macht es die App auch, und genau das soll der Hoertest abbilden.
        # lufs_a/lufs_b bleiben bewusst ungesetzt: sie steuern den Render
        # nicht mehr, _apply_lufs_delta bekommt gemessene Segment-Loudness
        # (siehe _apply_lufs_delta-Aufruf in render_transition_clip).
        first_downbeat_a=float(getattr(a, "first_downbeat", 0.0) or 0.0),
        first_downbeat_b=float(getattr(b, "first_downbeat", 0.0) or 0.0),
        downbeat_reliable_a=(
            getattr(a, "downbeat_confidence", 0.0) >= DOWNBEAT_RELIABLE_MIN
        ),
        downbeat_reliable_b=(
            getattr(b, "downbeat_confidence", 0.0) >= DOWNBEAT_RELIABLE_MIN
        ),
        bar_phase_reliable_a=(
            getattr(a, "downbeat_confidence", 0.0) == REFERENCE_BEATGRID_CONFIDENCE
        ),
        bar_phase_reliable_b=(
            getattr(b, "downbeat_confidence", 0.0) == REFERENCE_BEATGRID_CONFIDENCE
        ),
    )
    ziel = clips_dir / f"{pair_id}.wav"
    render_transition_clip(spec, str(ziel))
    return f"clips/{pair_id}.wav", crossfade


def lies_csv(pfad: Path) -> list[dict]:
    with pfad.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def schreibe_csv(pfad: Path, spalten, zeilen) -> None:
    with pfad.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(spalten))
        writer.writeheader()
        writer.writerows(zeilen)


# ===========================================================================
# Unterbefehl: prepare
# ===========================================================================

def befehl_prepare(args: argparse.Namespace) -> int:
    out = Path(args.out)
    clips_dir = out / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    tracks = lade_tracks_aus_cache(args.cache)
    print(f"Analysierte Tracks im Cache: {len(tracks)}")

    kandidaten = sammle_kandidaten(tracks, args.bpm_toleranz)
    print(f"Mixbare Kandidatenpaare mit vollstaendigen Faktoren: {len(kandidaten)}")
    if getattr(args, "nur_genre", None):
        kandidaten = filtere_nach_genre(kandidaten, args.nur_genre)
        print(f"davon reine {args.nur_genre}-Uebergaenge: {len(kandidaten)}")
    if not kandidaten:
        print("Keine Kandidaten — nichts zu rendern.")
        return 1

    # Nur die vier NEUEN Faktoren spannen den Auswahlraum auf: fuer sie soll
    # der Hoertest Kontrast liefern.
    vektoren = [[k["merkmale"][n] for n in NEUE_FAKTOREN] for k in kandidaten]
    # Ueberzaehlige Reserve: die Maximin-Reihenfolge ist eine Rangfolge, jeder
    # weitere Kandidat deckt die naechstgroesste Luecke. Ein Paar, dessen
    # Crossfade nicht passt oder dessen Render scheitert, wird so vom
    # naechstbesten ersetzt, statt den Satz zu verkleinern.
    reserve = maximin_auswahl(vektoren, args.anzahl * RESERVE_FAKTOR,
                              seed=args.seed)

    bewertung_zeilen: list[dict] = []
    merkmal_zeilen: list[dict] = []
    fehlgeschlagen = 0
    for index in reserve:
        if len(merkmal_zeilen) >= args.anzahl:
            break
        kandidat = kandidaten[index]
        nummer = len(merkmal_zeilen) + 1
        pair_id = f"{nummer:03d}"
        print(f"[{nummer}/{args.anzahl}] rendere {pair_id} ...", flush=True)
        try:
            clip, crossfade = rendere_paar(kandidat, pair_id, clips_dir)
        except Exception as exc:  # noqa: BLE001 — ein defekter Clip darf den Lauf nicht abbrechen
            fehlgeschlagen += 1
            logger.warning("Paar %s uebersprungen: %s", pair_id, exc)
            print(f"    uebersprungen: {exc}")
            continue
        bewertung_zeilen.append(
            {"pair_id": pair_id, "clip": clip, "bewertung": ""}
        )
        zeile = {"pair_id": pair_id}
        zeile.update(
            {n: round(kandidat["merkmale"][n], 6) for n in ALLE_FAKTOREN}
        )
        # Die Blendenlaenge variiert von Paar zu Paar. Sie wird mitgeschrieben,
        # damit die Konfundierung nachtraeglich von Hand pruefbar ist: der Fit
        # liest sie NICHT (verbinde_bewertungen nimmt nur ALLE_FAKTOREN), sie
        # geht also nicht als Kontrollvariable ins Modell ein.
        zeile["crossfade_sek"] = round(float(crossfade), 2)
        zeile["track_a"] = kandidat["track_a"].filePath
        zeile["track_b"] = kandidat["track_b"].filePath
        merkmal_zeilen.append(zeile)

    if not merkmal_zeilen:
        print("Kein einziger Clip konnte gerendert werden.")
        return 1

    schreibe_csv(out / "bewertung.csv", ("pair_id", "clip", "bewertung"),
                 bewertung_zeilen)
    schreibe_csv(
        out / "merkmale.csv",
        ("pair_id", *ALLE_FAKTOREN, "crossfade_sek", "track_a", "track_b"),
        merkmal_zeilen,
    )

    print()
    print(f"Kandidaten: {len(kandidaten)}   gewuenscht: {args.anzahl}   "
          f"gerendert: {len(merkmal_zeilen)}   uebersprungen: {fehlgeschlagen}")
    if len(merkmal_zeilen) < args.anzahl:
        print(f"Weniger als gewuenscht: es gab nur {len(merkmal_zeilen)} "
              f"brauchbare Paare (Kandidatenmenge erschoepft oder Crossfade "
              f"passte nicht). Der Satz umfasst {len(merkmal_zeilen)} Clips.")
    print("Streuung der vier neuen Faktoren im gewaehlten Satz:")
    for name in NEUE_FAKTOREN:
        werte = streuung([z[name] for z in merkmal_zeilen])
        print(f"  {name:9s} min {werte['min']:.3f}  median "
              f"{werte['median']:.3f}  max {werte['max']:.3f}")
    print()
    print(f"Jetzt bewerten ({BEWERTUNG_MIN} = geht gar nicht, "
          f"{BEWERTUNG_MAX} = sehr gut):")
    print(f"    python tools/hoertest_server.py --dir {out}")
    print(f"Die Seite spielt die Clips und schreibt die Noten selbst nach "
          f"{out / 'bewertung.csv'}.")
    return 0


# ===========================================================================
# Unterbefehl: fit
# ===========================================================================

def befehl_fit(args: argparse.Namespace) -> int:
    ordner = Path(args.dir)
    merkmale_roh = lies_csv(ordner / "merkmale.csv")
    bewertung_roh = lies_csv(ordner / "bewertung.csv")

    zeilen, ohne, ungueltig = verbinde_bewertungen(merkmale_roh, bewertung_roh)
    print(f"Bewertete Paare: {len(zeilen)}   ohne Bewertung uebersprungen: "
          f"{ohne}   ungueltige Eintragungen: {ungueltig}")
    if len(zeilen) < 2:
        print("Zu wenige Bewertungen fuer eine Schaetzung.")
        return 1

    aktive, streuungen = waehle_merkmale(zeilen)
    X, y = zu_zielgroesse(zeilen, aktive)
    n_gut = int(y.sum())
    n_schlecht = int(len(y) - n_gut)
    if n_gut == 0 or n_schlecht == 0:
        print("Alle Bewertungen fallen in dieselbe Klasse — keine Schaetzung "
              "moeglich. Es braucht sowohl gute (>= 4) als auch schwache Noten.")
        return 1

    belastbar, urteil = datenlage_urteil(n_gut, n_schlecht, len(aktive))

    beta = fit_logistic(X, y, L2_STAERKE)
    koeffizienten = {
        name: float(beta[1 + i]) for i, name in enumerate(aktive)
    }
    intervalle = bootstrap_intervalle(
        X, y, L2_STAERKE, BOOTSTRAP_ZIEHUNGEN, args.seed, aktive
    )
    gewichte = leite_gewichte_ab(koeffizienten, intervalle, belastbar)

    genres = args.genre or list(CANONICAL_GENRES)
    ergebnis = baue_ausgabe_json(
        genres, gewichte, koeffizienten, intervalle,
        len(zeilen), n_gut, belastbar, urteil,
        aktive, streuungen,
    )
    ziel = ordner / "gewichte.json"
    ziel.write_text(json.dumps(ergebnis, indent=2, ensure_ascii=False),
                    encoding="utf-8")

    verworfen = [n for n in KLASSISCHE_FAKTOREN if n not in aktive]
    print()
    print(f"In die Regression eingegangen ({len(aktive)} Merkmale): "
          f"{', '.join(aktive)}")
    if verworfen:
        print("Als Kontrollvariable VERWORFEN, weil im bewerteten Satz zu "
              f"wenig Streuung (< {MIN_KONTROLL_STREUUNG:.2f}): "
              + ", ".join(f"{n} (s={streuungen[n]:.3f})" for n in verworfen))
    print()
    print(urteil)
    print()
    print(f"{'Faktor':10s} {'Koeffizient':>12s} {'95-%-Bereich':>22s} "
          f"{'Gewicht':>9s}")
    for name in aktive:
        unten, oben = intervalle[name]
        rolle = "" if name in NEUE_FAKTOREN else "  (Kontrolle)"
        gewicht = gewichte.get(name)
        gewicht_text = "-" if gewicht is None else f"{gewicht:.4f}"
        print(f"{name:10s} {koeffizienten[name]:12.4f} "
              f"[{unten:8.4f}, {oben:8.4f}] {gewicht_text:>9s}{rolle}")

    gesichert_negativ = [
        n for n in NEUE_FAKTOREN if intervalle[n][1] < 0.0
    ]
    if gesichert_negativ:
        print()
        print("Gesichert NEGATIV (hoeherer Wert = schlechteres Urteil), bekommt "
              f"trotzdem kein Gewicht: {', '.join(gesichert_negativ)}")

    budget = sum(gewichte.values())
    print()
    if budget <= 0.0:
        print("Gewichtsbudget 0,000 — es wurde NICHTS gelernt. Die Defaults "
              "bleiben stehen.")
    else:
        print(f"Gewichtsbudget der vier neuen Faktoren: {budget:.3f}")
    print(f"Grundlage: {len(zeilen)} Bewertungen ({n_gut} gut / "
          f"{n_schlecht} nicht gut).")
    print(f"Geschrieben: {ziel}")
    return 0


# ===========================================================================
# CLI
# ===========================================================================

def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    unter = parser.add_subparsers(dest="befehl", required=True)

    p = unter.add_parser("prepare", help="Clips rendern und Bewertungsbogen anlegen")
    p.add_argument("--anzahl", type=int, default=STANDARD_ANZAHL)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--bpm-toleranz", dest="bpm_toleranz", type=float,
                   default=STANDARD_BPM_TOLERANZ)
    p.add_argument("--cache", default=None, help="Abweichende Cache-Datenbank")
    p.add_argument("--seed", type=int, default=STANDARD_SEED)
    # Bewusst NICHT --genre: bei `fit` steuert --genre die Ausgabe der
    # Genre-Gewichte, hier die Auswahl der Paare. Gleicher Name, andere
    # Wirkung waere eine Falle.
    p.add_argument("--nur-genre", dest="nur_genre", default=None,
                   choices=list(CANONICAL_GENRES),
                   help="Nur Paare, bei denen beide Tracks dieses Genre tragen")
    p.set_defaults(funktion=befehl_prepare)

    f = unter.add_parser("fit", help="Gewichte aus den Bewertungen schaetzen")
    f.add_argument("--dir", required=True, type=Path)
    f.add_argument("--seed", type=int, default=STANDARD_SEED)
    f.add_argument("--genre", action="append", choices=list(CANONICAL_GENRES),
                   help="Genre(s) fuer die Ausgabe; Standard: alle kanonischen")
    f.set_defaults(funktion=befehl_fit)

    args = parser.parse_args(argv)
    return int(args.funktion(args))


if __name__ == "__main__":
    raise SystemExit(main())

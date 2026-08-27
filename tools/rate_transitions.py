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
  Scoring), `rendere_paar` (TransitionPlan + Audio),
  `lies_csv` / `schreibe_csv`, `main`.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from copy import deepcopy
import csv
from dataclasses import replace
import hashlib
import io
import json
import logging
import math
import ntpath
import os
import random
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import soundfile as sf
from scipy.optimize import minimize

from hpg_core import (
    candidate_choices,
    candidate_preferences,
    config as hpg_config,
    tolerances,
)
from hpg_core.caching import (
    CACHE_FILE,
    CACHE_VERSION,
    dict_to_track,
    validate_track_dict,
)
from hpg_core.config import (
    MAX_TRANSITION_OVERLAP_SECONDS, PAAR_BPM_MAX, PAAR_MIN_LOCAL_GROOVE,
    PAAR_MIN_LOCAL_SCORE, SECURITY_MAX_PLAYLIST_SIZE,
)
from hpg_core.downbeat import (
    DOWNBEAT_RELIABLE_MIN,
    REFERENCE_BEATGRID_CONFIDENCE,
)
from hpg_core.genres import CANONICAL_GENRES, GENRE_TRANSITION_TOLERANCES
from hpg_core.models import QUANTIZE_TOLERANCE_SEC, Track, effective_bpm_diff
from hpg_core.tolerances import (
    KANDIDATEN_GEWICHT_SCHLUESSEL,
    NICHT_GEWICHT_SCHLUESSEL,
)
from hpg_core.app_metadata import APP_VERSION
from hpg_core.pair_candidates import (
    FAKTOREN as KANDIDATEN_TEILWERTE, PairCandidate, rank_pair_candidates,
)
from hpg_core.playlist import (
    compute_transition_recommendations,
    predict_transition_type,
    transition_type_for_candidate,
    transition_metrics_from_candidate,
)
from hpg_core.transition_renderer import (
    KICK_SYNC_MAX_ERROR_SECONDS,
    SUPPORTED_TRANSITION_TYPES,
    TransitionClipSpec,
    render_transition_clip,
)

logger = logging.getLogger("rate_transitions")

# --- Faktoren -------------------------------------------------------------
# Die vier neuen Faktoren, deren Gewicht geschaetzt werden soll.
NEUE_FAKTOREN: tuple[str, ...] = ("groove", "bass", "timbre", "mood")
# Die vier klassischen Faktoren laufen als KONTROLLVARIABLEN mit: ohne sie
# wuerde ihr Beitrag zum Urteil faelschlich den neuen Faktoren zugeschlagen.
KLASSISCHE_FAKTOREN: tuple[str, ...] = ("harmonic", "bpm", "energy", "genre")
ALLE_FAKTOREN: tuple[str, ...] = NEUE_FAKTOREN + KLASSISCHE_FAKTOREN
# Protokollspalten in merkmale.csv — der Fit liest sie NICHT (kein Merkmal).
ZUSATZ_SPALTEN: tuple[str, ...] = ("overall_score", "lufs_delta")
PLAN_AUDIT_SPALTEN: tuple[str, ...] = (
    "plan_mix_out_sec", "plan_mix_in_sec", "plan_overlap_sec",
    "plan_transition_type", "plan_target_sr", "kandidat_rang", "bpm_toleranz",
    "energy_direction",
)

# --- Kandidatenmodus (Spec 2026-08-21 Abschnitt 3) -------------------------
# bewertung.csv je Clip eines Paars: Note 1-5 und exklusive Wahl "bester".
BEWERTUNG_KANDIDATEN_SPALTEN: tuple[str, ...] = ("pair_id", "clip_id", "note", "gewaehlt", "zeit")
# merkmale.csv je Clip: die zehn Teilwerte aus pair_candidates.score_pair, der
# Score (nie angezeigt), Schema/Provenienz/Confidence je Seite, Blende und
# Anzeige-Kontext (bpm/genre/key — kein Score, kein Schema).
MERKMALE_KANDIDATEN_SPALTEN: tuple[str, ...] = (
    "pair_id", "clip_id", "clip", *KANDIDATEN_TEILWERTE, "score",
    "schema_out", "schema_in", "schemata_out", "schemata_in", "blend_bars", "t_out", "t_in",
    "provenance_out", "provenance_in", "confidence_out", "confidence_in",
    "crossfade_sek", "bpm_relation", "bpm_a", "bpm_b", "genre_a", "genre_b", "key_a", "key_b",
    "bpm_toleranz", "energy_direction",
    "rendered_transition_type", "transition_type_mode",
    "track_a", "track_b",
)
# Holdout nach Tracks: Anteil der Tracks, deren Clips NICHT in die Schaetzung
# gehen (ein Clip ist Holdout, wenn Track A ODER B dazugehoert — bei 30 % Tracks
# sind das rund 51 % der Clips). STARTWERT.
HOLDOUT_ANTEIL = 0.30
# Innerhalb-Paar-Streuung (Std der Sieger-Verlierer-Differenzen im Train), ab der
# ein Merkmal aus dem Paarvergleich identifizierbar ist. STARTWERT.
PAAR_STREUUNG_MIN = 0.05

# --- Auswahl / Rendern ----------------------------------------------------
# Harte Nutzer-Grenze (2026-08-21): hoechstens 2 BPM Unterschied zwischen
# zwei Tracks, die gemischt werden sollen (Grenze inklusive: 2.0 passt,
# 2.1 nicht). Half/Double-Relationen rechnet effective_bpm_diff wie in der
# App um. Dieselbe Regel gilt fuer die App (GUI-Slider Bereich 1-2, default 2.0);
# dort nicht als harte Gate-Grenze umgesetzt, aber als Nutzer-Auswahl für Kandidaten-
# Ranking und normale Bewertung verwendet.
STANDARD_BPM_TOLERANZ = 2.0
# Historischer API-Default fuer Auswertungen, die diese Konstante importieren.
# Der Prepare-Vertrag nutzt fuer Gate UND rank_pair_candidates ausschliesslich
# die explizite --bpm-toleranz; diese Konstante steuert das Ranking nicht.
SCORING_BPM_TOLERANZ = 3.0
MIN_HARMONIC_SCORE = 60
# Hoertest-spezifisches Zusatz-Gate: kein Produktionsvertrag. Das zentrale
# PairCandidate-Ranking wird unveraendert reproduziert; fuer den aktuellen
# Hoertest-Auftrag werden daraus zusaetzlich nur Kandidaten mit mindestens
# diesem Harmonie-Score zugelassen.
HARMONIC_GATE_SCOPE = "candidate_hearing_test_only"
# Paar-Gate ueber ALLE Scoring-Gewichte (harmonic/bpm/energy/genre plus
# groove/bass/timbre/mood): overall_score 0..1 aus
# calculate_enhanced_compatibility. 0.70 ist die Paar-Stufe "Solide
# Transition" der App (playlist.py, Transition-Beschreibung: >= 85
# sicher, >= 70 solide, >= 55 machbar). Der Hoertest bewertet damit nur
# Paare, die die App mit ihren aktuellen Gewichten als solide ansieht.
# Folge, bewusst in Kauf genommen: das Gate enthaelt die Startgewichte
# (groove 0.30), die die Noten ersetzen sollen, und es drueckt die Streuung
# von timbre/mood im Satz — liefert der Fit dort
# "Intervall enthaelt 0", heisst das "kein Kontrast im Satz", nicht
# "Faktor egal".
MIN_OVERALL_SCORE = PAAR_MIN_LOCAL_SCORE
# Groove-Untergrenze aus dem Tausch vom 21.08. (Paare mit groove < 0.5
# wurden damals von Hand aus beiden Saetzen entfernt).
MIN_GROOVE = PAAR_MIN_LOCAL_GROOVE
# Feste Blende fuer ALLE Hoertest-Clips: reine 3-Band-EQ-Blende ohne Echo,
# Cut oder Filter-Sweep. Vorher lief je Paar predict_transition_type, damit
# variierte der Effekt von Clip zu Clip und ging als nicht erfasste
# Stoergroesse in die Note ein (Konfundierung). Umgestellt 2026-08-21, alle
# Noten aus der Zeit davor wurden verworfen.
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
HOERTEST_TRANSITION_TYPE = "pro_eq_swap"
PRE_ROLL_SEK = 8.0
POST_ROLL_SEK = 8.0
# Wie viele Kandidaten ueber die gewuenschte Anzahl hinaus in die Warteschlange
# kommen, damit uebersprungene Paare ersetzt werden koennen.
RESERVE_FAKTOR = 4
# Standardumfang des Hoertests. 100 Bewertungen reichen bei den vier neuen
# Faktoren allein fuer die Faustregel (40 Ereignisse je Klasse), sofern das
# Urteil einigermassen ausgewogen ausfaellt.
STANDARD_ANZAHL = 100
STANDARD_MAX_VERSIONEN_PRO_PAAR = 5
MAX_ANZAHL = SECURITY_MAX_PLAYLIST_SIZE
KANDIDATEN_MANIFEST_VERSION = 1
KANDIDATEN_MANIFEST_NAME = "kandidaten_manifest.json"
ALGORITHM_BUILD_SCHEME = "sha256-path-bytes-v1"
# Windows-Virenscanner koennen einen gerade fertig geschriebenen Staging-
# Ordner fuer wenige Millisekunden blockieren. Genau dieser eine Fehler darf
# begrenzt wiederholt werden; Gesamtwartezeit 0,35 s.
PUBLISH_PERMISSION_BACKOFF_SECONDS: tuple[float, ...] = (0.05, 0.10, 0.20)

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

def _json_plain(value):
    """Loest Mapping-Proxies/Tupel tief in strikt serialisierbare JSON-Werte."""
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): _json_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_plain(item) for item in value]
    return value


def _json_roundtrip_strikt(value):
    """Erzeugt eine tiefe JSON-Kopie und verwirft NaN/Inf sofort."""
    return json.loads(json.dumps(
        _json_plain(value), ensure_ascii=False, allow_nan=False,
    ))


def _cache_pfad(db_pfad: str | None = None) -> Path:
    try:
        pfad = Path(db_pfad or CACHE_FILE).resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Cache-Datenbank nicht gefunden: {Path(db_pfad or CACHE_FILE)}"
        ) from exc
    if not pfad.is_file():
        raise FileNotFoundError(f"Cache-Datenbank nicht gefunden: {pfad}")
    return pfad


def _reject_pending_wal(cache: Path) -> None:
    wal = Path(f"{cache}-wal")
    if wal.exists() and wal.stat().st_size:
        raise ValueError(f"Cache hat ausstehendes WAL und wird nicht angefasst: {wal}")


def _fingerprint_cache(cache: Path) -> dict:
    digest = hashlib.sha256()
    size = 0
    with cache.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            digest.update(block)
    return {"size": size, "sha256": digest.hexdigest()}


def _fingerprint_kandidatensatz(root: Path) -> dict:
    """Kanonischer Digest aller Satzdateien; Symlinks sind verboten."""
    root = root.resolve(strict=True)
    eintraege = sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())
    symlinks = [path for path in eintraege if path.is_symlink()]
    if symlinks:
        raise ValueError(
            f"Kandidatensatz enthaelt Symlink: {symlinks[0].relative_to(root)}"
        )
    dateien = [path for path in eintraege if path.is_file()]
    digest = hashlib.sha256()
    for path in dateien:
        relativ = path.relative_to(root).as_posix().encode("utf-8")
        inhalt = path.read_bytes()
        digest.update(len(relativ).to_bytes(4, "big"))
        digest.update(relativ)
        digest.update(len(inhalt).to_bytes(8, "big"))
        digest.update(inhalt)
    return {"files": len(dateien), "sha256": digest.hexdigest()}


def _algorithm_build_fingerprint(repo_root: Path | None = None) -> dict:
    """Hash aller Core-Pythonquellen plus Producer, ohne Git/Netzwerk."""
    root = (repo_root or Path(__file__).resolve().parent.parent).resolve()
    files = sorted(
        [root / "tools" / "rate_transitions.py", *root.glob("hpg_core/**/*.py")],
        key=lambda path: path.relative_to(root).as_posix(),
    )
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return {
        "scheme": ALGORITHM_BUILD_SCHEME,
        "files": len(files),
        "sha256": digest.hexdigest(),
    }


def _baue_scoring_snapshot(args: argparse.Namespace) -> dict:
    """Friert alle externen Kandidatenregeln genau einmal als reines JSON ein."""
    geladene_toleranzen = deepcopy(tolerances.load_tolerances())
    geladene_praeferenzen = deepcopy(
        candidate_preferences.load_candidate_preferences()
    )
    geladene_wahlen = candidate_choices.snapshot()

    def nur_kandidatenwerte(werte: dict) -> dict:
        return {
            key: float(werte[key])
            for key in (
                *KANDIDATEN_GEWICHT_SCHLUESSEL,
                *NICHT_GEWICHT_SCHLUESSEL,
            )
        }

    fallback = nur_kandidatenwerte(
        geladene_toleranzen[CANONICAL_GENRES[0]]
    )
    toleranzen_je_genre: dict[str, dict] = {}
    schema_je_genre: dict[str, list[str]] = {}
    for genre in CANONICAL_GENRES:
        effektiv = nur_kandidatenwerte(geladene_toleranzen[genre])
        praferenz = geladene_praeferenzen.get(genre, {})
        gewichte = praferenz.get("gewichte")
        if gewichte is not None:
            effektiv.update({
                key: float(gewichte[key])
                for key in KANDIDATEN_GEWICHT_SCHLUESSEL
            })
        toleranzen_je_genre[genre] = effektiv
        schema_je_genre[genre] = list(praferenz.get("schema_rang") or [])

    snapshot = {
        "rank_args": {
            "bpm_tolerance": float(args.bpm_toleranz),
            "energy_direction": _energy_direction_text(
                getattr(args, "energy_direction", None)
            ),
            "harmonic_strictness": int(getattr(args, "harmonic_strictness", 7)),
            "allow_experimental": getattr(args, "allow_experimental", True),
        },
        "candidate_tolerances_by_genre": toleranzen_je_genre,
        "candidate_tolerances_fallback": fallback,
        "candidate_schema_ranks_by_genre": schema_je_genre,
        "candidate_schema_rank_fallback": [],
        "candidate_choices": geladene_wahlen,
    }
    return _json_roundtrip_strikt(snapshot)


def _rank_pair_mit_snapshot(
    track_a: Track,
    track_b: Track,
    *,
    scoring_snapshot: dict | None,
    bpm_tolerance: float = STANDARD_BPM_TOLERANZ,
    energy_direction: str | None = None,
) -> list[PairCandidate]:
    if scoring_snapshot is None:
        rank_kwargs = {
            "bpm_tolerance": bpm_tolerance,
            "energy_direction": energy_direction,
        }
    else:
        genre = loese_genre_auf(track_a)
        toleranzen_je_genre = scoring_snapshot["candidate_tolerances_by_genre"]
        schema_je_genre = scoring_snapshot["candidate_schema_ranks_by_genre"]
        if genre in toleranzen_je_genre:
            effektive_toleranzen = toleranzen_je_genre[genre]
            schema_rang = schema_je_genre[genre]
        else:
            effektive_toleranzen = scoring_snapshot["candidate_tolerances_fallback"]
            schema_rang = scoring_snapshot["candidate_schema_rank_fallback"]
        rank_args = scoring_snapshot["rank_args"]
        richtung = rank_args["energy_direction"]
        rank_kwargs = {
            "bpm_tolerance": float(rank_args["bpm_tolerance"]),
            "energy_direction": None if richtung == "auto" else richtung,
            "harmonic_strictness": int(rank_args["harmonic_strictness"]),
            "allow_experimental": bool(rank_args["allow_experimental"]),
            "tolerances": deepcopy(effektive_toleranzen),
            "schema_rang": list(schema_rang),
            "wahl": deepcopy(scoring_snapshot["candidate_choices"].get(
                candidate_choices.schluessel(track_a.filePath, track_b.filePath),
                {},
            )),
        }
    return rank_pair_candidates(track_a, track_b, **rank_kwargs)


def _windows_pfadschluessel(pfad: str) -> str:
    """Windows-Pfadvergleich unabhaengig vom Betriebssystem des Aufrufers."""
    return ntpath.normcase(ntpath.abspath(ntpath.normpath(str(pfad))))


def _json_strikt(roh: str, *, key: str) -> dict:
    def ungueltige_konstante(wert: str):
        raise ValueError(f"nicht-endliche JSON-Konstante {wert}")

    try:
        daten = json.loads(roh, parse_constant=ungueltige_konstante)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Cache-Zeile {key}: ungueltiges JSON ({exc})") from exc
    return validate_track_dict(daten)


def lade_tracks_aus_cache(db_pfad: str | None = None) -> list[Track]:
    """Liest einen vollstaendig validierten aktuellen Cache strikt read-only."""
    pfad = _cache_pfad(db_pfad)
    _reject_pending_wal(pfad)

    tracks: list[Track] = []
    gesehen: dict[str, str] = {}
    uri = f"file:{quote(pfad.as_posix(), safe='/:')}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        tabellen = {
            zeile[0]
            for zeile in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "cache" not in tabellen:
            raise ValueError("Cache-Schema fehlt: Tabelle cache nicht vorhanden")
        spalten = [zeile[1] for zeile in conn.execute("PRAGMA table_info(cache)")]
        if spalten != ["key", "filepath", "version", "data"]:
            raise ValueError(f"Cache-Schema ungueltig: Spalten {spalten!r}")
        marker_rows = list(conn.execute(
            "SELECT filepath, version, data FROM cache WHERE key = 'version'"
        ))
        if marker_rows != [("system", CACHE_VERSION, "metadata")]:
            raise ValueError(
                f"Cache-Marker ungueltig, doppelt oder veraltet: "
                f"erwartet exakt Version {CACHE_VERSION}"
            )
        for key, filepath, version, roh in conn.execute(
            "SELECT key, filepath, version, data FROM cache "
            "WHERE key <> 'version' ORDER BY key"
        ):
            if version != CACHE_VERSION:
                raise ValueError(
                    f"Cache-Zeile {key}: Version {version!r} statt {CACHE_VERSION}"
                )
            daten = _json_strikt(roh, key=key)
            track = dict_to_track(daten)
            if not filepath or _windows_pfadschluessel(filepath) != _windows_pfadschluessel(track.filePath):
                raise ValueError(f"Cache-Zeile {key}: filepath stimmt nicht mit JSON ueberein")
            pfad_key = _windows_pfadschluessel(track.filePath)
            if pfad_key in gesehen:
                raise ValueError(
                    f"Cache enthaelt Windows-Pfad doppelt: {track.filePath!r} "
                    f"und {gesehen[pfad_key]!r}"
                )
            gesehen[pfad_key] = track.filePath
            tracks.append(track)
    finally:
        conn.close()
    _reject_pending_wal(pfad)
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


def _endliche_zahl(value, name: str, *, minimum=None, maximum=None) -> float:
    """Konvertiert eine echte Zahl und verwirft Bool, NaN und Inf."""
    if isinstance(value, bool):
        raise ValueError(f"{name} darf kein Bool sein")
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} ist keine gueltige Zahl") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} muss endlich sein")
    if minimum is not None and number < minimum:
        raise ValueError(f"{name} liegt unter {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{name} liegt ueber {maximum}")
    return number


def _faktoren_vollstaendig(pair_candidate) -> dict[str, float] | None:
    """Liest alle normierten Faktoren und ihre LUFS-Quellwerte strikt."""
    try:
        werte = dict(pair_candidate.teilwerte or {})
        if set(werte) != set(KANDIDATEN_TEILWERTE):
            raise ValueError("Teilwerte haben kein exaktes Faktorenschema")
        normalisiert = {
            name: _endliche_zahl(
                werte[name], f"Teilwert {name}", minimum=0.0, maximum=1.0
            )
            for name in KANDIDATEN_TEILWERTE
        }
        _endliche_zahl(pair_candidate.score, "PairCandidate.score", minimum=0.0, maximum=1.0)
        _endliche_zahl(pair_candidate.out_a.lufs_lokal, "out_a.lufs_lokal")
        _endliche_zahl(pair_candidate.in_b.lufs_lokal, "in_b.lufs_lokal")
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    return normalisiert


def _validiere_prepare_metrics(metrics) -> tuple[float, float]:
    """Validiert die Gate- und Protokollwerte des zentralen Metrics-Vertrags."""
    harmonic = _endliche_zahl(
        metrics.harmonic_score, "harmonic_score", minimum=0.0, maximum=100.0
    )
    overall = _endliche_zahl(
        metrics.overall_score, "overall_score", minimum=0.0, maximum=1.0
    )
    _endliche_zahl(metrics.groove_match, "groove", minimum=0.0, maximum=1.0)
    _endliche_zahl(metrics.lufs_delta, "lufs_delta")
    return harmonic, overall


def _gueltige_bpm(value) -> float | None:
    """Normalisiert einen Cache-BPM-Wert fuer den sortierten Suchindex."""
    try:
        bpm = float(value)
    except (TypeError, ValueError):
        return None
    return bpm if math.isfinite(bpm) and bpm > 0 else None


def sammle_kandidaten(
    tracks: list[Track], bpm_toleranz: float = STANDARD_BPM_TOLERANZ,
    energy_direction: str | None = None,
    *, scoring_snapshot: dict | None = None,
) -> list[dict]:
    """Bildet Kandidatenpaare, die die App mit allen Regeln als mixbar ansieht.

    Gates: BPM-Abstand <= bpm_toleranz (hart, Nutzer-Regel 2 BPM), Tonart
    (harmonic_score >= MIN_HARMONIC_SCORE), Gesamtwertung ueber alle Gewichte
    (overall_score >= MIN_OVERALL_SCORE, Scoring mit bpm_toleranz und
    energy_direction)
    und groove >= MIN_GROOVE. Der Hoertest benotet also nur Paare, die die App
    auch waehlen wuerde; die Noten pruefen deren Gewichte. Lautheit ist einer
    der zehn lokal gemessenen Scoring-Faktoren und wird zusaetzlich als lokales
    lufs_delta protokolliert.
    """
    kandidaten: list[dict] = []
    normalisierte_bpm = [_gueltige_bpm(track.bpm) for track in tracks]
    bpm_index = sorted(
        (bpm, index)
        for index, bpm in enumerate(normalisierte_bpm)
        if bpm is not None
    )
    bpm_werte = [bpm for bpm, _index in bpm_index]

    for a_index, a in enumerate(tracks):
        a_bpm = normalisierte_bpm[a_index]
        if a_bpm is None:
            continue

        fenster = [(a_bpm - bpm_toleranz, a_bpm + bpm_toleranz)]
        if hpg_config.BPM_HALF_DOUBLE_ENABLED:
            fenster.extend(
                [
                    (
                        (a_bpm - bpm_toleranz) / 2.0,
                        (a_bpm + bpm_toleranz) / 2.0,
                    ),
                    (
                        2.0 * (a_bpm - bpm_toleranz),
                        2.0 * (a_bpm + bpm_toleranz),
                    ),
                ]
            )

        b_indizes: set[int] = set()
        for untergrenze, obergrenze in fenster:
            links = bisect_left(bpm_werte, untergrenze)
            rechts = bisect_right(bpm_werte, obergrenze)
            b_indizes.update(index for _bpm, index in bpm_index[links:rechts])

        for b_index in sorted(b_indizes):
            b = tracks[b_index]
            if a.filePath == b.filePath:
                continue
            b_bpm = normalisierte_bpm[b_index]
            if b_bpm is None:
                continue
            diff, _relation = effective_bpm_diff(a_bpm, b_bpm)
            if diff > bpm_toleranz:
                continue
            pcs = _rank_pair_mit_snapshot(
                a,
                b,
                scoring_snapshot=scoring_snapshot,
                bpm_tolerance=bpm_toleranz,
                energy_direction=energy_direction,
            )
            if not pcs:
                continue
            werte = _faktoren_vollstaendig(pcs[0])
            if werte is None:
                continue
            try:
                metrics = transition_metrics_from_candidate(pcs[0])
                harmonic_score, overall_score = _validiere_prepare_metrics(metrics)
            except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
                continue
            if harmonic_score < MIN_HARMONIC_SCORE:
                continue
            if overall_score < MIN_OVERALL_SCORE:
                continue
            if werte["groove"] < MIN_GROOVE:
                continue
            zusatz = {
                "overall_score": round(overall_score, 4),
                "lufs_delta": round(float(metrics.lufs_delta), 2),
            }
            kandidaten.append(
                {
                    "track_a": a, "track_b": b, "merkmale": werte,
                    "zusatz": zusatz, "pair_candidates": pcs,
                }
            )
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


def _strict_render_fields(a: Track, b: Track) -> dict:
    """Dieselbe Phasen-Verlaesslichkeit wie die App; der Hoertest aktiviert
    zusaetzlich bewusst ``strict_beat_sync`` fuer seine Vergleichsclips."""
    def phase_reliability(track: Track) -> tuple[bool, bool]:
        confidence = float(getattr(track, "downbeat_confidence", 0.0) or 0.0)
        reference_grid = (
            getattr(track, "beatgrid_source", "unknown") == "rekordbox"
            and getattr(track, "beatgrid_status", "unknown") == "verified"
            and confidence == REFERENCE_BEATGRID_CONFIDENCE
        )
        measured_audio = (
            DOWNBEAT_RELIABLE_MIN <= confidence < REFERENCE_BEATGRID_CONFIDENCE
        )
        return reference_grid or measured_audio, reference_grid

    downbeat_a, bar_a = phase_reliability(a)
    downbeat_b, bar_b = phase_reliability(b)
    return {
        "first_downbeat_a": float(getattr(a, "first_downbeat", 0.0) or 0.0),
        "first_downbeat_b": float(getattr(b, "first_downbeat", 0.0) or 0.0),
        "downbeat_reliable_a": downbeat_a,
        "downbeat_reliable_b": downbeat_b,
        "bar_phase_reliable_a": bar_a,
        "bar_phase_reliable_b": bar_b,
        "beatgrid_status_a": getattr(a, "beatgrid_status", "unknown"),
        "beatgrid_status_b": getattr(b, "beatgrid_status", "unknown"),
        "analysis_mode_a": getattr(a, "analysis_mode", "unknown"),
        "analysis_mode_b": getattr(b, "analysis_mode", "unknown"),
        "strict_beat_sync": True,
    }


def _transition_type_fuer(
    a,
    b,
    pc=None,
    *,
    modus: str = "kontrolliert",
    bpm_toleranz: float = STANDARD_BPM_TOLERANZ,
    energy_direction: str | None = None,
) -> str:
    """Bestimmt die Technik kontrolliert oder ueber denselben App-Vertrag."""
    if modus == "kontrolliert":
        return HOERTEST_TRANSITION_TYPE
    if modus == "produktion":
        return transition_type_for_candidate(
            a,
            b,
            pc,
            bpm_tolerance=bpm_toleranz,
            scoring_context={"energy_direction": energy_direction},
        )
    raise ValueError(f"Unbekannter transition_type_mode: {modus!r}")


def _validiere_transition_type(value: object) -> str:
    if type(value) is not str or value not in SUPPORTED_TRANSITION_TYPES:
        raise ValueError(f"Nicht unterstuetzter transition_type: {value!r}")
    return value


def rendere_paar(
    kandidat: dict,
    pair_id: str,
    clips_dir: Path,
    bpm_toleranz: float = STANDARD_BPM_TOLERANZ,
    energy_direction: str | None = None,
) -> tuple[str, object, dict]:
    """Rendert einen Uebergangs-Clip.

    Der aktive TransitionPlan ist die einzige Timing-Quelle. Rueckgabe:
    relativer Clip-Pfad, Plan und der tatsaechlich aktive PairCandidate.
    """
    a: Track = kandidat["track_a"]
    b: Track = kandidat["track_b"]
    empfehlungen = compute_transition_recommendations(
        [a, b],
        bpm_tolerance=float(bpm_toleranz),
        scoring_context={"energy_direction": energy_direction},
    )
    if not empfehlungen:
        raise ValueError("kein TransitionPlan fuer das Paar")
    empfehlung = empfehlungen[0]
    empfehlungsindex = getattr(empfehlung, "index", -1)
    if type(empfehlungsindex) is not int or empfehlungsindex != 0:
        raise ValueError("Empfehlung hat nicht den erwarteten Paar-Index 0")
    if (
        getattr(getattr(empfehlung, "from_track", None), "filePath", None) != a.filePath
        or getattr(getattr(empfehlung, "to_track", None), "filePath", None) != b.filePath
    ):
        raise ValueError("Empfehlung gehoert zu einem anderen Track-Paar")
    plan = getattr(empfehlung, "plan", None)
    if plan is None:
        raise ValueError("Empfehlung enthaelt keinen TransitionPlan")
    rang = getattr(empfehlung, "kandidat_aktiv", 0)
    if type(rang) is not int or rang <= 0:
        raise ValueError("Empfehlung hat keinen aktiven PairCandidate")
    kandidaten_liste = getattr(empfehlung, "kandidaten", None) or []
    if any(
        not isinstance(eintrag, dict)
        or type(eintrag.get("rang")) is not int
        or eintrag["rang"] <= 0
        for eintrag in kandidaten_liste
    ):
        raise ValueError("PairCandidate-Rang muss eine positive Ganzzahl sein")
    aktive = [
        eintrag for eintrag in kandidaten_liste if eintrag["rang"] == rang
    ]
    if len(aktive) != 1:
        raise ValueError(f"aktiver PairCandidate-Rang {rang} fehlt oder ist doppelt")
    aktiver_kandidat = aktive[0]
    try:
        kandidat_mix_out = float(aktiver_kandidat["t_out"])
        kandidat_mix_in = float(aktiver_kandidat["t_in"])
        kandidat_overlap = float(aktiver_kandidat["overlap_sec"])
        plan_mix_out = float(plan.mix_out_a)
        plan_mix_in = float(plan.mix_in_b)
        plan_overlap = float(plan.overlap)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Plan oder aktiver PairCandidate hat ungueltige Zeitwerte") from exc
    if not all(math.isfinite(wert) for wert in (
        kandidat_mix_out, kandidat_mix_in, kandidat_overlap,
        plan_mix_out, plan_mix_in, plan_overlap,
    )):
        raise ValueError("Plan oder aktiver PairCandidate hat nicht-endliche Zeitwerte")
    dauer_a = float(getattr(a, "duration", 0.0) or 0.0)
    dauer_b = float(getattr(b, "duration", 0.0) or 0.0)
    if not (
        math.isfinite(dauer_a) and math.isfinite(dauer_b)
        and 0.0 <= kandidat_mix_out < dauer_a
        and 0.0 <= plan_mix_out < dauer_a
        and 0.0 <= kandidat_mix_in < dauer_b
        and 0.0 <= plan_mix_in < dauer_b
    ):
        raise ValueError("Plan oder aktiver PairCandidate liegt ausserhalb der Trackdauer")
    if (
        abs(plan_mix_out - kandidat_mix_out) > QUANTIZE_TOLERANCE_SEC
        or abs(plan_mix_in - kandidat_mix_in) > QUANTIZE_TOLERANCE_SEC
    ):
        raise ValueError("TransitionPlan stimmt nicht mit dem aktiven PairCandidate ueberein")
    if (
        kandidat_overlap <= 0.0
        or plan_overlap <= 0.0
        or plan_overlap > kandidat_overlap + QUANTIZE_TOLERANCE_SEC
    ):
        raise ValueError("TransitionPlan-Overlap ist ungueltig oder groesser als der Kandidaten-Overlap")
    try:
        fade_out_start = float(plan.fade_out_start)
        fade_out_end = float(plan.fade_out_end)
    except (TypeError, ValueError) as exc:
        raise ValueError("TransitionPlan hat ungueltige Fade-Grenzen") from exc
    if not math.isfinite(fade_out_start) or not math.isfinite(fade_out_end):
        raise ValueError("TransitionPlan hat nicht-endliche Fade-Grenzen")
    if (
        abs(fade_out_start - plan_mix_out) > QUANTIZE_TOLERANCE_SEC
        or abs((fade_out_end - fade_out_start) - plan_overlap) > QUANTIZE_TOLERANCE_SEC
    ):
        raise ValueError("TransitionPlan-Fade-Grenzen widersprechen Mixpunkt oder Overlap")

    rest_a, rest_b = crossfade_reserve(
        plan_mix_out,
        dauer_a,
        dauer_b,
        plan_mix_in,
    )
    if min(rest_a, rest_b) < plan_overlap:
        raise ValueError(
            f"Crossfade von {plan_overlap:.0f} s passt nicht "
            f"(Rest A {rest_a:.1f} s, Rest B {rest_b:.1f} s)"
        )
    spec = replace(
        TransitionClipSpec.from_plan(plan, a, b),
        pre_roll_sec=PRE_ROLL_SEK,
        post_roll_sec=POST_ROLL_SEK,
        strict_beat_sync=True,
    )
    ziel = clips_dir / f"{pair_id}.wav"
    _rendere_atomar(spec, ziel)
    return f"clips/{pair_id}.wav", plan, aktiver_kandidat


def lies_csv(pfad: Path) -> list[dict]:
    with pfad.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def schreibe_csv(pfad: Path, spalten, zeilen) -> None:
    with pfad.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(spalten))
        writer.writeheader()
        writer.writerows(zeilen)


def _rendere_atomar(spec: TransitionClipSpec, ziel: Path) -> None:
    """Ein fehlgeschlagener Renderer darf nie eine sichtbare Partial-WAV lassen."""
    temp = ziel.with_name(f".{ziel.stem}.{uuid.uuid4().hex}.tmp.wav")
    try:
        render_transition_clip(spec, str(temp))
        if not temp.is_file():
            raise RuntimeError("Renderer meldete Erfolg, erzeugte aber keine WAV-Datei")
        os.replace(temp, ziel)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            logger.warning("Render-Tempdatei konnte nicht entfernt werden: %s", temp)


def _publiziere_staging(staging: Path, ziel: Path) -> None:
    """Verschiebt Staging ohne Zielueberschreibung; Scanner-Race begrenzt."""
    for versuch in range(len(PUBLISH_PERMISSION_BACKOFF_SECONDS) + 1):
        if ziel.exists():
            raise FileExistsError(f"Ausgabeziel entstand waehrend der Publikation: {ziel}")
        try:
            os.rename(staging, ziel)
            return
        except PermissionError as exc:
            # Ein Ziel-Race darf nie als Scanner-Race fehlklassifiziert werden.
            if ziel.exists():
                raise FileExistsError(
                    f"Ausgabeziel entstand waehrend der Publikation: {ziel}"
                ) from exc
            if versuch >= len(PUBLISH_PERMISSION_BACKOFF_SECONDS):
                raise PermissionError(
                    f"Ausgabe konnte nach begrenzten Windows-Retries nicht "
                    f"publiziert werden: {ziel}"
                ) from exc
            time.sleep(PUBLISH_PERMISSION_BACKOFF_SECONDS[versuch])


def _prepare_atomar(args: argparse.Namespace, funktion) -> int:
    """Baut den ganzen Satz im Geschwisterordner und publiziert ihn einmalig."""
    ziel = Path(args.out)
    if ziel.exists():
        print(f"Ausgabeziel existiert bereits; aus Sicherheitsgruenden abgelehnt: {ziel}")
        return 1
    ziel.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{ziel.name}.staging-", dir=ziel.parent))
    try:
        intern = argparse.Namespace(**vars(args))
        intern.out = staging
        intern.anzeige_out = ziel
        status = int(funktion(intern))
        if status != 0:
            return status
        try:
            _publiziere_staging(staging, ziel)
        except (FileExistsError, PermissionError) as exc:
            print(f"Ausgabe konnte nicht sicher publiziert werden: {exc}")
            return 1
        staging = None
        return 0
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


# ===========================================================================
# Kandidatenmodus (Spec 2026-08-21 Abschnitt 3): prepare --modus kandidaten
# ===========================================================================

def clip_id_fuer(pair_id: str, n: int) -> str:
    return f"{pair_id}_k{n}"


def _hauptschema(cand) -> str:
    from hpg_core.mix_candidates import SCHEMA_PRIORITAET
    s = [x for x in (cand.schema or []) if x in SCHEMA_PRIORITAET]
    return min(s, key=SCHEMA_PRIORITAET.index) if s else ""


def kandidaten_zeilen(
    pair_id: str,
    paare,
    track_a,
    track_b,
    clips: list[str],
    *,
    bpm_toleranz: float = STANDARD_BPM_TOLERANZ,
    energy_direction: str | None = None,
    rendered_transition_types: list[str] | None = None,
    transition_type_mode: str = "kontrolliert",
) -> tuple[list[dict], list[dict]]:
    """Zeilen fuer bewertung.csv und merkmale.csv je PairCandidate (Index n ab 1).
    Teilwerte None -> leere Zelle (Fit: Zeile faellt fuer das Merkmal heraus).
    bpm/genre/key sind Anzeige-Kontext fuer den Server (kein Score, kein Schema)."""
    if len(paare) != len(clips):
        raise ValueError("PairCandidates und Clips muessen 1:1 uebereinstimmen")
    if (
        rendered_transition_types is not None
        and len(rendered_transition_types) != len(paare)
    ):
        raise ValueError(
            "Gerenderte Transition-Types und PairCandidates muessen 1:1 uebereinstimmen"
        )
    bewertung, merkmale = [], []
    for n, (pc, clip) in enumerate(zip(paare, clips), start=1):
        rendered_transition_type = (
            rendered_transition_types[n - 1]
            if rendered_transition_types is not None
            else _transition_type_fuer(
                track_a,
                track_b,
                pc,
                modus=transition_type_mode,
                bpm_toleranz=bpm_toleranz,
                energy_direction=energy_direction,
            )
        )
        cid = clip_id_fuer(pair_id, n)
        bewertung.append({"pair_id": pair_id, "clip_id": cid, "note": "", "gewaehlt": "", "zeit": ""})
        zeile = {"pair_id": pair_id, "clip_id": cid, "clip": clip}
        for name in KANDIDATEN_TEILWERTE:
            wert = pc.teilwerte.get(name)
            zeile[name] = "" if wert is None else round(float(wert), 6)
        zeile.update({
            "score": round(float(pc.score), 6),
            "schema_out": _hauptschema(pc.out_a), "schema_in": _hauptschema(pc.in_b),
            "schemata_out": "|".join(pc.out_a.schema or []), "schemata_in": "|".join(pc.in_b.schema or []),
            "blend_bars": int(pc.blend_bars), "t_out": float(pc.t_out), "t_in": float(pc.t_in),
            "provenance_out": pc.out_a.provenance, "provenance_in": pc.in_b.provenance,
            "confidence_out": float(pc.out_a.confidence), "confidence_in": float(pc.in_b.confidence),
            "crossfade_sek": round(float(pc.overlap_sec), 2), "bpm_relation": pc.bpm_relation,
            "bpm_a": round(float(getattr(track_a, "bpm", 0.0) or 0.0), 1),
            "bpm_b": round(float(getattr(track_b, "bpm", 0.0) or 0.0), 1),
            "genre_a": loese_genre_auf(track_a), "genre_b": loese_genre_auf(track_b),
            "key_a": str(getattr(track_a, "camelotCode", "") or ""),
            "key_b": str(getattr(track_b, "camelotCode", "") or ""),
            "bpm_toleranz": float(bpm_toleranz),
            "energy_direction": _energy_direction_text(energy_direction),
            "rendered_transition_type": rendered_transition_type,
            "transition_type_mode": transition_type_mode,
            "track_a": track_a.filePath, "track_b": track_b.filePath,
        })
        merkmale.append(zeile)
    return bewertung, merkmale


def reihenfolge_fuer_paar(pair_id: str, clip_ids: list[str], seed_satz: int = STANDARD_SEED) -> dict:
    """Zufaellige, reproduzierbare Anzeige-Reihenfolge je Paar; der Seed wird
    mitgespeichert (reihenfolge.json)."""
    seed = int(seed_satz) + int("".join(ch for ch in pair_id if ch.isdigit()) or 0)
    clips = list(clip_ids)
    random.Random(seed).shuffle(clips)
    return {"seed": seed, "clips": clips}


def rendere_kandidat(
    a,
    b,
    pc,
    pair_id: str,
    n: int,
    clips_dir: Path,
    *,
    transition_type_mode: str = "kontrolliert",
    bpm_toleranz: float = STANDARD_BPM_TOLERANZ,
    energy_direction: str | None = None,
    transition_type_override: str | None = None,
) -> tuple[str, str]:
    """Rendert einen PairCandidate-Clip (Zeitpunkte und Blende des Kandidaten,
    sonst identisch zu rendere_paar). Wirft ValueError, wenn die Blende nicht
    in die Restlaengen passt oder ueber dem Renderer-Deckel liegt."""
    rest_a, rest_b = crossfade_reserve(float(pc.t_out), float(getattr(a, "duration", 0.0) or 0.0),
                                       float(getattr(b, "duration", 0.0) or 0.0), float(pc.t_in))
    if min(rest_a, rest_b) < float(pc.overlap_sec):
        raise ValueError(f"Blende {pc.overlap_sec:.1f} s passt nicht (Rest A {rest_a:.1f}, B {rest_b:.1f})")
    if float(pc.overlap_sec) > MAX_TRANSITION_OVERLAP_SECONDS:
        # Der gemeinsame Rendervertrag lehnt Blenden ueber 64 s unveraendert
        # ab. Hier frueh und mit Kandidatenkontext fehlschlagen.
        raise ValueError(f"Blende {pc.overlap_sec:.1f} s ueber Renderer-Deckel {MAX_TRANSITION_OVERLAP_SECONDS:.0f} s")
    if transition_type_override is not None:
        transition_type = _validiere_transition_type(transition_type_override)
        if transition_type_mode == "kontrolliert" and transition_type != HOERTEST_TRANSITION_TYPE:
            raise ValueError(
                "Kontrollierter Kandidatensatz muss pro_eq_swap verwenden"
            )
        if transition_type_mode not in {"kontrolliert", "produktion"}:
            raise ValueError(
                f"Unbekannter transition_type_mode: {transition_type_mode!r}"
            )
    else:
        transition_type = _validiere_transition_type(_transition_type_fuer(
            a,
            b,
            pc,
            modus=transition_type_mode,
            bpm_toleranz=bpm_toleranz,
            energy_direction=energy_direction,
        ))
    spec = TransitionClipSpec(
        track_a_path=a.filePath, track_b_path=b.filePath,
        mix_out_sec=float(pc.t_out), mix_in_sec=float(pc.t_in), crossfade_sec=float(pc.overlap_sec),
        transition_type=transition_type, pre_roll_sec=PRE_ROLL_SEK, post_roll_sec=POST_ROLL_SEK,
        bpm_a=float(getattr(a, "bpm", 0.0) or 120.0), bpm_b=float(getattr(b, "bpm", 0.0) or 120.0),
        **_strict_render_fields(a, b),
    )
    ziel = clips_dir / f"{clip_id_fuer(pair_id, n)}.wav"
    _rendere_atomar(spec, ziel)
    return f"clips/{clip_id_fuer(pair_id, n)}.wav", transition_type


LIESMICH_KANDIDATEN = """HPG Hoertest — Kandidatenmodus
Je Paar liegen hoechstens fuenf Clips (<pair_id>_k<n>.wav): gleicher Uebergang, andere
Mixpunkte/Blende. Seite je Paar: jeden Clip mit 1-5 benoten UND den besten
waehlen. Alles wird sofort in bewertung.csv geschrieben (pair_id, clip_id,
note, gewaehlt, zeit). Anzeige bewusst ohne Score/Schema.

Start am PC:   python tools/hoertest_server.py --dir <dieser Ordner> --port 8767
Mobil: diesen Ordner samt hoertest_server.py (Repo tools/) in den Mobil-Ordner
kopieren; der Server erkennt den Kandidatenmodus selbst (Spalte clip_id).
Audit:         python tools/audit_candidate_set.py --set-dir <Ordner> --cache <cache-v42.db> --report <separater-report.json>
Auswertung:    python tools/rate_transitions.py fit --modus kandidaten --dir <Ordner> --cache <cache-v42.db> --audit-report <separater-report.json>
Der Satz speichert --bpm-toleranz und --energy-direction je Clip. Der strenge
Audit spielt exakt mit diesen Regeln nach; "auto" bedeutet keine feste Richtung.
Das Manifest friert auch --harmonic-strictness und --allow-experimental ein.
MIN_HARMONIC_SCORE ist ein zusaetzliches hartes Gate nur fuer diesen Kandidaten-
Hoertest, keine Behauptung vollstaendiger Produktionsparitaet. APP_VERSION und
Algorithmus-/Build-Digest sichern den lokal verwendeten Python-Code ab.
"""


def _befehl_prepare_kandidaten_intern(args: argparse.Namespace) -> int:
    out = Path(args.out)
    anzeige_out = Path(getattr(args, "anzeige_out", out))
    clips_dir = out / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    cache = _cache_pfad(args.cache)
    _reject_pending_wal(cache)
    cache_fingerprint = _fingerprint_cache(cache)
    algorithm_build = _algorithm_build_fingerprint()
    tracks = lade_tracks_aus_cache(str(cache))
    print(f"Analysierte Tracks im Cache: {len(tracks)}")
    energy_direction = getattr(args, "energy_direction", None)
    scoring_snapshot = _baue_scoring_snapshot(args)
    kandidaten = sammle_kandidaten(
        tracks,
        args.bpm_toleranz,
        energy_direction,
        scoring_snapshot=scoring_snapshot,
    )
    if getattr(args, "nur_genre", None):
        kandidaten = filtere_nach_genre(kandidaten, args.nur_genre)
    print(f"Paare nach Gates: {len(kandidaten)}")
    if not kandidaten:
        print("Keine Paare — nichts zu rendern.")
        return 1
    vektor_faktoren = (
        KANDIDATEN_TEILWERTE
        if all(all(n in k["merkmale"] for n in KANDIDATEN_TEILWERTE) for k in kandidaten)
        else NEUE_FAKTOREN
    )
    vektoren = [[k["merkmale"][n] for n in vektor_faktoren] for k in kandidaten]
    # Die Audio-Synchronpruefung kann viele ansonsten geeignete Paare verwerfen.
    # Acht Reserven pro Zielpaar reichen fuer den strengen Hoertest, ohne die
    # komplette Kandidatenmenge teuer in eine Maximin-Reihenfolge zu bringen.
    reserve = maximin_auswahl(
        vektoren,
        min(len(kandidaten), args.anzahl * RESERVE_FAKTOR * 2),
        seed=args.seed,
    )
    bewertung_zeilen, merkmal_zeilen, reihenfolge = [], [], {}
    manifest_paare: list[dict] = []
    paare_fertig, uebersprungen = 0, 0
    for index in reserve:
        if paare_fertig >= args.anzahl:
            break
        k = kandidaten[index]
        a, b = k["track_a"], k["track_b"]
        pcs = list(k.get("pair_candidates") or _rank_pair_mit_snapshot(
            a,
            b,
            scoring_snapshot=scoring_snapshot,
        ))
        max_versionen = int(getattr(
            args,
            "max_versionen_pro_paar",
            STANDARD_MAX_VERSIONEN_PRO_PAAR,
        ))
        pcs = pcs[:max_versionen]
        if not pcs:
            uebersprungen += 1
            continue
        if [int(pc.rang) for pc in pcs] != list(range(1, len(pcs) + 1)):
            raise ValueError("Kandidaten sind kein exakter Top-N-Rangprefix")
        pair_id = f"{paare_fertig + 1:03d}"
        print(f"[{paare_fertig + 1}/{args.anzahl}] Paar {pair_id}: {len(pcs)} Kandidaten ...", flush=True)
        pair_temp = Path(tempfile.mkdtemp(prefix=f".{pair_id}-", dir=clips_dir))
        clips: list[str] = []
        gerenderte_typen: list[str] = []
        verschoben: list[Path] = []
        try:
            for n, pc in enumerate(pcs, start=1):
                clip, gerenderter_typ = rendere_kandidat(
                    a,
                    b,
                    pc,
                    pair_id,
                    n,
                    pair_temp,
                    transition_type_mode=getattr(
                        args, "transition_type_mode", "kontrolliert"
                    ),
                    bpm_toleranz=args.bpm_toleranz,
                    energy_direction=energy_direction,
                )
                clips.append(clip)
                gerenderte_typen.append(_validiere_transition_type(gerenderter_typ))
            for n in range(1, len(pcs) + 1):
                quelle = pair_temp / f"{pair_id}_k{n}.wav"
                ziel = clips_dir / quelle.name
                if not quelle.is_file():
                    raise RuntimeError(f"Kandidatenclip fehlt nach Render: {quelle.name}")
                os.replace(quelle, ziel)
                verschoben.append(ziel)
        except Exception as exc:  # noqa: BLE001 — Reservepaar statt Teilsatz
            for pfad in verschoben:
                pfad.unlink(missing_ok=True)
            logger.warning("Paar %s vollstaendig verworfen: %s", pair_id, exc)
            uebersprungen += 1
            continue
        finally:
            shutil.rmtree(pair_temp, ignore_errors=True)
        bew, merk = kandidaten_zeilen(
            pair_id,
            pcs,
            a,
            b,
            clips,
            bpm_toleranz=args.bpm_toleranz,
            energy_direction=energy_direction,
            rendered_transition_types=gerenderte_typen,
            transition_type_mode=getattr(
                args, "transition_type_mode", "kontrolliert"
            ),
        )
        bewertung_zeilen += bew
        merkmal_zeilen += merk
        reihenfolge[pair_id] = reihenfolge_fuer_paar(pair_id, [z["clip_id"] for z in bew], args.seed)
        manifest_paare.append({
            "pair_id": pair_id,
            "track_a": str(a.filePath),
            "track_b": str(b.filePath),
            "clips": [
                {
                    "clip_id": clip_id_fuer(pair_id, n),
                    "rank": int(pc.rang),
                    "t_out": float(pc.t_out),
                    "t_in": float(pc.t_in),
                    "blend_bars": int(pc.blend_bars),
                    "overlap_sec": float(pc.overlap_sec),
                    "rendered_transition_type": gerenderte_typen[n - 1],
                }
                for n, pc in enumerate(pcs, start=1)
            ],
        })
        paare_fertig += 1
    if paare_fertig != args.anzahl:
        print(
            f"Satz unvollstaendig: {paare_fertig} von {args.anzahl} Paaren "
            "konnten vollstaendig vorbereitet werden; nichts veroeffentlicht."
        )
        return 1
    schreibe_csv(out / "bewertung.csv", BEWERTUNG_KANDIDATEN_SPALTEN, bewertung_zeilen)
    schreibe_csv(out / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmal_zeilen)
    _schreibe_json_atomar(out / "reihenfolge.json", reihenfolge)
    (out / "LIESMICH-kandidaten.txt").write_text(LIESMICH_KANDIDATEN, encoding="utf-8")
    _reject_pending_wal(cache)
    if _fingerprint_cache(cache) != cache_fingerprint:
        raise RuntimeError("Cache wurde waehrend der Kandidatenvorbereitung veraendert")
    if _algorithm_build_fingerprint() != algorithm_build:
        raise RuntimeError(
            "Algorithmus-/Build-Dateien wurden waehrend der Vorbereitung veraendert"
        )
    manifest = {
        "format_version": KANDIDATEN_MANIFEST_VERSION,
        "app_version": APP_VERSION,
        "algorithm_build": algorithm_build,
        "hearing_test_contract": {
            "harmonic_gate_scope": HARMONIC_GATE_SCOPE,
            "minimum_harmonic_score": MIN_HARMONIC_SCORE,
        },
        "cache": {
            "version": CACHE_VERSION,
            **cache_fingerprint,
        },
        "render_args": {
            "anzahl": int(args.anzahl),
            "max_versionen_pro_paar": int(getattr(
                args,
                "max_versionen_pro_paar",
                STANDARD_MAX_VERSIONEN_PRO_PAAR,
            )),
            "nur_genre": getattr(args, "nur_genre", None),
            "transition_type_mode": getattr(
                args, "transition_type_mode", "kontrolliert"
            ),
            "seed": int(args.seed),
        },
        "scoring_snapshot": scoring_snapshot,
        "pairs": manifest_paare,
    }
    _schreibe_json_atomar(out / KANDIDATEN_MANIFEST_NAME, manifest)
    print(f"Paare: {paare_fertig}   Clips: {len(merkmal_zeilen)}   uebersprungen: {uebersprungen}")
    print(f"Jetzt bewerten: python tools/hoertest_server.py --dir {anzeige_out} --port 8767")
    return 0


def befehl_prepare_kandidaten(args: argparse.Namespace) -> int:
    return _prepare_atomar(args, _befehl_prepare_kandidaten_intern)


# ===========================================================================
# Unterbefehl: prepare
# ===========================================================================

def _befehl_prepare_intern(args: argparse.Namespace) -> int:
    out = Path(args.out)
    anzeige_out = Path(getattr(args, "anzeige_out", out))
    clips_dir = out / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    tracks = lade_tracks_aus_cache(args.cache)
    print(f"Analysierte Tracks im Cache: {len(tracks)}")

    energy_direction = getattr(args, "energy_direction", None)
    kandidaten = sammle_kandidaten(tracks, args.bpm_toleranz, energy_direction)
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
            clip, plan, aktiver_kandidat_dict = rendere_paar(
                kandidat,
                pair_id,
                clips_dir,
                bpm_toleranz=args.bpm_toleranz,
                energy_direction=energy_direction,
            )
            aktiver_kandidat = PairCandidate.from_dict(aktiver_kandidat_dict)
            aktive_faktoren = _faktoren_vollstaendig(aktiver_kandidat)
            if aktive_faktoren is None:
                raise ValueError("aktiver PairCandidate hat unvollstaendige Faktoren")
            aktive_metriken = transition_metrics_from_candidate(aktiver_kandidat)
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
            {n: round(aktive_faktoren[n], 6) for n in ALLE_FAKTOREN}
        )
        # Die Blendenlaenge variiert von Paar zu Paar. Sie wird mitgeschrieben,
        # damit die Konfundierung nachtraeglich von Hand pruefbar ist: der Fit
        # liest sie NICHT (verbinde_bewertungen nimmt nur ALLE_FAKTOREN), sie
        # geht also nicht als Kontrollvariable ins Modell ein.
        zeile["crossfade_sek"] = round(float(plan.overlap), 2)
        zeile["overall_score"] = round(float(aktive_metriken.overall_score), 4)
        zeile["lufs_delta"] = (
            "" if aktive_metriken.lufs_delta is None
            else round(float(aktive_metriken.lufs_delta), 2)
        )
        zeile.update({
            "plan_mix_out_sec": round(float(plan.mix_out_a), 6),
            "plan_mix_in_sec": round(float(plan.mix_in_b), 6),
            "plan_overlap_sec": round(float(plan.overlap), 6),
            "plan_transition_type": str(plan.transition_type),
            "plan_target_sr": int(plan.target_sr),
            "kandidat_rang": int(aktiver_kandidat.rang),
            "bpm_toleranz": float(args.bpm_toleranz),
            "energy_direction": _energy_direction_text(energy_direction),
        })
        zeile["track_a"] = kandidat["track_a"].filePath
        zeile["track_b"] = kandidat["track_b"].filePath
        merkmal_zeilen.append(zeile)

    if len(merkmal_zeilen) != args.anzahl:
        print(
            f"Satz unvollstaendig: {len(merkmal_zeilen)} von {args.anzahl} Clips "
            "konnten gerendert werden; nichts veroeffentlicht."
        )
        return 1

    schreibe_csv(out / "bewertung.csv", ("pair_id", "clip", "bewertung"),
                 bewertung_zeilen)
    schreibe_csv(
        out / "merkmale.csv",
        ("pair_id", *ALLE_FAKTOREN, "crossfade_sek", *ZUSATZ_SPALTEN,
         *PLAN_AUDIT_SPALTEN,
         "track_a", "track_b"),
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
    print(f"    python tools/hoertest_server.py --dir {anzeige_out}")
    print(f"Die Seite spielt die Clips und schreibt die Noten selbst nach "
          f"{anzeige_out / 'bewertung.csv'}.")
    return 0


def befehl_prepare(args: argparse.Namespace) -> int:
    return _prepare_atomar(args, _befehl_prepare_intern)


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

def _ganzzahl_im_bereich(name: str, minimum: int, maximum: int):
    def konvertiere(roh: str) -> int:
        try:
            wert = int(roh)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{name} muss eine Ganzzahl sein") from exc
        if not minimum <= wert <= maximum:
            raise argparse.ArgumentTypeError(
                f"{name} muss zwischen {minimum} und {maximum} liegen"
            )
        return wert
    return konvertiere


def _bpm_toleranz_arg(roh: str) -> float:
    try:
        wert = float(roh)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bpm-toleranz muss numerisch sein") from exc
    if not math.isfinite(wert) or not 0.0 < wert <= PAAR_BPM_MAX:
        raise argparse.ArgumentTypeError(
            f"bpm-toleranz muss endlich, groesser 0 und hoechstens {PAAR_BPM_MAX:g} sein"
        )
    return wert


def _energy_direction_arg(roh: str) -> str | None:
    wert = str(roh).strip().casefold()
    if wert == "auto":
        return None
    if wert in {"up", "down", "maintain"}:
        return wert
    raise argparse.ArgumentTypeError(
        "energy-direction muss auto, up, down oder maintain sein"
    )


def _striktes_bool_arg(roh: str) -> bool:
    if roh == "true":
        return True
    if roh == "false":
        return False
    raise argparse.ArgumentTypeError("Wert muss exakt true oder false sein")


def _energy_direction_text(value: str | None) -> str:
    return "auto" if value is None else str(value).strip().casefold()

# ===========================================================================
# Kandidatenmodus: fit --modus kandidaten — reine Logik
# ===========================================================================

def verbinde_bewertungen_kandidaten(merkmale_zeilen, bewertung_zeilen, merkmale=KANDIDATEN_TEILWERTE,
                                    genre_von=None) -> tuple[list[dict], int, int]:
    """Join ueber clip_id. Rueckgabe (Zeilen, ohne Note, verworfen). Verworfen =
    ungueltige Note oder ein leeres Merkmal (keine Imputation). Clips ohne Note
    bleiben (note None) — der Paarvergleich braucht alle Clips eines Paars."""
    noten = {str(z.get("clip_id", "")).strip(): z for z in bewertung_zeilen}
    zeilen, ohne, verworfen = [], 0, 0
    for roh in merkmale_zeilen:
        cid = str(roh.get("clip_id", "")).strip()
        b = noten.get(cid) or {}
        eintrag = str(b.get("note", "")).strip()
        try:
            werte = {n: float(roh[n]) for n in merkmale}
        except (KeyError, TypeError, ValueError):
            verworfen += 1            # leeres/ungueltiges Merkmal: fuer BEIDE Modelle raus
            continue
        note = None
        if eintrag:
            if not eintrag.isdecimal():
                verworfen += 1
                continue
            note = int(eintrag)
            if not BEWERTUNG_MIN <= note <= BEWERTUNG_MAX:
                verworfen += 1
                continue
        else:
            ohne += 1                 # ohne Note: bleibt fuer den Paarvergleich erhalten
        tracks = (str(roh.get("track_a", "")), str(roh.get("track_b", "")))
        genre_a = genre_von(tracks[0]) if genre_von else ""
        genre_b = genre_von(tracks[1]) if genre_von else ""
        zeilen.append({
            "pair_id": str(roh.get("pair_id", "")).strip(), "clip_id": cid,
            "note": note, "bewertung": note,   # "bewertung": Schluessel fuer zu_zielgroesse
            "gewaehlt": str(b.get("gewaehlt", "")).strip() == "1", "merkmale": werte, "tracks": tracks,
            "genre_a": genre_a, "genre_b": genre_b,
            "genre": genre_a if genre_a == genre_b else "",
            "schema_out": roh.get("schema_out", ""), "schema_in": roh.get("schema_in", ""),
            "schemata_out": [s for s in str(roh.get("schemata_out", "")).split("|") if s],
            "schemata_in": [s for s in str(roh.get("schemata_in", "")).split("|") if s],
        })
    return zeilen, ohne, verworfen


def filtere_reine_kandidatenpaare(zeilen: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Laesst nur konsistente Paare zweier Tracks desselben kanonischen Genres durch."""
    paare: dict[str, list[dict]] = {}
    for zeile in zeilen:
        paare.setdefault(str(zeile.get("pair_id", "")), []).append(zeile)

    ergebnis: list[dict] = []
    diagnose = {
        "inkonsistente_paare": 0, "inkonsistente_clips": 0,
        "gemischte_paare": 0, "gemischte_clips": 0,
        "unbekannte_paare": 0, "unbekannte_clips": 0,
    }
    kanonisch = set(CANONICAL_GENRES)
    for clips in paare.values():
        identitaeten = {
            (tuple(z.get("tracks") or ()), z.get("genre_a", ""), z.get("genre_b", ""))
            for z in clips
        }
        if len(identitaeten) != 1:
            diagnose["inkonsistente_paare"] += 1
            diagnose["inkonsistente_clips"] += len(clips)
            continue
        _, genre_a, genre_b = next(iter(identitaeten))
        if genre_a not in kanonisch or genre_b not in kanonisch:
            diagnose["unbekannte_paare"] += 1
            diagnose["unbekannte_clips"] += len(clips)
            continue
        if genre_a != genre_b:
            diagnose["gemischte_paare"] += 1
            diagnose["gemischte_clips"] += len(clips)
            continue
        for clip in clips:
            clip["genre"] = genre_a
        ergebnis.extend(clips)
    return ergebnis, diagnose


def validiere_kandidaten_csvs(
    merkmale_zeilen: list[dict], bewertung_zeilen: list[dict]
) -> None:
    """Erzwingt den unverfaelschten 1:1-Vertrag des Kandidatensatzes."""
    def indexiere(zeilen: list[dict], quelle: str) -> dict[tuple[str, str], dict]:
        index: dict[tuple[str, str], dict] = {}
        clip_ids: set[str] = set()
        for nummer, zeile in enumerate(zeilen, start=2):
            pair_id = str(zeile.get("pair_id", "")).strip()
            clip_id = str(zeile.get("clip_id", "")).strip()
            if not pair_id or not clip_id:
                raise ValueError(f"{quelle} Zeile {nummer}: pair_id/clip_id fehlt")
            schluessel = (pair_id, clip_id)
            if schluessel in index or clip_id in clip_ids:
                raise ValueError(f"{quelle}: clip_id nicht eindeutig: {clip_id}")
            index[schluessel] = zeile
            clip_ids.add(clip_id)
        return index

    merk_index = indexiere(merkmale_zeilen, "merkmale.csv")
    bew_index = indexiere(bewertung_zeilen, "bewertung.csv")
    if set(merk_index) != set(bew_index):
        fehlt_bew = sorted(set(merk_index) - set(bew_index))
        fehlt_merk = sorted(set(bew_index) - set(merk_index))
        raise ValueError(
            "CSV-Zeilen sind nicht 1:1 identisch "
            f"(ohne Bewertung: {fehlt_bew[:3]}, ohne Merkmale: {fehlt_merk[:3]})"
        )

    gewinner_je_paar: dict[str, int] = {}
    for schluessel, zeile in bew_index.items():
        note = str(zeile.get("note", "")).strip()
        if note and (not note.isdecimal() or not BEWERTUNG_MIN <= int(note) <= BEWERTUNG_MAX):
            raise ValueError(f"bewertung.csv: Note fuer {schluessel[1]} muss eine Ganzzahl 1..5 sein")
        gewaehlt = str(zeile.get("gewaehlt", "")).strip()
        if gewaehlt not in {"", "0", "1"}:
            raise ValueError(f"bewertung.csv: gewaehlt fuer {schluessel[1]} muss leer, 0 oder 1 sein")
        if gewaehlt == "1":
            gewinner_je_paar[schluessel[0]] = gewinner_je_paar.get(schluessel[0], 0) + 1
            if gewinner_je_paar[schluessel[0]] > 1:
                raise ValueError(f"bewertung.csv: mehr als ein Gewinner fuer Paar {schluessel[0]}")

    for schluessel, zeile in merk_index.items():
        if not str(zeile.get("track_a", "")).strip() or not str(
            zeile.get("track_b", "")
        ).strip():
            raise ValueError(
                f"merkmale.csv: track_a/track_b fuer {schluessel[1]} fehlt"
            )
        for name in KANDIDATEN_TEILWERTE:
            try:
                wert = float(zeile[name])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"merkmale.csv: {name} fuer {schluessel[1]} ungueltig") from exc
            if not math.isfinite(wert) or not 0.0 <= wert <= 1.0:
                raise ValueError(
                    f"merkmale.csv: {name} fuer {schluessel[1]} liegt nicht endlich in 0..1"
                )


def validiere_vollstaendige_kandidatenbewertung(
    bewertung_zeilen: list[dict],
) -> None:
    """Verlangt abgeschlossene menschliche Noten und Paarentscheidungen."""
    je_paar: dict[str, list[dict]] = {}
    for zeile in bewertung_zeilen:
        pair_id = str(zeile.get("pair_id", "")).strip()
        clip_id = str(zeile.get("clip_id", "")).strip()
        note = str(zeile.get("note", "")).strip()
        if note not in {"1", "2", "3", "4", "5"}:
            raise ValueError(
                f"bewertung.csv: vollstaendige Ganzzahl-Note 1..5 fehlt fuer {clip_id}"
            )
        je_paar.setdefault(pair_id, []).append(zeile)

    for pair_id, clips in je_paar.items():
        if len(clips) < 2:
            continue
        gewinner = [z for z in clips if str(z.get("gewaehlt", "")).strip() == "1"]
        if len(gewinner) == 1:
            if int(str(gewinner[0]["note"]).strip()) < 2:
                raise ValueError(
                    f"bewertung.csv: Gewinnernote fuer Paar {pair_id} muss mindestens 2 sein"
                )
            continue
        keine_beste = all(
            str(z.get("gewaehlt", "")).strip() == "0" for z in clips
        )
        if len(gewinner) == 0 and keine_beste:
            continue
        raise ValueError(
            f"bewertung.csv: Paar {pair_id} braucht exakt einen Gewinner oder "
            "explizit Keine-Beste (alle gewaehlt=0)"
        )


def _lade_json_strikt(path: Path, label: str) -> dict:
    try:
        daten = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda raw: (_ for _ in ()).throw(
                ValueError(f"{label} enthaelt nicht-endliche JSON-Konstante {raw}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} ist unlesbar: {exc}") from exc
    if type(daten) is not dict:
        raise ValueError(f"{label} muss ein JSON-Objekt sein")
    return daten


def _manifest_clip_ids(manifest: dict) -> list[tuple[str, str]]:
    """Liest die kanonische, geordnete Paar-/Clip-Liste aus dem Manifest."""
    render_args = manifest.get("render_args")
    pairs = manifest.get("pairs")
    if type(render_args) is not dict or type(pairs) is not list:
        raise ValueError("Manifest enthaelt keine gueltigen render_args/pairs")
    anzahl = render_args.get("anzahl")
    if type(anzahl) is not int or anzahl <= 0 or len(pairs) != anzahl:
        raise ValueError("Manifest-Paarzahl stimmt nicht mit render_args.anzahl")

    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pair_index, pair in enumerate(pairs, start=1):
        if type(pair) is not dict or set(pair) != {
            "pair_id", "track_a", "track_b", "clips",
        }:
            raise ValueError("Manifest-Paar hat kein exaktes Schema")
        pair_id = pair.get("pair_id")
        expected_pair_id = f"{pair_index:03d}"
        if pair_id != expected_pair_id or type(pair.get("track_a")) is not str or type(
            pair.get("track_b")
        ) is not str:
            raise ValueError("Manifest-Paar-ID oder Trackpfad ist ungueltig")
        clips = pair.get("clips")
        if type(clips) is not list or not clips:
            raise ValueError(f"Manifest-Paar {pair_id} enthaelt keine Clips")
        for clip_index, clip in enumerate(clips, start=1):
            if type(clip) is not dict or set(clip) != {
                "clip_id", "rank", "t_out", "t_in", "blend_bars",
                "overlap_sec", "rendered_transition_type",
            }:
                raise ValueError("Manifest-Clip hat kein exaktes Schema")
            clip_id = clip.get("clip_id")
            if type(clip_id) is not str or clip_id != f"{pair_id}_k{clip_index}":
                raise ValueError("Manifest-clip_id ist nicht kanonisch geordnet")
            if clip_id in seen:
                raise ValueError(f"Manifest enthaelt doppelte clip_id: {clip_id}")
            seen.add(clip_id)
            result.append((pair_id, clip_id))
    return result


def _csv_clip_ids(set_dir: Path, datei: str) -> tuple[list[tuple[str, str]], list[dict]]:
    rows = lies_csv(set_dir / datei)
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        pair_id = row.get("pair_id")
        clip_id = row.get("clip_id")
        if type(pair_id) is not str or type(clip_id) is not str:
            raise ValueError(f"{datei} enthaelt ungueltige Paar-/Clip-ID")
        if pair_id != pair_id.strip() or clip_id != clip_id.strip() or clip_id in seen:
            raise ValueError(f"{datei} enthaelt unkanonische oder doppelte clip_id")
        seen.add(clip_id)
        result.append((pair_id, clip_id))
    return result, rows


def _fit_binding_token(ordner: Path, audit_report_arg) -> tuple[tuple[str, object], ...]:
    """Unveraenderlicher Digest der Fit-Eingaben inklusive aller Satzdateien."""
    if not audit_report_arg:
        raise ValueError("fit --modus kandidaten verlangt --audit-report")
    set_dir = ordner.resolve(strict=True)
    audit_path = Path(audit_report_arg).resolve(strict=True)
    dateien = {
        "manifest_sha256": set_dir / KANDIDATEN_MANIFEST_NAME,
        "merkmale_sha256": set_dir / "merkmale.csv",
        "bewertung_sha256": set_dir / "bewertung.csv",
        "audit_sha256": audit_path,
    }
    digests = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in dateien.items()
    }
    satz = _fingerprint_kandidatensatz(set_dir)
    return (
        ("set_path", str(set_dir)),
        ("audit_path", str(audit_path)),
        ("set_files", satz["files"]),
        ("set_sha256", satz["sha256"]),
        *(sorted(digests.items())),
    )


def _bestaetige_fit_binding(
    erwartet: tuple[tuple[str, object], ...], ordner: Path, audit_report_arg
) -> None:
    if _fit_binding_token(ordner, audit_report_arg) != erwartet:
        raise ValueError("Kandidatensatz oder Audit-Report wurde waehrend fit veraendert")


def _lies_fit_csv_gebunden(
    pfad: Path, erwartet: tuple[tuple[str, object], ...], digest_name: str
) -> list[dict]:
    """Parst genau die CSV-Bytes, deren Digest im Start-Token steht."""
    erwartet_map = dict(erwartet)
    roh = pfad.read_bytes()
    if hashlib.sha256(roh).hexdigest() != erwartet_map[digest_name]:
        raise ValueError(f"{pfad.name} wurde waehrend fit veraendert")
    try:
        text = roh.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text, newline="")))
    except (UnicodeError, csv.Error) as exc:
        raise ValueError(f"{pfad.name} ist unlesbar: {exc}") from exc


def _validiere_audit_kandidaten(
    report: dict, manifest: dict, set_dir: Path
) -> None:
    """Bindet jeden Audit-Kandidaten an Manifest, CSV und reale WAV-Metadaten."""
    expected = _manifest_clip_ids(manifest)
    merkmale_ids, merkmale = _csv_clip_ids(set_dir, "merkmale.csv")
    bewertung_ids, _bewertung = _csv_clip_ids(set_dir, "bewertung.csv")
    if merkmale_ids != expected or bewertung_ids != expected:
        raise ValueError("Manifest, merkmale.csv und bewertung.csv sind nicht exakt 1:1 geordnet")

    pair_count = report.get("pairs")
    clip_count = report.get("clips")
    if type(pair_count) is not int or pair_count != len(manifest["pairs"]):
        raise ValueError("Audit-Report.pairs stimmt nicht exakt")
    if type(clip_count) is not int or clip_count != len(expected):
        raise ValueError("Audit-Report.clips stimmt nicht exakt")
    candidates = report.get("candidates")
    if type(candidates) is not list or len(candidates) != len(expected):
        raise ValueError("Audit-Report.candidates ist nicht vollstaendig")
    report_ids = [candidate.get("clip_id") if type(candidate) is dict else None for candidate in candidates]
    expected_ids = [clip_id for _pair_id, clip_id in expected]
    if report_ids != expected_ids or len(set(report_ids)) != len(report_ids):
        raise ValueError("Audit-Report.candidates folgt nicht exakt den eindeutigen clip_ids")

    rows_by_id = {row["clip_id"]: row for row in merkmale}
    clips_root = (set_dir / "clips").resolve(strict=True)
    for candidate in candidates:
        if set(candidate) != {"clip_id", "wav", "kick_lag_seconds"}:
            raise ValueError("Audit-Kandidat hat kein exaktes Schema")
        clip_id = candidate["clip_id"]
        wav = candidate["wav"]
        if type(wav) is not dict or set(wav) != {
            "samplerate", "channels", "frames", "format", "subtype",
        }:
            raise ValueError(f"{clip_id}: WAV-Metadaten haben kein exaktes Schema")
        if (
            type(wav["samplerate"]) is not int
            or wav["samplerate"] <= 0
            or type(wav["channels"]) is not int
            or wav["channels"] != 2
            or type(wav["frames"]) is not int
            or wav["frames"] <= 0
            or wav["format"] != "WAV"
            or wav["subtype"] != "PCM_16"
        ):
            raise ValueError(f"{clip_id}: WAV-Vertrag ist nicht PCM_16/Stereo/positiv")

        rel = rows_by_id[clip_id].get("clip")
        if type(rel) is not str or Path(rel).as_posix() != f"clips/{clip_id}.wav":
            raise ValueError(f"{clip_id}: CSV-Clip-Pfad ist ungueltig")
        actual_path = (set_dir / rel).resolve(strict=True)
        try:
            actual_path.relative_to(clips_root)
            info = sf.info(actual_path)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(f"{clip_id}: WAV ist nicht sicher lesbar") from exc
        actual = {
            "samplerate": int(info.samplerate),
            "channels": int(info.channels),
            "frames": int(info.frames),
            "format": info.format,
            "subtype": info.subtype,
        }
        if wav != actual:
            raise ValueError(f"{clip_id}: Audit-WAV-Metadaten stimmen nicht mit Datei")

        lags = candidate["kick_lag_seconds"]
        if type(lags) is not list or len(lags) != 3:
            raise ValueError(f"{clip_id}: exakt drei Kick-Lags erforderlich")
        for lag in lags:
            number = _endliche_zahl(lag, f"{clip_id}: Kick-Lag")
            if abs(number) > KICK_SYNC_MAX_ERROR_SECONDS:
                raise ValueError(f"{clip_id}: Kick-Lag ueberschreitet 6 ms")


def _validiere_fit_bindung(ordner: Path, cache_arg, audit_report_arg) -> dict:
    """Bindet Fit fail-closed an Manifest, Cache, Build und Erfolgs-Audit."""
    if not cache_arg:
        raise ValueError("fit --modus kandidaten verlangt explizites --cache")
    if not audit_report_arg:
        raise ValueError("fit --modus kandidaten verlangt --audit-report")
    set_dir = ordner.resolve(strict=True)
    cache = _cache_pfad(str(cache_arg))
    manifest_path = (set_dir / KANDIDATEN_MANIFEST_NAME).resolve(strict=True)
    manifest = _lade_json_strikt(manifest_path, KANDIDATEN_MANIFEST_NAME)
    if set(manifest) != {
        "format_version", "app_version", "algorithm_build",
        "hearing_test_contract", "cache", "render_args", "scoring_snapshot",
        "pairs",
    }:
        raise ValueError("kandidaten_manifest.json hat kein exaktes Schema")
    if manifest.get("format_version") != KANDIDATEN_MANIFEST_VERSION:
        raise ValueError("Manifest-Version stimmt nicht")
    if manifest.get("app_version") != APP_VERSION:
        raise ValueError("Manifest-App-Version stimmt nicht")
    build = _algorithm_build_fingerprint()
    if manifest.get("algorithm_build") != build:
        raise ValueError("Manifest-Build-Digest stimmt nicht mit lokalem Code")
    cache_fingerprint = {"version": CACHE_VERSION, **_fingerprint_cache(cache)}
    if manifest.get("cache") != cache_fingerprint:
        raise ValueError("Manifest-Cache-Digest stimmt nicht mit --cache")

    report_path = Path(audit_report_arg).resolve(strict=True)
    report = _lade_json_strikt(report_path, "Audit-Report")
    if set(report) != {
        "format_version", "status", "ok", "set", "cache", "algorithm_build",
        "pairs", "clips", "candidates",
    }:
        raise ValueError("Audit-Report hat kein exaktes Schema")
    if report.get("format_version") != 1 or report.get("status") != "passed" or report.get("ok") is not True:
        raise ValueError("Audit-Report ist kein explizit erfolgreicher Report")
    set_binding = report.get("set")
    if type(set_binding) is not dict or set(set_binding) != {
        "path", "manifest_sha256", "files", "sha256",
    }:
        raise ValueError("Audit-Report.set hat kein exaktes Schema")
    expected_set = {
        "path": str(set_dir),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        **_fingerprint_kandidatensatz(set_dir),
    }
    if set_binding != expected_set:
        raise ValueError("Audit-Report gehoert nicht zu diesem Kandidatensatz")
    if report.get("cache") != cache_fingerprint:
        raise ValueError("Audit-Report gehoert nicht zu diesem Cache")
    if report.get("algorithm_build") != build:
        raise ValueError("Audit-Report gehoert nicht zu diesem Build")
    _validiere_audit_kandidaten(report, manifest, set_dir)
    return manifest


def _schreibe_json_atomar(ziel: Path, daten: dict) -> None:
    ziel.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{ziel.name}.", suffix=".tmp", dir=ziel.parent
    )
    temp = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(
                daten,
                stream,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, ziel)
    finally:
        temp.unlink(missing_ok=True)


def nur_mit_note(zeilen: list[dict]) -> list[dict]:
    """Zielgroesse 1 (Note) sieht nur benotete Clips; Zielgroesse 2 alle."""
    return [z for z in zeilen if z.get("note") is not None]


def _kennzahlen(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Spaltenmittel und -streuung (Streuung 0 -> 1), Grundlage fuer
    _standardisiere_mit — Holdout wird mit den TRAIN-Kennzahlen skaliert."""
    X = np.asarray(X, dtype=float)
    mittel = X.mean(axis=0)
    streuung = X.std(axis=0)
    streuung[streuung == 0.0] = 1.0
    return mittel, streuung


def _standardisiere_mit(X: np.ndarray, mittel: np.ndarray, streuung: np.ndarray) -> np.ndarray:
    return (np.asarray(X, dtype=float) - mittel) / streuung


def auc(y: np.ndarray, score: np.ndarray) -> float | None:
    """Flaeche unter der ROC-Kurve als Rangstatistik (Mann-Whitney); None,
    wenn eine Klasse fehlt."""
    y = np.asarray(y, dtype=float)
    score = np.asarray(score, dtype=float)
    pos, neg = score[y == 1.0], score[y == 0.0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    groesser = (pos[:, None] > neg[None, :]).sum()
    gleich = (pos[:, None] == neg[None, :]).sum()
    return float((groesser + 0.5 * gleich) / (len(pos) * len(neg)))


def holdout_nach_tracks_mit_diagnose(
    zeilen: list[dict], anteil: float = HOLDOUT_ANTEIL, seed: int = STANDARD_SEED
) -> tuple[list[dict], list[dict], int, int]:
    """Strikter Track-Holdout; Paare ueber der Train-/Holdout-Grenze fallen weg."""
    tracks = sorted({t for z in zeilen for t in z["tracks"]})
    random.Random(seed).shuffle(tracks)
    n_hold = int(round(len(tracks) * anteil))
    hold = set(tracks[:n_hold])
    train = [z for z in zeilen if not set(z["tracks"]) & hold]
    holdout = [z for z in zeilen if set(z["tracks"]) <= hold]
    grenze = [
        z for z in zeilen
        if set(z["tracks"]) & hold and not set(z["tracks"]) <= hold
    ]
    grenz_paare = len({str(z.get("pair_id", "")) for z in grenze})
    return train, holdout, grenz_paare, len(grenze)


def holdout_nach_tracks(
    zeilen: list[dict], anteil: float = HOLDOUT_ANTEIL, seed: int = STANDARD_SEED
):
    """Kompatible Zweier-Rueckgabe des strikt track-disjunkten Holdouts."""
    train, holdout, _, _ = holdout_nach_tracks_mit_diagnose(zeilen, anteil, seed)
    return train, holdout


def paarvergleich_daten(zeilen: list[dict], merkmale) -> tuple[np.ndarray, list[str]]:
    """Differenzen Sieger - Verlierer je Paar mit genau einer Wahl (Bradley-
    Terry als paarweise Zerlegung: ein Vergleich je Verlierer, KEINE
    Spiegelung — die wuerde die Likelihood verdoppeln und L2 halbieren).
    Rueckgabe X_diff, Paar-Ids je Zeile (fuer den Cluster-Bootstrap)."""
    namen = list(merkmale)
    X, gruppen = [], []
    je_paar: dict[str, list[dict]] = {}
    for z in zeilen:
        je_paar.setdefault(z["pair_id"], []).append(z)
    for pid, clips in je_paar.items():
        sieger = [c for c in clips if c["gewaehlt"]]
        if (
            len(sieger) != 1 or len(clips) < 2
            or int(sieger[0].get("note") or 0) < 2
        ):
            continue
        s = np.array([sieger[0]["merkmale"][n] for n in namen], dtype=float)
        for c in clips:
            if c is sieger[0]:
                continue
            v = np.array([c["merkmale"][n] for n in namen], dtype=float)
            X.append(s - v)
            gruppen.append(pid)
    if not X:
        return np.zeros((0, len(namen))), []
    return np.vstack(X), gruppen


def identifizierbare_merkmale(X_diff: np.ndarray, namen, schwelle: float = PAAR_STREUUNG_MIN) -> list[str]:
    """Merkmale, die INNERHALB der Paare streuen (Std der Sieger-Verlierer-
    Differenzen >= schwelle). bpm/genre sind je Paar konstant -> nie dabei."""
    X_diff = np.asarray(X_diff, dtype=float)
    if X_diff.size == 0:
        return []
    std = X_diff.std(axis=0)
    return [n for n, s in zip(namen, std) if s >= schwelle]


def fit_paarvergleich(X_diff: np.ndarray, l2: float = L2_STAERKE) -> np.ndarray:
    """Bradley-Terry mit linearem Nutzen, ohne Achsenabschnitt:
    maximiert sum log sigmoid(beta . d) - l2 * |beta|^2 ueber alle
    Sieger-Verlierer-Differenzen d. Koeffizienten bewusst UNSTANDARDISIERT
    (Teilwert-Skala [0,1]): das Gewicht soll dem Nutzen je Teilwert-Einheit
    entsprechen, nicht je Standardabweichung."""
    X = np.asarray(X_diff, dtype=float)
    if X.size == 0:
        return np.zeros(X.shape[1] if X.ndim == 2 else 0)

    def ziel(beta):
        z = X @ beta
        return float(np.sum(np.logaddexp(0.0, -z))) + l2 * float(beta @ beta)

    def grad(beta):
        p = 1.0 / (1.0 + np.exp(-(X @ beta)))
        return -(X.T @ (1.0 - p)) + 2.0 * l2 * beta

    res = minimize(ziel, np.zeros(X.shape[1]), jac=grad, method="L-BFGS-B")
    return np.asarray(res.x, dtype=float)


def bootstrap_paarvergleich(X_diff, gruppen, l2=L2_STAERKE, ziehungen=BOOTSTRAP_ZIEHUNGEN,
                            seed=STANDARD_SEED) -> list[tuple[float, float]]:
    """95-%-Bootstrap je Koeffizient, Ziehung ueber PAARE (Cluster), nicht
    ueber Einzelzeilen: die K-1 Vergleiche eines Paars sind korreliert."""
    X_diff = np.asarray(X_diff, dtype=float)
    ids = sorted(set(gruppen))
    if not ids:
        return [(0.0, 0.0)] * (X_diff.shape[1] if X_diff.ndim == 2 else 0)
    index_je_id = {pid: [i for i, g in enumerate(gruppen) if g == pid] for pid in ids}
    rng = random.Random(seed)
    stapel = []
    for _ in range(int(ziehungen)):
        zug = [i for pid in rng.choices(ids, k=len(ids)) for i in index_je_id[pid]]
        stapel.append(fit_paarvergleich(X_diff[zug], l2))
    s = np.vstack(stapel)
    return [(float(np.percentile(s[:, j], 2.5)), float(np.percentile(s[:, j], 97.5))) for j in range(s.shape[1])]


def trefferquote_paarvergleich(beta: np.ndarray, zeilen: list[dict], merkmale) -> tuple[float | None, float | None]:
    """Anteil Paare, deren gewaehlter Clip den hoechsten Modell-Nutzen hat;
    zweiter Wert = Zufallsbasis (Mittel von 1/Clips je Paar)."""
    namen = list(merkmale)
    je_paar: dict[str, list[dict]] = {}
    for z in zeilen:
        je_paar.setdefault(z["pair_id"], []).append(z)
    treffer, basis, n = 0, 0.0, 0
    for clips in je_paar.values():
        sieger = [c for c in clips if c["gewaehlt"]]
        if (
            len(sieger) != 1 or len(clips) < 2
            or int(sieger[0].get("note") or 0) < 2
        ):
            continue
        nutzen = [float(np.array([c["merkmale"][m] for m in namen]) @ beta) for c in clips]
        if clips[int(np.argmax(nutzen))] is sieger[0]:
            treffer += 1
        basis += 1.0 / len(clips)
        n += 1
    if n == 0:
        return None, None
    return treffer / n, basis / n


def gewichte_aus_paarvergleich(namen, intervalle, identifizierbar, toleranz_gewichte: dict) -> dict[str, float]:
    """Gewichte fuer alle zehn Faktoren (Schluessel = Faktorname), Summe 1.0:
    nicht identifizierbare behalten ihr Toleranz-Gewicht (kandidaten_*_weight);
    das Restbudget wird auf identifizierbare Merkmale nach positiver unterer
    Bootstrap-Grenze verteilt; identifizierbare ohne gesicherten positiven
    Effekt bekommen 0. Kein identifizierbares positiv -> {} (keine Uebernahme)."""
    fest = {n: float(toleranz_gewichte.get(f"kandidaten_{n}_weight", 0.0))
            for n in KANDIDATEN_TEILWERTE if n not in identifizierbar}
    roh = {n: (lo if lo > 0.0 and hi > 0.0 else 0.0)
           for n, (lo, hi) in zip(namen, intervalle) if n in identifizierbar}
    summe = sum(roh.values())
    if summe <= 0.0:
        return {}
    rest = max(0.0, 1.0 - sum(fest.values()))
    ergebnis = dict(fest)
    ergebnis.update({n: rest * v / summe for n, v in roh.items()})
    for n in KANDIDATEN_TEILWERTE:
        ergebnis.setdefault(n, 0.0)
    return ergebnis


def schema_rangfolge(zeilen: list[dict], min_wahlen: int = MIN_EREIGNISSE_JE_MERKMAL) -> dict[str, list[str]]:
    """Je Genre: Schemata (alle Schemata des Kandidaten, Out- und In-Seite
    gemeinsam) nach Anteil 'gewaehlt' an 'angeboten' (Laplace +1/+2),
    absteigend; nur Genres mit mindestens min_wahlen Wahlen."""
    from hpg_core.mix_candidates import SCHEMA_PRIORITAET
    angebot: dict[str, dict[str, int]] = {}
    wahl: dict[str, dict[str, int]] = {}
    wahlen_je_genre: dict[str, int] = {}
    je_paar: dict[str, list[dict]] = {}
    for z in zeilen:
        je_paar.setdefault(z.get("pair_id", ""), []).append(z)
    vergleichszeilen = []
    for clips in je_paar.values():
        sieger = [c for c in clips if c.get("gewaehlt")]
        if len(clips) < 2 or len(sieger) != 1 or int(sieger[0].get("note") or 0) < 2:
            continue
        vergleichszeilen.extend(clips)

    for z in vergleichszeilen:
        g = z.get("genre") or ""
        schemata = list(z.get("schemata_out") or []) + list(z.get("schemata_in") or [])
        for s in schemata:
            if s not in SCHEMA_PRIORITAET:
                continue
            angebot.setdefault(g, {}).setdefault(s, 0)
            angebot[g][s] += 1
            if z.get("gewaehlt"):
                wahl.setdefault(g, {}).setdefault(s, 0)
                wahl[g][s] += 1
        if z.get("gewaehlt"):
            wahlen_je_genre[g] = wahlen_je_genre.get(g, 0) + 1
    ergebnis = {}
    for g, schemata in angebot.items():
        if wahlen_je_genre.get(g, 0) < min_wahlen:
            continue
        quote = {s: (wahl.get(g, {}).get(s, 0) + 1) / (n + 2) for s, n in schemata.items()}
        ergebnis[g] = sorted(quote, key=lambda s: (-quote[s], SCHEMA_PRIORITAET.index(s)))
    return ergebnis


def baue_candidate_preferences(
    gewichte_je_genre: dict[str, dict[str, float]],
    rangfolge: dict[str, list[str]],
    diagnose: dict,
) -> dict:
    """Partieller Entwurf: nur bestandene Genres, nie globale Vervielfaeltigung."""
    ergebnis: dict = {"_diagnose": {"fit_kandidaten": dict(diagnose)}}
    for genre, gewichte in gewichte_je_genre.items():
        if genre not in CANONICAL_GENRES:
            raise ValueError(f"Unbekanntes Genre im Fit-Ergebnis: {genre}")
        block = {
            f"kandidaten_{f}_weight": float(gewichte.get(f, 0.0))
            for f in KANDIDATEN_TEILWERTE
        }
        differenz = 1.0 - sum(block.values())
        groesster = max(block, key=block.get)
        block[groesster] += differenz
        if genre in rangfolge:
            block["schema_rang"] = list(rangfolge[genre])
        ergebnis[genre] = block
    return ergebnis


def uebernahme_erlaubt(*, belastbar_note: bool, n_paare_train: int, n_identifizierbar: int,
                       auc_holdout: float | None, treffer_holdout: float | None,
                       basis_holdout: float | None, gewichte: dict) -> tuple[bool, str]:
    """Entscheidung 10 (Plan Teil 3): alle Bedingungen muessen halten, sonst (False, Grund)."""
    if not belastbar_note:
        return False, "Datenlage Zielgroesse 1 nicht belastbar (10 je Merkmal und Klasse)"
    if n_identifizierbar == 0:
        return False, "kein Merkmal streut innerhalb der Paare (nicht identifizierbar)"
    if n_paare_train < MIN_EREIGNISSE_JE_MERKMAL * n_identifizierbar:
        return False, (f"zu wenige Paare mit Wahl im Train: {n_paare_train} < "
                       f"{MIN_EREIGNISSE_JE_MERKMAL * n_identifizierbar}")
    if auc_holdout is None or treffer_holdout is None or basis_holdout is None:
        return False, "Holdout leer oder ohne beide Klassen/ohne Paar mit Wahl"
    if not auc_holdout > 0.5:
        return False, f"Holdout-AUC {auc_holdout:.3f} nicht besser als Zufall"
    if not treffer_holdout > basis_holdout:
        return False, f"Holdout-Trefferquote {treffer_holdout:.3f} nicht ueber Zufallsbasis {basis_holdout:.3f}"
    if not any(v > 0.0 for v in gewichte.values()):
        return False, "kein identifizierbares Merkmal mit gesichert positivem Effekt"
    return True, "alle Bedingungen erfuellt"


def _genre_von_pfad(tracks) -> dict[str, str]:
    """Pfad (lower) -> Genre ueber loese_genre_auf, fuer verbinde_bewertungen_kandidaten."""
    return {str(t.filePath).lower(): loese_genre_auf(t) for t in tracks}


def _manifest_kandidatengewichte(scoring_snapshot: dict, genre: str) -> dict:
    """Liest die exakte Kandidaten-Gewichtsgruppe aus dem Prepare-Snapshot."""
    if not isinstance(scoring_snapshot, dict):
        raise ValueError("Manifest-scoring_snapshot ist kein Objekt")
    je_genre = scoring_snapshot.get("candidate_tolerances_by_genre")
    if not isinstance(je_genre, dict):
        raise ValueError("Manifest-scoring_snapshot enthaelt keine Genre-Toleranzen")
    eintrag = je_genre.get(genre)
    if not isinstance(eintrag, dict):
        raise ValueError(f"Manifest-scoring_snapshot enthaelt keine Toleranzen fuer {genre}")
    gewichtsschluessel = {
        key for key in eintrag
        if isinstance(key, str)
        and key.startswith("kandidaten_")
        and key.endswith("_weight")
    }
    erwartet = set(KANDIDATEN_GEWICHT_SCHLUESSEL)
    if gewichtsschluessel != erwartet:
        raise ValueError(
            f"Manifest-Kandidatengewichtsgruppe fuer {genre} ist nicht exakt vollstaendig"
        )
    werte: dict[str, float] = {}
    for key in KANDIDATEN_GEWICHT_SCHLUESSEL:
        wert = eintrag[key]
        if (
            isinstance(wert, bool)
            or not isinstance(wert, (int, float))
            or not math.isfinite(float(wert))
            or not 0.0 <= float(wert) <= 1.0
        ):
            raise ValueError(
                f"Manifest-Kandidatengewicht {key} fuer {genre} ist ungueltig"
            )
        werte[key] = float(wert)
    if not math.isclose(sum(werte.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(
            f"Manifest-Kandidatengewichte fuer {genre} summieren sich nicht auf 1"
        )
    return werte


def _fit_kandidaten_genre(
    genre: str, zeilen: list[dict], seed: int, toleranz_gewichte: dict
) -> tuple[dict[str, float] | None, list[str] | None, dict]:
    """Fuehrt den vollstaendigen Fit isoliert fuer genau ein Genre aus."""
    diagnose: dict = {"clips": len(zeilen), "uebernommen": False}
    train, holdout, grenz_paare, grenz_clips = holdout_nach_tracks_mit_diagnose(
        zeilen, HOLDOUT_ANTEIL, seed
    )
    behalten = train + holdout
    aktive = [
        name for name in KANDIDATEN_TEILWERTE
        if train and float(np.std([z["merkmale"][name] for z in train])) >= MIN_KONTROLL_STREUUNG
    ]
    diagnose["aktive_merkmale"] = aktive
    if not aktive:
        diagnose["grund"] = "kein Teilwert streut innerhalb dieses Genres"
        diagnose.update({
            "train_clips": len(train), "holdout_clips": len(holdout),
            "cross_boundary_pairs": grenz_paare,
            "cross_boundary_clips": grenz_clips,
        })
        return None, None, diagnose
    train_tracks = {track for z in train for track in z["tracks"]}
    holdout_tracks = {track for z in holdout for track in z["tracks"]}
    if train_tracks & holdout_tracks:
        raise RuntimeError(f"Interner Holdout-Fehler fuer {genre}: Track-Leak")

    train_n, hold_n = nur_mit_note(train), nur_mit_note(holdout)
    auc_holdout = None
    belastbar = False
    urteil = "Zielgroesse 1: keine benoteten Clips im Train."
    koeff_note: dict[str, float] = {}
    if len(train_n) >= 2:
        X1, y1 = zu_zielgroesse(train_n, aktive)
        n_gut, n_schlecht = int(y1.sum()), int(len(y1) - y1.sum())
        if n_gut and n_schlecht:
            belastbar, urteil = datenlage_urteil(n_gut, n_schlecht, len(aktive))
            beta1 = fit_logistic(X1, y1, L2_STAERKE)
            koeff_note = {name: float(beta1[1 + i]) for i, name in enumerate(aktive)}
            if hold_n:
                Xh, yh = zu_zielgroesse(hold_n, aktive)
                mittel, streuung = _kennzahlen(X1)
                score = _standardisiere_mit(Xh, mittel, streuung) @ beta1[1:] + beta1[0]
                auc_holdout = auc(yh, score)
        else:
            urteil = "Zielgroesse 1: alle Noten in einer Klasse — keine Schaetzung."

    X_diff, gruppen = paarvergleich_daten(train, aktive)
    identifizierbar = identifizierbare_merkmale(X_diff, aktive)
    n_paare_train = len(set(gruppen))
    beta2_voll = np.zeros(len(aktive))
    intervalle_id: list[tuple[float, float]] = []
    if identifizierbar and X_diff.size:
        spalten = [aktive.index(name) for name in identifizierbar]
        X_id = X_diff[:, spalten]
        beta_id = fit_paarvergleich(X_id, L2_STAERKE)
        intervalle_id = bootstrap_paarvergleich(
            X_id, gruppen, L2_STAERKE, BOOTSTRAP_ZIEHUNGEN, seed
        )
        for index, name in enumerate(identifizierbar):
            beta2_voll[aktive.index(name)] = beta_id[index]

    treffer_holdout, basis_holdout = trefferquote_paarvergleich(
        beta2_voll, holdout, aktive
    )
    gewichte = gewichte_aus_paarvergleich(
        identifizierbar, intervalle_id, identifizierbar, toleranz_gewichte
    )
    ok, grund = uebernahme_erlaubt(
        belastbar_note=belastbar,
        n_paare_train=n_paare_train,
        n_identifizierbar=len(identifizierbar),
        auc_holdout=auc_holdout,
        treffer_holdout=treffer_holdout,
        basis_holdout=basis_holdout,
        gewichte=gewichte,
    )
    rangfolge = schema_rangfolge(behalten).get(genre)
    diagnose.update({
        "train_clips": len(train), "holdout_clips": len(holdout),
        "cross_boundary_pairs": grenz_paare,
        "cross_boundary_clips": grenz_clips,
        "train_tracks": len(train_tracks), "holdout_tracks": len(holdout_tracks),
        "holdout_anteil_tracks": HOLDOUT_ANTEIL,
        "paare_mit_wahl_train": n_paare_train,
        "identifizierbar": identifizierbar,
        "nicht_identifizierbar": [n for n in aktive if n not in identifizierbar],
        "koeffizienten_note": {k: round(v, 4) for k, v in koeff_note.items()},
        "koeffizienten_paarvergleich": {
            n: round(float(beta2_voll[aktive.index(n)]), 4) for n in identifizierbar
        },
        "intervalle_paarvergleich": {
            n: [round(lo, 4), round(hi, 4)]
            for n, (lo, hi) in zip(identifizierbar, intervalle_id)
        },
        "auc_holdout": None if auc_holdout is None else round(auc_holdout, 4),
        "trefferquote_holdout": None if treffer_holdout is None else round(treffer_holdout, 4),
        "zufallsbasis_holdout": None if basis_holdout is None else round(basis_holdout, 4),
        "belastbar_note": belastbar, "urteil_note": urteil,
        "schema_rang_belastbar": rangfolge is not None,
        "uebernommen": ok, "grund": grund,
    })
    return (gewichte if ok else None), (rangfolge if ok else None), diagnose


def befehl_fit_kandidaten(args: argparse.Namespace) -> int:
    ordner = Path(args.dir)
    try:
        cache_arg = getattr(args, "cache", None)
        audit_arg = getattr(args, "audit_report", None)
        if not cache_arg:
            raise ValueError("fit --modus kandidaten verlangt explizites --cache")
        start_binding = _fit_binding_token(ordner, audit_arg)
        manifest = _validiere_fit_bindung(ordner, cache_arg, audit_arg)
        scoring_snapshot = manifest.get("scoring_snapshot")
        manifest_gewichte = {
            genre: _manifest_kandidatengewichte(scoring_snapshot, genre)
            for genre in CANONICAL_GENRES
        }
        _bestaetige_fit_binding(start_binding, ordner, audit_arg)
        merkmale_roh = _lies_fit_csv_gebunden(
            ordner / "merkmale.csv", start_binding, "merkmale_sha256"
        )
        bewertung_roh = _lies_fit_csv_gebunden(
            ordner / "bewertung.csv", start_binding, "bewertung_sha256"
        )
        _bestaetige_fit_binding(start_binding, ordner, audit_arg)
        validiere_kandidaten_csvs(merkmale_roh, bewertung_roh)
        validiere_vollstaendige_kandidatenbewertung(bewertung_roh)
    except ValueError as exc:
        print(f"Kandidatensatz ungueltig: {exc}")
        return 1
    genres_je_pfad = _genre_von_pfad(
        lade_tracks_aus_cache(getattr(args, "cache", None))
    )
    zeilen, ohne, verworfen = verbinde_bewertungen_kandidaten(
        merkmale_roh, bewertung_roh,
        genre_von=lambda pfad: genres_je_pfad.get(str(pfad).lower(), ""),
    )
    reine_zeilen, ausschluss = filtere_reine_kandidatenpaare(zeilen)
    print(
        f"Clips mit Merkmalen: {len(zeilen)}   genre-rein: {len(reine_zeilen)}   "
        f"ohne Note: {ohne}   verworfen: {verworfen}"
    )

    diagnose: dict = {
        "quelle": "tools/rate_transitions.py fit --modus kandidaten",
        "clips": len(zeilen), "genre_reine_clips": len(reine_zeilen),
        "ohne_note": ohne, "verworfen": verworfen, "ausgeschlossen": ausschluss,
        "l2_staerke": L2_STAERKE, "bootstrap_ziehungen": BOOTSTRAP_ZIEHUNGEN,
        "seed": args.seed, "genres": {},
    }
    gewichte_je_genre: dict[str, dict[str, float]] = {}
    rangfolge: dict[str, list[str]] = {}
    for genre in CANONICAL_GENRES:
        genre_zeilen = [z for z in reine_zeilen if z["genre"] == genre]
        if not genre_zeilen:
            continue
        gewichte, schema, genre_diagnose = _fit_kandidaten_genre(
            genre,
            genre_zeilen,
            args.seed,
            manifest_gewichte[genre],
        )
        diagnose["genres"][genre] = genre_diagnose
        if gewichte is not None:
            gewichte_je_genre[genre] = gewichte
            if schema is not None:
                rangfolge[genre] = schema
        print(
            f"{genre}: {'UEBERNAHME BEREIT' if gewichte is not None else 'nicht uebernommen'} — "
            f"{genre_diagnose['grund']}"
        )

    _bestaetige_fit_binding(start_binding, ordner, audit_arg)
    merkmale_vor_write = _lies_fit_csv_gebunden(
        ordner / "merkmale.csv", start_binding, "merkmale_sha256"
    )
    bewertung_vor_write = _lies_fit_csv_gebunden(
        ordner / "bewertung.csv", start_binding, "bewertung_sha256"
    )
    validiere_kandidaten_csvs(merkmale_vor_write, bewertung_vor_write)
    validiere_vollstaendige_kandidatenbewertung(bewertung_vor_write)
    _validiere_fit_bindung(
        ordner,
        cache_arg,
        audit_arg,
    )
    _bestaetige_fit_binding(start_binding, ordner, audit_arg)
    ergebnis = baue_candidate_preferences(gewichte_je_genre, rangfolge, diagnose)
    entwurf = ordner / "candidate_preferences_entwurf.json"
    if not gewichte_je_genre:
        _bestaetige_fit_binding(start_binding, ordner, audit_arg)
        _schreibe_json_atomar(entwurf, ergebnis)
        print(f"Kein Genre bestand das Gate; Nutzer-Override unveraendert. Entwurf: {entwurf}")
        return 0

    from hpg_core import candidate_preferences as cp
    updates = {genre: dict(ergebnis[genre]) for genre in gewichte_je_genre}
    _bestaetige_fit_binding(start_binding, ordner, audit_arg)
    try:
        ziel = cp.merge_user_preferences_atomically(updates, diagnose=diagnose)
    except Exception as exc:  # noqa: BLE001 - Persistenz garantiert selbst den Rollback
        for genre in gewichte_je_genre:
            diagnose["genres"][genre]["uebernommen"] = False
            diagnose["genres"][genre]["persistenzfehler"] = str(exc)
        ergebnis = baue_candidate_preferences(gewichte_je_genre, rangfolge, diagnose)
        _bestaetige_fit_binding(start_binding, ordner, audit_arg)
        _schreibe_json_atomar(entwurf, ergebnis)
        print(f"Uebernahme fehlgeschlagen; Override zurueckgerollt. Entwurf: {entwurf}")
        return 1

    print(
        f"Partiell uebernommen nach {ziel}: "
        + ", ".join(gewichte_je_genre)
    )
    return 0


def _fit(args: argparse.Namespace) -> int:
    """Weiche nach --modus (set_defaults kann nur eine Funktion tragen)."""
    if getattr(args, "modus", "einzel") == "kandidaten":
        return befehl_fit_kandidaten(args)
    return befehl_fit(args)


def _prepare(args: argparse.Namespace) -> int:
    """Weiche nach --modus (set_defaults kann nur eine Funktion tragen)."""
    if getattr(args, "modus", "einzel") == "kandidaten":
        return befehl_prepare_kandidaten(args)
    return befehl_prepare(args)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    unter = parser.add_subparsers(dest="befehl", required=True)

    p = unter.add_parser("prepare", help="Clips rendern und Bewertungsbogen anlegen")
    p.add_argument(
        "--anzahl",
        type=_ganzzahl_im_bereich("anzahl", 1, MAX_ANZAHL),
        default=STANDARD_ANZAHL,
    )
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--bpm-toleranz", dest="bpm_toleranz", type=_bpm_toleranz_arg,
                   default=STANDARD_BPM_TOLERANZ)
    p.add_argument(
        "--energy-direction",
        dest="energy_direction",
        type=_energy_direction_arg,
        default=None,
        metavar="{auto,up,down,maintain}",
        help="Energieverlauf fuer Gate, Ranking und Audit (Standard: auto)",
    )
    p.add_argument(
        "--harmonic-strictness",
        dest="harmonic_strictness",
        type=_ganzzahl_im_bereich("harmonic-strictness", 1, 10),
        default=7,
        help="Harmonie-Strenge fuer Ranking und Audit (1-10; Standard: 7)",
    )
    p.add_argument(
        "--allow-experimental",
        dest="allow_experimental",
        type=_striktes_bool_arg,
        default=True,
        metavar="{true,false}",
        help="Experimentelle Harmonie-Beziehungen strikt aktivieren/deaktivieren",
    )
    p.add_argument("--cache", default=None, help="Abweichende Cache-Datenbank")
    p.add_argument("--seed", type=int, default=STANDARD_SEED)
    # Bewusst NICHT --genre: bei `fit` steuert --genre die Ausgabe der
    # Genre-Gewichte, hier die Auswahl der Paare. Gleicher Name, andere
    # Wirkung waere eine Falle.
    p.add_argument("--nur-genre", dest="nur_genre", default=None,
                   choices=list(CANONICAL_GENRES),
                   help="Nur Paare, bei denen beide Tracks dieses Genre tragen")
    p.add_argument("--modus", choices=("einzel", "kandidaten"), default="einzel",
                   help="einzel = ein Clip je Paar; kandidaten = die bestbewerteten "
                        "PairCandidates bis zur Versionsgrenze")
    p.add_argument(
        "--max-versionen-pro-paar",
        type=_ganzzahl_im_bereich("max-versionen-pro-paar", 1, 5),
        default=STANDARD_MAX_VERSIONEN_PRO_PAAR,
        help="Kandidatenmodus: hoechstens so viele gerankte Clips je Paar (Standard: 5)",
    )
    p.add_argument(
        "--transition-type-modus",
        dest="transition_type_mode",
        choices=("kontrolliert", "produktion"),
        default="kontrolliert",
        help=(
            "Kandidatenmodus: kontrolliert nutzt fuer alle Clips pro_eq_swap; "
            "produktion nutzt dieselbe Typentscheidung wie die App"
        ),
    )
    p.set_defaults(funktion=_prepare)

    f = unter.add_parser("fit", help="Gewichte aus den Bewertungen schaetzen")
    f.add_argument("--dir", required=True, type=Path)
    f.add_argument("--seed", type=int, default=STANDARD_SEED)
    f.add_argument("--genre", action="append", choices=list(CANONICAL_GENRES),
                   help="Genre(s) fuer die Ausgabe; Standard: alle kanonischen")
    f.add_argument("--modus", choices=("einzel", "kandidaten"), default="einzel",
                   help="einzel = Einzelnoten-Satz (heute); kandidaten = Note + Paarvergleich je Paar "
                        "(--genre wird dort ignoriert: die Rangfolge entsteht je Genre aus den Daten)")
    f.add_argument("--cache", default=None,
                   help="Abweichende Cache-Datenbank (nur --modus kandidaten: Genre je Track)")
    f.add_argument(
        "--audit-report",
        dest="audit_report",
        type=Path,
        default=None,
        help="Pflicht in --modus kandidaten: erfolgreicher audit_candidate_set-Report",
    )
    f.set_defaults(funktion=_fit)

    args = parser.parse_args(argv)
    try:
        return int(args.funktion(args))
    except (FileNotFoundError, PermissionError, sqlite3.Error, csv.Error, ValueError) as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError) as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

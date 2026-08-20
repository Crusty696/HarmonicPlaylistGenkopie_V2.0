"""Paarweise Uebergangs-Vergleiche fuer das Playlist-Scoring.

Jede Funktion liefert einen Wert in [0, 1] oder None. None heisst
ausdruecklich "nicht bestimmbar" — das Scoring verteilt das Gewicht dann um,
statt den Uebergang zu bestrafen.
"""
from __future__ import annotations

import math

from .models import Track
from .tolerances import get_tolerances

# Anteil des Bassmusters am Groove-Vergleich. Der Bass traegt die Entscheidung
# "offbeat oder gerade" und wiegt deshalb schwerer als das Gesamt-Onset.
BASS_PATTERN_SHARE = 0.6

# Sprungbreiten, ab denen der jeweilige Faktor auf 0 faellt, falls das Genre
# keine gelernten Werte hat. Gemessen an 18 Tracks der Sammlung (60-s-
# Ausschnitte), Abstaende zwischen zufaelligen Trackpaaren:
#   bass_punch  Median 0,436  p90 0,923  max 1,393  -> 1,4 deckt den Bereich
#     (2026-08-19, unveraendert: bass_punch ist weiterhin ein Crest-Faktor
#      aus der Magnitude)
#   sub_energy  Median 0,140  p90 0,306  max 0,502  -> 0,50 deckt den Bereich
#     (NEU gemessen 2026-08-19, nachdem sub_energy von der Magnitude auf die
#      LEISTUNG umgestellt wurde. Die alten Zahlen — Median 0,063 / p90 0,135
#      / max 0,242 mit Toleranz 0,25 — galten fuer das Magnituden-Verhaeltnis
#      und sind seither ungueltig. Das Quadrieren spreizt den Wertebereich:
#      Einzelwerte jetzt 0,288 bis 0,790, Median 0,506.)
# Ein zu grosser Wert macht den Faktor konstant und damit wirkungslos.
DEFAULT_SUB_DELTA_MAX = 0.50
DEFAULT_PUNCH_DELTA_MAX = 1.4
# Gemessener Boden der Groove-Aehnlichkeit (siehe _spreize). Wird von der
# Genre-Tabelle ueberschrieben, sobald aus Mixen gelernte Werte vorliegen.
DEFAULT_GROOVE_SIM_FLOOR = 0.65
DEFAULT_BRIGHTNESS_DELTA_MAX = 60.0
DEFAULT_FLATNESS_DELTA_MAX = 0.15

# Abzug, wenn der Tongeschlecht-Wechsel die Stimmung kippt.
MODE_SWITCH_PENALTY = 0.15


def cosine_similarity(a, b) -> float | None:
    """Kosinus-Aehnlichkeit zweier Vektoren, auf [0, 1] geklemmt."""
    if not a or not b or len(a) != len(b):
        return None
    punkt = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0.0 or nb <= 0.0:
        return None
    return max(0.0, min(1.0, punkt / (na * nb)))


def _spreize(wert: float, boden: float) -> float:
    """Dehnt [boden, 1.0] auf [0.0, 1.0].

    Zwei zufaellige Tracks erreichen nie eine Groove-Aehnlichkeit von 0: alle
    4/4-Muster teilen sich das Grundraster. Gemessen an 276 Paaren aus 24
    Tracks der Sammlung (2026-08-19, Rekordbox-Tempo und ANLZ-Downbeat):
    min 0,654, p10 0,819, Median 0,922, p90 0,976, max 0,996.
    Ohne Spreizung laege der Faktor immer zwischen 0,65 und 1,0 und wuerde
    zwei Drittel seines Wertebereichs verschenken.
    """
    if boden >= 1.0:
        return wert
    return max(0.0, min(1.0, (wert - boden) / (1.0 - boden)))


def _normiert(delta: float, maximum: float) -> float:
    """Wandelt einen Absolutabstand in eine Aehnlichkeit in [0, 1]."""
    if maximum <= 0.0:
        return 1.0
    return max(0.0, 1.0 - abs(delta) / maximum)


def groove_match(track_a: Track, track_b: Track, genre: str) -> float | None:
    """Rhythmische Passung aus Gesamt- und Bassmuster."""
    onset_sim = cosine_similarity(track_a.groove_pattern, track_b.groove_pattern)
    bass_sim = cosine_similarity(track_a.bass_pattern, track_b.bass_pattern)

    if onset_sim is None and bass_sim is None:
        return None
    if bass_sim is None:
        roh = onset_sim
    elif onset_sim is None:
        roh = bass_sim
    else:
        roh = BASS_PATTERN_SHARE * bass_sim + (1.0 - BASS_PATTERN_SHARE) * onset_sim

    return _spreize(roh, get_tolerances(genre).get(
        "groove_sim_floor", DEFAULT_GROOVE_SIM_FLOOR
    ))


def _naht_werte(track: Track, rolle: str) -> tuple[float, float]:
    """Bassdruck an der Nahtstelle; Trackmittel als Rueckfallebene.

    rolle "out" = die Sektion, aus der Track A herauslaeuft (letzte
    Sektion mit Beat), rolle "in" = die Sektion, in die Track B
    hineingemischt wird (erste Sektion nach dem Intro).

    Ob zwei Tracks im Mittel aehnlich basslastig sind, ist fuer den Uebergang
    irrelevant — es zaehlt, was an der Nahtstelle passiert (Spec 5.3).

    Intros werden uebersprungen: in ein Intro mischt man HINEIN, gemessen
    wird aber, was danach kommt. Dort — auf der ersten Sektion mit vollem
    Bass — entscheidet sich, ob die Baesse mit dem auslaufenden Track
    kollidieren. Ein duennes Intro gegen ein volles Outro zu messen wuerde
    jeden Uebergang kuenstlich schlecht bewerten.

    Fehlen Sektionen oder die Schluessel (zu kurze Sektionen bekommen sie
    gar nicht erst, siehe groove.BASS_KENNWERTE_MIN_SEC), gilt das
    Trackmittel.
    """
    mittel = (track.sub_energy, track.bass_punch)
    sections = getattr(track, "sections", None) or []

    kandidaten = [
        sec for sec in sections
        if isinstance(sec, dict) and sec.get("label") != "intro"
    ]
    if not kandidaten:
        return mittel

    sec = kandidaten[-1] if rolle == "out" else kandidaten[0]
    sub = sec.get("sub_energy")
    punch = sec.get("bass_punch")
    if sub is None or punch is None:
        return mittel
    return float(sub), float(punch)


def bass_continuity(track_a: Track, track_b: Track, genre: str) -> float | None:
    """Kontinuitaet des Bassdrucks an der Nahtstelle."""
    # ODER, nicht UND: liefert EIN Track keinen Wert, ist der Vergleich nicht
    # bestimmbar. Mit UND schluepfte der haeufige Fall durch — ein Track mit
    # Werten gegen einen ohne ergab 0.0, also die haerteste Strafe fuer genau
    # die Tracks, die die Umverteilung schuetzen soll. compute_groove_fields
    # liefert bei downbeat_confidence < DOWNBEAT_RELIABLE_MIN ein leeres
    # GrooveFeatures(), und dessen sub_energy ist 0.0.
    # Ein echter Track hat immer sub_energy > 0 (gemessen 0,288 bis 0,790);
    # eine 0 bedeutet hier zuverlaessig "nicht gemessen".
    if track_a.sub_energy <= 0.0 or track_b.sub_energy <= 0.0:
        return None

    tol = get_tolerances(genre)
    sub_max = tol.get("bass_delta_max", DEFAULT_SUB_DELTA_MAX)

    # Verglichen wird Outro von A gegen Intro-Nachfolger von B, nicht
    # Trackmittel gegen Trackmittel (Spec 5.3).
    sub_a, punch_a = _naht_werte(track_a, "out")
    sub_b, punch_b = _naht_werte(track_b, "in")

    sub_sim = _normiert(sub_a - sub_b, sub_max)
    punch_sim = _normiert(punch_a - punch_b, DEFAULT_PUNCH_DELTA_MAX)
    return 0.6 * sub_sim + 0.4 * punch_sim


def timbre_match(track_a: Track, track_b: Track, genre: str) -> float | None:
    """Klangfarbliche Passung aus dem MFCC-Fingerabdruck."""
    return cosine_similarity(track_a.timbre_fingerprint, track_b.timbre_fingerprint)


def mood_match(track_a: Track, track_b: Track, genre: str) -> float | None:
    """Stimmungs-Passung aus Helligkeit, Flachheit und Tongeschlecht."""
    # ODER statt UND, gleiche Begruendung wie bei bass_continuity.
    # analysis.py setzt brightness bei gescheiterter Feature-Phase explizit
    # auf 0; ein normal analysierter Track liegt darueber.
    if track_a.brightness <= 0 or track_b.brightness <= 0:
        return None

    tol = get_tolerances(genre)
    hell_max = tol.get("brightness_delta_max", DEFAULT_BRIGHTNESS_DELTA_MAX)

    hell_sim = _normiert(
        float(track_a.brightness - track_b.brightness), hell_max
    )
    flach_sim = _normiert(
        track_a.spectral_flatness - track_b.spectral_flatness,
        DEFAULT_FLATNESS_DELTA_MAX,
    )
    score = 0.7 * hell_sim + 0.3 * flach_sim

    if track_a.keyMode and track_b.keyMode and track_a.keyMode != track_b.keyMode:
        score = max(0.0, score - MODE_SWITCH_PENALTY)
    return score

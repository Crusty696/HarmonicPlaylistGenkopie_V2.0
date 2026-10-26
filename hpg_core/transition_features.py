"""Paarweise Uebergangs-Vergleiche fuer das Playlist-Scoring.

Jede Funktion liefert einen Wert in [0, 1] oder None. None heisst
ausdruecklich "nicht bestimmbar" — das Scoring verteilt das Gewicht dann um,
statt den Uebergang zu bestrafen.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

from .dj_brain import section_dict_at_time
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
    if a is None or b is None or isinstance(a, (str, bytes, dict)) or isinstance(b, (str, bytes, dict)):
        return None
    try:
        if len(a) == 0 or len(b) == 0 or len(a) != len(b):
            return None
    except TypeError:
        return None
    try:
        links = tuple(float(x) for x in a)
        rechts = tuple(float(y) for y in b)
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(x) for x in (*links, *rechts)):
        return None
    punkt = sum(x * y for x, y in zip(links, rechts))
    na = math.sqrt(sum(x * x for x in links))
    nb = math.sqrt(sum(y * y for y in rechts))
    if (
        not math.isfinite(punkt)
        or not math.isfinite(na)
        or not math.isfinite(nb)
        or na <= 0.0
        or nb <= 0.0
    ):
        return None
    similarity = punkt / (na * nb)
    if not math.isfinite(similarity):
        return None
    return max(0.0, min(1.0, similarity))


def _spreize(wert: float, boden: float) -> float | None:
    """Dehnt [boden, 1.0] auf [0.0, 1.0].

    Zwei zufaellige Tracks erreichen nie eine Groove-Aehnlichkeit von 0: alle
    4/4-Muster teilen sich das Grundraster. Gemessen an 276 Paaren aus 24
    Tracks der Sammlung (2026-08-19, Rekordbox-Tempo und ANLZ-Downbeat):
    min 0,654, p10 0,819, Median 0,922, p90 0,976, max 0,996.
    Ohne Spreizung laege der Faktor immer zwischen 0,65 und 1,0 und wuerde
    zwei Drittel seines Wertebereichs verschenken.
    """
    if not _finite_number(wert) or not _finite_number(boden):
        return None
    wert, boden = float(wert), float(boden)
    if boden < 0.0:
        return None
    if boden >= 1.0:
        return wert
    return max(0.0, min(1.0, (wert - boden) / (1.0 - boden)))


def _normiert(delta: float, maximum: float) -> float | None:
    """Wandelt einen Absolutabstand in eine Aehnlichkeit in [0, 1]."""
    if not _finite_number(delta) or not _finite_number(maximum):
        return None
    delta, maximum = float(delta), float(maximum)
    if maximum <= 0.0:
        return None
    return max(0.0, 1.0 - abs(delta) / maximum)


def _finite_number(value) -> bool:
    """Nur endliche numerische Werte zulassen; Strings sind keine Messwerte."""
    if isinstance(value, (bool, str, bytes, bytearray)):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _tolerance_profile(genre: str, tolerances: Mapping | None) -> Mapping:
    """Nutzt einen Lauf-Snapshot oder den Legacy-Live-Fallback."""
    if tolerances is None:
        return get_tolerances(genre)
    if not isinstance(tolerances, Mapping):
        raise TypeError("tolerances muss ein Mapping oder None sein")
    return tolerances


def groove_match(
    track_a: Track,
    track_b: Track,
    genre: str,
    tolerances: Mapping | None = None,
) -> float | None:
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

    floor = _tolerance_profile(genre, tolerances).get(
        "groove_sim_floor", DEFAULT_GROOVE_SIM_FLOOR
    )
    return _spreize(roh, floor)


def _naht_werte(track: Track, rolle: str) -> tuple[float | None, float | None] | None:
    """Bassdruck an der Nahtstelle; Trackmittel als Rueckfallebene.

    Die Naht ist der MIXPUNKT — `mix_out_point` fuer den auslaufenden,
    `mix_in_point` fuer den eingehenden Track. Nicht das Label einer
    Sektion und nicht ihre Position in der Liste.

    Ob zwei Tracks im Mittel aehnlich basslastig sind, ist fuer den Uebergang
    irrelevant; es zaehlt, was an der Nahtstelle passiert (Spec 5.3).

    WARUM ueber den Mixpunkt und nicht ueber Labels: zwei naheliegende
    Abkuerzungen wurden an 200 analysierten Tracks gemessen und beide sind
    falsch. "Letzte Nicht-Intro-Sektion" trifft in 169 von 200 Faellen das
    OUTRO, nicht die Naht. "Letzte Main- oder Drop-Sektion" trifft sie in
    24 von 200 — in 170 Faellen beginnt diese Sektion erst NACH dem
    Mix-Out, im Median 47 s spaeter, also an einer Stelle, die der Track
    zur Mixzeit noch gar nicht erreicht hat. Der Mix-Out liegt im Median
    76 s vor dem Outro; aus der Invariante "Mix-Out vor dem Outro" folgt
    also gerade NICHT, in welcher Sektion er sitzt.

    Sentinel: `MIX_POINT_UNSET` ist -1.0, `0.0` ist ein gueltiger Mixpunkt —
    deshalb `>= 0.0` und nicht `> 0`.

    Fehlt der Mixpunkt, die Sektion oder ihre Bass-Schluessel (zu kurze
    Sektionen bekommen sie gar nicht erst, siehe
    groove.BASS_KENNWERTE_MIN_SEC), gilt das Trackmittel.
    """
    mittel = (
        float(track.sub_energy) if _finite_number(track.sub_energy)
        and float(track.sub_energy) > 0.0 else None,
        float(track.bass_punch) if _finite_number(track.bass_punch)
        and float(track.bass_punch) > 0.0 else None,
    )

    # 0.0 ist in GrooveFeatures der Sentinel fuer "nicht gemessen". Sektionen
    # duerfen diese fehlende Trackmessung nicht nachtraeglich ueberstimmen.
    if mittel == (None, None):
        return None

    zeitpunkt = track.mix_out_point if rolle == "out" else track.mix_in_point
    if not _finite_number(zeitpunkt) or float(zeitpunkt) < 0.0:
        return mittel

    sektion = section_dict_at_time(track, float(zeitpunkt))
    if sektion is None:
        return mittel

    sub = sektion.get("sub_energy")
    punch = sektion.get("bass_punch")
    werte = (
        float(sub) if _finite_number(sub) and float(sub) > 0.0 else mittel[0],
        float(punch) if _finite_number(punch) else mittel[1],
    )
    return None if werte == (None, None) else werte


def bass_continuity(
    track_a: Track,
    track_b: Track,
    genre: str,
    tolerances: Mapping | None = None,
) -> float | None:
    """Kontinuitaet des Bassdrucks an der Nahtstelle."""
    tol = _tolerance_profile(genre, tolerances)
    sub_max = tol.get("bass_delta_max", DEFAULT_SUB_DELTA_MAX)
    sub_max_valid = _finite_number(sub_max) and float(sub_max) > 0.0
    if sub_max_valid:
        sub_max = float(sub_max)

    # Verglichen wird die Sektion AM MIX-OUT von A gegen die Sektion AM
    # MIX-IN von B — nicht Trackmittel gegen Trackmittel und nicht
    # "Outro gegen Intro" (Spec 5.3, Herleitung in _naht_werte).
    seam_a = _naht_werte(track_a, "out")
    seam_b = _naht_werte(track_b, "in")
    if seam_a is None or seam_b is None:
        return None
    sub_a, punch_a = seam_a
    sub_b, punch_b = seam_b
    sub_sim = (_normiert(sub_a - sub_b, sub_max)
               if sub_a is not None and sub_b is not None and sub_max_valid else None)
    punch_sim = (_normiert(punch_a - punch_b, DEFAULT_PUNCH_DELTA_MAX)
                 if punch_a is not None and punch_b is not None else None)
    if sub_sim is None and punch_sim is None:
        return None
    if sub_sim is None:
        return punch_sim
    if punch_sim is None:
        return sub_sim
    return 0.6 * sub_sim + 0.4 * punch_sim


def timbre_match(track_a: Track, track_b: Track, genre: str) -> float | None:
    """Klangfarbliche Passung aus dem MFCC-Fingerabdruck."""
    return cosine_similarity(track_a.timbre_fingerprint, track_b.timbre_fingerprint)


def mood_match(
    track_a: Track,
    track_b: Track,
    genre: str,
    tolerances: Mapping | None = None,
) -> float | None:
    """Stimmungs-Passung aus Helligkeit, Flachheit und Tongeschlecht."""
    # ODER statt UND, gleiche Begruendung wie bei bass_continuity.
    # analysis.py setzt brightness bei gescheiterter Feature-Phase explizit
    # auf 0; ein normal analysierter Track liegt darueber.
    tol = _tolerance_profile(genre, tolerances)
    werte = []
    if (_finite_number(track_a.brightness) and _finite_number(track_b.brightness)
            and float(track_a.brightness) > 0.0 and float(track_b.brightness) > 0.0):
        hell_max = tol.get("brightness_delta_max", DEFAULT_BRIGHTNESS_DELTA_MAX)
        if _finite_number(hell_max) and float(hell_max) > 0.0:
            hell_sim = _normiert(float(track_a.brightness)-float(track_b.brightness),
                                 float(hell_max))
            if hell_sim is not None:
                werte.append((0.7, hell_sim))
    # Die erweiterte Analyse setzt spectral_flatness bei einem Fehler auf 0.0.
    # Wie brightness ist dieser Sentinel nicht als Messwert zu werten; sonst
    # würden zwei fehlgeschlagene Messungen eine perfekte Ähnlichkeit ergeben.
    if (_finite_number(track_a.spectral_flatness)
            and _finite_number(track_b.spectral_flatness)
            and float(track_a.spectral_flatness) > 0.0
            and float(track_b.spectral_flatness) > 0.0):
        flach_sim = _normiert(
            float(track_a.spectral_flatness)-float(track_b.spectral_flatness),
            DEFAULT_FLATNESS_DELTA_MAX,
        )
        if flach_sim is not None:
            werte.append((0.3, flach_sim))
    if not werte:
        return None
    gewicht = sum(weight for weight, _ in werte)
    score = sum(weight * similarity for weight, similarity in werte) / gewicht

    if track_a.keyMode and track_b.keyMode and track_a.keyMode != track_b.keyMode:
        score = max(0.0, score - MODE_SWITCH_PENALTY)
    return score

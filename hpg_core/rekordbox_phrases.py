"""Rekordbox-Phrasen (PSSI-Tag aus ANLZ0000.EXT) lesen.

Reine Funktionen ueber pyrekordbox-AnlzFile-Objekte (oder Objekte mit
derselben Oberflaeche `get_tag(key).content`). Zeiten kommen aus dem
Beatgrid (PQTZ, ANLZ0000.DAT): `entry.beat` ist ein 1-basierter Index in
die PQTZ-Beatliste (verifiziert 2026-08-21 an 699 von 2475 EXT-Dateien;
0-basiert passt nie; der erste Eintrag liegt im Vollbestand (2470 DAT) in
677 Faellen auf beatnum 2, 74x auf 3, 70x auf 4 (Beatgrid beginnt nicht auf
der 1); Stichprobe 699/2475 EXT fuer die 1-Basiertheit).
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

# Mood 1 ("high"): Kinds in eigenen Daten {1,2,3,5,6}; Kind 1 ist in
# 2370/2370 Tracks der erste, Kind 6 in 2370/2370 der letzte Eintrag
# (Messung 2026-08-21 ueber alle 2475 EXT-Dateien).
PHRASE_LABELS_HIGH: dict[int, str] = {1: "Intro", 2: "Up", 3: "Down", 5: "Chorus", 6: "Outro"}
# Mood 2 ("mid") und 3 ("low"): 102 eigene Tracks — Kind 1 in 100/102 der
# erste, Kind 10 in 100/102 der letzte Eintrag (Intro/Outro belegt).
# Verse/Bridge/Chorus dazwischen folgen dem Beat-Link-Schema und sind aus
# eigenen Daten NICHT pruefbar.
PHRASE_LABELS_MIDLOW: dict[int, str] = {
    1: "Intro", 2: "Verse 1", 3: "Verse 2", 4: "Verse 3", 5: "Verse 4",
    6: "Verse 5", 7: "Verse 6", 8: "Bridge", 9: "Chorus", 10: "Outro",
}
MOOD_NAMES: dict[int, str] = {1: "high", 2: "mid", 3: "low"}


def phrase_label(mood: int, kind: int) -> str:
    table = PHRASE_LABELS_HIGH if mood == 1 else PHRASE_LABELS_MIDLOW
    return table.get(int(kind), f"Unbekannt({int(kind)})")


def _tag_content(anlz, key: str):
    if anlz is None:
        return None
    try:
        return anlz.get_tag(key)
    except Exception:
        return None


def _beat_time(times, beat: int) -> float | None:
    """Zeit des 1-basierten Beat-Index, an den Rand geklemmt."""
    if isinstance(beat, bool):
        return None
    try:
        n = len(times)
        beat_number = int(beat)
    except (TypeError, ValueError, OverflowError):
        return None
    if n == 0:
        return None
    idx = min(max(beat_number - 1, 0), n - 1)
    try:
        value = float(times[idx])
    except (TypeError, ValueError, OverflowError, IndexError):
        return None
    if not math.isfinite(value) or value < 0.0:
        return None
    return value


def _phrase_start_time(times, beat: int) -> float | None:
    """Liest einen PSSI-Start nur bei gueltigem, nicht geklemmtem Beatindex."""
    if isinstance(beat, bool):
        return None
    try:
        beat_number = int(beat)
    except (TypeError, ValueError, OverflowError):
        return None
    if not 1 <= beat_number <= len(times):
        return None
    return _beat_time(times, beat_number)


def phrases_from_anlz(ext_anlz, dat_anlz, duration: float) -> list[dict]:
    """PSSI (aus EXT) + PQTZ (aus DAT) → Phrasenliste mit Sekunden.

    Rueckgabe: [{start_s, end_s, label, mood, kind, fill}], zeitlich
    sortiert, Ende = Start der naechsten Phrase, letzte endet am
    `end_beat` (geklemmt auf `duration`). Leer, wenn ein Tag fehlt.
    """
    if isinstance(duration, bool):
        return []
    try:
        duration_value = float(duration)
    except (TypeError, ValueError, OverflowError):
        return []
    if not math.isfinite(duration_value) or duration_value <= 0.0:
        return []

    pssi = _tag_content(ext_anlz, "PSSI")
    pqtz = _tag_content(dat_anlz, "PQTZ")
    if pssi is None or pqtz is None:
        return []
    try:
        _, _, times = pqtz.get()
    except Exception as exc:
        logger.warning("PQTZ nicht lesbar: %s", exc)
        return []
    try:
        content = pssi.content
        mood = int(getattr(content, "mood", 0))
        entries = list(getattr(content, "entries", []) or [])
    except (TypeError, ValueError, OverflowError, AttributeError) as exc:
        logger.warning("PSSI-Kopf nicht lesbar: %s", exc)
        return []
    if not entries or len(times) == 0:
        return []
    starts: list[tuple[float, int, int]] = []
    for e in entries:
        try:
            beat = int(e.beat)
            kind = int(e.kind)
            fill = int(getattr(e, "fill", 0))
        except (TypeError, ValueError, OverflowError, AttributeError) as exc:
            logger.warning("Defekter PSSI-Eintrag verworfen: %s", exc)
            continue
        t = _phrase_start_time(times, beat)
        if t is None or t > duration_value:
            continue
        starts.append((t, kind, fill))
    starts.sort(key=lambda s: s[0])
    unique_starts: list[tuple[float, int, int]] = []
    for item in starts:
        if not unique_starts or item[0] - unique_starts[-1][0] > 1e-6:
            unique_starts.append(item)
    starts = unique_starts
    if not starts:
        return []

    end_time = _phrase_start_time(times, getattr(content, "end_beat", 0))
    if end_time is None or end_time <= starts[-1][0]:
        end_time = duration_value
    end_time = min(end_time, duration_value)
    phrases: list[dict] = []
    for i, (t, kind, fill) in enumerate(starts):
        nxt = starts[i + 1][0] if i + 1 < len(starts) else end_time
        if nxt <= t:
            continue
        # Rohe Beatgrid-Floats, keine Rundung: 3 ms haben schon einmal einen
        # Mix-In um eine ganze Phrase verschoben (Speicher hpg-mixpoint-rundungsfehler).
        phrases.append({
            "start_s": t,
            "end_s": nxt,
            "label": phrase_label(mood, kind),
            "mood": mood,
            "kind": kind,
            "fill": fill,
        })
    unknown = sorted({p["kind"] for p in phrases if p["label"].startswith("Unbekannt")})
    if unknown:
        logger.info("PSSI: unbekannte Phrasen-Kinds %s bei mood %d", unknown, mood)
    return phrases


def phrase_grid_from_phrases(phrases: list[dict]) -> list[float]:
    """Gitterpunkte: alle Phrasenstarts plus das Ende der letzten Phrase."""
    if not phrases:
        return []
    try:
        pts = [float(p["start_s"]) for p in phrases] + [float(phrases[-1]["end_s"])]
    except (TypeError, ValueError, OverflowError, KeyError):
        return []
    out: list[float] = []
    for p in pts:
        if not math.isfinite(p) or p < 0.0:
            continue
        if not out or p - out[-1] > 1e-6:
            out.append(p)
    return out

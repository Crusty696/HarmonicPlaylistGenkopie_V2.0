# Spec: Intelligente Mix-Punkt-Berechnung mit Intro/Outro-Guard

## Datum: 2026-03-11

## Problem

Mix-In und Mix-Out Punkte koennen aktuell in Intro- oder Outro-Sektionen gesetzt werden:

1. `_find_mix_in_point()` gibt `0.0` zurueck (= Intro-Anfang) fuer kalte Starts
2. `_find_mix_out_point()` gibt den **Start** der Outro-Sektion zurueck (= IM Outro)
3. `mix_in_at_intro_start=True` fuer Psytrance/Trance erlaubt Mix-In im Intro explizit
4. Generischer Pfad in `analysis.py` setzt Mix-In auf `intro_end_time` (= Intro-Grenze)
5. Keine Validierung gegen erkannte Sektions-Labels

## Harte Regel

> **Mix-In-Point** muss NACH dem Ende aller Intro-Sektionen liegen.
> **Mix-Out-Point** muss VOR dem Beginn aller Outro-Sektionen liegen.
> Keine Ausnahmen. Kein Genre-Override.

## Design

### Prinzip: Intelligent pro Track, nie pauschal

Die App analysiert jeden Track individuell (Energie, Sektionen, Genre, BPM, Trends).
Mix-Punkte werden **pro Track** vom DJ Brain bestimmt basierend auf der tatsaechlichen
Audio-Analyse. Die Intro/Outro-Regel ist ein Guard, nicht die primaere Logik.

### Aenderung 1: `mix_in_at_intro_start` entfernen

**Datei:** `hpg_core/dj_brain.py`

- `GenreMixProfile.mix_in_at_intro_start` wird entfernt
- Psytrance-Profil (Zeile 50): `mix_in_at_intro_start=True` entfaellt
- Trance-Profil (Zeile 111): `mix_in_at_intro_start=True` entfaellt
- Alle Stellen die `mix_in_at_intro_start` lesen werden angepasst

### Aenderung 2: `_find_mix_in_point()` ueberarbeiten

**Datei:** `hpg_core/dj_brain.py`, Zeilen 317-376

Aktuelle Logik kann Zeitpunkte IM Intro zurueckgeben. Neue Logik:

1. Bestimme `intro_end` = Ende der letzten zusammenhaengenden Intro-Sektion
2. Suche die **erste energetisch starke Sektion NACH dem Intro**
3. Bewertungskriterien fuer den optimalen Einstiegspunkt:
   - Sektions-Label: "build" > "main" > "drop" (fuer Einstieg)
   - Energie relativ zum Track-Durchschnitt
   - Energie-Trend (steigend = guter Einstieg)
4. Quantisiere auf Genre-spezifische Phrasen-Grenze
5. **Garantie:** Rueckgabewert >= intro_end (nie im Intro)

Pseudocode:
```python
def _find_mix_in_point(sections, profile, seconds_per_bar):
    intro_end_time = _get_intro_end_from_sections(sections)

    # Suche beste Sektion nach Intro
    candidates = [s for s in sections if s["start_time"] >= intro_end_time
                  and s["label"] not in ("intro", "outro")]

    if not candidates:
        return intro_end_time  # Fallback: direkt nach Intro

    # Bewerte Kandidaten: Energie-Trend, Label-Praeferenz
    best = _score_mix_in_candidates(candidates, avg_energy, profile)

    # Quantisiere auf Phrasen-Grenze
    mix_in = _quantize_to_phrase(best["start_time"], seconds_per_bar, profile.phrase_unit)

    # Guard: nie vor Intro-Ende
    return max(mix_in, intro_end_time)
```

### Aenderung 3: `_find_mix_out_point()` ueberarbeiten

**Datei:** `hpg_core/dj_brain.py`, Zeilen 379-401

Aktuelle Logik gibt den Start der Outro-Sektion zurueck (= IM Outro). Neue Logik:

1. Bestimme `outro_start` = Start der ersten zusammenhaengenden Outro-Sektion
2. Suche die **letzte energetisch starke Sektion VOR dem Outro**
3. Bewertungskriterien:
   - Sektions-Label: "drop" oder "main" am Ende = guter Ausstieg
   - Energie-Abfall erkennen (wo beginnt natuerliches Ausklingen?)
   - Ende der letzten "drop"/"main"/"breakdown" Sektion vor Outro
4. Quantisiere auf Phrasen-Grenze
5. **Garantie:** Rueckgabewert < outro_start (nie im Outro)

Pseudocode:
```python
def _find_mix_out_point(sections, profile, seconds_per_bar, duration):
    outro_start_time = _get_outro_start_from_sections(sections, duration)

    # Suche beste Sektion vor Outro
    candidates = [s for s in sections if s["end_time"] <= outro_start_time
                  and s["label"] not in ("intro", "outro")]

    if not candidates:
        return outro_start_time  # Fallback: direkt vor Outro

    # Letzte starke Sektion: Ende davon ist der Mix-Out
    best = candidates[-1]  # Letzte Nicht-Outro-Sektion

    # Quantisiere auf Phrasen-Grenze
    mix_out = _quantize_to_phrase(best["end_time"], seconds_per_bar, profile.phrase_unit)

    # Guard: nie nach Outro-Start
    return min(mix_out, outro_start_time)
```

### Aenderung 4: Hilfsfunktionen

Neue Funktionen in `hpg_core/dj_brain.py`:

```python
def _get_intro_end_from_sections(sections: list[dict]) -> float:
    """Ende aller zusammenhaengenden Intro-Sektionen am Track-Anfang."""

def _get_outro_start_from_sections(sections: list[dict], duration: float) -> float:
    """Start aller zusammenhaengenden Outro-Sektionen am Track-Ende."""
```

Diese ersetzen die inline-Logik und werden auch von der Validierung genutzt.

### Aenderung 5: `calculate_genre_aware_mix_points()` Sicherheitsgrenzen

**Datei:** `hpg_core/dj_brain.py`, Zeilen 267-314

- Zeile 301: `min_mix_in = 0.0 if profile.mix_in_at_intro_start` entfaellt
- Stattdessen: `min_mix_in = _get_intro_end_from_sections(sections)`
- Zeile 303: `max_mix_out = _get_outro_start_from_sections(sections, duration)`
- Finale Validierung: `mix_in >= intro_end` und `mix_out <= outro_start`

### Aenderung 6: `calculate_paired_mix_points()` bereinigen

**Datei:** `hpg_core/dj_brain.py`, Zeilen 579-649

- Zeile 614: `if not profile_b.mix_in_at_intro_start` entfaellt
- Die Funktion arbeitet jetzt fuer ALLE Genres gleich
- Overlap-Berechnung basiert auf validierten Mix-Punkten (die bereits nicht im Intro/Outro liegen)

### Aenderung 7: `analysis.py` generischer Pfad absichern

**Datei:** `hpg_core/analysis.py`, Zeilen 544-694

Der generische Pfad hat keine Sektions-Labels, arbeitet nur mit RMS-Energie.
Anpassung:
- Mix-In wird auf die **erste Phrase-Grenze NACH intro_end_time** gesetzt (nicht auf intro_end_time selbst)
- Mix-Out wird auf die **letzte Phrase-Grenze VOR outro_start_time** gesetzt

Konkret (Zeile 635-639):
```python
# Alt: intro_phrase_count = round(intro_end_time / seconds_per_phrase)
# Neu: ceil statt round, damit wir NACH dem Intro landen
intro_phrase_count = ceil(intro_end_time / seconds_per_phrase)
if intro_phrase_count < 1:
    intro_phrase_count = 1
```

Konkret (Zeile 645-653):
```python
# Alt: outro_phrase_index = floor(outro_start_time / seconds_per_phrase)
# Neu: floor und dann -1, damit wir VOR dem Outro landen
outro_phrase_index = floor(outro_start_time / seconds_per_phrase) - 1
if outro_phrase_index < 1:
    outro_phrase_index = 1
```

### Aenderung 8: Tests

**Neue Tests:**
- `test_mix_in_never_in_intro_section`: Verschiedene Track-Strukturen -> Mix-In immer nach Intro
- `test_mix_out_never_in_outro_section`: Verschiedene Track-Strukturen -> Mix-Out immer vor Outro
- `test_psytrance_no_intro_start`: Psytrance Mix-In nicht bei 0.0 wenn Intro vorhanden
- `test_trance_no_intro_start`: Trance ebenso
- `test_different_structures_different_mix_points`: Tracks mit verschiedenen Strukturen bekommen verschiedene Mix-Punkte
- `test_short_track_with_mostly_intro_outro`: Edge-Case mit minimalem Nutzbereich

**Angepasste Tests:**
- Tests die `mix_in_at_intro_start=True` erwarten -> anpassen
- Tests die Mix-In bei 0.0 erwarten -> anpassen auf >= intro_end

### Nicht geaendert

- `hpg_core/structure_analyzer.py` (Sektions-Erkennung funktioniert korrekt)
- `hpg_core/scoring_engine.py` (nutzt Mix-Punkte nur lesend)
- `hpg_core/transition_renderer.py` (nutzt Mix-Punkte nur lesend)
- `hpg_core/models.py` (Track/TrackSection Datenmodell bleibt gleich)
- Genre-Kompatibilitaets-Matrix (nur Mix-Profile betroffen)

## Betroffene Dateien

| Datei | Aenderung |
|-------|-----------|
| `hpg_core/dj_brain.py` | Hauptaenderungen: Profile, Mix-Punkt-Logik, Validierung |
| `hpg_core/analysis.py` | Generischer Pfad: ceil/floor Korrektur |
| `tests/test_mix_points.py` | Anpassung bestehender Tests |
| `tests/test_mix_points_root.py` | Anpassung bestehender Tests |
| `tests/test_dj_brain.py` | Neue Tests fuer Intro/Outro-Guard |
| `tests/fixtures/track_factories.py` | Ggf. Factory-Anpassung |

## Risiken

- Psytrance/Trance DJs nutzen traditionell Intro-Start-Mixing. Diese Aenderung bricht damit.
  Entscheidung des Users: Regel gilt ausnahmslos.
- Tracks ohne erkannte Sektionen fallen auf den generischen Pfad zurueck.
  Dort ist die Absicherung weniger praezise (RMS-basiert statt sektionsbasiert).

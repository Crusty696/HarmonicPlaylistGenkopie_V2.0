---
name: hpg-genres
description: Use when adding, renaming or retuning an HPG genre, or when touching GENRE_PROFILES, GENRE_MIX_PROFILES, GENRE_COMPATIBILITY, ID3_GENRE_MAP, GENRE_PHRASE_UNITS, classify_genre oder wenn beim Import ein "Genre-Tabellen inkonsistent"-ValueError fliegt.
---

# HPG Genres

## Single Source of Truth

**Alles Genre-bezogene lebt in `hpg_core/genres.py`.** dj_brain und
genre_classifier re-exportieren nur; `structure_analyzer` leitet ab. Wer eine
zweite Genre-Tabelle anlegt, baut Drift.

`CANONICAL_GENRES` [hpg_core/genres.py] — aktuell 9:
Psytrance · Tech House · Progressive · Melodic Techno · Techno · Deep House ·
Trance · Drum & Bass · Minimal.

## Die vier Tabellen

| Tabelle | Inhalt |
|---|---|
| `GENRE_PROFILES` [hpg_core/genres.py] | `GenreProfile` — BPM-Range, spektrale Merkmale; Input der Klassifikation |
| `ID3_GENRE_MAP` [hpg_core/genres.py] | ID3-Tag-Text -> kanonisches Genre |
| `GENRE_MIX_PROFILES` [hpg_core/genres.py] | `GenreMixProfile` — `phrase_unit`, `transition_bars`, `outro_bars` |
| `GENRE_COMPATIBILITY` [hpg_core/genres.py] | `(a, b) -> 0.0-1.0`, symmetrisch gemeint |

## Neues Genre hinzufuegen — die Checkliste

`_validate_genre_tables()` [hpg_core/genres.py] laeuft **beim Import** und wirft
`ValueError("Genre-Tabellen inkonsistent: ...")`. Sie prueft:

1. `set(GENRE_PROFILES) == set(CANONICAL_GENRES)`
2. `set(GENRE_MIX_PROFILES) == set(CANONICAL_GENRES)`
3. alle in `GENRE_COMPATIBILITY` vorkommenden Genres == canonical
4. Selbst-Paar `(g, g) == 1.0` fuer jedes Genre
5. **jedes** Cross-Paar aus `combinations(canonical, 2)` vorhanden — in einer
   der beiden Richtungen. Ohne diesen Check waeren fehlende Paare still auf
   `0.5` gedriftet.
6. `ID3_GENRE_MAP`-Werte alle canonical
7. `profile.phrase_unit in (8, 16, 32)`

Also: **vier** Tabellen plus `CANONICAL_GENRES` anfassen, und bei 9 -> 10
Genres kommen **9 neue Cross-Paare** dazu. Nichts davon ist optional.

## Wirkung eines neuen Genres

`phrase_unit` ist der Hebel mit der groessten Auswirkung:

```
GENRE_MIX_PROFILES[g].phrase_unit
  -> `GENRE_PHRASE_UNITS` [hpg_core/structure_analyzer.py] (abgeleitet)
  -> Sektions-Erkennung (analyze_structure)
  -> grid = seconds_per_bar * phrase_unit
  -> Quantisierung aller Mix-Punkte
```

`GENRE_PHRASE_UNITS["Unknown"]` faellt auf `DEFAULT_MIX_PROFILE.phrase_unit`.

## Lookups sind case-insensitiv — aber nur im Fallback

`get_genre_compatibility` [hpg_core/dj_brain.py]: exakt -> vertauscht -> casefold
(`_GENRE_COMPATIBILITY_NORMALIZED`) -> `0.5`. `get_mix_profile`
[hpg_core/dj_brain.py]: exakt -> casefold -> `DEFAULT_MIX_PROFILE`.

`"Unknown"` oder leer liefert immer `0.5`. Achtung: `"Unknown"` ist ein
**truthy** String — ein `if not track.detected_genre`-Fallback greift dort
nie (Altbefund F12).

### Zwei Begriffe von "Genre dieses Tracks" — bewusst so

`_resolve_track_genre` [hpg_core/playlist.py] faellt auf das **ID3-Genre**
zurueck, wenn `detected_genre` fehlt oder `"Unknown"` ist. Genau diese
Funktion benutzt `pair_candidates._genre` fuer Toleranzen und Blendenlaengen.

Der DJ-Brain-Zweig kennt diesen Fallback NICHT: `has_dj_data`
[hpg_core/playlist.py] prueft allein `detected_genre`, und
`generate_dj_recommendation` [hpg_core/dj_brain.py] loest intern genauso auf
(`genre_a = track_a.detected_genre or "Unknown"`). Dieselbe Regel gilt in der
GUI [main.py].

Folge: ein Track mit `detected_genre = "Unknown"` und ID3 `"Deep House"`
bekommt Deep-House-Toleranzen in der Kandidatenbewertung, waehrend DJ-Brain
ihn ueberspringt. Entscheidung 2026-09-04: **nicht angleichen, nur
dokumentieren** — jede Angleichung verschiebt Scoring-Ergebnisse und braucht
einen Hoerbeleg. Wer `has_dj_data` allein auf `_resolve_track_genre`
umstellt, laesst DJ-Brain mit dem `DEFAULT_MIX_PROFILE` laufen; das waere
schlechter als der heutige Verzicht.

## Klassifikation

`classify_genre` [hpg_core/genre_classifier.py] ist **regelbasiert, kein ML**:
`extract_genre_features` -> `_score_genre` pro Profil -> bester Score.
`GENRE_CONFIDENCE_THRESHOLD = 0.4` [hpg_core/config.py]. Ein neues Genre wird nur
erkannt, wenn sein `GenreProfile` diskriminierende Ranges hat — die
Validierung prueft Vollstaendigkeit, nicht Erkennungsqualitaet.

DnB-Sonderfall: `DNB_MINIMUM_BPM = 160.0` daempft (kein harter Ausschluss) mit
`DNB_LOW_BPM_PENALTY = 0.5`; `BPM_HALFTIME_MAX_RESULT = 185.0` verhindert
falsche Verdopplung.

## Verifikation

`tests/test_genres.py` deckt die Tabellen-Invarianten ab. Nach jeder
Genre-Aenderung ausserdem `CACHE_VERSION` bumpen — `detected_genre`,
`phrase_unit` und die Mix-Punkte sind gecacht. Siehe `hpg-cache-persistence`.

## Common Mistakes

- Nur `GENRE_PROFILES` erweitern -> Import bricht sofort.
- Cross-Paare vergessen -> ValueError mit Paar-Liste (die Liste ist die
  To-do-Liste).
- `phrase_unit = 12` o.ae. -> unzulaessig, nur 8/16/32.
- Zweite Phrase-Tabelle anlegen statt aus `GENRE_MIX_PROFILES` abzuleiten.

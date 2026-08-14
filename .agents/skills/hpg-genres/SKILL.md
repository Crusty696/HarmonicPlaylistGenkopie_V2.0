---
name: hpg-genres
description: Use when adding, renaming or retuning an HPG genre, or when touching GENRE_PROFILES, GENRE_MIX_PROFILES, GENRE_COMPATIBILITY, ID3_GENRE_MAP, GENRE_PHRASE_UNITS, classify_genre oder wenn beim Import ein "Genre-Tabellen inkonsistent"-ValueError fliegt.
---

# HPG Genres

## Single Source of Truth

**Alles Genre-bezogene lebt in `hpg_core/genres.py`.** dj_brain und
genre_classifier re-exportieren nur; `structure_analyzer` leitet ab. Wer eine
zweite Genre-Tabelle anlegt, baut Drift.

`CANONICAL_GENRES` [genres.py:21] — aktuell 9:
Psytrance · Tech House · Progressive · Melodic Techno · Techno · Deep House ·
Trance · Drum & Bass · Minimal.

## Die vier Tabellen

| Tabelle | Zeile | Inhalt |
|---|---|---|
| `GENRE_PROFILES` | :47 | `GenreProfile` — BPM-Range, spektrale Merkmale; Input der Klassifikation |
| `ID3_GENRE_MAP` | :189 | ID3-Tag-Text -> kanonisches Genre |
| `GENRE_MIX_PROFILES` | :300 | `GenreMixProfile` — `phrase_unit`, `transition_bars`, `outro_bars` |
| `GENRE_COMPATIBILITY` | :400 | `(a, b) -> 0.0-1.0`, symmetrisch gemeint |

## Neues Genre hinzufuegen — die Checkliste

`_validate_genre_tables()` [genres.py:477] laeuft **beim Import** und wirft
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
  -> GENRE_PHRASE_UNITS  [structure_analyzer.py:64, abgeleitet]
  -> Sektions-Erkennung (analyze_structure)
  -> grid = seconds_per_bar * phrase_unit
  -> Quantisierung aller Mix-Punkte
```

`GENRE_PHRASE_UNITS["Unknown"]` faellt auf `DEFAULT_MIX_PROFILE.phrase_unit`.

## Lookups sind case-insensitiv — aber nur im Fallback

`get_genre_compatibility` [dj_brain.py:47]: exakt -> vertauscht -> casefold
(`_GENRE_COMPATIBILITY_NORMALIZED`) -> `0.5`. `get_mix_profile`
[dj_brain.py:88]: exakt -> casefold -> `DEFAULT_MIX_PROFILE`.

`"Unknown"` oder leer liefert immer `0.5`. Achtung: `"Unknown"` ist ein
**truthy** String — ein `if not track.detected_genre`-Fallback greift dort
nie (Altbefund F12).

## Klassifikation

`classify_genre` [genre_classifier.py:279] ist **regelbasiert, kein ML**:
`extract_genre_features` -> `_score_genre` pro Profil -> bester Score.
`GENRE_CONFIDENCE_THRESHOLD = 0.4` [config.py]. Ein neues Genre wird nur
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

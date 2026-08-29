# Plan: Mixpoint-Pfad-B-Konsolidierung (research-basiert)

**Datum:** 2026-07-17
**Ziel:** `analyze_structure_and_mix_points` (analysis.py, "Pfad B"/RMS-Fallback) entkernen — künftig nur noch EINE Quantisierungs-/Clamp-Logik (Pfad A, `calculate_genre_aware_mix_points`). Pfad B wird zur schlanken Fassade: RMS-Aktivitätserkennung → 3 Pseudo-Sektionen → Pfad A.

## Recherche-Grundlage (Web-Recherche 2026-07-17, Volltexte)

| Quelle | Verwertete Erkenntnis |
|---|---|
| Bittner et al., ISMIR 2017 (Spotify), archives.ismir.net/ismir2017/paper/000086.pdf | Mix-In-Kandidaten nur in den **ersten 20 %**, Mix-Out nur in den **letzten 25 %** des Tracks; Punkte downbeat-quantisiert; leise Übergangsregionen bestrafen |
| Zehren et al., arXiv 2007.08411 / Computer Music Journal 2022 | Abschnitt "tragfähig/aktiv" wenn mittlere Energie über **4-Takt-Fenster ≥ 0,4 × Track-Maximum** (Salience); Cues auf Downbeat/Periodengrenzen |
| Vande Veire & De Bie, EURASIP 2018 (From raw audio to a seamless mix) | Struktur binär L/H über **RMS pro Takt**; Boundaries auf **8-Takt-Raster**; Standard-Fades **16 Takte**; Einstieg 16 Takte vor Drop |
| arXiv 2407.06823 (Cue Point Estimation, 2024) | Reale DJ-Cues: häufigster Abstand **16 Takte**, dann 8 — Phrasengrenzen bestätigt |
| Tool-Recherche (MIK, rekordbox, VirtualDJ, djay) | Alle quantisieren auf Beatgrid/Phrase; Interna proprietär — Papers sind die belastbare Quelle |

## Ist-Zustand (Code-Analyse 2026-07-17)

- Pfad B läuft nur bei `DJ_BRAIN_ENABLED=False` ODER leeren `section_dicts` (analysis.py:780/1045). Bei Default (`True`) ist er produktiv toter Fallback — nur Tests rufen ihn direkt.
- Divergenz zu Pfad A: eigene Prozent-Clamps (0.4/0.6, 0.15/0.85), eigene ceil/floor-Logik, Schwelle 0,4×**Mittelwert** statt Max.
- `calculate_genre_aware_mix_points` braucht Section-Dicts mit `label`, `start_time`, `end_time` (optional `avg_energy`); 3 Pseudo-Sektionen intro/main/outro genügen.
- `phrase_unit` muss nicht übergeben werden: Genre-Übergabe reicht, `get_mix_profile(genre)` liefert konsistent dasselbe Profil (Unknown → DEFAULT, phrase_unit 8).

## Design der neuen Fassade

Signatur: `analyze_structure_and_mix_points(y, sr, duration, energy_level, bpm, genre="Unknown")` — `phrase_unit`-Parameter entfällt (kommt aus dem Genre-Profil).

1. **Guards unverändert**: `bpm <= 0` → ValueError (bestehender Vertrag, Tests); `duration/bpm` fehlt → Default-Rückgabe.
2. **RMS-Aktivitätserkennung (research-gehärtet):**
   - RMS-Kurve, geglättet über ein **4-Takt-Fenster** (Zehren-Salience statt bisher fixe 2 s)
   - aktiv = `rms_smooth ≥ 0,4 × max(rms_smooth)` (Zehren; bisher 0,4 × Mittelwert)
   - `intro_end` = erster aktiver Zeitpunkt, `outro_start` = letzter aktiver
   - Stille-Guard: Max ≈ 0 → 16-Takt-Fallbacks (Vande Veire Fade-Standard)
3. **Suchfenster-Pruning (Bittner):** `intro_end` gedeckelt auf **20 %** der Tracklänge, `outro_start` mindestens bei **75 %**; sonst 16-Takt-Fallback. Ersetzt die alten Konstanten `INTRO_MAX_PERCENTAGE`/`OUTRO_MIN_PERCENTAGE` durch `MIX_IN_SEARCH_WINDOW_PCT = 0.20` / `MIX_OUT_SEARCH_WINDOW_PCT = 0.75` (zitiert).
4. **Pseudo-Sektionen:** `[{intro: 0..intro_end}, {main: ..outro_start}, {outro: ..duration}]` mit `avg_energy` aus der geglätteten RMS (0–100, relativ zum Track-Max).
5. **Delegation:** `return calculate_genre_aware_mix_points(sections, bpm, duration, genre)` — Phrase-Alignment, Intro/Outro-Guards, Fenster-Clamps: alles nur noch in Pfad A.
6. **Except-Fallback** wie bisher (safe 0.2/0.8-Punkte).

## Folgeänderungen

- **Callsites** (analysis.py:790, 1056): `genre=genre_result.genre` statt `phrase_unit=...`.
- **`DJ_BRAIN_ENABLED` entfernen**: Nach der Konsolidierung enden beide Zweige in Pfad A — der Master-Schalter schaltet nichts mehr. Bedingung wird `if section_dicts:`. (config.py, analysis.py-Import, test_config.)
- **Tote Konstanten**: `INTRO_MAX_PERCENTAGE`, `OUTRO_MIN_PERCENTAGE` raus (ersetzt, s.o.); `BARS_PER_PHRASE` bleibt (Tests nutzen sie als Referenzwert).
- **`CACHE_VERSION` 14 → 15** (Analyse-Output ändert sich für Fallback-Tracks).

## Erwartete Test-Anpassungen (bewusst, kein Rubber-Stamping)

| Test | Grund | Anpassung |
|---|---|---|
| `test_zero_bpm` (2×) | Vertrag bleibt: Fassade wirft weiter ValueError | keine |
| `test_mix_in_max_30_percent` | 30 %-Cap war Pfad-B-Detail; Pfad A garantiert Fenster-Clamps | auf Suchfenster+Phrase-Puffer (≤ 40 %) lockern, Quelle zitieren |
| `test_4_phrase_gap_minimum`, `test_mix_out_min_70_percent` | Pfad A garantiert `min_window = 2 Phrasen` (nicht 4) | auf 2-Phrasen-Invariante umstellen |
| `test_mix_in_uses_ceil_logic` | ceil-Detail von Pfad B | auf Pfad-A-Invariante (mix_in ≥ 1 Phrase) umstellen |
| `%8`-Alignment-Tests | bleiben gültig (Unknown → phrase_unit 8) | keine |
| Fenster-Asserts in `test_standard_house_track_128bpm` | konkrete Sekundenfenster | an neue Grenzen anpassen |
| `test_config`-Asserts zu INTRO_MAX/OUTRO_MIN/DJ_BRAIN_ENABLED | Konstanten entfallen/ersetzt | auf neue Konstanten umstellen |

## Verifikation

Volle Suite grün + Import-Smoke-Test + manuelle Invariantenprüfung (0 ≤ in < out ≤ duration, Phrase-Alignment) über parametrisierte BPM/Dauer-Matrix.

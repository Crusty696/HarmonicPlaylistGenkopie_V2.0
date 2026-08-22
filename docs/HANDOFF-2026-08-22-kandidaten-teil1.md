# Handoff 2026-08-22: Mixpunkt-Kandidaten Teil 1 — Realmessung und Abschluss

Vorheriger Stand: `docs/HANDOFF-2026-08-22-stand-fuer-neuen-agenten.md`.
Plan: `docs/superpowers/plans/2026-08-21-mixpunkt-kandidaten-teil1-datenmodell.md`
(Task 12, Steps 1–2 und 4 sind mit diesem Dokument erledigt; Merge auf `main`
war `f18815b`).

## Messung an den 231 analysierten Tracks (Pflicht aus Task 12)

Werkzeug `tools/kandidaten_messen.py --liste tracks231.txt --json kandidaten_v34.json`
(Liste = alle 231 `filepath`-Zeilen aus `hpg_cache_v33.db`, alle Dateien
vorhanden), gestartet 2026-08-22 17:42, Dauer **10 503 s (2 h 55 min)**,
Exit-Code 0, einzelner Prozess, `venv312`. `analyze_track` schreibt in den
Cache v34 (nach dem Lauf 231 Zeilen in `hpg_cache_v34.db`).

| Kennzahl | Wert |
|---|---|
| Tracks | 231 |
| `intro_outro_verletzungen` | **0** (Pflicht erfuellt) |
| `ohne_in` / `ohne_out` | 1 / 1 |
| `mit_pssi` (Rekordbox-Phrasen gelesen) | 211 von 231 |
| Kandidaten je Seite, Median | In 8, Out 8 (= `KANDIDATEN_MAX_JE_SEITE`) |
| Kandidaten gesamt | 3 664 |
| Schemata In (Summe ueber alle Kandidaten, Mehrfachnennung) | pssi_phrase 1688, sektion 1633, auto_cue 819, energie_neuheit 596, analyzer 230 |
| Schemata Out | pssi_phrase 1688, sektion 1585, auto_cue 779, energie_neuheit 554, analyzer 228, benannter_cue 1 |
| Analysezeit je Track, Median | **42,23 s** |
| davon Kandidaten (`build_track_candidates`), Median | **20,32 s** (≈ 48 % der Analysezeit) |
| Analysepfade | fast 206, voll 20 (5 Tracks ohne Pfad-Logzeile) |

Die Analysezeit je Track steigt durch die Kandidaten-Messung erheblich (Spec
Abschnitt 4 "wird gemessen, nicht geschaetzt"): ~20 s je Track fuer bis zu 16
Kandidatenfenster mit LUFS in nativer Samplerate. Bei 231 Tracks sind das
knapp 80 min zusaetzlich (Einzelprozess; die App parallelisiert ueber
`ParallelAnalyzer`).

## Spannen der lokalen Messwerte (3 664 Kandidaten)

| Feld | n | min | p10 | Median | p90 | max |
|---|---|---|---|---|---|---|
| `avg_mids_lokal` (Prozentpunkte) | 3664 | 2.0 | 4.8 | 7.2 | 11.4 | 77.2 |
| `avg_highs_lokal` | 3664 | 0.1 | 1.1 | 1.9 | 3.1 | 13.1 |
| `bass_rms_dbfs` | 3664 | −43.9 | −13.9 | −10.5 | −8.4 | −5.9 |
| `lufs_lokal` | 3664 | −32.4 | −11.4 | −8.6 | −6.6 | −3.5 |
| `brightness_lokal` | 3664 | 0 | 13 | 22 | 32 | 55 |
| `syncopation_lokal` | 3513 | 0.000 | 0.336 | 0.455 | 0.603 | 0.998 |
| `percussive_ratio_lokal` | 3664 | 0.115 | 0.246 | 0.305 | 0.424 | 0.867 |
| `key_confidence_lokal` | 3664 | 0.40 | 0.40 | 0.60 | 1.00 | 1.00 |
| `neuheit` | 3632 | 0.000 | 0.013 | 0.072 | 0.264 | 0.640 |

Paarweise Differenzen (Out-Kandidat A ↔ In-Kandidat B, Stichprobe 20 000
Zufallspaare innerhalb 2 BPM): `avg_mids` Median 2.3 / p90 8.1; `avg_highs`
0.8 / 2.0; `bass_rms_dbfs` 1.9 dB / 7.2 dB; `lufs_lokal` 1.7 dB / 4.8 dB;
`syncopation` 0.09 / 0.28; `brightness` 7 / 17.

Weitere Befunde: `camelot_lokal` nie leer (0 von 3664); `kick_aktiv` True nur
82 / False 3359 / None 223 — die Teil-1-Startwerte `KICK_AKTIV_MIN_DBFS = −35`
und `KICK_AKTIV_ONBEAT_MIN = 0.40` markieren fast nie einen aktiven Kick
(offen, Hoertest prueft); `vocal_aktiv_lokal` True bei 1886 (51 %) — der
Vocal-Detektor schlaegt bei Psytrance haeufig an (bekannte Schwaeche des
Detektors, nicht Teil 1); `pssi_mood` fehlt bei 288 Kandidaten (Tracks ohne
PSSI); `percussive_ratio_lokal` liegt zur Haelfte unter 0.3 (Spec-Schwelle
"lange Blende erlaubt") und praktisch nie ueber 0.7.

Konsequenz fuer Teil 2 (bereits umgesetzt, Branch `kandidaten-teil2`): die
Normierungs-Spannen `BASS_RMS_DELTA_MAX_DB = 7.0`, `SYNCOPATION_DELTA_MAX =
0.3`, `MIDS_HIGHS_DELTA_MAX = 5.0` sind die gemessenen p90-Werte statt
Schaetzungen.

## Teil 1 damit abgeschlossen

- Code gemerged (`f18815b`), Suite 1786 passed.
- Realmessung wie oben, `intro_outro_verletzungen = 0`.
- Rohdaten der Messung: `kandidaten_v34.json` (Scratchpad der Session
  261b9a6b; bei Verlust: `tools/kandidaten_messen.py --cache` gegen
  `hpg_cache_v34.db`, das jetzt alle 231 Tracks enthaelt).

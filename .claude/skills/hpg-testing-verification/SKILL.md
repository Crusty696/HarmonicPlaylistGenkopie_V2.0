---
name: hpg-testing-verification
description: Use when running or writing HPG tests, or before claiming HPG work is done — pytest-Aufruf und Interpreter, Test-Baseline, Coverage-Gate, conftest-Fixtures und Assert-Helfer, verify_*.py, e2e_check.py, tools/-Validierungsskripte.
---

# HPG Testing & Verification

## Der Befehl

```bat
.\venv312\Scripts\python.exe -m pytest tests/ --no-cov -q
```

**Nur `venv312`.** Python 3.12.10, weil numba (librosa-Stack) kein 3.13+ kann.
System-Python liefert numba-Fehler, die wie Code-Bugs aussehen.

Volllauf mit Coverage (langsamer, aber das ist das echte Gate):

```bat
.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q
```

## Letzter Volltest-Snapshot

**2035 passed, 25 warnings, 81,65 % Coverage** wurden am 2026-08-25 vor den
nachfolgenden GUI-/E2E-/Kandidatensatz-Auditor-Aenderungen gemessen mit:

```bat
.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q
```

Diese Zahlen sind keine aktuelle Baseline und kein Abschlussbeleg fuer den
jetzigen Worktree. Immer neu messen.

**Historischer Snapshot 2026-08-15:** 1492 passed, 26 Warnungen und 75,92 %
Coverage mit den damals vorhandenen Tests. Diese Zahlen sind keine aktuelle
Baseline.

Aeltere Zahlen im Repo sind datierte Snapshots, keine Widersprueche:
`docs/AGENT_HANDOFF.md` nennt 1313, der historische Abschnitt in
`PRODUCTION_STATUS.md` nennt 1384. **Immer selbst zaehlen**, nie eine Zahl aus
einem Markdown uebernehmen — auch nicht aus diesem Skill.

## Was pytest.ini erzwingt

`--strict-markers --strict-config -ra --durations=10 --cov=hpg_core --cov=main
--cov-fail-under=70 -n auto`

- `-n auto` (xdist) ist Standard. Fuer korrekte Coverage-Messung deaktivieren
  (`tools/check_coverage.py` macht genau das).
- `error::UserWarning:hpg_core.*` — eine `UserWarning` aus `hpg_core` ist ein
  **Testfehler**, kein Rauschen.
- `--no-cov` nur fuer schnelle Einzellaeufe waehrend der Entwicklung, nie als
  Abschlussbeleg.
- Marker sind strikt: `unit`, `integration`, `performance_test`, `acceptance`,
  `regression`, `slow`, `requires_audio`, `gui`, `exporter`. Ein Tippfehler
  bricht die Sammlung ab.

## Fixtures und Helfer (tests/conftest.py)

- Audio: `click_128bpm`, `click_120bpm`, `silence_10s`, `noise_10s`,
  `structured_audio_128bpm`, `a_minor_chord`, `c_major_chord`
- Tracks: `house_track`, `techno_track`, `dnb_track`, `minimal_track`,
  `dj_set_8tracks`, `dj_set_3tracks`, `all_camelot_tracks`
- Invarianten: `assert_mix_points_valid` [:216], `assert_phrase_aligned` [:245]
- `tests/performance_fixtures.py` liefert vor-analysierte Tracks **ohne**
  Audio-Generierung — fuer alles, was keine echte Analyse braucht

Neue Mixpoint-Tests immer ueber die beiden Assert-Helfer fuehren, nicht mit
eigenen Toleranzen.

## Cache-Isolation

Tests duerfen nie die Produktiv-DB anfassen. `HPG_CACHE_FILE` bzw.
`HPG_CACHE_DIR` setzen (siehe `tests/test_cache_isolation.py`).

## Verifikation jenseits von pytest

| Skript | Prueft |
|---|---|
| `verify_fixes.py` | Welle-1-Audit-Szenarien (Mixpoint-Grenzen) |
| `verify_wave2.py` | Welle-2-Szenarien |
| `verify_wave4.py` | Welle-4-Szenarien, u. a. EQ-Mittelpunkt-Pegel |
| `e2e_check.py` | echtes Audio: Analyse zu Playlist zu Empfehlungen zu Render, mit Invarianten (Peak, Pegel, Grid) |
| `tools/check_coverage.py` | Coverage ohne xdist |
| `tools/validation_run.py` | reale Library gegen Ground Truth |
| `tools/bpm_accuracy_check.py`, `tools/batch_genre_check.py` | Feature-Genauigkeit |
| `tools/run_ground_truth_predictions.py`, `tools/evaluate_ground_truth.py` | reproduzierbare Predictions gegen Labels |
| `tools/prepare_dj_blind_test.py` | anonymisierte A/B-Clips fuer Hoertests |
| `tools/release_manifest.py` | SHA256 + Commit, verweigert dirty Worktree |

`e2e_check.py` sucht Audio unter `tests/`, `validation/` und
`HPG_TEST_AUDIO_DIR`. Ohne echte Dateien laeuft es ins Leere — das ist kein
Erfolg.

Hilfsskripte aus `tools/` muessen den Parent-Pfad zu `sys.path` haengen.

## Hoertest Kandidatenmodus (Teil 3, gebaut 2026-08-22)

Spec Abschnitt 3; Plan `docs/superpowers/plans/2026-08-22-mixpunkt-kandidaten-teil3-hoertest.md`.
- `tools/rate_transitions.py prepare --modus kandidaten --anzahl N --out <Satz>`:
  je Paar (Gates wie heute) alle `PairCandidate`s als Clip `<pair_id>_k<n>.wav`
  (`rendere_kandidat`: Zeitpunkte + Blende des Kandidaten, `pro_eq_swap`, 8 s
  Vor-/Nachlauf; Blende ueber `MAX_TRANSITION_OVERLAP_SECONDS` oder Restlaenge
  faellt weg). Dateien: `bewertung.csv` (`pair_id, clip_id, note, gewaehlt,
  zeit`), `merkmale.csv` (`MERKMALE_KANDIDATEN_SPALTEN`: zehn Teilwerte, score,
  Schema/Provenienz/Confidence, Blende, bpm/genre/key-Kontext), `reihenfolge.json`
  (Seed je Paar), `LIESMICH-kandidaten.txt`. `--modus einzel` (Default) =
  heutiger Satz, unveraendert.
- `tools/hoertest_server.py --dir <Satz>`: erkennt den Kandidatensatz an der
  Spalte `clip_id` (kein Schalter); Seite je Paar, Note 1-5 + "bester" (Taste B),
  POST `/note` `{pair_id, clip_id, note|null}`, POST `/bester` `{pair_id, clip_id}`,
  Zeitstempel; `/daten` liefert je Clip NUR `clip_id, clip, note, gewaehlt,
  crossfade_sek` (verdeckt). Mobil: Server samt Satz kopieren, Kontext kommt
  aus `merkmale.csv`, wenn kein Cache da ist.
- `tools/rate_transitions.py fit --modus kandidaten --dir <Satz> [--cache <db>]`
  (`--genre` wird hier ignoriert): Zielgroesse 1
  Note (L2-Logistik), Zielgroesse 2 Paarvergleich (Bradley-Terry, Differenzen
  Sieger-Verlierer ohne Spiegelung, unstandardisiert), nur **identifizierbare**
  Merkmale (Innerhalb-Paar-Streuung >= `PAAR_STREUUNG_MIN`) werden neu
  gewichtet, Holdout nach Tracks (`HOLDOUT_ANTEIL` 0.30 der Tracks, ~51 % der
  Clips), AUC/Trefferquote vs. Zufallsbasis; `uebernahme_erlaubt` entscheidet:
  ja -> `hpg_core/data/candidate_preferences.json`, nein ->
  `<Satz>/candidate_preferences_entwurf.json` + Grund.
- `hpg_core/candidate_preferences.py`: Lader (mitgeliefert + Override
  `%LOCALAPPDATA%\HPG\candidate_preferences.json` / `HPG_CANDIDATE_PREFERENCES_FILE`);
  `pair_candidates.score_pair` nimmt die Praeferenz-Gewichte, wenn kein
  explizites `tolerances` uebergeben wird. Tests sind per Autouse-Fixture in
  `tests/conftest.py` davon entkoppelt.
- Seit Teil 4 scort `prepare --modus kandidaten` mit `bass_swap_geplant=True`
  (pro_eq_swap ist ein Bass-Swap: kein `KICK_KONFLIKT_ABZUG` in der CSV).
- Hoerproben selbst (Menschen) stehen auf der Checkliste im Handoff Teil 3/4.
- App-Regression: `tools/playlist_kandidaten_messen.py --cache [--ohne-kandidaten]`.
- Objektive E2E-Pruefung der Kandidaten in der App (Preview = Plan, Wahl
  persistiert/folgt, Ketten-Neustarts, Regler-Wirkung, XML MIX IN/OUT = Plan,
  HPG-K-Cues) auf echten Cache-Daten: `tools/e2e_kandidaten_app.py --out <Ordner>`
  (schreibt Wahl/Regler nur in Dateien unter --out). Ersetzt nicht das Hoeren.

## Was "fertig" heisst

1. Volle Suite gruen, Zahl **selbst gesehen**
2. Coverage-Gate 70 % gehalten
3. bei DSP-/Analyse-Aenderungen: `e2e_check.py` auf echtem Audio
4. bei geaendertem Analyse-Output: `CACHE_VERSION` gebumpt
   (Skill `hpg-cache-persistence`)
5. keine neue `UserWarning` aus `hpg_core`

Ohne Punkt 1 gibt es keine Erfolgsmeldung — auch nicht "sollte gruen sein".

## Common Mistakes

- System-Python statt `venv312`.
- Testzahl aus einem Markdown zitieren.
- `--no-cov` benutzen und dann Coverage behaupten.
- Neue Datei in `tools/` ohne `sys.path`-Anpassung.
- Gruene Suite als Beweis fuer musikalische Qualitaet lesen — dafuer gibt es
  den Blindtest.

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
.\venv312\Scripts\python.exe -m pytest tests/ -q
```

## Baseline

**1492 passed, 26 warnings, ~102 s** im vollen Lauf (`pytest -m ""`),
**rund 1303 in ~70 s** im Standardlauf. Gemessen 2026-08-15.

Die zwei Integrationstests mit echter Audio-Analyse sind als `slow` markiert
und per `pytest.ini` standardmaessig abgewaehlt — sie brauchen rund 92 s bzw.
90 s CPU und kosten unter `-n auto` etwa 32 s Wall-Clock (102 s statt
70 s). Coverage faellt dadurch von 75,92 % auf rund 73,5 %, das 70-%-Gate
haelt in beiden Faellen.

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

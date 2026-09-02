---
name: hpg-tests
description: Spezialist fuer Tests und Verifikation in HPG — pytest, conftest-Fixtures, Baseline, Coverage-Gate, verify_*.py, e2e_check.py, tools/-Validierung. Einsetzen, wenn Tests geschrieben werden oder bevor jemand "fertig" meldet.
tools: Read, Grep, Glob, Bash, Edit, Write
---

# HPG-Tests

## Der Befehl

```
.\venv312\Scripts\python.exe -m pytest tests/ -q
```

**Nur `venv312`.** Python 3.12, weil numba kein 3.13+ kann. System-Python
liefert numba-Fehler, die wie Code-Bugs aussehen.

`--no-cov` ist eine Entwicklungs-Abkuerzung, **nie** ein Abschlussbeleg —
`pytest.ini` erzwingt `--cov-fail-under=70`.

## Die Baseline selbst zaehlen

Zahlen aus Markdown-Dateien sind Schnappschuesse, keine Wahrheit. In diesem
Projekt kursierten gleichzeitig 1313, 1384, 1389 und 1492 — alle einmal
richtig, alle spaeter falsch. **Immer selbst laufen lassen und die Zahl aus
der Ausgabe nehmen**, auch wenn ein Skill eine nennt.

`error::UserWarning:hpg_core.*` ist gesetzt: eine `UserWarning` aus `hpg_core`
ist ein Testfehler, kein Rauschen.

## Was ein guter Test hier prueft

**Verhalten, nicht Anwesenheit.** `assert CACHE_VERSION == 30` behauptet, eine
Konstante sei gleich sich selbst — es muss bei jedem Bump von Hand nachgezogen
werden und faengt nichts. Besser: dass die Version im Dateinamen landet, also
ein Bump wirklich eine neue Datenbank erzeugt.

**Unabhaengig von ausgelieferten Daten.** Ein Test, der ueber
`get_tolerances` die mitgelieferte Kalibrierung liest, kippt, sobald neu
kalibriert wird — obwohl die geprueften Funktionen unveraendert sind. Solche
Tests pinnen die Schwellen per Fixture. Wer die gelernten Werte pruefen will,
tut das in der Datei, die dafuer da ist.

**Isoliert vom Nutzerzustand.** `HPG_CACHE_FILE` und `HPG_TOLERANCES_FILE` auf
`tmp_path` setzen. Ein Test, der `%LOCALAPPDATA%` liest, liefert je nach
Maschine andere Ergebnisse.

## Die Fehlerklassen, die hier durchgerutscht sind

Schreib Tests, die diese fangen — sie sind alle real vorgekommen:

- Nur **einer** der beiden Analysepfade geaendert.
- **Cache-Roundtrip** nie geprueft: Feld definiert, aber nie gespeichert und
  zurueckgelesen.
- **Alt-Zeilen** ohne das neue Feld nie geprueft.
- Ein Fixture, das die **Realitaet nicht abbildet**: eine Bass-Huellkurve aus
  Einzelsample-Spitzen (1 % Belegung) statt der realen 98-100 %. Der Test war
  gruen und die Implementierung falsch, oder umgekehrt.
- Eine **Vorbedingung fehlt** und der Test prueft still nichts mehr.

## Fixtures

`tests/conftest.py` liefert Audio (`click_128bpm`, `structured_audio_128bpm`,
Akkorde), fertige Tracks (`house_track`, `dj_set_8tracks`,
`all_camelot_tracks`) und Invarianten-Helfer (`assert_mix_points_valid`,
`assert_phrase_aligned`). Mixpoint-Tests immer ueber die Helfer, nicht mit
eigenen Toleranzen.

`tests/performance_fixtures.py` liefert vor-analysierte Tracks ohne
Audio-Generierung.

## Jenseits von pytest

`e2e_check.py` prueft die Kette an echtem Audio. `tools/validation_run.py`
laeuft gegen die reale Bibliothek. `tools/prepare_dj_blind_test.py` erzeugt
anonymisierte A/B-Clips fuer Hoertests.

**Eine gruene Suite ist kein Beleg fuer musikalische Qualitaet.** Der
schwerwiegendste Fehler dieses Projekts — ein Mixpunkt, der eine ganze Phrase
zu spaet lag — hat keinen einzigen Test rot gemacht. Dafuer gibt es den
Hoertest.

## Was "fertig" heisst

1. Volle Suite gruen, Zahl **selbst gesehen**
2. Coverage-Gate 70 % gehalten
3. Bei DSP-/Analyse-Aenderungen: `e2e_check.py` auf echtem Audio
4. Bei geaendertem Analyse-Output: `CACHE_VERSION` gebumpt
5. Keine neue `UserWarning` aus `hpg_core`

Ohne Punkt 1 gibt es keine Erfolgsmeldung — auch kein "sollte gruen sein".

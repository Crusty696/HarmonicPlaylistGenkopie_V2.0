# Statischer Teilreview – keine formale Gesamtfreigabe

Der nachfolgende Originalreview behält sein tatsächliches TOR-1-Urteil MIT AUFLAGEN. Der formale Validator lehnt den TOR-2-Vertrag deshalb ab; sein Exit 1 wird nicht als Freigabe umgedeutet. Die Implementierungsauflagen wurden statisch geschlossen, die verbleibenden Ausführungsnachweise stehen im Bericht. Dieser Teilreview ersetzt keinen gültigen abschließenden Commit-Vertrag.

## Pruefvertrag

- tor: TOR 2
- auftrag: Ergänzten CSV-only-Kalibrierungs-Smoke gegen die akzeptierten TOR-1-Bedingungen prüfen.
- akzeptanzkriterien: Echter CalibrationWorker-Spawn; gültige Proposal mit fit_status="rejected"; tatsächliches Worker-Ende; eigenes Snapshot-Cleanup; unveränderte isolierte Preferences; keine zusätzlichen Audiodateien durch die CSV-Probe.
- erlaubte_dateien: hpg_core/hearing_smoke.py, tests/test_hearing_smoke.py.
- verbotene_dateien: Originalaudio, Cache, Datenbanken, Coverage, Locks, private Erinnerungen und Claude-Autopilot-Artefakte; keine Änderungen an Fit-/Analyse-/Scoring-Logik.
- referenzen: hpg_core/hearing_smoke.py:93, hpg_core/hearing_jobs.py:129, hpg_core/hearing_calibration.py:180, tests/test_hearing_smoke.py:114.
- invarianten: Bestehende Modul-/Form-/RAM-Prüfungen bleiben bestehen; kein MainWindow, keine Gewichtsübernahme, keine Produktivdateien.
- testbelege: Auftraggeber meldet RED: 1 failed mit KeyError: spawn_csv_fit, danach GREEN: 10 passed, 9.04 s, Exit 0. Nicht selbst ausgeführt oder anhand eines Laufprotokolls verifiziert.
- tor_1_urteil: MIT AUFLAGEN; Umsetzung unter ausdrücklich genannten Bedingungen akzeptiert.
- diff_bereich: WORKING TREE: gegenüber b876e59, begrenzt auf die zusätzliche CSV-Smoke-Prüfung. Beide Dateien sind derzeit untracked und wurden direkt gelesen.

## Urteil

MIT AUFLAGEN

## Vertragspruefung

- Die Umsetzung entspricht dem begrenzten Vorhaben. Die zuvor beanstandete Statusbezeichnung wurde auf den bestehenden Schemawert rejected korrigiert.
- Die Implementierungsauflagen dieser Ergänzung sind statisch geschlossen.
- Keine zusätzliche Architektur, Umbenennung oder Änderung der Fit-Verantwortlichkeit festgestellt.
- Die Testergänzung fordert den neuen Nachweis zusätzlich; vorhandene RAM- und Fingerprint-Erwartungen bleiben bestehen.
- Kein Gesamtfreigabeurteil: tatsächlicher Frozen-Nachweis und finaler Abschlusslauf bleiben offen.

## Belegmatrix

- Pruefpunkt: Echter Worker statt direktem oder simuliertem Fit | Beleg: hpg_core/hearing_smoke.py:111, hpg_core/hearing_smoke.py:121; hpg_core/hearing_jobs.py:157 | Ergebnis: erfuellt
- Pruefpunkt: Ergebnis plus tatsächliches Thread-Ende | Beleg: hpg_core/hearing_smoke.py:114, hpg_core/hearing_smoke.py:115, hpg_core/hearing_smoke.py:124 | Ergebnis: erfuellt
- Pruefpunkt: Gültige erwartete Ablehnung, keine Übernahme | Beleg: hpg_core/hearing_smoke.py:127, hpg_core/hearing_smoke.py:129, hpg_core/hearing_smoke.py:130; hpg_core/hearing_jobs.py:174 | Ergebnis: erfuellt
- Pruefpunkt: CSV-only, kein Cache und keine Source-Audios | Beleg: hpg_core/hearing_smoke.py:100, hpg_core/hearing_smoke.py:111, hpg_core/hearing_smoke.py:131, hpg_core/hearing_smoke.py:132 | Ergebnis: erfuellt
- Pruefpunkt: Cleanup-Warnung verhindert Erfolg; Snapshot-Inventar unverändert | Beleg: hpg_core/hearing_smoke.py:127, hpg_core/hearing_smoke.py:133 | Ergebnis: erfuellt
- Pruefpunkt: Isolierte Preferences vorher/nachher geprüft | Beleg: main.py:38, main.py:41; hpg_core/hearing_smoke.py:94, hpg_core/hearing_smoke.py:134 | Ergebnis: erfuellt
- Pruefpunkt: Bestehende neun Imports, Formen und RAM-Probe erhalten | Beleg: hpg_core/hearing_smoke.py:33, hpg_core/hearing_smoke.py:41, hpg_core/hearing_smoke.py:54 | Ergebnis: erfuellt
- Pruefpunkt: Source-Test verlangt neuen Nachweis zusätzlich | Beleg: tests/test_hearing_smoke.py:110, tests/test_hearing_smoke.py:114, tests/test_hearing_smoke.py:119 | Ergebnis: erfuellt

## Befunde

- keine

## Nicht geprueft

- Gemeldeter RED/GREEN-Lauf nicht unabhängig beobachtet; keine Tests gestartet.
- Tatsächliche Ausführung des ergänzten Kalibrierungs-Childs im finalen Frozen-Build.
- Finaler Fullsuite-/Coverage-Abschluss und menschliche GUI-Abnahme; nicht Teil dieser statischen Slice-Prüfung.

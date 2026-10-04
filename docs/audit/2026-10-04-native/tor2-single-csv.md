## Pruefvertrag

- tor: TOR 2
- auftrag: Unabhängige, schreibgeschützte Prüfung von McClintocks Einzel-CSV-Kompatibilität und opaker Clip-Behandlung; keine Prüfung meiner eigenen GUI-Änderungen.
- akzeptanzkriterien: Manifestloses Legacy-Einzel-CSV ohne Audioabhängigkeit; optionaler Cache mit echtem None; alte gewichte.json gebunden, niemals kopiert; clips nicht traversieren, lesen, hashen oder kopieren; unbekannte Root-Metadaten und Metadatenlinks ablehnen; Source- und Kandidatenpfade streng; bestehender CLI-Fit und Apply-Gates erhalten.
- erlaubte_dateien: hpg_core/hearing_calibration.py, hpg_core/hearing_panel.py, hpg_core/hearing_jobs.py, tests/test_hearing_calibration.py, tests/test_hearing_panel.py, tests/test_hearing_jobs.py — ausschließlich lesend.
- verbotene_dateien: Eigene main.py-/GUI-Teständerungen als Reviewgegenstand; sämtliche Schreibzugriffe und Testausführungen.
- referenzen: docs/audit/2026-10-04-native/tor1-single-csv.md:5; docs/audit/2026-10-04-native/tor1-csv-no-audio.md:5; hpg_core/hearing_calibration.py:23; hpg_core/hearing_panel.py:565; hpg_core/hearing_jobs.py:123.
- invarianten: Ausnahme nur manifestloses Einzel-CSV; kein Source-Fallback; Kandidaten benötigen Cache und Replay-Audit; keine ungefragte produktive Gewichtsübernahme.
- testbelege: Autor meldet 99 fokussierte GREEN-Tests; nicht unabhängig ausgeführt oder anhand eines Laufprotokolls bestätigt. Testcode lesend geprüft. Parent-Vollsuite 59483 laut Auftrag laufend.
- tor_1_urteil: DURCHGEWUNKEN
- diff_bereich: WORKING TREE: genannte Core-/Panel-/Worker-Dateien und zugehörige Tests gegenüber b876e5934c2601ff84f64efce661e616503e44df. Diese Dateien sind ungetrackte Neuzugänge und fehlen im Basisbaum; deshalb vollständige relevante Implementierung statt ausschließlich git-diff-Hunks geprüft.

## Urteil

MIT AUFLAGEN

Die begrenzte Implementierung erfüllt nach statischer Prüfung die beiden Verträge; kein konkreter Codebefund gefunden. Offen bleibt die Bestätigung des gemeldeten Laufzeitbelegs. Keine zusätzlichen Tests während der laufenden Parent-Suite erforderlich; deren Ergebnis beziehungsweise das fokussierte Autorprotokoll anschließend zuordnen. Keine Gesamt-/Release-Freigabe.

## Vertragspruefung

- [OBSERVATION] Der Legacy-Zweig wird ausschließlich ohne vorhandenes Source-Manifest und mit exakt erkanntem Einzel-Bewertungsschema gewählt.
- [OBSERVATION] Nullable Cache wird im Dialog und Worker ohne Stringifizierung von None weitergegeben. Ein ausdrücklich angegebener ungültiger Cache wird nicht ignoriert.
- [OBSERVATION] Die Legacy-Inventarisierung verwendet nur direkte Root-Einträge. Der Name clips wird vor Dateityp-, Link- und Fingerprintprüfungen übersprungen.
- [OBSERVATION] Alte gewichte.json ist Bestandteil der Bindung, aber von der Materialisierung ausgeschlossen. Änderungen, Erstellung oder Entfernung werden durch erneuten Snapshotvergleich erkannt.
- [OBSERVATION] Source-Manifest-Verarbeitung ruft den vollständigen Standardvalidator auf. Kandidaten bleiben an Cache, Quellen und Replay-Audit gebunden.
- [OBSERVATION] Die Berechnung delegiert an den bestehenden CLI-Fit. Einzelvorschläge erhalten keine produktiven Gate-Updates; Apply bleibt auf gatebestandene Kandidaten beschränkt.
- Historisches „unverändert“ sämtlicher Modulzweige lässt sich gegen die Basis ohne diese Dateien nicht nachweisen. Die strengen Zweige sind im aktuellen Code vorhanden.
- Keine Prüfung eigener GUI-Änderungen, keine Umbenennung bestehender Schnittstellen im geprüften Kompatibilitätsvertrag festgestellt.

## Belegmatrix

- Pruefpunkt: Manifestloses Einzel-CSV klar abgegrenzt | Beleg: hpg_core/hearing_calibration.py:30; hpg_core/hearing_calibration.py:38 | Ergebnis: erfuellt
- Pruefpunkt: Clips opak, keine rekursive Legacy-Inventarisierung | Beleg: hpg_core/hearing_calibration.py:60; hpg_core/hearing_calibration.py:64 | Ergebnis: erfuellt
- Pruefpunkt: Unbekannte Root-Metadaten und Metadatenlinks abgewiesen | Beleg: hpg_core/hearing_calibration.py:66; hpg_core/hearing_calibration.py:68 | Ergebnis: erfuellt
- Pruefpunkt: Alte Gewichte gebunden, nicht kopiert | Beleg: hpg_core/hearing_calibration.py:71; hpg_core/hearing_calibration.py:120; hpg_core/hearing_calibration.py:87 | Ergebnis: erfuellt
- Pruefpunkt: Proposal verlangt exaktes quellenloses Legacy-Inventar | Beleg: hpg_core/hearing_calibration.py:262 | Ergebnis: erfuellt
- Pruefpunkt: Echt nullable Cache und notwendiger Kandidatencache | Beleg: hpg_core/hearing_calibration.py:49; hpg_core/hearing_jobs.py:132; hpg_core/hearing_panel.py:601 | Ergebnis: erfuellt
- Pruefpunkt: Source-Validierung und Kandidaten-Audit bleiben verpflichtend | Beleg: hpg_core/hearing_calibration.py:32; hpg_core/hearing_calibration.py:175; hpg_core/hearing_calibration.py:287 | Ergebnis: erfuellt
- Pruefpunkt: Bestehender Fit, keine automatische Einzel-Übernahme | Beleg: hpg_core/hearing_calibration.py:187; hpg_core/hearing_calibration.py:294; hpg_core/hearing_calibration.py:344 | Ergebnis: erfuellt
- Pruefpunkt: Zugriffswächter und Negativfälle im Testcode vorhanden | Beleg: tests/test_hearing_calibration.py:32; tests/test_hearing_calibration.py:84; tests/test_hearing_calibration.py:96; tests/test_hearing_calibration.py:186 | Ergebnis: erfuellt
- Pruefpunkt: None-Spawn- und Dialogregressionen vorhanden | Beleg: tests/test_hearing_jobs.py:6; tests/test_hearing_panel.py:7 | Ergebnis: erfuellt
- Pruefpunkt: Gemeldeter GREEN-Lauf unabhängig bestätigt | Beleg: tests/test_hearing_jobs.py:14 beschreibt den Test, nicht dessen ausgeführten Lauf | Ergebnis: nicht erfuellt

## Befunde

- keine

## Nicht geprueft

- Ausgeführtes Ergebnis der gemeldeten 99 fokussierten Tests und der laufenden Parent-Vollsuite.
- Historischer Vorher-/Nachher-Vergleich innerhalb der ungetrackten Module.
- Eigene GUI-Integration, reale Musikqualität, Build und Release.
- Keine Tests und keine Schreibzugriffe ausgeführt.

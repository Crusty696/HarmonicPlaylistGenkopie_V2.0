## Pruefvertrag

- tor: TOR 1
- auftrag: Ergänzter Legacy-Einzel-CSV-Kompatibilitätsweg mit eigener QUALITY-Aktion; keine Veränderung des geöffneten Hörsatzes.
- akzeptanzkriterien: „Einzel-CSV auswerten“ wählt einen lokalen Ordner und startet ausschließlich den bestehenden Einzel-Fit. Exaktes Einzel-Bewertungsschema; kein Audio-Lader für Legacy-CSV-only; optionaler Cache mit echtem None; vorhandene gewichte.json binden, nicht kopieren. Source- und Kandidatenverträge bleiben streng.
- erlaubte_dateien: McClintock: hpg_core/hearing_calibration.py, hpg_core/hearing_panel.py, hpg_core/hearing_jobs.py und zugehörige Tests. Mill: main.py für Button, Signal/Wiring, neuen Slot, lokalen Directory-Override und Lifecycle-Guards sowie zugehörige GUI-Tests.
- verbotene_dateien: Andere GUI-Bereiche; Analyse-/Scoring-/Renderer-/Audit-/Fit-Algorithmik; Originalaudio, Cache-/DB-/Coverage-/Private-/Claude-Artefakte; bestehender E-Worktree. Keine Änderungen dieses Prüfers.
- referenzen: main.py:5457; main.py:5488; main.py:5965; main.py:5980; main.py:6052; main.py:6212; main.py:6313; hpg_core/hearing_panel.py:565; hpg_core/hearing_jobs.py:123; hpg_core/hearing_calibration.py:23; hpg_core/hearing_calibration.py:85; hpg_core/hearing_calibration.py:200; hpg_core/hearing_calibration.py:274; tools/rate_transitions.py:2729.
- invarianten: _hearing_set_path bleibt unverändert; bestehende Rating-/Load-/Playback-Pfade bleiben streng; Quellenlosigkeit nur beim manifestlosen Legacy-Einzelmodus; kein Source-Fallback; Kandidaten benötigen weiterhin Cache/Quellen/Audit; Einzel-Fit bleibt nicht produktiver Vorschlag.
- testbelege: TOR-1-Codeprüfung ohne Testausführung. Geplante TDD-Fälle für CSV-only-Service, echte None-Weitergabe, alte Ergebnisdatei, separate GUI-Auswahl, Schemaablehnung und Lifecycle-Sperren. Während des Parent-Volltests keine zusätzlichen Testläufe. Umsetzung und Laufzeitabnahme liegen außerhalb dieser begrenzten Vorhabenprüfung.

## Urteil

DURCHGEWUNKEN

## Vertragspruefung

- Die ausdrückliche Scope-Erweiterung schließt die zuvor offene native Auswahlmöglichkeit. Die neue Aktion ist unabhängig davon erreichbar, ob ein Hörsatz geladen ist.
- _fit_hearing_csv_set und der Directory-Override sind geplante neue Schnittstellen, keine behaupteten vorhandenen Funktionen.
- Der vorhandene _fit_hearing_set-Einstieg bleibt kompatibel; der neue Parameter soll als Keyword-only-Override ergänzt werden, beispielsweise `_fit_hearing_set(audit_only=False, *, directory=None)`.
- Der Override verwendet ausschließlich den lokalen Ordner und initial cache=None. Er überschreibt weder _hearing_set_path noch den Cachezustand des geöffneten Hörsatzes.
- Der Override lehnt andere Bewertungsschemata und audit_only=True ab. Ein vorhandenes Source-Manifest wird weiterhin vollständig geprüft und niemals durch den Legacy-Zweig umgangen.
- Die neue Schaltfläche wird in Worker-Deaktivierung und Zustandsaktualisierung aufgenommen. Auswahl und Workerstart prüfen Close-Pending, eigenen Worker, native Dialogaktivität, Remote-Server und aktiven Analyse-/Playlistlauf; nach modalen Dialogen werden die Sperren erneut geprüft.
- Mill besitzt sämtliche main.py-Änderungen; McClintock ändert dort nichts. Die Verantwortungsaufteilung ist damit ausdrücklich festgelegt.
- Nur das Vorhaben ist freigegeben. TOR 2 der Umsetzung fehlt; keine Test-, Laufzeit-, Vollparitäts- oder Release-Freigabe.

## Belegmatrix

- Pruefpunkt: Vorhandene QUALITY-Signalstruktur als Integrationsstelle | Beleg: main.py:5457 | Ergebnis: erfuellt
- Pruefpunkt: Vorhandene QUALITY-Buttonstruktur als Integrationsstelle | Beleg: main.py:5488 | Ergebnis: erfuellt
- Pruefpunkt: Vorhandenes Signal-Wiring als Integrationsstelle | Beleg: main.py:5965 | Ergebnis: erfuellt
- Pruefpunkt: Worker-Deaktivierung und Close-Pending-Startschutz vorhanden | Beleg: main.py:5980 | Ergebnis: erfuellt
- Pruefpunkt: Zustandsaktualisierung der Schaltflächen vorhanden | Beleg: main.py:6052 | Ergebnis: erfuellt
- Pruefpunkt: Auswahlguard wiederverwendbar | Beleg: main.py:6212 | Ergebnis: erfuellt
- Pruefpunkt: Bestehender Fit-Einstieg als Erweiterungsstelle vorhanden | Beleg: main.py:6313 | Ergebnis: erfuellt
- Pruefpunkt: Bestehender Kalibrierungsworker als Erweiterungsstelle vorhanden | Beleg: hpg_core/hearing_jobs.py:123 | Ergebnis: erfuellt
- Pruefpunkt: Bestehender CLI-Einzel-Fit statt neuer Algorithmik | Beleg: tools/rate_transitions.py:2729 | Ergebnis: erfuellt
- Pruefpunkt: Nullable-Binding klar abgegrenzt | Beleg: hpg_core/hearing_calibration.py:23 | Ergebnis: erfuellt
- Pruefpunkt: CSV-only-Materialisierung klar abgegrenzt | Beleg: hpg_core/hearing_calibration.py:85 | Ergebnis: erfuellt
- Pruefpunkt: Kandidaten-Audit-Sperre bleibt erhalten | Beleg: hpg_core/hearing_calibration.py:254 | Ergebnis: erfuellt
- Pruefpunkt: Apply-Sperre bleibt erhalten | Beleg: hpg_core/hearing_calibration.py:309 | Ergebnis: erfuellt

## Befunde

- keine

## Nicht geprueft

- keine

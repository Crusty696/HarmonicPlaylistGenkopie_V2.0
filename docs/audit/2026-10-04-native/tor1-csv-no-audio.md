## Pruefvertrag

- tor: TOR 1
- auftrag: Minimale Korrektur des bestätigten Legacy-Clip-Hash-Befunds; ausschließlich manifestlose Legacy-Einzel-CSV von unbenutzten Clips entkoppeln.
- akzeptanzkriterien: Nur merkmale.csv, bewertung.csv und optional gewichte.json inventarisieren und fingerprintbinden; clips-Unterbaum weder traversieren noch dessen Inhalte lesen, hashen oder kopieren; unbekannte Root-Metadaten und unzulässige Metadatenlinks weiterhin zurückweisen; Proposal-Validierung verlangt dieselbe exakte Inventarmenge; Source-Einzelmodus und Kandidaten behalten ihre vollständige Bindung.
- erlaubte_dateien: hpg_core/hearing_calibration.py, tests/test_hearing_calibration.py
- verbotene_dateien: Alle anderen Implementierungsdateien; Originalaudio, Cache, Datenbanken, Coverage, private und Claude-Artefakte sowie bestehender E-Worktree.
- referenzen: hpg_core/hearing_calibration.py:37, hpg_core/hearing_calibration.py:59, hpg_core/hearing_calibration.py:112, hpg_core/hearing_calibration.py:254
- invarianten: Ausnahme ausschließlich ohne Source-Manifest und bei exakt erkanntem Legacy-Einzelschema; keine Source-Fallbacks; alte gewichte.json bleibt gebunden, wird aber nicht übernommen; unbekannte Metadaten bleiben verboten; kein Eingriff in Fit-Algorithmus, Audit oder Apply-Gates.
- testbelege: Geplant sind Regressionen mit vorhandenen synthetischen Clips und Zugriffswächter, erfolgreichem CSV-only-Pfad sowie Ablehnung unbekannter Metadaten. Für diese Korrektur wird noch kein ausgeführter Testbeleg behauptet.

## Urteil

DURCHGEWUNKEN

## Vertragspruefung

- [INTENTION] Die vorgeschlagene Korrektur erfüllt die bereits vereinbarte TOR1-Anforderung „Legacy-CSV ohne Audiohash“ und beseitigt genau den bestätigten TOR2-Befund.
- [OBSERVATION] Der zuvor gelesene Snapshot fingerprintet Dateien rekursiv; die Materialisierung schließt Clips bereits aus. Die Korrektur betrifft daher Inventarisierung und Bindungsvalidierung, nicht Rendering oder Fit.
- Freigegeben ist dieses begrenzte Vorhaben zur Umsetzung. Das ist keine TOR2-Abnahme der anschließend geschriebenen Korrektur und keine Freigabe von Fullsuite, Build oder Release.

## Belegmatrix

- Pruefpunkt: Legacy-Einzelmodus ist separat und anhand des CSV-Schemas erkennbar | Beleg: hpg_core/hearing_calibration.py:37 | Ergebnis: erfuellt
- Pruefpunkt: Die Korrektur adressiert die bestätigte rekursive Audioabhängigkeit | Beleg: hpg_core/hearing_calibration.py:59 | Ergebnis: erfuellt
- Pruefpunkt: Clips und alte Einzelgewichte werden bereits von der Materialisierung ausgeschlossen | Beleg: hpg_core/hearing_calibration.py:112 | Ergebnis: erfuellt
- Pruefpunkt: Exakte Legacy-Inventarprüfung besitzt einen bestehenden Validierungspunkt | Beleg: hpg_core/hearing_calibration.py:254 | Ergebnis: erfuellt

## Befunde

- keine

## Nicht geprueft

- keine

## Pruefvertrag

- tor: TOR 1
- auftrag: Bestätigte Refresh-Regression durch identische Trennung von Advanced-Scoring und KI-Metadaten wie im Normalstart beheben.
- akzeptanzkriterien: Unveränderte Regression GREEN; Mapping-Kopie, striktes Boolean für `ai_enabled`, andere unbekannte Schlüssel weiterhin zurückweisen; Ownership unverändert.
- erlaubte_dateien: `main.py`, ausschließlich `_refresh_hearing_ranking`.
- verbotene_dateien: Andere Funktionen/Core-Dateien, Tests, Schemas, Gates, Audio-, Cache- und Gewichtsdateien.
- referenzen: `main.py:6420`, `main.py:6421`, `main.py:6764`, `main.py:6771`.
- invarianten: HPG-001; KI-Metadaten getrennt vom Scoring; aktuelle Strategie/BPM erhalten; keine Validator-Abschwächung.
- testbelege: Parent direkt beobachtet: 1 failed, 6 deselected, 0.74 s, Exit 1; unbekannter Schlüssel `ai_enabled`, kein Ranking-Worker. Nicht von mir erneut ausgeführt.

## Urteil

MIT AUFLAGEN

## Vertragspruefung

- **Der konkretisierte Fix ist zur Umsetzung akzeptiert.**
- `Mapping` prüfen → `deepcopy(dict(advanced_source))` → `ai_enabled` entfernen und strikt als Boolean prüfen → `StrategyConfig.from_mapping` → bereinigte Advanced-Werte und separaten KI-Metadatenschlüssel in Settings speichern → Resolver mit bereinigten Werten aufrufen.
- Diese Reihenfolge entspricht dem direkt gelesenen Normalstart-Vertrag. Andere unbekannte Schlüssel bleiben Fehler.
- Keine weitere Architektur oder zusätzliche Änderung erforderlich.

## Belegmatrix

- Pruefpunkt: Normalstart besitzt genau diese Kopie-/Validierungsfolge | Beleg: main.py:6764, main.py:6767, main.py:6768, main.py:6771 | Ergebnis: erfuellt
- Pruefpunkt: Refresh benötigt bereinigte Resolver-Eingabe | Beleg: main.py:6421 | Ergebnis: nicht erfuellt
- Pruefpunkt: Separater KI-Metadatenschlüssel entspricht Normalstart | Beleg: main.py:6800, main.py:6801 | Ergebnis: erfuellt

## Befunde

- keine

## Nicht geprueft

- Implementierungsdiff und unveränderter Regressionstest GREEN; anschließend TOR 2.
- Vollständiger positiver B-Ablauf und finale Vollsuite/Coverage.
- Erneuter Main-/Candidate-Buildbindungsnachweis nach dieser Änderung.

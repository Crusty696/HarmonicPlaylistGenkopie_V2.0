# Begrenzte Teilprüfung, keine formale Gesamtfreigabe

Das ursprüngliche TOR1-Urteil bleibt MIT AUFLAGEN. Der strikte formale Validator fordert für TOR2 ein TOR1-DURCHGEWUNKEN; diese Voraussetzung wird hier nicht rückwirkend erfunden. Der folgende unabhängige Bericht dokumentiert den tatsächlich geprüften Slice und seine Grenzen.

## Pruefvertrag

- tor: TOR 2
- auftrag: Eng begrenzten Ranking-Refresh-Fix gegen den akzeptierten TOR-1-Vertrag prüfen.
- akzeptanzkriterien: Mapping-Kopie; strikt boolesches `ai_enabled` getrennt vom Scoring; andere unbekannte Schlüssel weiterhin Fehler; unveränderte Ownership; bestehende Regression GREEN.
- erlaubte_dateien: `main.py`, ausschließlich `_refresh_hearing_ranking`.
- verbotene_dateien: Andere Core-/Test-/Schema-/Gate-Änderungen dieses Slices; Audio-, Cache- und Gewichtsdateien.
- referenzen: `main.py:6421`, `main.py:6428`, `main.py:6431`, `tests/test_hearing_end_to_end.py:17`.
- invarianten: HPG-001; aktuelle Strategie/BPM erhalten; KI nur Metadaten; Closing-/Run-/Worker-Guards unverändert.
- testbelege: Parent meldet gleicher Test RED: 1 failed/6 deselected, 0.74 s, Exit 1; GREEN: 1 passed/6 deselected, 0.78 s, Exit 0. Testcode selbst gelesen; nicht erneut ausgeführt.
- tor_1_urteil: MIT AUFLAGEN; gespeicherten Bericht direkt gelesen, nicht umdeklariert.
- diff_bereich: WORKING TREE: ausschließlich die akzeptierte Advanced-Settings-Ergänzung in `_refresh_hearing_ranking`.

## Urteil

MIT AUFLAGEN

## Vertragspruefung

- **Der Implementierungsbefund ist statisch geschlossen.** Der Fix entspricht exakt der akzeptierten Reihenfolge.
- Nur `ai_enabled` wird aus der kopierten Advanced-Map entfernt. Andere unbekannte Schlüssel werden weiterhin durch den bestehenden `StrategyConfig` abgewiesen.
- Strategie und BPM werden nicht geändert; bereinigte Advanced-Werte werden sowohl im Lauf-Snapshot als auch beim Resolver verwendet.
- Keine Umbenennung oder neue Abstraktion. Bestehende Guards, Workerstart und Ergebnisbehandlung bleiben erhalten.
- Die Regression verlangt weiterhin einen echten Playlist-Worker und ein tatsächliches Generationsergebnis; keine Erwartungsabschwächung festgestellt.

## Belegmatrix

- Pruefpunkt: Mapping geprüft und tief kopiert | Beleg: main.py:6422, main.py:6424 | Ergebnis: erfuellt
- Pruefpunkt: KI-Schlüssel separat und strikt boolesch | Beleg: main.py:6425, main.py:6426, main.py:6430 | Ergebnis: erfuellt
- Pruefpunkt: Andere unbekannte Schlüssel bleiben Fehler | Beleg: main.py:6428; hpg_core/playlist.py:172 | Ergebnis: erfuellt
- Pruefpunkt: Snapshot und Resolver erhalten dieselbe bereinigte Map | Beleg: main.py:6429, main.py:6431 | Ergebnis: erfuellt
- Pruefpunkt: Closing-/Run-Guard und Ranking-Workerzuordnung erhalten | Beleg: main.py:6415, main.py:6440, main.py:6442 | Ergebnis: erfuellt
- Pruefpunkt: Regression verlangt tatsächlichen Workerabschluss und Ergebnis | Beleg: tests/test_hearing_end_to_end.py:27, :29, :30 | Ergebnis: erfuellt

## Befunde

- keine

## Nicht geprueft

- Gemeldeter RED/GREEN-Lauf nicht unabhängig beobachtet.
- Vollständiger positiver B-Audit/Fit/Confirm-Apply/Ranking-Lauf.
- Finale Vollsuite/Coverage.
- Neuer main.py-/Candidate-Buildbindungsnachweis nach diesem Fix. Der frühere Candidate-Nachweis gilt nicht als Nachweis des aktuellen Main-Stands.
- Menschliche Workflow- und musikalische Abnahme; keine Gesamtfreigabe.

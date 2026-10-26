# STRIKTE ARBEITSANWEISUNG: AUTONOMER EXECUTION-LEITFADEN FÜR KI-AGENTEN

> **Geltungsbereich:** HarmonicPlaylistGenerator V2.0 (`C:\Users\david\Documents\HarmonicPlaylistGenerator_V2.0`)
> **Referenz-Plan:** [`specs/REKORDBOX_DEEP_ANALYSIS_INTEGRATION.md`](file:///C:/Users/david/Documents/HarmonicPlaylistGenerator_V2.0/specs/REKORDBOX_DEEP_ANALYSIS_INTEGRATION.md)
> **Modus:** 100% Autonomes Durcharbeiten, Zero Scope-Creep, Strikte Plantreue, Minimal-In-Flight-Testing

> **Vorrangige Nutzerpräzisierung vom 15.10.2026:** Zuerst alle vorgesehenen
> Implementierungsphasen fertig bauen, danach eine gebündelte Testsession.
> Die unten historisch vorgeschriebenen entwicklungsbegleitenden Smoke-, Import-,
> Unit- und Modellprobeläufe sind bis dahin ausgesetzt. Notwendiges Lesen von
> Code und Schnittstellenbefunden bleibt Teil der Implementierung. Ergebnisse
> bis zur Testsession als implementiert, ungetestet kennzeichnen. Nachtests nur
> wegen relevanter Korrekturen oder konkreter offener Nachweise. Stems und
> Embeddings waren zunächst zurückgestellt. Die spätere ausdrückliche Nutzerantwort
> „Danach ebenfalls implementieren“ beauftragt beide nach Abschluss der nativen
> Rekordbox-Anbindung. Agentenaufwand höchstens Mittel, ausschließlich normale Geschwindigkeit;
> keine Subagenten mit ausschließlich Priority-Service starten. Modellwechsel
> nur über tatsächlich verfügbare Einstellungen, keine behaupteten Umschaltungen.

---

## 1. OBERSTE VERHALTENSREGELN (HARD CONSTRAINTS)

1. **KEINE EIGENEN ERFINDUNGEN / ZERO SCOPE-CREEP:**
   - Du implementierst **ausschließlich** das, was im Plan [`specs/REKORDBOX_DEEP_ANALYSIS_INTEGRATION.md`](file:///C:/Users/david/Documents/HarmonicPlaylistGenerator_V2.0/specs/REKORDBOX_DEEP_ANALYSIS_INTEGRATION.md) explizit beschrieben ist.
   - Keine "Refactorings" bestehenden Codes, keine Umbenennungen funktionierender Methoden, keine neuen GUI-Buttons oder Menüs in `main.py`, keine Änderungen an `genres.py`.
2. **ZERO-ASSUMPTION & BELEG-PFLICHT:**
   - Erfinde keine Methodennamen oder Klassen. Wenn du dir bei einer Signatur unsicher bist: Datei im Repo lesen.
   - Nichts als "erledigt" deklarieren, was nicht im Terminal durch einen Befehl belegt wurde.
3. **HARDWARE & DEPENDENCIES:**
   - AMD RX 7800 XT DirectML: Keinerlei `torch.cuda` oder NVIDIA-Pakete installieren.
   - `numpy==1.26.4` Pin darf **niemals** auf 2.x aktualisiert werden.

---

## 2. TEST-STRATEGIE: MINIMAL WÄHREND DER ARBEIT, VOLLTEST AM SCHLUSS

Um maximale Arbeitsgeschwindigkeit ohne endlose Testschleifen zu gewährleisten:

### Während der Umsetzung (Phasen 1 bis 4):
- **VERBOTEN während der Entwicklung:**
  - Keine vollen `pytest`-Suites laufen lassen (`pytest` über das ganze Repo dauert Minuten und blockiert dich).
  - Keine manuellen Hörtests oder Audio-Renderings während kleiner Moduländerungen.
- **ERLAUBT & PFLICHT während der Entwicklung (Nur minimale Rauch-Tests):**
  - Nur ein kleiner, gezielter Import- und Funktionsaufruf pro neuem Modul (1-Zeilen Python-Command):
    ```powershell
    python -c "import hpg_core.ai_models.onnx_engine; print('OK')"
    ```
  - Nur Unit-Tests für die *neu* geschriebene Datei ausführen:
    ```powershell
    pytest tests/test_neue_datei.py
    ```

### Erst ganz am Schluss (Finale Abnahme):
- Erst wenn alle Module und Integrationsschritte fertig sind:
  1. Gezielter Test der beiden Analysepfade (Fast-Path & Vollpfad).
  2. Cache Roundtrip-Prüfung.
  3. Vollständige Test-Suite nach `AGENTS.md`.

---

## 3. SCHRITT-FÜR-SCHRITT EXECUTION-ROUTINE (AUTONOMES ARBEITEN)

Arbeite die Phasen aus dem Plan strikt nacheinander ab:

### Schritt 1: Dependencies vorbereiten
- `onnxruntime-directml` im virtuellen Environment `venv312` installieren:
  ```powershell
  & "C:\Users\david\Documents\HarmonicPlaylistGenerator_V2.0\venv312\Scripts\pip.exe" install onnxruntime-directml
  ```
- Rauch-Test: Prüfen, ob `DmlExecutionProvider` verfügbar ist:
  ```powershell
  & "C:\Users\david\Documents\HarmonicPlaylistGenerator_V2.0\venv312\Scripts\python.exe" -c "import onnxruntime as ort; print(ort.get_available_providers())"
  ```

### Schritt 2: Phase 1 – Inferenz-Modul bauen
- Erstelle `hpg_core/ai_models/onnx_engine.py` exakt nach Spezifikation Abschnitt 4 & Referenzcode Abschnitt 8.
- Provider-Reihenfolge: `DmlExecutionProvider`, Fallback `CPUExecutionProvider`.
- Minimal-Test: Modul importieren und `samplecnn.onnx` Session initialisieren.

### Schritt 3: Phase 2 – Phrasen- & Cue-Integration
- Binde `samplecnn.onnx` und `cue_prediction_model_no_abs_position.onnx` in `hpg_core/structure_analyzer.py` ein.
- Beachte die feste Eingangsgröße: 59.049 Samples bei 22.050 Hz.
- Minimal-Test: 1 Dummy-Array durch das Modell schicken.

### Schritt 4: Phase 3 – Stem-Extraktion (Demucs3 C-ABI)
- Erstelle `hpg_core/stem_analyzer.py` unter Verwendung von `ctypes` und `C:\Program Files\rekordbox\rekordbox 7.2.19\Demucs3.dll`.
- Minimal-Test: DLL laden und `demucs3IsInitialized()` abfragen.

### Schritt 5: Phase 4 – Track-Datenmodell & Cache
- Ergänze die neuen Felder in `hpg_core/models.py` (`Track`-Dataclass).
- Synchronisiere `TRACK_REQUIRED_FIELDS` und `TRACK_LIST_FIELDS` in `hpg_core/caching.py`.
- Erhöhe `CACHE_VERSION = 53`.

---

## 4. OPTIONALE WÄCHTERPRÜFUNG

Eine unabhängige Wächterprüfung kann auf Anforderung Vorhaben, Diff oder
Gesamtänderung prüfen. Sie hat keine Vorab- oder Commitgate-Funktion.
Ein Prüfvertrag kann diesen Umfang dokumentieren:

```text
## Pruefvertrag
- pruefumfang: Vorhaben | Diff | Gesamt
- auftrag: Autonome Umsetzung der Rekordbox Deep Analysis Integration (DirectML, Phrasen, Beatgrid, Stems)
- akzeptanzkriterien:
  1. onnxruntime-directml laeuft auf AMD GPU ohne Fehler (DmlExecutionProvider)
  2. Beide Analysepfade (Fast-Path und Vollpfad) erfuellen den gemeinsamen Vertrag identisch
  3. CACHE_VERSION in hpg_core/caching.py ordnungsgemaess erhoeht, Schema synchronisiert
  4. Minimale In-Flight-Tests bestanden
- erlaubte_dateien:
  - hpg_core/models.py
  - hpg_core/caching.py
  - hpg_core/analysis.py
  - hpg_core/dj_brain.py
  - hpg_core/pair_candidates.py
  - hpg_core/stem_analyzer.py (neu)
  - hpg_core/ai_models/* (neu)
  - requirements.txt
- verbotene_dateien:
  - main.py (keine ungeplanten GUI-Umbauten)
  - hpg_core/genres.py (Single Source of Truth fuer Genres bleibt unberuehrt)
- invarianten:
  - HPG-001 (Mixpoint-Konsistenz)
  - AMD DirectML-Only Constraint (kein CUDA)
  - numpy==1.26.4 Pin bleibt unangetastet
```

---

Es ist kein vorheriges Tor-1-Urteil und keine zweite Prüfung erforderlich.
Wächterbefunde sind Reviewhinweise; sie blockieren Umsetzung oder Commit nicht
automatisch. Angeforderte Korrekturen und geltende Sicherheitsregeln bleiben
maßgeblich.

## 5. ABSCHLUSS-SIGNAL
Wenn alle Schritte autonom durchgeführt wurden und die Minimal-Tests bestanden sind, melde dem Nutzer:
1. Welche Dateien erstellt und modifiziert wurden.
2. Dass die Ausführung ohne Scope-Creep exakt nach Plan erfolgt ist.
3. Den Status der finalen Verifikation.

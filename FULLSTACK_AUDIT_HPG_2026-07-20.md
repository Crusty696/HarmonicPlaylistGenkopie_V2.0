# Full-Stack-Systemaudit – Harmonic Playlist Generator V2.0

Datum: 2026-07-20  
Modus: `audit-plan`, read-only  
Ergebnis: 4 HIGH, 1 MEDIUM, 2 LOW; keine Codeänderungen im Audit

## 1. Umfang und Grenzen

Geprüft wurden die Desktop-App, der PyQt6-Einstiegspunkt, `hpg_core`, Analyse- und Worker-Pipelines, Cache/Persistenz, Playlist-Scoring, AI-Integration, Im-/Exporte, Konfiguration, Tools, Tests, Build-Konfiguration und die Verdrahtung der relevanten Call-Sites.

Inventar:

- 24 Module unter `hpg_core/`
- `main.py` als GUI-/Entry-Point mit QThread-Workern
- 56 Testdateien, 1.317 gesammelte Tests
- Python-, Konfigurations-, Dokumentations-, Build- und Tool-Dateien im Repository

Ausgeschlossen bzw. nicht verändert: Cache-/Lock-/Coverage-Dateien, Binärartefakte, Produktionsdaten und destruktive Build-/Installationsschritte. Browser-E2E ist für diese lokale PyQt6-Desktop-App nicht anwendbar. Es wurden keine echten Audioordner, Rekordbox-Produktionsdaten oder externen AI-Provider benötigt bzw. verändert.

## 2. Architektur und Datenfluss

```text
QApplication / main.py
  -> AnalysisWorker
     -> Ordner-Scan
     -> ParallelAnalyzer.analyze_files
        -> Cache-Lookup (SQLite, Cache-Version 18)
        -> Librosa-/Metadatenanalyse
     -> sanitize_playlist / validate_playlist_security
  -> PlaylistPanel / Playlist-Generierung
     -> StrategyConfig.effective_kwargs(mode)
     -> Scoring, Qualitätsmetriken, Übergangsempfehlungen
  -> optionale AI-Worker
     -> AI-Metadaten-Cache / Ollama- oder HTTP-Anbindung
  -> Exporte: M3U8 / Rekordbox XML
```

Der Produktionspfad ist grundsätzlich geschlossen: alle 24 `hpg_core`-Module importierten erfolgreich, `main.py` importierte erfolgreich, und die Vollsuite bestand. Die Befunde betreffen vor allem inkonsistente Scoring-Kontexte und kooperative Abbruch-/Lebenszyklus-Verträge.

## 3. Verifizierte Befunde

### HPG-001 – Scoring-Kontext der UI/Qualitätsanzeigen weicht vom Generierungsziel ab

Schweregrad: HIGH  
Status: bestätigt durch statische Analyse und fokussierte Laufzeitreproduktion; nicht behoben

`generate_playlist()` in `hpg_core/playlist.py:1528` verwendet die gewählten `StrategyConfig.effective_kwargs(mode)`. Nachgelagerte Pfade verwenden diese Parameter jedoch nicht konsistent:

- `compute_transition_recommendations()` ab `hpg_core/playlist.py:1148` berechnet mit Standardparametern.
- `calculate_playlist_quality()` ab `hpg_core/playlist.py:1294` berechnet mit Standard-Strictness und Standardwerten.
- Tabellen-/Reorder-Scores in `main.py:2443,2559` verwenden `calculate_enhanced_compatibility()` ohne den gewählten Scoring-Kontext.
- Qualitäts- und Empfehlungsaktualisierungen in `main.py:2589,2593,3669,3670` sowie Preview-Scores in `main.py:3907` tun dasselbe.

Reproduktion für `8A -> 12A`, 128 BPM, gleiche Energie:

```text
strictness 1  -> harmonic 84, overall 0.886640
strictness 7  -> harmonic 70, overall 0.831200
strictness 10 -> harmonic 53, overall 0.763880
UI-Default     -> harmonic 70
```

Damit kann eine Playlist unter einem anderen Optimierungsvertrag sortiert werden als dem, den Tabelle, Empfehlungen und Qualitätsanzeige darstellen. Empfohlene Folgemaßnahme: einen zentralen, unveränderlichen Scoring-Kontext durch Generierung, Reorder, Preview, Qualitätsmetriken und AI-Update reichen und eine UI-Integrationsregression ergänzen.

### HPG-002 – AI-Metadaten-Provenienz ist im Scoring nicht abgesichert

Schweregrad: HIGH  
Status: bestätigt durch statische Analyse und fokussierte Laufzeitreproduktion; nicht behoben

AI ist in `main.py:906-907` standardmäßig deaktiviert. Trotzdem berücksichtigt `hpg_core/playlist.py:157-176` nicht-leere `ai_metadata` direkt im Kompatibilitätsbonus, ohne Provenienz, Provider, Modell, Prompt oder Schema zu validieren. `ai_metadata_matches()` aus `hpg_core/ai_engine.py:37` wird nur im AI-Workerpfad (`main.py:235-236`) verwendet. Der Cache (`hpg_core/caching.py:60-70`) prüft nur, ob `ai_metadata` ein Dictionary ist.

Reproduktion:

```text
ohne ai_metadata:                         overall 0.95, ai_bonus 0.0
beliebige ai_metadata auf beiden Tracks: overall 1.00, ai_bonus 0.14
calculate_compatibility():               100
```

Die beliebigen Daten enthielten keine `_provenance`, beeinflussten aber dennoch den Score. Empfohlene Folgemaßnahme: AI-Bonus nur bei explizit aktiviertem, aktuell validiertem Provider/Modell/Schema gewähren; andernfalls Bonus deterministisch auf null setzen. Regression für stale/ungültige Cache-Daten ergänzen.

### HPG-003 – Abbruch der sekundären AI-Worker ist nicht kooperativ implementiert

Schweregrad: HIGH  
Status: bestätigt statisch; kein Live-Close-Test gegen externe AI-Dienste

`main.py:267` führt in `AIDetectWorker` einen Launcher-Aufruf ohne Unterbrechungsprüfung aus. `AITestWorker` (`main.py:291`) blockiert bei `requests.post(..., timeout=(3,30))`; `AIPullWorker` (`main.py:341`) kann beim Ollama-Pull bis zu 1.800 Sekunden blockieren. `closeEvent()` (`main.py:3951-3967`) ruft zwar `requestInterruption()` auf, wartet aber nicht auf das Ende dieser Worker.

Qt dokumentiert `requestInterruption()` als lediglich beratend: laufender Code muss `isInterruptionRequested()` selbst prüfen; für Synchronisierung ist `wait()` vorgesehen. Quelle: [Qt QThread-Dokumentation](https://doc.qt.io/qt-6.8/qthread.html).

Risiko: App-Schließen kann verzögert werden oder zu einem QThread-Lebenszyklusfehler führen. Empfohlene Folgemaßnahme: kooperative Checks an Subprozess-/Netzwerkgrenzen, terminate-fähige Prozesse, ein gemeinsames Pending-Worker-Tracking und explizites Warten vor `closeEvent`-Akzeptanz.

### HPG-004 – Timeout/Cancel des Transition-Preview-Workers beendet den Prozess nicht

Schweregrad: HIGH  
Status: bestätigt statisch; Timeout-/Close-Reproduktion mit echtem Renderprozess nicht ausgeführt

`TransitionRenderWorker` (`main.py:520-609`) setzt bei `request_cancel()` nur ein Flag, das zwischen Übergängen geprüft wird (`main.py:539,550`). Ein `ProcessPoolExecutor(max_workers=1)` wird als Context Manager erzeugt (`main.py:593`), und `future.result(timeout=60.0)` (`main.py:596`) meldet einen Timeout, beendet den Child-Prozess aber nicht. Beim Verlassen des Context Managers erfolgt weiterhin ein Shutdown mit Warten.

Die Python-Dokumentation beschreibt für den Executor-Context Manager ein Shutdown-Verhalten mit Warten wie bei `shutdown(wait=True)`. Quelle: [Python concurrent.futures-Dokumentation](https://docs.python.org/3/library/concurrent.futures.html).

Zusätzlich nimmt `closeEvent()` den Preview-Worker nicht in das allgemeine `running_workers`-Tracking auf. Empfohlene Folgemaßnahme: Executor-Lebensdauer selbst verwalten, bei Timeout/Cancel Futures abbrechen und Child-Prozesse terminieren, Preview-Worker in den Close-Lifecycle aufnehmen und Timeout/Cancel/Close testen.

### HPG-005 – Produktionsdokumentation ist gegenüber dem Quellstand veraltet

Schweregrad: MEDIUM  
Status: bestätigt durch Quell-/Dokumentvergleich; nicht behoben

`PRODUCTION_STATUS.md:21` nennt Cache-Version 14, der Code (`hpg_core/caching.py:28`) verwendet Version 18. `PRODUCTION_STATUS.md:23` nennt 11 Strategien, der aktuelle `STRATEGIES`-Katalog enthält 8. Außerdem werden in `PRODUCTION_STATUS.md:35-36` bereits konsolidierte Mixpoint-/Strategiearbeiten noch als offen geführt. `PRODUCTION_README.md` nennt ebenfalls Python 3.10–3.12 und 11 Modi, während `hpg_core/app_metadata.py` Python 3.12.1 und der Quellkatalog 8 Strategien ausweisen.

Empfohlene Folgemaßnahme: Snapshot-Dokumente klar als historisch markieren oder die autoritativen Produktionsdokumente aktualisieren.

### HPG-006 – Tote bzw. irreführende Hilfsartefakte

Schweregrad: LOW  
Status: statisch bestätigt; nicht entfernt, da Audit read-only und Dateien user-owned sind

- `hpg_core/config.py:136`: `AI_MODELS_AVAILABLE = []` hat keine Produktionsreferenzen.
- `main.py:3995`: No-op-`pass` im `__main__`-Block.
- `tools/_inspect_cache.py:12-14`: veralteter Shelve-Pfad `hpg_cache_v10.dbm`; der aktuelle Cache ist SQLite v18. Das Tool wurde nicht ausgeführt, um keinen veralteten Cache anzulegen oder zu verändern.
- Alte Root-Cache-Artefakte v14–v17 sind Integritäts-seitig lesbar, werden vom aktuellen Defaultpfad unter `%LOCALAPPDATA%\HPG\hpg_cache_v18.db` aber nicht verwendet.

Empfohlene Folgemaßnahme: unreferenzierte Konstante/No-op bereinigen und das alte Cache-Inspektionstool entweder entfernen oder auf den aktuellen Cache-Reader umstellen. Vor einer Entfernung ist die Eigentümerschaft zu bestätigen.

### HPG-007 – Direkte Laufzeitabhängigkeit `requests` fehlt in der Deklaration

Schweregrad: LOW  
Status: Packaging-Risiko bestätigt; aktuelles Environment funktioniert

`hpg_core/ai_engine.py:1`, `hpg_core/ai_launcher.py:23` und `main.py:305` importieren `requests`, `requirements.txt` deklariert es jedoch nicht direkt. Im vorhandenen Environment kommt es transitiv über `pooch`; `pip check` meldete keine kaputten Requirements. Eine saubere Installation kann den optionalen AI-Testpfad deshalb trotzdem ohne `requests` vorfinden.

Empfohlene Folgemaßnahme: die direkte Abhängigkeit in der Projekt-/Packaging-Metadatenquelle deklarieren, optional mit AI-Extra. Die Python Packaging Authority beschreibt `dependencies` als die erwarteten Installationsabhängigkeiten und `optional-dependencies` als Extras: [PyPA pyproject.toml specification](https://packaging.python.org/en/latest/specifications/pyproject-toml/).

## 4. Verifikation

Ausgeführt im vorhandenen Python-3.12-Environment:

```text
pytest --tb=short -q                 1317 passed, 26 warnings
Coverage                             76.80% (6694 statements, 1553 missed)
compileall main.py hpg_core tests tools erfolgreich
Import main.py                       IMPORT_MAIN_OK
Import aller 24 hpg_core-Module      FAILED []
Ruff F401/F821/F823/F841             All checks passed
pip check                            No broken requirements found
git diff --check                     erfolgreich
SQLite-Cacheintegrität               ok; Cache-Version 18
```

Ruff meldet zusätzlich 22 `E402`-Stellen in `main.py`. Diese folgen der absichtlichen Struktur, `multiprocessing.freeze_support()` vor Qt-/Audioimporten auszuführen, und wurden nicht als Befund gewertet.

Nicht ausgeführt: destruktiver PyInstaller-/Installer-Build, echter Audio-Korpuslauf, echtes Rekordbox-Datenbank-Import-Szenario, externe AI-Endpunkte sowie GUI-Close-Reproduktion unter blockierendem Netzwerk-/Render-Workload.

## 5. Gegenprüfung und Unsicherheit

Der Audit wurde in zwei Lesepässen durchgeführt: Architektur-/Datenflussprüfung sowie Call-Site-/Fehlerpfad-/Dead-Code-Prüfung. Die Befunde HPG-001 und HPG-002 wurden mit kleinen fokussierten Laufzeitreproduktionen abgesichert; HPG-003 und HPG-004 sind aus dem Quellvertrag und den offiziellen Laufzeitdokumentationen abgeleitet, aber nicht gegen externe/blockierende Live-Workloads ausgeführt.

Claude Code war in dieser Umgebung nicht authentifiziert; AGY startete nur einen interaktiven Lauf ohne verwertbaren Befund. Daher wurden keine externen Agentenaussagen als Evidenz verwendet. Die lokale Codebasis, Tests und Primärdokumentationen sind die maßgebliche Grundlage.

## 6. Priorisierte nächste Schritte

1. HPG-001: Scoring-Kontext zentralisieren und UI-Integrationsregression ergänzen.
2. HPG-002: AI-Provenienz und expliziten Aktivierungskontext in den Bonuspfad erzwingen.
3. HPG-003/004: kooperatives Canceln, terminierbare Child-Prozesse und sicheren Close-Lifecycle implementieren.
4. HPG-005: Produktionsdokumentation auf Cache-Version, Python-Mindestversion und Strategiekatalog synchronisieren.
5. HPG-006/007: tote Hilfsartefakte bereinigen und direkte AI-Abhängigkeit deklarieren.

Dieser Bericht enthält Diagnose und Priorisierung. Die vier HIGH-Befunde sollten vor einem produktiven Release behoben und mit Regressionstests verifiziert werden.

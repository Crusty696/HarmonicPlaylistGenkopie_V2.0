# AGENTS.md

## Verbindliche Erfolgsnachweise (Nutzerauftrag 2026-10-04)

Diese Regeln verhindern unbelegte Erfolgszusagen. Sie beschreiben Pflichten,
nicht bereits erfuellte Nachweise. Bestehende Sicherheits- und Pruefregeln
bleiben wirksam.

1. Nutzeranforderungen in pruefbare Akzeptanzkriterien und geeignete
   Regressionstests uebertragen. Unbekannte Vocals duerfen allein kein Paar
   sperren. Originalmusik nur am Quellort lesend analysieren und abspielen:
   niemals kopieren, verschieben, umbenennen, loeschen oder in Projekt, Git
   bzw. Sicherungen aufnehmen.
2. Den betroffenen nativen Benutzerablauf nachweisen: Originaltracks
   auswaehlen, frisch analysieren, Paare bewerten, Playlist erstellen und
   Ergebnisse direkt in der App verwenden. Einzelne Werkzeug-, DSP- und
   Mock-Tests ersetzen diesen Nachweis nicht. Fehlende Schritte offen nennen.
3. Frische Analyse mit isoliertem Testzustand und Cache-Wiederverwendung
   getrennt pruefen und berichten. Produktivcache nicht fuer Tests loeschen
   oder veraendern. Ein Cache-Erfolg beweist keinen erfolgreichen Erstlauf.
4. Genau die auszuliefernde bzw. gestartete Version pruefen. Eine EXE durch
   absoluten Pfad und SHA-256 dem geprueften Build zuordnen. Quellcode-Test,
   Build-Erfolg und erfolgreicher EXE-Lauf sind getrennte Nachweise.
5. Status getrennt melden: implementiert; automatisch getestet; mit
   Originaltracks im vollstaendigen Ablauf geprueft; musikalisch bewertet.
   Kein Status impliziert den naechsten. Absicht, Laufzeitbeobachtung und
   ausgefuehrten Nachweis unterscheiden. Historische Tests sind keine aktuelle
   Abnahme. Ohne erforderliche Nachweise kein pauschales "alles funktioniert".
6. Reproduzierbare Fehler durch Regression absichern: Fehler vor Korrektur
   nachweisen, denselben Test nach Korrektur bestehen lassen. Erwartungen
   nicht abschwaechen, ausser bei ausdruecklich geaendertem Nutzervertrag mit
   dokumentierter Begruendung. Wo automatisierte Reproduktion nicht moeglich
   ist, Einschraenkung und konkreten Diagnosebeleg nennen; kein RED/GREEN
   erfinden.

Bereits autorisierte sichere Schritte autonom ausfuehren, ohne zusaetzliche
routinemaessige Nutzerfreigaberunden. Dies hebt notwendige Sicherheits- und
Scope-Rueckfragen sowie unabhaengige Pruefungen nicht auf. Keine absolute
Fehlerfreiheit und keine ungepruefte musikalische Optimalitaet versprechen.

## Keine unnoetigen Wiederholungen (Nutzerauftrag 2026-10-04)

Bereits korrekt erledigte Arbeit und gueltige bestandene Pruefungen werden
weiterverwendet. Kosten, Tokens und Zeit sind bei der Arbeitsplanung zu
beruecksichtigen. Vor jedem erneuten Lauf vorhandene Ergebnisse lesen und
deren Geltungsbereich pruefen: relevante Quell-, Test- und Build-Hashes,
Eingaben, Umgebung, Befehl, Ergebnis und bekannte Einschraenkungen.

- Jeder erneute Lauf braucht einen konkreten Grund: relevante Aenderung,
  beobachteter Fehler oder fehlender Nachweis. Grund und kleinsten geeigneten
  Pruefumfang vor Start festhalten. Kein Wiederholen allein wegen einer
  Zusammenfassung, eines Agentenwechsels oder eines neuen Statusberichts.
- Ein verantwortlicher Agent koordiniert jeden teuren Lauf. Waehrend eines
  codegebundenen Langtests werden dessen relevante Dateien nicht geaendert.
  Parallel nur unabhaengige Arbeit; keine doppelten Test-/Build-Auftraege.
- Testerwartungen vor teuren Laeufen gegen den vereinbarten Vertrag pruefen.
  Ein neuberechneter Score erzwingt beispielsweise keinen Reihenfolgewechsel.
- Reine Dokumentationsaenderungen erfordern keinen neuen Build, Volltest oder
  Audioanalyselauf. Nur betroffene Nachweise bei relevanter Aenderung erneuern.
- Bei ausschliesslich begruendeten Korrekturen veralteter Testerwartungen und
  unveraendertem Produktcode, Abhaengigkeiten sowie relevanter Testumgebung
  genuegen die betroffenen Nachtests. Bestandene unveraenderte Faelle bleiben
  als Nachweise erhalten. Test-/Fixture-Aenderungen mit weiteren Auswirkungen
  erfordern entsprechend breitere Nachtests.
- Einen fehlgeschlagenen Volllauf stets als solchen dokumentieren, danach
  gezielte Nachtests separat nennen. Daraus keinen gruenen Volllauf erfinden.
  Quellcode-, Build-, App-Ablauf- und musikalische Nachweise bleiben getrennt.

## OpenClaw-Hochpraezisionsmodus

Dieser Ordner ist der Workspace des OpenClaw-Agenten `hpg`. Arbeite nur an
dem vom Auftrag betroffenen Teil des Repositories. `Claude-Autopilot-v5/`,
`Claude-Autopilot-v6/` und `Claude-Autopilot-v6.zip` sind bestehende,
ungetrackte Benutzerartefakte: nie aendern, verschieben, stagen oder in einen
Commit aufnehmen.

Vor jeder nichttrivialen Aenderung zuerst `hpg-orientation` und danach den
passenden HPG-Skill laden. Die Fachrollen liegen unter `.agents/agents/`:

- Audio/Analyse: `hpg-analyse`; Mixpunkte/Paarung: `hpg-mixpoints`;
  Scoring/Strategien: `hpg-scoring`; Cache: `hpg-cache`.
- PyQt6 und `main.py`: `hpg-gui`; Rekordbox: `hpg-rekordbox`; Rendering:
  `hpg-render`; Tests: `hpg-tests`; Messung/Statistik: `hpg-statistik`.
- Vor der Umsetzung und vor jedem Commit muss ein unabhaengiger,
  schreibgeschuetzter Pruefdurchgang nach `.agents/agents/hpg-waechter.md`
  erfolgen. Sein Urteil ist DURCHGEWUNKEN, MIT AUFLAGEN oder
  ZURUECKGEWIESEN.

Parallelisiere nur voneinander unabhaengige Recherche-, Review- oder
Testvorbereitung. Starte nie zwei volle pytest-Laeufe gleichzeitig: `pytest`
nutzt bereits `-n auto`. Fuer Abschlussbelege immer
`venv312\Scripts\python.exe -m pytest tests/ --tb=short -q` verwenden;
`--no-cov` ist nur fuer den lokalen Entwicklungszyklus erlaubt.
Die oben genannte direkte Nutzerregel praezisiert diese Vorgabe: Ein bereits
vorliegender Volllauf wird fuer reine Dokumentationsaenderungen oder die dort
beschriebenen isolierten Erwartungskorrekturen nicht wiederholt. Gezielt mit
`--no-cov` nachgepruefte Faelle werden getrennt vom vorhandenen Volllauf und
dessen Coverage ausgewiesen.

Bei Analyse-, Mixpoint-, Cache-, Genre- oder GUI-Aenderungen die in den
Fach-Skills definierten Invarianten explizit pruefen. Kein Abschluss ohne
Testbeleg, keine unbelegte Erfolgsmeldung, keine Aenderung von Cache-,
Datenbank-, Lock- oder Coverage-Dateien.

This file provides guidance to Codex when working with code in this repository.

# HPG - Harmonic Playlist Generator (v3.7.2)

## Projekt-Skills zuerst laden

Fuer dieses Repo existieren projekt-lokale Experten-Skills mit dem
verifizierten Ist-Stand. Sie liegen unter `.claude/skills/` (Claude Code)
bzw. `.agents/skills/` (Codex). Bei HPG-Arbeit zuerst `hpg-orientation`
laden, danach den fachlich passenden Skill:

`hpg-orientation`, `hpg-debugging`, `hpg-audio-analysis`,
`hpg-mixpoint-engineering`, `hpg-playlist-scoring`, `hpg-genres`,
`hpg-cache-persistence`, `hpg-parallel-performance`, `hpg-qt-gui`,
`hpg-transition-render`, `hpg-rekordbox`, `hpg-testing-verification`,
`hpg-release-build`, `hpg-audit-optimize`.

Regel: Statusdokumente sind Hypothesen, der Code ist die Wahrheit. Jede
Behauptung aus einem Markdown vor Gebrauch im Code nachpruefen.

## Projektarchitektur

```
main.py                    # PyQt6 GUI, QThread-Worker-Muster
hpg_core/                  # Core analysis modules
  models.py                # Track-Dataclass, Camelot-Map, TrackSection
  analysis.py              # Audio-Analyse (librosa): BPM, Key, Energy, Sections
  downbeat.py              # Downbeat- und Phrasen-Anker
  config.py                # Alle konfigurierbaren Konstanten
  genres.py                # Single Source of Truth: 9 kanonische Genres + Drift-Validierung
  caching.py               # SQLite-Cache (WAL), CACHE_VERSION 45
  parallel_analyzer.py     # ProcessPoolExecutor fuer Multi-Core Analyse
  genre_classifier.py      # Genre-Erkennung (regelbasiert, kein ML)
  structure_analyzer.py    # Track-Struktur (Intro/Breakdown/Drop/Outro)
  dj_brain.py              # Genre-spezifische Mix-Logik, Mixpoints
  playlist.py              # Playlist-Generierung und Scoring (STRATEGIES)
  transition_renderer.py   # Uebergangs-Preview (Crossfade, EQ, Limiter)
  rekordbox_importer.py    # Rekordbox-Datenbank Import (optional)
  ai_engine.py             # Optionales lokales LLM (nur Mood/Subgenre, kein Audio)
  ai_launcher.py           # Erkennung/Start von Ollama bzw. LM Studio
  theme.py                 # Farben und Styles der GUI
  playlist_security.py     # Pfad-Sanitizing und Playlist-Validierung
  resource_limits.py       # Groessen-/Dauer-/Anzahl-Limits
  error_reporter.py        # JSON-Fehlersenke logs/error_report.json
  logging_config.py        # Logging-Setup
  app_metadata.py          # APP_VERSION, MIN_PYTHON (Single Source)
  exporters/               # m3u8, Rekordbox XML Export
tests/                     # pytest (Anzahl/Coverage selbst messen)
tools/                     # Hilfsskripte (Manual Test, Genre Check, Cache Inspection)
docs/                      # Dokumentationen, Algorithmus-Erklaerungen, Quick-Start
docs/PROJECT_KNOWLEDGE.md  # Quellenwegweiser und konsolidierte Nutzervertraege
```

Es gibt kein `ui/`-Paket, keinen `GUI/`-Ordner und kein `theme.py` im
Wurzelverzeichnis — die gesamte GUI liegt in `main.py`, das Theme in
`hpg_core/theme.py`.

## Playlist-Strategien

Genau 8, registriert in `hpg_core/playlist.py` (`STRATEGIES`):
Harmonic Flow, Warm-Up, Cool-Down, Peak-Time, Energy Wave, Genre Flow,
Consistent, Context Flow. GUI-Default: Harmonic Flow.

Drei Altnamen bleiben ueber `STRATEGY_ALIASES` gueltig (gespeicherte
Settings, Cache-Metadaten): "Harmonic Flow Enhanced" -> Harmonic Flow,
"Peak-Time Enhanced" -> Peak-Time, "Emotional Journey" -> Context Flow.

## Python-Pfad (WICHTIG!)

- Python 3.12 zwingend, mindestens 3.12.1 (`MIN_PYTHON` in
  `hpg_core/app_metadata.py`). Kein 3.13+ — numba unterstuetzt es nicht.
- Projekt-venv: `.\venv312\Scripts\python.exe` (aktuell Python 3.12.10).

## Tests ausfuehren

```bash
.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q
```

`pytest.ini` setzt bereits `-n auto`, Coverage auf `hpg_core` und `main`
sowie `--cov-fail-under=70`. Fuer schnelle Laeufe `--no-cov` anhaengen.

## Coding-Konventionen

- Einrueckung: die des bearbeiteten Files fortsetzen. `main.py`,
  `hpg_core/analysis.py` und `hpg_core/playlist.py` nutzen 4 Leerzeichen,
  neuere Dateien wie `hpg_core/theme.py` und neuere Tests 2. Keine Tabs.
- Kommentare auf **Deutsch**
- UI-Updates NUR im Main-Thread
- Hilfsskripte aus `tools/` muessen den Parent-Pfad zu `sys.path` hinzufuegen

## Geschuetzte Dateien (NICHT editieren)

- `hpg_cache_v*.db`, `*.db-wal`, `*.db-shm`, `*.lock`, `*.coverage` —
  Cache-/System-Dateien. Der Laufzeit-Cache liegt ausserhalb des Repos unter
  `%LOCALAPPDATA%\HPG\hpg_cache_v45.db` (ueberschreibbar mit `HPG_CACHE_DIR`
  bzw. `HPG_CACHE_FILE`).

## Analyse-Pipeline

1. **Cache-Lookup** (Rekordbox-Signatur -> Cache-Key) — passiert **vor** der Analyse.
2. **Rekordbox Fast-Path**: Nutzt existierende Metadaten (BPM/Key/Beatgrid).
3. **Vollstaendige Librosa-Analyse**: Volle Audio-Analyse falls Metadaten fehlen.
4. Downbeat -> Phrasen-Anker -> Struktur -> Mixpoints entstehen innerhalb von
   `analyze_track`, nicht in einem spaeteren Schritt.

## Wissensquellen nach Bereinigung 2026-10-04

Zuerst `docs/PROJECT_KNOWLEDGE.md` und den aktuellen Auftrag lesen. Historische
Session-Auftraege niemals automatisch fortsetzen. Generierte Erinnerungen
und alte Testzahlen sind keine aktuelle Abnahme. Veraltete Quellen erst nach
Erkenntnisextraktion entfernen; keine neuen parallelen Statuskopien erzeugen.

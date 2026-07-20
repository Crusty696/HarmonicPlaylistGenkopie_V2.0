# HPG — Produktionsstatus

Stand: 2026-07-20 (nach Fullstack-Audit; Details: FULLSTACK_AUDIT_HPG_2026-07-20.md,
davor Doppel-Audit b5056a9 + Altlasten-Bereinigung, docs/AUDIT_BERICHT_2026-07-17.md)

## Umgebung (verbindlich)

- **Python 3.12** zwingend (numba braucht <3.13). Projekt-venv: `venv312\`
- Tests: `& '.\venv312\Scripts\python.exe' -m pytest tests/ --no-cov -q`
- Baseline: **1317 Tests grün** (verifiziert 2026-07-20)
- Das alte defekte `venv\` (Python 3.14) wurde 2026-07-17 geloescht
- Build: `build.bat` (findet Python 3.12 automatisch, nutzt venv312)
- Python-Basis: **3.12.10** (2026-07-16 aktualisiert; 3.12.0 hatte einen
  CPython-Bug, der scipy.stats im PyInstaller-Build crashte, pyinstaller#8186 —
  seit dem Update kein Workaround mehr nötig, scipy läuft unverändert)

## Aktiver Funktionsumfang

- **Mixpoint-Engine**: sektions-/phrasenbasiert, genre-aware (dj_brain), auf echter
  DJ-Praxis kalibriert (Techno 16-32 Bars, Trance 32-64, Psytrance 16er-Phrasen).
  LLM-Mixpoints und Rekordbox-Cues werden phrase-quantisiert. Cache-Version 18.
  Transition-Preview mit Beat-Phase-Alignment.
- **8 Playlist-Strategien** (Harmonic Flow, Warm-Up, Cool-Down, Peak-Time,
  Energy Wave, Genre Flow, Consistent, Context Flow — Set-Phasen-Zielenergie,
  Trend-Fortführung, Genre-Fatigue, Repetition-/Cliff-Penalties)
- **Security-Gate** (aktiv verdrahtet in AnalysisWorker): sanitize + validate,
  Limits aus config (500 MB/Datei, 2 h/Track, 1000 Tracks), UI-Feedback bei Filterung
- **ErrorReporter** (aktiv): JSON-Sink `logs/error_report.json`, Rotation 200 Einträge,
  angebunden an Analyse-, Playlist- und Render-Fehlerpfade
- **Transition-Preview**: Subprocess-isoliert (C-Crash-sicher), Crossfade bis 64 s,
  Half/Double-Erkennung mit 4%-Toleranz
- **Export**: m3u8 + Rekordbox XML (Folder/Playlist-Anlage gefixt)

## Bekannte offene Punkte

Siehe FULLSTACK_AUDIT_HPG_2026-07-20.md. Die früher hier gelisteten Punkte
(Mixpoint-Konsolidierung, Strategien-Konsolidierung 11 → 8) sind erledigt.

## Historie

Die frühere "Intelligent Scoring"-Schicht (7 Module) war nie verdrahtet und wurde
2026-07-16 entfernt; ihre 4 wertvollen Konzepte leben in der Context-Flow-Strategie
weiter (Details: Commit a2991bf).

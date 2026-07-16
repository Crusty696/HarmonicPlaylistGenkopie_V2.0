# HPG — Produktionsstatus

Stand: 2026-07-16 (nach Vollaudit + Fix-Runden, Commits 9b64953/3a4ccf4/a2991bf)

## Umgebung (verbindlich)

- **Python 3.12** zwingend (numba braucht <3.13). Projekt-venv: `venv312\`
- Tests: `& '.\venv312\Scripts\python.exe' -m pytest tests/ --no-cov -q`
- Baseline: **1241 Tests grün**
- `venv\` (Python 3.14) ist defekt und gitignored — nicht verwenden
- Build: `build.bat` (findet Python 3.12 automatisch, nutzt venv312)
- **Achtung Python 3.12.0**: CPython-Bug crasht scipy.stats im PyInstaller-Build
  (NameError 'obj', pyinstaller#8186). Workaround im venv312 gepatcht
  (`_distn_infrastructure.py`: `globals().pop('obj', None)`), Details im
  HPG.spec-Kommentar. Sauberste Lösung: Python auf ≥3.12.1 aktualisieren.

## Aktiver Funktionsumfang

- **Mixpoint-Engine**: sektions-/phrasenbasiert, genre-aware (dj_brain), auf echter
  DJ-Praxis kalibriert (Techno 16-32 Bars, Trance 32-64, Psytrance 16er-Phrasen).
  LLM-Mixpoints werden phrase-quantisiert. Cache-Version 12.
- **11 Playlist-Strategien** inkl. neu: **Context Flow** (Set-Phasen-Zielenergie,
  Trend-Fortführung, Genre-Fatigue, Repetition-/Cliff-Penalties)
- **Security-Gate** (aktiv verdrahtet in AnalysisWorker): sanitize + validate,
  Limits aus config (500 MB/Datei, 2 h/Track, 1000 Tracks), UI-Feedback bei Filterung
- **ErrorReporter** (aktiv): JSON-Sink `logs/error_report.json`, Rotation 200 Einträge,
  angebunden an Analyse-, Playlist- und Render-Fehlerpfade
- **Transition-Preview**: Subprocess-isoliert (C-Crash-sicher), Crossfade bis 64 s,
  Half/Double-Erkennung mit 4%-Toleranz
- **Export**: m3u8 + Rekordbox XML (Folder/Playlist-Anlage gefixt)

## Bekannte offene Punkte

Siehe `.claude/skills/hpg-audit-optimize/SKILL.md`:
- Mixpoint-Logik-Duplikat (analysis.py-Fallback vs. dj_brain) — Konsolidierung geplant
- `harmonic_strictness` wirkt nur im Fallback-Zweig

## Historie

Die frühere "Intelligent Scoring"-Schicht (7 Module) war nie verdrahtet und wurde
2026-07-16 entfernt; ihre 4 wertvollen Konzepte leben in der Context-Flow-Strategie
weiter (Details: Commit a2991bf).

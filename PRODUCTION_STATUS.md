# HPG — Produktionsstatus

Aktueller technischer Arbeitsstand: 2026-08-31, verifizierter uncommitteter
Code-Stand auf Commit `3c59dc8` von `origin/main`. Der lokale Code-Gate ist
gruen; Installer- und CI-Gates sind erst nach dem naechsten Push erneut zu
verifizieren. Die vollstaendige
Bibliotheksanalyse und der neue 30-Paar-Hoertestsatz bleiben auf
Nutzeranweisung pausiert. Abnahmen vom 2026-07-26 sowie Messungen vom
2026-08-14 und 2026-08-25 bleiben unten als historische Snapshots erhalten.

## Umgebung (verbindlich)

- **Python 3.12** zwingend (numba braucht <3.13). Projekt-venv: `venv312\`
- Abschluss-Gate: `& '.\venv312\Scripts\python.exe' -m pytest tests/ --tb=short -q`
- Lokaler Standard-Abschlusslauf: **3537 Tests gruen**, **85,81 % Coverage**
  (2026-08-31, isolierter Windows-Basetemp)
- GitHub Actions Lauf 33113355362 auf `3c59dc8`: **3522 Tests gruen**, 46
  Slow-Tests abgewählt, **85,77 % Coverage**; Installer-Smoke ebenfalls gruen
- Das alte defekte `venv\` (Python 3.14) wurde 2026-07-17 geloescht
- Build: `build.bat` (findet Python 3.12 automatisch, nutzt venv312)
- Python-Basis: **3.12.10** (2026-07-16 aktualisiert; 3.12.0 hatte einen
  CPython-Bug, der scipy.stats im PyInstaller-Build crashte, pyinstaller#8186 —
  seit dem Update kein Workaround mehr nötig, scipy läuft unverändert)

## Aktiver Funktionsumfang

- **Mixpoint-Engine**: sektions-/phrasenbasiert, genre-aware (dj_brain), auf echter
  DJ-Praxis kalibriert (Techno 16-32 Bars, Trance 32-64, Psytrance 16er-Phrasen).
  LLM-Mixpoints sind rein advisory und schreiben keine Track-Mixpoints;
  Rekordbox-Cues werden phrase-quantisiert und gegen die framegenaue echte
  Audiodauer geprueft. Cache-Version 44;
  `-1.0` ist der Nicht-gesetzt-Sentinel, `0.0` ein gueltiger Mix-In.
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

## Letzter Volltest-Snapshot: Messung 2026-08-25

Selbst gemessen mit dem Abschluss-Gate:

- **2035 passed**, 25 Warnungen
- Coverage gesamt: **81,65 %** — das Gate `--cov-fail-under=70` ist erfuellt
- `main.py`: **5752 Zeilen**
- **8** Strategien, **3** Strategie-Aliase, **9** kanonische Genres
- `CACHE_VERSION = 37`, Python 3.12.10 im `venv312`

## Historischer Snapshot: Messung 2026-08-14

Selbst gemessen mit `.\venv312\Scripts\python.exe -m pytest`:

- Volllauf mit Coverage (`-m ""`): **1471 passed**, 26 Warnungen, **164 s**
- Coverage gesamt: **75,49 %** — das Gate `--cov-fail-under=70` ist erfüllt
- Standardlauf (langsame Tests abgewählt): rund 1282 Tests in ~85 s, 73,5 %
- Weitere gemessene Fakten: `main.py` 4944 Zeilen, 8 Strategien in
  `STRATEGIES`, 3 Einträge in `STRATEGY_ALIASES`, 9 kanonische Genres,
  `CACHE_VERSION = 28`, Python 3.12.10 im `venv312`

Hinweis zu einer früheren Zwischenmessung in dieser Sitzung: Zwischenstände
mit 66,82 % Coverage und einem `NameError: ExportReport` in
`tests/test_main_workers.py` entstanden, während mehrere Agenten dieselben
Dateien gleichzeitig umschrieben. Beide sind am fertigen Stand widerlegt —
nachgemessen: Gate erfüllt, Suite vollständig grün.

## Offene Punkte

- Die vollstaendige 3666-Track-Analyse ist pausiert. Ein spaeter freigegebener
  Lauf muss mit einem neuen isolierten v44-Arbeitscache beginnen; historische
  v37-v43-Artefakte werden nicht fortgesetzt.
- Danach bleiben der neue 30-Paar-Kandidatensatz, der strikte PCM-/Kick-Audit
  und ein reales Render-E2E auf diesem Satz auszufuehren.
- Eine subjektive Langzeit-Hörsession bleibt optional und ist als
  Produktkalibrierung nicht vollständig automatisierbar.

## Abschlussverifikation 2026-07-26

- Volltest mit vier Workern: **1384 passed** in 305,90 s
- Coverage-Gate: **74,18 %**, Mindestwert 70 %
- Verify-Suiten: **14/14**, **17/17**, **8/8**
- E2E: **17/17** mit drei realen AIFF-Dateien; Render-Peak 0,955
- ANLZ-Ground-Truth: Content `254580025`, `ANLZ0000.DAT/PQTZ`, Rohwert und Importer `0,0017 s` identisch; Analyse-Konfidenz `1,0`, BPM `138,0`, Camelot `4A`
- Realer Uebergangs-Render: zwei Rekordbox-Tracks, 60 s / 44,1 kHz / Stereo, Peak `0,515`, Mitte-vs.-Anfang `-2,19 dB`, Kanalabweichung `0,06 dB`, finite Samples; akzeptiert
- `pip check`, `compileall` und `git diff --check`: erfolgreich
- Deep Bug-Hunt: Rekordbox-Duplikat-/Basename-Fallback abgesichert; 62 Importer-Regressionstests bestanden

## Reale Abschlussabnahme 2026-07-26

Der zuvor externe Restpunkt ist mit realen lokalen Daten geschlossen. Ein echter
Rekordbox-Track (Content `254580025`) lieferte aus `ANLZ0000.DAT/PQTZ` roh
`0,0017 s`; Importer und `analyze_track()` uebernahmen exakt diesen Wert mit
`downbeat_confidence=1,0`. Ein 60-s-Uebergangs-Render aus zwei lokalen
Rekordbox-Tracks bestand Peak-, Pegel-, Kanal- und Sample-Integritaetspruefungen.
Eine subjektive Langzeit-Hoersession bleibt optional und ist kein technischer
Repository-Fix.

## Historie

Die frühere "Intelligent Scoring"-Schicht (7 Module) war nie verdrahtet und wurde
2026-07-16 entfernt; ihre 4 wertvollen Konzepte leben in der Context-Flow-Strategie
weiter (Details: Commit a2991bf).

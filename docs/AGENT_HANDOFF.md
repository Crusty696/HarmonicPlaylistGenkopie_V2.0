# Agent Handoff – aktueller Hauptstand

Stand: 2026-07-20  
Autoritativer Branch: `main`

## Aktueller Zustand

Alle geprüften Hardening-, Installer-, Coverage- und Validierungsänderungen sind in `main` zusammengeführt. Der technische Abschlussstand vor diesem Handoff war Commit `f29654387dcb6120b0b2ff3b7fe9a4539a9c85ec`.

Der letzte vollständige Gate dieses Codes:

- 1.313 Tests bestanden, 26 Warnungen
- Gesamt-Coverage 76,85 %
- `main.py` 58 %
- `hpg_core/ai_launcher.py` 93 %
- Ruff: 0 Befunde
- Compileall und `git diff --check`: bestanden

Clean-Tree-Release des geprüften Commits:

- EXE SHA256: `687f1cf9406b4208313f4028c15b2b5bb3fa5bdb3dde99595f362ef3ecebca72`
- Installer SHA256: `0ee942bae50afaf13dce97118f29d3ae5476e063bd4eeccc6d8b03107f5553b5`
- Manifest: `C:\Users\david\.codex\visualizations\2026\07\19\019f7c6b-f4a6-7101-87ea-77f7aefb03f6\hpg-release-f296543\release-manifest.json`

## Was andere Agenten zuerst lesen müssen

1. `docs/DATA_AND_VALIDATION_CONTRACT.md`
2. `docs/INDEPENDENT_VALIDATION_PROTOCOL.md`
3. dieses Dokument
4. die Tests `test_run_lifecycle.py`, `test_ai_launcher.py`, `test_main_workers.py`, `test_codec_matrix.py` und `test_ground_truth_evaluator.py`

## Branch-Konsolidierung

Die früheren Arbeitsbranches wurden vor ihrer Entfernung einzeln gegen `main` geprüft:

- `codex/hpg-forensic-hardening`: byte-identisch mit `main`; vollständig fast-forward integriert.
- `claude/bug-search-18j1jh`: Connection-Lifecycle, `OSError`, `METER`, Cancel-Button und tote Variablen sind bereits in `main` enthalten oder robuster weiterentwickelt. Die drei dort committed `.coverage.vm.pid*`-Dateien sind unerwünschte Testartefakte.
- `fix-bpm-accuracy-unused-import-7372378997345439881`: exakt dieselbe Importbereinigung ist bereits in `main` enthalten.
- `fix-unused-imports-main-py-18341017338305922521`: 21 Bereinigungen sind enthalten; die alten Entfernungen von `QToolTip` und `QTimer` sind inzwischen falsch, weil beide im aktuellen GUI-/Shutdown-Code verwendet werden.
- `perf-optimize-string-concat-main-7325266356028154311`: nicht übernommen. Der Patch basiert auf einer stark veralteten `main.py`, lässt sich nicht sauber anwenden und spart beim Projektlimit von 1.000 Tracks im isolierten Benchmark nur ungefähr 19 Mikrosekunden. Kompatibilitätsberechnung und Qt-Rendering dominieren die reale Laufzeit. Nur nach neuem Profiling wieder aufnehmen.

`main` ist nach der Bereinigung die einzige Branch-Quelle. Alte Branch-Namen dürfen nicht als fehlende Arbeit interpretiert werden.

## Geschützte lokale Nutzerdateien

Die folgenden untracked Dateien/Ordner gehören dem Nutzer und wurden absichtlich nie committed oder gelöscht:

- `.agents/skills/hpg-audit-optimize/`
- `.agents/skills/hpg-debugging/`
- `.agents/skills/hpg-mixpoint-engineering/`
- `AGENTS.md`

## Offene Evidenz – nicht als erledigt behaupten

- Windows-Sandbox-Install-/Uninstall-Test nach PC-Neustart
- unabhängiges adjudiziertes reales Musikkorpus
- tatsächlicher DJ-Blindhörtest mit statistischer Auswertung
- Langzeit- und Fremdhardwaretests
- gezielte Prüfung der PyInstaller-Warnung zur optionalen `tbb12.dll`
- Coverage-Risikozonen: `main.py`, `parallel_analyzer.py`, `ai_engine.py`

Nicht behaupten: Die App sei zu 100 % crashfrei, alle Musikdaten seien fachlich korrekt oder der Installer sei bereits in einer frischen VM getestet.

## Teststrategie

Während Änderungen nur direkt betroffene Tests mit `--no-cov` ausführen. Vor Release oder Agentenübergabe einmal die vollständige Suite mit Coverage und anschließend Ruff, Compileall und `git diff --check` ausführen. Produktcache-Dateien niemals als Testziel verwenden oder verändern.

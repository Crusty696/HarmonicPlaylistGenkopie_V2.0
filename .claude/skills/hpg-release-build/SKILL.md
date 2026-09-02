---
name: hpg-release-build
description: Use when building or releasing HPG — build.bat, HPG.spec/PyInstaller, installer.iss/Inno Setup, Start.bat, requirements-Pinning, Versions-Bump, GitHub-Actions-Workflows oder wenn die EXE sich anders verhaelt als der Quellcode.
---

# HPG Release & Build

## Wer macht was

| Artefakt | Weg |
|---|---|
| Standalone-EXE | `build.bat` → venv312 → `pip install -r requirements.txt` → `pyinstaller --clean --noconfirm HPG.spec` → `HarmonicPlaylistGenerator.exe` im Root |
| Windows-Installer | Inno Setup: `ISCC.exe installer.iss` → `installer_output\HPG_v<version>_Setup.exe` |
| GitHub-Release | `.github/workflows/release.yml`, Trigger Tag `v*.*.*`, Python 3.12.10, ruft `build.bat`, veroeffentlicht die **rohe EXE** (keinen Installer) |

`build_installer.bat` ist der Inno-Setup-Wrapper. **Vor jedem Release pruefen,
ob es wirklich `ISCC.exe` aufruft** — es gab einen Stand, in dem das Skript nur
PyInstaller startete und trotzdem "Installer erstellt" meldete.

## Python-Vertrag

- **3.12.x zwingend**, mindestens 3.12.1. Nicht 3.13+, nicht 3.11 als Fallback:
  numba (librosa-Stack) unterstuetzt 3.13+ nicht, und 3.12.0 hatte einen
  CPython-Bug, der `scipy.stats` im Frozen-Build crashte (pyinstaller#8186).
  Basis ist 3.12.10.
- `MIN_PYTHON = "3.12.1"` in `hpg_core/app_metadata.py` ist die
  maschinenlesbare Quelle; `tests/test_release_metadata.py` prueft sie gegen
  die README.
- Ein Batch-Fallback auf Python 3.11 ist **falsch**, egal wie freundlich er
  formuliert ist.

## Batch-Falle (Windows cmd)

Innerhalb eines Klammerblocks wird `%VAR%` beim **Parsen** ersetzt, nicht zur
Laufzeit:

```bat
if exist "..." (
    set "PY=C:\...\python.exe"
    if exist "%PY%" ( ... )      REM  %PY% ist hier LEER
)
```

Loesung: `setlocal EnableDelayedExpansion` plus `!PY!`, oder Variable nicht im
selben Block setzen und lesen. Diese Falle hat den Global-Python-Zweig in
`Start.bat` schon zweimal still ausgeschaltet.

Neue oder geaenderte `.bat`/`.ps1` gehen ueber den `script-validator` (Skill
`validating-windows-scripts`): Parse-Check plus Smoke-Run, bis drei
fehlerfreie Laeufe in Folge stehen.

## requirements.txt

Direkte Imports gehoeren hinein — auch `soundfile` und `SQLAlchemy`, die
frueher nur transitiv kamen. Die produktive Kombination haengt zusammen:

```
numpy 1.26.4   <- erzwungen von numba 0.59.1
numba 0.59.1   <- Constraint fuer librosa 0.11.0
llvmlite 0.42.0 <- Constraint fuer numba
```

**numpy anheben, ohne numba und llvmlite gemeinsam zu heben und die Suite auf
echtem Audio zu fahren, bricht den librosa-Stack.** Vor jedem Pin-Wechsel
`pip list` gegen `requirements.txt` halten — die installierte `venv312` ist die
Wahrheit darueber, was tatsaechlich getestet wurde.

Die Test-Toolchain (`pytest`, `pytest-cov`, `pytest-xdist`, `pytest-qt`) setzt
`pytest.ini` voraus (`-n auto`, `--cov`). Fehlt sie in den Requirements, ist
ein frischer Klon rot.

## Versions-Bump: vollstaendige Liste

Von `tests/test_release_metadata.py` abgesichert:

- `hpg_core/app_metadata.py` → `APP_VERSION` (Quelle)
- `README.md` → `v<version>`
- `installer.iss` → `AppVersion=<version>`
- `version_info.txt` → die `ProductVersion`-Zeile
- `build.bat` → `v<version>`

**Nicht** abgesichert, trotzdem Pflicht:

- `hpg_core/__init__.py` → `__version__`
- `installer.iss` → `OutputBaseFilename` und der MsgBox-Text
- `version_info.txt` → `filevers`, `prodvers`, `FileVersion`
- `docs/QUICK_START.txt`

Derselbe Test prueft ausserdem, dass die README die echte Strategie-Anzahl
(`len(STRATEGIES)`) und `MIN_PYTHON` nennt — README-Aenderungen koennen die
Suite rot machen.

## PyInstaller

`HPG.spec`: `collect_submodules` fuer scipy/librosa/soundfile/pedalboard,
`collect_data_files` fuer librosa und pyrekordbox,
`collect_dynamic_libs('soundfile')`, `console=False`,
`version='version_info.txt'`, `icon.ico`. Neue native Abhaengigkeit →
Hidden-Imports **und** Data-Files pruefen, sonst faellt es erst zur Laufzeit im
Frozen-Build auf.

## Installer-Regeln

Der Uninstaller darf den **Benutzer-Cache nicht loeschen** — der liegt in
`%LOCALAPPDATA%\HPG`, nicht unter `{app}`. Nur App-Logs im App-Verzeichnis sind
loeschbar.

## Release-Reihenfolge

1. Volle Suite gruen (Skill `hpg-testing-verification`)
2. Version an allen Stellen gebumpt
3. `build.bat`, EXE starten und einen echten Ordner analysieren
4. `ISCC.exe installer.iss`, Installer auf sauberem System testen
5. `tools/release_manifest.py` (verweigert dirty Worktree)
6. Tag `v<version>` pushen → Workflow

## Common Mistakes

- Skript meldet Erfolg, ohne das Werkzeug ueberhaupt aufzurufen.
- Versionsstelle anfassen, die kein Test abdeckt, und eine vergessen.
- Pins entpinnen "damit es moderner ist".
- Batch-Variable im selben Klammerblock setzen und lesen.
- Hartkodierte Benutzerpfade in ausgelieferten Skripten.

# HPG — Produktionsdokumentation

Harmonic Playlist Generator: PyQt6-App für DJ-Playlist-Generierung mit
Audio-Analyse (librosa), genre-bewussten Mixpoints und Transition-Previews.

## Systemvoraussetzungen

- **Python 3.12** (mindestens 3.12.1, NICHT 3.13+ — numba-Inkompatibilität)
- Windows (primäre Zielplattform)
- Abhängigkeiten: `requirements.txt` (PyQt6, librosa, numpy, soundfile, pyrekordbox, …)

## Setup & Start

```bat
py -3.12 -m venv venv312
venv312\Scripts\python.exe -m pip install -r requirements.txt
venv312\Scripts\python.exe main.py
```

Alternativ: `build.bat` erzeugt eine PyInstaller-Exe, `installer.iss` den Inno-Setup-Installer.

## Tests

```bat
venv312\Scripts\python.exe -m pip install pytest pytest-xdist pytest-cov pytest-qt
venv312\Scripts\python.exe -m pytest tests/ --no-cov -q
```

## Kern-Workflow

1. Musikordner wählen → parallele Analyse (BPM, Key, Energy, Struktur, Genre; Rekordbox-Fast-Path falls DB vorhanden)
2. Strategie wählen (8 Modi, Standard: Harmonic Flow) → Playlist generieren
3. Transition-Empfehlungen + Audio-Previews (subprocess-gerendert)
4. Export: m3u8 oder Rekordbox XML

Aktueller Status und Umgebungsdetails: `PRODUCTION_STATUS.md`.

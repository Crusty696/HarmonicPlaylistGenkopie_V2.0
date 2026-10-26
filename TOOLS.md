# TOOLS.md

## Arbeitsumgebung

```powershell
# Abschlusspruefung: Python 3.12 aus diesem Projekt
.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q

# Schneller Entwicklungszyklus; kein Abschlussbeleg
.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q --no-cov

# GUI
.\venv312\Scripts\python.exe main.py
```

- Kein System-Python und kein Python 3.13+; numba ist an Python 3.12 gebunden.
- Keine parallelen vollen pytest-Laeufe, da die Suite bereits `-n auto` nutzt.
- Audio-/E2E-Werkzeuge nur im beauftragten Umfang mit expliziter Quelle und
  isolierten Ausgabe-/Cachepfaden starten. `e2e_check.py` ersetzt keine native
  App-Abnahme. `manual_test.bat --folder "<Quellordner>"` vermeidet den
  historischen Default-Pfad; Cache vorher isolieren.
- Laufzeitcache nur ueber `HPG_CACHE_DIR` oder `HPG_CACHE_FILE` isolieren;
  niemals die Benutzer-Cache-Datei direkt bearbeiten.
- Vor Build oder Installer zuerst Tests und Versionsquellen pruefen. Keine
  EXE-, Installer- oder Release-Artefakte ohne expliziten Auftrag erzeugen.

## OpenClaw

```powershell
openclaw agent --agent hpg --message "<Auftrag>"
openclaw gateway status --json
openclaw dashboard
openclaw memory status --deep --agent hpg
```

Alle Befehle werden im Projekt-Workspace ausgefuehrt. Vor Schreibzugriffen
immer den betroffenen Pfad und den aktuellen Git-Status pruefen.

# OpenClaw fuer Harmonic Playlist Generator

## Aktiver Agent

```powershell
openclaw agent --agent hpg --message "<dein HPG-Auftrag>"
```

Der Agent arbeitet im Repository-Workspace mit `openai/gpt-5.6-sol` ueber den
offiziellen Codex-Harness. Seine Identitaet im Dashboard ist **HPG Engineering**
mit dem Projekt-Icon.

## Eingebaute Projektanpassungen

- Alle 14 Skills aus `.agents/skills/` werden projektlokal entdeckt und haben
  Vorrang vor allgemeineren Skills.
- `AGENTS.md` erzwingt Orientierung, passende Fachrolle, schreibgeschuetzten
  Waechter vor/nach nichttrivialen Aenderungen und den HPG-Testvertrag.
- `SOUL.md`, `TOOLS.md`, `USER.md` und `IDENTITY.md` beschreiben den
  Engineering-Auftrag, die Python-3.12-Umgebung, Sicherheitsgrenzen und die
  Dashboard-Identitaet.
- `MEMORY.md` haelt nur langlebige HPG-Invarianten und Betriebswissen fest.
- Der Agent verwendet das Coding-Profil, keine Elevated-Tools und die globale
  Multi-Agent-Delegation mit maximal fuenf gleichzeitig aktiven Agenten.

## Empfohlene Auftragsform

```text
Analysiere zuerst den betroffenen Codepfad. Erstelle einen kleinen Plan.
Lass ihn vor der Umsetzung von hpg-waechter gegen den Code pruefen.
Implementiere nur den beauftragten Scope, fuehre die passenden Tests aus,
lasse den Diff erneut durch hpg-waechter pruefen und melde nur belegte Resultate.
```

## Wichtige Befehle

```powershell
# Status und Projektagent pruefen
openclaw agents list
openclaw skills list --agent hpg
openclaw memory status --deep --agent hpg

# HPG-Tests
.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q

# GUI
.\venv312\Scripts\python.exe main.py
```

## Grenzen

Keine realen Musikbibliotheken, Rekordbox-Datenbanken, Cache-Dateien,
Installer, Release-Artefakte, Remote-Git-Aktionen oder ungetrackten
`Claude-Autopilot-*`-Dateien ohne ausdruecklichen Auftrag bearbeiten.

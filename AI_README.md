# HPG Intelligence Layer (LLM Integration)

Diese Erweiterung integriert lokale Large Language Models (LLMs) in den Harmonic Playlist Generator (HPG), um ein semantisches Musikverständnis zu ermöglichen.

## Features
- **Asynchrone Analyse**: Die KI-Analyse läuft im Hintergrund und blockiert niemals die Benutzeroberfläche oder die Audio-Analyse.
- **Deep Tagging**: Generiert automatisch Mood-Tags und Sub-Genres basierend auf Track-Metadaten.
- **AI Insights**: Zeigt KI-generierte Beschreibungen direkt in der Playlist-Tabelle an.

## Konfiguration
Die Einstellungen befinden sich in `hpg_core/config.py`:

```python
AI_ENABLED = True
AI_API_URL = \"http://localhost:11434/v1/chat/completions\" # Ollama Standard
AI_MODEL = \"llama3\" # Das installierte Modell (Ollama/LM Studio)
```

## Setup (Lokal)
1. **Ollama**:
   - Installiere [Ollama](https://ollama.com/).
   - Lade ein Modell: `ollama run llama3`.
   - Stelle sicher, dass Ollama läuft (Standard: Port 11434).

2. **LM Studio**:
   - Starte den Local Server in LM Studio (OpenAI-kompatibel).
   - Passe den Port in `hpg_core/config.py` an (meist 1234).

## Auto-Start & Auto-Detect (ab V2.0)
Die App startet die AI-Provider selbst — kein manuelles `ollama serve` noetig.

- **Auto-Detect beider Provider**: Beim Start (und per Button *"AI erkennen / starten"*
  unter *Advanced Parameters → AI Intelligence Provider*) prueft die App
  Ollama **und** LM Studio. Reihenfolge: bevorzugter Radio-Provider zuerst,
  sonst Ollama → LM Studio.
- **Headless mit GUI-Fallback**: Erst wird der Server headless via CLI gestartet
  (`ollama serve` bzw. `lms server start`). Schlaegt die CLI fehl, wird die
  Desktop-App als Fallback gestartet.
- **Dynamischer LM-Studio-Port**: Der Port wird via `lms server status` erkannt
  (LM Studio laeuft nicht zwingend auf 1234).
- **Real installierte Modelle**: Das Modell-Dropdown wird mit den tatsaechlich
  installierten Modellen gefuellt (Ollama `/api/tags`, LM Studio `/v1/models`).
  Vorausgewaehlt wird `AI_MODEL` falls vorhanden, sonst das erste passende Modell.
- **Auto-Pull/Load**: Fehlt das gewuenschte Modell komplett, wird es automatisch
  geladen (Ollama `pull`, LM Studio `get` + `load`).

Implementiert in `hpg_core/ai_launcher.py` (reine Funktionen, ohne Qt) plus
`AIDetectWorker` (Hintergrund-Thread in `main.py`).

## Nutzung
1. Starte die HPG App. Die AI-Provider werden im Hintergrund automatisch erkannt
   und gestartet; der Status erscheint unter *AI Intelligence Provider*.
2. Analysiere einen Musik-Ordner.
3. Sobald die Audio-Analyse fertig ist, beginnt der `AIAnalysisWorker` automatisch
   mit der Anreicherung der Tracks. Falls der Server beim Start nicht lief, startet
   der Worker ihn selbst nach (`_ensure_ready`).
4. Die Ergebnisse erscheinen in der Spalte **AI Insights** in der Playlist-Ansicht
   (Format `[Sub-Genre] mood1, mood2`, Mixing-Tipp als Tooltip).

## JSON-Vertrag (wichtig)
Der `AI_SYSTEM_PROMPT` erzwingt exakt diese Keys (sonst bleibt die Spalte leer):
```json
{"sub_genre": "Peak-time Techno", "moods": ["driving","dark"], "description": "one-sentence mixing tip"}
```

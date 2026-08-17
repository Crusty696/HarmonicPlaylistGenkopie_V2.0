# HPG Intelligence Layer (LLM Integration)

Diese Erweiterung integriert lokale Large Language Models (LLMs) in den Harmonic Playlist Generator (HPG), um ein semantisches Musikverständnis zu ermöglichen.

## Features
- **Asynchrone Analyse**: Die KI-Analyse läuft im Hintergrund und blockiert niemals die Benutzeroberfläche oder die Audio-Analyse.
- **Deep Tagging**: Generiert automatisch Mood-Tags und Sub-Genres basierend auf Track-Metadaten.
- **AI Insights**: Zeigt KI-generierte Beschreibungen direkt in der Playlist-Tabelle an.

## Konfiguration
Die Einstellungen befinden sich in `hpg_core/config.py`:

```python
AI_PROVIDER = \"LM Studio\"          # oder \"Ollama\"
AI_MODEL = \"granite-4.0-h-tiny\"   # gemessener Sieger, siehe unten
AI_MAX_TOKENS = 400                # Pflicht bei erzwungenem JSON-Schema
```

## Modellwahl — gemessen, nicht geschaetzt (2026-08-14)

Getestet wurde gegen den echten Vertrag der App: eigener System-Prompt,
`response_format=json_schema` mit `strict: true`, volle Validierung inklusive
Provenienz. 8 reale Tracks je Modell, RX 7800 XT, LM Studio auf Vulkan.

| Modell | gueltig | Latenz | Laden | Groesse |
|---|---|---|---|---|
| **granite-4.0-h-tiny** | **8/8** | **2,7 s** | 20 s | 4,2 GB |
| llama-3.2-8x3b-dark-champion | 8/8 | 2,8 s | 40 s | 10,7 GB |
| ministral-3-14b-reasoning | 8/8 | 6,7 s | 51 s | 12,0 GB |
| qwen3.5-9b | 0/8 | — | 45 s | 10,5 GB |
| ornith-1.0-9b | 0/8 | — | 39 s | 9,5 GB |

Bei 500 Tracks: rund 22 Minuten mit granite gegen ueber 11 Stunden mit einem
27B-Reasoning-Modell (81 s/Track gemessen).

`qwen3.5-9b` und `ornith-1.0-9b` liefern unter dem Strict-Schema **leeren
Inhalt bei jedem Token-Budget** (400 / 1500 / 4000 / unbegrenzt, jeweils
`finish_reason='length'`, `content_len=0`). Sie sind fuer diesen Pfad
unbrauchbar — unabhaengig von der Modellgroesse.

**Warum `AI_MAX_TOKENS` gesetzt sein muss:** Unter erzwungenem Schema kann ein
Modell, das in eine ungeschlossene Struktur laeuft, nicht stoppen. Ohne Limit
verbrannte qwen3.5-9b 65,5 s pro Track fuer ein leeres Ergebnis, mit Limit
9,5 s — bei gleichem Ausgang.

**AMD-Hinweis:** ROCm unterstuetzt RDNA3 (gfx1101, RX 7800 XT) unter Windows
nicht. In LM Studio die **Vulkan**-Runtime waehlen.

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

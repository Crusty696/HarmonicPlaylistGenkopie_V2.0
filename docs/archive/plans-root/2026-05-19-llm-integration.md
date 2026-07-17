# HPG Intelligence Layer (LLM Integration) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integration lokaler LLMs (Ollama/LM Studio) für semantisches Musikverständnis ohne Blockade der Kern-Performance.

**Architecture:** Asynchroner I/O-Worker (QThread), der die Ergebnisse der Librosa-Analyse nimmt und via OpenAI-kompatibler API (Ollama/LM Studio) mit \"Deep Tags\" und Beschreibungen anreichert.

**Tech Stack:** Python `requests`, PyQt6 (QThread/Signals), Ollama/LM Studio API.

---

### Task 1: Datenmodell-Update & Config

**Files:**
- Modify: `hpg_core/models.py`
- Modify: `hpg_core/config.py`

- [ ] **Step 1: AI-Metadata Feld in `Track` hinzufügen**
  Füge `ai_metadata: dict = field(default_factory=dict)` zur `Track`-Klasse in `hpg_core/models.py` hinzu.

- [ ] **Step 2: AI-Konstanten in `hpg_core/config.py` definieren**
```python
# === AI Intelligence Layer ===
AI_ENABLED = True
AI_API_URL = \"http://localhost:11434/v1/chat/completions\" # Default Ollama
AI_MODEL = \"llama3\" # Oder mistral, etc.
AI_TIMEOUT = 10.0
AI_SYSTEM_PROMPT = \"You are a professional DJ assistant. Analyze track data and provide: 1. Sub-genre, 2. Three mood tags, 3. A 1-sentence description. Respond ONLY in JSON format.\"
```

- [ ] **Step 3: Commit**
`git commit -m \"feat: add ai metadata fields and config constants\"`

---

### Task 2: Der AI-Client (`ai_engine.py`)

**Files:**
- Create: `hpg_core/ai_engine.py`

- [ ] **Step 1: Basis-Client implementieren**
Erstelle eine Funktion `fetch_ai_analysis(track: Track) -> dict` in `hpg_core/ai_engine.py`.

```python
import requests
import logging
from .models import Track
from .config import AI_API_URL, AI_MODEL, AI_TIMEOUT, AI_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

def fetch_ai_analysis(track: Track) -> dict:
    if not track: return {}
    prompt = f\"Track: {track.artist} - {track.title}. Genre: {track.detected_genre}. BPM: {track.bpm}. Energy: {track.energy}.\"
    payload = {
        \"model\": AI_MODEL,
        \"messages\": [
            {\"role\": \"system\", \"content\": AI_SYSTEM_PROMPT},
            {\"role\": \"user\", \"content\": prompt}
        ],
        \"response_format\": {\"type\": \"json_object\"}
    }
    try:
        resp = requests.post(AI_API_URL, json=payload, timeout=AI_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f\"AI API Error: {e}\")
        return {}
```

- [ ] **Step 2: Commit**
`git commit -m \"feat: implement ai_engine core client\"`

---

### Task 3: Asynchrone UI-Integration (PyQt6)

**Files:**
- Modify: `main.py`

- [ ] **Step 1: `AIAnalysisWorker` Klasse erstellen**
Implementiere `AIAnalysisWorker(QThread)` in `main.py`. Er nimmt eine Liste von Tracks und feuert `ai_finished(track_path, data)`.

- [ ] **Step 2: UI-Update Logik im MainWindow**
Füge eine Methode `on_ai_finished` hinzu, die die Playlist-Tabelle aktualisiert. Füge ggf. eine neue Spalte \"AI Insights\" zur Tabelle hinzu.

- [ ] **Step 3: Trigger nach Audio-Analyse**
In `on_analysis_finished`, starte den `AIAnalysisWorker` für die gerade analysierten Tracks.

- [ ] **Step 4: Commit**
`git commit -m \"feat: integrate asynchronous ai worker into gui\"`

---

### Task 5: Validierung

- [ ] **Step 1: Testlauf mit Mock-Daten**
Simuliere eine API-Antwort und prüfe die UI-Anzeige.

- [ ] **Step 2: Commit**
`git commit -m \"test: verify ai integration with mock data\"`

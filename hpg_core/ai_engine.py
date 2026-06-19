import requests
import logging
import json
from .models import Track
from . import config

logger = logging.getLogger(__name__)

def fetch_ai_analysis(track: Track, provider: str = None, model: str = None,
                      url: str = None) -> dict:
    """
    Sendet Track-Daten an die lokale AI-Engine (Ollama oder LM Studio).
    Extrahiert und parst das zurückgegebene JSON-Objekt aus dem OpenAI-Kompatibilitätsformat.

    url: Optionaler voller Chat-Completions-Endpoint. Hat Vorrang vor den
         Config-Defaults — noetig weil LM Studio einen dynamischen Port nutzen
         kann (vom ai_launcher erkannt).
    """
    if not track: return {}

    current_provider = provider or config.AI_PROVIDER
    if url:
        pass  # expliziter Endpoint vom Launcher
    elif current_provider == "LM Studio":
        url = config.AI_API_URL_LMSTUDIO
    else:
        url = config.AI_API_URL_OLLAMA

    sections_str = ""
    if hasattr(track, "sections") and track.sections:
        sections_list = []
        for s in track.sections:
            label = s.get("label", "unknown")
            start = s.get("start_time", 0.0)
            end = s.get("end_time", 0.0)
            energy = s.get("avg_energy", 0.0)
            sections_list.append(f"{label}({start:.1f}s-{end:.1f}s, energy:{energy:.1f})")
        sections_str = " | ".join(sections_list)

    prompt = (
        f"Track: {track.artist} - {track.title}. "
        f"Genre: {track.detected_genre}. BPM: {track.bpm:.1f}. Energy: {track.energy}. Duration: {track.duration:.1f}s.\n"
    )
    if sections_str:
        prompt += f"Detected Audio Sections: {sections_str}\n"
    prompt += "Identify the optimal mix_in_time and mix_out_time in seconds. Ensure they are logically placed within the track duration and sections."

    payload = {
        "model": model or config.AI_MODEL,
        "messages": [
            {"role": "system", "content": config.AI_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"}
    }
    try:
        resp = requests.post(url, json=payload, timeout=(5.0, config.AI_TIMEOUT))
        resp.raise_for_status()
        resp_json = resp.json()
        
        # CRITICAL BUGFIX: Extrahiere und parse den JSON-String aus choices[0].message.content
        if "choices" in resp_json and len(resp_json["choices"]) > 0:
            content_str = resp_json["choices"][0]["message"]["content"]
            # Bereinigung falls LLM fälschlicherweise Markdown-Formatierung mitsendet
            content_str = content_str.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            content_str = content_str.strip()
            
            parsed_data = json.loads(content_str)
            logger.info(f"AI-Analyse erfolgreich geladen fuer {track.title} ({current_provider})")
            return parsed_data
            
        logger.warning(f"AI-Antwort besass kein 'choices'-Array: {resp_json}")
        return {}
    except Exception as e:
        logger.error(f"AI API Error ({current_provider}): {e}")
        return {}

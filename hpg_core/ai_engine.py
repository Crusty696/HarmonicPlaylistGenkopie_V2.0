import requests
import logging
import json
import math
from datetime import datetime, timezone
from .models import Track
from . import config

logger = logging.getLogger(__name__)

AI_SCHEMA_VERSION = 1
AI_PROMPT_VERSION = "2026-07-20"
AI_RESULT_KEYS = {"sub_genre", "moods", "description", "mix_in_time", "mix_out_time"}
AI_JSON_SCHEMA = {
    "name": "hpg_ai_analysis",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(AI_RESULT_KEYS),
        "properties": {
            "sub_genre": {"type": "string", "minLength": 1, "maxLength": 100},
            "moods": {
                "type": "array",
                "minItems": 2,
                "maxItems": 3,
                "items": {"type": "string", "minLength": 1, "maxLength": 40},
            },
            "description": {"type": "string", "minLength": 1, "maxLength": 1000},
            "mix_in_time": {"type": "number", "minimum": 0},
            "mix_out_time": {"type": "number", "minimum": 0},
        },
    },
}


def has_valid_provenance(metadata) -> bool:
    """Prueft, ob KI-Metadaten eine gueltige, aktuelle Provenienz tragen.

    HPG-002-Fix: Nur Daten, die durch validate_ai_analysis gelaufen sind
    (aktuelle Prompt-/Schema-Version), duerfen Scoring beeinflussen.
    """
    if not isinstance(metadata, dict) or not metadata:
        return False
    provenance = metadata.get("_provenance")
    if not isinstance(provenance, dict):
        return False
    return (
        bool(provenance.get("provider"))
        and bool(provenance.get("model"))
        and provenance.get("prompt_version") == AI_PROMPT_VERSION
        and provenance.get("schema_version") == AI_SCHEMA_VERSION
    )


def ai_metadata_matches(track: Track, provider: str, model: str) -> bool:
    """Prueft, ob vorhandene KI-Daten exakt zum aktuellen Vertrag passen."""
    metadata = getattr(track, "ai_metadata", {})
    if not isinstance(metadata, dict):
        return False
    provenance = metadata.get("_provenance")
    if not isinstance(provenance, dict):
        return False
    return (
        provenance.get("provider") == provider
        and provenance.get("model") == model
        and provenance.get("prompt_version") == AI_PROMPT_VERSION
        and provenance.get("schema_version") == AI_SCHEMA_VERSION
    )


def validate_ai_analysis(
    data: dict,
    track: Track,
    provider: str,
    model: str,
) -> dict:
    """Validiert den fachlichen KI-Vertrag und fuegt Provenienz hinzu."""
    if not isinstance(data, dict) or set(data) != AI_RESULT_KEYS:
        raise ValueError("KI-Ergebnis muss exakt das definierte Fuenf-Key-Schema besitzen")
    if (
        not isinstance(data["sub_genre"], str)
        or not data["sub_genre"].strip()
        or len(data["sub_genre"].strip()) > 100
    ):
        raise ValueError("sub_genre muss ein nichtleerer String sein")
    moods = data["moods"]
    if not isinstance(moods, list) or not 2 <= len(moods) <= 3:
        raise ValueError("moods muss zwei bis drei Eintraege besitzen")
    if any(
        not isinstance(mood, str) or not mood.strip() or len(mood.strip()) > 40
        for mood in moods
    ):
        raise ValueError("Jeder Mood muss ein nichtleerer String sein")
    if (
        not isinstance(data["description"], str)
        or not data["description"].strip()
        or len(data["description"].strip()) > 1000
    ):
        raise ValueError("description muss ein nichtleerer String sein")

    mix_in = float(data["mix_in_time"])
    mix_out = float(data["mix_out_time"])
    if not math.isfinite(mix_in) or not math.isfinite(mix_out):
        raise ValueError("KI-Mixpoints muessen endlich sein")
    if not 0.0 <= mix_in < mix_out <= float(track.duration):
        raise ValueError("KI-Mixpoints verletzen die Track-Grenzen")
    if not getattr(track, "outro_covered", False):
        raise ValueError("KI-Mix-Out ist ohne analysiertes Track-Ende unzulaessig")

    return {
        "sub_genre": data["sub_genre"].strip(),
        "moods": [mood.strip() for mood in moods],
        "description": data["description"].strip(),
        "mix_in_time": mix_in,
        "mix_out_time": mix_out,
        "_provenance": {
            "provider": provider,
            "model": model,
            "prompt_version": AI_PROMPT_VERSION,
            "schema_version": AI_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mixpoints_advisory": True,
        },
    }

def fetch_ai_analysis(track: Track, provider: str = None, model: str = None,
                      url: str = None) -> dict:
    """
    Sendet Track-Daten an die lokale AI-Engine (Ollama oder LM Studio).
    Extrahiert und parst das zurückgegebene JSON-Objekt aus dem OpenAI-Kompatibilitätsformat.

    url: Optionaler voller Chat-Completions-Endpoint. Hat Vorrang vor den
         Config-Defaults — noetig weil LM Studio einen dynamischen Port nutzen
         kann (vom ai_launcher erkannt).
    """
    if not track: 
        logger.warning("fetch_ai_analysis called with None track")
        return {}
    
    # Sicherheitsprüfung der Track-Daten
    if not hasattr(track, 'filePath') or not track.filePath:
        logger.error("Invalid track object - missing filePath")
        return {}

    current_provider = provider or config.AI_PROVIDER
    if url:
        pass  # expliziter Endpoint vom Launcher
    elif current_provider == "LM Studio":
        url = config.AI_API_URL_LMSTUDIO
    else:
        url = config.AI_API_URL_OLLAMA

    # Audit-Fix 2026-07-21: None-sicher formatieren. Ein explizit vorhandener
    # None-Wert (bpm/duration/start_time) haette format(None, ".1f") geworfen und
    # den AI-Worker-Thread ungefangen gecrasht (Prompt-Bau liegt vor dem try).
    def _f(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    sections_str = ""
    if hasattr(track, "sections") and track.sections:
        sections_list = []
        for s in track.sections:
            label = s.get("label", "unknown")
            start = _f(s.get("start_time", 0.0))
            end = _f(s.get("end_time", 0.0))
            energy = _f(s.get("avg_energy", 0.0))
            sections_list.append(f"{label}({start:.1f}s-{end:.1f}s, energy:{energy:.1f})")
        sections_str = " | ".join(sections_list)

    prompt = (
        f"Track: {track.artist} - {track.title}. "
        f"Genre: {track.detected_genre}. BPM: {_f(track.bpm):.1f}. "
        f"Energy: {track.energy}. Duration: {_f(track.duration):.1f}s.\n"
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
        "temperature": 0,
        "seed": 0,
    }
    
    payload["response_format"] = {
        "type": "json_schema",
        "json_schema": AI_JSON_SCHEMA,
    }
    
    try:
        logger.debug(f"Sending AI request to {url} for track: {track.title}")
        resp = requests.post(url, json=payload, timeout=(5.0, config.AI_TIMEOUT))
        
        # Überprüfe den Statuscode
        if resp.status_code != 200:
            logger.error(f"AI API returned status code {resp.status_code}: {resp.text}")
            return {}

        resp_json = resp.json()
        
        # Validierung der Antwortstruktur
        if not isinstance(resp_json, dict):
            logger.error(f"Invalid response format from AI: expected dict, got {type(resp_json)}")
            return {}
            
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
            
            # Sicherheitsprüfung der JSON-Struktur
            if not content_str:
                logger.warning(f"Empty AI response for track {track.title}")
                return {}
                
            try:
                parsed_data = json.loads(content_str)
                selected_model = str(resp_json.get("model") or model or config.AI_MODEL)
                parsed_data = validate_ai_analysis(
                    parsed_data,
                    track,
                    current_provider,
                    selected_model,
                )
                logger.info(f"AI-Analyse erfolgreich geladen fuer {track.title} ({current_provider})")
                return parsed_data
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.error(f"AI schema validation failed for track {track.title}: {e}")
                logger.debug(f"Raw content: {content_str}")
                return {}
            
        logger.warning(f"AI-Antwort besass kein 'choices'-Array: {resp_json}")
        return {}
    except requests.exceptions.Timeout as e:
        logger.error(f"AI API Timeout for track {track.title}: {e}")
        return {}
    except requests.exceptions.ConnectionError as e:
        logger.error(f"AI API Connection Error for track {track.title}: {e}")
        return {}
    except requests.exceptions.RequestException as e:
        logger.error(f"AI API Request Error for track {track.title}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error during AI analysis for track {track.title}: {e}", exc_info=True)
        return {}

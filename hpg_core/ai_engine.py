import requests
import logging
import json
import math
import multiprocessing
from datetime import datetime, timezone
from typing import Callable
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

_CANCEL_POLL_SECONDS = 0.05
_PROCESS_STOP_TIMEOUT_SECONDS = 1.0


class _ResponseSnapshot:
    """Kleine, prozessuebergreifend transportierbare HTTP-Antwort."""

    def __init__(self, status_code: int, text: str):
        self.status_code = int(status_code)
        self.text = str(text)

    def json(self):
        return json.loads(self.text)


def _http_post_in_spawned_process(send_connection, url, payload, timeout):
    """Spawn-Target: keine Closures, damit Windows und PyInstaller es laden koennen."""
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        send_connection.send(("response", response.status_code, response.text))
    except requests.exceptions.Timeout as exc:
        send_connection.send(("timeout", str(exc)))
    except requests.exceptions.ConnectionError as exc:
        send_connection.send(("connection", str(exc)))
    except requests.exceptions.RequestException as exc:
        send_connection.send(("request", str(exc)))
    except BaseException as exc:
        send_connection.send(("unexpected", f"{type(exc).__name__}: {exc}"))
    finally:
        send_connection.close()


def _stop_spawned_process(process) -> None:
    """Beendet einen Request-Prozess nachweisbar; nie einen QThread."""
    if process.is_alive():
        process.terminate()
    process.join(_PROCESS_STOP_TIMEOUT_SECONDS)
    if process.is_alive():
        process.kill()
        process.join(_PROCESS_STOP_TIMEOUT_SECONDS)
    if process.is_alive():
        raise RuntimeError("KI-HTTP-Prozess konnte nicht beendet werden")
    process.close()


def _cancelable_post(url, payload, timeout, cancel_check: Callable[[], bool]):
    """Fuehrt nur den blockierenden HTTP-Aufruf in einem terminierbaren Prozess aus."""
    if cancel_check():
        raise InterruptedError("KI-Analyse abgebrochen")

    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_http_post_in_spawned_process,
        args=(send_connection, url, payload, timeout),
        daemon=True,
    )
    started = False
    try:
        process.start()
        started = True
        send_connection.close()
        while True:
            if cancel_check():
                raise InterruptedError("KI-Analyse abgebrochen")
            if receive_connection.poll(_CANCEL_POLL_SECONDS):
                message = receive_connection.recv()
                break
            if not process.is_alive():
                if receive_connection.poll():
                    message = receive_connection.recv()
                    break
                raise requests.exceptions.RequestException(
                    f"KI-HTTP-Prozess endete ohne Ergebnis (Exitcode {process.exitcode})"
                )
    finally:
        receive_connection.close()
        if not started:
            send_connection.close()
        if started:
            _stop_spawned_process(process)

    kind, *values = message
    if kind == "response":
        return _ResponseSnapshot(values[0], values[1])
    error_message = values[0] if values else "Unbekannter KI-HTTP-Fehler"
    if kind == "timeout":
        raise requests.exceptions.Timeout(error_message)
    if kind == "connection":
        raise requests.exceptions.ConnectionError(error_message)
    if kind == "request":
        raise requests.exceptions.RequestException(error_message)
    raise RuntimeError(error_message)


def validate_ai_metadata(metadata, *, duration: float | None = None) -> bool:
    """Prueft denselben strikten Ergebnis- und Provenienzvertrag beim Reuse."""
    if not isinstance(metadata, dict) or set(metadata) != AI_RESULT_KEYS | {"_provenance"}:
        return False
    provenance = metadata.get("_provenance")
    if not isinstance(provenance, dict) or not (
        isinstance(provenance.get("provider"), str) and provenance["provider"].strip()
        and isinstance(provenance.get("model"), str) and provenance["model"].strip()
        and provenance.get("prompt_version") == AI_PROMPT_VERSION
        and provenance.get("schema_version") == AI_SCHEMA_VERSION
        and provenance.get("mixpoints_advisory") is True
    ):
        return False
    data = {key: metadata[key] for key in AI_RESULT_KEYS}
    if not isinstance(data["sub_genre"], str) or not data["sub_genre"].strip() or len(data["sub_genre"].strip()) > 100:
        return False
    moods = data["moods"]
    if not isinstance(moods, list) or not 2 <= len(moods) <= 3 or any(not isinstance(m, str) or not m.strip() or len(m.strip()) > 40 for m in moods):
        return False
    if not isinstance(data["description"], str) or not data["description"].strip() or len(data["description"].strip()) > 1000:
        return False
    values = (data["mix_in_time"], data["mix_out_time"])
    if values == (None, None):
        return True
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in values):
        return False
    if not float(values[0]) < float(values[1]) or float(values[0]) < 0.0:
        return False
    return duration is None or float(values[1]) <= float(duration)


def has_valid_provenance(metadata) -> bool:
    """Prueft, ob KI-Metadaten eine gueltige, aktuelle Provenienz tragen.

    Nur Daten aus dem aktuellen Prompt-/Schema-Vertrag duerfen als aktuelle
    KI-Beschreibung angezeigt oder wiederverwendet werden. Das lokale
    Paar-Scoring haengt nicht von KI-Metadaten ab.
    """
    return validate_ai_metadata(metadata)


def ai_metadata_matches(track: Track, provider: str, model: str) -> bool:
    """Prueft, ob vorhandene KI-Daten exakt zum aktuellen Vertrag passen."""
    metadata = getattr(track, "ai_metadata", {})
    if not isinstance(metadata, dict):
        return False
    if not validate_ai_metadata(metadata, duration=getattr(track, "duration", None)):
        return False
    provenance = metadata["_provenance"]
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

    for key in ("mix_in_time", "mix_out_time"):
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} muss eine JSON-Zahl sein")
    mix_in = float(data["mix_in_time"])
    mix_out = float(data["mix_out_time"])
    if not math.isfinite(mix_in) or not math.isfinite(mix_out):
        raise ValueError("KI-Mixpoints muessen endlich sein")
    if not 0.0 <= mix_in < mix_out <= float(track.duration):
        raise ValueError("KI-Mixpoints verletzen die Track-Grenzen")
    # Ohne analysiertes Track-Ende ist der KI-Mix-Out nicht belastbar. Bis
    # 2026-08-21 warf das das GESAMTE Ergebnis weg — auch die weiterhin
    # nutzbare Subgenre-/Mood-Beschreibung. Die KI-Mixpunkte selbst liest kein
    # Produktivpfad (sie sind "advisory", siehe
    # docs/DATA_AND_VALIDATION_CONTRACT.md). Deshalb: nur die Mixpunkte
    # verwerfen, den Rest durchlassen.
    mixpunkte_gueltig = bool(getattr(track, "outro_covered", False))

    result = {
        "sub_genre": data["sub_genre"].strip(),
        "moods": [mood.strip() for mood in moods],
        "description": data["description"].strip(),
        "mix_in_time": mix_in if mixpunkte_gueltig else None,
        "mix_out_time": mix_out if mixpunkte_gueltig else None,
        "_provenance": {
            "provider": provider,
            "model": model,
            "prompt_version": AI_PROMPT_VERSION,
            "schema_version": AI_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mixpoints_advisory": True,
        },
    }
    if not validate_ai_metadata(result, duration=float(track.duration)):
        raise ValueError("KI-Ergebnis verletzt den persistierbaren Vertrag")
    return result

def fetch_ai_analysis(
    track: Track,
    provider: str = None,
    model: str = None,
    url: str = None,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> dict:
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
        # AUDIT-FIX 2026-08-14: max_tokens war nicht gesetzt. Unter
        # response_format=json_schema erzwingt die Runtime eine Grammatik; ein
        # Modell, das dabei in eine ungeschlossene Struktur laeuft, KANN nicht
        # mehr stoppen, weil das Schema den Abschluss verlangt. LM Studio
        # dokumentiert das ausdruecklich und empfiehlt immer ein Token-Limit.
        # Ohne Limit frisst ein einziger solcher Track die vollen AI_TIMEOUT
        # Sekunden - bei einer Bibliothek mit hunderten Tracks summiert sich das.
        # Die erwartete Antwort ist klein (Sub-Genre, 2-3 Moods, ein Satz,
        # zwei Zahlen); 400 Tokens sind grosszuegig bemessen.
        "max_tokens": config.AI_MAX_TOKENS,
    }
    
    payload["response_format"] = {
        "type": "json_schema",
        "json_schema": AI_JSON_SCHEMA,
    }
    
    try:
        logger.debug(f"Sending AI request to {url} for track: {track.title}")
        request_timeout = (5.0, config.AI_TIMEOUT)
        if cancel_check is None:
            resp = requests.post(url, json=payload, timeout=request_timeout)
        else:
            resp = _cancelable_post(url, payload, request_timeout, cancel_check)
        
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
    except InterruptedError:
        raise
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

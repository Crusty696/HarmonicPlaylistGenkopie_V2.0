"""
hpg_core/ai_launcher.py

Auto-Start und Auto-Detect der lokalen AI-Provider (Ollama / LM Studio).

Strategie (vom User vorgegeben):
  * Provider: Auto-detect BEIDE, Reihenfolge Ollama -> LM Studio
    (oder bevorzugter Provider zuerst, wenn uebergeben).
  * Start: HEADLESS (CLI) zuerst, GUI-App als Fallback.
  * Modelle: REAL installierte Modelle live abfragen; gewuenschtes Modell
    automatisch pullen/laden, falls nicht vorhanden.

Keine Qt-Abhaengigkeit hier — reine Funktionen, damit sie in einem
Hintergrund-QThread (siehe main.py) aufgerufen werden koennen.
"""

import os
import re
import shutil
import logging
import subprocess
import time

import requests

from . import config

logger = logging.getLogger(__name__)

# Windows: Subprozesse ohne sichtbares Konsolenfenster starten
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# Wie lange auf einen frisch gestarteten Server gewartet wird
_WAIT_HEADLESS_SEC = 10
_WAIT_GUI_SEC = 25


# ---------------------------------------------------------------------------
# Ergebnis-Container
# ---------------------------------------------------------------------------

class AIProviderStatus:
    """Ergebnis einer Provider-Vorbereitung."""

    def __init__(self, name, base_url, models, active_model, running):
        self.name = name                  # "Ollama" | "LM Studio"
        self.base_url = base_url          # Voller Chat-Completions-Endpoint
        self.models = models or []        # Liste real installierter Modell-IDs
        self.active_model = active_model   # Vorausgewaehltes Modell
        self.running = running            # Server erreichbar?

    def __repr__(self):
        return (f"AIProviderStatus(name={self.name!r}, running={self.running}, "
                f"models={len(self.models)}, active={self.active_model!r}, "
                f"url={self.base_url!r})")


# ---------------------------------------------------------------------------
# Generische Helfer
# ---------------------------------------------------------------------------

def _http_json(url, timeout=2):
    """GET url, gibt (ok, json_or_None) zurueck. Niemals Exception nach aussen."""
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return True, r.json()
    except Exception:
        pass
    return False, None


def _wait_until(predicate, timeout_sec):
    """Pollt predicate() bis True oder Timeout. Gibt finalen bool zurueck."""
    import time
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.5)
    return predicate()


def _popen_hidden(args):
    """Startet einen Hintergrundprozess ohne Fenster, ohne zu blockieren."""
    return subprocess.Popen(
        args,
        creationflags=_CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )


def _run_hidden(args, timeout):
    """Fuehrt ein CLI-Kommando aus; gibt Ausgabe oder None bei Fehler zurueck."""
    try:
        res = subprocess.run(
            args, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            creationflags=_CREATE_NO_WINDOW, timeout=timeout,
        )
        output = (res.stdout or "") + (res.stderr or "")
        if res.returncode != 0:
            logger.debug(f"CLI-Aufruf fehlgeschlagen ({res.returncode}) {args}: {output}")
            return None
        return output
    except Exception as e:
        logger.debug(f"CLI-Aufruf fehlgeschlagen {args}: {e}")
        return None


def _is_embedding_model(model_id):
    """Embedding-Modelle taugen nicht fuer Chat — herausfiltern."""
    mid = model_id.lower()
    return "embed" in mid or "bert" in mid


def _match_preferred_model(installed, preferred):
    """Liefert nur einen echten Preferred-Match, niemals einen Fallback."""
    if not preferred:
        return ""
    chat_models = [m for m in installed if not _is_embedding_model(m)]
    pref = preferred.lower()
    if preferred in chat_models:
        return preferred
    for model in chat_models:
        if model.split(":")[0].lower() == pref or model.lower().startswith(pref):
            return model
    for model in chat_models:
        if pref in model.lower():
            return model
    return ""


def _pick_model(installed, preferred):
    """
    Waehlt das aktive Modell:
      1. preferred, falls exakt installiert
      2. preferred als Praefix-Match (Ollama-Tags: 'llama3' -> 'llama3:latest')
      3. erstes installiertes (Nicht-Embedding) Modell
    """
    chat_models = [m for m in installed if not _is_embedding_model(m)]
    preferred_match = _match_preferred_model(chat_models, preferred)
    if preferred_match:
        return preferred_match
    return chat_models[0] if chat_models else (installed[0] if installed else "")


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

_OLLAMA_HOST = "http://localhost:11434"


def _ollama_exe():
    return shutil.which("ollama") or os.path.expandvars(
        r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    )


def ollama_running():
    ok, _ = _http_json(_OLLAMA_HOST + "/api/tags")
    return ok


def ollama_models():
    """Gibt lokal installierte Chatmodelle zurueck, keine Embeddingmodelle."""
    ok, data = _http_json(_OLLAMA_HOST + "/api/tags")
    if not ok or not data:
        return []
    installed = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    return [model for model in installed if not _is_embedding_model(model)]


def ollama_active_model():
    """Gibt das aktuell im VRAM geladene Modell von Ollama zurueck oder ''."""
    ok, data = _http_json(_OLLAMA_HOST + "/api/ps")
    if ok and data and "models" in data:
        models = data["models"]
        if models:
            active = models[0].get("name", "")
            if active and not _is_embedding_model(active):
                return active
    return ""


def ollama_start():
    """Startet Ollama headless (ollama serve), GUI-App als Fallback. Bool zurueck."""
    if ollama_running():
        return True

    exe = _ollama_exe()
    if exe and os.path.exists(exe):
        # Headless: ollama serve. Wenn bereits ein Tray-Server laeuft, schlaegt
        # das mit 'address in use' fehl — egal, _wait_until erkennt den Server.
        try:
            _popen_hidden([exe, "serve"])
        except Exception as e:
            logger.warning(f"ollama serve Start fehlgeschlagen: {e}")
        if _wait_until(ollama_running, _WAIT_HEADLESS_SEC):
            return True

    # GUI-Fallback: Ollama Desktop-App startet ebenfalls den Server
    app = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama app.exe")
    if os.path.exists(app):
        try:
            subprocess.Popen([app])
        except Exception as e:
            logger.warning(f"Ollama GUI-Start fehlgeschlagen: {e}")
        return _wait_until(ollama_running, _WAIT_GUI_SEC)

    return ollama_running()


def ollama_pull(model, cancel_check=None):
    """Laedt ein Ollama-Modell (blockierend, grosser Download). Bool zurueck.

    cancel_check: optionale Callable ohne Argumente. Liefert sie True, wird
    der laufende Pull-Prozess terminiert (HPG-003: kooperativer Abbruch —
    vorher konnte der Pull bis 1800s unbeeinflussbar blockieren).
    """
    exe = _ollama_exe()
    if not exe or not os.path.exists(exe):
        return False
    logger.info(f"Ollama: pull {model} ...")
    if cancel_check is None:
        _run_hidden([exe, "pull", model], timeout=1800)  # bis 30 Min fuer grosse Modelle
    else:
        proc = None
        try:
            proc = subprocess.Popen(
                [exe, "pull", model],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
            )
            deadline = time.time() + 1800
            while proc.poll() is None:
                # Audit-Fix 2026-07-21: cancel_check() eigenes try — wirft der
                # Callback, wurde vorher der Pull-Prozess verwaist weitergefuehrt.
                try:
                    cancelled = bool(cancel_check())
                except Exception:
                    cancelled = True
                if cancelled or time.time() > deadline:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()  # Zombie vermeiden
                    logger.info(f"Ollama-Pull abgebrochen: {model}")
                    return False
                time.sleep(0.5)
        except Exception as e:
            logger.debug(f"Ollama-Pull fehlgeschlagen {model}: {e}")
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    pass
            return False
    return any(m.split(":")[0] == model.split(":")[0] for m in ollama_models())


def _prepare_ollama(preferred_model, cancel_check=None):
    if not ollama_start():
        return AIProviderStatus("Ollama", _OLLAMA_HOST + "/v1/chat/completions",
                                [], "", running=False)
    models = ollama_models()
    
    # Pruefen, was Ollama wirklich gerade im Speicher geladen hat
    active = ollama_active_model()
    preferred_match = _match_preferred_model(models, preferred_model)

    # Auto-Pull: exakt gewuenschtes Modell fehlt. Ein beliebiger installierter
    # Fallback darf diesen Download nicht unterdruecken.
    if preferred_model and not preferred_match:
        if ollama_pull(preferred_model, cancel_check=cancel_check):
            models = ollama_models()
            preferred_match = _match_preferred_model(models, preferred_model)
        elif cancel_check and cancel_check():
            raise InterruptedError("AI model download cancelled by user")

    active = preferred_match or (active if active in models else "")
    if not active:
        active = _pick_model(models, preferred_model)

    return AIProviderStatus(
        "Ollama", _OLLAMA_HOST + "/v1/chat/completions",
        models, active, running=True,
    )


# ---------------------------------------------------------------------------
# LM Studio
# ---------------------------------------------------------------------------

def _lms_exe():
    return shutil.which("lms") or os.path.expandvars(
        r"%USERPROFILE%\.lmstudio\bin\lms.exe"
    )


def lms_detect_port():
    """
    Liest den aktiven LM-Studio-Server-Port via 'lms server status'.
    LM Studio laeuft NICHT immer auf 1234 (user-konfigurierbar) — daher dynamisch.
    Gibt int-Port oder None zurueck.
    """
    exe = _lms_exe()
    if not exe or not os.path.exists(exe):
        return None
    out = _run_hidden([exe, "server", "status"], timeout=10) or ""
    low = out.lower()
    # Audit-Fix 2026-07-21: "not running" enthaelt den Substring "running" —
    # explizit ausschliessen. Port zusaetzlich aus "host:port"-Form lesen, falls
    # die CLI-Ausgabe das Wort "port" nicht enthaelt.
    if "running" in low and "not running" not in low:
        m = re.search(r"port\s+(\d+)", low) or re.search(r":(\d{2,5})\b", out)
        if m:
            return int(m.group(1))
    return None


def lms_start():
    """
    Startet LM-Studio-Server headless ('lms server start'), GUI-Fallback.
    Gibt aktiven Port (int) oder None zurueck.
    """
    port = lms_detect_port()
    if port:
        return port

    exe = _lms_exe()
    if exe and os.path.exists(exe):
        _run_hidden([exe, "server", "start"], timeout=25)
        port = lms_detect_port()
        if port:
            return port

    # GUI-Fallback: LM Studio Desktop-App starten, dann erneut Port suchen
    for cand in (
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\lm-studio\LM Studio.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\LM-Studio\LM Studio.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\LM Studio\LM Studio.exe"),
    ):
        if os.path.exists(cand):
            try:
                subprocess.Popen([cand])
            except Exception as e:
                logger.warning(f"LM Studio GUI-Start fehlgeschlagen: {e}")
            if _wait_until(lambda: lms_detect_port() is not None, _WAIT_GUI_SEC):
                return lms_detect_port()
            break
    return None


def lms_models(port):
    """Gibt lokal installierte LM-Studio-Chatmodelle zurueck."""
    ok, data = _http_json(f"http://localhost:{port}/api/v1/models")
    if not ok or not data:
        return []
    inventory = data.get("models", [])
    chat_models = [
        model.get("key", "")
        for model in inventory
        if model.get("type") == "llm"
        and model.get("key")
        and not _is_embedding_model(model.get("key", ""))
    ]
    logger.info(
        "LM Studio: %d/%d Chatmodelle verfuegbar",
        len(chat_models), len(inventory),
    )
    return chat_models


def lms_load(model, port):
    """Laedt ein bereits heruntergeladenes LM-Studio-Modell in den Speicher."""
    exe = _lms_exe()
    if not exe or not os.path.exists(exe):
        return False
    logger.info(f"LM Studio: load {model} ...")
    return _run_hidden([exe, "load", model, "--yes"], timeout=180) is not None


def lms_get(model, cancel_check=None):
    """Laedt ein LM-Studio-Modell; optional kooperativ abbrechbar."""
    exe = _lms_exe()
    if not exe or not os.path.exists(exe):
        return False
    logger.info(f"LM Studio: get {model} ...")
    if cancel_check is None:
        return _run_hidden([exe, "get", model, "--yes"], timeout=1800) is not None

    proc = None
    try:
        proc = subprocess.Popen(
            [exe, "get", model, "--yes"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW,
        )
        deadline = time.monotonic() + 1800
        while proc.poll() is None:
            try:
                cancelled = bool(cancel_check())
            except Exception:
                cancelled = True
            if cancelled or time.monotonic() >= deadline:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                logger.info(f"LM-Studio-Download abgebrochen: {model}")
                return False
            time.sleep(0.5)
        return proc.returncode == 0
    except Exception as error:
        logger.debug(f"LM-Studio-Download fehlgeschlagen {model}: {error}")
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                pass
        return False


def _prepare_lmstudio(preferred_model, cancel_check=None):
    port = lms_start()
    if not port:
        return AIProviderStatus("LM Studio", config.AI_API_URL_LMSTUDIO,
                                [], "", running=False)

    base = f"http://localhost:{port}/v1/chat/completions"
    models = lms_models(port)
    preferred_match = _match_preferred_model(models, preferred_model)

    # Auto-Get: gewuenschtes Modell weder geladen noch gelistet -> herunterladen
    if preferred_model and not preferred_match:
        if lms_get(preferred_model, cancel_check=cancel_check):
            models = lms_models(port)
            preferred_match = _match_preferred_model(models, preferred_model)
        elif cancel_check and cancel_check():
            raise InterruptedError("AI model download cancelled by user")

    active = preferred_match or _pick_model(models, preferred_model)

    # Modell in den Speicher laden (LM Studio bedient /v1 erst nach load)
    if active and not lms_load(active, port):
        active = ""

    return AIProviderStatus("LM Studio", base, models, active, running=True)


# ---------------------------------------------------------------------------
# Oeffentliche High-Level-API
# ---------------------------------------------------------------------------

def prepare_provider(name, preferred_model=None, cancel_check=None):
    """Bereitet EINEN benannten Provider vor (Start + Modell-Liste)."""
    if name == "LM Studio":
        return _prepare_lmstudio(preferred_model, cancel_check=cancel_check)
    return _prepare_ollama(preferred_model, cancel_check=cancel_check)


def detect_and_start(preferred=None, preferred_model=None, cancel_check=None):
    """
    Auto-detect beide Provider. Startet den ersten verfuegbaren.

    Reihenfolge: bevorzugter Provider zuerst, sonst Ollama -> LM Studio.
    Gibt AIProviderStatus des erfolgreichen Providers zurueck, oder einen
    Status mit running=False, wenn keiner verfuegbar ist.
    """
    order = ["Ollama", "LM Studio"]
    if preferred in order:
        order = [preferred] + [p for p in order if p != preferred]

    last = None
    for prov in order:
        if cancel_check and cancel_check():
            raise InterruptedError("AI provider detection cancelled by user")
        status = prepare_provider(
            prov, preferred_model, cancel_check=cancel_check
        )
        last = status
        if status.running and status.models and status.active_model:
            logger.info(f"AI-Provider bereit: {status}")
            return status
        logger.info(f"AI-Provider {prov} nicht nutzbar: {status}")

    if last:
        return AIProviderStatus(
            last.name, last.base_url, last.models, "", running=False
        )
    return AIProviderStatus(
        "Ollama", _OLLAMA_HOST + "/v1/chat/completions", [], "", running=False
    )

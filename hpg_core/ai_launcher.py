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
    """Fuehrt ein CLI-Kommando aus und gibt stdout (str) zurueck; '' bei Fehler."""
    try:
        res = subprocess.run(
            args, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            creationflags=_CREATE_NO_WINDOW, timeout=timeout,
        )
        return (res.stdout or "") + (res.stderr or "")
    except Exception as e:
        logger.debug(f"CLI-Aufruf fehlgeschlagen {args}: {e}")
        return ""


def _is_embedding_model(model_id):
    """Embedding-Modelle taugen nicht fuer Chat — herausfiltern."""
    mid = model_id.lower()
    return "embed" in mid or "bert" in mid


def _pick_model(installed, preferred):
    """
    Waehlt das aktive Modell:
      1. preferred, falls exakt installiert
      2. preferred als Praefix-Match (Ollama-Tags: 'llama3' -> 'llama3:latest')
      3. erstes installiertes (Nicht-Embedding) Modell
    """
    chat_models = [m for m in installed if not _is_embedding_model(m)]
    if preferred:
        pref = preferred.lower()
        if preferred in chat_models:
            return preferred
        # Praefix-Match (Ollama-Tags: 'llama3' -> 'llama3:latest')
        for m in chat_models:
            if m.split(":")[0].lower() == pref or m.lower().startswith(pref):
                return m
        # Substring-Match (LM-Studio 'provider/model': 'gemma' -> 'google/gemma-4-e4b')
        for m in chat_models:
            if pref in m.lower():
                return m
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
    ok, data = _http_json(_OLLAMA_HOST + "/api/tags")
    if not ok or not data:
        return []
    return [m.get("name", "") for m in data.get("models", []) if m.get("name")]


def ollama_active_model():
    """Gibt das aktuell im VRAM geladene Modell von Ollama zurueck oder ''."""
    ok, data = _http_json(_OLLAMA_HOST + "/api/ps")
    if ok and data and "models" in data:
        models = data["models"]
        if models:
            return models[0].get("name", "")
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


def ollama_pull(model):
    """Laedt ein Ollama-Modell (blockierend, grosser Download). Bool zurueck."""
    exe = _ollama_exe()
    if not exe or not os.path.exists(exe):
        return False
    logger.info(f"Ollama: pull {model} ...")
    _run_hidden([exe, "pull", model], timeout=1800)  # bis 30 Min fuer grosse Modelle
    return any(m.split(":")[0] == model.split(":")[0] for m in ollama_models())


def _prepare_ollama(preferred_model):
    if not ollama_start():
        return AIProviderStatus("Ollama", _OLLAMA_HOST + "/v1/chat/completions",
                                [], "", running=False)
    models = ollama_models()
    
    # Pruefen, was Ollama wirklich gerade im Speicher geladen hat
    active = ollama_active_model()
    if not active or active not in models:
        # Falls nichts geladen ist (oder das geladene nicht in der Liste der installierten ist),
        # waehle das bevorzugte Modell oder Fallback
        active = _pick_model(models, preferred_model)

    # Auto-Pull: gewuenschtes Modell fehlt -> ziehen (nur wenn ueberhaupt eins gewuenscht)
    if preferred_model and not active:
        if ollama_pull(preferred_model):
            models = ollama_models()
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
    out = _run_hidden([exe, "server", "status"], timeout=10)
    if "running" in out.lower():
        m = re.search(r"port\s+(\d+)", out)
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
    ok, data = _http_json(f"http://localhost:{port}/v1/models")
    if not ok or not data:
        return []
    return [m.get("id", "") for m in data.get("data", []) if m.get("id")]


def lms_load(model, port):
    """Laedt ein bereits heruntergeladenes LM-Studio-Modell in den Speicher."""
    exe = _lms_exe()
    if not exe or not os.path.exists(exe):
        return False
    logger.info(f"LM Studio: load {model} ...")
    _run_hidden([exe, "load", model, "--yes"], timeout=180)
    return True


def lms_get(model):
    """Laedt ein LM-Studio-Modell aus dem Hub herunter (blockierend, gross)."""
    exe = _lms_exe()
    if not exe or not os.path.exists(exe):
        return False
    logger.info(f"LM Studio: get {model} ...")
    _run_hidden([exe, "get", model, "--yes"], timeout=1800)
    return True


def _prepare_lmstudio(preferred_model):
    port = lms_start()
    if not port:
        return AIProviderStatus("LM Studio", config.AI_API_URL_LMSTUDIO,
                                [], "", running=False)

    base = f"http://localhost:{port}/v1/chat/completions"
    models = lms_models(port)
    active = _pick_model(models, preferred_model)

    # Auto-Get: gewuenschtes Modell weder geladen noch gelistet -> herunterladen
    if preferred_model and not active:
        if lms_get(preferred_model):
            models = lms_models(port)
            active = _pick_model(models, preferred_model)

    # Modell in den Speicher laden (LM Studio bedient /v1 erst nach load)
    if active:
        lms_load(active, port)

    return AIProviderStatus("LM Studio", base, models, active, running=True)


# ---------------------------------------------------------------------------
# Oeffentliche High-Level-API
# ---------------------------------------------------------------------------

def prepare_provider(name, preferred_model=None):
    """Bereitet EINEN benannten Provider vor (Start + Modell-Liste)."""
    if name == "LM Studio":
        return _prepare_lmstudio(preferred_model)
    return _prepare_ollama(preferred_model)


def detect_and_start(preferred=None, preferred_model=None):
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
        status = prepare_provider(prov, preferred_model)
        last = status
        if status.running and status.models:
            logger.info(f"AI-Provider bereit: {status}")
            return status
        logger.info(f"AI-Provider {prov} nicht nutzbar: {status}")

    return last or AIProviderStatus("Ollama", _OLLAMA_HOST + "/v1/chat/completions",
                                    [], "", running=False)

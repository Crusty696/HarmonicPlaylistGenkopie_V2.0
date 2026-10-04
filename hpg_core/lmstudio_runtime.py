"""Explizite lokale LM-Studio-GPU-Konfiguration, getrennt von Laufzeitnachweisen."""
from __future__ import annotations

import json
import math
import threading
import uuid
from urllib.parse import urlparse

TARGET_GPU = "AMD Radeon RX 7800 XT"
CONTEXT_TOKENS = 2048
RESERVE_BYTES = 2 * 1024**3
_OWNED_INSTANCES = {}
_LOAD_LOCK = threading.Lock()
_QUALIFICATIONS = {}
_QUALIFICATION_LOCK = threading.Lock()
_INSTANCE_QUALIFICATION_KEYS = {}


def _qualification_key(model_key, url, *, load_profile=None):
    """Sessionnachweis an echten Antwortvertrag und angefordertes GPU-Profil binden."""
    import hashlib
    from . import config
    from .ai_engine import AI_JSON_SCHEMA, AI_PROMPT_VERSION
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in {"127.0.0.1", "::1"}:
        host = "localhost"
    endpoint = (parsed.scheme.lower(), host, parsed.port, parsed.path.rstrip("/"))
    contract = {"schema": AI_JSON_SCHEMA, "prompt": config.AI_SYSTEM_PROMPT,
                "prompt_version": AI_PROMPT_VERSION, "context": CONTEXT_TOKENS,
                "gpu": TARGET_GPU, "runtime": "vulkan-2.51.0",
                "load_profile": load_profile,
                "offload": 1.0, "strict_vram": True, "kv_gpu": True,
                "max_tokens": config.AI_MAX_TOKENS, "temperature": 0, "seed": 0}
    digest = hashlib.sha256(json.dumps(contract, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return endpoint, model_key, digest


def record_qualification(model_key, url, passed, detail, *, qualification_key=None):
    key = qualification_key or _qualification_key(model_key, url)
    with _QUALIFICATION_LOCK:
        _QUALIFICATIONS[key] = (bool(passed), str(detail))


def require_not_failed(model_key, url, *, qualification_key=None):
    key = qualification_key or _qualification_key(model_key, url)
    with _QUALIFICATION_LOCK:
        result = _QUALIFICATIONS.get(key)
    if result is not None and not result[0]:
        raise ValueError(f"KI-Antwortvertrag bereits fehlgeschlagen: {result[1]}. Vor erneutem Analyselauf ausdrücklich 'Testen' verwenden.")


def instance_qualification_key(identifier):
    with _QUALIFICATION_LOCK:
        return _INSTANCE_QUALIFICATION_KEYS.get(identifier)


def select_target_gpu(survey):
    """Identitaet aus dem Runtime-Survey verwenden, niemals Listenpositionen."""
    matches = []
    for engine in survey.get("engines", []):
        if engine.get("name") != "llama.cpp-win-x86_64-vulkan-avx2":
            continue
        result = engine.get("hardwareSurvey", {}).get("gpuSurveyResult", {})
        if result.get("result", {}).get("code") != "success":
            continue
        devices = result.get("gpuInfo", [])
        for gpu in devices:
            if gpu.get("name") != TARGET_GPU or gpu.get("integrationType") != "discrete":
                continue
            ident, capacity = gpu.get("deviceId"), gpu.get("dedicatedMemoryCapacityBytes")
            if type(ident) is not int or type(capacity) is not int or capacity <= RESERVE_BYTES:
                continue
            ids = [item.get("deviceId") for item in devices]
            if any(type(value) is not int for value in ids) or len(set(ids)) != len(ids):
                raise ValueError("Mehrdeutige GPU-IDs im Runtime-Survey")
            visible = engine.get("visibleDevicesConfig", {}).get("visibleDevices", ids)
            if ident not in visible:
                raise ValueError("RX 7800 XT ist in der Runtime nicht sichtbar")
            matches.append({"device_id": ident, "disabled_ids": sorted(i for i in ids if i != ident),
                            "vram_bytes": capacity, "name": TARGET_GPU,
                            "runtime": engine["name"], "runtime_version": engine.get("version"),
                            "visible_devices": visible,
                            "changes_order": engine.get("visibleDevicesConfig", {}).get("changesOrder", False),
                            "survey_ids": ids})
    if len(matches) != 1:
        raise ValueError("RX 7800 XT nicht eindeutig in der Vulkan-Runtime erkannt")
    return matches[0]


def model_rejection_reason(record, vram_bytes):
    """Konservative technische Vorauswahl; kein Nachweis musikalischer Kompetenz."""
    if record.get("type") != "llm" or record.get("format") != "gguf":
        return "Kein lokales GGUF-Textmodell"
    architecture = record.get("architecture")
    if not architecture or architecture in {"ltxv", "clip", "bert", "t5", "whisper"}:
        return "Keine geeignete Textgenerierungs-Architektur nachgewiesen"
    capabilities = record.get("capabilities")
    if not isinstance(capabilities, dict) or capabilities.get("trained_for_tool_use") is not True:
        return "Strukturierte Instruktionsfähigkeit nicht ausgewiesen"
    size = record.get("size_bytes")
    if type(size) is not int or not 0 < size <= vram_bytes - RESERVE_BYTES:
        return "Modellgröße unbekannt oder kein Platz für Kontext und Laufzeitreserve"
    return ""


def runtime_target(host="127.0.0.1", port=1234):
    from .ai_launcher import _lms_exe, _run_hidden
    executable = _lms_exe()
    if not executable:
        raise ValueError("LM-Studio-CLI fehlt für die GPU-Erkennung")
    raw = _run_hidden([executable, "runtime", "survey", "--json", "--host", host, "--port", str(port)], timeout=15)
    if raw is None:
        raise ValueError("LM-Studio-GPU-Survey fehlgeschlagen")
    return select_target_gpu(json.loads(raw))


def requested_load_config(target):
    # LM Studio 0.4.25+1 uebersetzt Survey-Geraete-IDs selbst durch die
    # visibleDevices- und disabledGpus-Abbildungen. Nicht doppelt umnummerieren.
    # Quellcodebeleg und Runtime-Grenze: docs/IMPLEMENTATION_2026-10-04.md.
    if target.get("runtime_version") != "2.51.0":
        raise ValueError("GPU-Indexzuordnung dieser Runtime-Version nicht nachgewiesen; kein Modell geladen")
    visible, ids = target.get("visible_devices", []), target.get("survey_ids", [])
    if not visible or len(set(visible)) != len(visible) or any(i not in ids for i in visible):
        raise ValueError("Mehrdeutige GPU-Indexzuordnung; kein Modell geladen")
    return {"contextLength": CONTEXT_TOKENS,
            "gpu": {"ratio": 1.0, "mainGpu": target["device_id"],
                    "splitStrategy": "favorMainGpu", "disabledGpus": target["disabled_ids"]},
            "gpuStrictVramCap": True, "offloadKVCacheToGpu": True}


def require_matching_config(actual, expected):
    """Ein fehlender Readback ist kein Erfolg und kein Grund fuer CPU-Fallback."""
    for key in ("contextLength", "gpuStrictVramCap", "offloadKVCacheToGpu"):
        if actual.get(key) != expected[key]:
            raise ValueError(f"LM Studio bestätigt {key} nicht")
    for key in ("ratio", "mainGpu", "splitStrategy"):
        if actual.get("gpu", {}).get(key) != expected["gpu"][key]:
            raise ValueError(f"LM Studio bestätigt GPU-{key} nicht")
    if sorted(actual.get("gpu", {}).get("disabledGpus", [])) != expected["gpu"]["disabledGpus"]:
        raise ValueError("LM Studio bestätigt den Ausschluss anderer GPUs nicht")


def prepare_gpu_model(model_key, url, *, cancel_check=None, explicit_retest=False):
    """Eigene Instanz konfigurieren; fremde Modelle niemals entladen/umstellen.

    Config-Readback bestaetigt die Anforderung, nicht die physische Ausfuehrung.
    Der Aufrufer darf daraus keinen Laufzeitnachweis oder Audiofaehigkeit ableiten.
    """
    while not _LOAD_LOCK.acquire(timeout=.1):
        if cancel_check and cancel_check():
            raise InterruptedError("KI-Vorbereitung abgebrochen")
    try:
        return _prepare_gpu_model(model_key, url, cancel_check=cancel_check, explicit_retest=explicit_retest)
    finally:
        _LOAD_LOCK.release()


def _prepare_gpu_model(model_key, url, *, cancel_check=None, explicit_retest=False):
    import lmstudio as lms
    from .ai_launcher import _http_json, _lms_exe, _run_hidden
    parsed = urlparse(url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or not parsed.port:
        raise ValueError("GPU-Steuerung nur für einen lokalen LM-Studio-Endpunkt")
    target = runtime_target(parsed.hostname, parsed.port)
    ok, inventory = _http_json(f"http://{parsed.netloc}/api/v1/models", timeout=5)
    records = [m for m in (inventory or {}).get("models", []) if m.get("key") == model_key]
    if not ok or len(records) != 1:
        raise ValueError("Ausgewähltes Modell nicht eindeutig installiert")
    reason = model_rejection_reason(records[0], target["vram_bytes"])
    if reason:
        raise ValueError(reason)
    expected = requested_load_config(target)
    # Vor Netzwerk-Inferenz einfrieren: derselbe Schluessel gilt bis zum Record,
    # auch falls Defaults waehrend der Anfrage geaendert werden.
    qualification_key = _qualification_key(model_key, url, load_profile=expected)
    if not explicit_retest:
        require_not_failed(model_key, url, qualification_key=qualification_key)
    def checkpoint():
        if cancel_check and cancel_check():
            raise InterruptedError("KI-Vorbereitung abgebrochen")
    def validate(handle, identifier):
        info = handle.get_info()
        if handle.identifier != identifier or info.model_key != model_key:
            raise ValueError("LM-Studio-Instanz hat eine andere Modellidentität")
        require_matching_config(handle.get_load_config().to_dict(), expected)
    checkpoint()
    with lms.Client(api_host=parsed.netloc) as client:
        ownership_key = (parsed.netloc, model_key)
        identifier = _OWNED_INSTANCES.get(ownership_key)
        existing = [m for m in client.llm.list_loaded() if identifier and m.identifier == identifier]
        checkpoint()
        if existing:
            validate(existing[0], identifier)
            checkpoint()
            with _QUALIFICATION_LOCK:
                _INSTANCE_QUALIFICATION_KEYS[identifier] = qualification_key
            return identifier
        identifier = "hpg-" + uuid.uuid4().hex
        # Die CLI-Schaetzung ist nur ein zusaetzlicher konservativer Vorabfilter.
        # Sie ist kein Beleg fuer die tatsaechliche Belegung der Ziel-GPU.
        estimate = _run_hidden([_lms_exe(), "load", model_key, "--gpu", "max",
                                "--context-length", str(CONTEXT_TOKENS), "--parallel", "4",
                                "--estimate-only", "--host", parsed.hostname,
                                "--port", str(parsed.port)], timeout=30)
        import re
        match = re.search(r"Estimated GPU Memory:\s*([0-9.]+)\s*(GiB|MiB)", estimate or "")
        if not match:
            raise ValueError("Keine auswertbare GPU-Speicherschätzung; Modell nicht geladen")
        needed = float(match[1]) * (1024**3 if match[2] == "GiB" else 1024**2)
        if not math.isfinite(needed) or needed + RESERVE_BYTES > target["vram_bytes"]:
            raise ValueError("Modell und Kontext überschreiten das dedizierte VRAM-Budget")
        checkpoint()
        handle = None
        try:
            # SDK 1.5 unterdrueckt Exceptions aus Progress-Callbacks. Daher
            # keinen scheinbaren Sofortabbruch vortaeuschen: nach Rueckkehr
            # pruefen und die eigene Instanz bei Cancel wieder freigeben.
            handle = client.llm.load_new_instance(model_key, identifier, ttl=300, config=expected)
            validate(handle, identifier)
            checkpoint()
        except Exception:
            # Eine fehlgeschlagene SDK-Anfrage kann bereits publiziert haben.
            # Ausschliesslich die UUID dieses Ladeauftrags suchen und entladen.
            try:
                owned = ([handle] if handle is not None else
                         [m for m in client.llm.list_loaded() if m.identifier == identifier])
                for item in owned:
                    if item.identifier == identifier:
                        item.unload()
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Eigene KI-Instanz konnte nicht bereinigt werden")
            raise
        _OWNED_INSTANCES[ownership_key] = identifier
        with _QUALIFICATION_LOCK:
            _INSTANCE_QUALIFICATION_KEYS[identifier] = qualification_key
        return identifier

"""Quellgebundene Laufzeitpolitik der automatischen Zusatzanalyse.

Diese Hülle verändert weder Modellparameter noch Ergebnisidentitäten. Erst
die Analyseintegration aktiviert sie; direkte Clientaufrufe bleiben unberührt.
Trackdeadline, Prozessgrenze und CPU-Fallback verbleiben beim normalen Client.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import math
import os
from pathlib import Path

from .feature_audio import source_identity


MIN_STEM_TIMEOUT_SECONDS = 240.0
MAX_STEM_TIMEOUT_SECONDS = 900.0
STEM_STARTUP_RESERVE_SECONDS = 60.0


def _positive_finite(value):
    if type(value) not in (int, float):
        raise ValueError('Laufzeitwert muss eine endliche positive Zahl sein')
    try:
        converted = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError('Ungültiger Laufzeitwert') from error
    if not math.isfinite(converted) or converted <= 0:
        raise ValueError('Laufzeitwert muss eine endliche positive Zahl sein')
    return converted


def stem_timeout_seconds(duration):
    """Begrenztes Startbudget; kein Versprechen über die Modellgeschwindigkeit."""
    duration = _positive_finite(duration)
    return min(MAX_STEM_TIMEOUT_SECONDS,
               max(MIN_STEM_TIMEOUT_SECONDS, STEM_STARTUP_RESERVE_SECONDS + duration))


@dataclass(frozen=True)
class _Binding:
    path: str
    identity: tuple
    timeout_s: float


_binding = ContextVar('hpg_automatic_deep_feature_budget', default=None)


def _source(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('Absolute Audioquelle erforderlich')
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError('Audioquelle muss eine Datei sein')
    return os.path.normcase(str(resolved)), tuple(source_identity(resolved))


@contextmanager
def automatic_budget(track):
    """Nur die aktuelle Quelle freigeben; äußeren Kontext auch bei Fehlern erhalten."""
    try:
        timeout = stem_timeout_seconds(track.duration)
        path, identity = _source(track.filePath)
        current = _Binding(path, identity, timeout)
    except (AttributeError, OSError, TypeError, ValueError, RuntimeError):
        # Ungültige innere Aufrufe dürfen auch keine äußere Freigabe erben.
        current = None
    token = _binding.set(current)
    try:
        yield
    finally:
        _binding.reset(token)


class _AutomaticClient:
    def __init__(self, client, binding):
        self._client = client
        self._binding = binding

    def __getattr__(self, name):
        return getattr(self._client, name)

    def deep_features(self, parameters, *, timeout_s=MIN_STEM_TIMEOUT_SECONDS):
        timeout = _positive_finite(timeout_s)
        binding = self._binding
        # Nur das unveränderte Standardbudget des automatischen Attach-Aufrufs
        # ersetzen. Andere explizite Fristen und Embeddings bleiben erhalten.
        if (_binding.get() is binding and timeout == MIN_STEM_TIMEOUT_SECONDS
                and type(parameters) is dict and parameters.get('kind') == 'stems'):
            try:
                identity = parameters.get('identity')
                valid_identity = (type(identity) is list and len(identity) == 5
                                  and all(type(value) is int for value in identity))
                path, current_identity = _source(parameters.get('path'))
                if (valid_identity and path == binding.path
                        and tuple(identity) == binding.identity == current_identity):
                    timeout = binding.timeout_s
            except (OSError, TypeError, ValueError, RuntimeError):
                pass  # Quellabweichung gibt niemals mehr Laufzeit frei.
        return self._client.deep_features(parameters, timeout_s=timeout)


def client_for_context(client):
    """Kurzlebigen Proxy liefern, ohne den gespeicherten Poolclient zu verändern."""
    binding = _binding.get()
    return client if binding is None else _AutomaticClient(client, binding)


def attach(track):
    """Automatische Erst- und Deltaanalyse mit demselben Laufzeitvertrag verbinden."""
    from . import deep_features

    with automatic_budget(track):
        return deep_features.attach(track)

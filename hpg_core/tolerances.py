"""Laedt die Uebergangs-Toleranzen: Defaults, mitgeliefertes JSON, Override.

Gewichte sind Daten, keine Konstanten im Quelltext. Eine Aenderung erfordert
keine Neuanalyse, nur ein Neuberechnen der Scores.
"""
from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path

from .genres import CANONICAL_GENRES, GENRE_TRANSITION_TOLERANCES

logger = logging.getLogger(__name__)

_MITGELIEFERT = Path(__file__).parent / "data" / "transition_tolerances.json"

_cache: dict[str, dict] | None = None


def _override_pfad() -> Path:
    """Nutzer-Override; HPG_TOLERANCES_FILE hat Vorrang (auch fuer Tests)."""
    explizit = os.environ.get("HPG_TOLERANCES_FILE")
    if explizit:
        return Path(explizit)
    basis = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(basis) / "HPG" / "transition_tolerances.json"


def _merge(ziel: dict[str, dict], quelle: dict) -> None:
    """Uebernimmt nur bekannte Genres und ueberschreibt einzelne Schluessel."""
    for genre, werte in (quelle or {}).items():
        if genre in ziel and isinstance(werte, dict):
            ziel[genre].update(werte)


def load_tolerances() -> dict[str, dict]:
    """Defaults, darueber das mitgelieferte JSON, darueber der Override.

    Ein defektes JSON darf den Start nicht verhindern — der Fehler wird
    protokolliert und die bis dahin gueltigen Werte bleiben bestehen.
    """
    werte = copy.deepcopy(GENRE_TRANSITION_TOLERANCES)
    for pfad in (_MITGELIEFERT, _override_pfad()):
        try:
            if pfad.is_file():
                _merge(werte, json.loads(pfad.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning(f"Toleranz-Datei {pfad} nicht lesbar: {exc}")
    return werte


def get_tolerances(genre: str) -> dict:
    """Toleranzen eines Genres; unbekannte Genres bekommen das erste kanonische."""
    global _cache
    if _cache is None:
        _cache = load_tolerances()
    return _cache.get(genre) or _cache[CANONICAL_GENRES[0]]


def reset_cache() -> None:
    """Verwirft den Toleranz-Cache — nach dem Aendern von Gewichten aufrufen."""
    global _cache
    _cache = None


def write_override(gewichte: dict[str, float]) -> None:
    """Schreibt Gewichte fuer alle Genres in die Override-Datei.

    Die vier neuen Gewichte werden gesetzt, die vier bestehenden anteilig so
    skaliert, dass die Summe 1.0 bleibt.
    """
    neu_summe = sum(gewichte.values())
    if neu_summe >= 1.0:
        raise ValueError(f"Neue Gewichte summieren auf {neu_summe}, muss < 1.0 sein")
    rest = 1.0 - neu_summe
    basis = GENRE_TRANSITION_TOLERANCES[CANONICAL_GENRES[0]]
    alt_keys = ("harmonic_weight", "bpm_weight", "energy_weight", "genre_weight")
    alt_summe = sum(basis[k] for k in alt_keys)
    daten = {}
    for genre in CANONICAL_GENRES:
        eintrag = dict(gewichte)
        for k in alt_keys:
            eintrag[k] = basis[k] / alt_summe * rest
        daten[genre] = eintrag
    pfad = _override_pfad()
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, indent=2), encoding="utf-8")

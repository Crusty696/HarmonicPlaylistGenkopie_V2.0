"""Kandidaten-Praeferenzen aus dem Hoertest (Spec 2026-08-21, Abschnitt 3).

`fit --modus kandidaten` schreibt hpg_core/data/candidate_preferences.json:
je kanonischem Genre die zehn `kandidaten_*_weight` (Summe 1.0) fuer die
Paar-Bewertung (pair_candidates.score_pair) und `schema_rang` (Rangfolge der
Schemata, Teil 4). Aufbau wie tolerances.py: mitgelieferte Datei, dann
Override unter %LOCALAPPDATA%/HPG (oder HPG_CANDIDATE_PREFERENCES_FILE).
Fehlt alles, liefern die Funktionen None/[] und pair_candidates nimmt die
Toleranzen — es gibt keinen stillen Default.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .genres import CANONICAL_GENRES

logger = logging.getLogger(__name__)

GEWICHT_SCHLUESSEL = tuple(
    f"kandidaten_{f}_weight" for f in (
        "harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre", "mood",
        "loudness", "structure",
    )
)
_MITGELIEFERT = Path(__file__).parent / "data" / "candidate_preferences.json"
_cache: dict | None = None


def _override_pfad() -> Path:
    env = os.environ.get("HPG_CANDIDATE_PREFERENCES_FILE")
    if env:
        return Path(env)
    basis = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".hpg")
    return Path(basis) / "HPG" / "candidate_preferences.json"


def _lies(pfad: Path) -> dict:
    if not pfad.is_file():
        return {}
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("candidate_preferences nicht lesbar (%s): %s", pfad, exc)
        return {}
    return daten if isinstance(daten, dict) else {}


def _gueltige_gewichte(eintrag: dict) -> dict | None:
    """Alle zehn Schluessel vorhanden, numerisch, >= 0, Summe 1.0 (+-1e-6)."""
    try:
        werte = {k: float(eintrag[k]) for k in GEWICHT_SCHLUESSEL}
    except (KeyError, TypeError, ValueError):
        return None
    if any(v < 0.0 for v in werte.values()) or abs(sum(werte.values()) - 1.0) > 1e-6:
        return None
    return werte


def load_candidate_preferences() -> dict:
    """Liefert {genre: {"gewichte": dict|None, "schema_rang": list}} fuer
    kanonische Genres; ungueltige Gewichte werden geloggt und verworfen."""
    global _cache
    if _cache is not None:
        return _cache
    roh: dict = {}
    for quelle in (_MITGELIEFERT, _override_pfad()):
        for genre, eintrag in _lies(quelle).items():
            if genre in CANONICAL_GENRES and isinstance(eintrag, dict):
                roh.setdefault(genre, {}).update(eintrag)
    ergebnis: dict = {}
    for genre, eintrag in roh.items():
        gewichte = _gueltige_gewichte(eintrag)
        if gewichte is None and any(k in eintrag for k in GEWICHT_SCHLUESSEL):
            logger.warning("candidate_preferences: Gewichte fuer %s ungueltig (Summe != 1.0 "
                           "oder Schluessel fehlen) — ignoriert", genre)
        rang = [s for s in eintrag.get("schema_rang", []) if isinstance(s, str)]
        ergebnis[genre] = {"gewichte": gewichte, "schema_rang": rang}
    _cache = ergebnis
    return ergebnis


def kandidaten_gewichte(genre: str) -> dict | None:
    return load_candidate_preferences().get(genre, {}).get("gewichte")


def schema_rangfolge(genre: str) -> list[str]:
    return list(load_candidate_preferences().get(genre, {}).get("schema_rang", []))


def reset_cache() -> None:
    global _cache
    _cache = None

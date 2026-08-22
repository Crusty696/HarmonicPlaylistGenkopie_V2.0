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
    # json.loads liefert jeden JSON-Wurzeltyp — eine Liste, eine Zahl, null.
    # Ohne diesen Guard wirft `.items()` einen AttributeError, den der
    # Aufrufer nicht faengt, und die erste Playlist-Generierung stirbt.
    if not isinstance(quelle, dict):
        raise ValueError(f"Toleranz-Datei ist kein Objekt, sondern {type(quelle).__name__}")
    for genre, werte in quelle.items():
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
        except (json.JSONDecodeError, OSError, ValueError,
                TypeError, AttributeError) as exc:
            logger.warning(f"Toleranz-Datei {pfad} nicht lesbar: {exc}")
    return werte


def get_tolerances(genre: str) -> dict:
    """Toleranzen eines Genres; unbekannte Genres bekommen das erste kanonische."""
    global _cache
    if _cache is None:
        _cache = load_tolerances()
    return _cache.get(genre) or _cache[CANONICAL_GENRES[0]]


def entferne_override() -> bool:
    """Loescht die Nutzer-Override-Datei; True, wenn eine da war.

    Zuruecksetzen heisst LOESCHEN, nicht Defaults schreiben: der Override
    liegt in der Ladekette ueber den mitgelieferten gelernten Werten, ein
    geschriebener Default wuerde sie also dauerhaft verdecken.
    """
    pfad = _override_pfad()
    try:
        if pfad.is_file():
            pfad.unlink()
            return True
    except OSError as exc:
        logger.warning(f"Override-Datei {pfad} nicht loeschbar: {exc}")
    return False


def reset_cache() -> None:
    """Verwirft den Toleranz-Cache — nach dem Aendern von Gewichten aufrufen."""
    global _cache
    _cache = None
    _leere_paar_cache()


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
    pfad = _override_pfad()
    vorhanden = _lies_override(pfad)
    daten = {}
    for genre in CANONICAL_GENRES:
        # Kandidaten-Gewichte (kandidaten_*_weight, Teil 4) liegen in derselben
        # Datei und muessen einen Track-Regler-Schreibvorgang ueberleben.
        eintrag = {k: v for k, v in vorhanden.get(genre, {}).items() if k.startswith("kandidaten_")}
        eintrag.update(gewichte)
        for k in alt_keys:
            eintrag[k] = basis[k] / alt_summe * rest
        daten[genre] = eintrag
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, indent=2), encoding="utf-8")


def _lies_override(pfad: Path) -> dict:
    """Vorhandene Override-Datei lesen; fehlend/kaputt -> {} (Fehler geloggt)."""
    if not pfad.is_file():
        return {}
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Override-Datei %s nicht lesbar (%s) — wird ueberschrieben", pfad, exc)
        return {}
    return daten if isinstance(daten, dict) else {}


KANDIDATEN_GEWICHT_SCHLUESSEL = tuple(
    f"kandidaten_{f}_weight" for f in (
        "harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre", "mood", "loudness", "structure",
    )
)


def write_override_kandidaten(gewichte: dict[str, float]) -> None:
    """Schreibt die uebergebenen kandidaten_*_weight fuer alle Genres in die
    Override-Datei und skaliert die uebrigen Kandidaten-Gewichte proportional
    auf den Rest (Summe 1.0). Die acht Track-Gewichte bleiben unberuehrt —
    sie leben in derselben Datei unter anderen Schluesseln (Teil 4)."""
    unbekannt = [k for k in gewichte if k not in KANDIDATEN_GEWICHT_SCHLUESSEL]
    if unbekannt:
        raise ValueError(f"Unbekannte Kandidaten-Gewichte: {unbekannt}")
    neu_summe = sum(float(v) for v in gewichte.values())
    if any(float(v) < 0.0 for v in gewichte.values()) or neu_summe >= 1.0:
        raise ValueError(f"Kandidaten-Gewichte summieren auf {neu_summe}, muss in [0, 1) liegen")
    basis = get_tolerances(CANONICAL_GENRES[0])
    rest_keys = [k for k in KANDIDATEN_GEWICHT_SCHLUESSEL if k not in gewichte]
    rest_summe = sum(float(basis.get(k, 0.0)) for k in rest_keys) or 1.0
    pfad = _override_pfad()
    daten = _lies_override(pfad)
    for genre in CANONICAL_GENRES:
        eintrag = dict(daten.get(genre, {}))
        eintrag.update({k: float(v) for k, v in gewichte.items()})
        for k in rest_keys:
            eintrag[k] = float(basis.get(k, 0.0)) / rest_summe * (1.0 - neu_summe)
        daten[genre] = eintrag
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, indent=2), encoding="utf-8")


def _leere_paar_cache() -> None:
    """Kandidatenlisten der Playlist-Ebene verwerfen (lazy, kein Importzyklus)."""
    try:
        from .playlist import reset_pair_candidate_cache
    except Exception:  # noqa: BLE001 - beim Import von playlist selbst noch nicht verfuegbar
        return
    reset_pair_candidate_cache()

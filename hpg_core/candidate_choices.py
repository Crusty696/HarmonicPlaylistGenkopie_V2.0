"""Gespeicherte Kandidaten-Wahl je Trackpaar (Spec 2026-08-21, Abschnitt 4).

Ein Klick im Uebergangs-Panel merkt sich (t_out, t_in, blend_bars) fuer das
Paar (A, B); select_pair_candidate zieht diesen Kandidaten beim naechsten Lauf
nach vorn, wenn er noch unter den Kandidaten ist. Datei
%LOCALAPPDATA%/HPG/candidate_choices.json (oder HPG_CANDIDATE_CHOICES_FILE);
Schreiben atomar. Gerichtet: (A -> B) ist ein anderes Paar als (B -> A).
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)
_cache: dict | None = None


def _pfad() -> Path:
    env = os.environ.get("HPG_CANDIDATE_CHOICES_FILE")
    if env:
        return Path(env)
    basis = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".hpg")
    return Path(basis) / "HPG" / "candidate_choices.json"


def schluessel(pfad_a: str, pfad_b: str) -> str:
    def norm(p):
        return os.path.normcase(os.path.abspath(str(p)))
    return f"{norm(pfad_a)}||{norm(pfad_b)}"


def _lade() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    p = _pfad()
    daten: dict = {}
    if p.is_file():
        try:
            roh = json.loads(p.read_text(encoding="utf-8"))
            daten = roh if isinstance(roh, dict) else {}
        except (OSError, ValueError) as exc:
            logger.warning("candidate_choices nicht lesbar (%s): %s — wird als leer behandelt", p, exc)
    _cache = daten
    return daten


def _schreibe(daten: dict) -> None:
    p = _pfad()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="candidate_choices_", suffix=".json", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(daten, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def hole(pfad_a: str, pfad_b: str) -> dict | None:
    w = _lade().get(schluessel(pfad_a, pfad_b))
    return dict(w) if isinstance(w, dict) else None


def merke(pfad_a: str, pfad_b: str, *, t_out: float, t_in: float, blend_bars: int) -> None:
    global _cache
    daten = dict(_lade())
    daten[schluessel(pfad_a, pfad_b)] = {
        "t_out": float(t_out), "t_in": float(t_in), "blend_bars": int(blend_bars),
        "zeit": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    _schreibe(daten)
    _cache = daten
    _leere_paar_cache()


def vergiss(pfad_a: str, pfad_b: str) -> None:
    global _cache
    daten = dict(_lade())
    daten.pop(schluessel(pfad_a, pfad_b), None)
    _schreibe(daten)
    _cache = daten
    _leere_paar_cache()


def reset_cache() -> None:
    global _cache
    _cache = None
    _leere_paar_cache()


def _leere_paar_cache() -> None:
    """Kandidatenlisten der Playlist-Ebene verwerfen (lazy, kein Importzyklus)."""
    try:
        from .playlist import reset_pair_candidate_cache
    except Exception:  # noqa: BLE001 - beim Import von playlist selbst noch nicht verfuegbar
        return
    reset_pair_candidate_cache()

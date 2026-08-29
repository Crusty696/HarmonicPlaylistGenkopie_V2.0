"""Gespeicherte Kandidaten-Wahl je Trackpaar (Spec 2026-08-21, Abschnitt 4).

Ein Klick im Uebergangs-Panel merkt sich (t_out, t_in, blend_bars) fuer das
Paar (A, B); select_pair_candidate zieht diesen Kandidaten beim naechsten Lauf
nach vorn, wenn er noch unter den Kandidaten ist. Datei
%LOCALAPPDATA%/HPG/candidate_choices.json (oder HPG_CANDIDATE_CHOICES_FILE);
Schreiben atomar. Gerichtet: (A -> B) ist ein anderes Paar als (B -> A).
"""
from __future__ import annotations

import datetime
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import logging
import math
import numbers
import os
import tempfile
import threading
from pathlib import Path

from .caching import file_lock
from .config import (
    MAX_TRANSITION_OVERLAP_SECONDS,
    MIN_TRANSITION_BARS,
    SECURITY_MAX_TRACK_DURATION,
)
from .genres import GENRE_MIX_PROFILES

logger = logging.getLogger(__name__)
_cache: dict | None = None

_PFLICHTFELDER = ("t_out", "t_in", "blend_bars")
_AUDIT_VERSION = 2
_AUDITFELDER = ("bpm_a", "bpm_b", "overlap_sec")
_LOCK_TIMEOUT = 15.0
_IN_PROCESS_LOCK = threading.RLock()


@dataclass(frozen=True)
class _RollbackState:
    """Opaker Beleg fuer einen exakt ruecksetzbaren eigenen Commit."""

    path: str
    before_exists: bool
    before_bytes: bytes | None
    committed_digest: str


def _pfad() -> Path:
    env = os.environ.get("HPG_CANDIDATE_CHOICES_FILE")
    if env:
        return Path(env)
    basis = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".hpg")
    return Path(basis) / "HPG" / "candidate_choices.json"


def _lock_pfad(path: Path) -> Path:
    return Path(f"{path}.lock")


def schluessel(pfad_a: str, pfad_b: str) -> str:
    def norm(p):
        return os.path.normcase(os.path.abspath(str(p)))
    return f"{norm(pfad_a)}||{norm(pfad_b)}"


def _max_blend_bars() -> int:
    """Obergrenze direkt aus den kanonischen Genre-Profilen ableiten."""
    werte: list[int] = []
    for profile in GENRE_MIX_PROFILES.values():
        transition_bars = getattr(profile, "transition_bars", ())
        if not isinstance(transition_bars, (tuple, list)):
            continue
        werte.extend(
            wert for wert in transition_bars
            if isinstance(wert, int) and not isinstance(wert, bool)
        )
    if not werte:
        raise RuntimeError("GENRE_MIX_PROFILES enthalten keine gueltigen transition_bars")
    return max(werte)


def _validiere_wahl(wahl: object) -> dict:
    """Prueft und trennt eine persistierte Wahl tief vom Aufrufer."""
    if not isinstance(wahl, dict):
        raise ValueError("Eintrag ist kein Objekt")
    fehlend = [feld for feld in _PFLICHTFELDER if feld not in wahl]
    if fehlend:
        raise ValueError(f"Pflichtfelder fehlen: {', '.join(fehlend)}")

    ergebnis = deepcopy(wahl)
    for feld in ("t_out", "t_in"):
        wert = ergebnis[feld]
        if isinstance(wert, bool) or not isinstance(wert, numbers.Real):
            raise ValueError(f"{feld} muss eine echte Zahl sein")
        try:
            normalisiert = float(wert)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"{feld} muss endlich sein") from exc
        if not math.isfinite(normalisiert):
            raise ValueError(f"{feld} muss endlich sein")
        if not 0.0 <= normalisiert <= SECURITY_MAX_TRACK_DURATION:
            raise ValueError(
                f"{feld} muss zwischen 0 und {SECURITY_MAX_TRACK_DURATION} liegen"
            )
        ergebnis[feld] = normalisiert

    blend_bars = ergebnis["blend_bars"]
    if isinstance(blend_bars, bool) or not isinstance(blend_bars, int):
        raise ValueError("blend_bars muss eine ganze Zahl sein")
    max_bars = _max_blend_bars()
    if not MIN_TRANSITION_BARS <= blend_bars <= max_bars:
        raise ValueError(
            f"blend_bars muss zwischen {MIN_TRANSITION_BARS} und {max_bars} liegen"
        )

    if "zeit" in ergebnis:
        zeit = ergebnis["zeit"]
        if not isinstance(zeit, str) or not zeit.strip():
            raise ValueError("zeit muss eine nichtleere Zeichenkette sein")

    audit_vorhanden = "version" in ergebnis or any(
        feld in ergebnis for feld in _AUDITFELDER
    )
    if audit_vorhanden:
        if ergebnis.get("version") != _AUDIT_VERSION:
            raise ValueError(f"version muss {_AUDIT_VERSION} sein")
        fehlende_auditfelder = [
            feld for feld in _AUDITFELDER if feld not in ergebnis
        ]
        if fehlende_auditfelder:
            raise ValueError(
                "Auditfelder fehlen: " + ", ".join(fehlende_auditfelder)
            )
        for feld in _AUDITFELDER:
            wert = ergebnis[feld]
            if isinstance(wert, bool) or not isinstance(wert, numbers.Real):
                raise ValueError(f"{feld} muss eine echte Zahl sein")
            try:
                normalisiert = float(wert)
            except (OverflowError, TypeError, ValueError) as exc:
                raise ValueError(f"{feld} muss endlich und positiv sein") from exc
            if not math.isfinite(normalisiert) or normalisiert <= 0.0:
                raise ValueError(f"{feld} muss endlich und positiv sein")
            if (
                feld == "overlap_sec"
                and normalisiert > MAX_TRANSITION_OVERLAP_SECONDS
            ):
                raise ValueError(
                    "overlap_sec muss groesser als 0 und hoechstens "
                    f"{MAX_TRANSITION_OVERLAP_SECONDS:g} sein"
                )
            ergebnis[feld] = normalisiert
    return ergebnis


def _json_laden(raw: bytes, *, strict: bool) -> object:
    def reject_constant(value: str):
        raise ValueError(f"Nicht endliche JSON-Zahl: {value}")

    kwargs = {"parse_constant": reject_constant} if strict else {}
    return json.loads(raw.decode("utf-8"), **kwargs)


def _dekodiere(raw: bytes | None, *, strict: bool) -> dict:
    if raw is None:
        return {}
    roh = _json_laden(raw, strict=strict)
    if not isinstance(roh, dict):
        raise ValueError("Wurzel ist kein Objekt")

    daten: dict = {}
    for key, eintrag in roh.items():
        try:
            daten[key] = _validiere_wahl(eintrag)
        except (RuntimeError, ValueError) as exc:
            if strict:
                raise ValueError(
                    f"candidate_choices Eintrag {key!r} ist ungueltig: {exc}"
                ) from exc
            logger.warning(
                "candidate_choices Eintrag %r ungueltig: %s — wird nur fuer die Anzeige ausgeblendet",
                key,
                exc,
            )
    return daten


def _lese_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _lade() -> dict:
    """Toleranter, stets frischer Lesepfad fuer die reine Anzeige."""
    global _cache
    p = _pfad()
    try:
        daten = _dekodiere(_lese_bytes(p), strict=False)
    except (OSError, ValueError) as exc:
        logger.warning(
            "candidate_choices nicht lesbar (%s): %s — wird nur fuer die Anzeige als leer behandelt",
            p,
            exc,
        )
        daten = {}
    _cache = deepcopy(daten)
    return _cache


def _serialisiere(daten: dict) -> bytes:
    text = json.dumps(
        deepcopy(daten), indent=2, ensure_ascii=False, allow_nan=False
    ) + "\n"
    return text.encode("utf-8")


def _schreibe_bytes(p: Path, raw: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="candidate_choices_", suffix=".json", dir=str(p.parent))
    offen = fd
    try:
        with os.fdopen(fd, "wb") as fh:
            offen = -1
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    except Exception:
        if offen >= 0:
            try:
                os.close(offen)
            except OSError:
                pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _schreibe(daten: dict, path: Path | None = None) -> bytes:
    raw = _serialisiere(daten)
    _schreibe_bytes(_pfad() if path is None else path, raw)
    return raw


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _lade_strikt_unter_lock(path: Path) -> tuple[bytes | None, dict]:
    raw = _lese_bytes(path)
    return raw, _dekodiere(raw, strict=True)


def hole(pfad_a: str, pfad_b: str) -> dict | None:
    w = _lade().get(schluessel(pfad_a, pfad_b))
    return deepcopy(w) if isinstance(w, dict) else None


def snapshot() -> dict:
    """Liest frisch und liefert einen tief getrennten, weitergabefaehigen Snapshot."""
    global _cache
    p = _pfad()
    with _IN_PROCESS_LOCK:
        with file_lock(str(_lock_pfad(p)), timeout=_LOCK_TIMEOUT):
            _, daten = _lade_strikt_unter_lock(p)
    _cache = deepcopy(daten)
    return deepcopy(daten)


def merke(
    pfad_a: str,
    pfad_b: str,
    *,
    t_out: float,
    t_in: float,
    blend_bars: int,
    bpm_a: float | None = None,
    bpm_b: float | None = None,
    overlap_sec: float | None = None,
) -> object:
    global _cache
    p = _pfad()
    with _IN_PROCESS_LOCK:
        with file_lock(str(_lock_pfad(p)), timeout=_LOCK_TIMEOUT):
            vorher_raw, daten = _lade_strikt_unter_lock(p)
            key = schluessel(pfad_a, pfad_b)
            neue_wahl = deepcopy(daten.get(key, {}))
            neue_wahl.update({
                "t_out": t_out, "t_in": t_in, "blend_bars": blend_bars,
                "zeit": datetime.datetime.now().isoformat(timespec="seconds"),
            })
            auditwerte = (bpm_a, bpm_b, overlap_sec)
            if any(wert is not None for wert in auditwerte):
                if not all(wert is not None for wert in auditwerte):
                    raise ValueError(
                        "bpm_a, bpm_b und overlap_sec muessen gemeinsam gesetzt werden"
                    )
                neue_wahl.update({
                    "version": _AUDIT_VERSION,
                    "bpm_a": bpm_a,
                    "bpm_b": bpm_b,
                    "overlap_sec": overlap_sec,
                })
            else:
                # Ein alter Aufrufer darf bei einer geaenderten Primaerwahl keinen
                # veralteten Audit-Snapshot des vorherigen Kandidaten mitschleppen.
                for feld in ("version", *_AUDITFELDER):
                    neue_wahl.pop(feld, None)
            daten[key] = _validiere_wahl(neue_wahl)
            cache_snapshot = deepcopy(daten)
            committed_raw = _schreibe(daten, p)
            rollback_state = _RollbackState(
                path=str(p.resolve()),
                before_exists=vorher_raw is not None,
                before_bytes=vorher_raw,
                committed_digest=_digest(committed_raw),
            )
    _cache = cache_snapshot
    _leere_paar_cache()
    return rollback_state


def stelle_wieder_her(rollback_state: object) -> None:
    """Stellt eigene Vorherbytes nur bei unveraendertem eigenem Commit wieder her."""
    global _cache
    if not isinstance(rollback_state, _RollbackState):
        raise TypeError("rollback_state ist ungueltig")
    p = _pfad()
    if str(p.resolve()) != rollback_state.path:
        raise ValueError("Rollback gehoert zu einer anderen Kandidatenwahl-Datei")

    with _IN_PROCESS_LOCK:
        with file_lock(str(_lock_pfad(p)), timeout=_LOCK_TIMEOUT):
            aktuell_raw = _lese_bytes(p)
            if aktuell_raw is None or _digest(aktuell_raw) != rollback_state.committed_digest:
                raise RuntimeError(
                    "Kandidatenwahl wurde nach dem Commit veraendert; Rollback verweigert"
                )
            _dekodiere(aktuell_raw, strict=True)
            if rollback_state.before_exists:
                if rollback_state.before_bytes is None:
                    raise RuntimeError("Rollbackzustand enthaelt keine Vorherbytes")
                _schreibe_bytes(p, rollback_state.before_bytes)
                cache_snapshot = _dekodiere(
                    rollback_state.before_bytes, strict=True
                )
            else:
                try:
                    p.unlink()
                except FileNotFoundError as exc:
                    raise RuntimeError(
                        "Kandidatenwahl verschwand waehrend des Rollbacks"
                    ) from exc
                cache_snapshot = {}
    _cache = cache_snapshot
    _leere_paar_cache()


def vergiss(pfad_a: str, pfad_b: str) -> None:
    global _cache
    p = _pfad()
    with _IN_PROCESS_LOCK:
        with file_lock(str(_lock_pfad(p)), timeout=_LOCK_TIMEOUT):
            _, daten = _lade_strikt_unter_lock(p)
            key = schluessel(pfad_a, pfad_b)
            if key not in daten:
                return
            daten.pop(key)
            cache_snapshot = deepcopy(daten)
            _schreibe(daten, p)
    _cache = cache_snapshot
    _leere_paar_cache()


def reset_cache() -> None:
    global _cache
    _cache = None
    _leere_paar_cache()


def _leere_paar_cache() -> None:
    """Kandidatenlisten der Playlist-Ebene verwerfen (lazy, kein Importzyklus)."""
    try:
        from .playlist import reset_pair_candidate_cache
        reset_pair_candidate_cache()
    except Exception as exc:  # noqa: BLE001 - Persistenz-Commit darf nicht nachtraeglich scheitern
        try:
            logger.warning("Kandidatenlisten-Cache konnte nicht geleert werden: %s", exc)
        except Exception:  # noqa: BLE001 - auch fehlerhafte Logging-Handler isolieren
            pass

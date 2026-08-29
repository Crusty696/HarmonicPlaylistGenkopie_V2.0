"""Kandidaten-Praeferenzen aus dem Hoertest (Spec 2026-08-21, Abschnitt 3).

`fit --modus kandidaten` schreibt ausschliesslich den Nutzer-Override unter
%LOCALAPPDATA%/HPG (oder HPG_CANDIDATE_PREFERENCES_FILE). Nur Genres mit
eigenem bestandenem Fit werden partiell uebernommen. Die mitgelieferte Datei
bleibt eine schreibgeschuetzte Basis. Je Genre gelten die zehn
`kandidaten_*_weight` (Summe 1.0) und optional `schema_rang`.
Fehlt alles, liefern die Funktionen None/[] und pair_candidates nimmt die
Toleranzen — es gibt keinen stillen Default.
"""
from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import threading
import time
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from .caching import file_lock
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
_cache_signature: tuple | None = None
_IN_PROCESS_LOCK = threading.RLock()
_LOCK_TIMEOUT = 15.0
_STABILE_LESEVERSUCHE = 3


def _lock_pfad(pfad: Path) -> Path:
    return Path(f"{pfad}.lock")


def _digest(daten: bytes) -> str:
    return sha256(daten).hexdigest()


def _dateisignatur(pfad: Path) -> tuple:
    try:
        stat = pfad.stat()
    except FileNotFoundError:
        return (str(pfad.resolve()), False)
    return (
        str(pfad.resolve()), True, stat.st_size, stat.st_mtime_ns,
        stat.st_ctime_ns, stat.st_ino,
    )


def _quell_signatur() -> tuple:
    return (_dateisignatur(_MITGELIEFERT), _dateisignatur(_override_pfad()))


def _override_pfad() -> Path:
    env = os.environ.get("HPG_CANDIDATE_PREFERENCES_FILE")
    if env:
        return Path(env)
    basis = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".hpg")
    return Path(basis) / "HPG" / "candidate_preferences.json"


def override_path() -> Path:
    """Oeffentlicher Zielpfad fuer nutzerspezifische Praeferenzen."""
    return _override_pfad()


def _lies(pfad: Path) -> dict:
    if not pfad.is_file():
        return {}
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("candidate_preferences nicht lesbar (%s): %s", pfad, exc)
        return {}
    if not isinstance(daten, dict):
        logger.warning(
            "candidate_preferences: %s: Wurzel ist kein Objekt — Quelle ignoriert",
            pfad,
        )
        return {}
    return daten


def _gueltige_gewichte(eintrag: dict) -> dict | None:
    """Exakt zehn Gewichte, endlich, 0..1 und Summe 1.0 (+-1e-6)."""
    if not isinstance(eintrag, dict):
        return None
    vorhandene_schluessel = {
        key for key in eintrag
        if isinstance(key, str)
        and key.startswith("kandidaten_")
        and key.endswith("_weight")
    }
    if vorhandene_schluessel != set(GEWICHT_SCHLUESSEL):
        return None
    rohwerte = {k: eintrag[k] for k in GEWICHT_SCHLUESSEL}
    if any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(float(v))
        or not 0.0 <= float(v) <= 1.0
        for v in rohwerte.values()
    ):
        return None
    werte = {k: float(v) for k, v in rohwerte.items()}
    if abs(sum(werte.values()) - 1.0) > 1e-6:
        return None
    return werte


def _gueltige_schema_rangfolge(wert) -> list[str] | None:
    """Nur eindeutige, bekannte Schemata; eine leere Liste ist gueltig."""
    if not isinstance(wert, list):
        return None
    from .mix_candidates import SCHEMA_PRIORITAET

    if (
        any(not isinstance(schema, str) or schema not in SCHEMA_PRIORITAET for schema in wert)
        or len(set(wert)) != len(wert)
    ):
        return None
    return list(wert)


def _warn_ungueltige_gruppe(
    pfad: Path, genre: str, gruppe: str, fallback_vorhanden: bool
) -> None:
    fallback = (
        "vorherige gueltige Gruppe bleibt aktiv"
        if fallback_vorhanden
        else "kein gueltiger Fallback vorhanden"
    )
    logger.warning(
        "candidate_preferences: %s: Genre %s, Gruppe %s ungueltig — %s",
        pfad,
        genre,
        gruppe,
        fallback,
    )


def _lade_praeferenzen_unter_lock() -> dict:
    """Laedt beide Quellen frisch; Aufrufer haelt den Override-Dateilock."""
    ergebnis: dict = {}
    gueltige_gruppen: dict[str, set[str]] = {}
    for quelle in (_MITGELIEFERT, _override_pfad()):
        for genre, eintrag in _lies(quelle).items():
            if genre == "_diagnose" or genre not in CANONICAL_GENRES:
                continue
            if not isinstance(eintrag, dict):
                logger.warning(
                    "candidate_preferences: %s: Genre %s ist kein Objekt — Quelle ignoriert",
                    quelle,
                    genre,
                )
                continue

            ziel = ergebnis.setdefault(
                genre, {"gewichte": None, "schema_rang": []}
            )
            gruppen = gueltige_gruppen.setdefault(genre, set())
            gewichte_deklariert = any(
                isinstance(key, str)
                and key.startswith("kandidaten_")
                and key.endswith("_weight")
                for key in eintrag
            )
            if gewichte_deklariert:
                gewichte = _gueltige_gewichte(eintrag)
                if gewichte is None:
                    _warn_ungueltige_gruppe(
                        quelle, genre, "gewichte", "gewichte" in gruppen
                    )
                else:
                    ziel["gewichte"] = gewichte
                    gruppen.add("gewichte")

            if "schema_rang" in eintrag:
                rang = _gueltige_schema_rangfolge(eintrag["schema_rang"])
                if rang is None:
                    _warn_ungueltige_gruppe(
                        quelle,
                        genre,
                        "schema_rang",
                        "schema_rang" in gruppen,
                    )
                else:
                    ziel["schema_rang"] = rang
                    gruppen.add("schema_rang")
    return ergebnis


def _lade_stabile_praeferenzen_unter_lock() -> tuple[dict, tuple]:
    """Verknuepft nur einen unveraenderten Diskstand mit seiner Signatur."""
    for _ in range(_STABILE_LESEVERSUCHE):
        signatur_vorher = _quell_signatur()
        ergebnis = _lade_praeferenzen_unter_lock()
        signatur_nachher = _quell_signatur()
        if signatur_vorher == signatur_nachher:
            return ergebnis, signatur_nachher
    raise RuntimeError(
        "candidate_preferences wurde waehrend des Lesens wiederholt veraendert"
    )


def load_candidate_preferences() -> dict:
    """Liefert {genre: {"gewichte": dict|None, "schema_rang": list}} fuer
    kanonische Genres; ungueltige Gewichte werden geloggt und verworfen."""
    global _cache, _cache_signature
    ziel = _override_pfad()
    with _IN_PROCESS_LOCK:
        with file_lock(str(_lock_pfad(ziel)), timeout=_LOCK_TIMEOUT):
            aktuelle_signatur = _quell_signatur()
            if _cache is not None and _cache_signature == aktuelle_signatur:
                return deepcopy(_cache)
            ergebnis, signatur = _lade_stabile_praeferenzen_unter_lock()
        _cache = deepcopy(ergebnis)
        _cache_signature = signatur
        return deepcopy(ergebnis)


def kandidaten_gewichte(genre: str) -> dict | None:
    return load_candidate_preferences().get(genre, {}).get("gewichte")


def schema_rangfolge(genre: str) -> list[str]:
    return list(load_candidate_preferences().get(genre, {}).get("schema_rang", []))


def reset_cache() -> None:
    global _cache, _cache_signature
    with _IN_PROCESS_LOCK:
        _cache = None
        _cache_signature = None
    _leere_paar_cache()


def _lies_override_strikt(pfad: Path) -> tuple[dict, bytes | None]:
    """Liest den Nutzerstand ohne toleranten Loader-Fallback."""
    if not pfad.is_file():
        return {}, None
    vorher = pfad.read_bytes()
    try:
        daten = json.loads(vorher.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"candidate_preferences-Override ist ungueltig: {exc}") from exc
    if not isinstance(daten, dict):
        raise ValueError("candidate_preferences-Override ist kein JSON-Objekt")
    return daten, vorher


def _schreibe_bytes_atomar(pfad: Path, daten: bytes) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{pfad.name}.", suffix=".tmp", dir=str(pfad.parent)
    )
    temp_pfad = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(daten)
            handle.flush()
            os.fsync(handle.fileno())
        for versuch in range(3):
            try:
                os.replace(temp_pfad, pfad)
                break
            except PermissionError:
                if versuch == 2:
                    raise
                # Windows kann einen frisch geschlossenen Temp-Pfad kurz durch
                # Virenscanner/Indexer sperren. Der Bytezustand bleibt bis zum
                # erfolgreichen Replace unveraendert.
                time.sleep(0.01 * (versuch + 1))
    except Exception:
        if fd >= 0:
            os.close(fd)
        try:
            temp_pfad.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _normalisiere_updates(updates: dict) -> dict[str, dict]:
    if not isinstance(updates, dict) or not updates:
        raise ValueError("Mindestens ein Genre-Update ist erforderlich")
    normalisiert: dict[str, dict] = {}
    for genre, eintrag in updates.items():
        if genre not in CANONICAL_GENRES or not isinstance(eintrag, dict):
            raise ValueError(f"Ungueltiges Genre-Update: {genre!r}")
        ziel: dict = {}
        gewichte_deklariert = any(
            isinstance(key, str)
            and key.startswith("kandidaten_")
            and key.endswith("_weight")
            for key in eintrag
        )
        if gewichte_deklariert:
            gewichte = _gueltige_gewichte(eintrag)
            if gewichte is None:
                raise ValueError(f"Ungueltige Gewichtsgruppe fuer {genre}")
            ziel.update(gewichte)
        if "schema_rang" in eintrag:
            rang = _gueltige_schema_rangfolge(eintrag["schema_rang"])
            if rang is None:
                raise ValueError(f"Ungueltige Schema-Rangfolge fuer {genre}")
            ziel["schema_rang"] = rang
        unbekannt = set(eintrag).difference(GEWICHT_SCHLUESSEL).difference({"schema_rang"})
        if unbekannt:
            raise ValueError(f"Unbekannte Praeferenzfelder fuer {genre}: {sorted(unbekannt)}")
        if not ziel:
            raise ValueError(f"Leeres Genre-Update fuer {genre}")
        normalisiert[genre] = ziel
    return normalisiert


def _deep_merge_dict(basis: dict, update: dict) -> dict:
    """Fuehrt Dicts rekursiv zusammen; Nicht-Dicts werden gezielt ersetzt."""
    ergebnis = deepcopy(basis)
    for key, wert in update.items():
        vorhanden = ergebnis.get(key)
        if isinstance(vorhanden, dict) and isinstance(wert, dict):
            ergebnis[key] = _deep_merge_dict(vorhanden, wert)
        else:
            ergebnis[key] = deepcopy(wert)
    return ergebnis


def merge_user_preferences_atomically(
    updates: dict,
    *,
    diagnose: dict | None = None,
) -> Path:
    """Fuehrt bestandene Genre-Gruppen sicher in den Nutzer-Override ein.

    Der atomare Replace ist der Commit. Schlaegt die anschliessende effektive
    Pruefung fehl, bleibt der bereits publizierte gueltige Stand erhalten.
    Ein Rollback per zweitem Replace waere ohne echtes Filesystem-CAS unsicher,
    weil er einen nicht-lock-kooperierenden Zwischencommit ueberschreiben kann.
    """
    global _cache, _cache_signature
    normalisiert = _normalisiere_updates(updates)
    if diagnose is not None and not isinstance(diagnose, dict):
        raise ValueError("Diagnose muss ein JSON-Objekt sein")
    ziel = override_path()
    with _IN_PROCESS_LOCK:
        with file_lock(str(_lock_pfad(ziel)), timeout=_LOCK_TIMEOUT):
            vorhanden, _ = _lies_override_strikt(ziel)
            neu = deepcopy(vorhanden)
            for genre, update in normalisiert.items():
                alter_eintrag = neu.get(genre, {})
                if not isinstance(alter_eintrag, dict):
                    raise ValueError(f"Bestehender Genre-Eintrag fuer {genre} ist kein Objekt")
                neu[genre] = _deep_merge_dict(alter_eintrag, update)
            if diagnose is not None:
                alte_diagnose = neu.get("_diagnose", {})
                if not isinstance(alte_diagnose, dict):
                    raise ValueError("Bestehende _diagnose ist kein Objekt")
                fit_diagnose = alte_diagnose.get("fit_kandidaten", {})
                if not isinstance(fit_diagnose, dict):
                    raise ValueError("Bestehende _diagnose.fit_kandidaten ist kein Objekt")
                neu["_diagnose"] = _deep_merge_dict(
                    alte_diagnose, {"fit_kandidaten": diagnose}
                )

            payload = (json.dumps(neu, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            committed_digest = _digest(payload)
            _schreibe_bytes_atomar(ziel, payload)
            _leere_paar_cache()
            try:
                effektiv, effektive_signatur = _lade_stabile_praeferenzen_unter_lock()
                for genre, update in normalisiert.items():
                    if any(key in update for key in GEWICHT_SCHLUESSEL):
                        erwartet = {key: float(update[key]) for key in GEWICHT_SCHLUESSEL}
                        if effektiv.get(genre, {}).get("gewichte") != erwartet:
                            raise RuntimeError(f"Effektiver Reload der Gewichte fuer {genre} weicht ab")
                    if "schema_rang" in update and effektiv.get(genre, {}).get("schema_rang") != update["schema_rang"]:
                        raise RuntimeError(f"Effektiver Reload der Schema-Rangfolge fuer {genre} weicht ab")
            except Exception:
                aktuell = ziel.read_bytes() if ziel.is_file() else None
                _cache = None
                _cache_signature = None
                if aktuell is None or _digest(aktuell) != committed_digest:
                    raise RuntimeError(
                        "candidate_preferences wurde nach dem Commit veraendert; "
                        "fail-closed ohne Rollback"
                    )
                # Auch der unveraenderte eigene Commit wird nicht zurueckgerollt:
                # zwischen diesem Digestvergleich und einem Restore koennte ein
                # fremder Writer publizieren. Der naechste Read laedt frisch.
                raise
            _cache = deepcopy(effektiv)
            _cache_signature = effektive_signatur
    return ziel


def _leere_paar_cache() -> None:
    """Kandidatenlisten der Playlist-Ebene verwerfen (lazy, kein Importzyklus)."""
    try:
        from .playlist import reset_pair_candidate_cache
    except Exception:  # noqa: BLE001 - beim Import von playlist selbst noch nicht verfuegbar
        return
    reset_pair_candidate_cache()

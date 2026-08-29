"""Laedt die Uebergangs-Toleranzen: Defaults, mitgeliefertes JSON, Override.

Gewichte sind Daten, keine Konstanten im Quelltext. Eine Aenderung erfordert
keine Neuanalyse, nur ein Neuberechnen der Scores.
"""
from __future__ import annotations

import copy
import json
import logging
import math
import os
import tempfile
import threading
from hashlib import sha256
from pathlib import Path

from .caching import file_lock
from .genres import CANONICAL_GENRES, GENRE_TRANSITION_TOLERANCES

logger = logging.getLogger(__name__)

_MITGELIEFERT = Path(__file__).parent / "data" / "transition_tolerances.json"

_cache: dict[str, dict] | None = None
_cache_signature: tuple | None = None
_IN_PROCESS_LOCK = threading.RLock()
_LOCK_TIMEOUT = 15.0
_STABILE_LESEVERSUCHE = 3


def _lock_pfad(pfad: Path) -> Path:
    return Path(f"{pfad}.lock")


def _loeschmarke_pfad(pfad: Path) -> Path:
    return Path(f"{pfad}.deleted")


def _dateisignatur(pfad: Path) -> tuple:
    try:
        stat = pfad.stat()
    except FileNotFoundError:
        return (str(pfad.resolve()), False)
    return (
        str(pfad.resolve()), True, stat.st_size, stat.st_mtime_ns,
        stat.st_ctime_ns, stat.st_ino,
    )


def _override_signatur(pfad: Path) -> tuple:
    return (_dateisignatur(pfad), _dateisignatur(_loeschmarke_pfad(pfad)))


def _digest(daten: bytes) -> str:
    return sha256(daten).hexdigest()

# Reiner Legacy-Persistenzvertrag. Die aktuelle GUI und das Kandidaten-Scoring
# lesen diese Track-Gewichte nicht als gemeinsame Gewichtungsquelle.
TRACK_GEWICHT_SCHLUESSEL = (
    "harmonic_weight", "bpm_weight", "energy_weight", "genre_weight",
    "groove_weight", "bass_weight", "timbre_weight", "mood_weight",
)
SICHTBARE_TRACK_GEWICHT_SCHLUESSEL = (
    "groove_weight", "bass_weight", "timbre_weight", "mood_weight",
)
KANDIDATEN_GEWICHT_SCHLUESSEL = tuple(
    f"kandidaten_{f}_weight" for f in (
        "harmonic", "bpm", "energy", "genre", "groove", "bass",
        "timbre", "mood", "loudness", "structure",
    )
)
SICHTBARE_KANDIDATEN_GEWICHT_SCHLUESSEL = tuple(
    f"kandidaten_{f}_weight"
    for f in ("groove", "bass", "timbre", "mood", "loudness")
)
VERSTECKTE_KANDIDATEN_GEWICHT_SCHLUESSEL = tuple(
    key
    for key in KANDIDATEN_GEWICHT_SCHLUESSEL
    if key not in SICHTBARE_KANDIDATEN_GEWICHT_SCHLUESSEL
)
NICHT_GEWICHT_SCHLUESSEL = (
    "groove_sim_floor", "bass_delta_max", "brightness_delta_max",
)
ERLAUBTE_TOLERANZ_SCHLUESSEL = frozenset(
    TRACK_GEWICHT_SCHLUESSEL
    + KANDIDATEN_GEWICHT_SCHLUESSEL
    + NICHT_GEWICHT_SCHLUESSEL
)


def _gueltiges_gewicht(wert) -> bool:
    return (
        not isinstance(wert, bool)
        and isinstance(wert, (int, float))
        and math.isfinite(float(wert))
        and float(wert) >= 0.0
    )


def _override_pfad() -> Path:
    """Nutzer-Override; HPG_TOLERANCES_FILE hat Vorrang (auch fuer Tests)."""
    explizit = os.environ.get("HPG_TOLERANCES_FILE")
    if explizit:
        return Path(explizit)
    basis = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(basis) / "HPG" / "transition_tolerances.json"


def _merge(ziel: dict[str, dict], quelle: dict) -> None:
    """Uebernimmt nur vollstaendige Gewichtskreise und gueltige Grenzwerte."""
    # json.loads liefert jeden JSON-Wurzeltyp — eine Liste, eine Zahl, null.
    # Ohne diesen Guard wirft `.items()` einen AttributeError, den der
    # Aufrufer nicht faengt, und die erste Playlist-Generierung stirbt.
    if not isinstance(quelle, dict):
        raise ValueError(f"Toleranz-Datei ist kein Objekt, sondern {type(quelle).__name__}")
    for genre, werte in quelle.items():
        if genre not in ziel:
            logger.warning("Unbekanntes Toleranz-Genre %s ignoriert", genre)
            continue
        if not isinstance(werte, dict):
            logger.warning("Toleranzen fuer %s sind kein Objekt und werden ignoriert", genre)
            continue

        unbekannt = sorted(set(werte).difference(ERLAUBTE_TOLERANZ_SCHLUESSEL))
        for schluessel in unbekannt:
            logger.warning(
                "Unbekannter Toleranz-Schluessel %s fuer %s ignoriert",
                schluessel,
                genre,
            )

        for gruppe in (TRACK_GEWICHT_SCHLUESSEL, KANDIDATEN_GEWICHT_SCHLUESSEL):
            vorhanden = set(gruppe).intersection(werte)
            if not vorhanden:
                continue
            if vorhanden != set(gruppe):
                logger.warning(
                    "Unvollstaendiger Gewichtskreis fuer %s ignoriert: %s",
                    genre,
                    sorted(vorhanden),
                )
                continue
            gruppe_neu = {key: werte[key] for key in gruppe}
            if (
                any(not _gueltiges_gewicht(wert) for wert in gruppe_neu.values())
                or not math.isclose(
                    sum(float(wert) for wert in gruppe_neu.values()),
                    1.0,
                    rel_tol=0.0,
                    abs_tol=1e-6,
                )
            ):
                logger.warning("Ungueltiger Gewichtskreis fuer %s ignoriert", genre)
                continue
            ziel[genre].update({key: float(value) for key, value in gruppe_neu.items()})

        for schluessel in NICHT_GEWICHT_SCHLUESSEL:
            if schluessel not in werte:
                continue
            wert = werte[schluessel]
            gueltig = _gueltiges_gewicht(wert)
            if schluessel == "groove_sim_floor":
                gueltig = gueltig and float(wert) <= 1.0
            else:
                gueltig = gueltig and float(wert) > 0.0
            if not gueltig:
                logger.warning(
                    "Ungueltiger Toleranz-Grenzwert %s fuer %s ignoriert",
                    schluessel,
                    genre,
                )
                continue
            ziel[genre][schluessel] = float(wert)


def _lade_toleranzen_unter_lock() -> dict[str, dict]:
    """Laedt alle Quellen frisch; Aufrufer haelt den Override-Dateilock."""
    werte = copy.deepcopy(GENRE_TRANSITION_TOLERANCES)
    for pfad in (_MITGELIEFERT, _override_pfad()):
        try:
            if pfad == _override_pfad():
                roh = _lies_override_bytes(pfad)
                if roh is not None:
                    _merge(werte, json.loads(roh.decode("utf-8")))
            elif pfad.is_file():
                _merge(werte, json.loads(pfad.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, ValueError,
                TypeError, AttributeError) as exc:
            logger.warning(f"Toleranz-Datei {pfad} nicht lesbar: {exc}")
    return werte


def _lade_stabile_toleranzen_unter_lock(
    pfad: Path,
) -> tuple[dict[str, dict], tuple]:
    """Verknuepft nur einen unveraenderten Override-Stand mit seiner Signatur."""
    for _ in range(_STABILE_LESEVERSUCHE):
        signatur_vorher = _override_signatur(pfad)
        werte = _lade_toleranzen_unter_lock()
        signatur_nachher = _override_signatur(pfad)
        if signatur_vorher == signatur_nachher:
            return werte, signatur_nachher
    raise RuntimeError(
        "Toleranz-Override wurde waehrend des Lesens wiederholt veraendert"
    )


def load_tolerances() -> dict[str, dict]:
    """Defaults, darueber das mitgelieferte JSON, darueber der Override.

    Ein defektes JSON darf den Start nicht verhindern — der Fehler wird
    protokolliert und die bis dahin gueltigen Werte bleiben bestehen.
    """
    global _cache, _cache_signature
    pfad = _override_pfad()
    with _IN_PROCESS_LOCK:
        with file_lock(str(_lock_pfad(pfad)), timeout=_LOCK_TIMEOUT):
            werte, signatur = _lade_stabile_toleranzen_unter_lock(pfad)
        _cache = copy.deepcopy(werte)
        _cache_signature = signatur
        return copy.deepcopy(werte)


def get_tolerances(genre: str) -> dict:
    """Toleranzen eines Genres; unbekannte Genres bekommen das erste kanonische."""
    global _cache, _cache_signature
    pfad = _override_pfad()
    with _IN_PROCESS_LOCK:
        if _cache is None or _cache_signature != _override_signatur(pfad):
            werte = load_tolerances()
        else:
            werte = _cache
        auswahl = werte.get(genre) or werte[CANONICAL_GENRES[0]]
        return copy.deepcopy(auswahl)


def entferne_override() -> bool:
    """Loescht den Nutzer-Override logisch; True, wenn einer aktiv war.

    Ein Digest-Tombstone maskiert exakt den gelesenen Bytezustand. Die
    Zieldatei selbst wird nie per Check-then-unlink entfernt. Publiziert ein
    nicht-lock-kooperierender Writer vor, waehrend oder nach dem Vorgang andere
    Bytes, passen sie nicht zum Tombstone und bleiben sofort sichtbar.
    """
    pfad = _override_pfad()
    entfernt = False
    try:
        with _IN_PROCESS_LOCK:
            with file_lock(str(_lock_pfad(pfad)), timeout=_LOCK_TIMEOUT):
                if _lies_override_bytes(pfad) is None:
                    return False
                vorher = _lies_roh_bytes(pfad)
                if vorher is None:
                    return False
                _dekodiere_override(vorher)
                erwartet = _digest(vorher)
                _schreibe_loeschmarke_atomar(pfad, erwartet)
                aktuell = _lies_roh_bytes(pfad)
                if aktuell is None or _digest(aktuell) != erwartet:
                    _loeschmarke_pfad(pfad).unlink(missing_ok=True)
                    raise RuntimeError(
                        "Override-Datei wurde waehrend des Delete veraendert; "
                        "Delete fail-closed verworfen"
                    )
                _setze_cache_unter_lock(None, None)
                entfernt = True
    except OSError as exc:
        logger.warning(f"Override-Datei {pfad} nicht loeschbar: {exc}")
        return False
    if entfernt:
        _leere_paar_cache()
    return entfernt


def remove_candidate_overrides() -> bool:
    """Entfernt nur bekannte Kandidaten-Gewichte atomar aus dem Override.

    Andere Nutzerwerte, insbesondere der Track-Gewichtskreis, bleiben exakt
    erhalten. Ein unlesbarer Stand wird nicht stillschweigend ersetzt.
    """
    pfad = _override_pfad()
    with _IN_PROCESS_LOCK:
        with file_lock(str(_lock_pfad(pfad)), timeout=_LOCK_TIMEOUT):
            vorher = _lies_override_bytes(pfad)
            if vorher is None:
                return False
            daten = _dekodiere_override(vorher)
            bereinigt = {}
            entfernt = False
            for genre, eintrag in daten.items():
                if not isinstance(eintrag, dict):
                    bereinigt[genre] = copy.deepcopy(eintrag)
                    continue
                neuer_eintrag = {
                    key: copy.deepcopy(value) for key, value in eintrag.items()
                    if key not in KANDIDATEN_GEWICHT_SCHLUESSEL
                }
                entfernt = entfernt or len(neuer_eintrag) != len(eintrag)
                bereinigt[genre] = neuer_eintrag

            if entfernt:
                _schreibe_override_atomar(pfad, bereinigt)
                _setze_cache_unter_lock(None, None)
    if entfernt:
        _leere_paar_cache()
    return entfernt


def reset_cache() -> None:
    """Verwirft Toleranz- und Paar-Cache explizit (Writes tun dies bereits)."""
    _nach_commit_cache_leeren()


def _nach_commit_cache_leeren() -> None:
    """Macht einen erfolgreich persistierten Stand sofort sichtbar."""
    with _IN_PROCESS_LOCK:
        _setze_cache_unter_lock(None, None)
    _leere_paar_cache()


def _setze_cache_unter_lock(cache: dict | None, signatur: tuple | None) -> None:
    global _cache, _cache_signature
    _cache = cache
    _cache_signature = signatur


def _validiere_track_gewichte(gewichte: dict[str, float]) -> dict[str, float]:
    erlaubte_keys = set(SICHTBARE_TRACK_GEWICHT_SCHLUESSEL)
    if not isinstance(gewichte, dict) or not gewichte:
        raise ValueError("Gewichte muessen ein nicht leeres Objekt sein")
    unbekannt = [key for key in gewichte if key not in erlaubte_keys]
    if unbekannt:
        raise ValueError(f"Unbekannte Track-Gewichte: {unbekannt}")
    if any(not _gueltiges_gewicht(wert) for wert in gewichte.values()):
        raise ValueError("Track-Gewichte muessen endlich, numerisch und >= 0 sein")
    gewichte = {key: float(value) for key, value in gewichte.items()}
    return gewichte


def _baue_track_override(gewichte: dict[str, float], vorhanden: dict) -> dict:
    """Berechnet den Track-Gewichtskreis ohne Dateizugriff."""
    basis = GENRE_TRANSITION_TOLERANCES[CANONICAL_GENRES[0]]
    sichtbar = {
        key: float(basis[key]) for key in SICHTBARE_TRACK_GEWICHT_SCHLUESSEL
    }
    sichtbar.update(gewichte)
    sichtbar_summe = sum(sichtbar.values())
    if not math.isfinite(sichtbar_summe) or sichtbar_summe >= 1.0:
        raise ValueError(
            f"Sichtbare Track-Gewichte summieren auf {sichtbar_summe}, muss < 1.0 sein"
        )
    rest = 1.0 - sichtbar_summe
    alt_keys = ("harmonic_weight", "bpm_weight", "energy_weight", "genre_weight")
    alt_summe = sum(basis[k] for k in alt_keys)
    if rest <= 0.0 or alt_summe <= 0.0:
        raise ValueError("Restgewicht der Legacy-Track-Faktoren muss > 0 sein")
    daten = copy.deepcopy(vorhanden)
    for genre in CANONICAL_GENRES:
        roheintrag = daten.get(genre, {})
        if not isinstance(roheintrag, dict):
            raise ValueError(f"Override fuer {genre} ist kein Objekt")
        # Nichtgewichte und Legacy-Felder gehoeren dem Nutzer und bleiben
        # semantisch erhalten; nur die acht Track-Gewichte werden ersetzt.
        eintrag = dict(roheintrag)
        eintrag.update(sichtbar)
        for k in alt_keys:
            eintrag[k] = basis[k] / alt_summe * rest
        kreis_summe = sum(float(eintrag[key]) for key in TRACK_GEWICHT_SCHLUESSEL)
        if not math.isclose(kreis_summe, 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(
                f"Legacy-Track-Gewichtskreis fuer {genre} hat Summe {kreis_summe}"
            )
        daten[genre] = eintrag
    return daten


def _lies_roh_bytes(pfad: Path) -> bytes | None:
    try:
        return pfad.read_bytes()
    except FileNotFoundError:
        return None


def _lies_override_bytes(pfad: Path) -> bytes | None:
    roh = _lies_roh_bytes(pfad)
    if roh is None:
        return None
    marke = _lies_roh_bytes(_loeschmarke_pfad(pfad))
    if marke is None:
        return roh
    try:
        daten = json.loads(marke.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Ungueltige Delete-Marke fuer %s wird ignoriert", pfad)
        return roh
    if (
        isinstance(daten, dict)
        and set(daten) == {"sha256"}
        and isinstance(daten["sha256"], str)
        and daten["sha256"] == _digest(roh)
    ):
        return None
    return roh


def _dekodiere_override(roh: bytes) -> dict:
    try:
        daten = json.loads(roh.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Override-Datei enthaelt ungueltiges JSON: {exc}") from exc
    if not isinstance(daten, dict):
        raise ValueError("Override-Datei ist kein JSON-Objekt")
    return daten


def _lies_override(pfad: Path) -> dict:
    """Vorhandenen Override lesen; unlesbare Nutzerdaten nie ueberschreiben."""
    roh = _lies_override_bytes(pfad)
    if roh is None:
        return {}
    return _dekodiere_override(roh)


def _validiere_kandidaten_gewichte(
    gewichte: dict[str, float],
) -> dict[str, float]:
    if not isinstance(gewichte, dict) or not gewichte:
        raise ValueError("Kandidaten-Gewichte muessen ein nicht leeres Objekt sein")
    unbekannt = [
        k for k in gewichte
        if k not in SICHTBARE_KANDIDATEN_GEWICHT_SCHLUESSEL
    ]
    if unbekannt:
        raise ValueError(f"Unbekannte Kandidaten-Gewichte: {unbekannt}")
    if any(not _gueltiges_gewicht(v) for v in gewichte.values()):
        raise ValueError("Kandidaten-Gewichte muessen endlich, numerisch und >= 0 sein")
    gewichte = {key: float(value) for key, value in gewichte.items()}
    return gewichte


def _baue_kandidaten_override(
    daten: dict,
    gewichte: dict[str, float],
    toleranz_snapshot: dict[str, dict],
) -> dict:
    """Ergaenzt fuenf GUI-Gewichte und skaliert je Genre dessen Restbasis."""
    referenz_genre = CANONICAL_GENRES[0]
    referenz = toleranz_snapshot.get(referenz_genre)
    if not isinstance(referenz, dict):
        raise ValueError(f"Toleranz-Snapshot enthaelt {referenz_genre} nicht")

    sichtbar: dict[str, float] = {}
    for key in SICHTBARE_KANDIDATEN_GEWICHT_SCHLUESSEL:
        wert = referenz.get(key)
        if not _gueltiges_gewicht(wert):
            raise ValueError(f"Ungueltige sichtbare Kandidatenbasis: {key}")
        sichtbar[key] = float(wert)
    sichtbar.update(gewichte)
    sichtbar_summe = sum(sichtbar.values())
    if not math.isfinite(sichtbar_summe) or sichtbar_summe >= 1.0:
        raise ValueError(
            f"Sichtbare Kandidaten-Gewichte summieren auf {sichtbar_summe}, muss < 1.0 sein"
        )
    rest = 1.0 - sichtbar_summe
    if not math.isfinite(rest) or rest <= 0.0:
        raise ValueError("Restgewicht der versteckten Kandidaten-Faktoren muss > 0 sein")

    ergebnis = copy.deepcopy(daten)
    for genre in CANONICAL_GENRES:
        basis = toleranz_snapshot.get(genre)
        if not isinstance(basis, dict):
            raise ValueError(f"Toleranz-Snapshot enthaelt {genre} nicht")
        versteckte_basis: dict[str, float] = {}
        for key in VERSTECKTE_KANDIDATEN_GEWICHT_SCHLUESSEL:
            wert = basis.get(key)
            if not _gueltiges_gewicht(wert):
                raise ValueError(
                    f"Ungueltige versteckte Kandidatenbasis fuer {genre}: {key}"
                )
            versteckte_basis[key] = float(wert)
        basis_summe = sum(versteckte_basis.values())
        if not math.isfinite(basis_summe) or basis_summe <= 0.0:
            raise ValueError(
                f"Versteckte Kandidatenbasis fuer {genre} muss Summe > 0 haben"
            )

        roheintrag = ergebnis.get(genre, {})
        if not isinstance(roheintrag, dict):
            raise ValueError(f"Override fuer {genre} ist kein Objekt")
        eintrag = dict(roheintrag)
        eintrag.update(sichtbar)
        for key, wert in versteckte_basis.items():
            eintrag[key] = wert / basis_summe * rest
        kreis_summe = sum(
            float(eintrag[key]) for key in KANDIDATEN_GEWICHT_SCHLUESSEL
        )
        if not math.isclose(
            kreis_summe, 1.0, rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError(
                f"Kandidaten-Gewichtskreis fuer {genre} hat Summe {kreis_summe}"
            )
        ergebnis[genre] = eintrag
    return ergebnis


def _schreibe_override_atomar(
    pfad: Path,
    daten: dict,
    *,
    loeschmarke_entfernen: bool = True,
) -> None:
    """Schreibt JSON per gleicher-Ordner-Tempdatei, fsync und atomarem Replace."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{pfad.name}.", suffix=".tmp", dir=str(pfad.parent)
    )
    temp_pfad = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            fd = -1
            json.dump(daten, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_pfad, pfad)
        if loeschmarke_entfernen:
            _loeschmarke_pfad(pfad).unlink(missing_ok=True)
    except Exception:
        if fd >= 0:
            os.close(fd)
        try:
            temp_pfad.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _schreibe_loeschmarke_atomar(pfad: Path, digest: str) -> None:
    _schreibe_override_atomar(
        _loeschmarke_pfad(pfad),
        {"sha256": digest},
        loeschmarke_entfernen=False,
    )


def write_overrides_atomically(
    track_gewichte: dict[str, float] | None = None,
    kandidaten_gewichte: dict[str, float] | None = None,
) -> None:
    """Validiert und schreibt beide Gewichtskreise in genau einem Replace."""
    if track_gewichte is None and kandidaten_gewichte is None:
        raise ValueError("Mindestens ein Gewichtskreis muss gesetzt sein")
    track = (
        _validiere_track_gewichte(track_gewichte)
        if track_gewichte is not None
        else None
    )
    kandidaten = (
        _validiere_kandidaten_gewichte(kandidaten_gewichte)
        if kandidaten_gewichte is not None
        else None
    )
    pfad = _override_pfad()
    with _IN_PROCESS_LOCK:
        with file_lock(str(_lock_pfad(pfad)), timeout=_LOCK_TIMEOUT):
            vorhanden = _lies_override(pfad)
            daten = (
                _baue_track_override(track, vorhanden)
                if track is not None
                else copy.deepcopy(vorhanden)
            )
            if kandidaten is not None:
                # Snapshot und RMW stammen unter demselben Prozess-Dateilock
                # aus exakt demselben Diskstand.
                toleranz_snapshot = copy.deepcopy(_lade_toleranzen_unter_lock())
                daten = _baue_kandidaten_override(
                    daten, kandidaten, toleranz_snapshot
                )
            _schreibe_override_atomar(pfad, daten)
            _setze_cache_unter_lock(None, None)
    _leere_paar_cache()


def write_override(gewichte: dict[str, float]) -> None:
    """Kompatibilitaets-API fuer den Track-Gewichtskreis, atomar geschrieben."""
    write_overrides_atomically(track_gewichte=gewichte)


def write_override_kandidaten(gewichte: dict[str, float]) -> None:
    """Kompatibilitaets-API fuer den Kandidaten-Gewichtskreis, atomar geschrieben."""
    write_overrides_atomically(kandidaten_gewichte=gewichte)


def _leere_paar_cache() -> None:
    """Kandidatenlisten der Playlist-Ebene verwerfen (lazy, kein Importzyklus)."""
    try:
        from .playlist import reset_pair_candidate_cache
        reset_pair_candidate_cache()
    except Exception as exc:  # noqa: BLE001 - Persistenz nie zurueckrollen
        logger.warning("Paar-Kandidaten-Cache konnte nicht geleert werden: %s", exc)
        return

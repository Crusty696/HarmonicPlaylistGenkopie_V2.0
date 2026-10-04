"""
Rekordbox Database Importer

Imports analyzed track data from Rekordbox 6/7 master.db database.
Provides BPM, Key, Cue Points, and metadata from Rekordbox's professional analysis.

Features:
- Automatic Rekordbox database detection
- BPM import (Rekordbox analyzed)
- Musical Key import with Rekordbox → Camelot conversion
- Cue Point import (Memory Cues, Hot Cues)
- Fast lookup by file path
- Graceful fallback if Rekordbox not available
"""

import logging
import math
import os
import hashlib
import json
from copy import deepcopy
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from contextlib import contextmanager
from contextvars import ContextVar
import threading
from .models import CAMELOT_MAP
from .rekordbox_readonly import ReadOnlyRekordboxError

logger = logging.getLogger(__name__)
_detail_uncertain = ContextVar("rekordbox_detail_uncertain", default=False)


def _tag_evidence(files, keys):
    """Tag-Abwesenheit nur bestaetigen, wenn Zugriff ohne unbekannten Fehler gelang."""
    present = False
    try:
        for file in files:
            for key in keys:
                if hasattr(type(file), "__contains__") and key not in file:
                    continue
                getter = getattr(file, "get_tag", None)
                tag = getter(key) if callable(getter) else getattr(file, key, None)
                if callable(getter) and tag is None:
                    return "unverified"
                if tag is not None:
                    present = True
    except ReadOnlyRekordboxError:
        raise
    except Exception:
        return "unverified"
    return "present" if present else "missing"


@contextmanager
def _opaque_phrase_logging():
    """Hilfsmodul darf keine fremden Exceptiontexte dieses Aufrufs protokollieren."""
    thread_id = threading.get_ident()

    class Opaque(logging.Filter):
        def filter(self, record):
            if record.thread == thread_id:
                if record.levelno >= logging.WARNING:
                    _detail_uncertain.set(True)
                record.msg = "Rekordbox-Phrasendetail konnte nicht vollstaendig gelesen werden."
                record.args = ()
                record.exc_info = None
                record.exc_text = None
            return True

    target = logging.getLogger("hpg_core.rekordbox_phrases")
    filter_ = Opaque()
    target.addFilter(filter_)
    try:
        yield
    finally:
        target.removeFilter(filter_)

try:
    # Historischer Name bleibt als Mock-Einstieg erhalten; kein schreibender
    # pyrekordbox-Konstruktor darf hier mehr aufgerufen werden.
    from .rekordbox_readonly import open_rekordbox_readonly as Rekordbox6Database
    from pyrekordbox.db6 import tables
    from sqlalchemy.orm import joinedload

    REKORDBOX_AVAILABLE = True
except ImportError:
    REKORDBOX_AVAILABLE = False
    logger.info("pyrekordbox nicht installiert. Rekordbox-Import nicht verfuegbar.")
    logger.info("Installation: pip install pyrekordbox")


@dataclass
class RekordboxTrackData:
    """Container for Rekordbox analyzed track data"""

    bpm: Optional[float] = None
    key: Optional[str] = None  # Rekordbox notation (e.g., "Am", "C")
    camelot_code: Optional[str] = None  # Converted to Camelot (e.g., "8A", "8B")
    duration: Optional[float] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    genre: Optional[str] = None
    album: Optional[str] = None
    rating: Optional[int] = None
    cue_points: Optional[List[Dict]] = None
    color: Optional[str] = None
    # Downbeat-Feature 2026-07-17: DB-Content-ID fuer den lazy ANLZ-Zugriff
    # (Beatgrid/PQTZ liegt in den .DAT-Analysedateien, nicht in master.db)
    content_id: Optional[str] = None



@dataclass
class RekordboxCoverage:
    """Wie viele Tracks eines Laufs konnten Rekordbox-Daten nutzen?

    Trennt die drei Faelle, die im Log sonst alle gleich aussehen:
    analysiert, in der Collection aber unanalysiert, gar nicht vorhanden.
    """

    available: bool = False
    total: int = 0
    with_analysis: int = 0
    without_analysis: int = 0
    ambiguous: int = 0
    not_in_collection: int = 0
    examples_without_analysis: List[str] = field(default_factory=list)
    examples_ambiguous: List[str] = field(default_factory=list)

    @property
    def degraded(self) -> int:
        """Tracks, die Rekordbox-Daten haetten haben koennen, aber keine hatten."""
        return self.without_analysis + self.ambiguous


def _hat_tag(anlz_file, key: str) -> bool:
    """True, wenn die ANLZ-Datei den Tag `key` liefert (pyrekordbox wirft sonst)."""
    try:
        anlz_file.get_tag(key)
        return True
    except Exception:
        return False


class RekordboxImporter:
    """
    Imports track analysis data from Rekordbox 6/7 database

    Usage:
        importer = RekordboxImporter()
        if importer.is_available():
            data = importer.get_track_data("/path/to/track.wav")
            print(f"BPM: {data.bpm}, Key: {data.camelot_code}")
    """

    # Rekordbox stores keys in MIXED formats:
    # - Most tracks: Camelot codes (1A-12A, 1B-12B)
    # - Some tracks: Musical notation (Am, Fm, C, etc.)
    # We need to handle both!

    def __init__(self):
        """Initialize Rekordbox Importer"""
        self.db = None
        self.track_cache: Dict[str, RekordboxTrackData] = {}
        # Mehrere master.db-Records koennen auf dieselbe Datei zeigen. Bei
        # widerspruechlichen Analysewerten ist auch der exakte Pfad unsicher.
        self._ambiguous_paths: set[str] = set()
        # Mehrdeutige Basenames duerfen nie stillschweigend den ersten Track
        # liefern: bei verschobenen Dateien waeren BPM/Key/Cues sonst falsch.
        self.basename_cache: Dict[str, Optional[RekordboxTrackData]] = {}
        # Memo fuer lazy geparste ANLZ-Downbeats (content_id -> Sekunden oder None)
        self._downbeat_cache: Dict[str, Optional[float]] = {}
        # Vollstaendiger PQTZ-Verlauf; notwendig fuer Driftpruefung und
        # Cache-Invalidierung nach manueller Gridkorrektur in Rekordbox.
        self._beatgrid_cache: Dict[str, List[Dict]] = {}
        # PSSI-Ende haengt von der effektiven Trackdauer ab. Ein expliziter
        # Analysewert darf daher den parameterlosen Signaturwert nicht vergiften.
        self._phrases_cache: Dict[tuple[str, float], List[Dict]] = {}
        # Ein ANLZ-Snapshot je content_id. Signatur, Beatgrid, Downbeat und
        # Phrasen eines Analyselaufs muessen aus exakt denselben Dateien stammen.
        self._anlz_cache: Dict[str, list] = {}
        # Nur Lesebelege, niemals Teil der bisherigen Nutzdaten/Signatur.
        self._anlz_read_status: Dict[str, dict] = {}
        self._read_status_cache: Dict[tuple, str] = {}

        # Debug-/Validierungs-Schalter (2026-07-17): erzwingt die volle
        # Librosa-Analyse, auch wenn Tracks in der Rekordbox-DB stehen
        if os.environ.get("HPG_DISABLE_REKORDBOX"):
            logger.info("Rekordbox-Import per HPG_DISABLE_REKORDBOX deaktiviert")
            return

        if REKORDBOX_AVAILABLE:
            try:
                self.db = Rekordbox6Database()
                self._build_track_cache()
                logger.info(f"Rekordbox-DB geladen: {len(self.track_cache)} Tracks")
            except ReadOnlyRekordboxError:
                self.close()
                logger.warning("Rekordbox-Quelle konnte nicht sicher schreibgeschuetzt gelesen werden.")
            except Exception:
                # Treibertexte koennen SQLCipher-Schluessel enthalten.
                self.close()
                logger.warning("Rekordbox-Quelle konnte nicht geladen werden.")

    def close(self) -> None:
        """Reader freigeben und jeden davon abhaengigen Teilzustand verwerfen."""
        db, self.db = self.db, None
        self.track_cache.clear()
        self.basename_cache.clear()
        self._ambiguous_paths.clear()
        self._downbeat_cache.clear()
        self._beatgrid_cache.clear()
        self._phrases_cache.clear()
        self._anlz_cache.clear()
        getattr(self, "_anlz_read_status", {}).clear()
        getattr(self, "_read_status_cache", {}).clear()
        if db is not None:
            closer = getattr(db, "close", None)
            if closer is not None:
                try:
                    closer()
                except Exception:
                    logger.warning("Rekordbox-Reader konnte nicht vollstaendig freigegeben werden.")

    def is_available(self) -> bool:
        """Check if Rekordbox database is available"""
        return self.db is not None and len(self.track_cache) > 0

    @staticmethod
    def _safe_bpm(raw_bpm) -> Optional[float]:
        """Sicherer BPM-Wert aus Rekordbox (BPM * 100 gespeichert).

        Audit-Fix 2026-07-17: Sanity-Range — ein Feld, das ausnahmsweise schon
        in BPM steht (oder Muell enthaelt), darf nicht als 1.36-BPM-Track
        durchrutschen und spaeter jeden BPM-Gate reissen.
        """
        if not raw_bpm:
            return None
        try:
            bpm = float(raw_bpm) / 100.0
            if 40.0 <= bpm <= 250.0:
                return bpm
            # Vielleicht war der Rohwert bereits in BPM?
            raw = float(raw_bpm)
            if 40.0 <= raw <= 250.0:
                return raw
            return None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_duration(raw_duration) -> Optional[float]:
        """Uebernimmt nur endliche positive Rekordbox-Dauern."""
        if isinstance(raw_duration, bool):
            return None
        try:
            duration = float(raw_duration)
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(duration) or duration <= 0.0:
            return None
        return duration

    def _build_track_cache(self):
        """Build fast lookup cache of all Rekordbox tracks"""
        if not self.db:
            return

        try:
            # Query the database directly to eagerly load related tables
            # This avoids the N+1 problem when accessing properties like Cues, KeyName, etc.
            if hasattr(self.db, "query"):
                query = self.db.query(tables.DjmdContent).options(
                    joinedload(tables.DjmdContent.Cues),
                    joinedload(tables.DjmdContent.Key),
                    joinedload(tables.DjmdContent.Artist),
                    joinedload(tables.DjmdContent.Genre),
                    joinedload(tables.DjmdContent.Album),
                    joinedload(tables.DjmdContent.Color),
                )
                content_iterator = query
            else:
                # Fallback if DB layout changes
                content_iterator = self.db.get_content()

            for content in content_iterator:
                try:
                    self._cache_content_record(content)
                except ReadOnlyRekordboxError:
                    raise
                except Exception as error:
                    try:
                        file_name = getattr(content, "FileNameL", None) or getattr(
                            content, "FileNameS", None
                        )
                    except Exception:
                        file_name = "<unlesbar>"
                    try:
                        content_id = getattr(content, "ID", None)
                    except Exception:
                        content_id = "<unlesbar>"
                    logger.warning(
                        "Defekter Rekordbox-Track verworfen (ID=%r, Datei=%r): %s",
                        content_id,
                        file_name,
                        error,
                    )

        except Exception:
            # Auch Abfrageabbrueche duerfen keinen scheinbar gueltigen
            # Teilimport publizieren. Der Konstruktor uebernimmt die Meldung.
            self.close()
            raise

    def _cache_content_record(self, content) -> None:
        """Validiert und uebernimmt genau einen Rekordbox-Content-Record."""
        # DjmdContent.FolderPath ist bereits der volle Dateipfad.
        folder_path = content.FolderPath or ""
        file_name = content.FileNameL or content.FileNameS or ""
        if not file_name:
            return

        if folder_path:
            full_path = os.path.normpath(folder_path).lower()
        else:
            logger.debug(
                "Rekordbox-Track ohne FolderPath, nur Basename-Zuordnung: %s",
                file_name,
            )
            full_path = ""

        data = RekordboxTrackData(
            bpm=self._safe_bpm(content.BPM),
            key=content.KeyName if hasattr(content, "KeyName") else None,
            duration=self._safe_duration(getattr(content, "Length", None)),
            title=content.Title,
            artist=content.ArtistName if hasattr(content, "ArtistName") else None,
            genre=content.GenreName if hasattr(content, "GenreName") else None,
            album=content.AlbumName if hasattr(content, "AlbumName") else None,
            rating=content.Rating if content.Rating else None,
            color=content.ColorName if hasattr(content, "ColorName") else None,
            content_id=str(content.ID) if hasattr(content, "ID") else None,
        )

        if data.key:
            data.camelot_code = self._convert_key_to_camelot(data.key)
            if not data.camelot_code:
                logger.debug(
                    "Rekordbox-Key nicht konvertierbar: %r (%s)",
                    data.key,
                    file_name,
                )

        if hasattr(content, "Cues") and content.Cues:
            data.cue_points = self._extract_cue_points(content.Cues)

        basename = (
            os.path.basename(full_path)
            if full_path
            else os.path.basename(file_name).lower()
        )
        if full_path:
            existing_path_data = self.track_cache.get(full_path)
            if existing_path_data is None:
                self.track_cache[full_path] = data
            elif self._track_data_conflicts(existing_path_data, data):
                self._ambiguous_paths.add(full_path)
                logger.warning(
                    "Widerspruechliche Rekordbox-Records fuer Pfad verworfen: %s",
                    full_path,
                )
            elif self._track_data_quality(data) > self._track_data_quality(
                existing_path_data
            ):
                self.track_cache[full_path] = data

        if basename:
            existing = self.basename_cache.get(basename)
            if existing is None and basename in self.basename_cache:
                return
            if existing is not None and existing is not data:
                self.basename_cache[basename] = None
            else:
                self.basename_cache[basename] = data

    @staticmethod
    def _track_data_quality(data: RekordboxTrackData) -> int:
        """Bewertet, wie belastbar ein Rekordbox-Record analysiert ist."""
        return sum(
            value is not None
            for value in (data.bpm, data.camelot_code, data.duration, data.title)
        ) + len(data.cue_points or [])

    @staticmethod
    def _track_data_conflicts(
        left: RekordboxTrackData, right: RekordboxTrackData
    ) -> bool:
        """Erkennt widerspruechliche Werte, nicht nur doppelte Content-IDs."""
        for left_value, right_value in (
            (left.bpm, right.bpm),
            (left.camelot_code, right.camelot_code),
            (left.duration, right.duration),
            (left.title, right.title),
            (left.artist, right.artist),
            (left.genre, right.genre),
        ):
            if left_value is not None and right_value is not None and left_value != right_value:
                return True
        if (
            left.content_id
            and right.content_id
            and left.content_id != right.content_id
        ):
            return True
        if left.cue_points and right.cue_points:
            left_cues = sorted(
                json.dumps(cue, sort_keys=True, default=str)
                for cue in left.cue_points
            )
            right_cues = sorted(
                json.dumps(cue, sort_keys=True, default=str)
                for cue in right.cue_points
            )
            if left_cues != right_cues:
                return True
        return False

    def _convert_key_to_camelot(self, rekordbox_key: str) -> Optional[str]:
        """
        Convert/validate Rekordbox key to Camelot code using central definition.
        """
        key = rekordbox_key.strip()

        # 1. Check if it's already a Camelot code (Value in CAMELOT_MAP)
        if key in CAMELOT_MAP.values():
            return key

        # 2. Convert Musical Notation -> Camelot
        # Detect Mode
        if key.endswith("m"):
            mode = "Minor"
            note = key[:-1]
        else:
            mode = "Major"
            note = key

        # Handle Flat -> Sharp conversion (CAMELOT_MAP uses Sharps)
        flat_to_sharp = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
        if note in flat_to_sharp:
            note = flat_to_sharp[note]

        return CAMELOT_MAP.get((note, mode))

    def _extract_cue_points(self, cues) -> List[Dict]:
        """
        Extract cue points from Rekordbox Cues relationship

        Args:
            cues: Rekordbox Cues objects

        Returns:
            List of cue point dictionaries with position and name
        """
        cue_list = []

        for cue in cues:
            try:
                # Audit-Fix 2026-07-17: Memory-Cues ohne Position liefern
                # InMsec = -1/None — nicht als Cue bei -0.001s durchreichen
                raw_msec = getattr(cue, "InMsec", None)
                # Rekordbox-Cues nennen das Feld explizit InMsec.
                position = self._milliseconds_to_seconds(raw_msec)
                if position is None:
                    continue
                cue_data = {
                    "position": position,
                    "name": cue.Comment if hasattr(cue, "Comment") else None,
                    "type": cue.Kind if hasattr(cue, "Kind") else None,
                    "hot_cue_number": (
                        cue.HotCueBankNumber
                        if hasattr(cue, "HotCueBankNumber")
                        else None
                    ),
                    "color": cue.ColorID if hasattr(cue, "ColorID") else None,
                }
                cue_list.append(cue_data)
            except Exception as error:
                logger.warning("Defekter Rekordbox-Cue verworfen: %s", error)

        return cue_list

    def get_first_downbeat(self, file_path: str) -> Optional[float]:
        """
        Liest den ersten Downbeat (Sekunden) aus dem Rekordbox-Beatgrid.

        Downbeat-Feature 2026-07-17: Der echte Beatgrid liegt in den
        ANLZ-Analysedateien (.DAT, PQTZ-Tag) — jeder Tick traegt seine
        Beat-Nummer 1..4; der erste Tick mit beat==1 ist die erste "1".
        Lazy geparst (nur bei Bedarf, memoisiert), da ANLZ-Dateien nicht
        beim Cache-Aufbau geladen werden.

        Returns:
            Sekunden des ersten Downbeats oder None (nicht verfuegbar).

        Vertrag: Dieser Importer liefert ausschliesslich ``first_downbeat``,
        also den Takt-Anker der ersten "1". ``phrase_anchor`` wird downstream
        aus der Phrasen-Erkennung gewaehlt und kann bei ausreichender
        Konfidenz spaeter auf einer anderen Phrasengrenze liegen.
        """
        data = self.get_track_data(file_path)
        if not data or not data.content_id or self.db is None:
            return None

        if data.content_id in self._downbeat_cache:
            return self._downbeat_cache[data.content_id]

        result = next(
            (point["time"] for point in self.get_beatgrid(file_path)
             if point["beat"] == 1),
            None,
        )

        self._downbeat_cache[data.content_id] = result
        return result

    def get_beatgrid(self, file_path: str) -> List[Dict]:
        """Liefert den vollstaendigen normalisierten PQTZ-Beatverlauf."""
        data = self.get_track_data(file_path)
        if not data or not data.content_id:
            return []
        if data.content_id in self._beatgrid_cache:
            return deepcopy(self._beatgrid_cache[data.content_id])
        if self.db is None:
            return []
        result: List[Dict] = []
        state = "unverified"
        token = _detail_uncertain.set(False)
        try:
            files = self._read_anlz_files(data.content_id)
            result = self._extract_beatgrid_from_anlz(files)
            evidence = _tag_evidence(files, ("PQTZ", "PQT2", "beat_grid", "beats"))
            source = getattr(self, "_anlz_read_status", {}).get(data.content_id, {})
            if evidence == "unverified" or _detail_uncertain.get():
                state = "unverified"
            elif result:
                state = "ok"
            elif evidence == "missing" and (source.get("all") or source.get("dat")):
                state = "missing"
            elif source.get("error") and not source.get("dat"):
                state = "error"
        except ReadOnlyRekordboxError:
            self.close()
            raise
        except Exception:
            state = "error"
            logger.warning("Rekordbox-Beatgrid konnte nicht gelesen werden.")
        finally:
            _detail_uncertain.reset(token)
        self._store_read_status(data, "beatgrid", None, state)
        self._beatgrid_cache[data.content_id] = deepcopy(result)
        return deepcopy(self._beatgrid_cache[data.content_id])

    def _read_anlz_files(self, content_id: str) -> list:
        """Alle ANLZ-Dateien (DAT/EXT/2EX) eines Tracks, robust gegen die
        pyrekordbox-API.

        AUDIT-FIX RB-01 (2026-07-24, aus get_first_downbeat hierher
        verschoben): Vorher wurde ausschliesslich
        `read_anlz_file(content_id, "DAT")` + flache `.beats`/`.times`
        probiert — beides passt nicht zur aktuellen API, der Aufruf
        scheiterte still (DEBUG-Log) und der exakte Downbeat-Pfad war
        damit IMMER tot (nie confidence 1.0). Jetzt: mehrere API-Formen
        versuchen; per-Entry-Zugriff (.beat/.time) liegt beim Aufrufer.
        """
        cache = getattr(self, "_anlz_cache", None)
        if cache is None:
            cache = self._anlz_cache = {}
        if content_id in cache:
            return list(cache[content_id])
        anlz_files = []
        if self.db is None:
            return anlz_files
        status = {"all": False, "dat": False, "error": False}
        for reader, args in (
            (getattr(self.db, "read_anlz_files", None), (content_id,)),
            (getattr(self.db, "read_anlz_file", None), (content_id, "DAT")),
        ):
            if reader is None:
                continue
            try:
                res = reader(*args)
            except ReadOnlyRekordboxError:
                self.close()
                raise
            except Exception:
                status["error"] = True
                continue
            # Erfolgreiches Gesamtlesen belegt auch fehlende optionale Dateien.
            if len(args) == 1:
                status["all"] = isinstance(res, dict)
            else:
                status["dat"] = True
            if res is None:
                continue
            # read_anlz_files liefert dict {path: AnlzFile}, read_anlz_file ein Objekt
            if isinstance(res, dict):
                anlz_files.extend(res.values())
            else:
                anlz_files.append(res)
            if anlz_files:
                break
        cache[content_id] = list(anlz_files)
        self.__dict__.setdefault("_anlz_read_status", {})[content_id] = status
        return list(anlz_files)

    def get_phrases(
        self, file_path: str, *, duration: Optional[float] = None
    ) -> List[Dict]:
        """Rekordbox-Phrasen (PSSI) eines Tracks in Sekunden, memoisiert.

        Leer, wenn kein Rekordbox-Eintrag, keine EXT-Datei oder kein PSSI-Tag.
        Zeiten stammen aus dem PQTZ-Beatgrid derselben ANLZ-Gruppe.
        """
        from .rekordbox_phrases import phrases_from_anlz

        data = self.get_track_data(file_path)
        if not data or not data.content_id:
            return []
        effective_duration = 0.0
        for candidate in (duration, data.duration):
            try:
                value = float(candidate)
            except (OverflowError, TypeError, ValueError):
                continue
            if math.isfinite(value) and value > 0.0:
                effective_duration = value
                break
        cache_key = (data.content_id, effective_duration)
        # Memo-Treffer vor der db-Pruefung: einmal gelesene Phrasen bleiben
        # gueltig, auch wenn die DB-Verbindung spaeter wegfaellt.
        if cache_key in self._phrases_cache:
            return deepcopy(self._phrases_cache[cache_key])
        if self.db is None:
            return []
        result: List[Dict] = []
        state = "unverified"
        token = _detail_uncertain.set(False)
        try:
            files = self._read_anlz_files(data.content_id)
            ext = next((f for f in files if _hat_tag(f, "PSSI")), None)
            dat = next((f for f in files if _hat_tag(f, "PQTZ")), None)
            with _opaque_phrase_logging():
                result = phrases_from_anlz(ext, dat, effective_duration)
            pssi = _tag_evidence(files, ("PSSI",))
            pqtz = _tag_evidence(files, ("PQTZ",))
            source = getattr(self, "_anlz_read_status", {}).get(data.content_id, {})
            if "unverified" in (pssi, pqtz) or _detail_uncertain.get():
                state = "unverified"
            elif result:
                state = "ok"
            elif "missing" in (pssi, pqtz) and source.get("all"):
                state = "missing"
            elif source.get("error") and not source.get("dat"):
                state = "error"
        except ReadOnlyRekordboxError:
            self.close()
            raise
        except Exception:
            state = "error"
            logger.warning("Rekordbox-Phrasen konnten nicht gelesen werden.")
        finally:
            _detail_uncertain.reset(token)
        self._store_read_status(data, "phrases", effective_duration, state)
        self._phrases_cache[cache_key] = deepcopy(result)
        return deepcopy(self._phrases_cache[cache_key])

    @staticmethod
    def _extract_first_downbeat_from_anlz(anlz_files) -> Optional[float]:
        """Extrahiert die erste '1' aus PQTZ-Tags, robust gegen mehrere
        pyrekordbox-Tag-Formen (flache .beats/.times ODER per-Entry .beat/.time).
        AUDIT-FIX RB-01."""
        return next(
            (point["time"] for point in
             RekordboxImporter._extract_beatgrid_from_anlz(anlz_files)
             if point["beat"] == 1),
            None,
        )

    @staticmethod
    def _extract_beatgrid_from_anlz(anlz_files) -> List[Dict]:
        """Extrahiert alle gueltigen Beatnummern und Zeiten eines PQTZ-Tags."""
        for anlz_file in anlz_files:
            for tag_key in ("PQTZ", "PQT2", "beat_grid", "beats"):
                tag = None
                try:
                    getter = getattr(anlz_file, "get_tag", None)
                    tag = getter(tag_key) if getter else None
                except Exception:
                    tag = None
                if tag is None:
                    tag = getattr(anlz_file, tag_key, None)
                if tag is None:
                    continue

                points: List[Dict] = []
                # Form A: flache Parallel-Listen
                beats = getattr(tag, "beats", None)
                times = getattr(tag, "times", None)
                if beats is not None and times is not None:
                    try:
                        equal_lengths = len(beats) == len(times)
                    except TypeError:
                        equal_lengths = False
                    if not equal_lengths:
                        _detail_uncertain.set(True)
                    for beat_num, raw_time in zip(beats, times):
                        try:
                            # pyrekordbox normalisiert ``PQTZAnlzTag.times``
                            # bereits von Millisekunden auf Sekunden.
                            position = float(raw_time)
                            beat = int(beat_num)
                            if (
                                1 <= beat <= 4
                                and math.isfinite(position)
                                and position >= 0.0
                            ):
                                points.append({"beat": beat, "time": position})
                            else:
                                _detail_uncertain.set(True)
                        except (OverflowError, TypeError, ValueError):
                            _detail_uncertain.set(True)
                            continue
                    if points:
                        return points

                # Form B: iterierbare Entries mit .beat/.time
                entries = getattr(tag, "entries", None) or (tag if hasattr(tag, "__iter__") else None)
                if entries is not None:
                    try:
                        for entry in entries:
                            try:
                                beat = getattr(entry, "beat", None)
                                t = getattr(entry, "time", None)
                                position = RekordboxImporter._milliseconds_to_seconds(t)
                                beat = int(beat) if beat is not None else 0
                                if 1 <= beat <= 4 and position is not None:
                                    points.append({"beat": beat, "time": position})
                                else:
                                    _detail_uncertain.set(True)
                            except (AttributeError, OverflowError, TypeError, ValueError):
                                _detail_uncertain.set(True)
                                logger.warning(
                                    "Defekter Rekordbox-PQTZ-Eintrag verworfen.",
                                )
                    except (TypeError, ValueError):
                        _detail_uncertain.set(True)
                        logger.warning("Rekordbox-PQTZ-Liste nicht lesbar.")
                        continue
                    if points:
                        return points
        return []

    @staticmethod
    def _milliseconds_to_seconds(raw_time) -> Optional[float]:
        """Normalisiert einen Rekordbox-Zeitwert aus Millisekunden."""
        try:
            value = float(raw_time)
        except (OverflowError, TypeError, ValueError):
            return None
        if not math.isfinite(value) or value < 0:
            return None
        return round(value / 1000.0, 4)

    def get_track_data(self, file_path: str) -> Optional[RekordboxTrackData]:
        """
        Get Rekordbox analysis data for a specific track

        Args:
            file_path: Absolute path to audio file

        Returns:
            RekordboxTrackData object with analysis data, or None if not found
        """
        if not self.is_available():
            return None

        # Normalize path for lookup
        normalized_path = os.path.normpath(file_path).lower()

        # Try exact match
        if normalized_path in self._ambiguous_paths:
            logger.warning(
                "Mehrdeutige Rekordbox-Pfadzuordnung verworfen: %s", normalized_path
            )
            return None
        if normalized_path in self.track_cache:
            return self.track_cache[normalized_path]

        # Try filename-only match (fallback for moved files)
        filename = os.path.basename(normalized_path)
        fallback = self.basename_cache.get(filename)
        if fallback is not None:
            logger.debug(f"Rekordbox-Match per Dateiname: {filename}")
            return fallback
        if filename in self.basename_cache:
            logger.warning(
                "Mehrdeutiger Rekordbox-Basename-Fallback verworfen: %s", filename
            )

        return None

    @staticmethod
    def _read_context(data) -> str:
        return json.dumps(data.__dict__, sort_keys=True, default=str)

    def _store_read_status(self, data, detail, duration, state):
        self.__dict__.setdefault("_read_status_cache", {})[
            (data.content_id, self._read_context(data), detail, duration)] = state

    def get_track_read_status(self, file_path: str) -> Dict[str, str]:
        """Nur aktuelle Match-/Statusmemos lesen, niemals ANLZ oder DB oeffnen."""
        unknown = {"beatgrid": "unverified", "phrases": "unverified"}
        data = self.get_track_data(file_path)
        if data is None or not data.content_id:
            return unknown
        context = self._read_context(data)
        duration = 0.0
        try:
            candidate = float(data.duration)
            if math.isfinite(candidate) and candidate > 0:
                duration = candidate
        except (TypeError, ValueError, OverflowError):
            pass
        return {name: getattr(self, "_read_status_cache", {}).get(
                    (data.content_id, context, name, value), "unverified")
                for name, value in (("beatgrid", None), ("phrases", duration))}

    def get_track_signature(self, file_path: str) -> str:
        """Liefert eine stabile Signatur der importierten RB-Metadaten.

        Die Audio-Datei kann unveraendert bleiben, waehrend BPM, Key oder Cues
        in Rekordbox geaendert werden. Diese Signatur bindet solche Aenderungen
        an den HPG-Cache-Key.
        """
        data = self.get_track_data(file_path)
        if data is None:
            return ""
        if data.content_id:
            getattr(self, "_anlz_read_status", {}).pop(data.content_id, None)
            for status_key in tuple(getattr(self, "_read_status_cache", {})):
                if status_key[0] == data.content_id:
                    self._read_status_cache.pop(status_key, None)
            self._anlz_cache.pop(data.content_id, None)
            self._beatgrid_cache.pop(data.content_id, None)
            self._downbeat_cache.pop(data.content_id, None)
            for cache_key in tuple(self._phrases_cache):
                if cache_key[0] == data.content_id:
                    self._phrases_cache.pop(cache_key, None)
        payload_data = dict(data.__dict__)
        payload_data["beatgrid"] = self.get_beatgrid(file_path)
        # get_beatgrid fuellt _anlz_cache; get_phrases liest dadurch exakt
        # denselben ANLZ-Snapshot statt die zwischenzeitlich veraenderbaren
        # DAT/EXT-Dateien ein zweites Mal zu oeffnen.
        payload_data["phrases"] = self.get_phrases(file_path)
        payload = json.dumps(payload_data, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def summarize_coverage(self, file_paths) -> "RekordboxCoverage":
        """Zaehlt aus, wie viele der Dateien Rekordbox-Daten liefern konnten.

        Ohne diese Auswertung faellt HPG bei unanalysierten Collection-Tracks
        still auf die Librosa-Vollanalyse zurueck — das Ergebnis ist brauchbar,
        aber langsamer und ohne Rekordbox-Beatgrid, und niemand erfaehrt davon.
        """
        summary = RekordboxCoverage(available=self.is_available())
        if not summary.available:
            return summary

        for file_path in file_paths:
            summary.total += 1
            data = self.get_track_data(file_path)
            if data is not None and data.bpm:
                summary.with_analysis += 1
                continue

            name = os.path.basename(file_path)
            if data is not None:
                # Record vorhanden, aber in Rekordbox nie analysiert (BPM 0).
                summary.without_analysis += 1
                if len(summary.examples_without_analysis) < 3:
                    summary.examples_without_analysis.append(name)
                continue

            normalized = os.path.normpath(file_path).lower()
            basename = os.path.basename(normalized)
            is_ambiguous = normalized in self._ambiguous_paths or (
                basename in self.basename_cache
                and self.basename_cache[basename] is None
            )
            if is_ambiguous:
                summary.ambiguous += 1
                if len(summary.examples_ambiguous) < 3:
                    summary.examples_ambiguous.append(name)
            else:
                summary.not_in_collection += 1

        return summary

    def get_available_count(self) -> int:
        """Get number of tracks available in Rekordbox database"""
        return len(self.track_cache) - len(self._ambiguous_paths)

    def has_track(self, file_path: str) -> bool:
        """Check if track exists in Rekordbox database"""
        return self.get_track_data(file_path) is not None

    def get_statistics(self) -> Dict:
        """Get statistics about Rekordbox database content"""
        if not self.is_available():
            return {
                "available": False,
                "total_tracks": 0,
            }

        available_paths = set(self.track_cache) - self._ambiguous_paths
        available_data = [self.track_cache[path] for path in available_paths]
        stats = {
            "available": True,
            "total_tracks": len(available_paths),
            "tracks_with_bpm": sum(1 for d in available_data if d.bpm),
            "tracks_with_key": sum(
                1 for d in available_data if d.camelot_code
            ),
            "tracks_with_cues": sum(
                1 for d in available_data if d.cue_points
            ),
            "average_bpm": None,
        }

        # Calculate average BPM
        bpms = [d.bpm for d in available_data if d.bpm]
        if bpms:
            stats["average_bpm"] = sum(bpms) / len(bpms)

        return stats


# Global singleton instance
_rekordbox_importer: Optional[RekordboxImporter] = None


def get_rekordbox_importer() -> RekordboxImporter:
    """Get or create global RekordboxImporter singleton"""
    global _rekordbox_importer
    if _rekordbox_importer is None:
        _rekordbox_importer = RekordboxImporter()
    return _rekordbox_importer


def is_rekordbox_running() -> bool:
    """True, wenn gerade ein Rekordbox-Prozess laeuft.

    Rekordbox haelt seine Aenderungen im SQLite-WAL und checkpointet erst beim
    Beenden nach master.db. Solange die App laeuft, liest HPG daher womoeglich
    einen veralteten Stand — frisch analysierte Tracks fehlen dann noch.
    """
    if not REKORDBOX_AVAILABLE:
        return False
    try:
        from pyrekordbox.utils import get_rekordbox_pid

        return bool(get_rekordbox_pid())
    except Exception as exc:  # psutil-Ausfall darf den Start nicht kippen
        logger.debug("Rekordbox-Prozesspruefung fehlgeschlagen: %s", exc)
        return False

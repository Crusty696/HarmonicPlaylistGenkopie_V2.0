"""
Rekordbox XML Exporter - Professional DJ Integration

Exports playlists in Rekordbox XML format with full metadata:
- BPM, Key, Genre
- Hot Cues A/B + Memory Cues fuer Mix In/Out
- Memory Cues fuer erkannte Sektionen (Drop/Breakdown)
- Beat Grid (TEMPO-Element, Anker bei 0.0s)
- Playlist Hierarchy

Compatible with Rekordbox 5.x, 6.x, 7.x
"""

import logging
import math
import os
import tempfile
import xml.etree.ElementTree as ET
from typing import List, Optional
from ..downbeat import REFERENCE_BEATGRID_CONFIDENCE
from ..models import QUANTIZE_TOLERANCE_SEC, Track
from .base_exporter import BaseExporter, ExportReport

logger = logging.getLogger(__name__)

try:
    from pyrekordbox.rbxml import RekordboxXml

    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    logging.getLogger(__name__).warning("pyrekordbox nicht installiert. Install: pip install pyrekordbox")


class RekordboxXMLExporter(BaseExporter):
    """
    Rekordbox XML Exporter - Professional DJ Integration

    Features:
    - Metadata (BPM, Key, Genre)
    - Hot Cues A/B + Memory Cues (Mix In/Out), Sektions-Cues (Drop/Breakdown)
    - Beat Grid (TEMPO-Element)
    - Playlist hierarchy
    - Rekordbox 5.x, 6.x, 7.x compatible
    """

    # Camelot Wheel → Rekordbox Key Mapping
    CAMELOT_TO_REKORDBOX = {
        # Major Keys (B)
        "1B": "B",
        "2B": "Gb",
        "3B": "Db",
        "4B": "Ab",
        "5B": "Eb",
        "6B": "Bb",
        "7B": "F",
        "8B": "C",
        "9B": "G",
        "10B": "D",
        "11B": "A",
        "12B": "E",
        # Minor Keys (A)
        "1A": "Abm",
        "2A": "Ebm",
        "3A": "Bbm",
        "4A": "Fm",
        "5A": "Cm",
        "6A": "Gm",
        "7A": "Dm",
        "8A": "Am",
        "9A": "Em",
        "10A": "Bm",
        "11A": "Gbm",
        "12A": "Dbm",
    }

    def __init__(self):
        """
        Initialize Rekordbox XML Exporter

        Raises:
            ImportError: If pyrekordbox is not installed
        """
        if not PYREKORDBOX_AVAILABLE:
            raise ImportError(
                "pyrekordbox is required for Rekordbox XML export. "
                "Install with: pip install pyrekordbox"
            )

    def export(
        self,
        playlist: List[Track],
        output_path: str,
        playlist_name: str = "HPG Playlist",
        transitions: Optional[list] = None,
    ) -> ExportReport:
        """
        Export playlist to Rekordbox XML format

        Args:
            playlist: List of Track objects
            output_path: Path to save rekordbox.xml
            playlist_name: Name of the playlist
            transitions: optional TransitionRecommendations (len(playlist)-1),
                Spec 2026-08-21 Abschnitt 4: MIX OUT von Track i = Plan von
                Paar i, MIX IN von Track i = Plan von Paar i-1
                (aktiver TransitionPlan),
                dazu Memory-Cues "HPG K<n> OUT/IN <schema>" aller Kandidaten

        Raises:
            ValueError: If playlist is empty or invalid
            IOError: If file cannot be written
            ImportError: If pyrekordbox is not available
        """
        # Validate playlist
        self._validate_playlist(playlist)

        temp_path = ""
        errors = []
        tracks_written = 0
        cues_written = 0
        beatgrids_written = 0
        # Collection-Eintraege sind je Location eindeutig, Playlist-Eintraege
        # dagegen Occurrences. A -> B -> A braucht deshalb zwei Collection-
        # Tracks, aber drei Playlist-Referenzen (1, 2, 1).
        unique_by_location = {}
        points_by_location = {}
        occurrence_locations = []
        # TransitionPlan-Zeitpunkte je Playlist-Position (Spec Abschnitt 4); die
        # Zuordnung folgt der Playlist-Reihenfolge, nicht der Dedupe-Liste.
        punkte_je_track = self._kandidaten_punkte(playlist, transitions)
        for pos, track in enumerate(playlist):
            if not track.filePath:
                errors.append(
                    "Track uebersprungen (kein Dateipfad): "
                    + (track.title or track.fileName or "?")
                )
                continue
            loc = os.path.normcase(os.path.abspath(track.filePath))
            occurrence_locations.append(loc)
            unique_by_location.setdefault(loc, track)
            points_by_location.setdefault(loc, []).append(
                punkte_je_track.get(pos, {})
            )

        unique_tracks = []
        for loc, track in unique_by_location.items():
            punkte, conflicts = self._merge_occurrence_points(
                points_by_location[loc]
            )
            for side in conflicts:
                errors.append(
                    f"{track.filePath}: mehrere Occurrences haben "
                    f"widerspruechliche {side}-Punkte; generischer Cue ausgelassen"
                )
            unique_tracks.append((loc, track, punkte))

        try:
            # Create new Rekordbox XML
            xml = RekordboxXml()

            # Add tracks to collection — nur erfolgreich geschriebene IDs merken,
            # damit die Playlist-Referenzen nie auf fehlende TrackIDs zeigen.
            id_by_location = {}
            for idx, (loc, track, punkte) in enumerate(unique_tracks, start=1):
                try:
                    cue_count, beatgrid_count, track_errors = (
                        self._add_track_to_collection(
                            xml, track, idx,
                            mix_in=punkte.get("mix_in"), mix_out=punkte.get("mix_out"),
                            extra=punkte.get("extra", ()),
                            suppress_mix_in=punkte.get("suppress_mix_in", False),
                            suppress_mix_out=punkte.get("suppress_mix_out", False),
                        )
                    )
                    tracks_written += 1
                    id_by_location[loc] = str(idx)
                    cues_written += cue_count
                    beatgrids_written += beatgrid_count
                    errors.extend(track_errors)
                except Exception as exc:
                    errors.append(f"Track {track.filePath}: {exc}")

            # Create playlist -- get_playlist() wirft auf frischem XML ValueError,
            # Ordner und Playlist muessen explizit angelegt werden
            folder = xml.add_playlist_folder("HPG Playlists")
            pl = folder.add_playlist(playlist_name)
            for loc in occurrence_locations:
                track_id = id_by_location.get(loc)
                if track_id is not None:
                    pl.add_track(track_id)

            output_dir = os.path.dirname(os.path.abspath(output_path))
            os.makedirs(output_dir, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                prefix=".hpg_export_", suffix=".xml", dir=output_dir, delete=False
            )
            temp_path = handle.name
            handle.close()
            xml.save(temp_path)
            ET.parse(temp_path)
            # AUDIT-FIX F3 (2026-07-24): Die harte Vollstaendigkeitspruefung machte
            # den Partial-Export-Mechanismus zunichte — EIN defekter Track (z. B.
            # verschobene Datei) verwarf alle uebrigen. Jetzt: Export nur abbrechen,
            # wenn GAR KEIN Track geschrieben wurde; sonst status="partial" mit
            # Fehlerliste (die GUI zeigt dafuer bereits eine Warnung an).
            if tracks_written == 0:
                raise IOError(
                    f"Kein Track exportierbar (0/{len(playlist)}): "
                    + "; ".join(errors[:3])
                )
            if tracks_written != len(unique_tracks):
                errors.append(
                    f"{len(unique_tracks) - tracks_written} von {len(unique_tracks)} "
                    "Tracks uebersprungen (Details oben)"
                )
            os.replace(temp_path, output_path)
            temp_path = ""

            logger.info(f"Rekordbox XML exportiert: {output_path} ({tracks_written} Tracks, Playlist: {playlist_name})")
            return ExportReport(
                status="partial" if errors else "success",
                output_path=output_path,
                tracks_written=tracks_written,
                cues_written=cues_written,
                beatgrids_written=beatgrids_written,
                errors=tuple(errors),
            )

        except Exception as e:
            raise IOError(f"Failed to export Rekordbox XML: {e}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    logger.warning("Temporaere Exportdatei konnte nicht entfernt werden: %s", temp_path)

    def _add_track_to_collection(
        self, xml: "RekordboxXml", track: Track, track_id: int,
        mix_in: Optional[float] = None, mix_out: Optional[float] = None, extra=(),
        suppress_mix_in: bool = False, suppress_mix_out: bool = False,
    ) -> tuple[int, int, list[str]]:
        """
        Add a single track to the Rekordbox XML collection

        Args:
            xml: RekordboxXml instance
            track: Track object
            track_id: Unique track ID
        """
        # CRITICAL-Fix: rohen absoluten Pfad uebergeben, KEINE fertige URI.
        # pyrekordbox' add_track()/encode_path() baut die file://localhost-URI
        # inkl. Prozent-Kodierung selbst — eine vorgefertigte URI wird dadurch
        # DOPPELT kodiert (file://localhost/file://localhost/...), wodurch
        # Rekordbox nach dem XML-Import keine einzige Datei mehr findet.
        location_path = os.path.abspath(track.filePath)

        # Add track to collection
        rb_track = xml.add_track(location_path)

        try:
            # Basic metadata
            rb_track["TrackID"] = str(track_id)
            rb_track["Name"] = track.title or os.path.basename(track.filePath)
            rb_track["Artist"] = track.artist or "Unknown Artist"
            detected_genre = (track.detected_genre or "").strip()
            raw_genre = (track.genre or "").strip()
            rb_track["Genre"] = (
                detected_genre
                if detected_genre and detected_genre.casefold() != "unknown"
                else raw_genre
            )

            # Duration
            if track.duration:
                rb_track["TotalTime"] = str(int(track.duration))

            # BPM
            if track.bpm:
                rb_track["AverageBpm"] = f"{track.bpm:.2f}"

            # Key (convert from Camelot to Rekordbox notation)
            if track.camelotCode:
                rb_key = self._convert_camelot_to_rekordbox_key(track.camelotCode)
                if rb_key:
                    rb_track["Tonality"] = rb_key

            # Add Beat Grid (TEMPO element)
            beatgrid_count, beatgrid_errors = self._add_beat_grid(rb_track, track)

            # Add Cue Points (Mix In/Out markers + Sektions-Cues)
            cue_count, cue_errors = self._add_cue_points(
                xml, rb_track, track, mix_in=mix_in, mix_out=mix_out, extra=extra,
                suppress_mix_in=suppress_mix_in,
                suppress_mix_out=suppress_mix_out,
            )
            return cue_count, beatgrid_count, beatgrid_errors + cue_errors
        except Exception:
            try:
                xml.remove_track(rb_track)
            except Exception as rollback_error:
                raise RuntimeError(
                    "Track-Export fehlgeschlagen und Collection-Rollback "
                    f"scheiterte: {rollback_error}"
                ) from rollback_error
            raise

    @staticmethod
    def _kandidaten_punkte(playlist: List[Track], transitions) -> dict:
        """Je Playlist-Position: Mixpunkte aus dem aktiven TransitionPlan
        und Memory-Cues aller Kandidaten — MIX OUT/K..OUT aus dem Paar (i, i+1),
        MIX IN/K..IN aus dem Paar (i-1, i). Ohne Empfehlungen: leer (Track-Werte)."""
        punkte: dict = {}
        if not transitions:
            return punkte
        for position, rec in enumerate(transitions):
            try:
                i = int(getattr(rec, "index", position))
            except (TypeError, ValueError):
                continue
            if i < 0:
                continue
            if i + 1 >= len(playlist):
                continue
            plan = getattr(rec, "plan", None)
            if plan is None:
                punkte.setdefault(i, {})["suppress_mix_out"] = True
                punkte.setdefault(i + 1, {})["suppress_mix_in"] = True
                continue
            punkte.setdefault(i, {})["mix_out"] = float(plan.mix_out_a)
            punkte.setdefault(i + 1, {})["mix_in"] = float(plan.mix_in_b)
            punkte[i].setdefault("extra", [])
            punkte[i + 1].setdefault("extra", [])
            punkte[i]["extra"] += RekordboxXMLExporter._kandidaten_cues_out(rec)
            punkte[i + 1]["extra"] += RekordboxXMLExporter._kandidaten_cues_in(rec)
        return punkte

    @staticmethod
    def _merge_occurrence_points(items: list[dict]) -> tuple[dict, list[str]]:
        """Aggregiert Collection-Cues ohne Occurrence-Konflikte zu verstecken."""
        merged: dict = {"extra": []}
        conflicts: list[str] = []
        for side in ("mix_in", "mix_out"):
            suppress_key = f"suppress_{side}"
            values = [float(item[side]) for item in items if side in item]
            if any(bool(item.get(suppress_key)) for item in items):
                merged[suppress_key] = True
                if values:
                    conflicts.append(side.upper().replace("_", " "))
                continue
            if not values:
                continue
            first = values[0]
            if any(abs(value - first) > QUANTIZE_TOLERANCE_SEC for value in values[1:]):
                merged[suppress_key] = True
                conflicts.append(side.upper().replace("_", " "))
            else:
                merged[side] = first

        for item in items:
            for name, start in item.get("extra", ()) or ():
                start = float(start)
                if any(
                    str(name) == existing_name
                    and abs(start - existing_start) <= QUANTIZE_TOLERANCE_SEC
                    for existing_name, existing_start in merged["extra"]
                ):
                    continue
                merged["extra"].append((str(name), start))
        return merged, conflicts

    @staticmethod
    def _kandidaten_cues(rec, seite: str) -> list:
        """Memory-Cues "HPG K<n> OUT|IN <schema>": n je Seite fortlaufend 1..k in
        Rang-Reihenfolge nach Dedupe gleicher Zeitpunkte (Rang 1 -> K1), hoechstens
        sechs (Spec K1..K6). PairCandidate.rang ist bewusst NICHT der Name."""
        cues: list = []
        gesehen: list[float] = []
        for k in getattr(rec, "kandidaten", []) or []:
            t = float(k["t_out"] if seite == "OUT" else k["t_in"])
            if any(abs(t - g) <= QUANTIZE_TOLERANCE_SEC for g in gesehen):
                continue
            gesehen.append(t)
            cand = k.get("out_a" if seite == "OUT" else "in_b", {}) or {}
            schema = (cand.get("schema") or [""])[0]
            cues.append((f"HPG K{len(gesehen)} {seite} {schema}".rstrip(), t))
            if len(gesehen) >= 6:
                break
        return cues

    @staticmethod
    def _kandidaten_cues_out(rec) -> list:
        return RekordboxXMLExporter._kandidaten_cues(rec, "OUT")

    @staticmethod
    def _kandidaten_cues_in(rec) -> list:
        return RekordboxXMLExporter._kandidaten_cues(rec, "IN")

    def _add_beat_grid(self, rb_track: dict, track: Track) -> tuple[int, list[str]]:
        """
        Schreibt ein TEMPO-Element (Beatgrid-Anker) fuer den Track.

        Downbeat-Feature 2026-07-17: Anker ist der erkannte erste Downbeat
        (Track.first_downbeat). Ein unsicherer Anker wird nicht als Beatgrid
        exportiert.

        AUDIT-FIX D-03 (2026-08-14): Hier ist WIRKLICH nur das
        Referenz-Beatgrid gemeint, deshalb steht die Bedingung jetzt explizit
        als `== REFERENCE_BEATGRID_CONFIDENCE` statt als Zahlenschwelle. Ein
        TEMPO-Element traegt `Battito=1`, behauptet also die TAKT-Phase — und
        genau die liefert die Eigenschaetzung nicht verlaesslich (gemessen an
        35 ANLZ-Referenzen: 9 von 19 Schaetzungen um ganze Beats daneben).
        Ein falsches Beatgrid landet in der Rekordbox-Bibliothek des Nutzers
        und ist dort schlimmer als gar keines.
        """
        if not track.bpm or track.bpm <= 0:
            return 0, [f"{track.filePath}: Beatgrid fehlt wegen ungueltiger BPM"]
        try:
            first_downbeat = float(getattr(track, "first_downbeat", 0.0) or 0.0)
            if (
                hasattr(rb_track, "add_tempo")
                and getattr(track, "beatgrid_source", "unknown") == "rekordbox"
                and getattr(track, "beatgrid_status", "unknown") == "verified"
                and getattr(track, "downbeat_confidence", 0.0)
                == REFERENCE_BEATGRID_CONFIDENCE
                and math.isfinite(first_downbeat)
                and 0.0 <= first_downbeat < float(track.duration)
            ):
                rb_track.add_tempo(
                    Inizio=first_downbeat,
                    Bpm=float(track.bpm),
                    Metro="4/4",
                    Battito=1,
                )
                return 1, []
            if hasattr(rb_track, "add_tempo"):
                return 0, [f"{track.filePath}: Beatgrid ausgelassen (kein verlaesslicher Downbeat)"]
            return 0, [f"{track.filePath}: Export-Backend unterstuetzt kein Beatgrid"]
        except Exception as e:
            logger.warning(f"Beat Grid konnte nicht zur XML hinzugefuegt werden: {e}")
            return 0, [f"{track.filePath}: Beatgridfehler: {e}"]

    def _add_cue_points(
        self, xml: "RekordboxXml", rb_track: dict, track: Track,
        mix_in: Optional[float] = None, mix_out: Optional[float] = None, extra=(),
        suppress_mix_in: bool = False, suppress_mix_out: bool = False,
    ) -> tuple[int, list[str]]:
        """
        Add Cue Points to track (POSITION_MARKs).

        Mix In/Out werden doppelt geschrieben: als Hot Cue A/B (Num=0/1, direkt
        anspringbar) UND als Memory Cue (Num=-1, sichtbar in der Waveform).
        Erkannte Drop-/Breakdown-Sektionen werden als Memory Cues exportiert.
        mix_in/mix_out (aktiver TransitionPlan des Paars) ersetzen die
        Track-Werte; `extra` = weitere Memory-Cues (name, start) — "HPG K<n>".
        """
        eff_in = None if suppress_mix_in else (
            float(mix_in) if mix_in is not None
            else float(getattr(track, "mix_in_point", -1.0))
        )
        eff_out = None if suppress_mix_out else (
            float(mix_out) if mix_out is not None
            else float(getattr(track, "mix_out_point", -1.0))
        )
        if not self._cue_export_allowed(
            track, eff_in, eff_out,
            allow_partial=suppress_mix_in or suppress_mix_out,
        ):
            return 0, [
                f"{track.filePath}: Cues ausgelassen (Coverage/Schema/Provenienz unzureichend)"
            ]
        marks = getattr(rb_track, "marks", None)
        initial_mark_count = len(marks) if isinstance(marks, list) else None
        count = 0
        try:
            # pyrekordbox-API: Hot Cue = Num>=0, Memory Cue = Num=-1
            if eff_in is not None and eff_in >= 0:
                rb_track.add_mark(Name="MIX IN", Type="cue", Start=eff_in, Num=0)
                rb_track.add_mark(Name="MIX IN", Type="cue", Start=eff_in, Num=-1)
                count += 2

            if eff_out is not None and eff_out >= 0:
                rb_track.add_mark(Name="MIX OUT", Type="cue", Start=eff_out, Num=1)
                rb_track.add_mark(Name="MIX OUT", Type="cue", Start=eff_out, Num=-1)
                count += 2

            # Kandidaten-Cues (Spec Abschnitt 4): alle Kandidaten als Memory-Cues
            for name, start in extra or ():
                rb_track.add_mark(Name=str(name), Type="cue", Start=float(start), Num=-1)
                count += 1

            # Sektions-Cues: erkannte Drops/Breakdowns als Memory Cues
            for section in (track.sections or []):
                label = str(section.get("label", "")).lower()
                start = section.get("start_time")
                if label in ("drop", "breakdown") and start and start > 0:
                    rb_track.add_mark(
                        Name=label.upper(), Type="cue", Start=float(start), Num=-1
                    )
                    count += 1
            return count, []
        except Exception as e:
            try:
                self._rollback_cue_points(rb_track, initial_mark_count)
            except Exception as rollback_error:
                raise RuntimeError(
                    "Cue-Schreiben fehlgeschlagen und Cue-Rollback scheiterte: "
                    f"{rollback_error}"
                ) from rollback_error
            logger.warning(f"Cue Points konnten nicht zur XML hinzugefuegt werden: {e}")
            return 0, [f"{track.filePath}: Cuefehler: {e}"]

    @staticmethod
    def _rollback_cue_points(rb_track, initial_mark_count: Optional[int]) -> None:
        """Entfernt alle Marks eines fehlgeschlagenen Cue-Schreibversuchs."""
        marks = getattr(rb_track, "marks", None)
        if initial_mark_count is None or not isinstance(marks, list):
            raise RuntimeError("Export-Backend stellt keine Cue-Liste bereit")
        new_marks = list(marks[initial_mark_count:])
        remove_mark = getattr(type(rb_track), "remove_mark", None)
        if callable(remove_mark):
            for mark in reversed(new_marks):
                remove_mark(rb_track, mark)
            del marks[initial_mark_count:]
            return

        parent = getattr(rb_track, "_element", None)
        if parent is None or not hasattr(parent, "remove"):
            if new_marks:
                raise RuntimeError("Export-Backend kann Cues nicht entfernen")
            return
        for mark in reversed(new_marks):
            element = getattr(mark, "_element", None)
            if element is None:
                raise RuntimeError("Cue-Element fehlt beim Rollback")
            parent.remove(element)
        del marks[initial_mark_count:]

    @staticmethod
    def _cue_export_allowed(track: Track, mix_in: Optional[float] = None,
                            mix_out: Optional[float] = None,
                            *, allow_partial: bool = False) -> bool:
        """Cues brauchen echte End-Coverage und gueltige endliche Grenzen —
        geprueft auf den effektiven Punkten (Kandidat oder Track)."""
        import math

        if not getattr(track, "outro_covered", False) or track.duration <= 0:
            return False
        if allow_partial:
            values = [
                float(value) for value in (mix_in, mix_out) if value is not None
            ]
            if any(
                not math.isfinite(value)
                or not 0.0 <= value <= float(track.duration)
                for value in values
            ):
                return False
            if mix_in is not None and mix_out is not None:
                if not float(mix_in) < float(mix_out):
                    return False
        else:
            mix_in = float(
                mix_in if mix_in is not None
                else getattr(track, "mix_in_point", -1.0)
            )
            mix_out = float(
                mix_out if mix_out is not None
                else getattr(track, "mix_out_point", -1.0)
            )
            if not (math.isfinite(mix_in) and math.isfinite(mix_out)):
                return False
            if not 0.0 <= mix_in < mix_out <= float(track.duration):
                return False
        metadata = getattr(track, "ai_metadata", {})
        provenance = metadata.get("_provenance", {}) if isinstance(metadata, dict) else {}
        if metadata and not isinstance(provenance, dict):
            return False
        return True

    def _convert_camelot_to_rekordbox_key(self, camelot_code: str) -> Optional[str]:
        """
        Convert Camelot code to Rekordbox key notation

        Args:
            camelot_code: Camelot code (e.g., "8A", "9B")

        Returns:
            Rekordbox key notation (e.g., "Am", "G") or None if unknown
        """
        # m2: Case-Normalisierung fuer robuste Lookup
        if not camelot_code:
            return None
        return self.CAMELOT_TO_REKORDBOX.get(camelot_code.upper().strip())

    def get_format_info(self) -> dict:
        """
        Get information about the Rekordbox XML format

        Returns:
            Dictionary with format information
        """
        return {
            "format": "Rekordbox XML",
            "extension": ".xml",
            "compatible_with": ["Rekordbox 5.x", "Rekordbox 6.x", "Rekordbox 7.x"],
            "features": [
                "Track paths (URI format)",
                "Artist, Title, Genre metadata",
                "BPM & Beat Grid (TEMPO)",
                "Key (Musical Key)",
                "Hot Cues A/B + Memory Cues (Mix In/Out)",
                "Sektions-Cues (Drop/Breakdown)",
                "Playlist hierarchy",
                "Duration",
            ],
            "metadata_mapping": {
                "bpm": "AverageBpm",
                "key": "Tonality (Camelot → Key)",
                "mix_in_point": "POSITION_MARK (MIX IN)",
                "mix_out_point": "POSITION_MARK (MIX OUT)",
                "file_path": "Location (URI)",
                "artist": "Artist",
                "title": "Name",
                "genre": "Genre",
                "duration": "TotalTime",
            },
            "dependencies": ["pyrekordbox>=0.3.0"],
        }

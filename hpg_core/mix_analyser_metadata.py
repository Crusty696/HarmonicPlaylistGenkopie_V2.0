"""Read optional DJ Mix Analyser metadata for an unchanged local audio file."""
import logging
import math
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

logger = logging.getLogger(__name__)


def read_collection_metadata(file_path):
    source = Path(os.environ.get("HPG_MIX_ANALYSER_DB") or (
        Path.home() / "Documents" / "DJ-Mix-Analyser-Mix-2-Tracklist" / "collections.db"
    ))
    if not source.is_file():
        return {}
    try:
        audio = Path(file_path).resolve()
        stat = audio.stat()
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            row = db.execute("""
                SELECT t.artist, t.title, t.bpm, t.key FROM tracks t
                JOIN audio_locations l ON l.path=t.file_path
                WHERE t.file_path=? AND l.size=? AND l.mtime_ns=?
            """, (str(audio), stat.st_size, stat.st_mtime_ns)).fetchone()
    except (OSError, sqlite3.Error, ValueError) as exc:
        logger.debug("DJ Mix Analyser metadata unavailable: %s", exc)
        return {}
    if row is None:
        return {}
    artist, title, bpm, key = row
    return dict(artist=artist, title=title, key=key,
                bpm=bpm if isinstance(bpm, (float, int)) and math.isfinite(bpm) and 20 < bpm < 300 else None)

def collection_key(value):
    """Normalize musical key notation while leaving unknown input unresolved."""
    match = re.fullmatch(r"([A-G])([#b]?)(maj|min)", str(value).strip())
    if not match:
        return None
    note, accidental, mode = match.groups()
    note += accidental
    note = {"Db":"C#", "Eb":"D#", "Gb":"F#", "Ab":"G#", "Bb":"A#"}.get(note, note)
    return note, {"min":"Minor", "maj":"Major"}[mode]

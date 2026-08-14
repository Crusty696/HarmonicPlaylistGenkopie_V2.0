import math
import logging
from typing import List
from .models import Track
from .config import SECURITY_MAX_FILE_SIZE, SECURITY_MAX_TRACK_DURATION, SECURITY_MAX_PLAYLIST_SIZE

logger = logging.getLogger(__name__)

def validate_playlist_security(tracks: List[Track]) -> bool:
    """
    Validates playlist security constraints to prevent resource exhaustion attacks.
    
    Args:
        tracks: List of Track objects to validate
        
    Returns:
        bool: True if playlist passes all security checks, False otherwise
    """
    # Check maximum playlist size
    if len(tracks) > SECURITY_MAX_PLAYLIST_SIZE:
        logger.error(f"Playlist too large: {len(tracks)} tracks exceeds limit of {SECURITY_MAX_PLAYLIST_SIZE}")
        return False
        
    # Validate individual tracks
    for i, track in enumerate(tracks):
        # Check for missing essential fields
        if not hasattr(track, 'filePath') or not track.filePath:
            logger.warning(f"Track at index {i} has no filePath")
            continue
            
        # Validate file size (if available)
        try:
            import os
            file_size = os.path.getsize(track.filePath)
            if file_size > SECURITY_MAX_FILE_SIZE:
                logger.warning(f"Track {track.filePath} exceeds max file size: {file_size} bytes")
                return False
        except OSError as e:
            logger.debug(f"Could not check file size for track {track.filePath}: {e}")
            
        # Validate track duration if available
        # AUDIT-FIX 2026-08-14: `if track.duration:` liess negative Werte und
        # NaN durch — NaN scheitert an JEDEM Vergleich, ist also weder ">" noch
        # "<=" dem Limit, und -5.0 ist schlicht truthy. Gemessene Folge einer
        # negativen Dauer: calculate_genre_aware_mix_points liefert
        # mix_in=0.0 / mix_out=-5.0 und verletzt damit die eigene Invariante
        # 0 <= mix_in < mix_out <= duration.
        if hasattr(track, 'duration') and track.duration is not None:
            if not math.isfinite(track.duration) or track.duration <= 0:
                logger.warning(
                    f"Track {track.filePath} hat ungueltige Dauer: {track.duration!r}"
                )
                return False
            if track.duration > SECURITY_MAX_TRACK_DURATION:
                logger.warning(f"Track {track.filePath} exceeds max duration: {track.duration}s")
                return False
                
    return True

def sanitize_playlist(tracks: List[Track]) -> List[Track]:
    """
    Sanitizes playlist by removing invalid tracks and applying safety measures.
    
    Args:
        tracks: List of Track objects to sanitize
        
    Returns:
        List[Track]: Sanitized list of tracks
    """
    if not tracks:
        return []
        
    # Filter out None entries, tracks with missing essential data,
    # and tracks that violate security limits (file size / duration)
    sanitized_tracks = []
    for track in tracks:
        if track is None:
            continue

        if not validate_track_security(track):
            logger.debug(f"Skipping track failing security checks: {getattr(track, 'filePath', track)}")
            continue

        sanitized_tracks.append(track)
        
    # Apply size limit
    if len(sanitized_tracks) > SECURITY_MAX_PLAYLIST_SIZE:
        logger.warning(f"Playlist truncated from {len(sanitized_tracks)} to {SECURITY_MAX_PLAYLIST_SIZE} tracks")
        sanitized_tracks = sanitized_tracks[:SECURITY_MAX_PLAYLIST_SIZE]
        
    return sanitized_tracks

def validate_track_security(track: Track) -> bool:
    """
    Validates individual track security constraints.
    
    Args:
        track: Track object to validate
        
    Returns:
        bool: True if track passes security checks, False otherwise
    """
    # Check for essential fields
    if not hasattr(track, 'filePath') or not track.filePath:
        logger.error("Track missing filePath")
        return False
        
    # Check file size
    try:
        import os
        file_size = os.path.getsize(track.filePath)
        if file_size > SECURITY_MAX_FILE_SIZE:
            logger.warning(f"Track {track.filePath} exceeds max file size: {file_size} bytes")
            return False
    except OSError as e:
        logger.debug(f"Could not check file size for track {track.filePath}: {e}")
        
    # Check duration if available (siehe Begruendung oben: NaN und negative
    # Werte muessen explizit raus, `if track.duration:` genuegt nicht)
    if hasattr(track, 'duration') and track.duration is not None:
        if not math.isfinite(track.duration) or track.duration <= 0:
            logger.warning(
                f"Track {track.filePath} hat ungueltige Dauer: {track.duration!r}"
            )
            return False
        if track.duration > SECURITY_MAX_TRACK_DURATION:
            logger.warning(f"Track {track.filePath} exceeds max duration: {track.duration}s")
            return False
            
    return True
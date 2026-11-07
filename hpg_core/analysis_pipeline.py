"""Gemeinsame Ablaufgrenzen der Rekordbox- und Audioanalyse."""
import os


def finalize_track(track, *, cache_policy, cache_key, analysis_degraded,
                   anchor_transient, attach_features, transient_failure,
                   persist, logger):
    """Markiert Herkunft, ergänzt Features und persistiert nur belastbare Kerndaten.

    Dienste werden explizit übergeben. Dadurch bleibt dieser gemeinsame Schritt
    unabhängig von Decoder, Modellen, Cachepfad und GUI.
    """
    track.analysis_origin = "fresh"
    attach_features(track)
    if cache_policy == "reuse":
        cacheable = (
            not analysis_degraded
            and not transient_failure(track.neural_analysis)
            and track.native_phrase_analysis.get("status") != "unavailable"
            and not anchor_transient
        )
        if cacheable:
            if not persist(cache_key, track):
                return None
        else:
            logger.warning("Degradierte Kernanalyse NICHT gecacht: %s", os.path.basename(track.filePath))
    return track

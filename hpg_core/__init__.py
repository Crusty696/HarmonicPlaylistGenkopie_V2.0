"""
HPG Core - Harmonic Playlist Generator Core Module.

This package provides audio analysis, playlist generation,
and export functionality for DJ mixing.
"""

from .models import Track, CAMELOT_MAP
from .analysis import analyze_track
from .playlist import generate_playlist, calculate_playlist_quality, STRATEGIES
from .parallel_analyzer import ParallelAnalyzer

__version__ = "3.5.3"
__all__ = [
    "Track",
    "CAMELOT_MAP",
    "analyze_track",
    "generate_playlist",
    "calculate_playlist_quality",
    "STRATEGIES",
    "ParallelAnalyzer",
]

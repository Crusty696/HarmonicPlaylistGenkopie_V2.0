"""
Multi-core audio analysis engine for Harmonic Playlist Generator

Provides parallel processing capabilities using ProcessPoolExecutor for
CPU-intensive audio analysis tasks with smart multi-core scaling (up to 50% of cores).
"""

import os
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Callable, Optional
from .models import Track
from .analysis import analyze_track


def get_optimal_worker_count(file_count: Optional[int] = None) -> int:
    """
    Determines optimal number of worker processes based on CPU count and workload.

    Uses smart dynamic allocation:
    - Small CPUs (≤12 cores): Up to 6 cores
    - Large CPUs (>12 cores): Up to 50% of cores

    Args:
        file_count: Number of files to process (optional)

    Returns:
        int: Optimal number of workers (minimum 2, scales with CPU)
    """
    cpu_count = mp.cpu_count()

    # Smart scaling: use the better of the two strategies
    # - Small CPU strategy: min(6, cpu_count)
    # - Large CPU strategy: cpu_count // 2
    max_workers = max(min(6, cpu_count), cpu_count // 2)

    if file_count:
        # Only scale down for very small workloads to avoid process overhead
        if file_count < 5:
            return 1 # Force single worker to avoid spawn overhead on Windows
        elif file_count < 20:
            return 2
        elif file_count < 10:
            # For small workloads, use at least half capacity
            return max(4, max_workers // 2)
        # For 10+ files, use full capacity

    return max_workers


def _analyze_track_wrapper(file_path: str) -> Track:
    """
    Wrapper function for analyze_track() that can be pickled for multiprocessing.

    This function must be at module level for Windows multiprocessing compatibility.

    Args:
        file_path: Path to audio file

    Returns:
        Track object or None if analysis failed
    """
    try:
        return analyze_track(file_path)
    except Exception as e:
        print(f"[ERROR] Worker failed for {os.path.basename(file_path)}: {e}")
        return None


class ParallelAnalyzer:
    """
    Multi-core audio analysis engine using ProcessPoolExecutor.

    Provides:
    - Intelligent worker count selection
    - Progress callbacks for GUI integration
    - Robust error handling with graceful degradation
    - Timeout protection for corrupted files
    """

    def __init__(self, max_workers: Optional[int] = None):
        """
        Initialize parallel analyzer.

        Args:
            max_workers: Maximum number of worker processes (default: auto-detect, smart scaling)
        """
        cpu_count = mp.cpu_count()
        # Use smart allocation if max_workers not explicitly provided
        default_workers = max(min(6, cpu_count), cpu_count // 2)
        self.max_workers = min(max_workers or default_workers, cpu_count)
        print(f"[PARALLEL] Initialized with {self.max_workers} workers (CPU count: {cpu_count})")

    def analyze_files(
        self,
        file_paths: List[str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> List[Track]:
        """
        Analyze multiple audio files in parallel.

        Args:
            file_paths: List of file paths to analyze
            progress_callback: Optional callback(current, total, status_message)

        Returns:
            List of Track objects (None entries for failed analyses)
        """
        if not file_paths:
            return []

        total_files = len(file_paths)
        analyzed_tracks = [None] * total_files  # Pre-allocate result list
        completed_count = 0

        # Determine optimal worker count for this batch
        worker_count = get_optimal_worker_count(total_files)

        if progress_callback:
            progress_callback(0, total_files, f"Starting analysis with {worker_count} cores...")

        print(f"\n[PARALLEL] Processing {total_files} files with {worker_count} workers...")

        # Use ProcessPoolExecutor for true parallel processing (bypasses GIL)
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            # Submit all tasks
            future_to_index = {
                executor.submit(_analyze_track_wrapper, path): idx
                for idx, path in enumerate(file_paths)
            }

            # Collect results as they complete
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                file_path = file_paths[idx]

                try:
                    # Timeout after 60 seconds per track (protects against corrupted files)
                    track = future.result(timeout=60)
                    analyzed_tracks[idx] = track

                    if track:
                        completed_count += 1
                        status_msg = f"Analyzed: {os.path.basename(file_path)}"
                    else:
                        status_msg = f"[FAILED] {os.path.basename(file_path)}"

                except TimeoutError:
                    print(f"[TIMEOUT] Analysis timed out for {os.path.basename(file_path)}")
                    status_msg = f"[TIMEOUT] {os.path.basename(file_path)}"

                except Exception as e:
                    print(f"[ERROR] Worker crashed for {os.path.basename(file_path)}: {e}")
                    status_msg = f"[ERROR] {os.path.basename(file_path)}"

                # Report progress
                if progress_callback:
                    progress_callback(idx + 1, total_files, status_msg)

        # Filter out None values (failed analyses)
        successful_tracks = [track for track in analyzed_tracks if track is not None]

        print(f"\n[PARALLEL] Analysis complete: {len(successful_tracks)}/{total_files} successful")

        return successful_tracks

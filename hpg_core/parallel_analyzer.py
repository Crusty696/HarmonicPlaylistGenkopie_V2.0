"""
Multi-core audio analysis engine for Harmonic Playlist Generator

Provides parallel processing capabilities using ProcessPoolExecutor for
CPU-intensive audio analysis tasks with smart multi-core scaling (up to 50% of cores).
"""

import logging
import os
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Callable, Optional
from .models import Track
from .analysis import analyze_track
from . import config

logger = logging.getLogger(__name__)


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
    # M3 Audit-Fix: Konfigurierbar ueber config.py (config.PARALLEL_MAX_WORKERS)
    if config.PARALLEL_MAX_WORKERS is not None:
        return max(1, config.PARALLEL_MAX_WORKERS)

    cpu_count = mp.cpu_count()

    # Smart scaling: use the better of the two strategies
    # - Small CPU strategy: min(6, cpu_count)
    # - Large CPU strategy: cpu_count // 2
    max_workers = max(min(6, cpu_count), cpu_count // 2)

    if file_count:
        # Scale workers based on workload to avoid process overhead
        if file_count < 5:
            return 1  # Force single worker to avoid spawn overhead on Windows
        elif file_count < 10:
            return 2  # Small workload: minimal parallelism
        elif file_count < 20:
            return max(4, max_workers // 2)  # Medium workload: half capacity
        # For 20+ files, use full capacity

    return max_workers


def _analyze_track_wrapper(file_path: str) -> Track | None:
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
        logger.error(f"Worker fehlgeschlagen fuer {os.path.basename(file_path)}: {e}")
        return None


class ParallelAnalyzer:
    """
    Multi-core audio analysis engine using ProcessPoolExecutor.

    Provides:
    - Intelligent worker count selection
    - Progress callbacks for GUI integration
    - Robust error handling with graceful degradation
    - Timeout protection for corrupted files
    - Memory optimization for large playlists
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
        logger.info(f"Initialisiert mit {self.max_workers} Workers (CPU: {cpu_count} Kerne)")

    def analyze_files(
        self,
        file_paths: List[str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> List[Track]:
        """
        Analyze multiple audio files in parallel, with robust recovery from C-level worker crashes.

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
        finished_count = 0
        completed_count = 0

        worker_count = get_optimal_worker_count(total_files)
        # Batch mindestens 2 Tasks pro Worker, sonst laufen Prozesse leer
        # (Pool-Start ist teuer: Spawn + librosa-Import pro Prozess);
        # Obergrenze 48 begrenzt Memory-Bloat bei grossen Playlists
        BATCH_SIZE = min(48, max(worker_count * 2, total_files // 4))

        if progress_callback:
            progress_callback(0, total_files, f"Starting analysis with {worker_count} cores...")

        logger.info(f"Verarbeite {total_files} Dateien mit {worker_count} Workers in Batches von {BATCH_SIZE}...")

        from concurrent.futures.process import BrokenProcessPool

        # Process in batches
        for batch_start in range(0, total_files, BATCH_SIZE):
            batch_paths = file_paths[batch_start : batch_start + BATCH_SIZE]
            batch_indices = list(range(batch_start, min(batch_start + BATCH_SIZE, total_files)))

            logger.info(f"Starte Batch {batch_start // BATCH_SIZE + 1} ({len(batch_paths)} Dateien)...")

            pool_broken = False
            batch_results = {}  # index -> Track or None

            try:
                # Use ProcessPoolExecutor for true parallel processing (bypasses GIL)
                with ProcessPoolExecutor(max_workers=worker_count) as executor:
                    # Submit all tasks in this batch
                    future_to_idx = {
                        executor.submit(_analyze_track_wrapper, path): idx
                        for path, idx in zip(batch_paths, batch_indices)
                    }

                    # M10-Fix: Gesamtdeadline fuer den Batch — ein im C-Level
                    # haengender Worker wird sonst nie von as_completed geyieldet
                    # und der per-Future-Timeout greift nie
                    batch_timeout = (
                        config.PARALLEL_ANALYSIS_TIMEOUT
                        * max(1, -(-len(batch_paths) // worker_count))
                        + 30
                    )
                    try:
                        for future in as_completed(future_to_idx, timeout=batch_timeout):
                            idx = future_to_idx[future]
                            file_path = file_paths[idx]
                            status_msg = ""

                            try:
                                # W5: Konfigurierbarer Timeout (schuetzt gegen korrupte Dateien)
                                track = future.result(timeout=config.PARALLEL_ANALYSIS_TIMEOUT)
                                batch_results[idx] = track
                                finished_count += 1
                                if track:
                                    completed_count += 1
                                    status_msg = f"Analyzed: {os.path.basename(file_path)}"
                                else:
                                    status_msg = f"[FAILED] {os.path.basename(file_path)}"
                            except TimeoutError:
                                logger.warning(f"Timeout bei Analyse von {os.path.basename(file_path)}")
                                status_msg = f"[TIMEOUT] {os.path.basename(file_path)}"
                                batch_results[idx] = None
                                finished_count += 1
                            except (BrokenProcessPool, RuntimeError) as e:
                                # Process pool crashed abruptly!
                                logger.error(f"Worker-Crash (Pool beschaedigt) bei {os.path.basename(file_path)}: {e}")
                                pool_broken = True
                                # Break out to trigger recovery for unprocessed files in this batch
                                break
                            except Exception as e:
                                logger.error(f"Fehler bei {os.path.basename(file_path)}: {e}")
                                status_msg = f"[ERROR] {os.path.basename(file_path)}"
                                batch_results[idx] = None
                                finished_count += 1

                            if not pool_broken and progress_callback and status_msg:
                                # H7-Fix: Cancel (InterruptedError) aus dem Callback darf
                                # nicht als Pool-Crash interpretiert werden
                                try:
                                    progress_callback(finished_count, total_files, status_msg)
                                except InterruptedError:
                                    executor.shutdown(wait=False, cancel_futures=True)
                                    raise
                    except TimeoutError:
                        # M10-Fix: Batch-Deadline gerissen (haengender C-Level-Worker,
                        # den as_completed nie yielded). Restliche Futures verwerfen und
                        # Worker-Prozesse hart beenden — sonst blockiert der
                        # Executor-Shutdown beim Verlassen des with-Blocks endlos.
                        logger.error(
                            "Batch-Timeout: haengender Worker erkannt — verbleibende Dateien uebersprungen"
                        )
                        for fut, idx in future_to_idx.items():
                            if idx not in batch_results:
                                fut.cancel()
                                batch_results[idx] = None
                                finished_count += 1
                        for proc in getattr(executor, "_processes", {}).values():
                            proc.terminate()

                    if pool_broken:
                        # Abort execution of pending tasks in this broken pool
                        executor.shutdown(wait=False)

            except InterruptedError:
                # H7-Fix: sauberer User-Abbruch — nach oben durchreichen,
                # KEINE Safe-Mode-Reanalyse ausloesen
                logger.info("Analyse durch Benutzer abgebrochen")
                raise
            except Exception as pool_err:
                logger.error(f"Genereller Pool-Fehler in Batch: {pool_err}")
                pool_broken = True

            # Recovery mode for unprocessed files in this batch if the pool crashed
            if pool_broken:
                unprocessed_indices = [idx for idx in batch_indices if idx not in batch_results]
                logger.warning(f"Prozess-Pool abgestuerzt. Starte sicheren Recovery-Modus fuer {len(unprocessed_indices)} Dateien...")

                for idx in unprocessed_indices:
                    file_path = file_paths[idx]
                    logger.info(f"Analysiere im Safe-Modus: {os.path.basename(file_path)}")
                    
                    track = None
                    status_msg = ""
                    try:
                        # Process individual file in a fresh single-worker pool
                        with ProcessPoolExecutor(max_workers=1) as recovery_executor:
                            future = recovery_executor.submit(_analyze_track_wrapper, file_path)
                            track = future.result(timeout=config.PARALLEL_ANALYSIS_TIMEOUT)
                            if track:
                                completed_count += 1
                                status_msg = f"Analyzed (Safe Mode): {os.path.basename(file_path)}"
                            else:
                                status_msg = f"[FAILED] {os.path.basename(file_path)}"
                    except (BrokenProcessPool, RuntimeError) as e:
                        # This specific file caused the worker to crash!
                        logger.error(f"CRITICAL: Datei verursacht C-Level Absturz! Ueberspringe: {os.path.basename(file_path)}: {e}")
                        status_msg = f"[CRASHED/SKIPPED] {os.path.basename(file_path)}"
                        track = None
                    except TimeoutError:
                        logger.warning(f"Timeout im Safe-Modus bei {os.path.basename(file_path)}")
                        status_msg = f"[TIMEOUT] {os.path.basename(file_path)}"
                        track = None
                    except Exception as e:
                        logger.error(f"Fehler im Safe-Modus bei {os.path.basename(file_path)}: {e}")
                        status_msg = f"[ERROR] {os.path.basename(file_path)}"
                        track = None

                    batch_results[idx] = track
                    finished_count += 1
                    if progress_callback and status_msg:
                        progress_callback(finished_count, total_files, status_msg)

            # Apply batch results to master list
            for idx, track in batch_results.items():
                analyzed_tracks[idx] = track

        # Filter out None values (failed analyses)
        successful_tracks = [track for track in analyzed_tracks if track is not None]

        logger.info(f"Analyse fertig: {len(successful_tracks)}/{total_files} erfolgreich")

        return successful_tracks

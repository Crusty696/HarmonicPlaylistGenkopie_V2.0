"""
Multi-core audio analysis engine for Harmonic Playlist Generator

Provides parallel processing capabilities using ProcessPoolExecutor for
CPU-intensive audio analysis tasks with smart multi-core scaling (up to 50% of cores).
"""

import logging
import os
import multiprocessing as mp
import time
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from typing import List, Callable, Optional
from .models import Track
from .analysis import analyze_track
from .caching import VALID_ANALYSIS_MODES
from . import config

logger = logging.getLogger(__name__)


def _terminate_executor_processes(executor: ProcessPoolExecutor) -> None:
    """Best-effort-Cleanup, das niemals die urspruengliche Exception maskiert."""
    def log_cleanup_error(message: str, error: BaseException) -> None:
        try:
            logger.warning(message, error)
        except BaseException:
            pass

    try:
        processes = tuple((getattr(executor, "_processes", None) or {}).values())
    except BaseException as error:
        log_cleanup_error("Child-Prozessliste nicht lesbar: %s", error)
        processes = ()

    for process in processes:
        should_terminate = True
        try:
            should_terminate = process.is_alive()
        except BaseException as error:
            log_cleanup_error("Child-Status nicht lesbar; Terminate wird versucht: %s", error)
        if should_terminate:
            try:
                process.terminate()
            except BaseException as error:
                log_cleanup_error("Child-Prozess konnte nicht terminiert werden: %s", error)

    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except BaseException as error:
        log_cleanup_error("Executor-Cleanup ohne Wait fehlgeschlagen: %s", error)


def _is_successful_analysis_result(track: Track | None) -> bool:
    """Akzeptiert nur belastbare Track-Ergebnisse, keine Decode-Platzhalter."""
    return (
        track is not None
        and getattr(track, "analysis_mode", None) in VALID_ANALYSIS_MODES
    )


def get_optimal_worker_count(file_count: Optional[int] = None) -> int:
    """
    Determines optimal number of worker processes based on CPU count and workload.

    Uses smart dynamic allocation:
    - Small CPUs (≤12 cores): Up to 6 cores
    - Large CPUs (>12 cores): Up to 50% of cores, capped at four stable
      audio-decoder workers for Windows native-library safety

    Args:
        file_count: Number of files to process (optional)

    Returns:
        int: Optimal number of workers (minimum 2, scales with CPU)
    """
    cpu_count = mp.cpu_count()

    # M3 Audit-Fix: Konfigurierbar ueber config.py (config.PARALLEL_MAX_WORKERS)
    if config.PARALLEL_MAX_WORKERS is not None:
        return min(cpu_count, max(1, int(config.PARALLEL_MAX_WORKERS)))

    # Smart scaling: use the better of the two strategies
    # - Small CPU strategy: min(6, cpu_count)
    # - Large CPU strategy: cpu_count // 2
    max_workers = min(
        max(min(6, cpu_count), cpu_count // 2),
        config.PARALLEL_AUTO_MAX_WORKERS,
    )

    if file_count:
        # Scale workers based on workload to avoid process overhead
        if file_count < 5:
            return 1  # Force single worker to avoid spawn overhead on Windows
        elif file_count < 10:
            return 2  # Small workload: minimal parallelism
        elif file_count < 20:
            # Medium workload: half capacity — gegen cpu_count klemmen, sonst
            # liefert max(4, ...) auf 2-Kern-Maschinen 4 Worker (Oversubscription).
            return min(cpu_count, max(4, max_workers // 2))
        # For 20+ files, use full capacity

    return max_workers


def _worker_init() -> None:
    """AUDIT-FIX P-01 (2026-07-24): Prozess-Initializer — waermt die
    Rekordbox-Importer-Singleton (kompletter master.db-Scan) EINMAL pro
    Worker-Prozess statt bei jedem ersten analyze_track-Aufruf. Zusammen mit
    groesseren Batches (weniger Pool-Neustarts) spart das bei grossen
    Rekordbox-Libraries einen Grossteil der Anlaufzeit."""
    try:
        from .rekordbox_importer import get_rekordbox_importer
        get_rekordbox_importer()
    except Exception:
        # Rekordbox optional — Fehler hier darf den Worker nicht kippen
        pass


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
        default_workers = get_optimal_worker_count()
        self._explicit_max_workers = max_workers is not None
        self.max_workers = min(max_workers or default_workers, cpu_count)
        logger.info(f"Initialisiert mit {self.max_workers} Workers (CPU: {cpu_count} Kerne)")

    def analyze_files(
        self,
        file_paths: List[str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
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

        worker_count = (
            min(self.max_workers, total_files)
            if self._explicit_max_workers
            else get_optimal_worker_count(total_files)
        )
        # Batch mindestens 2 Tasks pro Worker, sonst laufen Prozesse leer
        # (Pool-Start ist teuer: Spawn + librosa-Import + Rekordbox-DB-Scan pro
        # Prozess). AUDIT-FIX P-01 (2026-07-24): Obergrenze 48 -> 200 angehoben.
        # Bei 1000 Tracks fielen vorher ~21 Pool-Neustarts an (je Neustart:
        # librosa-Import + kompletter master.db-Scan in JEDEM Worker); jetzt
        # ~5 Pools. Track-Objekte halten kein Audio -> Memory unkritisch.
        BATCH_SIZE = min(200, max(worker_count * 2, total_files // 4))

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
                # AUDIT-FIX P-01: initializer waermt die Rekordbox-Singleton
                # einmal pro Worker-Prozess statt bei jedem ersten Task.
                executor = ProcessPoolExecutor(
                    max_workers=worker_count, initializer=_worker_init
                )
                executor_stopped = False

                def terminate_executor() -> None:
                    nonlocal executor_stopped
                    if not executor_stopped:
                        _terminate_executor_processes(executor)
                        executor_stopped = True

                try:
                    # M10-Fix + AUDIT-FIX N-04 (2026-07-26): Haenger-Deadline
                    # haengt jetzt an worker_count statt an der Batch-Groesse.
                    # Vorher wuchs die Gesamt-Deadline proportional zur
                    # Batch-Groesse (bei 200er-Batches bis ~2,8 h, bevor ein
                    # haengender Worker erkannt wurde). Jetzt ist sie eine
                    # INAKTIVITAETS-Deadline pro Wartezyklus: solange
                    # ueberhaupt Futures fertig werden, darf der Batch
                    # beliebig lange laufen — erst wenn laenger als
                    # hang_timeout KEIN einziges Future fertig wird, gelten
                    # die Worker als haengend. Zusaetzlich gedeckelt auf
                    # config.PARALLEL_HANG_DEADLINE_MAX (~15 min).
                    hang_timeout = min(
                        config.PARALLEL_HANG_DEADLINE_MAX,
                        config.PARALLEL_ANALYSIS_TIMEOUT * worker_count + 30,
                    )
                    try:
                        # Hoechstens ein Task pro Worker bleibt gleichzeitig
                        # aktiv. Dadurch ist der per-Task-Timeout wirklich
                        # messbar; ein voller Batch mit bereits eingereihten
                        # Futures konnte zuvor nur ueber die globale
                        # Haenger-Deadline erkannt werden.
                        future_to_idx = {}
                        submitted_at = {}
                        pending_futures = set()
                        next_batch_offset = 0

                        def submit_available() -> None:
                            nonlocal next_batch_offset
                            while (
                                next_batch_offset < len(batch_paths)
                                and len(pending_futures) < worker_count
                            ):
                                idx = batch_indices[next_batch_offset]
                                future = executor.submit(
                                    _analyze_track_wrapper, batch_paths[next_batch_offset]
                                )
                                future_to_idx[future] = idx
                                submitted_at[future] = time.monotonic()
                                pending_futures.add(future)
                                next_batch_offset += 1

                        submit_available()
                        no_progress_since = time.monotonic()
                        while pending_futures and not pool_broken:
                            now = time.monotonic()
                            overdue_futures = {
                                future
                                for future in pending_futures
                                if now - submitted_at[future]
                                >= config.PARALLEL_ANALYSIS_TIMEOUT
                            }
                            if overdue_futures:
                                logger.warning(
                                    "Per-Task-Timeout bei %d Analyse(n) — Pool wird beendet",
                                    len(overdue_futures),
                                )
                                for future in overdue_futures:
                                    idx = future_to_idx[future]
                                    batch_results[idx] = None
                                    finished_count += 1
                                    if progress_callback:
                                        progress_callback(
                                            finished_count,
                                            total_files,
                                            f"[TIMEOUT] {os.path.basename(file_paths[idx])}",
                                        )
                                pool_broken = True
                                terminate_executor()
                                break

                            done_futures, _ = wait(
                                pending_futures,
                                timeout=min(0.5, hang_timeout),
                                return_when=FIRST_COMPLETED,
                            )
                            if cancel_callback and cancel_callback():
                                terminate_executor()
                                raise InterruptedError("Analysis cancelled by user")
                            if not done_futures:
                                # Kurze Polling-Intervalle halten den Cancel
                                # responsiv; die grosse Deadline bleibt die
                                # eigentliche Haenger-Erkennung.
                                if time.monotonic() - no_progress_since >= hang_timeout:
                                    raise TimeoutError()
                                continue

                            no_progress_since = time.monotonic()
                            pending_futures.difference_update(done_futures)

                            for future in done_futures:
                                idx = future_to_idx[future]
                                file_path = file_paths[idx]
                                status_msg = ""

                                try:
                                    # W5: Konfigurierbarer Timeout (schuetzt gegen korrupte Dateien)
                                    track = future.result(timeout=config.PARALLEL_ANALYSIS_TIMEOUT)
                                    batch_results[idx] = track
                                    finished_count += 1
                                    if _is_successful_analysis_result(track):
                                        completed_count += 1
                                        status_msg = f"Analyzed: {os.path.basename(file_path)}"
                                    else:
                                        track = None
                                        batch_results[idx] = None
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
                                        terminate_executor()
                                        raise
                            if not pool_broken:
                                submit_available()
                    except TimeoutError:
                        # M10-Fix: Haenger-Deadline gerissen (haengender C-Level-Worker,
                        # den wait() nie als fertig meldet). Restliche Futures verwerfen und
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
                        terminate_executor()

                    if pool_broken:
                        # Abort execution of pending tasks in this broken pool
                        terminate_executor()

                except BaseException:
                    # KeyboardInterrupt/SystemExit duerfen nie zuerst durch
                    # ProcessPoolExecutor.__exit__ -> shutdown(wait=True) laufen.
                    terminate_executor()
                    raise
                else:
                    if not executor_stopped:
                        try:
                            executor.shutdown(wait=True)
                        except BaseException:
                            terminate_executor()
                            raise

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

                # AUDIT-FIX PA-01 (2026-07-24): Executor MANUELL verwalten.
                # Vorher stand das `future.result(timeout=...)` in einem
                # `with ProcessPoolExecutor(...)`-Block — bei Timeout warf
                # result() INNERHALB des with, sodass __exit__ =
                # shutdown(wait=True) auf den haengenden Worker wartete und
                # unbegrenzt blockierte (GUI-Freeze). Der terminate-Aufruf
                # im except war unerreichbar. Jetzt: expliziter Executor,
                # Cleanup garantiert im finally mit wait=False.
                # AUDIT-FIX N-04 (2026-07-26): EIN Recovery-Executor fuer ALLE
                # restlichen Dateien statt ein neuer Pool PRO Datei (vorher bei
                # BrokenProcessPool spaet im 200er-Batch bis zu 199 Pool-Starts,
                # je Start: Prozess-Spawn + librosa-Import + Rekordbox-Scan).
                # Der Pool wird lazy angelegt und nur nach Crash/Timeout des
                # Recovery-Workers fuer die naechste Datei neu erzeugt.
                recovery_executor = None
                try:
                    for idx in unprocessed_indices:
                        if cancel_callback and cancel_callback():
                            if recovery_executor is not None:
                                _terminate_executor_processes(recovery_executor)
                                recovery_executor = None
                            raise InterruptedError("Analysis cancelled by user")

                        file_path = file_paths[idx]
                        logger.info(f"Analysiere im Safe-Modus: {os.path.basename(file_path)}")

                        track = None
                        status_msg = ""
                        try:
                            if recovery_executor is None:
                                recovery_executor = ProcessPoolExecutor(
                                    max_workers=1, initializer=_worker_init
                                )
                            future = recovery_executor.submit(_analyze_track_wrapper, file_path)
                            deadline = (
                                time.monotonic() + config.PARALLEL_ANALYSIS_TIMEOUT
                            )
                            while True:
                                if cancel_callback and cancel_callback():
                                    _terminate_executor_processes(recovery_executor)
                                    recovery_executor = None
                                    raise InterruptedError("Analysis cancelled by user")
                                done, _ = wait(
                                    {future}, timeout=0.5, return_when=FIRST_COMPLETED
                                )
                                if done:
                                    track = future.result()
                                    break
                                if time.monotonic() >= deadline:
                                    raise TimeoutError()
                            if _is_successful_analysis_result(track):
                                completed_count += 1
                                status_msg = f"Analyzed (Safe Mode): {os.path.basename(file_path)}"
                            else:
                                track = None
                                status_msg = f"[FAILED] {os.path.basename(file_path)}"
                        except (BrokenProcessPool, RuntimeError) as e:
                            # Ein einzelner Worker-Crash beweist keine Dateikorruption:
                            # Auch der eingefrorene Prozessstart oder eine native Bibliothek
                            # kann vor der eigentlichen Analyse abgestuerzt sein.
                            logger.error(f"CRITICAL: C-Level Worker-Absturz im Safe-Modus; Datei wird uebersprungen: {os.path.basename(file_path)}: {e}")
                            status_msg = f"[CRASHED/SKIPPED] {os.path.basename(file_path)}"
                            track = None
                            # Pool ist beschaedigt — fuer die naechste Datei neu anlegen
                            if recovery_executor is not None:
                                _terminate_executor_processes(recovery_executor)
                                recovery_executor = None
                        except TimeoutError:
                            logger.warning(f"Timeout im Safe-Modus bei {os.path.basename(file_path)}")
                            # Haengender Worker blockiert den Pool — hart beenden
                            # und fuer die naechste Datei neu anlegen
                            if recovery_executor is not None:
                                _terminate_executor_processes(recovery_executor)
                                recovery_executor = None
                            status_msg = f"[TIMEOUT] {os.path.basename(file_path)}"
                            track = None
                        except InterruptedError:
                            raise
                        except Exception as e:
                            # Normaler Fehler kam als Ergebnis zurueck — der Pool
                            # ist intakt und wird weiterverwendet
                            logger.error(f"Fehler im Safe-Modus bei {os.path.basename(file_path)}: {e}")
                            status_msg = f"[ERROR] {os.path.basename(file_path)}"
                            track = None

                        batch_results[idx] = track
                        finished_count += 1
                        if progress_callback and status_msg:
                            progress_callback(finished_count, total_files, status_msg)
                except BaseException:
                    if recovery_executor is not None:
                        _terminate_executor_processes(recovery_executor)
                        recovery_executor = None
                    raise
                finally:
                    # Cleanup garantiert — auch bei InterruptedError aus dem Callback
                    if recovery_executor is not None:
                        executor_to_shutdown = recovery_executor
                        recovery_executor = None
                        try:
                            executor_to_shutdown.shutdown(
                                wait=False, cancel_futures=True
                            )
                        except BaseException:
                            _terminate_executor_processes(executor_to_shutdown)
                            raise

            # Apply batch results to master list
            for idx, track in batch_results.items():
                analyzed_tracks[idx] = track

        # Filter out None values (failed analyses)
        successful_tracks = [
            track for track in analyzed_tracks
            if _is_successful_analysis_result(track)
        ]

        logger.info(f"Analyse fertig: {len(successful_tracks)}/{total_files} erfolgreich")

        return successful_tracks

"""Qt-Adapter fuer interne Hoertest-Services; keine CLI-Prozesse."""

from PyQt6.QtCore import QThread, pyqtSignal


def frozen_cohort_index(index):
    """Validierte, von veränderbaren Aufruferlisten gelöste Inventarkopie."""
    from .collection_index import CollectionIndex, _validated

    if type(index) is not CollectionIndex or index.cancelled or index.errors:
        raise ValueError("Vollstaendiges Inventar erforderlich")
    raw = {"kind": "hpg_collection_index", "version": 1, "roots": list(index.roots),
           "entries": [{"path": entry.path, "size": entry.size,
                        "mtime_ns": entry.mtime_ns, "status": entry.status}
                       for entry in index.entries]}
    return _validated(raw)


class HearingCohortWorker(QThread):
    """Nur die gewählte Inventarkohorte mit dem vorhandenen Analyzer verarbeiten."""

    status_update = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, index, track_count, pair_count, seed, mode, parent=None):
        super().__init__(parent)
        from threading import Event

        self.index = frozen_cohort_index(index)
        self.track_count = track_count
        self.pair_count = pair_count
        self.seed = seed
        self.mode = mode
        self.cancel = Event()

    def request_cancel(self):
        self.cancel.set()
        return True

    def run(self):
        result = {"ok": False}
        try:
            from .hearing_cohorts import CohortContext, select_cohort
            from .hearing_collection import analyze_cohort

            if self.mode not in ("einzel", "kandidaten") or type(self.pair_count) is not int or self.pair_count < 1:
                raise ValueError("Ungueltige Hoertest-Optionen")
            context = CohortContext()
            selected = select_cohort(self.index, count=self.track_count, seed=self.seed,
                                     context=context)
            if selected.shortfall or len(selected.paths) < 2:
                raise ValueError("Zu wenige verfuegbare Tracks fuer die gewuenschte Kohorte")
            self.status_update.emit(f"Kohorte: {len(selected.paths)} Tracks gewaehlt; Analyse startet.")
            analysis = analyze_cohort(
                self.index, selected, context=context, cancel=self.cancel,
                progress=lambda current, total, message: self.status_update.emit(
                    f"Kohorte: {current}/{total} – {message}"),
            )
            if self.cancel.is_set():
                raise InterruptedError("Kohortenanalyse abgebrochen")
            if not analysis.complete or len(analysis.track_snapshots) != len(selected.paths):
                raise ValueError(f"Kohortenanalyse unvollstaendig: {len(analysis.issues)} Probleme; kein Hoertest erstellt")
            result.update(ok=True, analysis=analysis, mode=self.mode,
                          pair_count=self.pair_count, seed=self.seed)
        except InterruptedError as exc:
            result.update(cancelled=True, output=str(exc))
        except Exception as exc:
            result["output"] = str(exc)
        self.completed.emit(result)


class HearingPrepareWorker(QThread):
    status_update = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, config, parent=None, *, managed_metadata=None):
        super().__init__(parent)
        from .hearing_workflow import CancellationToken

        self.config = config
        self.managed_metadata = managed_metadata
        self.cancel = CancellationToken()

    def request_cancel(self):
        return self.cancel.request_cancel()

    def run(self):
        from .hearing_workflow import create_set, HearingCancelledError

        result = {"ok": False, "set_path": str(self.config.output_dir),
                  "cache_path": str(self.config.cache), "report_path": ""}
        ownership = None
        published = False
        try:
            if self.managed_metadata is not None:
                from .hearing_managed import write_snapshot
                ownership = write_snapshot(self.config, self.managed_metadata, cancel=self.cancel)
            prepared = create_set(
                self.config,
                progress=lambda p: self.status_update.emit(f"{p.phase}: {p.completed}/{p.total} – {p.message}"),
                cancel=self.cancel,
            )
            published = True
            if self.managed_metadata is not None:
                from .hearing_managed import bind_set
                warning = bind_set(self.config, ownership=ownership)
                if warning:
                    result["cleanup_warning"] = warning
            result.update(ok=True, prepared_only=True,
                          output=f"{prepared.pair_count} Paare, {prepared.clip_count} Quellenreferenzen vorbereitet. Nicht auditiert.",
                          warnings=list(prepared.warnings))
        except (HearingCancelledError, InterruptedError) as exc:
            result.update(cancelled=True, output=str(exc))
        except Exception as exc:
            result["output"] = str(exc)
            if published:
                result.update(published_unbound=True, output=(
                    f"Satz veröffentlicht, aber Zuordnung fehlgeschlagen: {exc}. "
                    f"Daten erhalten unter {self.config.output_dir}. Nicht erneut vorbereiten."))
        finally:
            if ownership is not None and not published:
                from .hearing_managed import discard_unpublished_snapshot
                try:
                    discard_unpublished_snapshot(ownership)
                except Exception as exc:
                    result["cleanup_warning"] = f"Snapshot erhalten; Bereinigung verweigert: {exc}"
        self.completed.emit(result)


class HearingLoadWorker(QThread):
    """Quellhashes und Metadaten ausserhalb des GUI-Threads lesen."""

    status_update = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self.folder = str(folder)

    def request_cancel(self):
        self.requestInterruption()

    def run(self):
        from .hearing_ratings import load_session

        result = {"ok": False, "set_path": self.folder}
        try:
            if self.isInterruptionRequested():
                raise InterruptedError("Laden abgebrochen")
            self.status_update.emit("Prüfe Satz, Originalquellen und Bewertungen …")
            session = load_session(self.folder)
            from .hearing_managed import resolve_association
            cache = resolve_association(self.folder)
            if self.isInterruptionRequested():
                raise InterruptedError("Laden abgebrochen")
            result.update(ok=True, session=session, cache_path=str(cache) if cache else "")
        except Exception as exc:
            result["output"] = str(exc)
            result["cancelled"] = isinstance(exc, InterruptedError)
        self.completed.emit(result)


class HearingDiscoveryWorker(QThread):
    status_update = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = root

    def request_cancel(self):
        self.requestInterruption()

    def run(self):
        from pathlib import Path
        from .hearing_discovery import discover_sets
        def checkpoint():
            if self.isInterruptionRequested():
                raise InterruptedError("Satzsuche abgebrochen")
        try:
            self.status_update.emit("Lese Bewertungsfortschritt im gewählten Ordner und direkten Unterordnern …")
            result = {"ok": True, "summaries": discover_sets(Path(self.root), checkpoint)}
        except Exception as exc:
            result = {"ok": False, "output": str(exc), "cancelled": isinstance(exc, InterruptedError)}
        self.completed.emit(result)


class HearingBlindWorker(QThread):
    status_update = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        from .hearing_workflow import CancellationToken
        self.config = dict(config)
        self.cancel = CancellationToken()

    def request_cancel(self):
        return self.cancel.request_cancel()

    def run(self):
        from .hearing_blind import prepare_blind_references, OrphanBlindKeyError
        from .hearing_workflow import HearingCancelledError
        try:
            self.status_update.emit("Prüfe bestehende A/B-Quellen; publiziere nur Referenzen und privaten Schlüssel …")
            public, key = prepare_blind_references(**self.config, cancel=self.cancel)
            result = {"ok": True, "public_path": str(public), "key_path": str(key)}
        except Exception as exc:
            result = {"ok": False, "output": str(exc), "cancelled": isinstance(exc, HearingCancelledError),
                      "orphan_key": isinstance(exc, OrphanBlindKeyError)}
        self.completed.emit(result)


class HearingBlindCheckWorker(QThread):
    """Prueft bestehende Referenzen lesend; gibt keine Schluesseldaten weiter."""

    status_update = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, public_path, key_path, parent=None):
        super().__init__(parent)
        from pathlib import Path
        from .hearing_workflow import CancellationToken
        self.public_path, self.key_path = Path(public_path), Path(key_path)
        self.cancel = CancellationToken()

    def request_cancel(self):
        return self.cancel.request_cancel()

    def run(self):
        from .hearing_blind import load_blind_references
        from .hearing_workflow import HearingCancelledError
        try:
            self.cancel.checkpoint()
            self.status_update.emit("Prüfe A/B-Referenzen und ihre gespeicherte Quellenbindung …")
            public = load_blind_references(self.public_path, self.key_path, cancel=self.cancel)
            self.cancel.checkpoint()
            result = {"ok": True, "pair_count": len(public["pairs"])}
        except (HearingCancelledError, InterruptedError):
            result = {"ok": False, "cancelled": True, "output": "A/B-Integritätsprüfung abgebrochen. Keine Dateien verändert."}
        except Exception:
            # Validatorfehler koennen private Pfade enthalten: nie weiterreichen.
            result = {"ok": False, "cancelled": False,
                      "output": "A/B-Integritätsprüfung fehlgeschlagen. Referenzdatei, getrennten Schlüssel und unveränderte Quellen prüfen. Keine Dateien verändert."}
        self.completed.emit(result)


class HearingCalibrationWorker(QThread):
    """Besitzt Prozess und alle temporaeren Audit-/Fit-Ressourcen."""

    status_update = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, directory, cache, *, fit=True, seed=20260820, genres=(), timeout=3600, parent=None):
        super().__init__(parent)
        import threading
        self.directory, self.cache = str(directory), None if cache is None else str(cache)
        self.fit, self.seed, self.genres = fit, seed, tuple(genres)
        self.timeout = float(timeout)
        self._cancel = threading.Event()

    def request_cancel(self):
        self._cancel.set()

    def run(self):
        import multiprocessing
        import shutil
        import tempfile
        import time
        import uuid
        from pathlib import Path
        from .hearing_calibration import calibration_child, validate_proposal

        result = {"ok": False, "set_path": self.directory, "cache_path": self.cache}
        root = receiver = sender = process = None
        operation_id = uuid.uuid4().hex
        started = False
        try:
            if self._cancel.is_set():
                raise InterruptedError("Kalibrierung abgebrochen")
            root = Path(tempfile.mkdtemp(prefix="hpg-calibration-"))
            context = multiprocessing.get_context("spawn")
            receiver, sender = context.Pipe(duplex=False)
            process = context.Process(target=calibration_child, args=(
                sender, self.directory, self.cache, str(root), operation_id, self.fit, self.seed, self.genres,
            ))
            self.status_update.emit("Gebundener Snapshot, Übergangs-Replay und isolierter Fit …")
            process.start()
            started = True
            sender.close()
            deadline = time.monotonic() + self.timeout
            while True:
                if self._cancel.is_set():
                    raise InterruptedError("Kalibrierung abgebrochen; keine produktive Uebernahme")
                if receiver.poll(0.1):
                    ok, payload = receiver.recv()
                    if not ok:
                        raise RuntimeError(str(payload))
                    validate_proposal(payload, expected_operation_id=operation_id)
                    result.update(ok=True, proposal=payload, output=payload["output"])
                    break
                if not process.is_alive():
                    raise RuntimeError(f"Kalibrierungsprozess ohne Ergebnis beendet ({process.exitcode})")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Kalibrierung überschreitet Zeitlimit")
        except Exception as exc:
            result.update(output=str(exc), cancelled=isinstance(exc, InterruptedError))
        finally:
            for pipe in (receiver, sender):
                if pipe is not None:
                    pipe.close()
            may_cleanup = not started
            try:
                if started:
                    process.join(timeout=0.1)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=2)
                    if process.is_alive():
                        process.kill()
                        process.join()
                    may_cleanup = not process.is_alive()
                if process is not None:
                    process.close()
            except Exception as exc:
                may_cleanup = False
                result.update(ok=False, output=f"Eigenes Prozessende nicht nachgewiesen: {exc}")
            # Erst nach dem nachgewiesenen Prozessende eigene Temp-Dateien entfernen.
            if root is not None:
                try:
                    if not may_cleanup:
                        raise OSError("Prozessende nicht nachgewiesen; nichts entfernt")
                    shutil.rmtree(root)
                except OSError as exc:
                    result["cleanup_warning"] = f"Eigener Temp-Ordner blieb erhalten: {root}: {exc}"
        self.completed.emit(result)


class HearingApplyWorker(QThread):
    status_update = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, proposal, parent=None):
        super().__init__(parent)
        import copy
        self.proposal = copy.deepcopy(proposal)
        from .hearing_workflow import CancellationToken
        self.cancel = CancellationToken()

    def request_cancel(self):
        return self.cancel.request_cancel()

    def run(self):
        from .hearing_calibration import apply_proposal
        result = {"ok": False}
        try:
            self.cancel.checkpoint()
            self.status_update.emit("Prüfe bestätigten Vorschlag erneut; übernehme atomar …")
            state = apply_proposal(self.proposal, cancel=self.cancel)
            result.update(ok=True, apply_state=state)
        except Exception as exc:
            result["output"] = str(exc)
        self.completed.emit(result)

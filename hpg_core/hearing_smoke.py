"""Begrenzter Frozen-Smoke: Verpackung, Qt und echter RAM-Render, kein Klangurteil."""
from __future__ import annotations

import hashlib
import csv
import importlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path


def _probe_parallel_initializer():
    """Task-Eintritt NACH echtem Initializer; kein Beleg vor Cache-Zuweisung."""
    # Vor eigenen Numba-/Librosa-Imports messen, nicht nachtraeglich rekonstruieren.
    numba_loaded = "numba" in sys.modules
    beat_loaded = "librosa.beat" in sys.modules
    cache = os.environ.get("NUMBA_CACHE_DIR")
    import multiprocessing as mp
    import numba
    before = numba.config.CACHE_DIR
    importlib.import_module("librosa.beat")
    return {
        "worker_pid": os.getpid(), "start_method": mp.get_start_method(),
        "numba_loaded_at_task_entry": numba_loaded, "beat_loaded_at_task_entry": beat_loaded,
        "numba_cache_dir": cache, "effective_cache_dir_before_beat": before,
        "effective_cache_dir_after_beat": numba.config.CACHE_DIR,
        "beat_loaded_after_task": "librosa.beat" in sys.modules,
    }


def _check_parallel_initializer(*, timeout=30):
    """Eigener Produktions-Pool; begrenztes Warten, Cleanup unabhaengig nachpruefen."""
    from .parallel_analyzer import _create_executor, _shutdown_executor
    parent_environment = dict(os.environ)
    executor = _create_executor(1)
    root = getattr(executor, "_hpg_cache_root", None)
    identity = getattr(executor, "_hpg_cache_identity", None)
    processes, errors, payload, exitcodes = (), [], None, []
    try:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("Eigene Cache-Wurzel fehlt")
        stat = root.lstat()
        if (root.is_symlink() or root.is_junction() or root.resolve(strict=True) != root
                or (stat.st_dev, stat.st_ino) != identity):
            raise ValueError("Cache-Wurzelidentitaet nicht bestaetigt")
        future = executor.submit(_probe_parallel_initializer)
        # Submit startet den Worker; Referenzen vor result UND shutdown sichern.
        inventory = getattr(executor, "_processes", None)
        if inventory is None:
            raise ValueError("Prozessreferenzen unbekannt")
        processes = tuple(inventory.values())
        if len(processes) != 1:
            raise ValueError("Keine eindeutige nichtleere Prozessreferenz")
        payload = future.result(timeout=timeout)
        pid = payload["worker_pid"]
        if type(pid) is not int or pid <= 0 or pid == os.getpid() or pid != processes[0].pid:
            raise ValueError("Probe-PID stimmt nicht mit eigenem Worker ueberein")
        if (payload["start_method"] != "spawn" or payload["numba_loaded_at_task_entry"] is not True
                or payload["beat_loaded_at_task_entry"] is not False
                or payload["beat_loaded_after_task"] is not True):
            raise ValueError("Spawn-/Task-Eintritt-Timing nicht bestaetigt")
        cache = Path(payload["numba_cache_dir"])
        if (not cache.is_absolute() or cache.parent != root or not cache.is_dir()
                or any(p.is_symlink() or p.is_junction() for p in (cache, *cache.parents))
                or cache.resolve(strict=True) != cache):
            raise ValueError("Privater Worker-Cache nicht in eigener Wurzel")
        if not (str(cache) == payload["effective_cache_dir_before_beat"]
                == payload["effective_cache_dir_after_beat"]):
            raise ValueError("Effektiver Numba-Cache vor/nach Beat-Import abweichend")
        stat = root.lstat()
        if ((stat.st_dev, stat.st_ino) != identity or executor._hpg_cache_root != root
                or executor._hpg_cache_identity != identity):
            raise ValueError("Cache-Ownership waehrend Probe geaendert")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        try:
            _shutdown_executor(executor)
        except Exception as exc:
            errors.append(f"Shutdown: {type(exc).__name__}: {exc}")
        # None-Rueckgabe oder fehlende Exception beweist weder Join noch Loeschung.
        if not processes:
            errors.append("Nichtleere Prozessreferenzen fehlen; Reaping unbewiesen")
        for process in processes:
            try:
                process.join(timeout=1.0)
                if process.is_alive() is not False or type(process.exitcode) is not int:
                    raise ValueError("Worker-Ende/Exitcode nicht bestaetigt")
                # Der begrenzte Produktions-Owner darf nach Join terminieren.
                exitcodes.append(process.exitcode)
            except Exception as exc:
                errors.append(f"Reaping: {type(exc).__name__}: {exc}")
        try:
            if not isinstance(root, Path):
                raise ValueError("Cache-Wurzel unbekannt")
            try:
                root.lstat()
            except FileNotFoundError:
                pass
            else:
                raise ValueError("Cache-Wurzel blieb erhalten oder wurde ersetzt")
        except Exception as exc:
            errors.append(f"Cleanup: {type(exc).__name__}: {exc}")
        if dict(os.environ) != parent_environment:
            errors.append("Parent-Umgebung wurde veraendert")
    if errors:
        raise RuntimeError(f"Initializer-Smoke fehlgeschlagen; Cache-Wurzel: {root}; " + "; ".join(errors))
    return {**payload, "parent_pid": os.getpid(), "cache_root": str(root),
            "cache_root_identity": list(identity), "captured_process_count": len(processes),
            "worker_exitcodes": exitcodes,
            "parent_environment_unchanged": True, "workers_reaped": True, "cache_root_cleaned": True,
            "timing_scope": "task entry after production initializer; not before cache assignment"}


def run(report_path):
    """Nur expliziter Diagnose-Start; keine Produktiv-DB oder Musiksammlung."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtWidgets import QApplication
    import numpy as np
    import soundfile as sf
    from .hearing_playback import HearingAudioWorker
    from .hearing_jobs import HearingCalibrationWorker
    from .hearing_panel import HearingPrepareDialog, HearingRatingDialog, HearingFitDialog
    from .transition_renderer import TransitionClipSpec
    from tools.rate_transitions import _algorithm_build_fingerprint
    from tools import rate_transitions as rate
    from dataclasses import asdict

    app = QApplication.instance() or QApplication([])
    result = {"format": "hpg_native_smoke", "version": 1, "ok": False, "checks": {},
              "scope": "synthetic packaging/Qt/process/DSP transport, not musical or whole-app acceptance"}
    try:
        modules = ["hearing_sources", "hearing_workflow", "hearing_ratings", "hearing_jobs",
                   "hearing_panel", "hearing_playback", "hearing_calibration", "hearing_blind", "hearing_discovery"]
        for name in modules:
            importlib.import_module("hpg_core." + name)
        result["checks"]["native_imports"] = modules
        result["algorithm_build"] = _algorithm_build_fingerprint()
        prepare = HearingPrepareDialog()
        fit = HearingFitDialog()
        for mode in ("einzel", "kandidaten", "dreinoten", "dramaturgie"):
            dimensions = ("bewertung",) if mode == "einzel" else (("note",) if mode == "kandidaten" else ("track_note", "technik_note", "gesamt_note"))
            session = {"mode": mode, "groups": [{"id": "neutral", "ratings": {}, "clips": [{
                "pair_id": "neutral", "clip_id": "neutral", "path": None,
                "ratings": {key: "" for key in dimensions},
            }]}]}
            dialog = HearingRatingDialog(session, save=lambda *_args: None)
            assert set(dialog.rating_boxes) == set(dimensions)
            dialog.reject()
            dialog.deleteLater()
        prepare.reject()
        fit.reject()
        result["checks"]["native_forms"] = True
        result["checks"]["parallel_initializer"] = _check_parallel_initializer()
        with tempfile.TemporaryDirectory(prefix="hpg-native-smoke-") as tmp:
            root = Path(tmp)
            sr = 8000
            time = np.arange(sr * 6) / sr
            audio = np.column_stack((.05 * np.sin(2 * np.pi * 220 * time), .04 * np.sin(2 * np.pi * 220 * time)))
            sources = []
            for name in ("synthetic-a.wav", "synthetic-b.wav"):
                path = root / name
                sf.write(path, audio, sr, subtype="PCM_16")
                sources.append({"path": str(path), "root": str(root), "size_bytes": path.stat().st_size,
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            spec = TransitionClipSpec(sources[0]["path"], sources[1]["path"], 2., 1., 1.,
                                      target_sr=sr, pre_roll_sec=0., post_roll_sec=1., strict_beat_sync=False)
            worker = HearingAudioWorker(asdict(spec), sources, timeout=45)
            payloads, errors = [], []
            loop = QEventLoop()
            worker.audio_ready.connect(payloads.append)
            worker.audio_error.connect(errors.append)
            worker.finished.connect(loop.quit)
            deadline = QTimer()
            deadline.setSingleShot(True)
            deadline.timeout.connect(worker.request_cancel)
            deadline.timeout.connect(loop.quit)
            deadline.start(50000)
            worker.start()
            loop.exec()
            worker.request_cancel()
            if not worker.wait(10000):
                raise RuntimeError("Eigener Smoke-Worker nicht beendet")
            deadline.stop()
            assert not errors and len(payloads) == 1, errors
            info = sf.info(io.BytesIO(payloads[0]))
            decoded, decoded_sr = sf.read(io.BytesIO(payloads[0]), always_2d=True)
            assert info.channels == 2 and info.samplerate == sr and info.frames == sr * 2
            assert decoded_sr == sr and np.isfinite(decoded).all() and np.max(np.abs(decoded)) > 0
            assert {path.name for path in root.iterdir()} == {"synthetic-a.wav", "synthetic-b.wav"}
            assert all(hashlib.sha256(Path(s["path"]).read_bytes()).hexdigest() == s["sha256"] for s in sources)
            result["checks"]["spawn_ram_render"] = {"frames": info.frames, "samplerate": sr, "channels": 2,
                                                     "new_disk_audio": False, "sources_unchanged": True}
        # Echter Child-/Proposal-Transport: zu wenig Bewertungen muss abgelehnt werden.
        preferences = Path(os.environ["HPG_CANDIDATE_PREFERENCES_FILE"])
        before_preferences = preferences.read_bytes() if preferences.exists() else None
        temporary_root = Path(tempfile.gettempdir())
        before_snapshots = set(temporary_root.glob("hpg-calibration-*"))
        with tempfile.TemporaryDirectory(prefix="hpg-smoke-csv-") as tmp:
            root = Path(tmp)
            for name, fields, rows in (
                ("merkmale.csv", ("pair_id", *rate.ALLE_FAKTOREN), [
                    {"pair_id": str(i), **{factor: (i + 1) / 4 for factor in rate.ALLE_FAKTOREN}}
                    for i in range(2)]),
                ("bewertung.csv", ("pair_id", "clip", "bewertung"), [
                    {"pair_id": str(i), "clip": f"clips/{i}.wav", "bewertung": ""} for i in range(2)]),
            ):
                with (root / name).open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
            worker = HearingCalibrationWorker(root, None, timeout=45)
            results = []
            loop = QEventLoop()
            worker.completed.connect(results.append)
            worker.finished.connect(loop.quit)
            deadline = QTimer()
            deadline.setSingleShot(True)
            deadline.timeout.connect(worker.request_cancel)
            deadline.timeout.connect(loop.quit)
            deadline.start(50000)
            worker.start()
            loop.exec()
            worker.request_cancel()
            if not worker.wait(10000):
                raise RuntimeError("Eigener Kalibrierungs-Smoke-Worker nicht beendet")
            deadline.stop()
            assert len(results) == 1 and results[0]["ok"] and not results[0].get("cleanup_warning"), results
            proposal = results[0]["proposal"]
            assert proposal["fit_status"] == "rejected" and proposal["single_proposal"] is None
            assert not proposal["gate_updates"] and proposal["live_applied"] is False
            assert proposal["binding"]["cache_path"] is None and proposal["binding"]["sources"] == {}
            assert {path.name for path in root.iterdir()} == {"merkmale.csv", "bewertung.csv"}
        assert set(temporary_root.glob("hpg-calibration-*")) == before_snapshots
        assert (preferences.read_bytes() if preferences.exists() else None) == before_preferences
        result["checks"]["spawn_csv_fit"] = {
            "fit_status": "rejected", "cache": None, "no_audio": True,
            "preferences_unchanged": True, "snapshot_cleaned": True,
        }
        result["ok"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    with Path(report_path).open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False, allow_nan=False)
    app.processEvents()
    return 0 if result["ok"] else 1

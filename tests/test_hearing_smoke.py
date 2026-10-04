"""Echter isolierter Diagnose-Start; keine musikalische Abnahme."""
import json
import os
from pathlib import Path
import subprocess
import sys
import ast
import types

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _smoke_bootstrap_source():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8-sig"))
    stop = next(i for i, node in enumerate(tree.body) if isinstance(node, ast.ImportFrom) and node.module == "PyQt6.QtWidgets")
    return ast.unparse(ast.Module(body=tree.body[:stop], type_ignores=[]))


@pytest.mark.parametrize("report_race", [False, True])
def test_smoke_hook_captures_predispatch_exception_without_overwriting(tmp_path, report_race):
    root = tmp_path / "owned"
    root.mkdir()
    report = root / "report.json"
    injection = ("\n_smoke_report.write_bytes(b'foreign report')" if report_race else "")
    source = _smoke_bootstrap_source() + injection + "\nraise RuntimeError('injected startup failure')"
    environment = dict(os.environ, HPG_SMOKE_ROOT=str(root))
    run = subprocess.run([sys.executable, "-c", "__file__=" + repr(str(ROOT / "main.py")) + "\n" + source,
                          "--hpg-native-smoke", str(report)], cwd=tmp_path, env=environment,
                         capture_output=True, timeout=30)
    assert run.returncode != 0
    if report_race:
        assert report.read_bytes() == b"foreign report"
    else:
        result = json.loads(report.read_bytes())
        assert result["ok"] is False and result["phase"] == "startup_import"
        assert result["checks"] == {}
        assert "injected startup failure" in result["traceback"]
    assert not list(root.rglob("*.db"))


def test_smoke_hook_absent_in_normal_bootstrap(tmp_path):
    source = _smoke_bootstrap_source() + "\nassert _bootstrap_sys.excepthook is _bootstrap_sys.__excepthook__"
    run = subprocess.run([sys.executable, "-c", "__file__=" + repr(str(ROOT / "main.py")) + "\n" + source],
                         cwd=tmp_path, capture_output=True, timeout=30)
    assert run.returncode == 0, run.stderr


@pytest.mark.parametrize("kind", ["missing_root", "missing_report", "outside", "existing", "absent_directory"])
def test_native_smoke_rejects_bad_arguments_before_product_state(tmp_path, kind):
    root = tmp_path / "owned"
    root.mkdir()
    report = root / "report.json"
    args = [str(report)]
    environment = dict(os.environ)
    environment["HPG_SMOKE_ROOT"] = str(root)
    environment["HPG_CACHE_FILE"] = str(tmp_path / "must-not-create.db")
    if kind == "missing_root":
        environment.pop("HPG_SMOKE_ROOT", None)
    elif kind == "missing_report":
        args = []
    elif kind == "outside":
        args = [str(tmp_path / "outside.json")]
    elif kind == "absent_directory":
        environment["HPG_SMOKE_ROOT"] = str(tmp_path / "absent")
    else:
        report.write_bytes(b"valuable")
    run = subprocess.run([sys.executable, str(ROOT / "main.py"), "--hpg-native-smoke", *args],
                         cwd=tmp_path, env=environment, capture_output=True, timeout=30)
    assert run.returncode == 2
    assert not (tmp_path / "must-not-create.db").exists()
    assert not (root / "state").exists()
    if kind == "existing":
        assert report.read_bytes() == b"valuable"


def test_smoke_dispatch_restores_actual_previous_hook(monkeypatch):
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8-sig"))
    entry = next(node for node in reversed(tree.body) if isinstance(node, ast.If))
    branch = entry.body[0]
    previous = lambda *_args: None
    startup = lambda *_args: None
    runtime = types.SimpleNamespace(argv=["main.py", "--hpg-native-smoke", "report.json"], excepthook=startup)
    smoke = types.ModuleType("hpg_core.hearing_smoke")

    def run(_path):
        assert runtime.excepthook is previous
        return 0

    smoke.run = run
    monkeypatch.setitem(sys.modules, "hpg_core.hearing_smoke", smoke)
    source = ast.Module(body=[branch], type_ignores=[])
    with pytest.raises(SystemExit) as ended:
        exec(compile(source, "smoke-dispatch", "exec"), {"sys": runtime, "_smoke_previous_hook": previous})
    assert ended.value.code == 0


def test_source_smoke_actual_qt_spawn_ram_dsp_from_unrelated_directory(tmp_path):
    root = tmp_path / "owned"
    root.mkdir()
    report = root / "report.json"
    environment = dict(os.environ, HPG_SMOKE_ROOT=str(root))
    run = subprocess.run([sys.executable, str(ROOT / "main.py"), "--hpg-native-smoke", str(report)],
                         cwd=tmp_path, env=environment, capture_output=True, timeout=180)
    assert run.returncode == 0, (run.stdout, run.stderr)
    result = json.loads(report.read_bytes())
    assert result["ok"] is True
    assert result["checks"]["spawn_ram_render"] == {
        "frames": 16000, "samplerate": 8000, "channels": 2,
        "new_disk_audio": False, "sources_unchanged": True,
    }
    assert result["checks"]["spawn_csv_fit"] == {
        "fit_status": "rejected", "cache": None, "no_audio": True,
        "preferences_unchanged": True, "snapshot_cleaned": True,
    }
    check = result["checks"]["parallel_initializer"]
    assert check["worker_pid"] != check["parent_pid"] and check["worker_pid"] > 0
    assert check["start_method"] == "spawn"
    assert check["numba_loaded_at_task_entry"] is True
    assert check["beat_loaded_at_task_entry"] is False
    assert check["beat_loaded_after_task"] is True
    assert check["numba_cache_dir"] == check["effective_cache_dir_before_beat"] == check["effective_cache_dir_after_beat"]
    assert Path(check["numba_cache_dir"]).parent == Path(check["cache_root"])
    assert check["captured_process_count"] == 1
    assert check["parent_environment_unchanged"] is True
    assert check["workers_reaped"] is True and check["cache_root_cleaned"] is True
    assert check["timing_scope"] == "task entry after production initializer; not before cache assignment"
    assert not Path(check["cache_root"]).exists()
    from tools.rate_transitions import _algorithm_build_fingerprint
    assert result["algorithm_build"] == _algorithm_build_fingerprint()
    assert not list(root.rglob("*.wav"))
    assert not list(root.rglob("*.mp3"))


@pytest.mark.parametrize("failure", [
    "none", "timeout", "cancelled", "task_error", "empty_refs", "unknown_refs", "wrong_identity",
    "replaced_root", "foreign_cache", "pre_config", "post_config", "prebeat",
    "wrong_pid", "parent_env", "alive", "unknown_alive", "unknown_exit",
    "join_error", "root_retained", "shutdown_error",
])
def test_initializer_probe_fails_closed_and_checks_actual_cleanup(tmp_path, monkeypatch, failure):
    # Rueckkehr ohne Exception ist kein Reaping-/Cleanup-Beleg. Fehler kontrolliert injizieren.
    from concurrent.futures import CancelledError, TimeoutError
    from hpg_core import hearing_smoke as smoke, parallel_analyzer as pa
    probe = getattr(smoke, "_check_parallel_initializer", None)
    assert callable(probe), "Initializer-Probe fehlt"
    root = tmp_path / "owned-pool"
    root.mkdir()
    identity = (root.stat().st_dev, root.stat().st_ino)
    cache = root / "worker-4242-private"
    cache.mkdir()
    foreign = tmp_path / "foreign-cache"
    foreign.mkdir()
    (foreign / "valuable").write_bytes(b"preserve")
    payload = {
        "worker_pid": 4242, "start_method": "spawn", "numba_loaded_at_task_entry": True,
        "beat_loaded_at_task_entry": False, "beat_loaded_after_task": True,
        "numba_cache_dir": str(cache), "effective_cache_dir_before_beat": str(cache),
        "effective_cache_dir_after_beat": str(cache),
    }
    events = []
    class Process:
        pid = 4242
        exitcode = None
        def join(self, timeout=None):
            assert timeout is not None and 0 <= timeout <= 1
            events.append("join")
            if failure == "join_error":
                raise RuntimeError("synthetic join failure")
        def is_alive(self):
            events.append("status")
            if failure == "unknown_alive":
                raise RuntimeError("synthetic unknown status")
            return failure == "alive"
    process = Process()
    class Future:
        def result(self, timeout=None):
            assert timeout == .01
            events.append("result")
            if failure == "timeout":
                raise TimeoutError("synthetic deadline")
            if failure == "cancelled":
                raise CancelledError("synthetic cancelled future")
            if failure == "task_error":
                raise ValueError("synthetic task failure")
            if failure == "parent_env":
                monkeypatch.setenv("NUMBA_CACHE_DIR", str(foreign))
            return payload
    executor = types.SimpleNamespace(_hpg_cache_root=root, _hpg_cache_identity=identity,
                                     _processes={4242: process})
    def submit(task):
        assert task is smoke._probe_parallel_initializer
        events.append("submit")
        return Future()
    executor.submit = submit
    if failure == "empty_refs":
        executor._processes = {}
    elif failure == "unknown_refs":
        executor._processes = None
    elif failure == "wrong_identity":
        executor._hpg_cache_identity = (-1, -1)
    elif failure == "foreign_cache":
        payload.update(numba_cache_dir=str(foreign), effective_cache_dir_before_beat=str(foreign),
                       effective_cache_dir_after_beat=str(foreign))
    elif failure == "pre_config":
        payload["effective_cache_dir_before_beat"] = str(foreign)
    elif failure == "post_config":
        payload["effective_cache_dir_after_beat"] = str(foreign)
    elif failure == "prebeat":
        payload["beat_loaded_at_task_entry"] = True
    elif failure == "wrong_pid":
        payload["worker_pid"] = 99
    def create(count):
        assert count == 1
        return executor
    def shutdown(value):
        assert value is executor
        events.append("shutdown")
        executor._processes = None
        process.exitcode = None if failure == "unknown_exit" else 0
        if failure == "shutdown_error":
            raise RuntimeError("synthetic shutdown failure")
        if failure == "replaced_root":
            root.rename(tmp_path / "old-owned")
            root.mkdir()
            (root / "replacement").write_bytes(b"preserve replacement")
        elif failure != "root_retained":
            cache.rmdir()
            root.rmdir()
    monkeypatch.setattr(pa, "_create_executor", create)
    monkeypatch.setattr(pa, "_shutdown_executor", shutdown)
    if failure == "none":
        result = probe(timeout=.01)
        assert result["workers_reaped"] is True and result["cache_root_cleaned"] is True
        assert events.index("shutdown") < events.index("join")
    else:
        with pytest.raises(RuntimeError, match="Initializer") as error:
            probe(timeout=.01)
        assert str(root) in str(error.value)
        assert "shutdown" in events
        if failure == "cancelled":
            assert "CancelledError: synthetic cancelled future" in str(error.value)
            assert events.index("result") < events.index("shutdown") < events.index("join") < events.index("status")
            assert process.exitcode == 0 and not root.exists()
    assert (foreign / "valuable").read_bytes() == b"preserve"
    if failure == "replaced_root":
        assert (root / "replacement").read_bytes() == b"preserve replacement"

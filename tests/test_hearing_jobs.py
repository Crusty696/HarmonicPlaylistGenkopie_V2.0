"""Service-Worker pruefen echte Publikation und kooperativen Abbruch."""

from tests.test_hearing_workflow import config_fixture

import pytest


@pytest.mark.parametrize("fault", ["valid", "public", "key", "inside", "source", "missing", "assignment", "cancel"])
def test_blind_check_real_worker_validates_without_disclosing_or_writing(tmp_path, qtbot, monkeypatch, fault):
    import json
    from PyQt6.QtCore import QThread
    from hpg_core import hearing_blind, hearing_jobs
    from tests.test_hearing_blind import _fixture
    from tests.test_hearing_native_integration import _fingerprints

    manifest, output, key, root = _fixture(tmp_path, count=2)
    public, _ = hearing_blind.prepare_blind_references(manifest, output, key, root, seed=3)
    if fault == "public":
        public.write_text('{"private_secret": "SECRET"}', encoding="utf-8")
    elif fault == "key":
        key.write_text("SECRET invalid JSON", encoding="utf-8")
    elif fault == "inside":
        inside = output / "SECRET-key.json"
        inside.write_bytes(key.read_bytes())
        key = inside
    elif fault == "source":
        (root / "hpg_0.wav").write_bytes(b"SECRET changed source")
    elif fault == "missing":
        key = tmp_path / "SECRET-missing-key.json"
    elif fault == "assignment":
        private = json.loads(key.read_text(encoding="utf-8"))
        private["pairs"][0]["original_pair_id"] = "SECRET"
        key.write_text(json.dumps(private), encoding="utf-8")
    before = _fingerprints(tmp_path)
    worker_type = getattr(hearing_jobs, "HearingBlindCheckWorker", None)
    assert worker_type is not None, "Blind-Integritaetsworker fehlt"
    worker = worker_type(public, key)
    gui_thread, hashes, messages = QThread.currentThread(), [], []
    real_hash = hearing_blind._fingerprint
    def observe_hash(path, checkpoint):
        hashes.append(QThread.currentThread())
        return real_hash(path, checkpoint)
    monkeypatch.setattr(hearing_blind, "_fingerprint", observe_hash)
    worker.status_update.connect(messages.append)
    if fault == "cancel":
        worker.request_cancel()
    with qtbot.waitSignal(worker.completed, timeout=10000) as signal:
        worker.start()
    assert worker.wait(5000)
    result = signal.args[0]
    assert result["ok"] is (fault == "valid")
    if fault == "valid":
        assert result == {"ok": True, "pair_count": 2}
        assert hashes and all(thread != gui_thread for thread in hashes)
    else:
        assert result["cancelled"] is (fault == "cancel")
        assert result["output"]
    exposed = json.dumps([result, messages], ensure_ascii=False)
    assert "SECRET" not in exposed and str(key) not in exposed
    assert "original_" not in exposed and "candidate_a_system" not in exposed
    assert _fingerprints(tmp_path) == before


def test_blind_check_worker_cooperative_cancel_during_real_hash(tmp_path, qtbot, monkeypatch):
    import threading
    from hpg_core import hearing_blind, hearing_jobs
    from tests.test_hearing_blind import _fixture
    from tests.test_hearing_native_integration import _fingerprints
    manifest, output, key, root = _fixture(tmp_path)
    public, _ = hearing_blind.prepare_blind_references(manifest, output, key, root)
    before = _fingerprints(tmp_path)
    worker_type = getattr(hearing_jobs, "HearingBlindCheckWorker", None)
    assert worker_type is not None, "Blind-Integritaetsworker fehlt"
    entered, release = threading.Event(), threading.Event()
    real_hash = hearing_blind._fingerprint
    def paused_hash(path, checkpoint):
        entered.set()
        assert release.wait(10)
        return real_hash(path, checkpoint)
    monkeypatch.setattr(hearing_blind, "_fingerprint", paused_hash)
    worker = worker_type(public, key)
    try:
        with qtbot.waitSignal(worker.completed, timeout=15000) as signal:
            worker.start()
            qtbot.waitUntil(entered.is_set, timeout=5000)
            worker.request_cancel()
            release.set()
        assert worker.wait(5000)
        assert signal.args[0]["cancelled"] and not signal.args[0]["ok"]
        assert _fingerprints(tmp_path) == before
    finally:
        release.set()
        worker.wait(5000)


def test_csv_single_worker_real_spawn_preserves_none_cache(tmp_path, monkeypatch, qtbot):
    from tests.test_hearing_calibration import _csv_single
    from hpg_core.hearing_jobs import HearingCalibrationWorker
    root = _csv_single(tmp_path)
    live = tmp_path / "live.json"
    live.write_bytes(b"parent preferences untouched")
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(live))
    worker = HearingCalibrationWorker(root, None, timeout=30)
    with qtbot.waitSignal(worker.completed, timeout=35000) as signal:
        worker.start()
    assert worker.wait(5000)
    result = signal.args[0]
    assert result["ok"], result["output"]
    assert result["cache_path"] is None
    assert result["proposal"]["binding"]["cache_path"] is None
    assert result["proposal"]["fit_status"] == "rejected"
    assert live.read_bytes() == b"parent preferences untouched"
    assert "cleanup_warning" not in result


def test_prepare_worker_publishes_source_metadata(config_fixture, qtbot):
    from hpg_core.hearing_jobs import HearingPrepareWorker
    worker = HearingPrepareWorker(config_fixture)
    with qtbot.waitSignal(worker.completed, timeout=5000) as signal:
        worker.start()
    assert worker.wait(5000)
    result = signal.args[0]
    assert result["ok"] and result["prepared_only"]
    assert result["report_path"] == ""
    assert not list(config_fixture.output_dir.rglob("*.wav"))


def test_prepare_worker_cancel_before_start_publishes_nothing(config_fixture, qtbot):
    from hpg_core.hearing_jobs import HearingPrepareWorker
    worker = HearingPrepareWorker(config_fixture)
    worker.request_cancel()
    with qtbot.waitSignal(worker.completed, timeout=5000) as signal:
        worker.start()
    assert worker.wait(5000)
    assert signal.args[0]["cancelled"]
    assert not config_fixture.output_dir.exists()

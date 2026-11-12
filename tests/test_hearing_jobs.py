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


@pytest.mark.artifact_contract
def test_portable_blind_export_worker_copies_neutral_clips_and_separates_key(tmp_path, qtbot):
    import csv
    from hpg_core import hearing_jobs
    from tests.test_hearing_blind import _fixture
    from tests.test_hearing_native_integration import _fingerprints

    manifest, output, _key, root = _fixture(tmp_path, count=2)
    key = tmp_path / "private" / "blind_key.csv"
    before = _fingerprints(root)
    worker = hearing_jobs.HearingBlindExportWorker({
        "manifest": manifest,
        "output_dir": output,
        "key_path": key,
        "source_root": root,
        "seed": 7,
    })
    messages = []
    worker.status_update.connect(messages.append)

    with qtbot.waitSignal(worker.completed, timeout=10000) as signal:
        worker.start()
    assert worker.wait(5000)

    result = signal.args[0]
    assert result == {
        "ok": True,
        "public_path": str(output / "blind_session.csv"),
        "key_path": str(key),
    }
    public_path = output / "blind_session.csv"
    public_rows = list(csv.DictReader(public_path.open(encoding="utf-8")))
    key_rows = list(csv.DictReader(key.open(encoding="utf-8")))
    assert len(public_rows) == 2 and len(key_rows) == 4
    assert all((output / row[field]).is_file() for row in public_rows for field in (
        "candidate_a_clip", "candidate_b_clip"
    ))
    assert all("hpg" not in row[field].casefold() and "baseline" not in row[field].casefold()
               for row in public_rows for field in ("candidate_a_clip", "candidate_b_clip"))
    assert {row["system"] for row in key_rows} == {"HPG", "baseline"}
    assert key.parent != output and "erstelle neutrale Sessionkopien" in messages[0]
    assert _fingerprints(root) == before

    check_worker = hearing_jobs.HearingBlindExportCheckWorker(public_path, key)
    with qtbot.waitSignal(check_worker.completed, timeout=10000) as check_signal:
        check_worker.start()
    assert check_worker.wait(5000)
    assert check_signal.args[0] == {"session_id": public_rows[0]["session_id"],
                                    "pair_count": 2, "clip_count": 4, "ok": True}

    cancel_worker = hearing_jobs.HearingBlindExportCheckWorker(public_path, key)
    assert cancel_worker.request_cancel()
    with qtbot.waitSignal(cancel_worker.completed, timeout=5000) as cancel_signal:
        cancel_worker.start()
    assert cancel_worker.wait(5000)
    assert cancel_signal.args[0]["cancelled"] and not cancel_signal.args[0]["ok"]


def test_portable_blind_export_worker_cancels_before_publish_and_cleans_staging(
    tmp_path, qtbot, monkeypatch
):
    import threading
    from hpg_core import hearing_jobs
    from tests.test_hearing_blind import _fixture
    from tools import prepare_dj_blind_test

    manifest, output, _key, root = _fixture(tmp_path, count=2)
    key = tmp_path / "private" / "blind_key.csv"
    entered, release = threading.Event(), threading.Event()
    real_prepare = prepare_dj_blind_test.prepare

    def paused_prepare(*args, **kwargs):
        progress = kwargs["progress"]

        def pause_after_staging(current, total, message):
            progress(current, total, message)
            entered.set()
            assert release.wait(10)

        kwargs["progress"] = pause_after_staging
        return real_prepare(*args, **kwargs)

    monkeypatch.setattr(prepare_dj_blind_test, "prepare", paused_prepare)
    worker = hearing_jobs.HearingBlindExportWorker({
        "manifest": manifest, "output_dir": output, "key_path": key,
        "source_root": root, "seed": 7,
    })
    try:
        with qtbot.waitSignal(worker.completed, timeout=10000) as signal:
            worker.start()
            qtbot.waitUntil(entered.is_set, timeout=5000)
            assert worker.request_cancel()
            release.set()
        assert worker.wait(5000)
        assert signal.args[0]["cancelled"] is True
        assert signal.args[0]["ok"] is False
        assert not output.exists() and not key.exists()
        assert not list(tmp_path.glob(".session.staging-*"))
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


def test_prepare_worker_publishes_source_metadata(config_fixture, qtbot, monkeypatch):
    from hpg_core.hearing_jobs import HearingPrepareWorker
    from hpg_core import hearing_playback
    checked = []
    def preflight(spec, sources, checkpoint):
        checkpoint()
        hearing_playback._check_sources(sources)
        checked.append((spec, sources))
        return True
    # Diese Fixture enthält nur Quellidentitäten, kein decodierbares Audio.
    monkeypatch.setattr(hearing_playback, "preflight_renderability", preflight)
    worker = HearingPrepareWorker(config_fixture)
    with qtbot.waitSignal(worker.completed, timeout=5000) as signal:
        worker.start()
    assert worker.wait(5000)
    result = signal.args[0]
    assert result["ok"] and result["prepared_only"]
    assert result["report_path"] == ""
    assert len(checked) == 1
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

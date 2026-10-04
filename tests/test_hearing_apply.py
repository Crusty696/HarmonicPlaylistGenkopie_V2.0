"""Transportvertrag: gebundener Vorschlag, echter Merge und echter Reload.

Der Audit-Payload ist eine strukturell gueltige synthetische Fixture. Diese
Tests fuehren weder Replay-Audit noch Fit aus und belegen keine numerische
Auditgueltigkeit, statistische Kalibrierung oder musikalische Qualitaet.
Alle Quellen, Cache- und Override-Dateien liegen ausschliesslich im tmp_path.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from hpg_core import candidate_preferences as cp
from hpg_core import hearing_calibration as calibration
from hpg_core.hearing_workflow import CancellationToken, create_set
from tests.test_hearing_producer_sink import _source_service_config


@pytest.fixture
def transport_proposal(tmp_path, monkeypatch):
    config = _source_service_config(monkeypatch, tmp_path, "kandidaten")
    result = create_set(config)
    override = tmp_path / "preferences" / "candidate_preferences.json"
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(override))
    cp.reset_cache()
    binding = calibration.snapshot(result.output_dir, config.cache, seed=7, genres=("Psytrance",))
    # Handgeschriebene Testgewichte: exakt zehn kanonische Faktoren, Summe 1.
    weights = {key: (index + 1) / 55 for index, key in enumerate(cp.GEWICHT_SCHLUESSEL)}
    assert len(weights) == 10 and sum(weights.values()) == pytest.approx(1.)
    updates = cp._normalisiere_updates({"Psytrance": weights})
    proposal = {
        "format": "hpg_calibration_proposal", "version": 1, "operation_id": "a" * 32,
        "binding": binding, "audit_passed": True,
        # Nur die von validate_proposal geforderten Transportfelder; kein Audit-Ergebnis.
        "audit": {"ok": True, "status": "passed", "algorithm_build": deepcopy(binding["build"])},
        "fit_status": "passed", "gate_updates": updates,
        "diagnose": {"transport_contract_fixture": True, "numerical_audit_proven": False},
        "single_proposal": None, "live_applied": False,
        "output": "Synthetic transport fixture; no replay audit or fit executed.",
    }
    proposal["proposal_sha256"] = calibration._digest(proposal)
    calibration.validate_proposal(proposal, expected_operation_id="a" * 32)
    calibration.verify_binding(binding)
    assert cp.override_path() == override
    yield proposal, override, config
    cp.reset_cache()


def _seed_existing_preferences():
    """Echte Persistenz auch fuer den vorherigen Stand, kein Fake-Merge."""
    cp.merge_user_preferences_atomically(
        {"Techno": {key: .1 for key in cp.GEWICHT_SCHLUESSEL},
         "Psytrance": {"schema_rang": ["analyzer"]}},
        diagnose={"preserved_transport_context": {"previous": True}},
    )


@pytest.mark.parametrize("existing", [False, True])
def test_apply_transport_real_merge_and_effective_reload(transport_proposal, existing):
    proposal, override, config = transport_proposal
    if existing:
        _seed_existing_preferences()
    expected = cp._normalisiere_updates(proposal["gate_updates"])["Psytrance"]
    before_binding = deepcopy(proposal["binding"])
    token = CancellationToken()
    result = calibration.apply_proposal(proposal, cancel=token)
    assert result == {"persisted": True, "effective_reload": True, "error": "", "path": str(override)}
    assert token.state == token.COMPLETE
    disk = json.loads(override.read_text(encoding="utf-8"))
    assert {k: disk["Psytrance"][k] for k in cp.GEWICHT_SCHLUESSEL} == expected
    assert disk["_diagnose"]["fit_kandidaten"]["numerical_audit_proven"] is False
    if existing:
        assert disk["Techno"] == {key: .1 for key in cp.GEWICHT_SCHLUESSEL}
        assert disk["Psytrance"]["schema_rang"] == ["analyzer"]
        assert disk["_diagnose"]["fit_kandidaten"]["preserved_transport_context"] == {"previous": True}
    # Wegwerfen des Prozess-Caches erzwingt den echten Dateilader.
    cp.reset_cache()
    assert cp.kandidaten_gewichte("Psytrance") == expected
    assert cp.load_candidate_preferences()["Psytrance"]["gewichte"] == expected
    assert calibration.snapshot(config.output_dir, config.cache, seed=7, genres=("Psytrance",)) == before_binding
    assert proposal["live_applied"] is False
    assert not list(override.parent.glob(f".{override.name}.*.tmp"))


@pytest.mark.parametrize("changed", ["ratings", "source", "cache", "build"])
@pytest.mark.parametrize("existing", [False, True])
def test_wrong_binding_rejects_before_real_merge(transport_proposal, monkeypatch, changed, existing):
    from tools import rate_transitions as rate
    proposal, override, config = transport_proposal
    if existing:
        _seed_existing_preferences()
    before = override.read_bytes() if override.exists() else None
    calls = []
    real_merge = cp.merge_user_preferences_atomically
    def observe_merge(*a, **k):
        calls.append((a, k))
        return real_merge(*a, **k)
    monkeypatch.setattr(cp, "merge_user_preferences_atomically", observe_merge)
    if changed == "ratings":
        path = config.output_dir / "bewertung.csv"
        rows = rate.lies_csv(path)
        rows[0]["note"] = "4"
        rate.schreibe_csv(path, rate.BEWERTUNG_KANDIDATEN_SPALTEN, rows)
    elif changed == "source":
        path = Path(next(iter(proposal["binding"]["sources"])))
        path.write_bytes(path.read_bytes() + b"synthetic mutation")
    elif changed == "cache":
        config.cache.write_bytes(config.cache.read_bytes() + b"synthetic mutation")
    else:
        changed_build = deepcopy(proposal["binding"]["build"])
        changed_build["sha256"] = "b" * 64
        monkeypatch.setattr(rate, "_algorithm_build_fingerprint", lambda: changed_build)
    # Vorschlag unveraendert und strukturell gueltig; nur aktuelle Bindung ist falsch.
    calibration.validate_proposal(proposal)
    with pytest.raises(ValueError):
        calibration.apply_proposal(proposal)
    assert not calls
    assert (override.read_bytes() if override.exists() else None) == before


@pytest.mark.parametrize("boundary", ["entry", "begin_publish"])
def test_cancel_before_publish_creates_no_override(transport_proposal, monkeypatch, boundary):
    proposal, override, _ = transport_proposal
    token = CancellationToken()
    calls = []
    real_merge = cp.merge_user_preferences_atomically
    def observe_merge(*a, **k):
        calls.append(None)
        return real_merge(*a, **k)
    monkeypatch.setattr(cp, "merge_user_preferences_atomically", observe_merge)
    if boundary == "entry":
        token.request_cancel()
    else:
        real_begin = token.begin_publish
        def cancel_at_begin():
            assert token.request_cancel()
            return real_begin()
        monkeypatch.setattr(token, "begin_publish", cancel_at_begin)
    with pytest.raises(InterruptedError):
        calibration.apply_proposal(proposal, cancel=token)
    assert not calls and not override.exists()
    assert not override.parent.exists()
    assert token.state == token.CANCELLED


@pytest.mark.parametrize("failure", ["exception", "mismatch"])
def test_postcommit_merge_reload_error_reports_persisted_not_effective(transport_proposal, monkeypatch, failure):
    proposal, override, _ = transport_proposal
    expected = cp._normalisiere_updates(proposal["gate_updates"])["Psytrance"]
    token = CancellationToken()
    # Nur den Reload NACH dem echten atomaren Replace stoeren, niemals den Merge faken.
    with monkeypatch.context() as patch:
        def fail_reload():
            assert override.is_file()
            committed = json.loads(override.read_text(encoding="utf-8"))
            assert {k: committed["Psytrance"][k] for k in cp.GEWICHT_SCHLUESSEL} == expected
            if failure == "exception":
                raise RuntimeError("synthetic postcommit reload error")
            return {}
        patch.setattr(cp, "_lade_praeferenzen_unter_lock", fail_reload)
        result = calibration.apply_proposal(proposal, cancel=token)
    assert result["persisted"] is True
    assert result["effective_reload"] is False
    assert result["error"]
    assert result["path"] == str(override)
    assert token.state == token.COMPLETE
    assert {k: json.loads(override.read_bytes())["Psytrance"][k] for k in cp.GEWICHT_SCHLUESSEL} == expected
    # Der gueltige Commit bleibt bestehen und laesst sich danach wirklich neu laden.
    cp.reset_cache()
    assert cp.kandidaten_gewichte("Psytrance") == expected

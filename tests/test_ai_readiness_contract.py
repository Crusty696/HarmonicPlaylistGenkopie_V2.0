"""Eine Auswahl oder HTTP-Antwort ist kein GPU-/Eignungsnachweis."""
from types import SimpleNamespace

import pytest


@pytest.fixture
def panel(qtbot):
    import main
    widget = main.AdvancedParametersWidget()
    qtbot.addWidget(widget)
    widget.ai_enabled_checkbox.blockSignals(True)
    widget.ai_enabled_checkbox.setChecked(True)
    widget.ai_enabled_checkbox.blockSignals(False)
    return widget


def test_selection_does_not_claim_verified_readiness(panel):
    panel._on_model_changed("unverified-model")
    assert "bereit" not in panel.ai_status_label.text().lower()
    assert "unverified-model" in panel.ai_status_label.text()


def test_server_inventory_does_not_claim_verified_readiness(panel):
    panel._on_ai_detected(SimpleNamespace(
        running=True, name="LM Studio", models=["installed-model"],
        active_model="installed-model", base_url="http://localhost:1234/v1/chat/completions",
    ))
    assert "bereit" not in panel.ai_status_label.text().lower()


def test_failed_probe_does_not_claim_readiness(panel, monkeypatch):
    import main
    monkeypatch.setattr(main.QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(main.QMessageBox, "critical", lambda *a, **k: None)
    panel._on_test_finished(False, "GPU-Zuordnung fehlt", "model", 0.1)
    assert "bereit" not in panel.ai_status_label.text().lower()
    assert "GPU" in panel.ai_status_label.text()

"""Tests fuer die Uebergangs-Gewichte-Regler in AdvancedParametersWidget."""

import json

import pytest

import main
from hpg_core.genres import CANONICAL_GENRES
from hpg_core.tolerances import reset_cache

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _clear_tolerances_cache():
  """Verhindert, dass Tests sich gegenseitig ueber den Modul-Cache stoeren."""
  reset_cache()
  yield
  reset_cache()


def test_sliders_exist_with_default_start_values(qtbot):
  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)

  sliders = widget.transition_weight_sliders
  assert sliders["groove_weight"].value() == 12
  assert sliders["bass_weight"].value() == 8
  assert sliders["timbre_weight"].value() == 5
  assert sliders["mood_weight"].value() == 5


def test_moving_slider_writes_override_file(qtbot, monkeypatch, tmp_path):
  override_pfad = tmp_path / "transition_tolerances.json"
  monkeypatch.setenv("HPG_TOLERANCES_FILE", str(override_pfad))

  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)

  widget.transition_weight_sliders["groove_weight"].setValue(20)

  assert override_pfad.is_file()
  daten = json.loads(override_pfad.read_text(encoding="utf-8"))
  ein_genre = daten[CANONICAL_GENRES[0]]
  assert ein_genre["groove_weight"] == pytest.approx(0.20)

  summe = sum(
    ein_genre[k]
    for k in (
      "harmonic_weight",
      "bpm_weight",
      "energy_weight",
      "genre_weight",
      "groove_weight",
      "bass_weight",
      "timbre_weight",
      "mood_weight",
    )
  )
  assert summe == pytest.approx(1.0)


def test_weights_summing_to_one_or_more_show_error_and_skip_write(
  qtbot, monkeypatch, tmp_path
):
  override_pfad = tmp_path / "transition_tolerances.json"
  monkeypatch.setenv("HPG_TOLERANCES_FILE", str(override_pfad))

  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)

  # Jeder einzelne Schritt ist fuer sich gueltig und wird sofort
  # geschrieben (40, dann 40+30, dann 40+30+20 -> je < 1.0).
  widget.transition_weight_sliders["groove_weight"].setValue(40)
  widget.transition_weight_sliders["bass_weight"].setValue(30)
  widget.transition_weight_sliders["timbre_weight"].setValue(20)
  stand_vor_fehler = override_pfad.read_text(encoding="utf-8")

  # 40 + 30 + 20 + 20 = 110 -> Summe 1.10, ValueError erwartet. Die zuletzt
  # gueltig geschriebene Datei darf dabei NICHT ueberschrieben werden.
  widget.transition_weight_sliders["mood_weight"].setValue(20)

  assert "ungueltig" in widget.transition_weight_status.text()
  assert override_pfad.read_text(encoding="utf-8") == stand_vor_fehler


def test_reset_button_restores_default_start_values(qtbot, monkeypatch, tmp_path):
  override_pfad = tmp_path / "transition_tolerances.json"
  monkeypatch.setenv("HPG_TOLERANCES_FILE", str(override_pfad))

  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)

  widget.transition_weight_sliders["groove_weight"].setValue(20)
  widget.transition_weight_sliders["bass_weight"].setValue(20)

  widget._on_transition_weights_reset()

  sliders = widget.transition_weight_sliders
  assert sliders["groove_weight"].value() == 12
  assert sliders["bass_weight"].value() == 8
  assert sliders["timbre_weight"].value() == 5
  assert sliders["mood_weight"].value() == 5
  assert override_pfad.is_file()

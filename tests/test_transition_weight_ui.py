"""Tests fuer die Uebergangs-Gewichte-Regler in AdvancedParametersWidget."""

import json

import pytest

import main
from hpg_core.genres import CANONICAL_GENRES
from hpg_core.playlist import TransitionMetrics
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


def test_passung_tooltip_zeigt_alle_acht_faktoren(qtbot):
  panel = main.PlaylistPanel()
  qtbot.addWidget(panel)

  metrics = TransitionMetrics(
    harmonic_score=80,
    bpm_smoothness=0.7,
    energy_flow=0.6,
    genre_compatibility=0.9,
    overall_score=0.75,
    groove_match=0.5,
    bass_continuity=0.4,
    timbre_match=0.3,
    mood_match=0.2,
  )

  tooltip = panel._passung_tooltip(metrics)

  assert "Harmonik" in tooltip
  assert "80" in tooltip
  assert "BPM" in tooltip and "70" in tooltip
  assert "Energie" in tooltip and "60" in tooltip
  assert "Genre" in tooltip and "90" in tooltip
  assert "Groove" in tooltip and "50" in tooltip
  assert "Bassdruck" in tooltip and "40" in tooltip
  assert "Klangfarbe" in tooltip and "30" in tooltip
  assert "Stimmung" in tooltip and "20" in tooltip
  # Acht Faktor-Zeilen plus mindestens eine Ueberschrift.
  assert len(tooltip.strip().splitlines()) >= 9


def test_passung_tooltip_zeigt_nicht_bestimmbar_statt_null_prozent(qtbot):
  panel = main.PlaylistPanel()
  qtbot.addWidget(panel)

  metrics = TransitionMetrics(
    harmonic_score=80,
    bpm_smoothness=0.7,
    energy_flow=0.6,
    genre_compatibility=0.9,
    overall_score=0.75,
    groove_match=None,
    bass_continuity=0.4,
    timbre_match=0.3,
    mood_match=0.2,
  )

  tooltip = panel._passung_tooltip(metrics)

  groove_zeile = next(
    zeile for zeile in tooltip.splitlines() if "Groove" in zeile
  )
  assert "nicht bestimmbar" in groove_zeile
  assert "0 %" not in groove_zeile


def test_passung_tooltip_ohne_metrics_ist_leer(qtbot):
  panel = main.PlaylistPanel()
  qtbot.addWidget(panel)

  assert panel._passung_tooltip(None) == ""

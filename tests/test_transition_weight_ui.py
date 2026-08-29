"""Tests fuer die Uebergangs-Gewichte-Regler in AdvancedParametersWidget."""

import json

import pytest

import main
from hpg_core import candidate_preferences as cp
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


def test_sliders_exist_with_default_start_values(qtbot, monkeypatch, tmp_path):
  # Seit 2026-08-21 befuellt der Aufbau die Regler aus dem wirksamen Stand
  # (_lade_transition_regler). Ohne Isolierung laese der Test die echte
  # Toleranz-Datei des Entwicklerrechners und waere rechnerabhaengig rot.
  monkeypatch.setenv("HPG_TOLERANCES_FILE", str(tmp_path / "leer.json"))
  from hpg_core.tolerances import reset_cache
  reset_cache()
  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)

  sliders = widget.transition_weight_sliders
  assert set(sliders) == {
    "kandidaten_groove_weight",
    "kandidaten_bass_weight",
    "kandidaten_timbre_weight",
    "kandidaten_mood_weight",
    "kandidaten_loudness_weight",
  }
  assert sliders["kandidaten_groove_weight"].value() == 26
  assert sliders["kandidaten_bass_weight"].value() == 7
  assert sliders["kandidaten_timbre_weight"].value() == 4
  assert sliders["kandidaten_mood_weight"].value() == 4
  assert sliders["kandidaten_loudness_weight"].value() == 6


def test_moving_slider_writes_override_file(qtbot, monkeypatch, tmp_path):
  override_pfad = tmp_path / "transition_tolerances.json"
  monkeypatch.setenv("HPG_TOLERANCES_FILE", str(override_pfad))
  track_gewichte = {
    "harmonic_weight": 0.20,
    "bpm_weight": 0.10,
    "energy_weight": 0.10,
    "genre_weight": 0.10,
    "groove_weight": 0.25,
    "bass_weight": 0.10,
    "timbre_weight": 0.075,
    "mood_weight": 0.075,
  }
  override_pfad.write_text(
    json.dumps({CANONICAL_GENRES[0]: track_gewichte}), encoding="utf-8"
  )
  reset_cache()

  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)

  widget.transition_weight_sliders["kandidaten_groove_weight"].setValue(20)

  assert override_pfad.is_file()
  daten = json.loads(override_pfad.read_text(encoding="utf-8"))
  ein_genre = daten[CANONICAL_GENRES[0]]
  assert ein_genre["kandidaten_groove_weight"] == pytest.approx(0.20)
  # Nur der bewegte Regler wird aus der ganzzahligen Anzeige uebernommen;
  # unberuehrte echte Defaults duerfen nicht auf 4/26 Prozent abrunden.
  assert ein_genre["kandidaten_timbre_weight"] == pytest.approx(0.044)
  assert ein_genre["kandidaten_mood_weight"] == pytest.approx(0.044)
  assert {key: ein_genre[key] for key in track_gewichte} == track_gewichte

  from hpg_core.tolerances import KANDIDATEN_GEWICHT_SCHLUESSEL
  summe = sum(
    ein_genre[k] for k in KANDIDATEN_GEWICHT_SCHLUESSEL
  )
  assert summe == pytest.approx(1.0)


def test_weights_summing_to_one_or_more_show_error_and_skip_write(
  qtbot, monkeypatch, tmp_path
):
  override_pfad = tmp_path / "transition_tolerances.json"
  monkeypatch.setenv("HPG_TOLERANCES_FILE", str(override_pfad))

  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)

  # 50 + 30 + 4 + 4 + 6 = 94 % ist noch gueltig.
  widget.transition_weight_sliders["kandidaten_groove_weight"].setValue(50)
  widget.transition_weight_sliders["kandidaten_bass_weight"].setValue(30)
  stand_vor_fehler = override_pfad.read_text(encoding="utf-8")

  # 50 + 30 + 10 + 4 + 6 = 100 % -> ValueError. Die zuletzt gueltig
  # geschriebene Datei darf dabei nicht ueberschrieben werden.
  widget.transition_weight_sliders["kandidaten_timbre_weight"].setValue(10)

  assert "ungueltig" in widget.transition_weight_status.text()
  assert override_pfad.read_text(encoding="utf-8") == stand_vor_fehler
  assert widget.transition_weight_sliders["kandidaten_timbre_weight"].value() == 4


def test_reset_button_restores_default_start_values(qtbot, monkeypatch, tmp_path):
  override_pfad = tmp_path / "transition_tolerances.json"
  monkeypatch.setenv("HPG_TOLERANCES_FILE", str(override_pfad))
  track_gewichte = {
    "harmonic_weight": 0.20,
    "bpm_weight": 0.10,
    "energy_weight": 0.10,
    "genre_weight": 0.10,
    "groove_weight": 0.25,
    "bass_weight": 0.10,
    "timbre_weight": 0.075,
    "mood_weight": 0.075,
  }
  override_pfad.write_text(
    json.dumps({CANONICAL_GENRES[0]: track_gewichte}), encoding="utf-8"
  )
  reset_cache()

  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)

  widget.transition_weight_sliders["kandidaten_groove_weight"].setValue(20)
  widget.transition_weight_sliders["kandidaten_bass_weight"].setValue(20)

  widget._on_transition_weights_reset()

  sliders = widget.transition_weight_sliders
  assert sliders["kandidaten_groove_weight"].value() == 26
  assert sliders["kandidaten_bass_weight"].value() == 7
  assert sliders["kandidaten_timbre_weight"].value() == 4
  assert sliders["kandidaten_mood_weight"].value() == 4
  assert sliders["kandidaten_loudness_weight"].value() == 6
  daten = json.loads(override_pfad.read_text(encoding="utf-8"))
  assert {key: daten[CANONICAL_GENRES[0]][key] for key in track_gewichte} == track_gewichte
  assert not any(
    key.startswith("kandidaten_") for key in daten[CANONICAL_GENRES[0]]
  )


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



def test_lautheit_regler_schreibt_kandidaten_gewicht(qtbot, monkeypatch, tmp_path):
  override_pfad = tmp_path / "transition_tolerances.json"
  monkeypatch.setenv("HPG_TOLERANCES_FILE", str(override_pfad))
  reset_cache()
  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)
  sliders = widget.transition_weight_sliders
  assert "kandidaten_loudness_weight" in sliders
  assert sliders["kandidaten_loudness_weight"].value() == 6      # Startwert 0.060 * 100

  sliders["kandidaten_loudness_weight"].setValue(20)

  from hpg_core.tolerances import KANDIDATEN_GEWICHT_SCHLUESSEL, get_tolerances
  reset_cache()
  w = get_tolerances(CANONICAL_GENRES[0])
  assert w["kandidaten_loudness_weight"] == pytest.approx(0.20)
  assert sum(w[k] for k in KANDIDATEN_GEWICHT_SCHLUESSEL) == pytest.approx(1.0)
  assert w["groove_weight"] == pytest.approx(0.30)                # Track-Gewichte unberuehrt
  daten = json.loads(override_pfad.read_text(encoding="utf-8"))
  assert daten[CANONICAL_GENRES[0]]["kandidaten_loudness_weight"] == pytest.approx(0.20)


def test_bpm_tooltip_beschreibt_transitionplan_gate_statt_nachbar_garantie(qtbot):
  panel = main.LibraryPanel()
  qtbot.addWidget(panel)

  tooltip = panel.bpm_tolerance_slider.toolTip()

  assert "TransitionPlan" in tooltip
  assert "Half-/Double-Time" in tooltip
  assert "garantiert nicht" in tooltip
  assert "UNGEPLANT" in tooltip
  assert "nicht gerendert" in tooltip


def test_kandidaten_toleranzbasis_zeigt_initial_sofort_hoertest_overrides_sortiert(
  qtbot, monkeypatch, tmp_path
):
  toleranzen = tmp_path / "toleranzen.json"
  prefs = tmp_path / "prefs.json"
  monkeypatch.setenv("HPG_TOLERANCES_FILE", str(toleranzen))
  monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(prefs))
  gewichte = {key: 0.1 for key in cp.GEWICHT_SCHLUESSEL}
  prefs.write_text(json.dumps({
    "Techno": gewichte,
    "Psytrance": gewichte,
  }), encoding="utf-8")
  cp.reset_cache()
  reset_cache()

  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)

  assert widget.transition_weight_group.title() == "Editierbare Kandidaten-Toleranzbasis"
  status = widget.transition_weight_status.text()
  assert "naechsten Lauf" in status
  assert "Psytrance, Techno" in status
  assert "wirkt dort nicht" in status


def test_speichern_und_reset_zeigen_den_gleichen_override_hinweis(
  qtbot, monkeypatch, tmp_path
):
  toleranzen = tmp_path / "toleranzen.json"
  prefs = tmp_path / "prefs.json"
  monkeypatch.setenv("HPG_TOLERANCES_FILE", str(toleranzen))
  monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(prefs))
  prefs.write_text(json.dumps({
    "Psytrance": {key: 0.1 for key in cp.GEWICHT_SCHLUESSEL}
  }), encoding="utf-8")
  cp.reset_cache()
  reset_cache()
  widget = main.AdvancedParametersWidget()
  qtbot.addWidget(widget)

  widget.transition_weight_sliders["kandidaten_groove_weight"].setValue(20)
  assert "Kandidaten-Toleranzbasis gespeichert" in widget.transition_weight_status.text()
  assert "wirkt dort nicht" in widget.transition_weight_status.text()

  widget._on_transition_weights_reset()
  assert "Kandidaten-Toleranzbasis" in widget.transition_weight_status.text()
  assert "wirkt dort nicht" in widget.transition_weight_status.text()

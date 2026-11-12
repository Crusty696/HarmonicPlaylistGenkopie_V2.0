"""Lange Tracknamen dürfen die Übergangsbedienung nicht aus dem Fenster schieben."""

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QLabel

import main
from hpg_core.playlist_results import TransitionPlan, TransitionRecommendation
from tests.fixtures.track_factories import make_track


@pytest.mark.parametrize("width", [700, 1100])
def test_lange_titel_bleiben_in_der_uebergangsansicht(qtbot, width):
    tracks = [make_track(fileName=("Sehr_langer_Trackname_" * 12) + str(i)) for i in range(2)]
    plan = TransitionPlan(140.0, 70.0, 140.0, 156.0, 16.0, "pro_eq_swap")
    rec = TransitionRecommendation(
        0, *tracks, 140.0, 156.0, 70.0, 70.0, 16.0, 0.0, 0, 80, "low",
        "Übergang: 8 Takte", plan=plan, transition_type="pro_eq_swap",
        kandidaten=[{"rang": 1, "blend_bars": 8, "begruendung": "Messwerte " * 50}],
        kandidat_aktiv=1,
    )
    panel = main.MixTipsPanel()
    qtbot.addWidget(panel)
    panel.resize(width, 700)
    panel.set_recommendations([rec], tracks)
    panel.show()
    qtbot.wait(50)

    assert 0 < panel.width() <= width
    assert panel.scroll.horizontalScrollBar().maximum() == 0
    viewport = panel.scroll.viewport()
    for widget in panel.container.findChildren(QLabel):
        right = widget.mapTo(viewport, QPoint(widget.width(), 0)).x()
        assert right <= viewport.width()
    table = panel._kandidaten_tabellen[0]
    assert table.horizontalScrollBar().maximum() > 0

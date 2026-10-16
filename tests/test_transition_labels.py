"""Verständliche Messwerte und fehlende Übergangsfreigaben in der Tabelle."""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
import main
from hpg_core.theme import get_texture_label
from hpg_core.models import Track


@pytest.mark.parametrize('value', [0.86, 1.0])
def test_texture_similarity_does_not_claim_identity(value):
    assert get_texture_label(value) == 'Klangfarbe: sehr ähnlich'


@pytest.mark.parametrize('fingerprint', [[], [10, 0, 0], [10, float('nan'), 1]])
def test_missing_texture_is_not_measured_contrast(qtbot, fingerprint):
    item = main.PlaylistPanel._make_texture_item(
        SimpleNamespace(timbre_fingerprint=fingerprint),
        SimpleNamespace(timbre_fingerprint=[10, 1, 0]))
    assert 'unbekannt' in item.text()
    assert 'nicht bestimmbar' in item.toolTip()


def test_real_low_texture_has_measure_and_limits(qtbot):
    item = main.PlaylistPanel._make_texture_item(
        SimpleNamespace(timbre_fingerprint=[10, 1, 0]),
        SimpleNamespace(timbre_fingerprint=[10, 0, 1]))
    assert 'unterschiedlich' in item.text()
    assert '0.000' in item.toolTip()
    assert 'Synchronität' in item.toolTip()


def test_unplanned_reason_is_visible_without_musical_zero_grade(qtbot):
    reason = 'Tempoabstand zu groß\n4,25 BPM liegen über 2 BPM.'
    item = main.PlaylistPanel._make_unplanned_transition_score_item(reason)
    assert item.text() == 'Kein Übergang: Tempoabstand zu groß'
    assert reason in item.toolTip()
    assert '0%' not in item.text()
    assert item.data(Qt.ItemDataRole.UserRole) == 0.0


def test_analysis_mixpoint_explicitly_remains_proposal(qtbot):
    track = SimpleNamespace(mix_in_point=10, mix_out_point=100, bpm=120)
    rec = SimpleNamespace(index=0, plan=None, notes='Taktanfang unsicher\nTrack B')
    item, _ = main._mixpunkt_items(1, track, [rec])
    assert 'Vorschlag' in item.text()
    assert 'Taktanfang unsicher' in item.toolTip()


def test_table_initial_and_reorder_keep_reason_and_unknown(qtbot, monkeypatch):
    tracks = [Track(filePath='a', fileName='a'), Track(filePath='b', fileName='b')]
    reason = 'Taktanfang unsicher\nLokale Rhythmusmesswerte fehlen.'
    rec = SimpleNamespace(index=0, plan=None, notes=reason, kandidat_aktiv=0)
    panel = main.PlaylistPanel()
    qtbot.addWidget(panel)
    panel.set_playlist_data(tracks, {}, transition_recommendations=[rec])
    monkeypatch.setattr(main, 'calculate_playlist_quality', lambda *args: {})
    monkeypatch.setattr(main, 'compute_transition_recommendations', lambda *args, **kwargs: [rec])
    for refresh in (lambda: None, panel._update_table_after_reorder):
        refresh()
        assert panel.table.item(1, 14).text() == 'Kein Übergang: Taktanfang unsicher'
        assert reason in panel.table.item(1, 14).toolTip()
        assert 'unbekannt' in panel.table.item(1, 13).text()
        assert 'Vorschlag' in panel.table.item(1, 10).text()

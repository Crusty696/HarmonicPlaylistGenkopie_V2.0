"""Sichtbare Trackdetails verwenden die konkrete Tabelleninstanz."""

import main


def test_auswahl_zeigt_instanz_und_fehlenden_uebergang(qtbot, house_track):
    panel = main.PlaylistPanel()
    qtbot.addWidget(panel)
    panel.set_playlist_data([house_track, house_track], {}, transition_recommendations=[])
    assert hasattr(panel, "details_text")
    panel.table.setCurrentCell(1, 1)
    text = panel.details_text.toPlainText()
    assert "Position 2" in text
    assert "UNGEPLANT" in text
    assert "Analyseherkunft" in text
    panel.table.setCurrentCell(0, 1)
    assert "Erster Track" in panel.details_text.toPlainText()


def test_erweiterte_spalten_und_leere_details(qtbot, house_track):
    panel = main.PlaylistPanel()
    qtbot.addWidget(panel)
    assert hasattr(panel, "extended_columns")
    assert panel.table.isColumnHidden(9)
    assert not panel.table.isColumnHidden(14)
    panel.extended_columns.setChecked(True)
    assert not any(panel.table.isColumnHidden(i) for i in range(16))
    panel.set_playlist_data([house_track], {}, transition_recommendations=[])
    panel.table.setCurrentCell(0, 1)
    panel.set_playlist_data([], {}, transition_recommendations=[])
    assert "Titel auswählen" in panel.details_text.toPlainText()
    assert panel.details_text.accessibleName() == "Titel- und Übergangsdetails"


def test_tabellen_rollback_erhaelt_details_und_spaltenmodus(qtbot, house_track):
    panel = main.PlaylistPanel()
    qtbot.addWidget(panel)
    panel.set_playlist_data([house_track, house_track], {}, transition_recommendations=[])
    assert hasattr(panel, "details_text")
    panel.table.setCurrentCell(1, 1)
    panel._capture_reorder_table_snapshot()
    panel._restore_reorder_table_snapshot()
    assert panel.table.isColumnHidden(9)
    assert panel.table.currentRow() == 1
    assert "Position 2" in panel.details_text.toPlainText()


def test_veroeffentlichung_erhaelt_ansicht_und_konkretes_vorkommen(qtbot, monkeypatch, house_track):
    from dataclasses import replace
    from hpg_core.playlist import generate_playlist_result
    from tests.test_main_window import _window

    window = _window(qtbot, monkeypatch)
    result = generate_playlist_result([house_track, house_track], "Warm-Up", candidate_choice_snapshot={})
    panel = window.playlist_panel
    panel.set_playlist_data(list(result.tracks), {}, transition_recommendations=[], generation_result=result)
    panel.extended_columns.setChecked(True)
    panel.details_toggle.setChecked(False)
    panel.table.setCurrentCell(1, 1)
    reordered = replace(result, occurrences=tuple(reversed(result.occurrences)))
    prepared = window._prepare_uebergangs_views(
        list(reordered.tracks), {}, [], 2.0, {}, generation_result=reordered,
    )
    window._commit_uebergangs_views(prepared, list(reordered.tracks), {}, reordered)
    replacement = window.playlist_panel
    assert replacement.extended_columns.isChecked()
    assert not replacement.details_toggle.isChecked()
    assert replacement.table.currentRow() == 0
    assert replacement.table.item(0, 1).data(main.Qt.ItemDataRole.UserRole) == result.occurrences[1].occurrence_id


def test_bibliothek_expertenparameter_bleiben_erreichbar_ohne_fensterwachstum(qtbot):
    panel = main.LibraryPanel()
    qtbot.addWidget(panel)
    panel.resize(1000, 650)
    panel.show()
    assert panel.advanced_params.isHidden()
    panel.advanced_toggle.click()
    assert not panel.advanced_params.isHidden()
    assert panel.height() == 650
    assert panel.settings_scroll.widgetResizable()


def test_details_zeigen_keine_unvalidierte_diagnose_payload(house_track):
    from hpg_core.ui.track_details import playlist_track_details
    house_track.measurement_diagnostics = {"unbekannt": {"reason": "UNVALIDIERTE_PAYLOAD"}}
    text = playlist_track_details(house_track, 0, [])
    assert "UNVALIDIERTE_PAYLOAD" not in text
    assert "ungültige Diagnose" in text


def test_toolbar_zeigt_laufschritt_und_naechste_aktion(qtbot):
    toolbar = main.ToolbarWidget()
    qtbot.addWidget(toolbar)
    assert hasattr(toolbar, "workflow_label")
    toolbar.set_run_state(main.RunState.AUDIO)
    assert "Analyse" in toolbar.workflow_label.text()
    toolbar.set_run_state(main.RunState.PARTIAL)
    assert "prüfen" in toolbar.workflow_label.text()
    toolbar.set_run_state(main.RunState.CANCELLING)
    assert "Abbruch" in toolbar.workflow_label.text()

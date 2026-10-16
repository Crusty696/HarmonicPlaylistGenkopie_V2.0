"""Karten bewerten den gebundenen Clip; Renderfehler bleiben harte Sperren."""

import io
import wave

import pytest
from PyQt6.QtCore import Qt


DIMENSIONS = ("track_note", "technik_note", "gesamt_note")


def _session(*, spec=False, groups=1):
    return {"mode": "dreinoten", "groups": [
        {"id": f"p{pair}", "ratings": {}, "clips": [
            {"pair_id": f"p{pair}", "clip_id": f"p{pair}_c{clip}",
             "path": None, "ratings": {name: "" for name in DIMENSIONS},
             "gewaehlt": "", **({"spec": {
                 "mix_out_sec": 3.0, "pre_roll_sec": 8.0,
                 "crossfade_sec": 12.0, "post_roll_sec": 5.0,
             }} if spec else {})}
            for clip in (1, 2)
        ]} for pair in range(1, groups + 1)
    ]}


def _dialog(qtbot, *, session=None, read_only=False):
    from hpg_core.hearing_panel import HearingRatingDialog

    saved = []
    dialog = HearingRatingDialog(session or _session(),
        save=lambda route, data: saved.append((route, data)), read_only=read_only)
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog, saved


def _ready(dialog):
    # Synthetisches WAV prueft GUI-Freigabe, nicht DSP oder Musikqualitaet.
    data = io.BytesIO()
    with wave.open(data, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 8000)
    worker = object()
    dialog._audio_worker = worker
    dialog._render_ready(data.getvalue(), worker, dialog._render_generation)
    dialog._audio_worker = None
    return worker


def test_both_variant_cards_show_three_direct_note_scales(qtbot):
    dialog, saved = _dialog(qtbot)
    assert len(dialog.variant_cards) == 2
    for card in dialog.variant_cards:
        assert card.isVisible()
        assert set(card.rating_boxes) == set(DIMENSIONS)
        for scale in card.rating_boxes.values():
            assert set(scale.buttons) == {1, 2, 3, 4, 5}
            assert all(button.isVisible() for button in scale.buttons.values())
    assert saved == []


@pytest.mark.parametrize("dimension,note", [("track_note", 5), ("technik_note", 2), ("gesamt_note", 4)])
def test_real_note_button_saves_correct_clip_and_dimension(qtbot, dimension, note):
    dialog, saved = _dialog(qtbot)
    scale = dialog.variant_cards[0].rating_boxes[dimension]
    qtbot.mouseClick(scale.buttons[note], Qt.MouseButton.LeftButton)
    assert saved == [("/note", {"pair_id": "p1", "clip_id": "p1_c1",
                                "dimension": dimension, "note": note})]
    assert dialog.session["groups"][0]["clips"][0]["ratings"][dimension] == str(note)
    assert dialog.session["groups"][0]["clips"][1]["ratings"][dimension] == ""
    assert scale.currentIndex() == note
    qtbot.mouseClick(scale.clear_button, Qt.MouseButton.LeftButton)
    assert saved[-1][1]["note"] is None
    assert scale.currentIndex() == 0


def test_inactive_card_cannot_write_even_when_widget_forced_enabled(qtbot):
    dialog, saved = _dialog(qtbot)
    scale = dialog.variant_cards[1].rating_boxes["technik_note"]
    assert not scale.isEnabled()
    scale.setEnabled(True)
    scale.setCurrentIndex(5)
    assert saved == []
    assert dialog.session["groups"][0]["clips"][1]["ratings"]["technik_note"] == ""
    assert dialog.session["groups"][0]["clips"][0]["ratings"]["technik_note"] == ""


@pytest.mark.parametrize("read_only", [False, True])
def test_successful_render_only_unlocks_current_writable_card(qtbot, read_only):
    dialog, saved = _dialog(qtbot, session=_session(spec=True), read_only=read_only)
    assert all(not scale.isEnabled() for card in dialog.variant_cards for scale in card.rating_boxes.values())
    _ready(dialog)
    assert all(scale.isEnabled() is (not read_only) for scale in dialog.variant_cards[0].rating_boxes.values())
    assert all(not scale.isEnabled() for scale in dialog.variant_cards[1].rating_boxes.values())
    if read_only:
        scale = dialog.variant_cards[0].rating_boxes["gesamt_note"]
        scale.setEnabled(True)
        scale.setCurrentIndex(1)
        assert saved == []


def test_render_error_revokes_card_notes_and_group_choices_without_rewriting(qtbot):
    session = _session(spec=True)
    session["groups"][0]["clips"][0]["ratings"]["track_note"] = "3"
    dialog, saved = _dialog(qtbot, session=session)
    _ready(dialog)
    dialog._move_clip(1)
    _ready(dialog)
    assert dialog.variant_cards[1].best_button.isEnabled()
    worker = object()
    dialog._audio_worker = worker
    dialog._render_error("BeatSyncError", worker, dialog._render_generation)
    dialog._audio_worker = None
    scale = dialog.variant_cards[1].rating_boxes["track_note"]
    assert not scale.isEnabled()
    assert not dialog.variant_cards[1].best_button.isEnabled()
    assert not dialog.no_best_button.isEnabled()
    scale.setEnabled(True)
    scale.setCurrentIndex(1)
    dialog._choose(False)
    assert saved == []
    assert session["groups"][0]["clips"][0]["ratings"]["track_note"] == "3"


def test_navigation_restores_all_notes_without_fake_saves(qtbot):
    session = _session(groups=2)
    session["groups"][0]["clips"][0]["ratings"].update(track_note="5", technik_note="2", gesamt_note="4")
    session["groups"][0]["clips"][1]["ratings"].update(track_note="3", technik_note="4", gesamt_note="1")
    dialog, saved = _dialog(qtbot, session=session)
    dialog.next_clip_button.click()
    assert [dialog.rating_boxes[name].currentIndex() for name in DIMENSIONS] == [3, 4, 1]
    dialog.next_pair_button.click()
    dialog.previous_pair_button.click()
    assert [dialog.variant_cards[0].rating_boxes[name].currentIndex() for name in DIMENSIONS] == [5, 2, 4]
    assert [dialog.variant_cards[1].rating_boxes[name].currentIndex() for name in DIMENSIONS] == [3, 4, 1]
    assert saved == []


def test_previous_pair_card_callback_cannot_rate_new_pair(qtbot):
    dialog, saved = _dialog(qtbot, session=_session(groups=2))
    old_scale = dialog.variant_cards[0].rating_boxes["gesamt_note"]
    dialog.next_pair_button.click()
    old_scale.currentIndexChanged.emit(5)
    assert saved == []
    assert dialog.session["groups"][1]["clips"][0]["ratings"]["gesamt_note"] == ""


def test_obsolete_card_cannot_rate_when_navigation_returns_to_same_pair(qtbot):
    dialog, saved = _dialog(qtbot, session=_session(groups=2))
    old_scale = dialog.variant_cards[0].rating_boxes["track_note"]
    dialog.next_pair_button.click()
    dialog.previous_pair_button.click()
    old_scale.currentIndexChanged.emit(5)
    assert saved == []
    assert dialog.session["groups"][0]["clips"][0]["ratings"]["track_note"] == ""
    dialog.variant_cards[0].rating_boxes["track_note"].buttons[4].click()
    assert saved == [("/note", {"pair_id": "p1", "clip_id": "p1_c1",
                                "dimension": "track_note", "note": 4})]


def test_timeline_uses_clipped_preroll_and_spec_crossfade_without_source_details(qtbot):
    dialog, saved = _dialog(qtbot, session=_session(spec=True))
    timeline = dialog.variant_cards[0].timeline
    assert timeline.sections == ("A", "Anfang", "Mitte", "Ende", "B")
    assert timeline.durations == pytest.approx((3, 4, 4, 4, 5))
    assert saved == []


def test_progress_counts_complete_three_note_variants_only(qtbot):
    dialog, saved = _dialog(qtbot)
    assert "0/2" in dialog.progress_label.text()
    for dimension in DIMENSIONS[:-1]:
        dialog.variant_cards[0].rating_boxes[dimension].buttons[4].click()
    assert "0/2" in dialog.progress_label.text()
    dialog.variant_cards[0].rating_boxes["gesamt_note"].buttons[5].click()
    assert "1/2" in dialog.progress_label.text()
    dialog.variant_cards[0].rating_boxes["technik_note"].clear_button.click()
    assert "0/2" in dialog.progress_label.text()
    assert len(saved) == 4


def test_player_signals_update_active_seek_and_slider_sends_actual_milliseconds(qtbot, monkeypatch):
    dialog, saved = _dialog(qtbot, session=_session(spec=True))
    assert not dialog.variant_cards[0].position_slider.isEnabled()
    _ready(dialog)
    assert not dialog.variant_cards[0].position_slider.isEnabled()
    positions = []
    monkeypatch.setattr(dialog.player, "setPosition", positions.append)
    # Synthetische Player-Signale pruefen Verdrahtung, keine echte Decoder-Suche.
    dialog.player.durationChanged.emit(20000)
    dialog.player.positionChanged.emit(7350)
    slider = dialog.variant_cards[0].position_slider
    assert slider.maximum() == 20000
    assert slider.value() == 7350
    slider.sliderMoved.emit(12000)
    assert positions == [12000]
    dialog.variant_cards[1].position_slider.sliderMoved.emit(9000)
    assert positions == [12000]
    worker = object()
    dialog._audio_worker = worker
    dialog._render_error("BeatSyncError", worker, dialog._render_generation)
    dialog._audio_worker = None
    slider.sliderMoved.emit(15000)
    assert positions == [12000]
    assert saved == []


@pytest.mark.parametrize("enabled", [True, False], ids=["editable", "loaded-disabled"])
def test_loaded_note_selection_is_visibly_rendered_under_real_app_theme(qtbot, qapp, enabled):
    from PyQt6.QtGui import QPalette
    from hpg_core.hearing_panel import NoteScale
    from hpg_core.theme import apply_dark_theme

    old_palette = QPalette(qapp.palette())
    old_stylesheet = qapp.styleSheet()
    scale = NoteScale()
    qtbot.addWidget(scale)
    try:
        apply_dark_theme(qapp)
        scale.resize(600, 60)
        scale.setEnabled(enabled)
        for button in (*scale.buttons.values(), scale.clear_button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scale.show()
        qapp.processEvents()
        before = scale.grab().toImage()
        button_before = scale.buttons[4].grab().toImage()
        # Geladene Note setzt den Zustand ohne Mausklick oder Fokusmarkierung.
        scale.setCurrentIndex(4)
        qapp.processEvents()
        after = scale.grab().toImage()
        button_after = scale.buttons[4].grab().toImage()
        assert scale.currentIndex() == 4
        assert [note for note, button in scale.buttons.items() if button.isChecked()] == [4]
        assert button_after != button_before, "Ausgewählte Note 4 ist optisch unverändert"
        assert after != before, "Notenleiste zeigt die gespeicherte Auswahl nicht"
    finally:
        scale.close()
        qapp.setStyleSheet(old_stylesheet)
        qapp.setPalette(old_palette)

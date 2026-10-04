"""Native Bewertung muss ohne Browser speichern und fortsetzbar sein."""

import pytest


@pytest.mark.parametrize("cache", [None, ""])
def test_single_fit_dialog_accepts_absent_cache_as_true_none(qtbot, cache):
    from PyQt6.QtWidgets import QDialogButtonBox, QDialog
    from hpg_core.hearing_panel import HearingFitDialog
    dialog = HearingFitDialog(cache, single=True)
    qtbot.addWidget(dialog)
    assert dialog.cache_edit.text() == ""
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.cache is None


@pytest.mark.parametrize("single,audit_only,cache", [(False, False, ""), (False, True, ""), (True, False, "missing.db")])
def test_fit_dialog_does_not_ignore_required_or_supplied_bad_cache(qtbot, single, audit_only, cache):
    from PyQt6.QtWidgets import QDialogButtonBox, QDialog
    from hpg_core.hearing_panel import HearingFitDialog
    dialog = HearingFitDialog(cache, single=single, audit_only=audit_only)
    qtbot.addWidget(dialog)
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.error_label.text()


@pytest.mark.parametrize("mode", ["einzel", "kandidaten", "dreinoten", "dramaturgie"])
def test_native_rating_dialog_exposes_every_supported_schema(qtbot, mode):
    from hpg_core.hearing_panel import HearingRatingDialog

    dimensions = ("bewertung",) if mode == "einzel" else (
        ("note",) if mode == "kandidaten" else
        ("track_note", "technik_note", "gesamt_note")
    )
    session = {"mode": mode, "groups": [{"id": "p1", "clips": [{
        "pair_id": "p1", "clip_id": "c1", "path": None,
        "ratings": {name: "" for name in dimensions},
    }], "ratings": {name: "" for name in (
        "dramaturgie_gesamt", "energieverlauf", "peak_platzierung", "kohaerenz"
    )} if mode == "dramaturgie" else {}}]}
    saved = []
    dialog = HearingRatingDialog(session, save=lambda route, data: saved.append((route, data)))
    qtbot.addWidget(dialog)
    assert set(dialog.rating_boxes) == set(dimensions)
    dialog.rating_boxes[dimensions[0]].setCurrentIndex(4)
    assert len(saved) == 1
    route, payload = saved[0]
    assert route == ("/transition-note" if mode == "dramaturgie" else "/note")
    assert payload["note"] == 4
    if mode == "dramaturgie":
        assert set(dialog.sequence_boxes) == {
            "dramaturgie_gesamt", "energieverlauf", "peak_platzierung", "kohaerenz"
        }


def test_native_rating_dialog_failed_save_does_not_claim_saved(qtbot):
    from hpg_core.hearing_panel import HearingRatingDialog

    def fail(_route, _data):
        raise ValueError("Speicherfehler")

    session = {"mode": "einzel", "groups": [{"id": "p1", "ratings": {},
        "clips": [{"pair_id": "p1", "clip_id": "", "path": None,
                   "ratings": {"bewertung": ""}}]}]}
    dialog = HearingRatingDialog(session, save=fail)
    qtbot.addWidget(dialog)
    dialog.rating_boxes["bewertung"].setCurrentIndex(5)
    assert "Speicherfehler" in dialog.status_label.text()
    assert session["groups"][0]["clips"][0]["ratings"]["bewertung"] == ""
    assert dialog.rating_boxes["bewertung"].currentIndex() == 0


def test_native_rating_dialog_keeps_notes_when_navigating_and_clears_explicitly(qtbot):
    from hpg_core.hearing_panel import HearingRatingDialog

    session = {"mode": "kandidaten", "groups": [{"id": "p1", "ratings": {},
        "clips": [{"pair_id": "p1", "clip_id": f"c{i}", "path": None,
                   "ratings": {"note": "3"}, "gewaehlt": ""} for i in (1, 2)]}]}
    saved = []
    dialog = HearingRatingDialog(session, save=lambda route, data: saved.append((route, data)))
    qtbot.addWidget(dialog)
    assert dialog.rating_boxes["note"].currentIndex() == 3
    assert saved == []
    dialog.rating_boxes["note"].setCurrentIndex(5)
    dialog.next_clip_button.click()
    assert dialog.rating_boxes["note"].currentIndex() == 3
    dialog.previous_clip_button.click()
    assert dialog.rating_boxes["note"].currentIndex() == 5
    assert len(saved) == 1
    dialog.best_button.click()
    assert saved[-1] == ("/bester", {"pair_id": "p1", "clip_id": "c1"})
    dialog.rating_boxes["note"].setCurrentIndex(0)
    assert saved[-1][1]["note"] is None
    assert session["groups"][0]["clips"][0]["gewaehlt"] == ""


def test_native_sequence_rating_is_not_a_transition_rating(qtbot):
    from hpg_core.hearing_panel import HearingRatingDialog

    session = {"mode": "dramaturgie", "groups": [{"id": "v1", "ratings": {
        name: "" for name in ("dramaturgie_gesamt", "energieverlauf", "peak_platzierung", "kohaerenz")},
        "clips": [{"pair_id": "t1", "clip_id": "t1", "path": None,
                   "ratings": {name: "" for name in ("track_note", "technik_note", "gesamt_note")}}]}]}
    saved = []
    dialog = HearingRatingDialog(session, save=lambda route, data: saved.append((route, data)))
    qtbot.addWidget(dialog)
    dialog.sequence_boxes["energieverlauf"].setCurrentIndex(5)
    assert saved == [("/dramaturgie-note", {"variant_id": "v1", "dimension": "energieverlauf", "note": 5})]
    assert session["groups"][0]["clips"][0]["ratings"]["gesamt_note"] == ""


@pytest.mark.parametrize("index,mode,three", [(0,"einzel",False),(1,"kandidaten",False),(2,"kandidaten",True),(3,"dramaturgie",False)])
def test_prepare_form_maps_modes_and_disables_ineffective_fields(qtbot,index,mode,three):
    from hpg_core.hearing_panel import HearingPrepareDialog

    dialog = HearingPrepareDialog()
    qtbot.addWidget(dialog)
    dialog.mode_box.setCurrentIndex(index)
    values = dialog.values()
    assert values["mode"] == mode
    assert values["three_notes"] is three
    assert dialog.count_box.isEnabled() is (mode != "dramaturgie")
    assert dialog.seed_box.isEnabled() is (mode != "dramaturgie")
    assert dialog.workers_box.isEnabled() is (mode == "kandidaten")
    assert dialog.sequence_tracks_box.isEnabled() is (mode == "dramaturgie")


def test_prepare_form_exposes_all_effective_candidate_options(qtbot):
    from hpg_core.hearing_panel import HearingPrepareDialog

    dialog = HearingPrepareDialog()
    qtbot.addWidget(dialog)
    dialog.mode_box.setCurrentIndex(2)
    dialog.count_box.setValue(157)
    dialog.bpm_box.setValue(1.5)
    dialog.energy_box.setCurrentText("down")
    dialog.harmonic_box.setValue(9)
    dialog.experimental_box.setChecked(False)
    dialog.seed_box.setValue(42)
    dialog.versions_box.setValue(3)
    dialog.tracks_once_box.setChecked(True)
    dialog.profile_edit.setText("C:/selection.json")
    dialog.workers_box.setValue(4)
    dialog.transition_box.setCurrentText("produktion")
    values = dialog.values()
    assert {name: values[name] for name in (
        "count","bpm_tolerance","energy_direction","harmonic_strictness",
        "allow_experimental","seed","max_versions_per_pair","three_notes",
        "tracks_once","selection_profile","workers","transition_type_mode",
    )} == {
        "count":157,"bpm_tolerance":1.5,"energy_direction":"down","harmonic_strictness":9,
        "allow_experimental":False,"seed":42,"max_versions_per_pair":3,"three_notes":True,
        "tracks_once":True,"selection_profile":"C:/selection.json","workers":4,"transition_type_mode":"produktion",
    }


def test_native_memory_playback_retains_buffer_and_releases_on_reject(qtbot):
    import io
    import numpy as np
    import soundfile as sf
    from PyQt6.QtMultimedia import QMediaPlayer
    from hpg_core.hearing_panel import HearingRatingDialog

    session = {"mode": "einzel", "groups": [{"id": "p1", "ratings": {}, "clips": [{
        "pair_id": "p1", "clip_id": "", "path": None, "spec": {"test": True}, "ratings": {"bewertung": ""},
    }]}]}
    dialog = HearingRatingDialog(session, save=lambda *_args: None)
    qtbot.addWidget(dialog)
    data = io.BytesIO()
    sf.write(data, np.zeros((16000, 2)), 8000, format="WAV", subtype="PCM_16")
    source = object()
    dialog._audio_worker = source
    dialog._render_ready(data.getvalue(), source, dialog._render_generation)
    qtbot.waitUntil(lambda: dialog.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState, timeout=3000)
    assert dialog._audio_buffer.isOpen()
    dialog._audio_worker = None
    dialog.reject()
    assert dialog._audio_buffer is None
    assert dialog.player.sourceDevice() is None


def test_native_candidate_action_persists_csv_and_reopens_without_server(tmp_path, qtbot):
    from tests.test_hearing_preview import _set
    from hpg_core.hearing_ratings import load_session, save_rating
    from hpg_core.hearing_panel import HearingRatingDialog

    folder = _set(tmp_path)
    session = load_session(folder)
    dialog = HearingRatingDialog(session, save=lambda route, data: save_rating(folder, route, data))
    qtbot.addWidget(dialog)
    dialog.rating_boxes["note"].setCurrentIndex(4)
    dialog.best_button.click()
    dialog.reject()
    reloaded = load_session(folder)
    assert reloaded["groups"][0]["clips"][0]["clip_id"] == "p1_k2"
    assert reloaded["groups"][0]["clips"][0]["ratings"]["note"] == "4"
    assert reloaded["groups"][0]["clips"][0]["gewaehlt"] == "1"
    reopened = HearingRatingDialog(reloaded, save=lambda route, data: save_rating(folder, route, data))
    qtbot.addWidget(reopened)
    assert reopened.rating_boxes["note"].currentIndex() == 4
    reopened.rating_boxes["note"].setCurrentIndex(0)
    assert load_session(folder)["groups"][0]["clips"][0]["ratings"]["note"] == ""
    assert load_session(folder)["groups"][0]["clips"][0]["gewaehlt"] == ""


def test_navigation_away_and_back_rejects_stale_render(qtbot):
    from hpg_core.hearing_panel import HearingRatingDialog

    session = {"mode": "einzel", "groups": [{"id": "p1", "ratings": {}, "clips": [{
        "pair_id": "p1", "clip_id": "", "path": None, "ratings": {"bewertung": ""},
    }]}]}
    dialog = HearingRatingDialog(session, save=lambda *_args: None)
    qtbot.addWidget(dialog)
    class CancelledWorker:
        def request_cancel(self):
            pass
    source = CancelledWorker()
    dialog._audio_worker = source
    token = dialog._render_generation
    dialog._show_clip()
    dialog.status_label.setText("Neuer Zustand")
    dialog._render_ready(b"stale", source, token)
    dialog._render_error("stale", source, token)
    assert dialog._audio_buffer is None
    assert dialog.status_label.text() == "Neuer Zustand"
    dialog._audio_worker = None


def test_rating_refresh_does_not_reset_sequence_media(qtbot):
    from hpg_core.hearing_panel import HearingRatingDialog

    session = {"mode": "dramaturgie", "groups": [{"id": "v1", "ratings": {}, "clips": [{
        "pair_id": "t1", "clip_id": "t1", "path": None,
        "ratings": {name: "" for name in ("track_note", "technik_note", "gesamt_note")},
    }]}]}
    dialog = HearingRatingDialog(session, save=lambda *_args: None)
    qtbot.addWidget(dialog)
    dialog._sequence_playing = True
    generation = dialog._render_generation
    dialog.sequence_boxes["energieverlauf"].setCurrentIndex(4)
    assert dialog._render_generation == generation
    assert dialog._sequence_playing


def test_native_spec_rating_requires_current_successful_render(qtbot):
    import io
    import numpy as np
    import soundfile as sf
    from hpg_core.hearing_panel import HearingRatingDialog

    session = {"mode": "kandidaten", "groups": [{"id": "p1", "ratings": {}, "clips": [
        {"pair_id": "p1", "clip_id": f"c{i}", "path": None,
         "spec": {"test": i}, "ratings": {"note": ""}, "gewaehlt": ""}
        for i in (1, 2)
    ]}]}
    saved = []
    dialog = HearingRatingDialog(session, save=lambda route, data: saved.append((route, data)))
    qtbot.addWidget(dialog)
    assert not dialog.rating_boxes["note"].isEnabled()
    assert not dialog.best_button.isEnabled()
    assert not dialog.no_best_button.isEnabled()
    dialog.rating_boxes["note"].setEnabled(True)
    dialog.rating_boxes["note"].setCurrentIndex(5)
    assert dialog.rating_boxes["note"].currentIndex() == 0
    assert not dialog.rating_boxes["note"].isEnabled()
    dialog._rate("note", 5)
    dialog._choose(True)
    dialog._choose(False)
    assert saved == []

    data = io.BytesIO()
    sf.write(data, np.zeros((16000, 2)), 8000, format="WAV", subtype="PCM_16")
    worker = object()
    dialog._audio_worker = worker
    token = dialog._render_generation
    dialog._render_ready(data.getvalue(), worker, token)
    assert dialog.rating_boxes["note"].isEnabled()
    dialog._rate("note", 4)
    assert saved == [("/note", {"pair_id": "p1", "clip_id": "c1", "dimension": "note", "note": 4})]
    dialog._audio_worker = None
    dialog._move_clip(1)
    assert not dialog.rating_boxes["note"].isEnabled()
    dialog._render_ready(data.getvalue(), worker, token)
    assert not dialog.rating_boxes["note"].isEnabled()
    dialog._rate("note", 5)
    dialog._choose(False)
    assert len(saved) == 1
    dialog._move_clip(-1)
    assert not dialog.rating_boxes["note"].isEnabled()
    assert not dialog.no_best_button.isEnabled()
    dialog._rate("note", 5)
    assert len(saved) == 1


def test_native_spec_render_error_never_writes_negative_rating(qtbot):
    from hpg_core.hearing_panel import HearingRatingDialog

    session = {"mode": "kandidaten", "groups": [{"id": "p1", "ratings": {}, "clips": [{
        "pair_id": "p1", "clip_id": "c1", "path": None, "spec": {"test": True},
        "ratings": {"note": "3"}, "gewaehlt": "",
    }]}]}
    saved = []
    dialog = HearingRatingDialog(session, save=lambda route, data: saved.append((route, data)))
    qtbot.addWidget(dialog)
    worker = object()
    dialog._audio_worker = worker
    token = dialog._render_generation
    dialog._render_error("BeatSyncError", worker, token - 1)
    assert "BeatSyncError" not in dialog.status_label.text()
    dialog._render_error("BeatSyncError", worker, token)
    assert "BeatSyncError" in dialog.status_label.text()
    assert not dialog.best_button.isEnabled()
    assert not dialog.no_best_button.isEnabled()
    dialog._rate("note", 1)
    dialog._choose(True)
    dialog._choose(False)
    assert saved == []
    assert session["groups"][0]["clips"][0]["ratings"]["note"] == "3"
    dialog._audio_worker = None


def test_read_only_rating_stays_locked_after_successful_render(qtbot):
    import io
    import numpy as np
    import soundfile as sf
    from hpg_core.hearing_panel import HearingRatingDialog

    session = {"mode": "kandidaten", "groups": [{"id": "p1", "ratings": {}, "clips": [{
        "pair_id": "p1", "clip_id": "c1", "path": None, "spec": {"test": True},
        "ratings": {"note": "3"}, "gewaehlt": "",
    }]}]}
    saved = []
    dialog = HearingRatingDialog(session, save=lambda route, data: saved.append((route, data)), read_only=True)
    qtbot.addWidget(dialog)
    data = io.BytesIO()
    sf.write(data, np.zeros((16000, 2)), 8000, format="WAV", subtype="PCM_16")
    source = object()
    dialog._audio_worker = source
    dialog._render_ready(data.getvalue(), source, dialog._render_generation)
    assert not dialog.rating_boxes["note"].isEnabled()
    assert not dialog.best_button.isEnabled()
    assert not dialog.no_best_button.isEnabled()
    dialog._rate("note", 5)
    dialog._choose(True)
    dialog._choose(False)
    assert saved == []
    assert session["groups"][0]["clips"][0]["ratings"]["note"] == "3"
    dialog._audio_worker = None


def test_spec_path_cannot_bypass_ram_render(qtbot, monkeypatch):
    from hpg_core.hearing_panel import HearingRatingDialog

    session = {"mode": "einzel", "groups": [{"id": "p1", "ratings": {}, "clips": [{
        "pair_id": "p1", "clip_id": "c1", "path": "C:/existing.wav",
        "spec": {"test": True}, "ratings": {"bewertung": ""},
    }]}]}
    dialog = HearingRatingDialog(session, save=lambda *_args: None)
    qtbot.addWidget(dialog)
    called = []
    monkeypatch.setattr(dialog, "_start_render", lambda: called.append(True))
    assert dialog.player.source().isEmpty()
    assert not dialog.rating_boxes["bewertung"].isEnabled()
    dialog._toggle_playback()
    assert called == [True]


def test_group_best_choice_requires_all_rendered_and_error_revokes_it(qtbot):
    import io
    import numpy as np
    import soundfile as sf
    from hpg_core.hearing_panel import HearingRatingDialog

    session = {"mode": "kandidaten", "groups": [{"id": "p1", "ratings": {}, "clips": [
        {"pair_id": "p1", "clip_id": f"c{i}", "path": None,
         "spec": {"test": i}, "ratings": {"note": "3"}, "gewaehlt": ""}
        for i in (1, 2)
    ]}]}
    saved = []
    dialog = HearingRatingDialog(session, save=lambda route, data: saved.append((route, data)))
    qtbot.addWidget(dialog)
    data = io.BytesIO()
    sf.write(data, np.zeros((16000, 2)), 8000, format="WAV", subtype="PCM_16")
    worker = object()
    dialog._audio_worker = worker
    dialog._render_ready(data.getvalue(), worker, dialog._render_generation)
    assert dialog.rating_boxes["note"].isEnabled()
    assert not dialog.best_button.isEnabled()
    assert not dialog.no_best_button.isEnabled()
    dialog._choose(True)
    assert saved == []

    dialog._audio_worker = None
    dialog._move_clip(1)
    worker = object()
    dialog._audio_worker = worker
    dialog._render_ready(data.getvalue(), worker, dialog._render_generation)
    assert dialog.best_button.isEnabled()
    assert dialog.no_best_button.isEnabled()
    dialog._choose(True)
    assert saved == [("/bester", {"pair_id": "p1", "clip_id": "c2"})]
    dialog._render_error("BeatSyncError", worker, dialog._render_generation)
    assert not dialog.rating_boxes["note"].isEnabled()
    assert not dialog.best_button.isEnabled()
    assert not dialog.no_best_button.isEnabled()
    dialog._rate("note", 1)
    dialog._choose(False)
    assert len(saved) == 1
    assert session["groups"][0]["clips"][1]["ratings"]["note"] == "3"
    dialog._audio_worker = None

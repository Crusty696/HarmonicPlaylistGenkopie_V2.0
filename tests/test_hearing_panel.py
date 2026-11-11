"""Native Bewertung muss ohne Browser speichern und fortsetzbar sein."""

import json

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


def test_blind_prepare_form_maps_portable_copy_and_csv_key(qtbot, tmp_path):
    from PyQt6.QtWidgets import QDialog
    from hpg_core.hearing_panel import HearingBlindPrepareDialog

    dialog = HearingBlindPrepareDialog()
    qtbot.addWidget(dialog)
    dialog.delivery_box.setCurrentIndex(1)
    paths = {
        "manifest": tmp_path / "manifest.csv",
        "output_dir": tmp_path / "session",
        "key_path": tmp_path / "private" / "key.csv",
        "source_root": tmp_path,
    }
    for name, path in paths.items():
        dialog.edits[name].setText(str(path))

    dialog._accept_config()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.config == {**paths, "seed": None, "delivery_mode": "portable_copy"}
    assert "neutralen WAV-Namen" in dialog.notice.text()
    assert "Originaltracks" in dialog.notice.text()


def test_blind_prepare_form_rejects_wrong_key_extension(qtbot, tmp_path):
    from PyQt6.QtWidgets import QDialog
    from hpg_core.hearing_panel import HearingBlindPrepareDialog

    dialog = HearingBlindPrepareDialog()
    qtbot.addWidget(dialog)
    paths = {
        "manifest": tmp_path / "manifest.csv",
        "output_dir": tmp_path / "session",
        "key_path": tmp_path / "private" / "key.json",
        "source_root": tmp_path,
    }
    for name, path in paths.items():
        dialog.edits[name].setText(str(path))
    dialog.delivery_box.setCurrentIndex(1)

    dialog._accept_config()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert ".csv" in dialog.error_label.text()


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
    assert dialog.bpm_box.isEnabled()
    assert dialog.energy_box.isEnabled() is (mode != "dramaturgie")
    assert dialog.genre_box.isEnabled() is (mode != "dramaturgie")
    for widget in (dialog.harmonic_box, dialog.experimental_box, dialog.versions_box,
                   dialog.tracks_once_box, dialog.profile_edit, dialog.profile_browse, dialog.workers_box,
                   dialog.transition_box):
        assert widget.isEnabled() is (mode == "kandidaten")
    assert dialog.sequence_tracks_box.isEnabled() is (mode == "dramaturgie")
    assert dialog.transitions_box.isEnabled() is (mode == "dramaturgie")


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


@pytest.mark.parametrize("index,mode", [
    (0, "einzel"), (1, "kandidaten"), (2, "kandidaten"), (3, "dramaturgie"),
])
def test_prepare_form_config_and_producer_namespace_parity(qtbot, monkeypatch, tmp_path, index, mode):
    import json
    from hpg_core.hearing_panel import HearingPrepareDialog
    from hpg_core.hearing_sources import SourceRenderSink
    from hpg_core.hearing_workflow import CancellationToken, _producer_namespace
    from tools import rate_transitions as rate

    source_root = tmp_path / "originals"
    source_root.mkdir()
    profile = tmp_path / "selection.json"
    profile.write_text(json.dumps({
        "purpose": "selection_only", "product_weights_changed": False,
        "features": ["groove"], "feature_mean": {"groove": 0.5},
        "feature_std": {"groove": 0.2},
        "models": {name: {"intercept": 0.0, "coefficients": {"groove": 1.0}}
                   for name in ("track_note", "technik_note", "gesamt_note")},
        "excluded_undirected_pairs": [], "historical_track_counts": {"old-track.wav": 2},
    }), encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    dialog = HearingPrepareDialog(folder=str(source_root))
    qtbot.addWidget(dialog)
    dialog.mode_box.setCurrentIndex(index)
    dialog.count_box.setValue(12)
    dialog.bpm_box.setValue(1.5)
    dialog.energy_box.setCurrentText("down")
    dialog.seed_box.setValue(31)
    dialog.genre_box.setCurrentText("Techno")
    dialog.harmonic_box.setValue(9)
    dialog.experimental_box.setChecked(False)
    dialog.versions_box.setValue(3)
    dialog.tracks_once_box.setChecked(True)
    dialog.profile_edit.setText(str(profile))
    dialog.workers_box.setValue(4)
    dialog.transition_box.setCurrentText("produktion")
    dialog.sequence_tracks_box.setValue(18)
    dialog.transitions_box.setValue(6)
    dialog._accept_config()

    config = dialog.config
    assert config.mode == mode
    assert config.source_roots == (source_root.resolve(),)
    assert config.bpm_tolerance == 1.5
    stage = tmp_path / "staging"
    stage.mkdir()
    sink = SourceRenderSink(stage, config.source_roots)
    args = _producer_namespace(config, stage, config.output_dir, sink,
                               CancellationToken(), None)
    assert args.modus == mode
    assert args.anzahl == (100 if mode == "dramaturgie" else 12)
    assert args.bpm_toleranz == 1.5
    assert args.energy_direction == ("down" if mode != "dramaturgie" else None)
    assert args.nur_genre == ("Techno" if mode != "dramaturgie" else None)
    assert args.seed == (rate.STANDARD_SEED if mode == "dramaturgie" else 31)
    assert args.harmonic_strictness == (9 if mode == "kandidaten" else 7)
    assert args.allow_experimental is (False if mode == "kandidaten" else True)
    assert args.max_versionen_pro_paar == (3 if mode == "kandidaten" else rate.STANDARD_MAX_VERSIONEN_PRO_PAAR)
    assert args.dreinoten_pilot is (index == 2)
    assert args.tracks_einmalig is (mode == "kandidaten")
    assert args.auswahlprofil == (profile if mode == "kandidaten" else None)
    assert args.workers == (4 if mode == "kandidaten" else 1)
    assert args.transition_type_mode == ("produktion" if mode == "kandidaten" else "kontrolliert")
    assert args.sequenz_tracks == (18 if mode == "dramaturgie" else rate.STANDARD_SEQUENZ_TRACKS)
    assert args.uebergaenge_pro_variante == (
        6 if mode == "dramaturgie" else rate.STANDARD_UEBERGAENGE_PRO_VARIANTE
    )
    if mode == "einzel":
        assert config.only_genre == "Techno"
    elif mode == "kandidaten":
        assert config.only_genre == "Techno"
        candidate = {
            "track_a": type("TrackRef", (), {"filePath": str(tmp_path / "a.wav")})(),
            "track_b": type("TrackRef", (), {"filePath": str(tmp_path / "b.wav")})(),
            "merkmale": {"groove": 0.7},
        }
        ranked, selected = rate.wende_auswahlprofil_an([candidate], profile)
        assert len(ranked) == 1 and selected == 0
        assert ranked[0]["historische_prognose"] == pytest.approx(1.0)
    else:
        assert config.only_genre is None


def test_prepare_form_selection_profile_file_picker(qtbot, monkeypatch, tmp_path):
    from PyQt6.QtWidgets import QFileDialog
    from hpg_core.hearing_panel import HearingPrepareDialog

    profile = tmp_path / "selection.json"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(profile), "JSON (*.json)"))
    dialog = HearingPrepareDialog()
    qtbot.addWidget(dialog)
    dialog.mode_box.setCurrentIndex(1)
    dialog.profile_browse.click()
    assert dialog.profile_edit.text() == str(profile)


@pytest.mark.parametrize("payload", [
    "not JSON",
    "{}",
    json.dumps({"purpose": "ranking", "product_weights_changed": False}),
    json.dumps({
        "purpose": "selection_only", "product_weights_changed": False,
        "features": ["unknown"], "feature_mean": {"unknown": 0.0},
        "feature_std": {"unknown": 1.0},
        "models": {name: {"intercept": 0.0, "coefficients": {"unknown": 1.0}}
                   for name in ("track_note", "technik_note", "gesamt_note")},
        "excluded_undirected_pairs": [], "historical_track_counts": [],
    }),
])
def test_prepare_form_rejects_bad_selection_profile_before_config_or_worker(qtbot, monkeypatch, tmp_path, payload):
    from hpg_core import hearing_managed
    from hpg_core.hearing_panel import HearingPrepareDialog

    source_root = tmp_path / "originals"
    source_root.mkdir()
    profile = tmp_path / "selection.json"
    profile.write_text(payload, encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(
        hearing_managed, "managed_config",
        lambda *_args, **_kwargs: pytest.fail("Ungültiges Profil darf nicht bis zur Konfiguration gelangen"),
    )
    dialog = HearingPrepareDialog(folder=str(source_root))
    qtbot.addWidget(dialog)
    dialog.mode_box.setCurrentIndex(1)
    dialog.profile_edit.setText(str(profile))
    dialog._accept_config()
    assert dialog.result() != 1
    assert not hasattr(dialog, "config")
    assert dialog.error_label.text()


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

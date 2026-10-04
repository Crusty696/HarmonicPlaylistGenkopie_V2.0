"""Lesender Kandidaten-Hoertest in der App."""

import csv
import json
import wave

import pytest
from PyQt6.QtCore import QTimer

import main
from hpg_core.hearing_preview import HearingPreviewDialog, load_candidate_preview


def _set(tmp_path, *, order=None, second_clip="clips/p1_k2.wav"):
    folder = tmp_path / "set"
    clips = folder / "clips"
    clips.mkdir(parents=True)
    for name in ("p1_k1.wav", "p1_k2.wav"):
        with wave.open(str(clips / name), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(44100)
            handle.writeframes(b"\0" * (44100 * 2 * 2))
    with (folder / "bewertung.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("pair_id", "clip_id", "note", "gewaehlt", "zeit"))
        writer.writeheader()
        writer.writerows([
            {"pair_id": "p1", "clip_id": "p1_k1", "note": "", "gewaehlt": "", "zeit": ""},
            {"pair_id": "p1", "clip_id": "p1_k2", "note": "", "gewaehlt": "", "zeit": ""},
        ])
    with (folder / "merkmale.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("pair_id", "clip_id", "clip", "score"))
        writer.writeheader()
        writer.writerows([
            {"pair_id": "p1", "clip_id": "p1_k1", "clip": "clips/p1_k1.wav", "score": "99"},
            {"pair_id": "p1", "clip_id": "p1_k2", "clip": second_clip, "score": "1"},
        ])
    (folder / "reihenfolge.json").write_text(json.dumps(order or {
        "p1": {"seed": 42, "clips": ["p1_k2", "p1_k1"]}
    }), encoding="utf-8")
    return folder


def test_preview_follows_blinded_order_without_exposing_scores(tmp_path):
    folder = _set(tmp_path)
    pairs = load_candidate_preview(folder)
    assert len(pairs) == 1
    assert [path.name for path in pairs[0]] == ["p1_k2.wav", "p1_k1.wav"]
    assert all(path.is_file() for path in pairs[0])


@pytest.mark.parametrize("second_clip", ["../outside.wav", "clips/p1_k1.wav", "clips/p1_k2.mp3"])
def test_preview_rejects_wrong_or_unsafe_clip_binding(tmp_path, second_clip):
    folder = _set(tmp_path, second_clip=second_clip)
    with pytest.raises(ValueError):
        load_candidate_preview(folder)


def test_preview_rejects_incomplete_blinded_order(tmp_path):
    folder = _set(tmp_path, order={"p1": {"seed": 42, "clips": ["p1_k1"]}})
    with pytest.raises(ValueError):
        load_candidate_preview(folder)


def test_preview_rejects_malformed_blinded_order(tmp_path):
    folder = _set(tmp_path, order={"p1": {"seed": 42, "clips": [{"id": "p1_k1"}, "p1_k2"]}})
    with pytest.raises(ValueError):
        load_candidate_preview(folder)


def test_preview_rejects_clips_directory_link_outside_set(tmp_path):
    folder = _set(tmp_path)
    external = tmp_path / "outside"
    (folder / "clips").rename(external)
    try:
        (folder / "clips").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Verzeichnis-Symlinks auf diesem System nicht erlaubt")
    with pytest.raises(ValueError):
        load_candidate_preview(folder)


@pytest.mark.parametrize("name", ["bewertung.csv", "merkmale.csv", "reihenfolge.json"])
def test_preview_rejects_metadata_link_outside_set(tmp_path, name):
    folder = _set(tmp_path)
    source = folder / name
    external = tmp_path / name
    source.rename(external)
    try:
        source.symlink_to(external)
    except OSError:
        pytest.skip("Datei-Symlinks auf diesem System nicht erlaubt")

    with pytest.raises(ValueError, match="Metadaten"):
        load_candidate_preview(folder)


def test_native_dialog_uses_neutral_labels_and_stops_player(tmp_path, qtbot):
    folder = _set(tmp_path)
    dialog = HearingPreviewDialog(load_candidate_preview(folder))
    qtbot.addWidget(dialog)
    assert dialog.pair_label.text() == "Paar 1/1"
    assert dialog.clip_label.text() == "Variante 1/2"
    assert dialog.player.source().toLocalFile().endswith("p1_k2.wav")
    dialog.next_clip_button.click()
    assert dialog.clip_label.text() == "Variante 2/2"
    assert dialog.player.source().toLocalFile().endswith("p1_k1.wav")
    dialog.close()
    assert dialog.player.source().isEmpty()


def test_native_dialog_reject_releases_audio_source(tmp_path, qtbot):
    folder = _set(tmp_path)
    dialog = HearingPreviewDialog(load_candidate_preview(folder))
    qtbot.addWidget(dialog)
    dialog.show()
    assert not dialog.player.source().isEmpty()
    dialog.reject()
    assert dialog.player.source().isEmpty()


def test_native_dialog_play_button_starts_valid_wav(tmp_path, qtbot):
    folder = _set(tmp_path)
    dialog = HearingPreviewDialog(load_candidate_preview(folder))
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.play_button.click()
    qtbot.waitUntil(
        lambda: dialog.player.playbackState() == main.QMediaPlayer.PlaybackState.PlayingState,
        timeout=3000,
    )
    dialog.reject()


def test_quality_panel_opens_existing_preview_without_server(tmp_path, qtbot, monkeypatch):
    folder = _set(tmp_path)
    monkeypatch.setattr(main.MainWindow, "check_dependencies_and_warn", lambda _self: None)
    window = main.MainWindow()
    qtbot.addWidget(window)
    window._hearing_set_path = str(folder)
    window._update_hearing_buttons()
    if hasattr(window.analytics_panel, "hearing_preview_button"):
        QTimer.singleShot(0, lambda: next(
            widget for widget in window.findChildren(HearingPreviewDialog)
        ).close())
    window.analytics_panel.hearing_preview_button.click()
    assert window._hearing_process is None
    assert "keine Audit-Prüfung" in window.analytics_panel.hearing_status.text()

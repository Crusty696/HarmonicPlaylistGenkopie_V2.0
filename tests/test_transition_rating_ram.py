"""Direkte Vorschau-Bewertung darf keine Audiodatei erzeugen."""

from types import SimpleNamespace
from unittest.mock import Mock


def test_main_passes_preview_bytes_to_rating_without_temporary_audio(monkeypatch, tmp_path):
    import main
    from hpg_core import hearing_panel
    from hpg_core.transition_renderer import TransitionClipSpec

    source_a, source_b = tmp_path / "a.wav", tmp_path / "b.wav"
    source_a.write_bytes(b"Quellidentitaet A")
    source_b.write_bytes(b"Quellidentitaet B")
    track_a = SimpleNamespace(filePath=str(source_a), fileName="a.wav", bpm=120.)
    track_b = SimpleNamespace(filePath=str(source_b), fileName="b.wav", bpm=120.)
    transition = SimpleNamespace(from_track=track_a, to_track=track_b, plan=None)
    spec = TransitionClipSpec(track_a_path=str(source_a), track_b_path=str(source_b),
                              mix_out_sec=60., mix_in_sec=30., crossfade_sec=16.)
    monkeypatch.setattr(main.TransitionClipSpec, "from_plan", lambda *_: spec)
    monkeypatch.setattr(main.QStandardPaths, "writableLocation", lambda *_: str(tmp_path))
    monkeypatch.setattr(main.tempfile, "mkstemp",
                        Mock(side_effect=AssertionError("Keine temporaere Audiodatei")))
    captured = []
    released = []

    class Dialog:
        def __init__(self, session, **kwargs):
            captured.append(session)

        def setWindowTitle(self, title):
            pass

        def exec(self):
            pass

        def deleteLater(self):
            released.append(self)

    monkeypatch.setattr(hearing_panel, "HearingRatingDialog", Dialog)
    window = SimpleNamespace(
        _close_pending=False, _hearing_native_active=False, _hearing_worker=None,
        _hearing_process=None, playlist_panel=SimpleNamespace(scoring_context={}),
        _update_hearing_buttons=Mock())
    audio = b"RAM-Vorschau"

    main.MainWindow._rate_transition_preview(window, transition, (None, audio))

    clip = captured[0]["groups"][0]["clips"][0]
    assert clip["audio_bytes"] == audio
    assert clip["path"] is None
    assert not window._hearing_native_active
    assert len(released) == 1
    main.tempfile.mkstemp.assert_not_called()


def test_rating_dialog_keeps_preview_in_ram_and_blocks_rating_after_player_error(qtbot, monkeypatch):
    from PyQt6.QtMultimedia import QMediaPlayer
    from hpg_core.hearing_panel import HearingRatingDialog

    # Qt-Lebenszyklus real; Codec und Ausgabe sind fuer diesen Vertrag irrelevant.
    monkeypatch.setattr(QMediaPlayer, "setSourceDevice", lambda *_: None)
    monkeypatch.setattr(HearingRatingDialog, "_start_render",
                        Mock(side_effect=AssertionError("Fertige Vorschau nicht erneut rendern")))
    audio = b"Bereits gerenderte RAM-Vorschau"
    session = {"mode": "einzel", "groups": [{"id": "p1", "ratings": {}, "clips": [{
        "pair_id": "p1", "clip_id": "c1", "path": None, "audio_bytes": audio,
        "ratings": {"bewertung": ""}, "gewaehlt": "",
    }]}]}
    saved = []
    dialog = HearingRatingDialog(session, save=lambda *args: saved.append(args))
    qtbot.addWidget(dialog)
    assert bytes(dialog._audio_buffer.data()) == audio
    assert dialog.play_button.isEnabled()
    assert dialog._rating_allowed()
    dialog.rating_boxes["bewertung"].setCurrentIndex(4)
    assert saved == [("/note", {"pair_id": "p1", "note": 4})]

    dialog._playback_error(QMediaPlayer.Error.FormatError, "kontrollierter Decoderfehler")

    assert dialog._audio_buffer is None
    assert not dialog._rating_allowed()
    assert not dialog.rating_boxes["bewertung"].isEnabled()
    dialog.close()

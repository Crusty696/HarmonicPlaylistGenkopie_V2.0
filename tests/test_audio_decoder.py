"""Vertrag fuer den gebuendelten FFmpeg-Pfad von Audioread."""
from types import SimpleNamespace
import sys

from hpg_core import audio_decoder


def test_packed_ffmpeg_is_first_audioread_command(monkeypatch, tmp_path):
    import audioread.ffdec

    executable = tmp_path / 'ffmpeg.exe'
    executable.write_bytes(b'fake executable path')
    monkeypatch.setitem(sys.modules, 'imageio_ffmpeg', SimpleNamespace(
        get_ffmpeg_exe=lambda: str(executable)))
    monkeypatch.setattr(audioread.ffdec, 'COMMANDS', ('ffmpeg', 'avconv'))
    monkeypatch.setattr(audio_decoder, '_CONFIGURED', False)

    assert audio_decoder.configure_audioread_ffmpeg()
    assert audioread.ffdec.COMMANDS == (str(executable), 'ffmpeg', 'avconv')

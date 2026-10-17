"""Gemeinsame FFmpeg-Auswahl fuer Audioread-Formate ohne libsndfile."""
from __future__ import annotations

import threading
from pathlib import Path


_LOCK = threading.Lock()
_CONFIGURED = False


def configure_audioread_ffmpeg() -> bool:
    """Bevorzuge das gepackte HPG-FFmpeg; ohne Paket bleibt PATH-Fallback."""
    global _CONFIGURED
    if _CONFIGURED:
        return True
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        import audioread.ffdec
        executable = str(get_ffmpeg_exe())
        if not Path(executable).is_file():
            return False
    except (ImportError, RuntimeError, OSError):
        return False
    with _LOCK:
        if not _CONFIGURED:
            # audioread liest COMMANDS synchron beim Erzeugen des Decoders.
            # Der absolute Paketpfad funktioniert auch bei bereinigter PATH.
            audioread.ffdec.COMMANDS = (executable, 'ffmpeg', 'avconv')
            _CONFIGURED = True
    return True

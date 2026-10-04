"""Lesende native Vorschau vorhandener Kandidaten-Hoertests."""

import json
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from tools.hoertest_server import (
    BEWERTUNG_KANDIDATEN_SPALTEN,
    bewertungsschema,
    lies_csv,
    sichere_clip_datei,
)


class HearingPreviewDialog(QDialog):
    """Spielt nur bereits vorhandene Clips; bewertet und speichert nichts."""

    def __init__(self, pairs, parent=None):
        super().__init__(parent)
        if not pairs or any(not clips for clips in pairs):
            raise ValueError("Keine Hoerclips vorhanden")
        self.pairs = pairs
        self.pair_index = 0
        self.clip_index = 0
        self.setWindowTitle("Hörtest in der App – nur anhören")
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.finished.connect(self._stop_player)

        layout = QVBoxLayout(self)
        self.pair_label = QLabel()
        self.clip_label = QLabel()
        layout.addWidget(QLabel("Höransicht, keine Audit-Prüfung. Bewertungen im Browser."))
        layout.addWidget(self.pair_label)
        layout.addWidget(self.clip_label)
        clip_row = QHBoxLayout()
        self.previous_clip_button = QPushButton("Vorherige Variante")
        self.play_button = QPushButton("Abspielen / Pause")
        self.next_clip_button = QPushButton("Nächste Variante")
        for button in (self.previous_clip_button, self.play_button, self.next_clip_button):
            clip_row.addWidget(button)
        layout.addLayout(clip_row)
        pair_row = QHBoxLayout()
        self.previous_pair_button = QPushButton("Vorheriges Paar")
        self.next_pair_button = QPushButton("Nächstes Paar")
        pair_row.addWidget(self.previous_pair_button)
        pair_row.addWidget(self.next_pair_button)
        layout.addLayout(pair_row)

        self.previous_clip_button.clicked.connect(lambda: self._move_clip(-1))
        self.next_clip_button.clicked.connect(lambda: self._move_clip(1))
        self.previous_pair_button.clicked.connect(lambda: self._move_pair(-1))
        self.next_pair_button.clicked.connect(lambda: self._move_pair(1))
        self.play_button.clicked.connect(self._toggle_playback)
        self._show_clip()

    def _show_clip(self):
        self.player.stop()
        path = self.pairs[self.pair_index][self.clip_index]
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.pair_label.setText(f"Paar {self.pair_index + 1}/{len(self.pairs)}")
        self.clip_label.setText(
            f"Variante {self.clip_index + 1}/{len(self.pairs[self.pair_index])}"
        )

    def _move_clip(self, step):
        count = len(self.pairs[self.pair_index])
        self.clip_index = (self.clip_index + step) % count
        self._show_clip()

    def _move_pair(self, step):
        self.pair_index = (self.pair_index + step) % len(self.pairs)
        self.clip_index = 0
        self._show_clip()

    def _toggle_playback(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _stop_player(self, _result=None):
        self.player.stop()
        self.player.setSource(QUrl())

    def closeEvent(self, event):
        self._stop_player()
        super().closeEvent(event)


def load_candidate_preview(folder):
    """Liefert WAV-Pfade je Paar in der gespeicherten blinden Reihenfolge."""
    root = Path(folder)
    resolved_root = root.resolve(strict=True)
    clips_root = (root / "clips").resolve()
    if resolved_root not in clips_root.parents:
        raise ValueError("Clip-Ordner liegt ausserhalb des Satzes")
    ratings_path = root / "bewertung.csv"
    features_path = root / "merkmale.csv"
    order_path = root / "reihenfolge.json"
    for metadata_path in (ratings_path, features_path, order_path):
        if metadata_path.resolve(strict=True).parent != resolved_root:
            raise ValueError("Metadaten-Datei liegt ausserhalb des Satzes")
    if bewertungsschema(ratings_path) != BEWERTUNG_KANDIDATEN_SPALTEN:
        raise ValueError("Kein Kandidatensatz mit erwarteter Bewertungsspaltenfolge")
    ratings = lies_csv(ratings_path)
    features = lies_csv(features_path)
    if not ratings or not features:
        raise ValueError("Kandidatensatz ist leer")
    if any(None in row for row in ratings + features):
        raise ValueError("CSV enthaelt ueberzaehlige Spalten")
    if any(not {"pair_id", "clip_id", "clip"} <= set(row) for row in features):
        raise ValueError("Merkmale-Spalten fehlen")

    by_pair = {}
    by_id = {}
    for row in ratings:
        pair_id = str(row.get("pair_id") or "").strip()
        clip_id = str(row.get("clip_id") or "").strip()
        if not pair_id or not clip_id or clip_id in by_id:
            raise ValueError("Paar- oder Clip-ID fehlt oder ist doppelt")
        by_id[clip_id] = pair_id
        by_pair.setdefault(pair_id, []).append(clip_id)

    paths = {}
    for row in features:
        clip_id = str(row.get("clip_id") or "").strip()
        pair_id = str(row.get("pair_id") or "").strip()
        if clip_id not in by_id or by_id[clip_id] != pair_id or clip_id in paths:
            raise ValueError("Merkmale passen nicht zur Bewertung")
        rel = row.get("clip")
        if rel != f"clips/{clip_id}.wav":
            raise ValueError("Clip-Pfad passt nicht zur ID")
        path = sichere_clip_datei(clips_root, f"{clip_id}.wav")
        if not path.is_file():
            raise ValueError("Clip-Datei fehlt")
        paths[clip_id] = path
    if set(paths) != set(by_id):
        raise ValueError("Clips fehlen in den Merkmalen")

    try:
        order = json.loads(order_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Blinde Reihenfolge ist nicht lesbar") from exc
    if not isinstance(order, dict) or set(order) != set(by_pair):
        raise ValueError("Blinde Reihenfolge passt nicht zu den Paaren")
    result = []
    for pair_id, ids in by_pair.items():
        item = order[pair_id]
        ordered = item.get("clips") if isinstance(item, dict) else None
        if (
            not isinstance(ordered, list)
            or len(ordered) != len(ids)
            or any(not isinstance(clip_id, str) for clip_id in ordered)
            or set(ordered) != set(ids)
        ):
            raise ValueError("Blinde Clip-Reihenfolge ist unvollstaendig")
        result.append([paths[clip_id] for clip_id in ordered])
    return result

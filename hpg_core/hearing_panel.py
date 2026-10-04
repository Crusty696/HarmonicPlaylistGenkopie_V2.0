"""Native, verdeckte Hoertest-Bewertung ohne Browser-Abhaengigkeit."""

import csv
from pathlib import Path

from PyQt6.QtCore import QBuffer, QIODevice, QUrl
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QVBoxLayout, QPlainTextEdit, QWidget, QScrollArea,
    QTableWidget, QTableWidgetItem, QAbstractItemView,
)


NOTE_LABELS = {
    "bewertung": "Gesamtnote", "note": "Gesamtnote",
    "track_note": "Track-Passung", "technik_note": "Übergangstechnik",
    "gesamt_note": "Gesamtwirkung", "dramaturgie_gesamt": "Dramaturgie gesamt",
    "energieverlauf": "Energieverlauf", "peak_platzierung": "Peak-Platzierung",
    "kohaerenz": "Kohärenz",
}


class HearingPrepareDialog(QDialog):
    """Alle fachlich wirksamen Producer-Optionen ohne CLI-Eingabe."""

    def __init__(self, parent=None, *, folder=""):
        super().__init__(parent)
        from tools import rate_transitions as rate
        from hpg_core.genres import CANONICAL_GENRES

        self.setWindowTitle("Hörtest vorbereiten – Originaldateien nur lesen")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.mode_box = QComboBox()
        self.mode_box.addItems(["Einzel", "Kandidaten", "Dreinoten-Pilot", "Dramaturgie"])
        self.cache_edit = QLineEdit()
        self.output_edit = QLineEdit()
        self.source_roots_edit = QPlainTextEdit()
        self.source_roots_edit.setPlaceholderText("Freigegebene Musikordner: ein vollständiger Pfad pro Zeile")
        self.source_roots_edit.setMaximumHeight(90)
        form.addRow("Satztyp", self.mode_box)
        self.folder_edit = QLineEdit(str(folder or ""))
        self.folder_edit.setToolTip("Nur diesen Musikordner verwenden. Fehlende Analyse wird mit der vorhandenen Analyse gestartet. Originaldateien bleiben am Quellort.")
        source_button = QPushButton("Musikordner wählen")
        source_button.setToolTip("Einen Musikordner wählen; Analyse-Snapshot und Satzordner werden automatisch privat angelegt.")
        source_button.clicked.connect(self._add_source_root)
        form.addRow("Original-Musikordner (nur lesen)", self.folder_edit)
        form.addRow("", source_button)
        def integer(low, high, value):
            box = QSpinBox()
            box.setRange(low, high)
            box.setValue(value)
            return box
        self.count_box = integer(1, rate.MAX_ANZAHL, 20)
        self.bpm_box = QDoubleSpinBox()
        self.bpm_box.setRange(0.01, rate.PAAR_BPM_MAX)
        self.bpm_box.setDecimals(2)
        self.bpm_box.setValue(rate.STANDARD_BPM_TOLERANZ)
        self.energy_box = QComboBox()
        self.energy_box.addItems(["auto", "up", "down", "maintain"])
        self.harmonic_box = integer(1, 10, 7)
        self.experimental_box = QCheckBox("Experimentelle Harmonie-Beziehungen erlauben")
        self.experimental_box.setChecked(True)
        self.seed_box = integer(-2147483647, 2147483647, rate.STANDARD_SEED)
        self.genre_box = QComboBox()
        self.genre_box.addItems(["Alle", *CANONICAL_GENRES])
        self.versions_box = integer(1, 5, rate.STANDARD_MAX_VERSIONEN_PRO_PAAR)
        self.tracks_once_box = QCheckBox("Jeden Track im Durchgang höchstens einmal")
        self.profile_edit = QLineEdit()
        self.workers_box = integer(1, 4, 1)
        self.transition_box = QComboBox()
        self.transition_box.addItems(["kontrolliert", "produktion"])
        self.sequence_tracks_box = integer(rate.MIN_SEQUENZ_TRACKS, rate.MAX_ANZAHL, rate.STANDARD_SEQUENZ_TRACKS)
        self.transitions_box = integer(rate.MIN_DRAMATURGIE_UEBERGAENGE, rate.MAX_ANZAHL, rate.STANDARD_UEBERGAENGE_PRO_VARIANTE)
        advanced = QWidget()
        advanced_form = QFormLayout(advanced)
        self.advanced_button = QPushButton("Erweiterte Optionen")
        self.advanced_button.setCheckable(True)
        self.advanced_button.setToolTip("Zusätzliche Auswahlparameter anzeigen. Werte gelten nur für den jeweils aktivierten Satztyp.")
        self.advanced_button.toggled.connect(advanced.setVisible)
        advanced.setVisible(False)
        form.addRow(self.advanced_button)
        form.addRow(advanced)
        tips = (
            "Gewünschte Anzahl gültiger Übergangspaare; nicht Anzahl Tracks.",
            "Maximal erlaubter Tempoabstand für die Paar-Auswahl.",
            "Gewünschter Energieverlauf; auto verwendet die Producer-Vorgabe.",
            "Strenge der harmonischen Auswahl für Kandidaten (1 bis 10).",
            "Zusätzliche experimentelle harmonische Beziehungen zulassen.",
            "Reproduzierbare Zufallsauswahl bei gleichen Eingaben.",
            "Paar-Auswahl auf das gewählte Genre beschränken; Alle deaktiviert den Filter.",
            "Höchstens fünf bewertbare Varianten pro Paar.",
            "Jeden Track höchstens einmal im Durchgang auswählen.",
            "Optionales Auswahlprofil für Kandidaten; leer verwendet die Producer-Vorgabe.",
            "Anzahl paralleler Suchprozesse für Kandidaten (1 bis 4).",
            "Kontrollierte Übergänge oder Übergangstypen aus der Produktionslogik.",
            "Anzahl Tracks im Dramaturgie-Pool.",
            "Anzahl Übergänge je Dramaturgie-Variante.",
        )
        for index, (label, widget) in enumerate((
            ("Anzahl Übergangspaare", self.count_box), ("BPM-Toleranz", self.bpm_box),
            ("Energie-Richtung", self.energy_box), ("Harmonie-Strenge", self.harmonic_box),
            ("Experimentell", self.experimental_box), ("Zufallsseed", self.seed_box),
            ("Nur gleiche Genres", self.genre_box), ("Versionen pro Paar", self.versions_box),
            ("Track-Auswahl", self.tracks_once_box), ("Auswahlprofil (optional)", self.profile_edit),
            ("Suchprozesse", self.workers_box), ("Übergangstyp-Modus", self.transition_box),
            ("Tracks im Dramaturgie-Pool", self.sequence_tracks_box),
            ("Übergänge pro Dramaturgie-Variante", self.transitions_box),
        )):
            widget.setToolTip(tips[index])
            advanced_form.addRow(label, widget)
        self.mode_box.setToolTip("Einzel: eine Note; Kandidaten: Variantenvergleich; Dreinoten: drei Dimensionen; Dramaturgie: Sequenzbewertung.")
        form_widget = QWidget()
        form_widget.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)
        layout.addWidget(scroll)
        self.resize(740, 760)
        layout.addWidget(QLabel("Nur Metadaten speichern. Übergänge bei Bedarf anhören. Vorbereitung ist kein Render-/Audit-Nachweis."))
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_config)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.mode_box.currentIndexChanged.connect(self._mode_changed)
        self.mode_box.setCurrentIndex(1)
        self._mode_changed()

    def _browse(self, edit, directory):
        if directory:
            parent = QFileDialog.getExistingDirectory(self, "Elternordner wählen; neuen Ordnernamen im Feld ergänzen")
            if parent:
                edit.setText(parent.rstrip("/\\") + "/Neuer-Hoertest")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Analyse-Cache wählen", "", "SQLite (*.db)")
            if path:
                edit.setText(path)

    def _add_source_root(self):
        path = QFileDialog.getExistingDirectory(self, "Original-Musikordner zum Lesen freigeben", self.folder_edit.text())
        if path:
            self.folder_edit.setText(path)

    def _mode_changed(self, _index=None):
        candidate = self.mode_box.currentIndex() in (1, 2)
        dramaturgy = self.mode_box.currentIndex() == 3
        for widget in (self.count_box, self.seed_box, self.energy_box, self.genre_box):
            widget.setEnabled(not dramaturgy)
        for widget in (self.harmonic_box, self.experimental_box, self.versions_box, self.tracks_once_box, self.profile_edit, self.workers_box, self.transition_box):
            widget.setEnabled(candidate)
        self.sequence_tracks_box.setEnabled(dramaturgy)
        self.transitions_box.setEnabled(dramaturgy)

    def values(self):
        index = self.mode_box.currentIndex()
        mode = ("einzel", "kandidaten", "kandidaten", "dramaturgie")[index]
        values = {"mode": mode, "cache": self.cache_edit.text().strip(), "output_dir": self.output_edit.text().strip(), "bpm_tolerance": self.bpm_box.value()}
        if mode != "dramaturgie":
            values.update(count=self.count_box.value(), seed=self.seed_box.value(), energy_direction=None if self.energy_box.currentText() == "auto" else self.energy_box.currentText(), only_genre=None if self.genre_box.currentIndex() == 0 else self.genre_box.currentText())
        if mode == "kandidaten":
            values.update(harmonic_strictness=self.harmonic_box.value(), allow_experimental=self.experimental_box.isChecked(), max_versions_per_pair=self.versions_box.value(), three_notes=index == 2, tracks_once=self.tracks_once_box.isChecked(), selection_profile=self.profile_edit.text().strip() or None, workers=self.workers_box.value(), transition_type_mode=self.transition_box.currentText())
        else:
            values["three_notes"] = False
        if mode == "dramaturgie":
            values.update(sequence_tracks=self.sequence_tracks_box.value(), transitions_per_variant=self.transitions_box.value())
        return values

    def _accept_config(self):
        try:
            from hpg_core.hearing_managed import managed_config
            values = self.values()
            for key in ("cache", "output_dir"):
                values.pop(key)
            if values.get("selection_profile"):
                values["selection_profile"] = Path(values["selection_profile"])
            if values.get("energy_direction") is None:
                values["energy_direction"] = "auto"
            if not self.folder_edit.text().strip():
                raise ValueError("Einen Original-Musikordner wählen")
            self.config = managed_config(self.folder_edit.text().strip(), **values)
        except (OSError, ValueError, TypeError) as exc:
            self.error_label.setText(str(exc))
            return
        self.accept()


class HearingRatingDialog(QDialog):
    """Speichert jede Eingabe durch den gemeinsamen Bewertungsservice."""

    def __init__(self, session, save, parent=None, *, read_only=False):
        super().__init__(parent)
        if session.get("mode") not in {"einzel", "kandidaten", "dreinoten", "dramaturgie"}:
            raise ValueError("Unbekannter Bewertungsmodus")
        if not session.get("groups") or any(not group.get("clips") for group in session["groups"]):
            raise ValueError("Keine bewertbaren Hörproben")
        self.session = session
        self.save = save
        self.read_only = bool(read_only)
        self.pair_index = self.clip_index = 0
        self._loading = False
        self._audio_worker = None
        self._render_generation = 0
        self._audio_buffer = None
        self._pending_render = False
        self._closing_result = None
        self._current_render_ready = False
        self._rendered_clips = set()
        self.rating_boxes = {}
        self.sequence_boxes = {}
        self.setWindowTitle("Hörtest – in der App bewerten")
        self.resize(580, 460)
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.errorOccurred.connect(lambda _error, message: self.status_label.setText(f"Audiofehler: {message}"))
        self.player.mediaStatusChanged.connect(self._media_status)
        self.finished.connect(self._stop_player)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Verdeckte Bewertung. Strukturprüfung ist keine Audit-Prüfung."))
        self.pair_label = QLabel()
        self.clip_label = QLabel()
        layout.addWidget(self.pair_label)
        layout.addWidget(self.clip_label)
        row = QHBoxLayout()
        self.previous_clip_button = QPushButton("Vorherige Variante")
        self.play_button = QPushButton("Abspielen / Pause")
        self.next_clip_button = QPushButton("Nächste Variante")
        for button in (self.previous_clip_button, self.play_button, self.next_clip_button):
            row.addWidget(button)
        layout.addLayout(row)
        form = QFormLayout()
        mode = session["mode"]
        dimensions = ("bewertung",) if mode == "einzel" else (
            ("note",) if mode == "kandidaten" else
            ("track_note", "technik_note", "gesamt_note")
        )
        for dimension in dimensions:
            box = self._note_box()
            self.rating_boxes[dimension] = box
            form.addRow(NOTE_LABELS[dimension], box)
            box.currentIndexChanged.connect(lambda index, name=dimension: self._rate(name, index))
        layout.addLayout(form)
        if mode in {"kandidaten", "dreinoten"}:
            choices = QHBoxLayout()
            self.best_button = QPushButton("Diese Variante ist die beste")
            self.no_best_button = QPushButton("Keine beste Variante")
            self.best_button.clicked.connect(lambda: self._choose(True))
            self.no_best_button.clicked.connect(lambda: self._choose(False))
            choices.addWidget(self.best_button)
            choices.addWidget(self.no_best_button)
            layout.addLayout(choices)
            self.choice_label = QLabel()
            layout.addWidget(self.choice_label)
        if mode == "dramaturgie":
            sequence_form = QFormLayout()
            for dimension in ("dramaturgie_gesamt", "energieverlauf", "peak_platzierung", "kohaerenz"):
                box = self._note_box()
                self.sequence_boxes[dimension] = box
                sequence_form.addRow(NOTE_LABELS[dimension], box)
                box.currentIndexChanged.connect(lambda index, name=dimension: self._rate(name, index, sequence=True))
            layout.addWidget(QLabel("Bewertung der gesamten Sequenz"))
            layout.addLayout(sequence_form)
            self.sequence_play_button = QPushButton("Sequenz ab hier abspielen")
            self.sequence_play_button.clicked.connect(self._play_sequence)
            layout.addWidget(self.sequence_play_button)
        self._sequence_playing = False
        pair_row = QHBoxLayout()
        self.previous_pair_button = QPushButton("Vorheriges Paar / Sequenz")
        self.next_pair_button = QPushButton("Nächstes Paar / Sequenz")
        pair_row.addWidget(self.previous_pair_button)
        pair_row.addWidget(self.next_pair_button)
        layout.addLayout(pair_row)
        self.status_label = QLabel("Vorhandene Noten geladen. Änderungen werden sofort gespeichert.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.previous_clip_button.clicked.connect(lambda: self._move_clip(-1))
        self.next_clip_button.clicked.connect(lambda: self._move_clip(1))
        self.previous_pair_button.clicked.connect(lambda: self._move_pair(-1))
        self.next_pair_button.clicked.connect(lambda: self._move_pair(1))
        self.play_button.clicked.connect(self._toggle_playback)
        self._show_clip()

    @staticmethod
    def _note_box():
        box = QComboBox()
        box.addItems(["Nicht bewertet / Note löschen", "1 – geht gar nicht", "2", "3", "4", "5 – sehr gut"])
        return box

    def _group(self):
        return self.session["groups"][self.pair_index]

    def _clip(self):
        return self._group()["clips"][self.clip_index]

    def _clip_key(self):
        return self.pair_index, self.clip_index

    def _rating_allowed(self):
        return not self._clip().get("spec") or self._current_render_ready

    def _group_rendered(self):
        return all(
            not clip.get("spec") or (self.pair_index, index) in self._rendered_clips
            for index, clip in enumerate(self._group()["clips"])
        )

    def _show_clip(self):
        self._render_generation += 1
        self._current_render_ready = False
        self.player.stop()
        self.player.setSource(QUrl())
        if self._audio_buffer is not None:
            self._audio_buffer.close()
            self._audio_buffer.deleteLater()
            self._audio_buffer = None
        if self._audio_worker is not None:
            self._audio_worker.request_cancel()
        self._pending_render = False
        path = self._clip().get("path")
        self.player.setSource(QUrl.fromLocalFile(str(path)) if path and not self._clip().get("spec") else QUrl())
        self.play_button.setEnabled(bool(path) or bool(self._clip().get("spec")))
        self._refresh_ratings()

    def _refresh_ratings(self):
        """Noten aktualisieren, ohne laufende Wiedergabe zu unterbrechen."""
        self._loading = True
        try:
            kind = "Sequenz" if self.session["mode"] == "dramaturgie" else "Paar"
            self.pair_label.setText(f"{kind} {self.pair_index + 1}/{len(self.session['groups'])}")
            self.clip_label.setText(f"Variante {self.clip_index + 1}/{len(self._group()['clips'])}")
            for name, box in self.rating_boxes.items():
                box.setCurrentIndex(int(self._clip()["ratings"].get(name) or 0))
                box.setEnabled(not self.read_only and self._rating_allowed())
            for name, box in self.sequence_boxes.items():
                box.setCurrentIndex(int(self._group()["ratings"].get(name) or 0))
                box.setEnabled(not self.read_only and self._group_rendered())
            if hasattr(self, "choice_label"):
                chosen = self._clip().get("gewaehlt", "")
                self.choice_label.setText("Als beste gewählt" if chosen == "1" else (
                    "Keine beste Variante gewählt" if all(c.get("gewaehlt") == "0" for c in self._group()["clips"]) else "Diese Variante ist nicht als beste gewählt"
                ))
                self.best_button.setEnabled(
                    not self.read_only and self._rating_allowed() and self._group_rendered() and
                    (self.session["mode"] == "dreinoten" or int(self._clip()["ratings"].get("note") or 0) >= 2)
                )
                self.no_best_button.setEnabled(not self.read_only and self._rating_allowed() and self._group_rendered())
        finally:
            self._loading = False

    def _persist(self, route, payload):
        try:
            self.save(route, payload)
        except (OSError, ValueError, RuntimeError, csv.Error) as exc:
            self.status_label.setText(f"Nicht gespeichert: {exc}")
            self._refresh_ratings()
            return False
        self.status_label.setText("Bewertung gespeichert.")
        return True

    def _rate(self, dimension, index, sequence=False):
        if self._loading:
            return
        if self.read_only:
            self._refresh_ratings()
            return
        if not (self._group_rendered() if sequence else self._rating_allowed()):
            self.status_label.setText("Erst nach erfolgreichem Rendern bewerten. Vorhandene Noten bleiben unverändert.")
            self._refresh_ratings()
            return
        note = index if index else None
        clip, group = self._clip(), self._group()
        if sequence:
            route, payload = "/dramaturgie-note", {"variant_id": group["id"], "dimension": dimension, "note": note}
        elif self.session["mode"] == "dramaturgie":
            route, payload = "/transition-note", {"transition_id": clip["pair_id"], "dimension": dimension, "note": note}
        else:
            route, payload = "/note", {"pair_id": clip["pair_id"], "note": note}
            if self.session["mode"] != "einzel":
                payload.update(clip_id=clip["clip_id"], dimension=dimension)
        if self._persist(route, payload):
            target = group["ratings"] if sequence else clip["ratings"]
            target[dimension] = str(note) if note is not None else ""
            if dimension == "note" and note in (None, 1) and clip.get("gewaehlt") == "1":
                clip["gewaehlt"] = ""
            self._refresh_ratings()

    def _choose(self, best):
        if self.read_only:
            self._refresh_ratings()
            return
        if not self._rating_allowed() or not self._group_rendered():
            self.status_label.setText("Bestwahl erst nach erfolgreichem Rendern aller Varianten möglich.")
            self._refresh_ratings()
            return
        payload = {"pair_id": self._clip()["pair_id"], "clip_id": self._clip()["clip_id"] if best else ""}
        if self._persist("/bester", payload):
            for clip in self._group()["clips"]:
                clip["gewaehlt"] = ("1" if clip is self._clip() else "") if best else "0"
            self._refresh_ratings()

    def _move_clip(self, step):
        self._sequence_playing = False
        self.clip_index = (self.clip_index + step) % len(self._group()["clips"])
        self._show_clip()

    def _move_pair(self, step):
        self._sequence_playing = False
        self.pair_index = (self.pair_index + step) % len(self.session["groups"])
        self.clip_index = 0
        self._show_clip()

    def _toggle_playback(self):
        self._sequence_playing = False
        if self._clip().get("spec") and self._audio_buffer is None:
            self._start_render()
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _play_sequence(self):
        self._sequence_playing = True
        if self._clip().get("spec") and self._audio_buffer is None:
            self._start_render()
        else:
            self.player.play()

    def _media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._sequence_playing:
            if self.clip_index + 1 < len(self._group()["clips"]):
                self.clip_index += 1
                self._show_clip()
                if self._clip().get("spec"):
                    self._start_render()
                else:
                    self.player.play()
            else:
                self._sequence_playing = False
                self.status_label.setText("Sequenz vollständig abgespielt.")

    def _stop_player(self, _result=None):
        self._render_generation += 1
        self._sequence_playing = False
        self.player.stop()
        self.player.setSource(QUrl())
        if self._audio_buffer is not None:
            self._audio_buffer.close()
            self._audio_buffer.deleteLater()
            self._audio_buffer = None

    def _start_render(self):
        if self._audio_worker is not None:
            self._audio_worker.request_cancel()
            self._pending_render = True
            return
        from hpg_core.hearing_playback import HearingAudioWorker

        clip = self._clip()
        self._current_render_ready = False
        self._rendered_clips.discard(self._clip_key())
        self._refresh_ratings()
        source = HearingAudioWorker(clip["spec"], clip.get("sources", ()), parent=self)
        self._audio_worker = source
        self._render_generation += 1
        token = self._render_generation
        self.status_label.setText("Übergang wird bei Bedarf im Speicher gerendert …")
        source.audio_ready.connect(lambda data, worker=source, key=token: self._render_ready(data, worker, key))
        source.audio_error.connect(lambda error, worker=source, key=token: self._render_error(error, worker, key))
        source.finished.connect(lambda worker=source: self._render_finished(worker))
        source.start()

    def _render_ready(self, data, worker, token):
        if worker is not self._audio_worker or token != self._render_generation or self._closing_result is not None:
            return
        self._current_render_ready = True
        self._rendered_clips.add(self._clip_key())
        self._refresh_ratings()
        self._audio_buffer = QBuffer(self)
        self._audio_buffer.setData(data)
        self._audio_buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.player.setSourceDevice(self._audio_buffer, QUrl("memory:preview.wav"))
        self.player.play()
        self.status_label.setText("Übergang bereit. Nur im Speicher; kein Audit-Nachweis.")

    def _render_error(self, error, worker, token):
        if worker is self._audio_worker and token == self._render_generation and self._closing_result is None:
            self._current_render_ready = False
            self._rendered_clips.discard(self._clip_key())
            self._refresh_ratings()
            self.status_label.setText(
                f"Übergang nicht abspielbar: {error}. Keine neue Bewertung möglich; vorhandene Noten bleiben unverändert."
            )

    def _render_finished(self, worker):
        if worker is not self._audio_worker:
            return
        self._audio_worker = None
        worker.deleteLater()
        if self._closing_result is not None:
            super().done(self._closing_result)
        elif self._pending_render:
            self._pending_render = False
            self._start_render()

    def done(self, result):
        self._current_render_ready = False
        self._rendered_clips.clear()
        if self._audio_worker is not None:
            self._closing_result = result
            self._pending_render = False
            self._stop_player()
            self._audio_worker.request_cancel()
            self.status_label.setText("Beende eigenen Renderprozess …")
            return
        super().done(result)

    def closeEvent(self, event):
        if self._audio_worker is not None:
            self.done(QDialog.DialogCode.Rejected)
            event.ignore()
            return
        self._stop_player()
        super().closeEvent(event)


class HearingSetBrowserDialog(QDialog):
    """Fortschritt ist keine Quellen-/Auditpruefung; Oeffnen validiert separat."""

    def __init__(self, summaries, parent=None):
        super().__init__(parent)
        self.summaries = tuple(summaries)
        self.selected_path = None
        self.setWindowTitle("Hörtest-Sätze – Fortschritt / Fortsetzen")
        self.resize(950, 480)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Nur gewählter Ordner und direkte Unterordner. Kein Quellen- oder Auditnachweis.\nÖffnen prüft den gewählten Satz vollständig im Hintergrund."))
        self.table = QTableWidget(len(self.summaries), 5)
        self.table.setHorizontalHeaderLabels(["Ordner", "Typ", "Bewertungen", "Status", "Fehler"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i, summary in enumerate(self.summaries):
            values = (str(summary.path), summary.type, f"{summary.rated}/{summary.total}", summary.status, " | ".join(summary.errors))
            for j, value in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        self.open_button = buttons.button(QDialogButtonBox.StandardButton.Open)
        self.open_button.setEnabled(False)
        self.table.itemSelectionChanged.connect(self._selection)
        self.table.cellDoubleClicked.connect(lambda *_args: self._open_selected())
        buttons.accepted.connect(self._open_selected)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _selection(self):
        row = self.table.currentRow()
        enabled = 0 <= row < len(self.summaries) and self.summaries[row].status not in {"error", "empty"}
        self.open_button.setEnabled(enabled)

    def _open_selected(self):
        self._selection()
        if self.open_button.isEnabled():
            self.selected_path = self.summaries[self.table.currentRow()].path
            self.accept()


class HearingBlindPrepareDialog(QDialog):
    """Vorhandene HPG/Baseline-Clips referenzieren; keine neuen Musikdateien."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("A/B-Blindsatz vorbereiten – nur lokale Referenzen")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.edits = {}
        labels = {"manifest": "A/B-Manifest CSV", "output_dir": "Neuer Satzordner", "key_path": "Neuer privater Schlüssel JSON",
                  "source_root": "Erlaubter Quellordner"}
        for key, label in labels.items():
            edit = QLineEdit()
            self.edits[key] = edit
            row = QHBoxLayout()
            row.addWidget(edit)
            button = QPushButton("Wählen")
            button.clicked.connect(lambda _checked=False, name=key: self._browse(name))
            row.addWidget(button)
            form.addRow(label, row)
        self.seed_enabled = QCheckBox("Reproduzierbarer Seed")
        self.seed_box = QSpinBox()
        self.seed_box.setRange(-2147483647, 2147483647)
        self.seed_box.setValue(20260820)
        self.seed_box.setEnabled(False)
        self.seed_enabled.toggled.connect(self.seed_box.setEnabled)
        form.addRow(self.seed_enabled, self.seed_box)
        layout.addLayout(form)
        notice = QLabel("LOCAL UI BLIND: Nur neutrale IDs, Originalpfade bleiben in den Metadaten sichtbar.\nNicht metadatenblind, nicht portabel. Nur Vorbereitung; keine Blindbewertung/Statistik.\nSchlüssel muss außerhalb des Satzordners liegen. Ein Absturz zwischen beiden Publikationen kann einen verwaisten Schlüssel hinterlassen.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.error_label = QLabel()
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_config)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self, key):
        if key == "source_root":
            path = QFileDialog.getExistingDirectory(self, "Quellordner wählen")
        elif key == "manifest":
            path, _ = QFileDialog.getOpenFileName(self, "Manifest wählen", "", "CSV (*.csv)")
        else:
            path, _ = QFileDialog.getSaveFileName(self, "Neues Ziel wählen", "", "JSON (*.json)" if key == "key_path" else "Alle (*)")
        if path:
            self.edits[key].setText(path)

    def _accept_config(self):
        if any(not edit.text().strip() or not Path(edit.text().strip()).is_absolute() for edit in self.edits.values()):
            self.error_label.setText("Alle vier vollständigen Pfade angeben.")
            return
        self.config = {key: Path(edit.text().strip()) for key, edit in self.edits.items()}
        self.config["seed"] = self.seed_box.value() if self.seed_enabled.isChecked() else None
        self.accept()


class HearingFitDialog(QDialog):
    """Fit-Optionen und Cache explizit waehlen; noch keine Gewichte aktivieren."""

    def __init__(self, cache="", *, audit_only=False, single=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hörtest prüfen" if audit_only else "Bewertungen auswerten – nur Vorschlag")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.cache_edit = QLineEdit("" if cache is None else str(cache))
        self.cache_edit.setToolTip("Zum Satz gehörender Analyse-Snapshot. Bei alten Sätzen manuell wählen; niemals den aktuellen Cache ersatzweise verwenden.")
        row = QHBoxLayout()
        row.addWidget(self.cache_edit)
        browse = QPushButton("Cache wählen")
        browse.setToolTip("Nur den ursprünglichen Cache dieses alten Satzes wählen. Der Replay-Audit prüft die Bindung.")
        def choose():
            selected, _ = QFileDialog.getOpenFileName(self, "Zum Satz gehörenden Cache wählen", "", "SQLite (*.db)")
            if selected:
                self.cache_edit.setText(selected)
        browse.clicked.connect(choose)
        row.addWidget(browse)
        advanced = QWidget()
        advanced_form = QFormLayout(advanced)
        advanced_form.addRow("Analyse-Cache (Einzel: optional)" if single and not audit_only else "Analyse-Cache", row)
        advanced.setVisible(False)
        toggle = QPushButton("Erweiterte Optionen / ältere Sätze")
        toggle.setCheckable(True)
        toggle.setToolTip("Manuellen Cache und zusätzliche Fit-Optionen anzeigen.")
        toggle.toggled.connect(advanced.setVisible)
        form.addRow(toggle)
        form.addRow(advanced)
        self.seed_box = QSpinBox()
        self.seed_box.setRange(-2147483647, 2147483647)
        self.seed_box.setValue(20260820)
        self.genres_edit = QLineEdit()
        self.genres_edit.setPlaceholderText("Einzel-Fit: kanonische Genres, komma-getrennt; leer = alle")
        self.seed_box.setToolTip("Zufallsseed für reproduzierbaren Fit bei identischen Eingaben; im reinen Audit ohne Wirkung.")
        self.genres_edit.setToolTip("Nur Einzel-Fit: kanonische Genres komma-getrennt; leer wertet alle aus. Kandidaten ignorieren diesen Filter.")
        advanced_form.addRow("Fit-Seed", self.seed_box)
        advanced_form.addRow("Einzel-Fit-Genres", self.genres_edit)
        self.seed_box.setEnabled(not audit_only)
        self.genres_edit.setEnabled(not audit_only and single)
        layout.addLayout(form)
        layout.addWidget(QLabel("Kandidaten: exakter Replay-Audit. Einzel: eigener Fit. Dramaturgie: kein Fit.\nBerechnung verändert keine aktiven Nutzergewichte."))
        self.error_label = QLabel()
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        def accept_valid():
            from .genres import CANONICAL_GENRES
            cache_text = self.cache_edit.text().strip()
            self.cache = Path(cache_text) if cache_text else None
            self.genres = tuple(g.strip() for g in self.genres_edit.text().split(",") if g.strip()) if single else ()
            if (self.cache is None and (not single or audit_only)
                    or self.cache is not None and not self.cache.is_file()
                    or any(g not in CANONICAL_GENRES for g in self.genres)):
                self.error_label.setText("Vorhandenen Cache und gültige kanonische Genres wählen.")
                return
            self.seed = self.seed_box.value()
            self.accept()
        buttons.accepted.connect(accept_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class HearingCalibrationResultDialog(QDialog):
    """Zeigt reale Gates und Vorschlag; aktive Uebernahme separat bestaetigen."""

    def __init__(self, proposal, parent=None, cleanup_warning=""):
        super().__init__(parent)
        import json
        from .hearing_calibration import validate_proposal
        validate_proposal(proposal)
        self.proposal = proposal
        self.setWindowTitle("Kalibrierungsergebnis – noch nicht aktiv übernommen")
        self.resize(850, 620)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"Replay-Audit: {'bestanden' if proposal['audit_passed'] else 'nicht durchgeführt'} | Fit: {proposal['fit_status']}\n"
            f"Gatebestandene Genres: {', '.join(proposal['gate_updates']) or 'keine'} | Produktive Übernahme: NEIN"
        ))
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(json.dumps(proposal, ensure_ascii=False, indent=2))
        layout.addWidget(text)
        row = QHBoxLayout()
        self.apply_button = QPushButton("Diese Gewichte übernehmen und Playlist neu berechnen")
        self.apply_button.setEnabled(bool(proposal["gate_updates"]) and proposal["fit_status"] == "passed" and proposal["audit_passed"])
        self.apply_button.clicked.connect(self.accept)
        row.addWidget(self.apply_button)
        export = QPushButton("Bericht / Vorschlag speichern")
        export.clicked.connect(self._export)
        row.addWidget(export)
        close = QPushButton("Ohne Übernahme schließen")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        layout.addLayout(row)
        self.status_label = QLabel(cleanup_warning or "Temporäres Replay-Audio ist entfernt. Audit bleibt ein Nachweis des damaligen temporären Snapshots.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Kalibrierungsbericht speichern", "kalibrierung.json", "JSON (*.json)")
        if not path:
            return
        try:
            from .hearing_calibration import export_proposal
            target = export_proposal(self.proposal, path)
        except (OSError, ValueError) as exc:
            self.status_label.setText(f"Bericht nicht gespeichert: {exc}")
            return
        self.status_label.setText(f"Bericht gespeichert: {target}")

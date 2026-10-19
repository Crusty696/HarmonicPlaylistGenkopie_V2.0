"""Sichtbare App mit belegten Originaltrack-Snapshots, ohne erneute Analyse.

Dies belegt keinen frischen GUI-Import: die Eingangsdaten stammen explizit
aus dem benannten vorherigen Analysebeleg. Vorschau wird normal angeklickt.
"""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    root = Path(sys.argv[1]).resolve(strict=True)
    output = Path(sys.argv[2]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ['HPG_CACHE_FILE'] = str(output/'isolated.db')
    os.environ['HPG_CANDIDATE_CHOICES_FILE'] = str(output/'choices.json')
    from dataclasses import asdict
    from hpg_core.ai_models.feature_reuse import digest
    report = json.loads((root/'report.json').read_text(encoding='utf-8'))
    for path, source in report['sources'].items():
        if digest(path) != source['before_sha256']:
            raise ValueError('Originalquelle seit Analysebeleg geaendert')
    from PyQt6.QtCore import QSettings, QTimer
    from PyQt6.QtWidgets import QApplication
    from hpg_core.caching import dict_to_track
    from hpg_core.playlist import generate_playlist_result
    from hpg_core.theme import apply_dark_theme
    from main import MainWindow
    app = QApplication(sys.argv[:1])
    app.setStyle('Fusion')
    apply_dark_theme(app)
    events = []
    completed = set()
    render_all = '--render-all' in sys.argv[3:]
    def record(selected):
        base, result, peaks, duration, pending = selected[:5]
        index = result.boundary_index
        if index in completed:
            return
        completed.add(index)
        events.append(dict(event='reserve_ready', index=index,
            gui_cache_ready=index in window.mix_tips_panel._ram_preview_cache,
            bytes=len(result.audio), duration=duration,
            rejected=len(result.rejected), spec=asdict(result.spec), pending=list(pending)))
        (output/'gui-events.json').write_text(json.dumps(events, indent=2), encoding='utf-8')
        if render_all and index+1 < len(tracks)-1:
            QTimer.singleShot(100, lambda: window.mix_tips_panel._request_preview(index+1))
    class EvidenceWindow(MainWindow):
        def _publiziere_generation_result(self, result):
            super()._publiziere_generation_result(result)
            self.mix_tips_panel.reserve_ready.connect(record)
    settings = QSettings(str(output/'settings.ini'), QSettings.Format.IniFormat)
    window = EvidenceWindow(settings=settings)
    tracks = [dict_to_track(json.loads(path.read_text(encoding='utf-8')))
              for path in sorted(root.glob('track-*.json'))]
    if len(tracks) != len(report['sources']):
        raise ValueError('Unvollständige Originaltrack-Snapshots')
    result = generate_playlist_result(tracks, 'Harmonic Flow', candidate_choice_snapshot={})
    window._publiziere_generation_result(result)
    window.setWindowTitle('HPG – Originaltrack-Vorschau mit Analyse-Snapshot')
    window.show()
    if render_all:
        window._on_nav_changed(2)
        QTimer.singleShot(500, lambda: window.mix_tips_panel._request_preview(0))
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())

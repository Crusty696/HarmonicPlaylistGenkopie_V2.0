import os, runpy, sys

sys.path.insert(0, 'C:\\Users\\david\\Documents\\HarmonicPlaylistGenkopie_V2.0-main\\HarmonicPlaylistGenkopie_V2.0-main')

from pathlib import Path

from types import SimpleNamespace as NS

import numpy as np

import soundfile as sf

from tools import rate_transitions as rt

from hpg_core import candidate_choices as cc, playlist as pl, tolerances

from hpg_core import transition_renderer as tr

from hpg_core.exporters import rekordbox_xml_exporter as rx

cache = Path('C:\\Users\\david\\Documents\\HarmonicPlaylistGenkopie_V2.0-main\\HarmonicPlaylistGenkopie_V2.0-main\\.pytest-e2e-followup-final\\popen-gw4\\test_neues_wal_waehrend_lauf_v0\\cache.db')

track_a = NS(filePath=str(cache.parent / "a.wav"))

track_b = NS(filePath=str(cache.parent / "b.wav"))

Path(track_a.filePath).write_bytes(b"a")

Path(track_b.filePath).write_bytes(b"b")

plan = NS(mix_out_a=1.0, mix_in_b=2.0, overlap=0.01, transition_type="pro_eq_swap")

k1 = {"t_out": 1.0, "t_in": 2.0, "blend_bars": 8, "flags": {}}

k2 = {"t_out": 1.5, "t_in": 2.5, "blend_bars": 8, "flags": {}}

rec = NS(index=0, kandidat_aktiv=1, kandidat_konsistent=True, kandidaten=[k1, k2], plan=plan, from_track=track_a, to_track=track_b)

rt.lade_tracks_aus_cache = lambda _path: [track_a, track_b]

rt._algorithm_build_fingerprint = lambda: {"sha256": "a" * 64}

pl.reset_pair_candidate_cache = lambda: None

pl.generate_playlist = lambda *_args, **_kwargs: [track_a, track_b]

pl.compute_adjacent_transition_metrics = lambda *_args, **_kwargs: {}

pl.compute_transition_recommendations = lambda *_args, **_kwargs: [rec]

cc.reset_cache = lambda: None

cc.merke = lambda *_args, **_kwargs: None

cc.hole = lambda *_args, **_kwargs: {"ok": True}

cc.vergiss = lambda *_args, **_kwargs: None

tolerances.reset_cache = lambda: None

tolerances.write_override_kandidaten = lambda _data: Path(os.environ["HPG_TOLERANCES_FILE"]).write_text("{}", encoding="utf-8")

tolerances.get_tolerances = lambda _genre: {"kandidaten_loudness_weight": 1.0}

tr.TransitionClipSpec.from_plan = classmethod(lambda cls, *_args: NS(pre_roll_sec=0.01, crossfade_sec=0.01, post_roll_sec=0.01))

def render(_spec, path):

    sf.write(path, np.ones((300, 2), dtype=np.float32) * 0.01, 10000)

    return path

tr.render_transition_clip = render

class Exporter:

    def export(self, _liste, path, _name, transitions=None):

        Path(path).write_text("<DJ_PLAYLISTS><COLLECTION /></DJ_PLAYLISTS>", encoding="utf-8")

        Path(f"{cache}-wal").write_bytes(b"entstand waehrend lauf")

        return NS(status="success", tracks_written=0, cues_written=0, errors=[])

rx.RekordboxXMLExporter = Exporter

sys.argv = ['C:\\Users\\david\\Documents\\HarmonicPlaylistGenkopie_V2.0-main\\HarmonicPlaylistGenkopie_V2.0-main\\tools\\e2e_kandidaten_app.py', "--out", 'C:\\Users\\david\\Documents\\HarmonicPlaylistGenkopie_V2.0-main\\HarmonicPlaylistGenkopie_V2.0-main\\.pytest-e2e-followup-final\\popen-gw4\\test_neues_wal_waehrend_lauf_v0\\satz', "--cache", str(cache)]

runpy.run_path('C:\\Users\\david\\Documents\\HarmonicPlaylistGenkopie_V2.0-main\\HarmonicPlaylistGenkopie_V2.0-main\\tools\\e2e_kandidaten_app.py', run_name="__main__")


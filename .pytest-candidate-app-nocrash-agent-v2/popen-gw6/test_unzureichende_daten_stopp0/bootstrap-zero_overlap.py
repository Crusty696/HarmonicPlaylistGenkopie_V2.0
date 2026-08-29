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

scenario = 'zero_overlap'

cache = Path('C:\\Users\\david\\Documents\\HarmonicPlaylistGenkopie_V2.0-main\\HarmonicPlaylistGenkopie_V2.0-main\\.pytest-candidate-app-nocrash-agent-v2\\popen-gw6\\test_unzureichende_daten_stopp0\\cache.db')

track_a = NS(filePath=str(cache.parent / "a.wav"))

track_b = NS(filePath=str(cache.parent / "b.wav"))

Path(track_a.filePath).write_bytes(b"a")

Path(track_b.filePath).write_bytes(b"b")

k1 = {"t_out": 1.0, "t_in": 2.0, "blend_bars": 8, "flags": {}}

k2 = {"t_out": 1.5, "t_in": 2.5, "blend_bars": 8, "flags": {}}

choice = {}

def make_plan(t_out=1.0, t_in=2.0, overlap=0.01):

    return NS(mix_out_a=t_out, mix_in_b=t_in, overlap=overlap, transition_type="pro_eq_swap")

def make_rec():

    if scenario == "no_candidates":

        return NS(index=0, kandidat_aktiv=0, kandidat_konsistent=True, kandidaten=[], plan=make_plan(), from_track=track_a, to_track=track_b)

    if scenario == "one_candidate":

        return NS(index=0, kandidat_aktiv=1, kandidat_konsistent=True, kandidaten=[k1], plan=make_plan(), from_track=track_a, to_track=track_b)

    candidates = [k1, (dict(k1) if scenario == "no_alternative" else k2)]

    active_plan = None if scenario == "missing_plan" else make_plan(overlap=(0.0 if scenario == "zero_overlap" else 0.01))

    if choice:

        chosen = dict(k2); chosen["flags"] = {"gespeicherte_wahl": True}

        candidates = [chosen, k1]; active_plan = make_plan(1.5, 2.5)

    elif Path(os.environ["HPG_TOLERANCES_FILE"]).exists() and scenario != "no_rank_change":

        candidates = [k2, k1]; active_plan = make_plan(1.5, 2.5)

    return NS(index=0, kandidat_aktiv=1, kandidat_konsistent=True, kandidaten=candidates, plan=active_plan, from_track=track_a, to_track=track_b)

rt.lade_tracks_aus_cache = lambda _path: ([] if scenario == "no_tracks" else [track_a, track_b])

rt._algorithm_build_fingerprint = lambda: {"sha256": "a" * 64}

pl.reset_pair_candidate_cache = lambda: None

pl.generate_playlist = lambda *_args, **_kwargs: [track_a, track_b]

pl.compute_adjacent_transition_metrics = lambda *_args, **_kwargs: {}

pl.compute_transition_recommendations = lambda *_args, **_kwargs: ([] if scenario == "no_recommendations" else [make_rec()])

cc.reset_cache = lambda: None

cc.merke = lambda *_args, **_kwargs: choice.update(ok=True)

cc.hole = lambda *_args, **_kwargs: ({"ok": True} if choice else None)

cc.vergiss = lambda *_args, **_kwargs: choice.clear()

tolerances.reset_cache = lambda: None

tolerances.write_override_kandidaten = lambda _data: Path(os.environ["HPG_TOLERANCES_FILE"]).write_text("{}", encoding="utf-8")

tolerances.get_tolerances = lambda _genre: {"kandidaten_loudness_weight": 1.0}

tr.TransitionClipSpec.from_plan = classmethod(lambda cls, *_args: NS(pre_roll_sec=0.01, crossfade_sec=0.01, post_roll_sec=0.01))

def render(_spec, path):

    if scenario == "render_error":

        Path(path).write_bytes(b"teil")

        raise RuntimeError("Render absichtlich fehlgeschlagen")

    sf.write(path, np.ones((300, 2), dtype=np.float32) * 0.01, 10000)

    return path

tr.render_transition_clip = render

class Exporter:

    def export(self, _liste, path, _name, transitions=None):

        if scenario == "export_error":

            Path(path).write_text("<teil>", encoding="utf-8")

            raise RuntimeError("Export absichtlich fehlgeschlagen")

        xml = ('<DJ_PLAYLISTS><COLLECTION>'

               '<TRACK Location="' + track_a.filePath + '">'

               '<POSITION_MARK Name="MIX OUT" Start="1.0" />'

               '<POSITION_MARK Name="HPG K1 OUT" Start="1.0" /></TRACK>'

               '<TRACK Location="' + track_b.filePath + '">'

               '<POSITION_MARK Name="MIX IN" Start="2.0" />'

               '<POSITION_MARK Name="HPG K1 IN" Start="2.0" /></TRACK>'

               '</COLLECTION></DJ_PLAYLISTS>')

        Path(path).write_text(xml, encoding="utf-8")

        if scenario == "partial_export":

            return NS(status="partial", tracks_written=1, cues_written=2, errors=["Teil-Export"])

        return NS(status="success", tracks_written=2, cues_written=4, errors=[])

rx.RekordboxXMLExporter = Exporter

sys.argv = ['C:\\Users\\david\\Documents\\HarmonicPlaylistGenkopie_V2.0-main\\HarmonicPlaylistGenkopie_V2.0-main\\tools\\e2e_kandidaten_app.py', "--out", 'C:\\Users\\david\\Documents\\HarmonicPlaylistGenkopie_V2.0-main\\HarmonicPlaylistGenkopie_V2.0-main\\.pytest-candidate-app-nocrash-agent-v2\\popen-gw6\\test_unzureichende_daten_stopp0\\ausgabe\\satz', "--cache", str(cache)]

runpy.run_path('C:\\Users\\david\\Documents\\HarmonicPlaylistGenkopie_V2.0-main\\HarmonicPlaylistGenkopie_V2.0-main\\tools\\e2e_kandidaten_app.py', run_name="__main__")


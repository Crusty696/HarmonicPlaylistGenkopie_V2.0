import os, runpy, shutil, sys

sys.path.insert(0, 'C:\\Users\\david\\Documents\\HarmonicPlaylistGenkopie_V2.0-main\\HarmonicPlaylistGenkopie_V2.0-main')

from pathlib import Path

from types import SimpleNamespace as NS

import numpy as np

import soundfile as sf

from tools import rate_transitions as rt

from hpg_core import candidate_choices as cc, playlist as pl, tolerances

from hpg_core import transition_renderer as tr

from hpg_core.exporters import rekordbox_xml_exporter as rx

scenario = 'identical_audio'

cache = Path('C:\\Users\\david\\Documents\\HarmonicPlaylistGenkopie_V2.0-main\\HarmonicPlaylistGenkopie_V2.0-main\\.pytest-candidate-app-nocrash-agent-v4\\popen-gw6\\test_laufzeitfehler_und_fail_o0\\cache.db')

track_a = NS(filePath=str(cache.parent / "a.wav"))

track_b = NS(filePath=str(cache.parent / "b.wav"))

Path(track_a.filePath).write_bytes(b"a")

Path(track_b.filePath).write_bytes(b"b")

k1 = {"t_out": 1.0, "t_in": 2.0, "blend_bars": 8, "flags": {}}

k2 = {"t_out": 1.5, "t_in": 2.5, "blend_bars": 8, "flags": {}}

choice = {}

forgotten = {"value": False}

override_written = {"value": False}

def make_plan(t_out=1.0, t_in=2.0, overlap=0.01):

    return NS(mix_out_a=t_out, mix_in_b=t_in, overlap=overlap, transition_type="pro_eq_swap")

def make_rec():

    if scenario == "no_candidates":

        return NS(index=0, kandidat_aktiv=0, kandidat_konsistent=True, kandidaten=[], plan=make_plan(), from_track=track_a, to_track=track_b)

    if scenario == "one_candidate":

        return NS(index=0, kandidat_aktiv=1, kandidat_konsistent=True, kandidaten=[k1], plan=make_plan(), from_track=track_a, to_track=track_b)

    candidates = [k1, (dict(k1) if scenario == "no_alternative" else k2)]

    overlap = {"zero_overlap": 0.0, "negative_overlap": -1.0, "nan_overlap": float("nan"), "inf_overlap": float("inf")}.get(scenario, 0.01)

    active_plan = None if scenario == "missing_plan" else make_plan(overlap=overlap)

    active_rank = 3 if scenario == "wrong_rank" else (None if scenario == "wrong_rank_type" else 1)

    if choice:

        chosen = dict(k2); chosen["flags"] = ({} if scenario == "missing_choice_flag" else {"gespeicherte_wahl": True})

        candidates = [chosen, k1]

        active_plan = make_plan() if scenario == "plan_not_follow" else make_plan(1.5, 2.5)

        active_rank = 1

    elif forgotten["value"] and scenario in ("reset_flag", "reset_rank"):

        flagged = dict(k1); flagged["flags"] = ({"gespeicherte_wahl": True} if scenario == "reset_flag" else {})

        candidates = [flagged, k2]; active_plan = make_plan(); active_rank = (2 if scenario == "reset_rank" else 1)

    elif Path(os.environ["HPG_TOLERANCES_FILE"]).exists() and scenario != "no_rank_change":

        candidates = [k2, k1]; active_plan = make_plan(1.5, 2.5); active_rank = 1

    elif override_written["value"] and scenario == "incomplete_regler_reset":

        candidates = [k2, k1]; active_plan = make_plan(1.5, 2.5); active_rank = 1

    return NS(index=0, kandidat_aktiv=active_rank, kandidat_konsistent=True, kandidaten=candidates, plan=active_plan, from_track=track_a, to_track=track_b)

rt.lade_tracks_aus_cache = lambda _path: ([] if scenario == "no_tracks" else [track_a, track_b])

rt._algorithm_build_fingerprint = lambda: {"sha256": "a" * 64}

pl.reset_pair_candidate_cache = lambda: None

pl.generate_playlist = lambda *_args, **_kwargs: [track_a, track_b]

pl.compute_adjacent_transition_metrics = lambda *_args, **_kwargs: {}

pl.compute_transition_recommendations = lambda *_args, **_kwargs: ([] if scenario == "no_recommendations" else [make_rec()])

cc.reset_cache = lambda: None

def remember(*_args, **_kwargs):

    choice.update(ok=True); forgotten["value"] = False

cc.merke = remember

cc.hole = lambda *_args, **_kwargs: (None if scenario == "not_persisted" else ({"ok": True} if choice else None))

def forget(*_args, **_kwargs):

    forgotten["value"] = True

    if scenario != "reset_persisted": choice.clear()

cc.vergiss = forget

tolerances.reset_cache = lambda: None

def write_override(_data):

    override_written["value"] = True

    return Path(os.environ["HPG_TOLERANCES_FILE"]).write_text("{}", encoding="utf-8")

tolerances.write_override_kandidaten = write_override

tolerances.get_tolerances = lambda _genre: {"kandidaten_loudness_weight": 1.0}

tr.TransitionClipSpec.from_plan = classmethod(lambda cls, plan, *_args: NS(pre_roll_sec=0.01, crossfade_sec=0.01, post_roll_sec=0.01, marker=plan.mix_out_a))

def render(_spec, path):

    if scenario in ("render_error", "cleanup_error"):

        Path(path).write_bytes(b"teil")

        raise RuntimeError("Render absichtlich fehlgeschlagen")

    amplitude = 0.01 if scenario == "identical_audio" else 0.01 + _spec.marker * 0.001

    sf.write(path, np.ones((300, 2), dtype=np.float32) * amplitude, 10000)

    return path

tr.render_transition_clip = render

class Exporter:

    def export(self, _liste, path, _name, transitions=None):

        if scenario == "export_error":

            Path(path).write_text("<teil>", encoding="utf-8")

            raise RuntimeError("Export absichtlich fehlgeschlagen")

        out_start = "ungueltig" if scenario == "invalid_cue_start" else ("9.0" if scenario == "wrong_mix_cue" else "1.0")

        out_mark = "" if scenario == "missing_mix_cue" else '<POSITION_MARK Name="MIX OUT" Start="' + out_start + '" />'

        in_mark = "" if scenario == "missing_mix_cue" else '<POSITION_MARK Name="MIX IN" Start="2.0" />'

        hpg_out = "" if scenario == "missing_hpg_cues" else '<POSITION_MARK Name="HPG K1 OUT" Start="1.0" />'

        hpg_in = "" if scenario == "missing_hpg_cues" else '<POSITION_MARK Name="HPG K1 IN" Start="2.0" />'

        xml = ('<DJ_PLAYLISTS><COLLECTION>'

               '<TRACK Location="' + track_a.filePath + '">'

               + out_mark + hpg_out + '</TRACK>'

               '<TRACK Location="' + track_b.filePath + '">'

               + in_mark + hpg_in + '</TRACK>'

               '</COLLECTION></DJ_PLAYLISTS>')

        Path(path).write_text(xml, encoding="utf-8")

        if scenario == "partial_export":

            return NS(status="partial", tracks_written=1, cues_written=2, errors=["Teil-Export"])

        if scenario == "success_with_errors":

            return NS(status="success", tracks_written=2, cues_written=4, errors=["Fehler trotz success"])

        if scenario == "incomplete_report":

            return NS(status="success")

        return NS(status="success", tracks_written=2, cues_written=4, errors=[])

rx.RekordboxXMLExporter = Exporter

if scenario == "cleanup_error":

    real_rmtree = shutil.rmtree

    cleanup_calls = {"count": 0}

    def flaky_rmtree(path):

        cleanup_calls["count"] += 1

        if cleanup_calls["count"] == 1:

            raise PermissionError("Aufraeumen absichtlich einmal blockiert")

        return real_rmtree(path)

    shutil.rmtree = flaky_rmtree

sys.argv = ['C:\\Users\\david\\Documents\\HarmonicPlaylistGenkopie_V2.0-main\\HarmonicPlaylistGenkopie_V2.0-main\\tools\\e2e_kandidaten_app.py', "--out", 'C:\\Users\\david\\Documents\\HarmonicPlaylistGenkopie_V2.0-main\\HarmonicPlaylistGenkopie_V2.0-main\\.pytest-candidate-app-nocrash-agent-v4\\popen-gw6\\test_laufzeitfehler_und_fail_o0\\ausgabe\\satz', "--cache", str(cache)]

runpy.run_path('C:\\Users\\david\\Documents\\HarmonicPlaylistGenkopie_V2.0-main\\HarmonicPlaylistGenkopie_V2.0-main\\tools\\e2e_kandidaten_app.py', run_name="__main__")


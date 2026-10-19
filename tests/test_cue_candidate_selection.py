"""Gebundene Cue-Rohscores beeinflussen ausschließlich die Kandidatenkappung."""
from copy import deepcopy
from types import SimpleNamespace
from contextlib import contextmanager
import numpy as np
import pytest
from hpg_core import analysis, caching, mix_candidates as mc
from hpg_core.ai_models import cue_predictor as cp, cue_service as cs
from hpg_core.structure_analyzer import TrackStructure, TrackSection
from hpg_core.rekordbox_importer import RekordboxTrackData
from tests.test_cue_pipeline_integration import pipeline

_REAL_CANDIDATES = analysis._kandidaten_berechnen


def phrases():
    return [dict(start_s=float(16+16*i), end_s=float(32+16*i), kind=1, mood=1, fill=0, label='main')
            for i in range(12)]


def collect(values, **kwargs):
    return mc.collect_candidate_times(seite_grid=mc.phrase_grid_from_phrases(values),
        sections=[], phrases=values, cues=kwargs.pop('cues', []), analyzer_in=None, analyzer_out=None,
        duration=240., grid_sec=16., intro_end=0., outro_start=240., outro_covered=True, **kwargs)


def test_scored_slots_reordered_before_cap_unscored_fixed(monkeypatch):
    monkeypatch.setattr(mc, 'KANDIDATEN_MAX_JE_SEITE', 4)
    baseline = collect(phrases())[0]
    selected = collect(phrases(), cue_scores={i:float(i) for i in range(12) if i != 1})[0]
    assert [c.t for c in baseline] == [16.,32.,48.,64.]
    assert [c.t for c in selected] == [32.,160.,176.,192.]
    assert all(c.confidence == baseline[0].confidence for c in selected)


def test_native_phrase_scores_reorder_only_native_phrase_slots(monkeypatch):
    monkeypatch.setattr(mc, 'KANDIDATEN_MAX_JE_SEITE', 4)
    values = phrases()
    baseline = mc.collect_candidate_times(
        seite_grid=[], sections=[], phrases=[], native_phrases=values, cues=[],
        analyzer_in=None, analyzer_out=None, duration=240., grid_sec=16.,
        intro_end=0., outro_start=240., outro_covered=True, anchor=16.)[0]
    selected = mc.collect_candidate_times(
        seite_grid=[], sections=[], phrases=[], native_phrases=values, cues=[],
        analyzer_in=None, analyzer_out=None, duration=240., grid_sec=16.,
        intro_end=0., outro_start=240., outro_covered=True, anchor=16.,
        cue_scores={i: float(i) for i in range(12)})[0]
    assert [candidate.t for candidate in baseline] == [16., 32., 48., 64.]
    assert [candidate.t for candidate in selected] == [144., 160., 176., 192.]
    assert all(candidate.provenance == 'rekordbox_native_phrase_generator'
               for candidate in selected)


def test_structure_cue_candidates_keep_pssi_precedence_and_gate_native():
    native = dict(status='ok', phrases=phrases())
    selected, verified = analysis._cue_candidates_for_structure(
        phrases=[], pssi_grid_usable=False, native_phrase_analysis=native,
        phrase_phase_usable=True, pssi_grid_verified=False)
    assert selected is native['phrases'] and verified is True
    pssi = phrases()
    selected, verified = analysis._cue_candidates_for_structure(
        phrases=pssi, pssi_grid_usable=True, native_phrase_analysis=native,
        phrase_phase_usable=True, pssi_grid_verified=True)
    assert selected is pssi and verified is True
    selected, verified = analysis._cue_candidates_for_structure(
        phrases=pssi, pssi_grid_usable=True, native_phrase_analysis=native,
        phrase_phase_usable=True, pssi_grid_verified=False)
    assert selected is native['phrases'] and verified is True
    selected, verified = analysis._cue_candidates_for_structure(
        phrases=pssi, pssi_grid_usable=True, native_phrase_analysis=native,
        phrase_phase_usable=False, pssi_grid_verified=False)
    assert selected is None and verified is False


def test_cue_source_signature_exists_without_rekordbox_and_tracks_file_change(tmp_path):
    source = tmp_path / 'audio.wav'
    source.write_bytes(b'first source')
    first = analysis._cue_source_signature(source, '')
    assert len(first) == 64
    assert analysis._cue_source_signature(source, 'rekordbox-track') != first
    source.write_bytes(b'changed source with different size')
    assert analysis._cue_source_signature(source, '') != first


def scored(values, start=0., end=240.):
    output = []
    for index, phrase in enumerate(values):
        center = int((phrase['start_s']-start)*22050)
        low, high = center-3*59049, center+3*59049
        available = int((end-start)*22050)
        output.append(dict(index=index, status='ok', reason=None, raw_score=float(index),
            source=cp.CUE_SCORE_SOURCE, model_hashes=dict(cp.MODEL_HASHES),
            preprocess_version=cp.PREPROCESS_VERSION,
            coverage=dict(window_start_s=start, window_end_s=end, track_duration_s=240.,
                required_start_sample=low, required_end_sample=high, sample_rate=22050,
                source_sample_rate=22050, source_sample_count=available,
                padded_left_samples=max(0,-low), padded_right_samples=max(0,high-available))))
    return output


def test_binding_head_tail_conflicts_mutation_and_identity():
    values = phrases()
    binding = analysis._bind_cue_scores(values, 'rb-source', True)
    head = dict(status='evaluated', results=scored(values))
    tail = deepcopy(head)
    scores = analysis._bound_cue_scores(values, 'rb-source', binding, [head,tail])
    assert scores == dict(enumerate(map(float,range(12))))
    tail['results'][0]['raw_score'] += 1.
    tail['results'][1].update(status='unavailable', raw_score=None)
    scores = analysis._bound_cue_scores(values, 'rb-source', binding, [head,tail])
    assert 0 not in scores and scores[1] == 1.
    tail['results'][2]['model_hashes']['cue'] = 'a'*64
    assert 2 not in analysis._bound_cue_scores(values,'rb-source',binding,[head,tail])
    assert analysis._bound_cue_scores(values,'other-source',binding,[head]) == {}
    values[1]['fill'] = 1
    assert analysis._bound_cue_scores(values,'rb-source',binding,[head]) == {}
    values = phrases()
    values[1] = deepcopy(values[0])
    binding = analysis._bind_cue_scores(values,'rb-source',True)
    assert not ({0,1} & analysis._bound_cue_scores(values,'rb-source',binding,[head]).keys())
    binding = analysis._bind_cue_scores(phrases(),'rb-source',False)
    assert analysis._bound_cue_scores(phrases(),'rb-source',binding,[head]) == {}


def test_manual_and_quantized_collision_remain_neutral(monkeypatch):
    monkeypatch.setattr(mc,'KANDIDATEN_MAX_JE_SEITE',4)
    values = phrases()
    cue = dict(t=32.,name='MIX IN',provenance='manual')
    baseline = collect(values,cues=[cue])[0]
    result = collect(values,cues=[cue],cue_scores={i:float(i) for i in range(12)})[0]
    assert 32. in [x.t for x in baseline] and 32. in [x.t for x in result]
    assert next(x for x in result if x.t == 32.).schema == next(x for x in baseline if x.t == 32.).schema
    # Zwei verschiedene Rohidentitäten kollidieren nach bestehender Rundung.
    values.insert(1,dict(values[0],start_s=16.0001,end_s=31.))
    result = collect(values,cue_scores={i:float(i) for i in range(len(values))})[0]
    assert 16. in [x.t for x in result]


@pytest.mark.parametrize('fast',[True,False])
def test_both_producers_select_and_cache_bound_scores(pipeline,monkeypatch,fast):
    path, importer, _ = pipeline
    values = phrases()
    importer.get_phrases.return_value = values
    importer.get_beatgrid.return_value = [dict(time=index * .5, beat=index % 4 + 1)
                                          for index in range(480)]
    # PSSI-Cue-Scoring braucht zusätzlich die bestätigte Taktposition.
    from tests.test_neural_anchor_integration import windows
    aligned_windows = windows()
    for window in aligned_windows:
        for item in window['results']:
            item['decoder']['first_downbeat'] -= .2
            for event in item['decoder']['beats']:
                event['time_s'] -= .2
    monkeypatch.setattr(analysis, '_collect_beat_windows', lambda *a: aligned_windows)
    monkeypatch.setattr(analysis, 'estimate_first_downbeat', lambda *a, **k: (0., .6))
    importer.get_track_data.return_value = RekordboxTrackData(bpm=120. if fast else None,
                                                             duration=240.,camelot_code='8A')
    monkeypatch.setattr(analysis,'_get_file_duration',lambda *a:240.)
    monkeypatch.setattr(analysis.librosa,'load',lambda *a,**k:(np.ones(22050*240,np.float32),22050))
    monkeypatch.setattr(analysis, '_load_analysis_audio', lambda *a, **k: (
        np.ones(round(min(k.get('duration', 240.), 240. - k.get('offset', 0.))
                      * k.get('sr', 22050)), np.float32), k.get('sr', 22050)))
    monkeypatch.setattr(analysis,'get_cached_track',lambda *a,**k:None)
    monkeypatch.setattr(analysis,'_persist_analysis_result',lambda *a:True)
    monkeypatch.setattr(analysis,'_kandidaten_berechnen',_REAL_CANDIDATES)
    monkeypatch.setattr(mc,'measure_candidate_window',lambda *a,**k:None)
    monkeypatch.setattr(mc,'KANDIDATEN_MAX_JE_SEITE',4)
    @contextmanager
    def session():
        yield SimpleNamespace(config=cs.model_config())
    monkeypatch.setattr(cs,'session',session)
    def structure(audio,sr,bpm,genre,**kwargs):
        assert kwargs['cue_context']['verified_grid'] is True
        results = scored(kwargs['cue_context']['candidates'])
        cs._validate_results(results)
        return TrackStructure(sections=[TrackSection('main',0.,240.,0,120,50.)],cue_diagnostics=results)
    monkeypatch.setattr(analysis,'analyze_structure',structure)
    track = analysis.analyze_track(str(path))
    assert track is not None
    assert 192. in [c['t'] for c in track.mix_in_candidates]
    assert all('raw_score' not in c for c in track.mix_in_candidates)
    assert track.neural_analysis['windows'][0]['results'][-1]['raw_score'] == 11.
    assert caching.CACHE_VERSION == 181
    key = caching.generate_cache_key(str(path),track.rekordbox_signature)
    assert caching.cache_track(key,track)
    cached = caching.get_cached_track(key,file_path=str(path))
    assert cached.mix_in_candidates == track.mix_in_candidates
    assert cached.neural_analysis == track.neural_analysis

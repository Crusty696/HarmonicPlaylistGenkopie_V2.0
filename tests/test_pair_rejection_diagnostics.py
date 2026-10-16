"""Ablehnungsgruende muessen den echten Rankinglauf erklaeren, nicht ersetzen."""
from copy import deepcopy

from hpg_core import pair_candidates as pc, playlist as pl
from tests.fixtures.track_factories import make_track


def tracks():
    result = [make_track(filePath=f'{x}.wav', fileName=f'{x}.wav',
                         genre='Psytrance', detected_genre='Psytrance') for x in 'ab']
    for track in result:
        track.analysis_coverage = [{'start': 0.0, 'end': track.duration}]
    return result


def test_diagnose_aendert_qualifizierte_kandidaten_nicht():
    a, b = tracks()
    baseline = pc.rank_pair_candidates(a, b, wahl={})
    reasons = ['alt']
    actual = pc.rank_pair_candidates(a, b, wahl={}, rejection_reasons=reasons)
    assert baseline
    assert [p.to_dict() for p in actual] == [p.to_dict() for p in baseline]
    assert reasons == []


def test_tempo_grund_enthaelt_effektiven_abstand_und_grenze():
    a, b = tracks()
    b.bpm = a.bpm + 8
    reasons = []
    assert pc.rank_pair_candidates(a, b, bpm_tolerance=2, rejection_reasons=reasons) == []
    assert reasons[0] == 'Tempoabstand zu groß'
    assert '8' in reasons[1] and '2' in reasons[1]


def test_niedrige_konfidenz_allein_erfindet_keinen_ablehnungsgrund():
    a, b = tracks()
    b.downbeat_confidence = 0.01
    reasons = []
    assert pc.rank_pair_candidates(a, b, rejection_reasons=reasons)
    assert not reasons


def test_fehlende_beatmerkmale_erklaeren_taktunsicherheit():
    a, b = tracks()
    b.downbeat_confidence = 0.01
    b.mix_in_candidates = deepcopy(b.mix_in_candidates)
    for c in b.mix_in_candidates:
        c.groove_pattern_lokal = []
        c.bass_pattern_lokal = []
        c.kick_aktiv = None
        c.traegt_allein = None
    reasons = []
    assert not pc.rank_pair_candidates(a, b, rejection_reasons=reasons)
    assert reasons[0] == 'Taktanfang unsicher'
    assert 'Groove' in '\n'.join(reasons)
    assert 'b.wav' in '\n'.join(reasons)


def test_fehlende_messwerte_sind_keine_erfundene_taktunsicherheit():
    a, b = tracks()
    b.mix_in_candidates = deepcopy(b.mix_in_candidates)
    for c in b.mix_in_candidates:
        c.timbre_fingerprint_lokal = []
    reasons = []
    assert not pc.rank_pair_candidates(a, b, rejection_reasons=reasons)
    assert reasons[0] == 'Messwerte fehlen'
    assert 'Klangfarbe' in '\n'.join(reasons)
    assert 'Taktanfang' not in '\n'.join(reasons)


def test_refinement_transportiert_grund_bis_zur_empfehlung():
    a, b = tracks()
    b.bpm = a.bpm + 8
    context = pl.resolve_run_scoring_context('Harmonic Flow', {})
    occurrences = tuple(pl.TrackOccurrence('test', i, t) for i, t in enumerate((a, b)))
    order, ranked = pl._refine_order_with_chain(occurrences, 'Harmonic Flow', 2, context, {})
    result = pl._build_generation_result(run_id='test', mode='Harmonic Flow', occurrences=order,
        input_tracks=2, invalid_bpm_excluded=0, bpm_tolerance=2, context=context,
        choice_snapshot={}, ranked_boundaries=ranked)
    assert result.recommendations[0].plan is None
    assert result.recommendations[0].notes.startswith('Tempoabstand zu groß\n')
    assert result.path_stats.planned == 0


def test_kettenkonflikt_wird_nicht_als_messausfall_erklaert():
    a, b = tracks()
    occurrences = tuple(pl.TrackOccurrence('test', i, t) for i, t in enumerate((a, b)))
    context = pl.resolve_run_scoring_context('Harmonic Flow', {})
    snapshots, maps, _ = pl._rank_fixed_boundaries(occurrences, 2, context, {})
    assert snapshots[0]
    rec = pl._recommendation_snapshot(0, occurrences, snapshots[0], None, None, False,
                                      maps[0], 2, context)
    assert rec.notes.startswith('Mixpunkte passen nicht zur Kette\n')
    assert rec.plan is None

"""Messausfälle dürfen weder schlechte noch bessere Passung vortäuschen."""
import json

import pytest

from hpg_core.mix_analysis import TransitionSample, cluster_bootstrap_auc, deltas_between
from tools import mix_mining
from tools.mix_mining import (
    baue_ergebnis, berechne_auc_grenzen, berechne_auc_richtung,
    berechne_toleranzen, bewerte_holdout, kombinierter_score,
)


def test_leeres_rhythmusfenster_bleibt_unbekannt_bei_messbarem_klang():
    # Originalbefund vor Marke 750 s: beide Rhythmusmuster leer, MFCC vorhanden.
    before = TransitionSample(timbre=[1., 0.])
    after = TransitionSample(bass_pattern=[1.] * 16, timbre=[1., 0.])
    delta = deltas_between(before, after)
    assert 'groove_sim' not in delta
    assert delta['timbre_sim'] == pytest.approx(1.)
    assert berechne_toleranzen([delta])['groove_sim_min'] is None
    # Der gelernte Gesamtscore braucht alle gewichteten Faktoren. Eine
    # Umverteilung auf Klang allein würde den Messausfall zur besseren Passung machen.
    assert kombinierter_score(delta, {'groove_sim': .5, 'timbre_sim': .5}, {}) is None


def test_echte_nullmessung_bleibt_erhalten():
    delta = deltas_between(TransitionSample(timbre=[1., 0.]),
                           TransitionSample(timbre=[0., 1.]))
    assert delta['timbre_sim'] == 0.
    assert 'timbre_sim' not in deltas_between(TransitionSample(), TransitionSample())


def test_fehlende_faktoren_verzerren_auc_und_toleranz_nicht():
    positives = [{'groove_sim': .9}, {}]
    negatives = [{'groove_sim': .2}, {}]
    assert berechne_auc_richtung(positives, negatives)['groove_sim'] == 1.
    assert berechne_toleranzen(positives)['groove_sim_min'] == .9
    result = baue_ergebnis('Psytrance', positives, negatives, None)
    assert result['messwerte_je_faktor']['groove_sim'] == {'uebergaenge': 1, 'zufallspaare': 1}
    assert result['messwerte_je_faktor']['timbre_sim'] == {'uebergaenge': 0, 'zufallspaare': 0}
    assert result['gewichte']['timbre_weight'] == 0.


def test_leere_cluster_liefern_keine_belastbare_trennung():
    intervals = berechne_auc_grenzen([[{}], [{}]], [[{}], [{}]])
    assert intervals['groove_sim'] == (.5, 0., 1.)


def test_fehlender_gewichteter_faktor_erhoeht_gesamtscore_nicht():
    weights = {'groove_sim': .5, 'timbre_sim': .5}
    assert kombinierter_score({'groove_sim': 0., 'timbre_sim': 1.}, weights, {}) == .5
    assert kombinierter_score({'timbre_sim': 1.}, weights, {}) is None
    assert kombinierter_score({}, weights, {}) is None
    assert kombinierter_score({'timbre_sim': 1.}, {}, {}) is None


def test_ungewichteter_fehlender_faktor_und_echte_null_bleiben_gueltig():
    assert kombinierter_score({'timbre_sim': 0.}, {'timbre_sim': 1., 'groove_sim': 0.}, {}) == 0.


@pytest.mark.parametrize('invalid', [None, float('nan'), float('inf')])
def test_ungueltiger_gewichteter_faktor_bleibt_unbekannt(invalid):
    assert kombinierter_score({'timbre_sim': invalid}, {'timbre_sim': 1.}, {}) is None


def test_holdout_zaehlt_ausfaelle_und_vergleicht_nur_denselben_gesamtscore():
    weights = {'groove_sim': .5, 'timbre_sim': .5}
    # Beide vollständig gemessenen Klassen haben denselben Score. Das
    # zusätzliche positive Fenster darf allein durch fehlenden Groove nicht gewinnen.
    valid = {'groove_sim': 0., 'timbre_sim': 1.}
    passed, counts = bewerte_holdout([valid, {'timbre_sim': 1.}], [valid], weights, {})
    assert passed is False
    assert counts == {
        'uebergaenge': {'verwendet': 1, 'ausgelassen': 1},
        'zufallspaare': {'verwendet': 1, 'ausgelassen': 0},
    }


def test_holdout_ohne_messbare_klasse_bleibt_unbewertet():
    passed, counts = bewerte_holdout([{}], [{'groove_sim': .2}], {'groove_sim': 1.}, {})
    assert passed is None
    assert counts['uebergaenge'] == {'verwendet': 0, 'ausgelassen': 1}


def test_ein_gemessener_cluster_plus_leere_cluster_bleibt_unbelastbar():
    intervals = berechne_auc_grenzen(
        [[{'groove_sim': .9}], [{}], [{}]],
        [[{'groove_sim': .2}], [{}], [{}]],
    )
    assert intervals['groove_sim'] == (1., 0., 1.)


def test_einseitige_cluster_duerfen_keine_kuenstliche_trennung_erzeugen():
    assert cluster_bootstrap_auc([[.9], []], [[], [.2]]) == (.5, 0., 1.)


def test_bootstrap_erhaelt_paarung_der_klassen_im_selben_mix():
    # Innerhalb jedes Mixes sind beide Klassen identisch. Gemeinsames Resampling
    # erhält deshalb in jeder Ziehung exakt AUC .5, trotz verschiedener Mixniveaus.
    positives = [[.1], [.9], [.4]]
    assert cluster_bootstrap_auc(positives, [[.1], [.9], [.4]], ziehungen=50) == (.5, .5, .5)


def test_bootstrap_verwirft_nicht_zuordenbare_clusterlisten():
    with pytest.raises(ValueError, match='dieselben Mixe'):
        cluster_bootstrap_auc([[.9], [.8]], [[.2]])


def test_cli_schreibt_holdout_verwendungszahlen_ohne_audio(monkeypatch, tmp_path):
    positive = {'groove_sim': .9, 'timbre_sim': .9}
    negative = {'groove_sim': .1, 'timbre_sim': .1}
    monkeypatch.setattr(mix_mining, 'verarbeite_mix', lambda path:
                        ([positive, {'timbre_sim': .9}], []) if path == 'holdout'
                        else ([positive], []))
    monkeypatch.setattr(mix_mining, 'zufallsdeltas_je_mix', lambda *a: [[negative]])
    monkeypatch.setattr(mix_mining, 'zufallsdeltas_aus_fenstern', lambda *a, **kw: [negative, {}])
    monkeypatch.setattr(mix_mining, 'berechne_auc_grenzen', lambda *a:
                        {'groove_sim': (1., 1., 1.), 'timbre_sim': (1., 1., 1.)})
    output = tmp_path / 'report.json'
    assert mix_mining.main(['--genre', 'Psytrance', '--mix', 'train',
                           '--holdout', 'holdout', '--out', str(output)]) == 0
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['holdout'] is True
    assert report['holdout_messwerte'] == {
        'uebergaenge': {'verwendet': 1, 'ausgelassen': 1},
        'zufallspaare': {'verwendet': 1, 'ausgelassen': 1},
    }

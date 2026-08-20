"""Tests fuer die paarweisen Uebergangs-Vergleiche."""
import pytest

from hpg_core.models import Track
from hpg_core.transition_features import (
    bass_continuity,
    cosine_similarity,
    groove_match,
    mood_match,
    timbre_match,
)


@pytest.fixture(autouse=True)
def feste_toleranzen(monkeypatch):
    """Entkoppelt diese Tests von den ausgelieferten Kalibrierdaten.

    `mood_match` und `bass_continuity` lesen ihre Schwellen ueber
    `get_tolerances` aus `hpg_core/data/transition_tolerances.json`. Diese
    Datei wird aus echten DJ-Mixen neu gelernt — als die gemessenen Werte
    einzogen, fiel `brightness_delta_max` von 60 auf 11,3 und ein Test
    kippte, obwohl die geprueften Funktionen sich nicht geaendert hatten.

    Diese Datei prueft das VERHALTEN der Vergleichsfunktionen, nicht den
    Stand der Kalibrierung. Deshalb hier fest die Defaults aus genres.py.
    Wer die gelernten Werte pruefen will, tut das in test_tolerances.py.
    """
    import hpg_core.transition_features as tf
    from hpg_core.genres import GENRE_TRANSITION_TOLERANCES

    monkeypatch.setattr(
        tf, "get_tolerances", lambda genre: GENRE_TRANSITION_TOLERANCES.get(
            genre, GENRE_TRANSITION_TOLERANCES["Psytrance"]
        )
    )


def _track(**kwargs) -> Track:
    t = Track(filePath=kwargs.pop("path", "a.mp3"), fileName="a.mp3")
    for k, v in kwargs.items():
        setattr(t, k, v)
    return t


def _gerade():
    p = [0.0] * 16
    for s in (0, 4, 8, 12):
        p[s] = 0.25
    return p


def _offbeat():
    p = [0.0] * 16
    for s in (2, 6, 10, 14):
        p[s] = 0.25
    return p


def test_cosine_similarity_identisch_ist_eins():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_ist_null():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_leer_ist_none():
    assert cosine_similarity([], [1.0]) is None


def test_groove_match_gleiches_muster_ist_hoch():
    a = _track(groove_pattern=_gerade(), bass_pattern=_gerade())
    b = _track(groove_pattern=_gerade(), bass_pattern=_gerade())
    assert groove_match(a, b, "Psytrance") > 0.95


def test_groove_match_offbeat_gegen_gerade_ist_niedrig():
    a = _track(groove_pattern=_gerade(), bass_pattern=_gerade())
    b = _track(groove_pattern=_offbeat(), bass_pattern=_offbeat())
    assert groove_match(a, b, "Psytrance") < 0.2


def test_groove_match_ohne_muster_ist_none():
    a = _track(groove_pattern=[], bass_pattern=[])
    b = _track(groove_pattern=_gerade(), bass_pattern=_gerade())
    assert groove_match(a, b, "Psytrance") is None


def test_bass_continuity_gleicher_druck_ist_hoch():
    a = _track(sub_energy=0.30, bass_punch=3.0)
    b = _track(sub_energy=0.30, bass_punch=3.0)
    assert bass_continuity(a, b, "Psytrance") > 0.95


def test_bass_continuity_grosser_sprung_ist_niedrig():
    a = _track(sub_energy=0.05, bass_punch=1.2)
    b = _track(sub_energy=0.50, bass_punch=6.0)
    assert bass_continuity(a, b, "Psytrance") < 0.5


def test_bass_continuity_ohne_werte_ist_none():
    a = _track(sub_energy=0.0, bass_punch=0.0)
    b = _track(sub_energy=0.0, bass_punch=0.0)
    assert bass_continuity(a, b, "Psytrance") is None


def test_timbre_match_ohne_fingerprint_ist_none():
    a = _track(timbre_fingerprint=[])
    b = _track(timbre_fingerprint=[1.0, 2.0])
    assert timbre_match(a, b, "Psytrance") is None


def test_timbre_match_identisch_ist_hoch():
    fp = [1.0, 2.0, 3.0, 4.0]
    assert timbre_match(_track(timbre_fingerprint=fp),
                        _track(timbre_fingerprint=fp), "Psytrance") > 0.95


def test_mood_match_gleiche_stimmung_ist_hoch(feste_toleranzen):
    a = _track(brightness=50, spectral_flatness=0.05, keyMode="Minor")
    b = _track(brightness=52, spectral_flatness=0.05, keyMode="Minor")
    assert mood_match(a, b, "Psytrance") > 0.9


def test_mood_match_heller_sprung_ist_niedriger():
    a = _track(brightness=10, spectral_flatness=0.02, keyMode="Minor")
    b = _track(brightness=95, spectral_flatness=0.02, keyMode="Major")
    assert mood_match(a, b, "Psytrance") < 0.5


def test_mood_match_ohne_brightness_ist_none():
    a = _track(brightness=0, spectral_flatness=0.0)
    b = _track(brightness=0, spectral_flatness=0.0)
    assert mood_match(a, b, "Psytrance") is None


def test_ein_track_ohne_groove_daten_macht_alle_faktoren_unbestimmbar():
    """Regression: frueher pruefte die None-Bedingung mit UND statt ODER.

    compute_groove_fields liefert bei zu niedriger downbeat_confidence ein
    leeres GrooveFeatures() — sub_energy und bass_punch sind dann 0.0, und
    analysis.py setzt brightness bei gescheiterter Feature-Phase auf 0. Ein
    solcher Track gegen einen normal analysierten ergab 0.0 bzw. 0.2, also
    die haerteste Strafe fuer genau die Tracks, die die Umverteilung
    schuetzen soll.
    """
    voll = _track(groove_pattern=_gerade(), bass_pattern=_gerade(),
                  sub_energy=0.5, bass_punch=2.0, brightness=55,
                  spectral_flatness=0.05, timbre_fingerprint=[1.0, 2.0, 3.0])
    leer = _track(groove_pattern=[], bass_pattern=[],
                  sub_energy=0.0, bass_punch=0.0, brightness=0,
                  spectral_flatness=0.0, timbre_fingerprint=[])

    assert groove_match(voll, leer, "Psytrance") is None
    assert bass_continuity(voll, leer, "Psytrance") is None
    assert mood_match(voll, leer, "Psytrance") is None
    assert timbre_match(voll, leer, "Psytrance") is None
    # und in der Gegenrichtung
    assert bass_continuity(leer, voll, "Psytrance") is None
    assert mood_match(leer, voll, "Psytrance") is None


# --- Mechanismus 1: Bassdruck an der Nahtstelle (Spec 5.3) ---


def _sektion(label, start, ende, sub=None, punch=None):
    """Baut ein Section-Dict; sub/punch nur setzen, wenn angegeben."""
    d = {
        "label": label,
        "start_time": start,
        "end_time": ende,
        "avg_energy": 5.0,
        "avg_bass": 40.0,
        "avg_mids": 40.0,
        "avg_highs": 20.0,
        "percussive_ratio": 0.5,
        "spectral_flatness": 0.05,
        "analysis_status": "ok",
    }
    if sub is not None:
        d["sub_energy"] = sub
    if punch is not None:
        d["bass_punch"] = punch
    return d


def test_naht_werte_out_nimmt_die_sektion_am_mix_out_nicht_das_outro():
    """Gemessen wird, wo der Mix-Out sitzt — nicht die letzte Sektion.

    An 200 analysierten Tracks liegt der Mix-Out im Median 76 s VOR dem
    Outro. Die Abkuerzung "letzte Nicht-Intro-Sektion" traf in 169 von 200
    Faellen das Outro, also eine Stelle, an der der Uebergang laengst
    vorbei ist.
    """
    from hpg_core.transition_features import _naht_werte

    t = _track(sub_energy=0.30, bass_punch=3.0, mix_out_point=120.0, sections=[
        _sektion("intro", 0.0, 30.0, sub=0.10, punch=1.0),
        _sektion("main", 30.0, 200.0, sub=0.40, punch=2.0),
        _sektion("outro", 200.0, 260.0, sub=0.55, punch=4.0),
    ])

    assert _naht_werte(t, "out") == (0.40, 2.0)


def test_naht_werte_out_nimmt_auch_einen_breakdown_wenn_die_naht_dort_liegt():
    """Kein Label wird bevorzugt — es zaehlt allein der Mixpunkt.

    Die Gegenprobe zur verworfenen Abkuerzung "letzte Main/Drop-Sektion":
    liegt der Mix-Out real in einem Breakdown, ist dessen duenner Bass die
    Wahrheit ueber die Naht und nicht ein spaeterer Drop.
    """
    from hpg_core.transition_features import _naht_werte

    t = _track(sub_energy=0.30, bass_punch=3.0, mix_out_point=215.0, sections=[
        _sektion("main", 0.0, 200.0, sub=0.40, punch=2.0),
        _sektion("breakdown", 200.0, 230.0, sub=0.12, punch=1.1),
        _sektion("drop", 230.0, 300.0, sub=0.60, punch=5.0),
    ])

    assert _naht_werte(t, "out") == (0.12, 1.1)


def test_naht_werte_in_nimmt_die_sektion_am_mix_in():
    from hpg_core.transition_features import _naht_werte

    t = _track(sub_energy=0.30, bass_punch=3.0, mix_in_point=45.0, sections=[
        _sektion("intro", 0.0, 30.0, sub=0.10, punch=1.0),
        _sektion("build", 30.0, 60.0, sub=0.45, punch=2.5),
        _sektion("main", 60.0, 200.0, sub=0.40, punch=2.0),
    ])

    assert _naht_werte(t, "in") == (0.45, 2.5)


def test_naht_werte_ohne_gesetzten_mixpunkt_faellt_auf_trackmittel_zurueck():
    """MIX_POINT_UNSET ist -1.0; 0.0 waere ein gueltiger Mixpunkt."""
    from hpg_core.transition_features import _naht_werte

    t = _track(sub_energy=0.30, bass_punch=3.0, mix_out_point=-1.0, sections=[
        _sektion("main", 0.0, 200.0, sub=0.40, punch=2.0),
    ])

    assert _naht_werte(t, "out") == (0.30, 3.0)


def test_naht_werte_faellt_ohne_sektionen_auf_trackmittel_zurueck():
    from hpg_core.transition_features import _naht_werte

    t = _track(sub_energy=0.30, bass_punch=3.0, sections=[])

    assert _naht_werte(t, "out") == (0.30, 3.0)
    assert _naht_werte(t, "in") == (0.30, 3.0)


def test_naht_werte_faellt_ohne_schluessel_auf_trackmittel_zurueck():
    """Zu kurze Sektionen bekommen die Schluessel gar nicht erst."""
    from hpg_core.transition_features import _naht_werte

    t = _track(sub_energy=0.30, bass_punch=3.0, sections=[
        _sektion("main", 30.0, 31.0),
        _sektion("outro", 31.0, 32.0),
    ])

    assert _naht_werte(t, "out") == (0.30, 3.0)
    assert _naht_werte(t, "in") == (0.30, 3.0)


def test_naht_werte_nur_intro_faellt_auf_trackmittel_zurueck():
    from hpg_core.transition_features import _naht_werte

    t = _track(sub_energy=0.30, bass_punch=3.0, sections=[
        _sektion("intro", 0.0, 30.0, sub=0.10, punch=1.0),
    ])

    assert _naht_werte(t, "out") == (0.30, 3.0)
    assert _naht_werte(t, "in") == (0.30, 3.0)


def test_bass_continuity_misst_die_nahtstelle_nicht_das_trackmittel():
    """Gleiches Trackmittel, weit auseinanderliegende Nahtstellen.

    Beide Paare haben identische Trackmittel. Nur die Nahtstellen
    unterscheiden sich — genau das muss den Unterschied machen.
    """
    # Die Mixpunkte legen fest, WO die Naht liegt — ohne sie faellt
    # _naht_werte auf das Trackmittel zurueck und der Test pruefte nichts.
    gleich_a = _track(sub_energy=0.30, bass_punch=3.0, mix_out_point=150.0, sections=[
        _sektion("intro", 0.0, 30.0, sub=0.05, punch=1.0),
        _sektion("main", 30.0, 260.0, sub=0.30, punch=3.0),
    ])
    gleich_b = _track(sub_energy=0.30, bass_punch=3.0, mix_in_point=150.0, sections=[
        _sektion("intro", 0.0, 30.0, sub=0.05, punch=1.0),
        _sektion("main", 30.0, 260.0, sub=0.30, punch=3.0),
    ])

    weit_a = _track(sub_energy=0.30, bass_punch=3.0, mix_out_point=150.0, sections=[
        _sektion("intro", 0.0, 30.0, sub=0.05, punch=1.0),
        _sektion("main", 30.0, 260.0, sub=0.60, punch=5.0),
    ])
    weit_b = _track(sub_energy=0.30, bass_punch=3.0, mix_in_point=150.0, sections=[
        _sektion("intro", 0.0, 30.0, sub=0.05, punch=1.0),
        _sektion("main", 30.0, 260.0, sub=0.10, punch=1.2),
    ])

    nah = bass_continuity(gleich_a, gleich_b, "Psytrance")
    fern = bass_continuity(weit_a, weit_b, "Psytrance")

    assert nah > 0.95
    assert fern < 0.5
    assert nah - fern > 0.4


def test_bass_continuity_ohne_sektionen_bleibt_beim_trackmittel():
    a = _track(sub_energy=0.30, bass_punch=3.0, sections=[])
    b = _track(sub_energy=0.30, bass_punch=3.0, sections=[])

    assert bass_continuity(a, b, "Psytrance") > 0.95


def test_bass_continuity_none_regel_gilt_trotz_sektionen():
    """Das Gate haengt am Trackmittel, nicht an den Sektionswerten."""
    a = _track(sub_energy=0.0, bass_punch=0.0, sections=[
        _sektion("main", 30.0, 200.0, sub=0.40, punch=2.0),
    ])
    b = _track(sub_energy=0.30, bass_punch=3.0, sections=[
        _sektion("main", 30.0, 200.0, sub=0.40, punch=2.0),
    ])

    assert bass_continuity(a, b, "Psytrance") is None
    assert bass_continuity(b, a, "Psytrance") is None

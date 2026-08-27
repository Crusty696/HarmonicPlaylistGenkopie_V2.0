"""Tests fuer das Laden der Uebergangs-Toleranzen."""
import json
import multiprocessing
import os

import pytest

from hpg_core.genres import CANONICAL_GENRES, GENRE_TRANSITION_TOLERANCES
from hpg_core.tolerances import get_tolerances, load_tolerances


def _prozess_aendert_toleranzen(datei, start, ergebnis, modus):
    os.environ["HPG_TOLERANCES_FILE"] = str(datei)
    from hpg_core import tolerances

    tolerances.reset_cache()
    start.wait(10)
    try:
        if modus == "track":
            tolerances.write_override({"groove_weight": 0.20})
        elif modus == "kandidaten":
            tolerances.write_override_kandidaten(
                {"kandidaten_loudness_weight": 0.20}
            )
        elif modus == "remove":
            tolerances.remove_candidate_overrides()
        else:  # pragma: no cover - nur Testhelfervertrag
            raise AssertionError(modus)
        ergebnis.put(None)
    except Exception as exc:  # pragma: no cover - Elternprozess prueft Ergebnis
        ergebnis.put(repr(exc))


def test_alle_kanonischen_genres_haben_toleranzen():
    assert set(GENRE_TRANSITION_TOLERANCES) == set(CANONICAL_GENRES)


def test_gewichte_summieren_auf_eins():
    for genre, werte in GENRE_TRANSITION_TOLERANCES.items():
        summe = sum(
            werte[k] for k in (
                "harmonic_weight", "bpm_weight", "energy_weight", "genre_weight",
                "groove_weight", "bass_weight", "timbre_weight", "mood_weight",
            )
        )
        assert summe == pytest.approx(1.0, abs=1e-6), f"{genre}: {summe}"


def test_get_tolerances_unbekanntes_genre_faellt_auf_default():
    werte = get_tolerances("Gibt Es Nicht")
    assert "groove_weight" in werte


def test_vollstaendiger_override_gewichtskreis_schlaegt_default(tmp_path, monkeypatch):
    datei = tmp_path / "transition_tolerances.json"
    track_gewichte = {
        key: GENRE_TRANSITION_TOLERANCES["Psytrance"][key]
        for key in (
            "harmonic_weight", "bpm_weight", "energy_weight", "genre_weight",
            "groove_weight", "bass_weight", "timbre_weight", "mood_weight",
        )
    }
    track_gewichte["groove_weight"] = 0.42
    track_gewichte["harmonic_weight"] -= 0.12
    datei.write_text(
        json.dumps({"Psytrance": track_gewichte}), encoding="utf-8"
    )
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    werte = load_tolerances()

    assert werte["Psytrance"]["groove_weight"] == 0.42
    # nicht ueberschriebene Schluessel bleiben erhalten
    assert "harmonic_weight" in werte["Psytrance"]


def test_unvollstaendiger_track_gewichtskreis_wird_atomar_ignoriert(
    tmp_path, monkeypatch
):
    datei = tmp_path / "transition_tolerances.json"
    datei.write_text(
        json.dumps({"Psytrance": {"groove_weight": 0.42}}), encoding="utf-8"
    )
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    werte = load_tolerances()

    assert werte["Psytrance"]["groove_weight"] == pytest.approx(
        GENRE_TRANSITION_TOLERANCES["Psytrance"]["groove_weight"]
    )


def test_kaputtes_json_faellt_auf_defaults_ohne_ausnahme(tmp_path, monkeypatch):
    datei = tmp_path / "transition_tolerances.json"
    datei.write_text("{ das ist kein json", encoding="utf-8")
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    werte = load_tolerances()

    assert set(werte) == set(CANONICAL_GENRES)


@pytest.mark.parametrize("wert", [float("nan"), float("inf"), -0.1, "0.2", True])
def test_ungueltiges_override_gewicht_faellt_auf_default(
    tmp_path, monkeypatch, wert
):
    datei = tmp_path / "transition_tolerances.json"
    datei.write_text(
        json.dumps({"Psytrance": {"groove_weight": wert}}), encoding="utf-8"
    )
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    werte = load_tolerances()

    assert werte["Psytrance"]["groove_weight"] == pytest.approx(
        GENRE_TRANSITION_TOLERANCES["Psytrance"]["groove_weight"]
    )


def test_ungueltiger_kandidatenkreis_verwirft_keinen_gueltigen_trackkreis(
    tmp_path, monkeypatch
):
    defaults = GENRE_TRANSITION_TOLERANCES["Psytrance"]
    track = {
        key: defaults[key]
        for key in (
            "harmonic_weight", "bpm_weight", "energy_weight", "genre_weight",
            "groove_weight", "bass_weight", "timbre_weight", "mood_weight",
        )
    }
    kandidaten = {
        key: defaults[key]
        for key in defaults if key.startswith("kandidaten_") and key.endswith("_weight")
    }
    track["groove_weight"] += 0.05
    track["harmonic_weight"] -= 0.05
    kandidaten["kandidaten_groove_weight"] += 0.20
    datei = tmp_path / "transition_tolerances.json"
    datei.write_text(
        json.dumps({"Psytrance": {**track, **kandidaten}}), encoding="utf-8"
    )
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    werte = load_tolerances()["Psytrance"]

    assert werte["groove_weight"] == pytest.approx(track["groove_weight"])
    assert werte["kandidaten_groove_weight"] == pytest.approx(
        defaults["kandidaten_groove_weight"]
    )


@pytest.mark.parametrize(
    "schluessel,wert",
    [
        ("groove_sim_floor", -0.01),
        ("groove_sim_floor", 1.01),
        ("groove_sim_floor", "0.5"),
        ("groove_sim_floor", True),
        ("bass_delta_max", 0.0),
        ("bass_delta_max", float("nan")),
        ("brightness_delta_max", -1.0),
        ("brightness_delta_max", float("inf")),
    ],
)
def test_ungueltiger_nichtgewicht_grenzwert_wird_ignoriert(
    tmp_path, monkeypatch, schluessel, wert
):
    datei = tmp_path / "transition_tolerances.json"
    datei.write_text(
        json.dumps({"Psytrance": {schluessel: wert}}), encoding="utf-8"
    )
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    werte = load_tolerances()["Psytrance"]

    assert werte[schluessel] == pytest.approx(
        GENRE_TRANSITION_TOLERANCES["Psytrance"][schluessel]
    )


@pytest.mark.parametrize(
    "schluessel,wert",
    [
        ("groove_sim_floor", 0.0),
        ("groove_sim_floor", 1.0),
        ("bass_delta_max", 0.01),
        ("brightness_delta_max", 120.0),
    ],
)
def test_gueltiger_nichtgewicht_grenzwert_wird_uebernommen(
    tmp_path, monkeypatch, schluessel, wert
):
    datei = tmp_path / "transition_tolerances.json"
    datei.write_text(
        json.dumps({"Psytrance": {schluessel: wert}}), encoding="utf-8"
    )
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    assert load_tolerances()["Psytrance"][schluessel] == pytest.approx(wert)


def test_unbekannter_schluessel_wird_nicht_weitergereicht(tmp_path, monkeypatch):
    datei = tmp_path / "transition_tolerances.json"
    datei.write_text(
        json.dumps({"Psytrance": {"unbekannt": "kaputt"}}), encoding="utf-8"
    )
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    assert "unbekannt" not in load_tolerances()["Psytrance"]


@pytest.mark.parametrize("wert", [float("nan"), float("inf"), -0.1, "0.2", True])
def test_write_override_verwirft_ungueltige_gewichte(
    tmp_path, monkeypatch, wert
):
    from hpg_core.tolerances import write_override

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    with pytest.raises(ValueError):
        write_override({"groove_weight": wert})

    assert not datei.exists()


def test_write_override_haelt_summe_bei_eins(tmp_path, monkeypatch):
    from hpg_core.tolerances import reset_cache, write_override

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    write_override({"groove_weight": 0.20, "bass_weight": 0.10,
                    "timbre_weight": 0.05, "mood_weight": 0.05})
    reset_cache()

    werte = load_tolerances()
    summe = sum(werte["Psytrance"][k] for k in (
        "harmonic_weight", "bpm_weight", "energy_weight", "genre_weight",
        "groove_weight", "bass_weight", "timbre_weight", "mood_weight"))
    assert summe == pytest.approx(1.0, abs=1e-6)


def test_partielle_legacy_track_api_schreibt_vollstaendigen_kreis(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    tolerances.write_override({"groove_weight": 0.20})

    for genre, werte in load_tolerances().items():
        assert set(tolerances.TRACK_GEWICHT_SCHLUESSEL) <= set(werte)
        assert werte["groove_weight"] == pytest.approx(0.20)
        assert sum(
            werte[key] for key in tolerances.TRACK_GEWICHT_SCHLUESSEL
        ) == pytest.approx(1.0, abs=1e-12)


def test_write_override_kandidaten_haelt_summe_eins(tmp_path, monkeypatch):
    from hpg_core.tolerances import (
        KANDIDATEN_GEWICHT_SCHLUESSEL, reset_cache, write_override, write_override_kandidaten,
    )
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(tmp_path / "tol.json"))
    reset_cache()
    write_override_kandidaten({"kandidaten_loudness_weight": 0.20})
    reset_cache()
    w = get_tolerances("Psytrance")
    assert w["kandidaten_loudness_weight"] == pytest.approx(0.20)
    assert sum(w[k] for k in KANDIDATEN_GEWICHT_SCHLUESSEL) == pytest.approx(1.0)
    assert w["groove_weight"] == pytest.approx(0.300)          # Track-Gewichte unberuehrt
    with pytest.raises(ValueError):
        write_override_kandidaten({"kandidaten_loudness_weight": 1.2})
    with pytest.raises(ValueError):
        write_override_kandidaten({"groove_weight": 0.3})
    # Track-Regler danach: Kandidaten-Gewichte ueberleben write_override
    write_override({"groove_weight": 0.4, "bass_weight": 0.1, "timbre_weight": 0.05, "mood_weight": 0.05})
    reset_cache()
    w2 = get_tolerances("Psytrance")
    assert w2["kandidaten_loudness_weight"] == pytest.approx(0.20)
    assert w2["groove_weight"] == pytest.approx(0.4)
    reset_cache()


def test_write_overrides_atomically_schreibt_beide_kreise_mit_einem_replace(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    replace_original = tolerances.os.replace
    replace_aufrufe = []
    fsync_aufrufe = []

    def replace_spy(quelle, ziel):
        replace_aufrufe.append((quelle, ziel))
        return replace_original(quelle, ziel)

    monkeypatch.setattr(tolerances.os, "replace", replace_spy)
    monkeypatch.setattr(tolerances.os, "fsync", fsync_aufrufe.append)
    tolerances.write_overrides_atomically(
        {
            "groove_weight": 0.20,
            "bass_weight": 0.10,
            "timbre_weight": 0.05,
            "mood_weight": 0.05,
        },
        {"kandidaten_loudness_weight": 0.20},
    )

    assert len(replace_aufrufe) == 1
    assert len(fsync_aufrufe) == 1
    daten = json.loads(datei.read_text(encoding="utf-8"))
    psy = daten["Psytrance"]
    assert sum(psy[k] for k in tolerances.TRACK_GEWICHT_SCHLUESSEL) == pytest.approx(1.0)
    assert sum(psy[k] for k in tolerances.KANDIDATEN_GEWICHT_SCHLUESSEL) == pytest.approx(1.0)


def test_track_gewichtsschreiben_erhaelt_andere_bekannte_nutzertoleranzen(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    datei.write_text(json.dumps({
        "Psytrance": {
            "groove_sim_floor": 0.73,
            "bass_delta_max": 4.25,
            "legacy_feld": "bleibt",
        }
    }), encoding="utf-8")

    tolerances.write_overrides_atomically(track_gewichte={"groove_weight": 0.20})

    psy = json.loads(datei.read_text(encoding="utf-8"))["Psytrance"]
    assert psy["groove_sim_floor"] == pytest.approx(0.73)
    assert psy["bass_delta_max"] == pytest.approx(4.25)
    assert psy["legacy_feld"] == "bleibt"


def test_write_overrides_atomically_replace_fehler_belaesst_alte_datei(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    vorher = b'{"vorher": true}\n'
    datei.write_bytes(vorher)
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    monkeypatch.setattr(
        tolerances.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("gesperrt"))
    )

    with pytest.raises(OSError, match="gesperrt"):
        tolerances.write_overrides_atomically(
            {"groove_weight": 0.20},
            {"kandidaten_loudness_weight": 0.20},
        )

    assert datei.read_bytes() == vorher
    assert list(tmp_path.glob(".transition_tolerances.json.*.tmp")) == []


def test_remove_candidate_overrides_ist_atomar_und_bewahrt_trackwerte(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    vorher = {
        "Psytrance": {
            "groove_weight": 0.25,
            "bass_delta_max": 4.25,
            "kandidaten_groove_weight": 0.20,
            "kandidaten_loudness_weight": 0.10,
        },
        "fremder_metadatenblock": {"bleibt": True},
    }
    datei.write_text(json.dumps(vorher), encoding="utf-8")
    replace_original = tolerances.os.replace
    replace_aufrufe = []
    invalidierungen = []

    def replace_spy(quelle, ziel):
        replace_aufrufe.append((quelle, ziel))
        return replace_original(quelle, ziel)

    monkeypatch.setattr(tolerances.os, "replace", replace_spy)
    monkeypatch.setattr(
        tolerances, "_leere_paar_cache", lambda: invalidierungen.append(True)
    )

    assert tolerances.remove_candidate_overrides() is True

    assert len(replace_aufrufe) == 1
    assert invalidierungen == [True]
    nachher = json.loads(datei.read_text(encoding="utf-8"))
    assert nachher["Psytrance"] == {
        "groove_weight": 0.25,
        "bass_delta_max": 4.25,
    }
    assert nachher["fremder_metadatenblock"] == {"bleibt": True}


def test_remove_candidate_overrides_belaesst_kaputtes_json_unveraendert(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    vorher = b"{ kaputt"
    datei.write_bytes(vorher)
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    with pytest.raises(ValueError, match="ungueltiges JSON"):
        tolerances.remove_candidate_overrides()

    assert datei.read_bytes() == vorher


def test_write_belaesst_kaputtes_json_unveraendert_ohne_replace(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    vorher = b"{ kaputt"
    datei.write_bytes(vorher)
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    replace = []
    monkeypatch.setattr(tolerances.os, "replace", lambda *args: replace.append(args))

    with pytest.raises(ValueError, match="ungueltiges JSON"):
        tolerances.write_override_kandidaten({"kandidaten_groove_weight": 0.20})

    assert replace == []
    assert datei.read_bytes() == vorher


def test_partielle_candidate_api_ergaenzt_fuenf_sichtbare_aus_einem_snapshot(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    snapshot = load_tolerances()
    aufrufe = []

    def load_spy():
        aufrufe.append(True)
        return snapshot

    monkeypatch.setattr(tolerances, "_lade_toleranzen_unter_lock", load_spy)
    tolerances.write_override_kandidaten({"kandidaten_groove_weight": 0.20})

    assert len(aufrufe) == 1
    daten = json.loads(datei.read_text(encoding="utf-8"))
    referenz = snapshot[CANONICAL_GENRES[0]]
    for genre in CANONICAL_GENRES:
        eintrag = daten[genre]
        assert eintrag["kandidaten_groove_weight"] == pytest.approx(0.20)
        for key in tolerances.SICHTBARE_KANDIDATEN_GEWICHT_SCHLUESSEL:
            if key != "kandidaten_groove_weight":
                assert eintrag[key] == pytest.approx(referenz[key])
        assert sum(
            eintrag[key] for key in tolerances.KANDIDATEN_GEWICHT_SCHLUESSEL
        ) == pytest.approx(1.0, abs=1e-12)


def test_versteckte_candidate_gewichte_behalten_je_genre_eigene_verhaeltnisse(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    snapshot = load_tolerances()
    genre_a, genre_b = CANONICAL_GENRES[:2]
    hidden = tolerances.VERSTECKTE_KANDIDATEN_GEWICHT_SCHLUESSEL
    snapshot[genre_a][hidden[0]], snapshot[genre_a][hidden[1]] = 0.30, 0.10
    snapshot[genre_b][hidden[0]], snapshot[genre_b][hidden[1]] = 0.10, 0.30
    monkeypatch.setattr(tolerances, "_lade_toleranzen_unter_lock", lambda: snapshot)

    tolerances.write_override_kandidaten({"kandidaten_loudness_weight": 0.10})

    daten = json.loads(datei.read_text(encoding="utf-8"))
    assert daten[genre_a][hidden[0]] / daten[genre_a][hidden[1]] == pytest.approx(3.0)
    assert daten[genre_b][hidden[0]] / daten[genre_b][hidden[1]] == pytest.approx(1 / 3)


@pytest.mark.parametrize("wert", [float("nan"), float("inf"), -0.01, True])
def test_candidate_api_verwirft_nicht_endliche_oder_negative_werte_ohne_replace(
    tmp_path, monkeypatch, wert
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    replace = []
    monkeypatch.setattr(tolerances.os, "replace", lambda *args: replace.append(args))

    with pytest.raises(ValueError):
        tolerances.write_override_kandidaten({"kandidaten_groove_weight": wert})

    assert replace == []
    assert not datei.exists()


def test_candidate_api_verwirft_nullrest_ohne_replace(tmp_path, monkeypatch):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    replace = []
    monkeypatch.setattr(tolerances.os, "replace", lambda *args: replace.append(args))

    with pytest.raises(ValueError, match="muss < 1.0 sein"):
        tolerances.write_override_kandidaten({"kandidaten_groove_weight": 1.0})

    assert replace == []
    assert not datei.exists()


def test_fehlendes_snapshot_genre_verhindert_replace(tmp_path, monkeypatch):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    snapshot = load_tolerances()
    snapshot.pop(CANONICAL_GENRES[-1])
    monkeypatch.setattr(tolerances, "_lade_toleranzen_unter_lock", lambda: snapshot)
    replace = []
    monkeypatch.setattr(tolerances.os, "replace", lambda *args: replace.append(args))

    with pytest.raises(ValueError, match=CANONICAL_GENRES[-1]):
        tolerances.write_override_kandidaten({"kandidaten_groove_weight": 0.20})

    assert replace == []
    assert not datei.exists()


def test_leere_versteckte_genrebasis_verhindert_replace(tmp_path, monkeypatch):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    snapshot = load_tolerances()
    genre = CANONICAL_GENRES[-1]
    for key in tolerances.VERSTECKTE_KANDIDATEN_GEWICHT_SCHLUESSEL:
        snapshot[genre][key] = 0.0
    monkeypatch.setattr(tolerances, "_lade_toleranzen_unter_lock", lambda: snapshot)
    replace = []
    monkeypatch.setattr(tolerances.os, "replace", lambda *args: replace.append(args))

    with pytest.raises(ValueError, match="Summe > 0"):
        tolerances.write_override_kandidaten({"kandidaten_groove_weight": 0.20})

    assert replace == []
    assert not datei.exists()


def test_verstecktes_candidate_gewicht_ist_keine_oeffentliche_schreibquelle(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    with pytest.raises(ValueError, match="Unbekannte Kandidaten-Gewichte"):
        tolerances.write_override_kandidaten({"kandidaten_bpm_weight": 0.20})

    assert not datei.exists()


def test_entferne_override_invalidiert_nur_nach_erfolgreichem_delete(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    datei.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    invalidierungen = []
    monkeypatch.setattr(
        tolerances, "_leere_paar_cache", lambda: invalidierungen.append(True)
    )

    assert tolerances.entferne_override() is True
    assert tolerances.entferne_override() is False

    assert invalidierungen == [True]
    assert datei.read_text(encoding="utf-8") == "{}"
    assert tolerances._loeschmarke_pfad(datei).is_file()
    assert tolerances._lies_override_bytes(datei) is None


def test_fremder_write_nach_logischem_delete_ist_sofort_sichtbar(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    datei.write_bytes(b'{"Psytrance": {"brightness_delta_max": 10}}\n')
    tolerances.reset_cache()

    assert tolerances.entferne_override() is True
    fremd = b'{"Psytrance": {"brightness_delta_max": 11}}\n'
    datei.write_bytes(fremd)

    assert datei.read_bytes() == fremd
    assert tolerances.get_tolerances("Psytrance")["brightness_delta_max"] == 11


def test_candidate_commit_ist_sofort_lesbar_und_invalidiert_einmal(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    tolerances.reset_cache()
    assert tolerances.get_tolerances("Psytrance")["kandidaten_groove_weight"] != 0.20
    invalidierungen = []
    monkeypatch.setattr(
        tolerances, "_leere_paar_cache", lambda: invalidierungen.append(True)
    )

    tolerances.write_override_kandidaten({"kandidaten_groove_weight": 0.20})

    assert invalidierungen == [True]
    assert tolerances.get_tolerances("Psytrance")["kandidaten_groove_weight"] == pytest.approx(0.20)


def test_replace_fehler_invalidiert_keinen_cache(tmp_path, monkeypatch):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    invalidierungen = []
    monkeypatch.setattr(
        tolerances, "_leere_paar_cache", lambda: invalidierungen.append(True)
    )
    monkeypatch.setattr(
        tolerances.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("gesperrt")),
    )

    with pytest.raises(OSError, match="gesperrt"):
        tolerances.write_override_kandidaten({"kandidaten_groove_weight": 0.20})

    assert invalidierungen == []


def test_pair_cache_fehler_wird_nach_commit_nicht_weitergereicht(
    tmp_path, monkeypatch, caplog
):
    from hpg_core import playlist, tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    with monkeypatch.context() as kontext:
        kontext.setattr(
            playlist,
            "reset_pair_candidate_cache",
            lambda: (_ for _ in ()).throw(RuntimeError("nur Cache")),
        )
        tolerances.write_override_kandidaten({"kandidaten_groove_weight": 0.20})

    assert datei.is_file()
    assert "Paar-Kandidaten-Cache konnte nicht geleert werden: nur Cache" in caplog.text


def test_externer_write_ist_ohne_reset_im_getter_sichtbar(tmp_path, monkeypatch):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    tolerances.reset_cache()
    vorher = tolerances.get_tolerances("Psytrance")["brightness_delta_max"]
    datei.write_text(
        json.dumps({"Psytrance": {"brightness_delta_max": vorher + 1.0}}),
        encoding="utf-8",
    )

    assert tolerances.get_tolerances("Psytrance")["brightness_delta_max"] == pytest.approx(
        vorher + 1.0
    )


def test_externer_replace_zwischen_read_und_signatur_cached_nur_neustand(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    datei.write_text(
        json.dumps({"Psytrance": {"brightness_delta_max": 10.0}}),
        encoding="utf-8",
    )
    tolerances.reset_cache()
    echtes_laden = tolerances._lade_toleranzen_unter_lock
    aufrufe = 0

    def laden_mit_externem_replace():
        nonlocal aufrufe
        aufrufe += 1
        ergebnis = echtes_laden()
        if aufrufe == 1:
            temp = tmp_path / "tolerances.extern.tmp"
            temp.write_text(
                json.dumps({"Psytrance": {"brightness_delta_max": 11.0}}),
                encoding="utf-8",
            )
            os.replace(temp, datei)
        return ergebnis

    monkeypatch.setattr(
        tolerances, "_lade_toleranzen_unter_lock", laden_mit_externem_replace
    )

    geladen = tolerances.load_tolerances()

    assert aufrufe == 2
    assert geladen["Psytrance"]["brightness_delta_max"] == pytest.approx(11.0)
    assert tolerances.get_tolerances("Psytrance")["brightness_delta_max"] == pytest.approx(
        11.0
    )
    assert tolerances._cache_signature == tolerances._override_signatur(datei)


def test_wiederholt_instabiler_toleranz_read_schlaegt_begrenzt_fehl(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    tolerances.reset_cache()
    zaehler = 0

    def wechselnde_signatur(_pfad):
        nonlocal zaehler
        zaehler += 1
        return (zaehler,)

    monkeypatch.setattr(tolerances, "_override_signatur", wechselnde_signatur)

    with pytest.raises(RuntimeError, match="wiederholt veraendert"):
        tolerances.load_tolerances()

    assert zaehler == tolerances._STABILE_LESEVERSUCHE * 2
    assert tolerances._cache is None


def test_delete_ueberschreibt_nach_digestpruefung_keinen_fremden_zwischenstand(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    datei.write_bytes(b'{"Psytrance": {"brightness_delta_max": 10}}\n')
    fremd = b'{"fremd": {"bleibt": true}}\n'
    echtes_schreiben = tolerances._schreibe_loeschmarke_atomar

    def fremder_write_nach_erfolgreicher_digestpruefung(pfad, digest):
        datei.write_bytes(fremd)
        echtes_schreiben(pfad, digest)

    monkeypatch.setattr(
        tolerances,
        "_schreibe_loeschmarke_atomar",
        fremder_write_nach_erfolgreicher_digestpruefung,
    )

    with pytest.raises(RuntimeError, match="Delete fail-closed verworfen"):
        tolerances.entferne_override()

    assert datei.read_bytes() == fremd
    assert not tolerances._loeschmarke_pfad(datei).exists()


def test_delete_belaesst_kaputtes_json_bytegleich(tmp_path, monkeypatch):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    vorher = b"{ kaputt"
    datei.write_bytes(vorher)

    with pytest.raises(ValueError, match="ungueltiges JSON"):
        tolerances.entferne_override()

    assert datei.read_bytes() == vorher


def test_zwei_spawn_prozesse_verlieren_keine_unabhaengigen_gewichtskreise(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    ergebnis = context.Queue()
    prozesse = [
        context.Process(
            target=_prozess_aendert_toleranzen,
            args=(datei, start, ergebnis, modus),
        )
        for modus in ("track", "kandidaten")
    ]
    for prozess in prozesse:
        prozess.start()
    start.set()
    for prozess in prozesse:
        prozess.join(20)
        assert prozess.exitcode == 0
    assert [ergebnis.get(timeout=2) for _ in prozesse] == [None, None]

    daten = json.loads(datei.read_text(encoding="utf-8"))
    for genre in CANONICAL_GENRES:
        assert "groove_weight" in daten[genre]
        assert "kandidaten_loudness_weight" in daten[genre]


def test_spawn_write_remove_race_bewahrt_trackwerte_und_fremde_felder(
    tmp_path, monkeypatch
):
    from hpg_core import tolerances

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    tolerances.write_override_kandidaten({"kandidaten_loudness_weight": 0.20})
    daten = json.loads(datei.read_text(encoding="utf-8"))
    daten["plugin"] = {"tief": {"bleibt": True}}
    datei.write_text(json.dumps(daten), encoding="utf-8")

    context = multiprocessing.get_context("spawn")
    start = context.Event()
    ergebnis = context.Queue()
    prozesse = [
        context.Process(
            target=_prozess_aendert_toleranzen,
            args=(datei, start, ergebnis, modus),
        )
        for modus in ("track", "remove")
    ]
    for prozess in prozesse:
        prozess.start()
    start.set()
    for prozess in prozesse:
        prozess.join(20)
        assert prozess.exitcode == 0
    assert [ergebnis.get(timeout=2) for _ in prozesse] == [None, None]

    nachher = json.loads(datei.read_text(encoding="utf-8"))
    assert nachher["plugin"] == {"tief": {"bleibt": True}}
    for genre in CANONICAL_GENRES:
        assert "groove_weight" in nachher[genre]
        assert not set(tolerances.KANDIDATEN_GEWICHT_SCHLUESSEL).intersection(
            nachher[genre]
        )
